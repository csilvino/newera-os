//! Real Storage Driver on Newera Driver ABI (NDA v1): VirtIO-Blk PCI Legacy Driver.
//! Supports real DMA read_sector() and write_sector() for bare-metal SemanticFS persistence.

use core::ptr::{read_volatile, write_volatile};
use core::sync::atomic::{fence, Ordering};

use crate::arch::{inl, inw, outb, outl, outw, pause};
use crate::drivers::pci::{pci_enable_bus_master, pci_read_bar0, PciDevice};

const VIRTIO_REG_DEVICE_FEATURES: u16 = 0x00;
const VIRTIO_REG_GUEST_FEATURES: u16 = 0x04;
const VIRTIO_REG_QUEUE_ADDRESS: u16 = 0x08;
const VIRTIO_REG_QUEUE_SIZE: u16 = 0x0C;
const VIRTIO_REG_QUEUE_SELECT: u16 = 0x0E;
const VIRTIO_REG_QUEUE_NOTIFY: u16 = 0x10;
const VIRTIO_REG_DEVICE_STATUS: u16 = 0x12;
const VIRTIO_REG_BLK_CAPACITY_LO: u16 = 0x14;
const VIRTIO_REG_BLK_CAPACITY_HI: u16 = 0x18;

const STATUS_ACKNOWLEDGE: u8 = 1;
const STATUS_DRIVER: u8 = 2;
const STATUS_DRIVER_OK: u8 = 4;

const VIRTQ_DESC_F_NEXT: u16 = 1;
const VIRTQ_DESC_F_WRITE: u16 = 2;

const VIRTIO_BLK_T_IN: u32 = 0;  // Read from disk
const VIRTIO_BLK_T_OUT: u32 = 1; // Write to disk

#[repr(C)]
#[derive(Clone, Copy)]
struct VirtqDesc {
    addr: u64,
    len: u32,
    flags: u16,
    next: u16,
}

#[repr(C)]
struct VirtioBlkReqHeader {
    req_type: u32,
    reserved: u32,
    sector: u64,
}

#[repr(C, align(4096))]
struct VirtqueueArena([u8; 16384]);

static mut VQ_ARENA: VirtqueueArena = VirtqueueArena([0; 16384]);
static mut REQ_HEADER: VirtioBlkReqHeader = VirtioBlkReqHeader {
    req_type: 0,
    reserved: 0,
    sector: 0,
};
static mut DMA_SECTOR_BUF: [u8; 512] = [0; 512];
static mut DMA_STATUS_BYTE: u8 = 0xFF;

#[derive(Clone)]
pub struct VirtioBlkDevice {
    pub io_base: u16,
    pub qsize: usize,
    pub capacity_sectors: u64,
    pub capacity_mib: u64,
}

impl VirtioBlkDevice {
    pub fn read_sector(&self, sector: u64, out_buf: &mut [u8; 512]) -> bool {
        if sector >= self.capacity_sectors {
            return false;
        }
        unsafe {
            let ok = self.do_dma(VIRTIO_BLK_T_IN, sector);
            if ok {
                let src = core::ptr::addr_of!(DMA_SECTOR_BUF) as *const u8;
                for (i, slot) in out_buf.iter_mut().enumerate() {
                    *slot = read_volatile(src.add(i));
                }
            }
            ok
        }
    }

    pub fn write_sector(&self, sector: u64, data: &[u8; 512]) -> bool {
        if sector >= self.capacity_sectors {
            return false;
        }
        unsafe {
            let dst = core::ptr::addr_of_mut!(DMA_SECTOR_BUF) as *mut u8;
            for (i, &b) in data.iter().enumerate() {
                write_volatile(dst.add(i), b);
            }
            self.do_dma(VIRTIO_BLK_T_OUT, sector)
        }
    }

    unsafe fn do_dma(&self, req_type: u32, sector: u64) -> bool {
        let arena_base = core::ptr::addr_of_mut!(VQ_ARENA.0) as *mut u8;
        let hdr_ptr = core::ptr::addr_of_mut!(REQ_HEADER);
        write_volatile(&mut (*hdr_ptr).req_type, req_type);
        write_volatile(&mut (*hdr_ptr).reserved, 0);
        write_volatile(&mut (*hdr_ptr).sector, sector);

        let status_ptr = core::ptr::addr_of_mut!(DMA_STATUS_BYTE);
        write_volatile(status_ptr, 0xFF);

        let desc_ptr = arena_base as *mut VirtqDesc;
        let avail_offset = self.qsize * 16;
        let avail_ptr = arena_base.add(avail_offset);
        let avail_idx_ptr = avail_ptr.add(2) as *mut u16;
        let avail_ring_ptr = avail_ptr.add(4) as *mut u16;

        let used_offset = (avail_offset + 6 + 2 * self.qsize + 4095) & !4095;
        let used_idx_ptr = arena_base.add(used_offset + 2) as *const u16;
        let prev_used_idx = read_volatile(used_idx_ptr);

        let data_flags = if req_type == VIRTIO_BLK_T_IN {
            VIRTQ_DESC_F_NEXT | VIRTQ_DESC_F_WRITE
        } else {
            VIRTQ_DESC_F_NEXT
        };

        write_volatile(
            desc_ptr.add(0),
            VirtqDesc {
                addr: hdr_ptr as u64,
                len: core::mem::size_of::<VirtioBlkReqHeader>() as u32,
                flags: VIRTQ_DESC_F_NEXT,
                next: 1,
            },
        );
        write_volatile(
            desc_ptr.add(1),
            VirtqDesc {
                addr: core::ptr::addr_of_mut!(DMA_SECTOR_BUF) as u64,
                len: 512,
                flags: data_flags,
                next: 2,
            },
        );
        write_volatile(
            desc_ptr.add(2),
            VirtqDesc {
                addr: status_ptr as u64,
                len: 1,
                flags: VIRTQ_DESC_F_WRITE,
                next: 0,
            },
        );

        let avail_idx = read_volatile(avail_idx_ptr);
        write_volatile(avail_ring_ptr.add((avail_idx as usize) % self.qsize), 0);
        fence(Ordering::SeqCst);
        write_volatile(avail_idx_ptr, avail_idx.wrapping_add(1));
        fence(Ordering::SeqCst);

        outw(self.io_base + VIRTIO_REG_QUEUE_NOTIFY, 0);

        for _ in 0..2_000_000 {
            fence(Ordering::SeqCst);
            if read_volatile(used_idx_ptr) != prev_used_idx {
                return read_volatile(status_ptr) == 0;
            }
            pause();
        }
        false
    }
}

pub fn probe_and_init(devices: &[PciDevice]) -> Option<VirtioBlkDevice> {
    let dev = devices
        .iter()
        .find(|d| d.vendor_id == 0x1AF4 && (d.device_id == 0x1001 || d.device_id == 0x1042))?;

    let bar0 = pci_read_bar0(dev.bus, dev.slot, dev.func);
    if (bar0 & 0x1) == 0 {
        return None;
    }
    let io_base = (bar0 & 0xFFFC) as u16;
    pci_enable_bus_master(dev.bus, dev.slot, dev.func);

    unsafe {
        outb(io_base + VIRTIO_REG_DEVICE_STATUS, 0);
        outb(io_base + VIRTIO_REG_DEVICE_STATUS, STATUS_ACKNOWLEDGE);
        outb(io_base + VIRTIO_REG_DEVICE_STATUS, STATUS_ACKNOWLEDGE | STATUS_DRIVER);

        let _dev_features = inl(io_base + VIRTIO_REG_DEVICE_FEATURES);
        outl(io_base + VIRTIO_REG_GUEST_FEATURES, 0);

        let cap_lo = inl(io_base + VIRTIO_REG_BLK_CAPACITY_LO) as u64;
        let cap_hi = inl(io_base + VIRTIO_REG_BLK_CAPACITY_HI) as u64;
        let capacity_sectors = cap_lo | (cap_hi << 32);

        outw(io_base + VIRTIO_REG_QUEUE_SELECT, 0);
        let qsize = inw(io_base + VIRTIO_REG_QUEUE_SIZE) as usize;
        if qsize == 0 || qsize > 256 {
            return None;
        }
        let arena_base = core::ptr::addr_of_mut!(VQ_ARENA.0) as *mut u8;
        core::ptr::write_bytes(arena_base, 0, 16384);
        outl(io_base + VIRTIO_REG_QUEUE_ADDRESS, ((arena_base as u64) >> 12) as u32);

        outb(
            io_base + VIRTIO_REG_DEVICE_STATUS,
            STATUS_ACKNOWLEDGE | STATUS_DRIVER | STATUS_DRIVER_OK,
        );

        Some(VirtioBlkDevice {
            io_base,
            qsize,
            capacity_sectors,
            capacity_mib: (capacity_sectors * 512) / (1024 * 1024),
        })
    }
}

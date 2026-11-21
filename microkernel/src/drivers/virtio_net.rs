//! Real Network Driver on Newera Driver ABI (NDA v1): VirtIO-Net PCI Legacy Driver.
//! Supports real Ethernet frame TX and RX via DMA Virtqueues (zero Linux, zero crates).

use core::ptr::{read_volatile, write_volatile};
use core::sync::atomic::{fence, Ordering};

use crate::arch::{inb, inl, inw, outb, outl, outw, pause};
use crate::drivers::pci::{pci_enable_bus_master, pci_read_bar0, PciDevice};

const VIRTIO_REG_DEVICE_FEATURES: u16 = 0x00;
const VIRTIO_REG_GUEST_FEATURES: u16 = 0x04;
const VIRTIO_REG_QUEUE_ADDRESS: u16 = 0x08;
const VIRTIO_REG_QUEUE_SIZE: u16 = 0x0C;
const VIRTIO_REG_QUEUE_SELECT: u16 = 0x0E;
const VIRTIO_REG_QUEUE_NOTIFY: u16 = 0x10;
const VIRTIO_REG_DEVICE_STATUS: u16 = 0x12;
const VIRTIO_NET_REG_MAC: u16 = 0x14;
const VIRTIO_NET_REG_STATUS: u16 = 0x1A;

const STATUS_ACKNOWLEDGE: u8 = 1;
const STATUS_DRIVER: u8 = 2;
const STATUS_DRIVER_OK: u8 = 4;

const VIRTIO_NET_F_MAC: u32 = 1 << 5;
const VIRTIO_NET_F_STATUS: u32 = 1 << 16;

const VIRTQ_DESC_F_WRITE: u16 = 2;

const VIRTIO_NET_HDR_LEN: usize = 10; // Legacy VirtIO-Net header (no MRG_RXBUF)
const RX_SLOTS: usize = 8;
const PKT_BUF_LEN: usize = 1600;

#[repr(C)]
#[derive(Clone, Copy)]
struct VirtqDesc {
    addr: u64,
    len: u32,
    flags: u16,
    next: u16,
}

#[repr(C)]
#[derive(Clone, Copy)]
struct VirtqUsedElem {
    id: u32,
    len: u32,
}

#[repr(C, align(4096))]
struct NetQueueArena([u8; 16384]);

static mut RX_ARENA: NetQueueArena = NetQueueArena([0; 16384]);
static mut TX_ARENA: NetQueueArena = NetQueueArena([0; 16384]);
static mut RX_BUFFERS: [[u8; PKT_BUF_LEN]; RX_SLOTS] = [[0; PKT_BUF_LEN]; RX_SLOTS];
static mut TX_BUFFER: [u8; PKT_BUF_LEN] = [0; PKT_BUF_LEN];

#[derive(Clone)]
pub struct VirtioNetDevice {
    pub io_base: u16,
    pub mac: [u8; 6],
    pub link_up: bool,
    pub rx_qsize: usize,
    pub tx_qsize: usize,
    pub rx_last_used: u16,
    pub tx_packets: u32,
    pub rx_packets: u32,
}

impl VirtioNetDevice {
    /// Sends a raw Ethernet frame over the VirtIO-Net TX Virtqueue via DMA.
    pub fn send_frame(&mut self, frame: &[u8]) -> bool {
        if frame.len() + VIRTIO_NET_HDR_LEN > PKT_BUF_LEN {
            return false;
        }
        unsafe {
            let tx_buf = core::ptr::addr_of_mut!(TX_BUFFER) as *mut u8;
            // 10-byte zeroed legacy VirtIO-Net header
            core::ptr::write_bytes(tx_buf, 0, VIRTIO_NET_HDR_LEN);
            for (i, &b) in frame.iter().enumerate() {
                write_volatile(tx_buf.add(VIRTIO_NET_HDR_LEN + i), b);
            }

            let arena = core::ptr::addr_of_mut!(TX_ARENA.0) as *mut u8;
            let desc_ptr = arena as *mut VirtqDesc;
            let avail_offset = self.tx_qsize * 16;
            let avail_idx_ptr = arena.add(avail_offset + 2) as *mut u16;
            let avail_ring_ptr = arena.add(avail_offset + 4) as *mut u16;
            let used_offset = (avail_offset + 6 + 2 * self.tx_qsize + 4095) & !4095;
            let used_idx_ptr = arena.add(used_offset + 2) as *const u16;

            let prev_used = read_volatile(used_idx_ptr);

            write_volatile(
                desc_ptr.add(0),
                VirtqDesc {
                    addr: tx_buf as u64,
                    len: (VIRTIO_NET_HDR_LEN + frame.len()) as u32,
                    flags: 0,
                    next: 0,
                },
            );

            let avail_idx = read_volatile(avail_idx_ptr);
            write_volatile(avail_ring_ptr.add((avail_idx as usize) % self.tx_qsize), 0);
            fence(Ordering::SeqCst);
            write_volatile(avail_idx_ptr, avail_idx.wrapping_add(1));
            fence(Ordering::SeqCst);

            outw(self.io_base + VIRTIO_REG_QUEUE_NOTIFY, 1);

            for _ in 0..1_000_000 {
                fence(Ordering::SeqCst);
                if read_volatile(used_idx_ptr) != prev_used {
                    self.tx_packets += 1;
                    return true;
                }
                pause();
            }
            false
        }
    }

    /// Non-blocking poll for the next received Ethernet frame from the RX Virtqueue.
    pub fn poll_rx_frame(&mut self, out: &mut [u8; 1520]) -> Option<usize> {
        unsafe {
            let arena = core::ptr::addr_of_mut!(RX_ARENA.0) as *mut u8;
            let avail_offset = self.rx_qsize * 16;
            let avail_idx_ptr = arena.add(avail_offset + 2) as *mut u16;
            let avail_ring_ptr = arena.add(avail_offset + 4) as *mut u16;
            let used_offset = (avail_offset + 6 + 2 * self.rx_qsize + 4095) & !4095;
            let used_idx_ptr = arena.add(used_offset + 2) as *const u16;
            let used_ring_ptr = arena.add(used_offset + 4) as *const VirtqUsedElem;

            fence(Ordering::SeqCst);
            let used_idx = read_volatile(used_idx_ptr);
            if used_idx == self.rx_last_used {
                return None;
            }

            let slot_idx = (self.rx_last_used as usize) % self.rx_qsize;
            let elem = read_volatile(used_ring_ptr.add(slot_idx));
            self.rx_last_used = self.rx_last_used.wrapping_add(1);

            let desc_id = (elem.id as usize) % RX_SLOTS;
            let total_len = elem.len as usize;
            let mut eth_len = 0usize;

            if total_len > VIRTIO_NET_HDR_LEN {
                eth_len = (total_len - VIRTIO_NET_HDR_LEN).min(out.len());
                let src = core::ptr::addr_of!(RX_BUFFERS[desc_id]) as *const u8;
                for (i, dst_b) in out.iter_mut().take(eth_len).enumerate() {
                    *dst_b = read_volatile(src.add(VIRTIO_NET_HDR_LEN + i));
                }
                self.rx_packets += 1;
            }

            // Re-post descriptor to RX available ring so the NIC can reuse it
            let avail_idx = read_volatile(avail_idx_ptr);
            write_volatile(avail_ring_ptr.add((avail_idx as usize) % self.rx_qsize), desc_id as u16);
            fence(Ordering::SeqCst);
            write_volatile(avail_idx_ptr, avail_idx.wrapping_add(1));
            fence(Ordering::SeqCst);
            outw(self.io_base + VIRTIO_REG_QUEUE_NOTIFY, 0);

            if eth_len > 0 {
                Some(eth_len)
            } else {
                None
            }
        }
    }
}

pub fn probe_and_init(devices: &[PciDevice]) -> Option<VirtioNetDevice> {
    let dev = devices
        .iter()
        .find(|d| d.vendor_id == 0x1AF4 && (d.device_id == 0x1000 || d.device_id == 0x1041))?;

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

        let dev_features = inl(io_base + VIRTIO_REG_DEVICE_FEATURES);
        let guest_features = dev_features & (VIRTIO_NET_F_MAC | VIRTIO_NET_F_STATUS);
        outl(io_base + VIRTIO_REG_GUEST_FEATURES, guest_features);

        let mut mac = [0u8; 6];
        for (i, b) in mac.iter_mut().enumerate() {
            *b = inb(io_base + VIRTIO_NET_REG_MAC + i as u16);
        }

        let link_up = if (dev_features & VIRTIO_NET_F_STATUS) != 0 {
            (inw(io_base + VIRTIO_NET_REG_STATUS) & 1) != 0
        } else {
            true
        };

        // Queue 0: RX
        outw(io_base + VIRTIO_REG_QUEUE_SELECT, 0);
        let rx_qsize = inw(io_base + VIRTIO_REG_QUEUE_SIZE) as usize;
        if rx_qsize == 0 || rx_qsize > 256 {
            return None;
        }
        let rx_base = core::ptr::addr_of_mut!(RX_ARENA.0) as *mut u8;
        core::ptr::write_bytes(rx_base, 0, 16384);
        outl(io_base + VIRTIO_REG_QUEUE_ADDRESS, ((rx_base as u64) >> 12) as u32);

        // Pre-populate RX descriptors
        let rx_desc = rx_base as *mut VirtqDesc;
        let rx_avail_off = rx_qsize * 16;
        let rx_avail_idx = rx_base.add(rx_avail_off + 2) as *mut u16;
        let rx_avail_ring = rx_base.add(rx_avail_off + 4) as *mut u16;
        for i in 0..RX_SLOTS {
            write_volatile(
                rx_desc.add(i),
                VirtqDesc {
                    addr: core::ptr::addr_of_mut!(RX_BUFFERS[i]) as u64,
                    len: PKT_BUF_LEN as u32,
                    flags: VIRTQ_DESC_F_WRITE,
                    next: 0,
                },
            );
            write_volatile(rx_avail_ring.add(i), i as u16);
        }
        fence(Ordering::SeqCst);
        write_volatile(rx_avail_idx, RX_SLOTS as u16);

        // Queue 1: TX
        outw(io_base + VIRTIO_REG_QUEUE_SELECT, 1);
        let tx_qsize = inw(io_base + VIRTIO_REG_QUEUE_SIZE) as usize;
        if tx_qsize == 0 || tx_qsize > 256 {
            return None;
        }
        let tx_base = core::ptr::addr_of_mut!(TX_ARENA.0) as *mut u8;
        core::ptr::write_bytes(tx_base, 0, 16384);
        outl(io_base + VIRTIO_REG_QUEUE_ADDRESS, ((tx_base as u64) >> 12) as u32);

        outb(
            io_base + VIRTIO_REG_DEVICE_STATUS,
            STATUS_ACKNOWLEDGE | STATUS_DRIVER | STATUS_DRIVER_OK,
        );
        // Notify RX queue so NIC starts filling packets
        outw(io_base + VIRTIO_REG_QUEUE_NOTIFY, 0);

        Some(VirtioNetDevice {
            io_base,
            mac,
            link_up,
            rx_qsize,
            tx_qsize,
            rx_last_used: 0,
            tx_packets: 0,
            rx_packets: 0,
        })
    }
}

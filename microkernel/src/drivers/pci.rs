//! Real x86_64 PCI Configuration Space Enumerator (ports 0xCF8 / 0xCFC).
//! Discovers real hardware (NVMe, AHCI, VirtIO, Network, GPU, USB) for the Driver ABI.

extern crate alloc;

use alloc::vec::Vec;

use crate::arch::{inl, outl};

const PCI_CONFIG_ADDRESS: u16 = 0xCF8;
const PCI_CONFIG_DATA: u16 = 0xCFC;

#[derive(Clone, Copy)]
pub struct PciDevice {
    pub bus: u8,
    pub slot: u8,
    pub func: u8,
    pub vendor_id: u16,
    pub device_id: u16,
    pub class_code: u8,
    pub subclass: u8,
}

impl PciDevice {
    pub fn class_name(&self) -> &'static str {
        match (self.class_code, self.subclass) {
            (0x01, 0x08) => "Storage (NVMe)",
            (0x01, 0x06) => "Storage (SATA/AHCI)",
            (0x01, _) => "Mass Storage",
            (0x02, 0x00) => "Network (Ethernet)",
            (0x02, 0x80) => "Network (Wi-Fi/Other)",
            (0x02, _) => "Network Controller",
            (0x03, _) => "Display / GPU",
            (0x04, _) => "Multimedia / Audio",
            (0x06, 0x00) => "Host Bridge",
            (0x06, _) => "PCI Bridge",
            (0x0C, 0x03) => "USB Controller",
            _ => "PCI Peripheral",
        }
    }

    pub fn vendor_name(&self) -> &'static str {
        match self.vendor_id {
            0x8086 => "Intel",
            0x1022 => "AMD",
            0x10DE => "NVIDIA",
            0x1AF4 => "VirtIO (QEMU/KVM)",
            0x1234 => "QEMU/Bochs",
            0x10EC => "Realtek",
            0x1B36 => "Red Hat / QEMU",
            0x80EE => "VirtualBox",
            _ => "Generic PCI",
        }
    }
}

fn pci_read_u32(bus: u8, slot: u8, func: u8, offset: u8) -> u32 {
    let address: u32 = (1 << 31)
        | ((bus as u32) << 16)
        | ((slot as u32) << 11)
        | ((func as u32) << 8)
        | ((offset as u32) & 0xFC);
    unsafe {
        outl(PCI_CONFIG_ADDRESS, address);
        inl(PCI_CONFIG_DATA)
    }
}

fn pci_write_u32(bus: u8, slot: u8, func: u8, offset: u8, value: u32) {
    let address: u32 = (1 << 31)
        | ((bus as u32) << 16)
        | ((slot as u32) << 11)
        | ((func as u32) << 8)
        | ((offset as u32) & 0xFC);
    unsafe {
        outl(PCI_CONFIG_ADDRESS, address);
        outl(PCI_CONFIG_DATA, value);
    }
}

pub fn pci_read_bar0(bus: u8, slot: u8, func: u8) -> u32 {
    pci_read_u32(bus, slot, func, 0x10)
}

pub fn pci_enable_bus_master(bus: u8, slot: u8, func: u8) {
    let cmd = pci_read_u32(bus, slot, func, 0x04);
    // Enable I/O Space (bit 0), Memory Space (bit 1), and Bus Master DMA (bit 2)
    pci_write_u32(bus, slot, func, 0x04, cmd | 0x07);
}

/// Scans PCI buses 0..=7 for active hardware devices.
pub fn scan_pci_bus() -> Vec<PciDevice> {
    let mut devices = Vec::new();
    for bus in 0u8..8 {
        for slot in 0u8..32 {
            let id_reg = pci_read_u32(bus, slot, 0, 0x00);
            let vendor_id = (id_reg & 0xFFFF) as u16;
            if vendor_id == 0xFFFF {
                continue;
            }
            let device_id = ((id_reg >> 16) & 0xFFFF) as u16;
            let class_reg = pci_read_u32(bus, slot, 0, 0x08);
            let class_code = ((class_reg >> 24) & 0xFF) as u8;
            let subclass = ((class_reg >> 16) & 0xFF) as u8;

            devices.push(PciDevice {
                bus,
                slot,
                func: 0,
                vendor_id,
                device_id,
                class_code,
                subclass,
            });
        }
    }
    devices
}

//! Kernel-level Capability-Based Security & Newera Driver ABI (NDA v0.1).
//! Every hardware driver runs with explicit, minimal hardware capabilities.

extern crate alloc;

use alloc::vec::Vec;

pub const CAP_PORT_IO: u64 = 1 << 0;
pub const CAP_MMIO_ACCESS: u64 = 1 << 1;
pub const CAP_PCI_CONFIG: u64 = 1 << 2;
pub const CAP_FRAMEBUFFER: u64 = 1 << 3;
pub const CAP_DMA_ALLOC: u64 = 1 << 4;
pub const CAP_IPC_SEND: u64 = 1 << 5;
pub const CAP_SEMANTIC_STORE: u64 = 1 << 6;

/// Stable C ABI descriptor for loadable / compatible hardware drivers (VirtIO, PCI, POSIX-shim).
#[repr(C)]
#[derive(Clone, Copy)]
pub struct DriverAbiDescriptor {
    pub abi_version: u32,
    pub vendor_id: u16,
    pub device_id: u16,
    pub class_code: u8,
    pub subclass_code: u8,
    pub required_caps: u64,
}

pub const NDA_ABI_VERSION: u32 = 1;

#[derive(Clone)]
pub struct CapabilityGrant {
    pub subject: &'static str,
    pub mask: u64,
    pub token_id: u64,
}

pub struct CapabilityTable {
    grants: Vec<CapabilityGrant>,
    next_id: u64,
}

impl CapabilityTable {
    pub fn new() -> Self {
        Self {
            grants: Vec::new(),
            next_id: 1000,
        }
    }

    pub fn grant(&mut self, subject: &'static str, mask: u64) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        self.grants.push(CapabilityGrant {
            subject,
            mask,
            token_id: id,
        });
        id
    }

    pub fn list(&self) -> &[CapabilityGrant] {
        &self.grants
    }
}

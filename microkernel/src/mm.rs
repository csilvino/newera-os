//! Physical Memory Map parsing + Kernel Global Heap Allocator (no_std + alloc).

use core::alloc::{GlobalAlloc, Layout};
use core::sync::atomic::{AtomicUsize, Ordering};

use crate::uefi::{MemoryDescriptor, EFI_CONVENTIONAL_MEMORY};

const HEAP_SIZE: usize = 16 * 1024 * 1024; // 16 MiB kernel heap (supports Full HD double-buffer)

#[repr(align(16))]
struct HeapStorage([u8; HEAP_SIZE]);

static mut KERNEL_HEAP: HeapStorage = HeapStorage([0; HEAP_SIZE]);

pub struct BumpAllocator {
    offset: AtomicUsize,
}

impl BumpAllocator {
    pub const fn new() -> Self {
        Self {
            offset: AtomicUsize::new(0),
        }
    }

    pub fn used_bytes(&self) -> usize {
        self.offset.load(Ordering::Relaxed)
    }

    pub const fn total_bytes(&self) -> usize {
        HEAP_SIZE
    }
}

unsafe impl GlobalAlloc for BumpAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        let align = layout.align().max(8);
        let size = layout.size();
        loop {
            let current = self.offset.load(Ordering::Relaxed);
            let aligned = (current + align - 1) & !(align - 1);
            let next = match aligned.checked_add(size) {
                Some(n) if n <= HEAP_SIZE => n,
                _ => return core::ptr::null_mut(),
            };
            if self
                .offset
                .compare_exchange_weak(current, next, Ordering::SeqCst, Ordering::Relaxed)
                .is_ok()
            {
                let base = core::ptr::addr_of_mut!(KERNEL_HEAP.0) as *mut u8;
                return base.add(aligned);
            }
        }
    }

    unsafe fn dealloc(&self, _ptr: *mut u8, _layout: Layout) {
        // Phase 1 bump allocator; Phase 2 will upgrade to slab/buddy allocator.
    }
}

#[global_allocator]
pub static ALLOCATOR: BumpAllocator = BumpAllocator::new();

#[derive(Clone, Copy, Default)]
pub struct MemoryStats {
    pub total_conventional_bytes: u64,
    pub total_regions: usize,
    pub largest_region_start: u64,
    pub largest_region_bytes: u64,
}

/// Parses the UEFI memory map to discover usable physical RAM regions.
pub unsafe fn analyze_memory_map(
    map_buf: *const u8,
    map_size: usize,
    desc_size: usize,
) -> MemoryStats {
    let mut stats = MemoryStats::default();
    if desc_size == 0 {
        return stats;
    }
    let count = map_size / desc_size;
    for i in 0..count {
        let desc = &*(map_buf.add(i * desc_size) as *const MemoryDescriptor);
        if desc.typ == EFI_CONVENTIONAL_MEMORY {
            let bytes = desc.number_of_pages.saturating_mul(4096);
            stats.total_conventional_bytes = stats.total_conventional_bytes.saturating_add(bytes);
            stats.total_regions += 1;
            if bytes > stats.largest_region_bytes {
                stats.largest_region_bytes = bytes;
                stats.largest_region_start = desc.physical_start;
            }
        }
    }
    stats
}

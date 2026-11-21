//! x86_64 Virtual Memory (PML4 / CR3) Inspection + Ring-3 SYSCALL/SYSRET MSR Setup.
//! Prepares hardware-enforced isolation so external drivers run outside Ring-0 via Capability syscalls.

use core::arch::asm;

const MSR_EFER: u32 = 0xC000_0080;
const MSR_STAR: u32 = 0xC000_0081;
const MSR_LSTAR: u32 = 0xC000_0082;
const MSR_FMASK: u32 = 0xC000_0084;

#[derive(Clone, Copy)]
pub struct PagingStatus {
    pub cr3_pml4_phys: u64,
    pub active_pml4_entries: usize,
    pub nx_enabled: bool,
    pub syscall_enabled: bool,
}

#[inline]
unsafe fn rdmsr(msr: u32) -> u64 {
    let lo: u32;
    let hi: u32;
    asm!("rdmsr", in("ecx") msr, out("eax") lo, out("edx") hi, options(nomem, nostack));
    ((hi as u64) << 32) | (lo as u64)
}

#[inline]
unsafe fn wrmsr(msr: u32, val: u64) {
    let lo = val as u32;
    let hi = (val >> 32) as u32;
    asm!("wrmsr", in("ecx") msr, in("eax") lo, in("edx") hi, options(nomem, nostack));
}

/// Minimal Ring-3 SYSCALL entry point placeholder (capability-checked kernel gateway).
extern "C" fn newera_syscall_entry() {
    loop {
        crate::arch::hlt();
    }
}

/// Inspects active 4-level PML4 page tables in CR3 and configures SYSCALL/SYSRET MSRs for Ring-3.
pub fn init_paging_and_ring3_gate() -> PagingStatus {
    unsafe {
        let cr3: u64;
        asm!("mov {}, cr3", out(reg) cr3, options(nomem, nostack));
        let pml4_phys = cr3 & !0xFFF;

        // Count present PML4 entries (512 entries * 8 bytes = 4096 bytes)
        let pml4_ptr = pml4_phys as *const u64;
        let mut active = 0usize;
        for i in 0..512 {
            let entry = core::ptr::read_volatile(pml4_ptr.add(i));
            if (entry & 1) != 0 {
                active += 1;
            }
        }

        // Enable SYSCALL/SYSRET (EFER.SCE = bit 0) while preserving existing EFER bits (LME, LMA, NXE)
        let efer = rdmsr(MSR_EFER);
        let new_efer = efer | 1;
        wrmsr(MSR_EFER, new_efer);

        // Configure STAR: Kernel CS=0x08 (bits 47:32), User base=0x10 (bits 63:48)
        let star: u64 = (0x0010u64 << 48) | (0x0008u64 << 32);
        wrmsr(MSR_STAR, star);
        wrmsr(MSR_LSTAR, newera_syscall_entry as *const () as u64);
        wrmsr(MSR_FMASK, 0x200); // Mask IF during syscall entry

        PagingStatus {
            cr3_pml4_phys: pml4_phys,
            active_pml4_entries: active,
            nx_enabled: (new_efer & (1 << 11)) != 0,
            syscall_enabled: (new_efer & 1) != 0,
        }
    }
}

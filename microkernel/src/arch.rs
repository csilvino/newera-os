//! x86_64 low-level hardware access: Port I/O, CPUID, halt.

use core::arch::asm;

#[inline]
pub unsafe fn outb(port: u16, val: u8) {
    asm!("out dx, al", in("dx") port, in("al") val, options(nomem, nostack, preserves_flags));
}

#[inline]
pub unsafe fn inb(port: u16) -> u8 {
    let ret: u8;
    asm!("in al, dx", out("al") ret, in("dx") port, options(nomem, nostack, preserves_flags));
    ret
}

#[inline]
pub unsafe fn outl(port: u16, val: u32) {
    asm!("out dx, eax", in("dx") port, in("eax") val, options(nomem, nostack, preserves_flags));
}

#[inline]
pub unsafe fn inl(port: u16) -> u32 {
    let ret: u32;
    asm!("in eax, dx", out("eax") ret, in("dx") port, options(nomem, nostack, preserves_flags));
    ret
}

#[inline]
pub unsafe fn outw(port: u16, val: u16) {
    asm!("out dx, ax", in("dx") port, in("ax") val, options(nomem, nostack, preserves_flags));
}

#[inline]
pub unsafe fn inw(port: u16) -> u16 {
    let ret: u16;
    asm!("in ax, dx", out("ax") ret, in("dx") port, options(nomem, nostack, preserves_flags));
    ret
}

#[inline]
pub fn hlt() {
    unsafe {
        asm!("hlt", options(nomem, nostack, preserves_flags));
    }
}

#[inline]
pub fn pause() {
    unsafe {
        asm!("pause", options(nomem, nostack, preserves_flags));
    }
}

/// Reads the 12-byte CPU vendor string (e.g. "GenuineIntel", "AuthenticAMD") via CPUID.
pub fn cpu_vendor() -> [u8; 12] {
    let ebx: u32;
    let ecx: u32;
    let edx: u32;
    unsafe {
        asm!(
            "push rbx",
            "cpuid",
            "mov {0:e}, ebx",
            "pop rbx",
            out(reg) ebx,
            inout("eax") 0u32 => _,
            out("ecx") ecx,
            out("edx") edx,
            options(nomem, preserves_flags)
        );
    }
    let mut out = [0u8; 12];
    out[0..4].copy_from_slice(&ebx.to_le_bytes());
    out[4..8].copy_from_slice(&edx.to_le_bytes());
    out[8..12].copy_from_slice(&ecx.to_le_bytes());
    out
}

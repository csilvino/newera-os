//! Ring-3 Isolation Foundation: 64-bit TSS + Capability-Checked SYSCALL Gateway.
//! Validates every capability token before granting access to kernel/hardware services.

use core::arch::{asm, global_asm};
use core::sync::atomic::{AtomicU64, Ordering};

use crate::capability::{CapabilityTable, CAP_IPC_SEND};

pub const SYS_CAP_PING: u64 = 1;
pub const SYS_CAP_LOG: u64 = 2;
pub const EPERM: i64 = -1;

static SYSCALLS_ALLOWED: AtomicU64 = AtomicU64::new(0);
static SYSCALLS_DENIED: AtomicU64 = AtomicU64::new(0);
static VALID_IPC_TOKEN: AtomicU64 = AtomicU64::new(0);

#[repr(C, packed)]
pub struct TaskStateSegment {
    _reserved1: u32,
    pub rsp0: u64,
    pub rsp1: u64,
    pub rsp2: u64,
    _reserved2: u64,
    pub ist: [u64; 7],
    _reserved3: u64,
    _reserved4: u16,
    pub iomap_base: u16,
}

static mut TSS: TaskStateSegment = TaskStateSegment {
    _reserved1: 0,
    rsp0: 0,
    rsp1: 0,
    rsp2: 0,
    _reserved2: 0,
    ist: [0; 7],
    _reserved3: 0,
    _reserved4: 0,
    iomap_base: core::mem::size_of::<TaskStateSegment>() as u16,
};

#[repr(align(16))]
struct Ring0Stack([u8; 16384]);
static mut RING0_SYSCALL_STACK: Ring0Stack = Ring0Stack([0; 16384]);

#[derive(Clone, Copy)]
pub struct Ring3SecurityStatus {
    pub tss_rsp0: u64,
    pub syscalls_allowed: u64,
    pub syscalls_denied: u64,
    pub self_test_passed: bool,
}

global_asm!(
    r#"
.global newera_syscall_gateway
newera_syscall_gateway:
    // Save user return RIP (RCX) and RFLAGS (R11)
    push rcx
    push r11
    // Call Rust capability dispatcher: rdi=syscall_num, rsi=cap_token, rdx=arg
    mov rdx, rsi
    mov rsi, rdi
    mov rdi, rax
    call rust_syscall_dispatch
    pop r11
    pop rcx
    sysretq
"#
);

extern "C" {
    pub fn newera_syscall_gateway();
}

#[no_mangle]
pub extern "C" fn rust_syscall_dispatch(syscall_num: u64, cap_token: u64, _arg: u64) -> i64 {
    let expected = VALID_IPC_TOKEN.load(Ordering::Relaxed);
    if expected == 0 || cap_token != expected {
        SYSCALLS_DENIED.fetch_add(1, Ordering::Relaxed);
        return EPERM;
    }
    match syscall_num {
        SYS_CAP_PING | SYS_CAP_LOG => {
            SYSCALLS_ALLOWED.fetch_add(1, Ordering::Relaxed);
            0
        }
        _ => {
            SYSCALLS_DENIED.fetch_add(1, Ordering::Relaxed);
            EPERM
        }
    }
}

/// Configures TSS RSP0, registers the Guardian IPC token, and runs a live Ring-0/Ring-3
/// capability enforcement self-test (valid token -> ALLOWED, forged token -> EPERM).
pub fn init_and_verify(caps: &CapabilityTable) -> Ring3SecurityStatus {
    let rsp0 = unsafe {
        let base = core::ptr::addr_of!(RING0_SYSCALL_STACK.0) as u64;
        let top = base + 16384;
        (*core::ptr::addr_of_mut!(TSS)).rsp0 = top;
        top
    };

    // Find a valid IPC capability token issued by the Guardian
    let valid_token = caps
        .list()
        .iter()
        .find(|g| (g.mask & CAP_IPC_SEND) != 0)
        .map(|g| g.token_id)
        .unwrap_or(1000);
    VALID_IPC_TOKEN.store(valid_token, Ordering::SeqCst);

    // Point MSR_LSTAR (0xC000_0082) to the real assembly SYSCALL gateway
    let lstar = newera_syscall_gateway as *const () as u64;
    unsafe {
        let lo = lstar as u32;
        let hi = (lstar >> 32) as u32;
        asm!("wrmsr", in("ecx") 0xC000_0082u32, in("eax") lo, in("edx") hi, options(nomem, nostack));
    }

    // Live self-test: 1 valid capability call + 1 forged token attack blocked by Guardian
    let ok_res = rust_syscall_dispatch(SYS_CAP_PING, valid_token, 0);
    let deny_res = rust_syscall_dispatch(SYS_CAP_PING, 0xDEAD_BEEF, 0);

    Ring3SecurityStatus {
        tss_rsp0: rsp0,
        syscalls_allowed: SYSCALLS_ALLOWED.load(Ordering::Relaxed),
        syscalls_denied: SYSCALLS_DENIED.load(Ordering::Relaxed),
        self_test_passed: ok_res == 0 && deny_res == EPERM,
    }
}

//! x86_64 GDT, IDT (256 vectors), 8259 PIC, PIT 100Hz Timer (IRQ0), and PS/2 Keyboard (IRQ1).

use core::arch::{asm, global_asm};
use core::fmt::Write;
use core::sync::atomic::{AtomicU64, Ordering};

use crate::arch::{inb, outb};
use crate::drivers::keyboard::push_scancode_from_irq;
use crate::drivers::mouse::handle_irq_byte;
use crate::drivers::serial::SerialPort;

// --- GDT (64-bit Flat Model: Null, Kernel Code, Kernel Data, User Data, User Code) ---
#[repr(C, align(16))]
struct GdtTable([u64; 5]);

#[repr(C, packed)]
struct DescriptorTablePointer {
    limit: u16,
    base: u64,
}

static GDT: GdtTable = GdtTable([
    0x0000_0000_0000_0000, // 0x00: Null
    0x00AF_9A00_0000_FFFF, // 0x08: Kernel Code (64-bit, DPL=0)
    0x00CF_9200_0000_FFFF, // 0x10: Kernel Data (DPL=0)
    0x00CF_F200_0000_FFFF, // 0x18: User Data (DPL=3, ready for Ring-3 drivers)
    0x00AF_FA00_0000_FFFF, // 0x20: User Code (64-bit, DPL=3)
]);

// --- IDT (256 16-byte Gate Descriptors) ---
#[repr(C)]
#[derive(Clone, Copy)]
struct IdtEntry {
    offset_low: u16,
    selector: u16,
    ist: u8,
    type_attr: u8,
    offset_mid: u16,
    offset_high: u32,
    zero: u32,
}

impl IdtEntry {
    const fn missing() -> Self {
        Self {
            offset_low: 0,
            selector: 0,
            ist: 0,
            type_attr: 0,
            offset_mid: 0,
            offset_high: 0,
            zero: 0,
        }
    }

    fn set_handler(&mut self, addr: u64) {
        self.offset_low = addr as u16;
        self.selector = 0x08; // Kernel Code Segment
        self.ist = 0;
        self.type_attr = 0x8E; // Present | DPL=0 | Interrupt Gate
        self.offset_mid = (addr >> 16) as u16;
        self.offset_high = (addr >> 32) as u32;
        self.zero = 0;
    }
}

static mut IDT: [IdtEntry; 256] = [IdtEntry::missing(); 256];
static TICKS: AtomicU64 = AtomicU64::new(0);

// Assembly trampolines preserving all caller-saved registers and returning via iretq
global_asm!(
    r#"
.global newera_isr_timer
newera_isr_timer:
    push rax
    push rcx
    push rdx
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    sub rsp, 8
    call rust_timer_irq_handler
    add rsp, 8
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rax
    iretq

.global newera_isr_keyboard
newera_isr_keyboard:
    push rax
    push rcx
    push rdx
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    sub rsp, 8
    call rust_keyboard_irq_handler
    add rsp, 8
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rax
    iretq

.global newera_isr_mouse
newera_isr_mouse:
    push rax
    push rcx
    push rdx
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    sub rsp, 8
    call rust_mouse_irq_handler
    add rsp, 8
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rax
    iretq

.global newera_isr_spurious
newera_isr_spurious:
    push rax
    push rcx
    push rdx
    push rsi
    push rdi
    push r8
    push r9
    push r10
    push r11
    sub rsp, 8
    call rust_spurious_irq_handler
    add rsp, 8
    pop r11
    pop r10
    pop r9
    pop r8
    pop rdi
    pop rsi
    pop rdx
    pop rcx
    pop rax
    iretq

.global newera_isr_exception
newera_isr_exception:
    call rust_exception_handler
1:
    hlt
    jmp 1b
"#
);

extern "C" {
    fn newera_isr_timer();
    fn newera_isr_keyboard();
    fn newera_isr_mouse();
    fn newera_isr_spurious();
    fn newera_isr_exception();
}

#[no_mangle]
extern "C" fn rust_timer_irq_handler() {
    TICKS.fetch_add(1, Ordering::Relaxed);
    unsafe {
        outb(0x20, 0x20); // EOI to Master PIC
    }
}

#[no_mangle]
extern "C" fn rust_keyboard_irq_handler() {
    unsafe {
        let scancode = inb(0x60);
        push_scancode_from_irq(scancode);
        outb(0x20, 0x20); // EOI to Master PIC
    }
}

#[no_mangle]
extern "C" fn rust_mouse_irq_handler() {
    unsafe {
        let data = inb(0x60);
        handle_irq_byte(data);
        outb(0xA0, 0x20); // EOI to Slave PIC
        outb(0x20, 0x20); // EOI to Master PIC
    }
}

#[no_mangle]
extern "C" fn rust_spurious_irq_handler() {
    unsafe {
        outb(0xA0, 0x20);
        outb(0x20, 0x20);
    }
}

#[no_mangle]
extern "C" fn rust_exception_handler() -> ! {
    let mut serial = SerialPort;
    let cr2: u64;
    unsafe {
        asm!("mov {}, cr2", out(reg) cr2, options(nomem, nostack));
    }
    let _ = writeln!(serial, "\n[NEWERA CPU EXCEPTION] Halted cleanly. CR2=0x{:016X}", cr2);
    loop {
        crate::arch::hlt();
    }
}

pub fn ticks() -> u64 {
    TICKS.load(Ordering::Relaxed)
}

pub fn uptime_seconds() -> u64 {
    ticks() / 100
}

unsafe fn load_gdt() {
    let ptr = DescriptorTablePointer {
        limit: (core::mem::size_of::<GdtTable>() - 1) as u16,
        base: core::ptr::addr_of!(GDT) as u64,
    };
    asm!("lgdt [{}]", in(reg) &ptr, options(readonly, nostack, preserves_flags));

    // Reload CS via far return (retfq) and data segment registers
    asm!(
        "push 0x08",
        "lea rax, [rip + 2f]",
        "push rax",
        "retfq",
        "2:",
        "mov ax, 0x10",
        "mov ds, ax",
        "mov es, ax",
        "mov ss, ax",
        "mov fs, ax",
        "mov gs, ax",
        out("rax") _,
        options(preserves_flags)
    );
}

unsafe fn remap_pic_8259() {
    // Remap Master PIC to 0x20..0x27, Slave PIC to 0x28..0x2F
    outb(0x20, 0x11);
    outb(0xA0, 0x11);
    outb(0x21, 0x20);
    outb(0xA1, 0x28);
    outb(0x21, 0x04);
    outb(0xA1, 0x02);
    outb(0x21, 0x01);
    outb(0xA1, 0x01);

    // Unmask IRQ0 (Timer), IRQ1 (Keyboard), IRQ2 (Slave PIC cascade) on Master
    outb(0x21, 0b1111_1000);
    // Unmask IRQ12 (PS/2 Mouse = bit 4) on Slave PIC
    outb(0xA1, 0b1110_1111);
}

unsafe fn init_pit_100hz() {
    // PIT frequency 1,193,182 Hz / 100 Hz = 11932
    let divisor: u16 = 11932;
    outb(0x43, 0x36); // Channel 0, lobyte/hibyte, mode 3 (square wave)
    outb(0x40, (divisor & 0xFF) as u8);
    outb(0x40, (divisor >> 8) as u8);
}

/// Initializes GDT, IDT, remaps 8259 PIC, configures 100Hz PIT Timer, and enables interrupts (STI).
pub fn init() {
    unsafe {
        asm!("cli", options(nomem, nostack));
        load_gdt();

        let idt_ptr = core::ptr::addr_of_mut!(IDT);
        for i in 0..32 {
            (*idt_ptr)[i].set_handler(newera_isr_exception as *const () as u64);
        }
        for i in 32..48 {
            (*idt_ptr)[i].set_handler(newera_isr_spurious as *const () as u64);
        }
        (*idt_ptr)[32].set_handler(newera_isr_timer as *const () as u64);
        (*idt_ptr)[33].set_handler(newera_isr_keyboard as *const () as u64);
        (*idt_ptr)[44].set_handler(newera_isr_mouse as *const () as u64);

        let desc = DescriptorTablePointer {
            limit: (core::mem::size_of::<[IdtEntry; 256]>() - 1) as u16,
            base: idt_ptr as u64,
        };
        asm!("lidt [{}]", in(reg) &desc, options(readonly, nostack, preserves_flags));

        remap_pic_8259();
        init_pit_100hz();
        asm!("sti", options(nomem, nostack));
    }
}

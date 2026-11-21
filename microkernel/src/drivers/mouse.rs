//! PS/2 Mouse Driver (IRQ12, IDT vector 44) — Real 3-byte packet decoder + pointer state.

use core::sync::atomic::{AtomicBool, AtomicI32, AtomicU8, Ordering};

use crate::arch::{inb, outb};

const STATUS_PORT: u16 = 0x64;
const DATA_PORT: u16 = 0x60;

static MOUSE_X: AtomicI32 = AtomicI32::new(640);
static MOUSE_Y: AtomicI32 = AtomicI32::new(400);
static MAX_X: AtomicI32 = AtomicI32::new(1279);
static MAX_Y: AtomicI32 = AtomicI32::new(799);
static BUTTONS: AtomicU8 = AtomicU8::new(0);
static LEFT_CLICK_EDGE: AtomicBool = AtomicBool::new(false);
static MOVED: AtomicBool = AtomicBool::new(false);

static mut PACKET: [u8; 3] = [0; 3];
static mut CYCLE: usize = 0;

#[derive(Clone, Copy)]
pub struct MouseState {
    pub x: usize,
    pub y: usize,
    pub left_down: bool,
    pub left_clicked: bool,
}

fn wait_write() {
    for _ in 0..100_000 {
        if unsafe { (inb(STATUS_PORT) & 0x02) == 0 } {
            return;
        }
    }
}

fn wait_read() {
    for _ in 0..100_000 {
        if unsafe { (inb(STATUS_PORT) & 0x01) != 0 } {
            return;
        }
    }
}

unsafe fn write_mouse(byte: u8) {
    wait_write();
    outb(STATUS_PORT, 0xD4);
    wait_write();
    outb(DATA_PORT, byte);
    wait_read();
    let _ = inb(DATA_PORT); // ACK (0xFA)
}

/// Initializes the 8042 PS/2 auxiliary mouse port and enables IRQ12 packet streaming.
pub fn init(screen_w: usize, screen_h: usize) {
    MAX_X.store((screen_w.saturating_sub(1)) as i32, Ordering::Relaxed);
    MAX_Y.store((screen_h.saturating_sub(1)) as i32, Ordering::Relaxed);
    MOUSE_X.store((screen_w / 2) as i32, Ordering::Relaxed);
    MOUSE_Y.store((screen_h / 2) as i32, Ordering::Relaxed);

    unsafe {
        // Enable auxiliary device (mouse)
        wait_write();
        outb(STATUS_PORT, 0xA8);

        // Read controller config byte
        wait_write();
        outb(STATUS_PORT, 0x20);
        wait_read();
        let mut status = inb(DATA_PORT);
        // Enable IRQ12 (bit 1) and ensure mouse clock is enabled (clear bit 5)
        status |= 0x02;
        status &= !0x20;
        wait_write();
        outb(STATUS_PORT, 0x60);
        wait_write();
        outb(DATA_PORT, status);

        // Use default settings (0xF6) and enable packet streaming (0xF4)
        write_mouse(0xF6);
        write_mouse(0xF4);
    }
}

/// Called directly from hardware IRQ12 (IDT vector 44).
pub fn handle_irq_byte(byte: u8) {
    unsafe {
        match CYCLE {
            0 => {
                // Bit 3 must always be 1 in a valid PS/2 sync byte
                if (byte & 0x08) != 0 {
                    PACKET[0] = byte;
                    CYCLE = 1;
                }
            }
            1 => {
                PACKET[1] = byte;
                CYCLE = 2;
            }
            _ => {
                PACKET[2] = byte;
                CYCLE = 0;

                let flags = PACKET[0];
                // Ignore overflow packets
                if (flags & 0xC0) != 0 {
                    return;
                }
                let dx = PACKET[1] as i8 as i32;
                let dy = -(PACKET[2] as i8 as i32); // PS/2 Y is inverted relative to screen

                let max_x = MAX_X.load(Ordering::Relaxed);
                let max_y = MAX_Y.load(Ordering::Relaxed);
                let nx = (MOUSE_X.load(Ordering::Relaxed) + dx).clamp(0, max_x);
                let ny = (MOUSE_Y.load(Ordering::Relaxed) + dy).clamp(0, max_y);
                MOUSE_X.store(nx, Ordering::Relaxed);
                MOUSE_Y.store(ny, Ordering::Relaxed);

                let prev_btn = BUTTONS.swap(flags & 0x07, Ordering::Relaxed);
                let curr_left = (flags & 0x01) != 0;
                let prev_left = (prev_btn & 0x01) != 0;
                if curr_left && !prev_left {
                    LEFT_CLICK_EDGE.store(true, Ordering::Release);
                }
                MOVED.store(true, Ordering::Release);
            }
        }
    }
}

pub fn take_dirty() -> bool {
    MOVED.swap(false, Ordering::AcqRel)
}

pub fn read_state() -> MouseState {
    let clicked = LEFT_CLICK_EDGE.swap(false, Ordering::AcqRel);
    let btns = BUTTONS.load(Ordering::Relaxed);
    MouseState {
        x: MOUSE_X.load(Ordering::Relaxed).max(0) as usize,
        y: MOUSE_Y.load(Ordering::Relaxed).max(0) as usize,
        left_down: (btns & 0x01) != 0,
        left_clicked: clicked,
    }
}

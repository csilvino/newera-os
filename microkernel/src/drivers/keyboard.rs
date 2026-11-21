//! PS/2 Keyboard Driver — IRQ1 interrupt-driven lock-free ring buffer with Shift support.

use core::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

const BUF_LEN: usize = 64;
static mut SCANCODE_BUF: [u8; BUF_LEN] = [0; BUF_LEN];
static HEAD: AtomicUsize = AtomicUsize::new(0);
static TAIL: AtomicUsize = AtomicUsize::new(0);
static SHIFT_HELD: AtomicBool = AtomicBool::new(false);

pub enum KeyEvent {
    Char(u8),
    Enter,
    Backspace,
}

pub fn push_scancode_from_irq(scancode: u8) {
    let head = HEAD.load(Ordering::Relaxed);
    let next = (head + 1) % BUF_LEN;
    if next != TAIL.load(Ordering::Acquire) {
        unsafe {
            SCANCODE_BUF[head] = scancode;
        }
        HEAD.store(next, Ordering::Release);
    }
}

pub fn pop_key() -> Option<KeyEvent> {
    loop {
        let tail = TAIL.load(Ordering::Relaxed);
        if tail == HEAD.load(Ordering::Acquire) {
            return None;
        }
        let scancode = unsafe { SCANCODE_BUF[tail] };
        TAIL.store((tail + 1) % BUF_LEN, Ordering::Release);

        // Track Left/Right Shift press (0x2A, 0x36) and release (0xAA, 0xB6)
        match scancode {
            0x2A | 0x36 => {
                SHIFT_HELD.store(true, Ordering::Relaxed);
                continue;
            }
            0xAA | 0xB6 => {
                SHIFT_HELD.store(false, Ordering::Relaxed);
                continue;
            }
            _ => {}
        }

        if (scancode & 0x80) != 0 {
            continue;
        }
        let shifted = SHIFT_HELD.load(Ordering::Relaxed);
        if let Some(ev) = decode_scancode(scancode, shifted) {
            return Some(ev);
        }
    }
}

fn decode_scancode(scancode: u8, shift: bool) -> Option<KeyEvent> {
    match scancode {
        0x1C => Some(KeyEvent::Enter),
        0x0E => Some(KeyEvent::Backspace),
        0x39 => Some(KeyEvent::Char(b' ')),
        0x02..=0x0B => {
            const NORMAL: &[u8] = b"1234567890";
            const SHIFTED: &[u8] = b"!@#$%^&*()";
            let table = if shift { SHIFTED } else { NORMAL };
            Some(KeyEvent::Char(table[(scancode - 0x02) as usize]))
        }
        0x10..=0x19 => {
            const ROW1: &[u8] = b"qwertyuiop";
            let ch = ROW1[(scancode - 0x10) as usize];
            Some(KeyEvent::Char(if shift { ch.to_ascii_uppercase() } else { ch }))
        }
        0x1E..=0x26 => {
            const ROW2: &[u8] = b"asdfghjkl";
            let ch = ROW2[(scancode - 0x1E) as usize];
            Some(KeyEvent::Char(if shift { ch.to_ascii_uppercase() } else { ch }))
        }
        0x2C..=0x32 => {
            const ROW3: &[u8] = b"zxcvbnm";
            let ch = ROW3[(scancode - 0x2C) as usize];
            Some(KeyEvent::Char(if shift { ch.to_ascii_uppercase() } else { ch }))
        }
        0x0C => Some(KeyEvent::Char(if shift { b'_' } else { b'-' })),
        0x0D => Some(KeyEvent::Char(if shift { b'+' } else { b'=' })),
        0x27 => Some(KeyEvent::Char(if shift { b':' } else { b';' })),
        0x33 => Some(KeyEvent::Char(if shift { b'<' } else { b',' })),
        0x34 => Some(KeyEvent::Char(if shift { b'>' } else { b'.' })),
        0x35 => Some(KeyEvent::Char(if shift { b'?' } else { b'/' })),
        _ => None,
    }
}

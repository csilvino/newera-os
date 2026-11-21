//! UART 16550 Serial Port Driver (COM1 0x3F8) for bare-metal kernel logging.

use core::fmt;

use crate::arch::{inb, outb};

const COM1: u16 = 0x3F8;

pub struct SerialPort;

impl SerialPort {
    pub fn init() {
        unsafe {
            outb(COM1 + 1, 0x00); // Disable interrupts
            outb(COM1 + 3, 0x80); // Enable DLAB
            outb(COM1 + 0, 0x03); // 38400 baud lo
            outb(COM1 + 1, 0x00); // 38400 baud hi
            outb(COM1 + 3, 0x03); // 8 bits, no parity, one stop bit
            outb(COM1 + 2, 0xC7); // Enable FIFO
            outb(COM1 + 4, 0x0B); // IRQs enabled, RTS/DSR set
        }
    }

    pub fn write_byte(byte: u8) {
        unsafe {
            let mut spins = 0;
            while (inb(COM1 + 5) & 0x20) == 0 && spins < 10_000 {
                spins += 1;
            }
            outb(COM1, byte);
        }
    }
}

impl fmt::Write for SerialPort {
    fn write_str(&mut self, s: &str) -> fmt::Result {
        for b in s.bytes() {
            if b == b'\n' {
                Self::write_byte(b'\r');
            }
            Self::write_byte(b);
        }
        Ok(())
    }
}

//! Bare-Metal Modern 2D Compositor (UEFI GOP — RTX 3060 & QEMU).
//! Features: Pre-rendered Aurora Mesh Wallpaper, real RGBA Alpha Blending (Glassmorphism),
//! Soft Drop Shadows, Anti-Aliased Proportional TrueType Font Atlas (Segoe UI 15px & 26px),
//! Smooth Rounded Rects, Vector-style Dock Icons, and Tear-Free Double Buffering.

extern crate alloc;

use alloc::vec;
use alloc::vec::Vec;

use crate::font_atlas::{
    lookup, GlyphMetric, FONT_BODY_BITMAP, FONT_BODY_GLYPHS, FONT_TITLE_BITMAP, FONT_TITLE_GLYPHS,
};

pub struct Framebuffer {
    vram: *mut u32,
    backbuffer: Vec<u32>,
    wallpaper: Vec<u32>,
    pub width: usize,
    pub height: usize,
    pub stride: usize,
    pub is_bgr: bool,
}

impl Framebuffer {
    pub unsafe fn new(base: u64, width: u32, height: u32, stride: u32, pixel_format: u32) -> Self {
        let w = width as usize;
        let h = height as usize;
        let s = stride as usize;
        let is_bgr = pixel_format == 1;
        let backbuffer = vec![0u32; w * h];
        let wallpaper = build_aurora_wallpaper(w, h, is_bgr);
        Self {
            vram: base as *mut u32,
            backbuffer,
            wallpaper,
            width: w,
            height: h,
            stride: s,
            is_bgr,
        }
    }

    #[inline]
    pub fn rgb(&self, r: u8, g: u8, b: u8) -> u32 {
        pack_rgb(r, g, b, self.is_bgr)
    }

    #[inline]
    fn unpack(&self, px: u32) -> (u8, u8, u8) {
        if self.is_bgr {
            (((px >> 16) & 0xFF) as u8, ((px >> 8) & 0xFF) as u8, (px & 0xFF) as u8)
        } else {
            ((px & 0xFF) as u8, ((px >> 8) & 0xFF) as u8, ((px >> 16) & 0xFF) as u8)
        }
    }

    #[inline]
    pub fn blend_pixel(&mut self, x: usize, y: usize, r: u8, g: u8, b: u8, alpha: u8) {
        if x >= self.width || y >= self.height || alpha == 0 {
            return;
        }
        let idx = y * self.width + x;
        if alpha == 255 {
            self.backbuffer[idx] = self.rgb(r, g, b);
            return;
        }
        let (dr, dg, db) = self.unpack(self.backbuffer[idx]);
        let a = alpha as u32;
        let inv = 255 - a;
        let nr = ((r as u32 * a + dr as u32 * inv) / 255) as u8;
        let ng = ((g as u32 * a + dg as u32 * inv) / 255) as u8;
        let nb = ((b as u32 * a + db as u32 * inv) / 255) as u8;
        self.backbuffer[idx] = self.rgb(nr, ng, nb);
    }

    pub fn draw_wallpaper(&mut self) {
        self.backbuffer.copy_from_slice(&self.wallpaper);
    }

    pub fn present(&self) {
        unsafe {
            if self.stride == self.width {
                core::ptr::copy_nonoverlapping(
                    self.backbuffer.as_ptr(),
                    self.vram,
                    self.width * self.height,
                );
            } else {
                for y in 0..self.height {
                    core::ptr::copy_nonoverlapping(
                        self.backbuffer.as_ptr().add(y * self.width),
                        self.vram.add(y * self.stride),
                        self.width,
                    );
                }
            }
        }
    }

    pub fn fill_rect_rgba(
        &mut self,
        x: usize,
        y: usize,
        w: usize,
        h: usize,
        r: u8,
        g: u8,
        b: u8,
        a: u8,
    ) {
        let x_end = (x + w).min(self.width);
        let y_end = (y + h).min(self.height);
        for py in y..y_end {
            for px in x..x_end {
                self.blend_pixel(px, py, r, g, b, a);
            }
        }
    }

    /// Draws a soft multi-layer drop shadow under floating windows, Spotlight bar, and Dock.
    pub fn draw_shadow(&mut self, x: usize, y: usize, w: usize, h: usize, radius: usize) {
        for layer in (1..=4).rev() {
            let expand = layer * 3;
            let alpha = (26 - layer * 5) as u8;
            self.fill_rounded_rect_rgba(
                x.saturating_sub(expand / 2),
                y + layer * 2,
                w + expand,
                h + expand / 2,
                radius + layer,
                0,
                0,
                0,
                alpha,
            );
        }
    }

    pub fn fill_rounded_rect_rgba(
        &mut self,
        x: usize,
        y: usize,
        w: usize,
        h: usize,
        radius: usize,
        r: u8,
        g: u8,
        b: u8,
        alpha: u8,
    ) {
        if w == 0 || h == 0 || alpha == 0 {
            return;
        }
        let rad = radius.min(w / 2).min(h / 2);
        let r2 = (rad * rad) as isize;
        for dy in 0..h {
            let py = y + dy;
            if py >= self.height {
                break;
            }
            let cy = if dy < rad {
                rad - dy
            } else if dy >= h - rad {
                dy - (h - rad - 1)
            } else {
                0
            };
            for dx in 0..w {
                let px = x + dx;
                if px >= self.width {
                    break;
                }
                if cy > 0 {
                    let cx = if dx < rad {
                        rad - dx
                    } else if dx >= w - rad {
                        dx - (w - rad - 1)
                    } else {
                        0
                    };
                    if cx > 0 && ((cx * cx + cy * cy) as isize) > r2 {
                        continue;
                    }
                }
                self.blend_pixel(px, py, r, g, b, alpha);
            }
        }
    }

    pub fn stroke_rounded_rect_rgba(
        &mut self,
        x: usize,
        y: usize,
        w: usize,
        h: usize,
        radius: usize,
        r: u8,
        g: u8,
        b: u8,
        alpha: u8,
    ) {
        let rad = radius.min(w / 2).min(h / 2);
        self.fill_rect_rgba(x + rad, y, w.saturating_sub(rad * 2), 1, r, g, b, alpha);
        self.fill_rect_rgba(x + rad, y + h.saturating_sub(1), w.saturating_sub(rad * 2), 1, r, g, b, alpha);
        self.fill_rect_rgba(x, y + rad, 1, h.saturating_sub(rad * 2), r, g, b, alpha);
        self.fill_rect_rgba(x + w.saturating_sub(1), y + rad, 1, h.saturating_sub(rad * 2), r, g, b, alpha);
    }

    pub fn fill_circle_rgba(
        &mut self,
        cx: usize,
        cy: usize,
        radius: usize,
        r: u8,
        g: u8,
        b: u8,
        alpha: u8,
    ) {
        let rad = radius as isize;
        let r2 = rad * rad;
        for dy in -rad..=rad {
            let y = cy as isize + dy;
            if y < 0 || y >= self.height as isize {
                continue;
            }
            for dx in -rad..=rad {
                if dx * dx + dy * dy <= r2 {
                    let x = cx as isize + dx;
                    if x >= 0 && x < self.width as isize {
                        self.blend_pixel(x as usize, y as usize, r, g, b, alpha);
                    }
                }
            }
        }
    }

    /// Draws a glowing hollow ring (for the Jarvis-style luminous orb).
    pub fn draw_ring_rgba(
        &mut self,
        cx: usize,
        cy: usize,
        radius: usize,
        thickness: usize,
        r: u8,
        g: u8,
        b: u8,
        alpha: u8,
    ) {
        let outer = radius as isize;
        let inner = radius.saturating_sub(thickness) as isize;
        let r_out2 = outer * outer;
        let r_in2 = inner * inner;
        for dy in -outer..=outer {
            let y = cy as isize + dy;
            if y < 0 || y >= self.height as isize {
                continue;
            }
            for dx in -outer..=outer {
                let d2 = dx * dx + dy * dy;
                if d2 <= r_out2 && d2 >= r_in2 {
                    let x = cx as isize + dx;
                    if x >= 0 && x < self.width as isize {
                        self.blend_pixel(x as usize, y as usize, r, g, b, alpha);
                    }
                }
            }
        }
    }

    pub fn draw_line_rgba(
        &mut self,
        x0: isize,
        y0: isize,
        x1: isize,
        y1: isize,
        r: u8,
        g: u8,
        b: u8,
        alpha: u8,
    ) {
        let mut x = x0;
        let mut y = y0;
        let dx = (x1 - x0).abs();
        let dy = -(y1 - y0).abs();
        let sx = if x0 < x1 { 1 } else { -1 };
        let sy = if y0 < y1 { 1 } else { -1 };
        let mut err = dx + dy;
        loop {
            if x >= 0 && y >= 0 {
                self.blend_pixel(x as usize, y as usize, r, g, b, alpha);
            }
            if x == x1 && y == y1 {
                break;
            }
            let e2 = 2 * err;
            if e2 >= dy {
                err += dy;
                x += sx;
            }
            if e2 <= dx {
                err += dx;
                y += sy;
            }
        }
    }

    pub fn draw_progress_bar(
        &mut self,
        x: usize,
        y: usize,
        w: usize,
        h: usize,
        pct: usize,
        r: u8,
        g: u8,
        b: u8,
    ) {
        self.fill_rounded_rect_rgba(x, y, w, h, h / 2, 255, 255, 255, 26);
        let fill_w = (w * pct.min(100)) / 100;
        if fill_w > 2 {
            self.fill_rounded_rect_rgba(x, y, fill_w, h, h / 2, r, g, b, 235);
        }
    }

    pub fn measure_text(&self, text: &str, title: bool) -> usize {
        let glyphs = if title { FONT_TITLE_GLYPHS } else { FONT_BODY_GLYPHS };
        let mut w = 0usize;
        for ch in text.chars() {
            if let Some(g) = lookup(glyphs, ch) {
                w += g.advance as usize;
            } else {
                w += if title { 12 } else { 7 };
            }
        }
        w
    }

    pub fn draw_text_body(&mut self, x: usize, y: usize, text: &str, r: u8, g: u8, b: u8) {
        self.draw_atlas_text(x, y, text, r, g, b, FONT_BODY_GLYPHS, FONT_BODY_BITMAP);
    }

    pub fn draw_text_title(&mut self, x: usize, y: usize, text: &str, r: u8, g: u8, b: u8) {
        self.draw_atlas_text(x, y, text, r, g, b, FONT_TITLE_GLYPHS, FONT_TITLE_BITMAP);
    }

    fn draw_atlas_text(
        &mut self,
        x: usize,
        y: usize,
        text: &str,
        r: u8,
        g: u8,
        b: u8,
        glyphs: &[GlyphMetric],
        bitmap: &[u8],
    ) {
        let mut cx = x as isize;
        let base_y = y as isize;
        for ch in text.chars() {
            if let Some(m) = lookup(glyphs, ch) {
                let gw = m.width as usize;
                let gh = m.height as usize;
                for gy in 0..gh {
                    let py = base_y + m.y_off as isize + gy as isize;
                    if py < 0 || py >= self.height as isize {
                        continue;
                    }
                    let row_off = m.offset + gy * gw;
                    for gx in 0..gw {
                        let a = bitmap[row_off + gx];
                        if a > 8 {
                            let px = cx + m.x_off as isize + gx as isize;
                            if px >= 0 && px < self.width as isize {
                                self.blend_pixel(px as usize, py as usize, r, g, b, a);
                            }
                        }
                    }
                }
                cx += m.advance as isize;
            } else {
                cx += 7;
            }
        }
    }

    pub fn draw_cursor(&mut self, mx: usize, my: usize) {
        const CURSOR: [&str; 16] = [
            "X...........",
            "XX..........",
            "XWX.........",
            "XWWX........",
            "XWWWX.......",
            "XWWWWX......",
            "XWWWWWX.....",
            "XWWWWWWX....",
            "XWWWWWWWX...",
            "XWWWWWWWWX..",
            "XWWWWWXXXX..",
            "XWWXWWX.....",
            "XWX.XWWX....",
            "XX..XWWX....",
            ".....XWWX...",
            "......XX....",
        ];
        for (dy, row) in CURSOR.iter().enumerate() {
            for (dx, ch) in row.bytes().enumerate() {
                match ch {
                    b'X' => self.blend_pixel(mx + dx, my + dy, 10, 14, 24, 240),
                    b'W' => self.blend_pixel(mx + dx, my + dy, 255, 255, 255, 255),
                    _ => {}
                }
            }
        }
    }
}

#[inline]
fn pack_rgb(r: u8, g: u8, b: u8, is_bgr: bool) -> u32 {
    if is_bgr {
        ((r as u32) << 16) | ((g as u32) << 8) | (b as u32)
    } else {
        ((b as u32) << 16) | ((g as u32) << 8) | (r as u32)
    }
}

/// Generates a modern desktop mesh-aurora wallpaper (inspired by macOS Sequoia / Windows 11 Bloom).
fn build_aurora_wallpaper(w: usize, h: usize, is_bgr: bool) -> Vec<u32> {
    let mut buf = vec![0u32; w * h];
    let c1x = (w as isize * 22) / 100;
    let c1y = (h as isize * 28) / 100;
    let c2x = (w as isize * 78) / 100;
    let c2y = (h as isize * 32) / 100;
    let c3x = (w as isize * 52) / 100;
    let c3y = (h as isize * 82) / 100;
    let scale = ((w * w + h * h) / 6).max(1) as isize;

    for y in 0..h {
        let yi = y as isize;
        let row = y * w;
        let v_t = (y * 255) / h.max(1);
        for x in 0..w {
            let xi = x as isize;

            // Base deep twilight gradient
            let mut r = 10 + (v_t * 10) / 255;
            let mut g = 14 + (v_t * 14) / 255;
            let mut b = 30 + (v_t * 28) / 255;

            // Aurora glow 1: Oceanic Cyan (top-left)
            let d1 = (xi - c1x) * (xi - c1x) + (yi - c1y) * (yi - c1y);
            if d1 < scale {
                let w1 = ((scale - d1) * 100) / scale;
                let w1s = ((w1 * w1) / 100) as usize;
                r += (w1s * 14) / 100;
                g += (w1s * 96) / 100;
                b += (w1s * 125) / 100;
            }

            // Aurora glow 2: Royal Indigo / Violet (top-right)
            let d2 = (xi - c2x) * (xi - c2x) + (yi - c2y) * (yi - c2y);
            if d2 < scale {
                let w2 = ((scale - d2) * 100) / scale;
                let w2s = ((w2 * w2) / 100) as usize;
                r += (w2s * 82) / 100;
                g += (w2s * 42) / 100;
                b += (w2s * 138) / 100;
            }

            // Aurora glow 3: Warm Teal (bottom-center)
            let d3 = (xi - c3x) * (xi - c3x) + (yi - c3y) * (yi - c3y);
            if d3 < scale {
                let w3 = ((scale - d3) * 100) / scale;
                let w3s = ((w3 * w3) / 100) as usize;
                r += (w3s * 12) / 100;
                g += (w3s * 68) / 100;
                b += (w3s * 88) / 100;
            }

            buf[row + x] = pack_rgb(r.min(255) as u8, g.min(255) as u8, b.min(255) as u8, is_bgr);
        }
    }
    buf
}

//! Newera OS Desktop Environment (Bare-Metal v0.6).
//! Features: Aurora Wallpaper, Translucent Menu Bar, Clean Spotlight Bar,
//! Vector-drawn Dock Icons, Draggable Floating Glass Windows, Live Network Telemetry (ARP/IPv4/Ping/UDP).

extern crate alloc;

use alloc::format;

use crate::capability::CapabilityTable;
use crate::drivers::mouse::MouseState;
use crate::drivers::pci::PciDevice;
use crate::drivers::virtio_blk::VirtioBlkDevice;
use crate::drivers::virtio_net::VirtioNetDevice;
use crate::gfx::Framebuffer;
use crate::mm::{MemoryStats, ALLOCATOR};
use crate::net::{GenWidget, NetworkState};
use crate::paging::PagingStatus;
use crate::ring3::Ring3SecurityStatus;
use crate::semantic_fs::BareMetalSemanticFS;

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum OpenWindow {
    None,
    IntentResult,
    Semantic,
    System,
    Guardian,
}

#[derive(Clone, Copy)]
pub struct WindowGeometry {
    pub x: usize,
    pub y: usize,
    pub dragging: bool,
    pub drag_off_x: isize,
    pub drag_off_y: isize,
}

impl WindowGeometry {
    pub fn centered(screen_w: usize) -> Self {
        let w = 820usize.min(screen_w.saturating_sub(80));
        Self {
            x: (screen_w.saturating_sub(w)) / 2,
            y: 78,
            dragging: false,
            drag_off_x: 0,
            drag_off_y: 0,
        }
    }
}

#[derive(Clone, Copy)]
struct Rect {
    x: usize,
    y: usize,
    w: usize,
    h: usize,
}

impl Rect {
    fn contains(&self, px: usize, py: usize) -> bool {
        px >= self.x && px < self.x + self.w && py >= self.y && py < self.y + self.h
    }
}

pub enum UiAction {
    None,
    SetWindow(OpenWindow),
    ToggleCheck(usize),
    ToggleKeyboard,
}

fn accent_rgb(name: &str) -> (u8, u8, u8) {
    match name {
        "green" => (52, 211, 153),
        "amber" => (251, 191, 36),
        "indigo" => (129, 140, 248),
        "rose" => (244, 63, 94),
        _ => (56, 189, 248),
    }
}

#[allow(clippy::too_many_arguments)]
pub fn render_desktop(
    fb: &mut Framebuffer,
    open_win: OpenWindow,
    win_geo: &mut WindowGeometry,
    mouse: MouseState,
    cpu_vendor: &str,
    mem: MemoryStats,
    pci_devices: &[PciDevice],
    disk: &Option<VirtioBlkDevice>,
    semfs: &Option<BareMetalSemanticFS>,
    net_dev: &Option<VirtioNetDevice>,
    net_state: &NetworkState,
    paging_info: PagingStatus,
    ring3_status: Ring3SecurityStatus,
    caps: &CapabilityTable,
    search_query: &str,
    input: &str,
    text_input_open: bool,
    toast: &str,
    uptime_s: u64,
    anim_ticks: u64,
) -> UiAction {
    let mut action = UiAction::None;

    // 1. Aurora Wallpaper
    fb.draw_wallpaper();

    // 2. Translucent Top Menu Bar (34px)
    fb.fill_rect_rgba(0, 0, fb.width, 34, 10, 14, 26, 175);
    fb.fill_rect_rgba(0, 34, fb.width, 1, 255, 255, 255, 24);

    fb.fill_circle_rgba(22, 17, 7, 56, 189, 248, 240);
    fb.draw_text_body(38, 9, "Newera OS", 248, 250, 252);
    let surface_name = match open_win {
        OpenWindow::None => "Horizonte",
        OpenWindow::IntentResult => "Canvas de Intenção (Continuum)",
        OpenWindow::Semantic => "Memória Semântica",
        OpenWindow::System => "Monitor do Sistema & Rede",
        OpenWindow::Guardian => "Guardian & Segurança",
    };
    fb.draw_text_body(132, 9, surface_name, 148, 163, 184);

    // Center Clock (Real synced wall-clock time from Continuum, or session uptime fallback)
    let clock = if let Some(base_secs) = net_state.synced_secs_base {
        let elapsed = uptime_s.saturating_sub(net_state.synced_at_uptime);
        let total = (base_secs + elapsed) % 86400;
        let hh = total / 3600;
        let mm = (total % 3600) / 60;
        let ss = total % 60;
        format!("{} • {:02}:{:02}:{:02}", net_state.synced_date, hh, mm, ss)
    } else {
        let mins = uptime_s / 60;
        let secs = uptime_s % 60;
        format!("Sessão ativa • {:02}:{:02}", mins, secs)
    };
    let cw = fb.measure_text(&clock, false);
    fb.draw_text_body((fb.width.saturating_sub(cw)) / 2, 9, &clock, 226, 232, 240);

    // Right System Tray with real IPv4 status
    let net_label = if net_state.ping_ok {
        format!(
            "{}.{}.{}.{} ({}ms)",
            net_state.ip[0], net_state.ip[1], net_state.ip[2], net_state.ip[3], net_state.last_rtt_ms
        )
    } else if net_dev.is_some() {
        format!("{}.{}.{}.{}", net_state.ip[0], net_state.ip[1], net_state.ip[2], net_state.ip[3])
    } else {
        format!("Offline")
    };
    let tray = format!("{}  •  Guardian Ativo", net_label);
    let tw = fb.measure_text(&tray, false);
    let tx = fb.width.saturating_sub(tw + 28);
    fb.fill_circle_rgba(tx.saturating_sub(10), 17, 4, 52, 211, 153, 240);
    fb.draw_text_body(tx, 9, &tray, 203, 213, 225);

    // 3. Center Surface: Clean Horizon or Draggable Floating Glass Window
    match open_win {
        OpenWindow::None => {
            if draw_clean_horizon(fb, mouse, input, text_input_open, toast, net_state, anim_ticks) {
                action = UiAction::ToggleKeyboard;
            }
        }
        OpenWindow::IntentResult => {
            let win_title = net_state
                .last_response
                .as_ref()
                .map(|r| r.title.as_str())
                .unwrap_or("Canvas Generativo (Continuum AI)");
            let mut toggled_chk: Option<usize> = None;
            let closed = draw_draggable_window(fb, win_geo, mouse, win_title, |fb, x, y, w, _h| {
                if let Some(ref resp) = net_state.last_response {
                    let badge = format!("Interface Generativa • Motor: {} • Guardian Ativo", resp.provider);
                    fb.draw_text_body(x, y, &badge, 110, 231, 183);

                    if !resp.widgets.is_empty() {
                        let mut cy = y + 30;
                        // 1. Render KPI cards row
                        let kpis: alloc::vec::Vec<_> = resp
                            .widgets
                            .iter()
                            .filter_map(|w| match w {
                                GenWidget::Kpi { label, value, accent } => Some((label, value, accent)),
                                _ => None,
                            })
                            .collect();
                        if !kpis.is_empty() {
                            let count = kpis.len().min(3);
                            let gap = 12usize;
                            let card_w = (w.saturating_sub(gap * (count - 1))) / count;
                            for (i, (label, value, accent)) in kpis.iter().take(3).enumerate() {
                                let cx = x + i * (card_w + gap);
                                let (ar, ag, ab) = accent_rgb(accent);
                                fb.fill_rounded_rect_rgba(cx, cy, card_w, 64, 10, 255, 255, 255, 14);
                                fb.stroke_rounded_rect_rgba(cx, cy, card_w, 64, 10, ar, ag, ab, 95);
                                fb.draw_text_body(cx + 14, cy + 10, label, 148, 163, 184);
                                fb.draw_text_title(cx + 14, cy + 30, value, ar, ag, ab);
                            }
                            cy += 78;
                        }

                        // 2. Render Bar charts, Interactive Checklists & Text
                        for (idx, widget) in resp.widgets.iter().enumerate() {
                            match widget {
                                GenWidget::Kpi { .. } => {}
                                GenWidget::Bar { label, value_text, pct, accent } => {
                                    let (ar, ag, ab) = accent_rgb(accent);
                                    let row = format!("{}  —  {}", label, value_text);
                                    fb.draw_text_body(x, cy, &row, 226, 232, 240);
                                    fb.draw_progress_bar(x, cy + 20, w, 10, *pct, ar, ag, ab);
                                    cy += 40;
                                }
                                GenWidget::Check { done, text } => {
                                    let r = Rect { x, y: cy, w, h: 30 };
                                    let hovered = r.contains(mouse.x, mouse.y);
                                    fb.fill_rounded_rect_rgba(
                                        x,
                                        cy,
                                        w,
                                        30,
                                        8,
                                        255,
                                        255,
                                        255,
                                        if hovered { 24 } else { 12 },
                                    );
                                    if *done {
                                        fb.fill_circle_rgba(x + 16, cy + 15, 6, 52, 211, 153, 240);
                                        fb.draw_text_body(x + 32, cy + 7, text, 148, 163, 184);
                                    } else {
                                        fb.fill_circle_rgba(x + 16, cy + 15, 6, 255, 255, 255, 50);
                                        fb.draw_text_body(x + 32, cy + 7, text, 241, 245, 249);
                                    }
                                    if hovered && mouse.left_clicked {
                                        toggled_chk = Some(idx);
                                    }
                                    cy += 36;
                                }
                                GenWidget::Text(line) => {
                                    fb.draw_text_body(x, cy, line, 203, 213, 225);
                                    cy += 22;
                                }
                            }
                        }
                    } else {
                        let mut cy = y + 34;
                        for line in resp.body.lines().take(15) {
                            let color = if line.starts_with('•') || line.starts_with("Distribuição") || line.starts_with("Clima") {
                                (186, 230, 253)
                            } else if line.starts_with("[Guardian]") {
                                (52, 211, 153)
                            } else {
                                (241, 245, 249)
                            };
                            fb.draw_text_body(x, cy, line, color.0, color.1, color.2);
                            cy += 22;
                        }
                    }
                } else {
                    fb.draw_text_body(x, y, "Aguardando resposta da Ponte Continuum via UDP (porta 8766)...", 148, 163, 184);
                }
            });
            if closed {
                action = UiAction::SetWindow(OpenWindow::None);
            } else if let Some(idx) = toggled_chk {
                action = UiAction::ToggleCheck(idx);
            }
        }
        OpenWindow::Semantic => {
            if draw_draggable_window(fb, win_geo, mouse, "Memória Semântica (SemanticFS)", |fb, x, y, w, _h| {
                if let (Some(d), Some(fs)) = (disk, semfs) {
                    let sub = format!(
                        "Volume VirtIO-Blk ({} MiB) • {} memórias salvas sem pastas",
                        d.capacity_mib, fs.entry_count
                    );
                    fb.draw_text_body(x, y, &sub, 148, 163, 184);

                    let hits = fs.search(search_query);
                    let mut cy = y + 36;
                    for rec in hits.iter().take(6) {
                        fb.fill_rounded_rect_rgba(x, cy, w, 58, 10, 255, 255, 255, 14);
                        fb.stroke_rounded_rect_rgba(x, cy, w, 58, 10, 255, 255, 255, 24);
                        fb.draw_text_body(x + 16, cy + 10, &rec.title, 248, 250, 252);
                        fb.draw_text_body(x + 16, cy + 32, &rec.content, 186, 200, 220);
                        cy += 68;
                    }
                    if hits.is_empty() {
                        fb.draw_text_body(x, cy, "Nenhuma memória encontrada. Digite 'salvar <nota>' no Horizonte.", 148, 163, 184);
                    }
                } else {
                    fb.draw_text_body(x, y, "Nenhum volume VirtIO-Blk detectado.", 248, 113, 113);
                }
            }) {
                action = UiAction::SetWindow(OpenWindow::None);
            }
        }
        OpenWindow::System => {
            if draw_draggable_window(fb, win_geo, mouse, "Monitor do Sistema & Rede Bare-Metal", |fb, x, y, w, _h| {
                let ram_mib = mem.total_conventional_bytes / (1024 * 1024);
                let heap_pct = ((ALLOCATOR.used_bytes() * 100) / ALLOCATOR.total_bytes()).min(100);
                let cpu_line = format!("Processador: {}  •  RAM Física: {} MiB", cpu_vendor, ram_mib);
                fb.draw_text_body(x, y, &cpu_line, 248, 250, 252);

                let heap_line = format!(
                    "Heap do Kernel: {} KB / {} MB ({}%)",
                    ALLOCATOR.used_bytes() / 1024,
                    ALLOCATOR.total_bytes() / (1024 * 1024),
                    heap_pct
                );
                fb.draw_text_body(x, y + 26, &heap_line, 186, 200, 220);
                fb.draw_progress_bar(x, y + 48, w.min(460), 9, heap_pct, 56, 189, 248);

                if let Some(n) = net_dev {
                    let net_line = format!(
                        "VirtIO-Net MAC: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}  •  IP: {}.{}.{}.{}  •  TX:{} RX:{}",
                        n.mac[0], n.mac[1], n.mac[2], n.mac[3], n.mac[4], n.mac[5],
                        net_state.ip[0], net_state.ip[1], net_state.ip[2], net_state.ip[3],
                        n.tx_packets, n.rx_packets
                    );
                    fb.draw_text_body(x, y + 72, &net_line, 110, 231, 183);

                    let ping_line = if let Some(gw) = net_state.gateway_mac {
                        format!(
                            "Gateway ARP: {:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X}  •  Ping: {} ({} ms)  •  UDP Continuum: {}",
                            gw[0], gw[1], gw[2], gw[3], gw[4], gw[5],
                            if net_state.ping_ok { "OK" } else { "Aguardando" },
                            net_state.last_rtt_ms,
                            net_state.udp_sent
                        )
                    } else {
                        format!("Gateway ARP: resolvendo 10.0.2.2...")
                    };
                    fb.draw_text_body(x, y + 96, &ping_line, 186, 230, 253);
                }

                fb.draw_text_body(x, y + 132, "Dispositivos PCI detectados no hardware:", 148, 163, 184);
                let mut py = y + 158;
                for dev in pci_devices.iter().take(6) {
                    let line = format!(
                        "PCI {:02X}:{:02X}  •  {}  —  {} ({:04X}:{:04X})",
                        dev.bus, dev.slot, dev.vendor_name(), dev.class_name(), dev.vendor_id, dev.device_id
                    );
                    fb.draw_text_body(x + 8, py, &line, 226, 232, 240);
                    py += 24;
                }
            }) {
                action = UiAction::SetWindow(OpenWindow::None);
            }
        }
        OpenWindow::Guardian => {
            if draw_draggable_window(fb, win_geo, mouse, "Guardian — Soberania & Isolamento Ring-0", |fb, x, y, w, _h| {
                let p1 = format!(
                    "Paginação PML4 (CR3): 0x{:X}  •  Proteção NX: {}  •  SYSCALL Ring-3: {}",
                    paging_info.cr3_pml4_phys,
                    if paging_info.nx_enabled { "Ativa" } else { "Inativa" },
                    if paging_info.syscall_enabled { "Ativo" } else { "Inativo" }
                );
                let p2 = format!(
                    "TSS RSP0: 0x{:X}  •  Syscalls Permitidas: {}  •  Ataques Bloqueados (EPERM): {}  •  Teste: {}",
                    ring3_status.tss_rsp0,
                    ring3_status.syscalls_allowed,
                    ring3_status.syscalls_denied,
                    if ring3_status.self_test_passed { "PASS" } else { "FAIL" }
                );
                fb.draw_text_body(x, y, &p1, 110, 231, 183);
                fb.draw_text_body(x, y + 24, &p2, 186, 230, 253);
                fb.draw_text_body(x, y + 54, "Permissões ativas por Capability (nenhum driver tem acesso total):", 148, 163, 184);

                let mut cy = y + 80;
                for g in caps.list().iter().take(7) {
                    fb.fill_rounded_rect_rgba(x, cy, w, 30, 8, 255, 255, 255, 12);
                    let row = format!("Token #{}   •   {}   (máscara 0x{:04X})", g.token_id, g.subject, g.mask);
                    fb.draw_text_body(x + 14, cy + 7, &row, 226, 232, 240);
                    cy += 36;
                }
            }) {
                action = UiAction::SetWindow(OpenWindow::None);
            }
        }
    }

    // 4. Floating Translucent Bottom Dock with Vector Icons
    if let Some(dock_act) = draw_floating_dock(fb, mouse, open_win) {
        action = dock_act;
    }

    // 5. Mouse Cursor
    fb.draw_cursor(mouse.x, mouse.y);

    // 6. Present backbuffer tear-free
    fb.present();

    action
}

/// Integer-only 16-step sine/cosine lookup (scaled x100) for smooth Jarvis orbital animation in no_std.
const COS16: [isize; 16] = [100, 92, 71, 38, 0, -38, -71, -92, -100, -92, -71, -38, 0, 38, 71, 92];
const SIN16: [isize; 16] = [0, 38, 71, 92, 100, 92, 71, 38, 0, -38, -71, -92, -100, -92, -71, -38];

/// Draws Horizon v1.3 (Voice-First):
/// - Hands-free always-on mic: zero text box cluttering the screen by default!
/// - Top: Discrete Keyboard toggle button (opens writing bar only when clicked or typing)
/// - Center: Jarvis-style luminous animated energy orb (pulses when AI speaks / listens)
/// - Side: Live Microphone VU Volume Meter rising and falling in real time
/// Returns true if the Keyboard toggle button was clicked.
fn draw_clean_horizon(
    fb: &mut Framebuffer,
    mouse: MouseState,
    input: &str,
    text_input_open: bool,
    toast: &str,
    net_state: &NetworkState,
    anim_ticks: u64,
) -> bool {
    let cx = fb.width / 2;
    let bar_y = 66usize;
    let kb_clicked;

    if text_input_open {
        // Expandable Top Writing Bar (shown only when user clicks Keyboard icon or types)
        let bar_w = 660usize.min(fb.width.saturating_sub(80));
        let bar_h = 52usize;
        let bar_x = cx.saturating_sub(bar_w / 2);

        fb.draw_shadow(bar_x, bar_y, bar_w, bar_h, 16);
        fb.fill_rounded_rect_rgba(bar_x, bar_y, bar_w, bar_h, 16, 16, 22, 40, 218);
        fb.stroke_rounded_rect_rgba(bar_x, bar_y, bar_w, bar_h, 16, 56, 189, 248, 120);

        fb.fill_circle_rgba(bar_x + 24, bar_y + 26, 7, 56, 189, 248, 235);
        if input.is_empty() {
            fb.draw_text_body(bar_x + 44, bar_y + 17, "Digite sua intenção e pressione Enter...", 148, 163, 184);
        } else {
            let prompt = format!("{}|", input);
            fb.draw_text_body(bar_x + 44, bar_y + 17, &prompt, 255, 255, 255);
        }

        // Keyboard toggle button inside right side of bar (closes bar back to pure voice)
        let kb_btn = Rect { x: bar_x + bar_w - 48, y: bar_y + 7, w: 38, h: 38 };
        let kb_hover = kb_btn.contains(mouse.x, mouse.y);
        fb.fill_rounded_rect_rgba(kb_btn.x, kb_btn.y, kb_btn.w, kb_btn.h, 11, 56, 189, 248, if kb_hover { 255 } else { 210 });
        draw_keyboard_icon(fb, kb_btn.x + 8, kb_btn.y + 11, 10, 14, 26);
        kb_clicked = kb_hover && mouse.left_clicked;
    } else {
        // Pure Voice-First Mode: clean floating Keyboard icon pill at top-right of Horizon
        let kb_btn = Rect { x: fb.width.saturating_sub(72), y: 54, w: 46, h: 40 };
        let kb_hover = kb_btn.contains(mouse.x, mouse.y);
        fb.draw_shadow(kb_btn.x, kb_btn.y, kb_btn.w, kb_btn.h, 12);
        fb.fill_rounded_rect_rgba(
            kb_btn.x,
            kb_btn.y,
            kb_btn.w,
            kb_btn.h,
            12,
            if kb_hover { 30 } else { 16 },
            if kb_hover { 44 } else { 22 },
            if kb_hover { 72 } else { 40 },
            210,
        );
        fb.stroke_rounded_rect_rgba(
            kb_btn.x,
            kb_btn.y,
            kb_btn.w,
            kb_btn.h,
            12,
            if kb_hover { 56 } else { 255 },
            if kb_hover { 189 } else { 255 },
            if kb_hover { 248 } else { 255 },
            if kb_hover { 170 } else { 48 },
        );
        draw_keyboard_icon(fb, kb_btn.x + 12, kb_btn.y + 12, 226, 232, 240);
        if kb_hover {
            let tip = "Digitar";
            let tw = fb.measure_text(tip, false);
            fb.draw_text_body(kb_btn.x.saturating_sub(tw + 12), kb_btn.y + 11, tip, 186, 230, 253);
        }
        kb_clicked = kb_hover && mouse.left_clicked;
    }

    // 2. CENTER: JARVIS-STYLE LUMINOUS ENERGY ORB
    let orb_x = cx;
    let orb_y = fb.height / 2;
    let phase = ((anim_ticks / 8) % 16) as usize;
    let pulse = if net_state.ai_speaking {
        ((anim_ticks / 4) % 18) as usize
    } else if net_state.mic_listening {
        (net_state.mic_level as usize / 5).min(18)
    } else {
        ((anim_ticks / 14) % 6) as usize
    };

    let (or, og, ob) = if net_state.ai_speaking {
        (56, 189, 248) // Vibrant Jarvis Cyan when speaking
    } else if net_state.mic_listening {
        (52, 211, 153) // Emerald when actively hearing you
    } else {
        (99, 102, 241) // Calm Indigo/Cyan idle breathing
    };

    fb.fill_circle_rgba(orb_x, orb_y, 122 + pulse, or, og, ob, if net_state.ai_speaking { 38 } else { 22 });
    fb.fill_circle_rgba(orb_x, orb_y, 90 + pulse / 2, 34, 211, 238, if net_state.ai_speaking { 56 } else { 30 });

    fb.draw_ring_rgba(orb_x, orb_y, 108 + pulse / 2, 2, 56, 189, 248, 170);
    fb.draw_ring_rgba(orb_x, orb_y, 84, 3, or, og, ob, 220);
    fb.draw_ring_rgba(orb_x, orb_y, 60 + pulse / 3, 2, 186, 230, 253, 200);

    fb.fill_circle_rgba(orb_x, orb_y, 36 + pulse / 3, 34, 211, 238, 170);
    fb.fill_circle_rgba(orb_x, orb_y, 19 + pulse / 4, 240, 249, 255, 240);

    for k in 0..4 {
        let idx = (phase + k * 4) % 16;
        let r_orb = (84 + (k % 2) * 24) as isize;
        let px = (orb_x as isize + (COS16[idx] * r_orb) / 100) as usize;
        let py = (orb_y as isize + (SIN16[idx] * r_orb) / 100) as usize;
        fb.fill_circle_rgba(px, py, if net_state.ai_speaking { 6 } else { 4 }, 224, 242, 254, 240);
    }

    let orb_label = if net_state.ai_speaking {
        "Newera falando..."
    } else if net_state.mic_listening {
        "Ouvindo você..."
    } else {
        "Pode falar — microfone ativo"
    };
    let olw = fb.measure_text(orb_label, false);
    fb.draw_text_body(orb_x.saturating_sub(olw / 2), orb_y + 138, orb_label, 186, 230, 253);

    // 3. SIDE: LIVE MICROPHONE VU VOLUME METER (12 LED bars)
    let vu_x = orb_x + 184;
    let vu_w = 54usize;
    let vu_h = 196usize;
    let vu_y = orb_y.saturating_sub(vu_h / 2);

    fb.draw_shadow(vu_x, vu_y, vu_w, vu_h, 14);
    fb.fill_rounded_rect_rgba(vu_x, vu_y, vu_w, vu_h, 14, 16, 22, 40, 195);
    fb.stroke_rounded_rect_rgba(vu_x, vu_y, vu_w, vu_h, 14, 255, 255, 255, 42);

    let active_bars = ((net_state.mic_level as usize) * 12 + 50) / 100;
    for b in 0..12usize {
        let by = vu_y + vu_h - 32 - b * 12;
        let lit = b < active_bars.max(if net_state.mic_listening { 2 } else { 1 });
        let (br, bg, bb, ba) = if !lit {
            (255, 255, 255, 22)
        } else if b >= 10 {
            (244, 63, 94, 240)
        } else if b >= 7 {
            (251, 191, 36, 240)
        } else if b >= 4 {
            (56, 189, 248, 240)
        } else {
            (52, 211, 153, 240)
        };
        fb.fill_rounded_rect_rgba(vu_x + 11, by, vu_w - 22, 8, 3, br, bg, bb, ba);
    }
    let vu_txt = "VU";
    let vtw = fb.measure_text(vu_txt, false);
    fb.draw_text_body(vu_x + (vu_w.saturating_sub(vtw)) / 2, vu_y + vu_h - 22, vu_txt, 148, 163, 184);

    if !toast.is_empty() && text_input_open {
        let mw = fb.measure_text(toast, false);
        fb.draw_text_body(cx.saturating_sub(mw / 2), bar_y + 62, toast, 186, 230, 253);
    }

    kb_clicked
}

/// Draws a clean vector-style keyboard icon (22x16 px).
fn draw_keyboard_icon(fb: &mut Framebuffer, x: usize, y: usize, r: u8, g: u8, b: u8) {
    fb.stroke_rounded_rect_rgba(x, y, 22, 16, 3, r, g, b, 240);
    // Top key row (4 keys)
    for k in 0..4 {
        fb.fill_rect_rgba(x + 3 + k * 4, y + 4, 3, 2, r, g, b, 230);
    }
    // Middle key row (4 keys)
    for k in 0..4 {
        fb.fill_rect_rgba(x + 3 + k * 4, y + 8, 3, 2, r, g, b, 230);
    }
    // Spacebar
    fb.fill_rect_rgba(x + 6, y + 12, 10, 2, r, g, b, 240);
}

fn draw_draggable_window<F>(
    fb: &mut Framebuffer,
    geo: &mut WindowGeometry,
    mouse: MouseState,
    title: &str,
    draw_body: F,
) -> bool
where
    F: FnOnce(&mut Framebuffer, usize, usize, usize, usize),
{
    let w = 820usize.min(fb.width.saturating_sub(80));
    let h = 470usize.min(fb.height.saturating_sub(170));

    // Handle drag on title bar
    let title_bar = Rect { x: geo.x + 76, y: geo.y, w: w.saturating_sub(76), h: 44 };
    if mouse.left_down {
        if !geo.dragging && title_bar.contains(mouse.x, mouse.y) {
            geo.dragging = true;
            geo.drag_off_x = mouse.x as isize - geo.x as isize;
            geo.drag_off_y = mouse.y as isize - geo.y as isize;
        }
        if geo.dragging {
            let max_x = fb.width.saturating_sub(w) as isize;
            let max_y = fb.height.saturating_sub(h + 90) as isize;
            geo.x = (mouse.x as isize - geo.drag_off_x).clamp(8, max_x.max(8)) as usize;
            geo.y = (mouse.y as isize - geo.drag_off_y).clamp(40, max_y.max(40)) as usize;
        }
    } else {
        geo.dragging = false;
    }

    let x = geo.x;
    let y = geo.y;

    fb.draw_shadow(x, y, w, h, 16);
    fb.fill_rounded_rect_rgba(x, y, w, h, 16, 16, 22, 38, 228);
    fb.stroke_rounded_rect_rgba(x, y, w, h, 16, 255, 255, 255, 42);
    fb.fill_rect_rgba(x + 1, y + 44, w - 2, 1, 255, 255, 255, 22);

    let close_rect = Rect { x: x + 14, y: y + 14, w: 18, h: 18 };
    let close_hover = close_rect.contains(mouse.x, mouse.y);
    fb.fill_circle_rgba(x + 22, y + 22, 6, 244, 63, 94, if close_hover { 255 } else { 215 });
    fb.fill_circle_rgba(x + 42, y + 22, 6, 245, 158, 11, 185);
    fb.fill_circle_rgba(x + 62, y + 22, 6, 34, 197, 94, 185);

    let tw = fb.measure_text(title, false);
    fb.draw_text_body(x + (w.saturating_sub(tw)) / 2, y + 14, title, 241, 245, 249);

    draw_body(fb, x + 26, y + 60, w - 52, h - 80);

    close_hover && mouse.left_clicked
}

fn draw_floating_dock(
    fb: &mut Framebuffer,
    mouse: MouseState,
    open_win: OpenWindow,
) -> Option<UiAction> {
    let items: [(&str, OpenWindow, (u8, u8, u8)); 4] = [
        ("Horizonte", OpenWindow::None, (14, 165, 233)),
        ("Memória", OpenWindow::Semantic, (16, 185, 129)),
        ("Sistema & Rede", OpenWindow::System, (99, 102, 241)),
        ("Guardian", OpenWindow::Guardian, (245, 158, 11)),
    ];

    let icon_sz = 48usize;
    let gap = 16usize;
    let pad_x = 18usize;
    let dock_w = items.len() * icon_sz + (items.len() - 1) * gap + pad_x * 2;
    let dock_h = 68usize;
    let dock_x = (fb.width.saturating_sub(dock_w)) / 2;
    let dock_y = fb.height.saturating_sub(dock_h + 18);

    fb.draw_shadow(dock_x, dock_y, dock_w, dock_h, 18);
    fb.fill_rounded_rect_rgba(dock_x, dock_y, dock_w, dock_h, 18, 18, 24, 42, 188);
    fb.stroke_rounded_rect_rgba(dock_x, dock_y, dock_w, dock_h, 18, 255, 255, 255, 45);

    let mut result = None;
    for (i, (label, target, (cr, cg, cb))) in items.into_iter().enumerate() {
        let ix = dock_x + pad_x + i * (icon_sz + gap);
        let iy = dock_y + 10;
        let rect = Rect { x: ix, y: iy, w: icon_sz, h: icon_sz };
        let hovered = rect.contains(mouse.x, mouse.y);
        let active = open_win == target;

        let draw_y = if hovered { iy.saturating_sub(5) } else { iy };
        fb.fill_rounded_rect_rgba(ix, draw_y, icon_sz, icon_sz, 13, cr, cg, cb, if hovered { 250 } else { 215 });

        // Draw crisp vector-style emblem inside each dock icon (no plain letters!)
        let cx = ix + icon_sz / 2;
        let cy = draw_y + icon_sz / 2;
        match i {
            0 => {
                // Compass / Horizon star
                fb.fill_circle_rgba(cx, cy, 12, 255, 255, 255, 60);
                fb.draw_line_rgba(cx as isize - 9, cy as isize, cx as isize + 9, cy as isize, 255, 255, 255, 245);
                fb.draw_line_rgba(cx as isize, cy as isize - 9, cx as isize, cy as isize + 9, 255, 255, 255, 245);
                fb.fill_circle_rgba(cx, cy, 4, 255, 255, 255, 255);
            }
            1 => {
                // Semantic Graph (3 connected nodes)
                fb.draw_line_rgba(cx as isize - 9, cy as isize + 6, cx as isize, cy as isize - 8, 255, 255, 255, 220);
                fb.draw_line_rgba(cx as isize + 9, cy as isize + 6, cx as isize, cy as isize - 8, 255, 255, 255, 220);
                fb.draw_line_rgba(cx as isize - 9, cy as isize + 6, cx as isize + 9, cy as isize + 6, 255, 255, 255, 220);
                fb.fill_circle_rgba(cx, cy - 8, 4, 255, 255, 255, 255);
                fb.fill_circle_rgba(cx - 9, cy + 6, 4, 255, 255, 255, 255);
                fb.fill_circle_rgba(cx + 9, cy + 6, 4, 255, 255, 255, 255);
            }
            2 => {
                // System / Network Monitor (bars)
                fb.fill_rounded_rect_rgba(cx - 10, cy + 1, 5, 10, 2, 255, 255, 255, 240);
                fb.fill_rounded_rect_rgba(cx - 2, cy - 6, 5, 17, 2, 255, 255, 255, 255);
                fb.fill_rounded_rect_rgba(cx + 6, cy - 11, 5, 22, 2, 255, 255, 255, 240);
            }
            _ => {
                // Guardian Shield
                fb.fill_rounded_rect_rgba(cx - 9, cy - 10, 18, 15, 4, 255, 255, 255, 240);
                fb.fill_circle_rgba(cx, cy + 4, 9, 255, 255, 255, 240);
                fb.fill_circle_rgba(cx, cy - 1, 4, 245, 158, 11, 255);
            }
        }

        if active {
            fb.fill_circle_rgba(cx, dock_y + dock_h - 4, 2, 248, 250, 252, 240);
        }

        if hovered {
            let lw = fb.measure_text(label, false);
            let tx = cx.saturating_sub((lw + 18) / 2);
            let ty = dock_y.saturating_sub(34);
            fb.fill_rounded_rect_rgba(tx, ty, lw + 18, 24, 8, 15, 23, 42, 230);
            fb.draw_text_body(tx + 9, ty + 4, label, 248, 250, 252);
            if mouse.left_clicked {
                result = Some(UiAction::SetWindow(target));
            }
        }
    }

    result
}

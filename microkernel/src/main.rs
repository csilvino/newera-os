//! Newera OS Bare-Metal UEFI x86_64 Microkernel (v0.6.0).
//! Modern Desktop + Draggable Glass Windows + Vector Dock Icons + Real Bare-Metal Network Stack
//! (Ethernet II + ARP + IPv4 + ICMP Ping + UDP Continuum) over VirtIO-Net — ZERO Linux, ZERO Windows.

#![no_std]
#![no_main]

extern crate alloc;

mod arch;
mod capability;
mod drivers;
mod font_atlas;
mod gfx;
mod interrupts;
mod mm;
mod net;
mod paging;
mod ring3;
mod semantic_fs;
mod uefi;
mod ui;

use alloc::format;
use alloc::string::String;
use core::ffi::c_void;
use core::fmt::Write;
use core::panic::PanicInfo;

use capability::{
    CapabilityTable, CAP_DMA_ALLOC, CAP_FRAMEBUFFER, CAP_IPC_SEND, CAP_MMIO_ACCESS, CAP_PCI_CONFIG,
    CAP_PORT_IO, CAP_SEMANTIC_STORE,
};
use drivers::keyboard::{pop_key, KeyEvent};
use drivers::mouse;
use drivers::pci::scan_pci_bus;
use drivers::serial::SerialPort;
use drivers::virtio_blk;
use drivers::virtio_net;
use gfx::Framebuffer;
use mm::{analyze_memory_map, MemoryStats};
use net::NetworkState;
use paging::init_paging_and_ring3_gate;
use semantic_fs::BareMetalSemanticFS;
use uefi::{
    GraphicsOutputProtocol, Handle, MemoryDescriptor, Status, SystemTable, EFI_SUCCESS,
    GRAPHICS_OUTPUT_PROTOCOL_GUID,
};
use ui::{render_desktop, OpenWindow, UiAction, WindowGeometry};

static mut MEMORY_MAP_BUF: [u8; 32768] = [0; 32768];

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    let mut serial = SerialPort;
    let _ = writeln!(serial, "\n[NEWERA KERNEL PANIC] {}", info);
    loop {
        arch::hlt();
    }
}

#[no_mangle]
pub extern "efiapi" fn efi_main(image_handle: Handle, system_table: *mut SystemTable) -> Status {
    SerialPort::init();
    let mut serial = SerialPort;
    let _ = writeln!(
        serial,
        "\n[NEWERA] Booting Newera OS Bare-Metal v0.6 (Desktop + IPv4/ARP/Ping/UDP)..."
    );

    unsafe {
        let bs = &*(*system_table).boot_services;
        let _ = (bs.set_watchdog_timer)(0, 0, 0, core::ptr::null());

        let mut gop_ptr: *mut c_void = core::ptr::null_mut();
        let gop_status = (bs.locate_protocol)(
            &GRAPHICS_OUTPUT_PROTOCOL_GUID,
            core::ptr::null_mut(),
            &mut gop_ptr,
        );
        if gop_status != EFI_SUCCESS || gop_ptr.is_null() {
            let _ = writeln!(serial, "[NEWERA] ERROR: GOP framebuffer not available");
            loop {
                arch::hlt();
            }
        }
        let gop = &*(gop_ptr as *const GraphicsOutputProtocol);
        let mode = &*gop.mode;
        let info = &*mode.info;

        let mut fb = Framebuffer::new(
            mode.frame_buffer_base,
            info.horizontal_resolution,
            info.vertical_resolution,
            info.pixels_per_scan_line,
            info.pixel_format,
        );

        let mut map_size = core::mem::size_of_val(&*core::ptr::addr_of!(MEMORY_MAP_BUF));
        let mut map_key: usize = 0;
        let mut desc_size: usize = 0;
        let mut desc_ver: u32 = 0;

        let status = (bs.get_memory_map)(
            &mut map_size,
            core::ptr::addr_of_mut!(MEMORY_MAP_BUF) as *mut MemoryDescriptor,
            &mut map_key,
            &mut desc_size,
            &mut desc_ver,
        );
        if status == EFI_SUCCESS {
            let _ = (bs.exit_boot_services)(image_handle, map_key);
        }

        let mem_stats = analyze_memory_map(
            core::ptr::addr_of!(MEMORY_MAP_BUF) as *const u8,
            map_size,
            desc_size,
        );
        let _ = writeln!(
            serial,
            "[NEWERA] Hardware ownership acquired! RAM={} MiB, Desktop GOP={}x{}",
            mem_stats.total_conventional_bytes / (1024 * 1024),
            fb.width,
            fb.height
        );

        kernel_main(&mut fb, mem_stats);
    }
}

fn kernel_main(fb: &mut Framebuffer, mem: MemoryStats) -> ! {
    let mut serial = SerialPort;

    mouse::init(fb.width, fb.height);
    interrupts::init();
    let paging_info = init_paging_and_ring3_gate();

    let vendor_bytes = arch::cpu_vendor();
    let cpu_vendor = core::str::from_utf8(&vendor_bytes).unwrap_or("x86_64");
    let pci_devices = scan_pci_bus();
    let disk = virtio_blk::probe_and_init(&pci_devices);
    let mut semfs = disk.as_ref().map(BareMetalSemanticFS::mount);
    let mut net_dev = virtio_net::probe_and_init(&pci_devices);
    let mut net_state = NetworkState::new();

    if let Some(ref mut nic) = net_dev {
        net_state.bootstrap_and_ping(nic);
        if let Some(gw) = net_state.gateway_mac {
            let _ = writeln!(
                serial,
                "[NEWERA] NET ONLINE! IP=10.0.2.15 GW_MAC={:02X}:{:02X}:{:02X}:{:02X}:{:02X}:{:02X} PING_OK={} RTT={}ms CONTINUUM={} PROVIDER={}",
                gw[0], gw[1], gw[2], gw[3], gw[4], gw[5],
                net_state.ping_ok, net_state.last_rtt_ms, net_state.continuum_online, net_state.ai_provider
            );
        } else {
            let _ = writeln!(serial, "[NEWERA] NET: VirtIO-Net active, awaiting gateway ARP");
        }
    }

    let mut caps = CapabilityTable::new();
    caps.grant("driver.uart_serial", CAP_PORT_IO);
    caps.grant("driver.ps2_keyboard", CAP_PORT_IO);
    caps.grant("driver.ps2_mouse_irq12", CAP_PORT_IO);
    caps.grant("driver.pci_bus", CAP_PCI_CONFIG | CAP_MMIO_ACCESS);
    caps.grant("driver.virtio_blk", CAP_PCI_CONFIG | CAP_PORT_IO | CAP_DMA_ALLOC);
    caps.grant("driver.virtio_net", CAP_PCI_CONFIG | CAP_PORT_IO | CAP_DMA_ALLOC);
    caps.grant("net.ipv4_continuum", CAP_IPC_SEND);
    caps.grant("fs.semantic_baremetal", CAP_SEMANTIC_STORE);
    caps.grant("gfx.aurora_compositor", CAP_FRAMEBUFFER);
    caps.grant("core.syscall_ring3", CAP_IPC_SEND);

    // Initialize 64-bit TSS + SYSCALL Capability Gateway + live self-test
    let ring3_status = ring3::init_and_verify(&caps);
    let _ = writeln!(
        serial,
        "[NEWERA] RING-3 GATEWAY OK! TSS_RSP0=0x{:X} ALLOWED={} DENIED={} SELF_TEST={}",
        ring3_status.tss_rsp0,
        ring3_status.syscalls_allowed,
        ring3_status.syscalls_denied,
        ring3_status.self_test_passed
    );

    let mut open_win = OpenWindow::None;
    let mut win_geo = WindowGeometry::centered(fb.width);
    let mut input = String::new();
    let mut text_input_open = false;
    let mut search_query = String::new();
    let mut toast = String::new();
    let mut last_sec = u64::MAX;
    let mut last_anim_tick = 0u64;
    let mut need_render = true;

    loop {
        if let Some(ref mut nic) = net_dev {
            net_state.poll(nic);

            // Execute OS Skills triggered by the AI / Continuum Bridge!
            if let Some(cmd) = net_state.pending_skill.take() {
                let _ = writeln!(
                    serial,
                    "[NEWERA] SKILL EXECUTED ({}): {}('{}', '{}')",
                    cmd.provider, cmd.skill, cmd.arg1, cmd.arg2
                );
                match cmd.skill.as_str() {
                    "save_memory" => {
                        if let (Some(ref d), Some(ref mut fs)) = (&disk, &mut semfs) {
                            let ok = fs.store(d, "ia-skill", &cmd.arg1, &cmd.arg2);
                            open_win = OpenWindow::Semantic;
                            search_query.clear();
                            toast = if ok {
                                format!("Skill IA gravou no disco via DMA! Total: {} memórias.", fs.entry_count)
                            } else {
                                String::from("Falha DMA ao gravar memória.")
                            };
                        }
                    }
                    "search_memory" => {
                        open_win = OpenWindow::Semantic;
                        search_query = cmd.arg1;
                    }
                    "open_surface" => {
                        open_win = match cmd.arg1.as_str() {
                            "semantic" => OpenWindow::Semantic,
                            "system" => OpenWindow::System,
                            "guardian" => OpenWindow::Guardian,
                            _ => OpenWindow::None,
                        };
                    }
                    "network_ping" => {
                        net_state.bootstrap_and_ping(nic);
                        open_win = OpenWindow::System;
                    }
                    _ => {}
                }
                need_render = true;
            }

            if net_state.has_new_response {
                net_state.has_new_response = false;
                open_win = OpenWindow::IntentResult;
                toast.clear();
                need_render = true;
            }
        }

        if mouse::take_dirty() {
            need_render = true;
        }

        while let Some(ev) = pop_key() {
            need_render = true;
            match ev {
                KeyEvent::Char(c) => {
                    text_input_open = true;
                    if input.len() < 48 {
                        input.push(c as char);
                    }
                }
                KeyEvent::Backspace => {
                    input.pop();
                }
                KeyEvent::Enter => {
                    let cmd = input.trim();
                    if let Some(rest) = cmd.strip_prefix("salvar ") {
                        if let (Some(ref d), Some(ref mut fs)) = (&disk, &mut semfs) {
                            let ok = fs.store(d, "nota", rest, rest);
                            open_win = OpenWindow::Semantic;
                            search_query.clear();
                            toast = if ok {
                                format!("Salvo no disco via DMA ({} memórias).", fs.entry_count)
                            } else {
                                String::from("Falha ao gravar no disco.")
                            };
                        }
                    } else if cmd.contains("ping") {
                        if let Some(ref mut nic) = net_dev {
                            net_state.bootstrap_and_ping(nic);
                            open_win = OpenWindow::System;
                        }
                    } else if cmd.contains("sistema") || cmd.contains("hard") || cmd.contains("pci") || cmd.contains("rede") {
                        open_win = OpenWindow::System;
                    } else if cmd.contains("guard") || cmd.contains("seg") || cmd.contains("cap") {
                        open_win = OpenWindow::Guardian;
                    } else if cmd.is_empty() {
                        open_win = OpenWindow::None;
                    } else if let Some(ref mut nic) = net_dev {
                        if net_state.send_intent(nic, cmd) {
                            toast = format!("Enviado para Continuum AI via UDP...");
                            open_win = OpenWindow::IntentResult;
                        } else {
                            open_win = OpenWindow::Semantic;
                            search_query = String::from(cmd);
                        }
                    } else {
                        open_win = OpenWindow::Semantic;
                        search_query = String::from(cmd);
                    }
                    input.clear();
                }
            }
        }

        let now_ticks = interrupts::ticks();
        let sec = now_ticks / 100;
        if sec != last_sec {
            last_sec = sec;
            need_render = true;
        }
        // Smooth ~12 FPS animation for Jarvis Orb + live VU meter on Horizon
        if open_win == OpenWindow::None && now_ticks.saturating_sub(last_anim_tick) >= 8 {
            last_anim_tick = now_ticks;
            need_render = true;
        }

        if need_render {
            need_render = false;
            let mstate = mouse::read_state();
            let act = render_desktop(
                fb,
                open_win,
                &mut win_geo,
                mstate,
                cpu_vendor,
                mem,
                &pci_devices,
                &disk,
                &semfs,
                &net_dev,
                &net_state,
                paging_info,
                ring3_status,
                &caps,
                &search_query,
                &input,
                text_input_open,
                &toast,
                sec,
                now_ticks,
            );
            match act {
                UiAction::SetWindow(w) => {
                    open_win = w;
                    search_query.clear();
                    need_render = true;
                }
                UiAction::ToggleCheck(idx) => {
                    if let Some(ref mut resp) = net_state.last_response {
                        if let Some(net::GenWidget::Check { done, .. }) = resp.widgets.get_mut(idx) {
                            *done = !*done;
                            need_render = true;
                        }
                    }
                }
                UiAction::ToggleKeyboard => {
                    text_input_open = !text_input_open;
                    need_render = true;
                }
                UiAction::None => {}
            }
        }

        arch::hlt();
    }
}

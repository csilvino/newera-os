//! Bare-Metal Network Stack (Ethernet II + ARP + IPv4 + ICMP Ping + UDP Continuum) over VirtIO-Net.
//! Zero Linux, zero external crates — connects the bare-metal desktop to AI & Continuum nodes.

extern crate alloc;

use alloc::format;
use alloc::string::String;
use alloc::vec::Vec;

use crate::arch::pause;
use crate::drivers::virtio_net::VirtioNetDevice;
use crate::interrupts::ticks;

pub const LOCAL_IP: [u8; 4] = [10, 0, 2, 15];
pub const GATEWAY_IP: [u8; 4] = [10, 0, 2, 2];
pub const CONTINUUM_UDP_PORT: u16 = 8766;
pub const LOCAL_UDP_PORT: u16 = 40000;

const ETHERTYPE_ARP: u16 = 0x0806;
const ETHERTYPE_IPV4: u16 = 0x0800;

#[derive(Clone)]
pub enum GenWidget {
    Kpi { label: String, value: String, accent: String },
    Bar { label: String, value_text: String, pct: usize, accent: String },
    Check { done: bool, text: String },
    Text(String),
}

#[derive(Clone)]
pub struct ContinuumResponse {
    pub provider: String,
    pub title: String,
    pub body: String,
    pub widgets: Vec<GenWidget>,
}

#[derive(Clone)]
pub struct SkillCommand {
    pub provider: String,
    pub skill: String,
    pub arg1: String,
    pub arg2: String,
}

#[derive(Clone)]
pub struct NetworkState {
    pub ip: [u8; 4],
    pub gateway_ip: [u8; 4],
    pub gateway_mac: Option<[u8; 6]>,
    pub ping_ok: bool,
    pub last_rtt_ms: u64,
    pub udp_sent: u32,
    pub udp_received: u32,
    pub continuum_online: bool,
    pub ai_provider: String,
    pub synced_date: String,
    pub synced_secs_base: Option<u64>,
    pub synced_at_uptime: u64,
    pub mic_level: u8,
    pub ai_speaking: bool,
    pub mic_listening: bool,
    pub last_response: Option<ContinuumResponse>,
    pub has_new_response: bool,
    pub pending_skill: Option<SkillCommand>,
}

impl NetworkState {
    pub fn new() -> Self {
        Self {
            ip: LOCAL_IP,
            gateway_ip: GATEWAY_IP,
            gateway_mac: None,
            ping_ok: false,
            last_rtt_ms: 0,
            udp_sent: 0,
            udp_received: 0,
            continuum_online: false,
            ai_provider: String::from("local"),
            synced_date: String::new(),
            synced_secs_base: None,
            synced_at_uptime: 0,
            mic_level: 12,
            ai_speaking: false,
            mic_listening: false,
            last_response: None,
            has_new_response: false,
            pending_skill: None,
        }
    }

    /// Resolves gateway MAC via ARP, runs ICMP Ping, and handshakes with Continuum UDP Bridge.
    pub fn bootstrap_and_ping(&mut self, nic: &mut VirtioNetDevice) {
        self.send_arp_request(nic, self.gateway_ip);

        let mut rx_buf = [0u8; 1520];
        for _ in 0..400_000 {
            if let Some(len) = nic.poll_rx_frame(&mut rx_buf) {
                self.handle_frame(nic, &rx_buf[..len], None);
                if self.gateway_mac.is_some() {
                    break;
                }
            }
            pause();
        }

        if let Some(gw_mac) = self.gateway_mac {
            let t0 = ticks();
            self.send_icmp_echo(nic, gw_mac, self.gateway_ip, 1);
            for _ in 0..600_000 {
                if let Some(len) = nic.poll_rx_frame(&mut rx_buf) {
                    self.handle_frame(nic, &rx_buf[..len], Some(t0));
                    if self.ping_ok {
                        break;
                    }
                }
                pause();
            }
            if self.send_udp(
                nic,
                gw_mac,
                self.gateway_ip,
                LOCAL_UDP_PORT,
                CONTINUUM_UDP_PORT,
                b"NEWERA-CONTINUUM-HELLO-V0.7",
            ) {
                self.udp_sent += 1;
                for _ in 0..500_000 {
                    if let Some(len) = nic.poll_rx_frame(&mut rx_buf) {
                        self.handle_frame(nic, &rx_buf[..len], None);
                        if self.continuum_online {
                            break;
                        }
                    }
                    pause();
                }
            }
        }
    }

    /// Sends a natural-language user intent to the Continuum AI Bridge over UDP.
    pub fn send_intent(&mut self, nic: &mut VirtioNetDevice, query: &str) -> bool {
        let gw_mac = match self.gateway_mac {
            Some(m) => m,
            None => return false,
        };
        let payload = format!("INTENT|{}", query);
        let ok = self.send_udp(
            nic,
            gw_mac,
            self.gateway_ip,
            LOCAL_UDP_PORT,
            CONTINUUM_UDP_PORT,
            payload.as_bytes(),
        );
        if ok {
            self.udp_sent += 1;
        }
        ok
    }

    /// Triggers microphone capture on the Voice Daemon via Continuum Bridge.
    pub fn trigger_mic(&mut self, nic: &mut VirtioNetDevice) -> bool {
        let gw_mac = match self.gateway_mac {
            Some(m) => m,
            None => return false,
        };
        let ok = self.send_udp(
            nic,
            gw_mac,
            self.gateway_ip,
            LOCAL_UDP_PORT,
            CONTINUUM_UDP_PORT,
            b"MIC_TRIGGER|",
        );
        if ok {
            self.mic_listening = true;
            self.udp_sent += 1;
        }
        ok
    }

    /// Polls incoming packets during the desktop loop (replies to ARP and ICMP pings automatically).
    pub fn poll(&mut self, nic: &mut VirtioNetDevice) {
        let mut rx_buf = [0u8; 1520];
        while let Some(len) = nic.poll_rx_frame(&mut rx_buf) {
            self.handle_frame(nic, &rx_buf[..len], None);
        }
    }

    fn handle_frame(&mut self, nic: &mut VirtioNetDevice, frame: &[u8], ping_start_ticks: Option<u64>) {
        if frame.len() < 14 {
            return;
        }
        let ethertype = u16::from_be_bytes([frame[12], frame[13]]);
        match ethertype {
            ETHERTYPE_ARP => self.handle_arp(nic, &frame[14..]),
            ETHERTYPE_IPV4 => self.handle_ipv4(nic, &frame[6..12], &frame[14..], ping_start_ticks),
            _ => {}
        }
    }

    fn handle_arp(&mut self, nic: &mut VirtioNetDevice, pkt: &[u8]) {
        if pkt.len() < 28 {
            return;
        }
        let op = u16::from_be_bytes([pkt[6], pkt[7]]);
        let sender_mac = [pkt[8], pkt[9], pkt[10], pkt[11], pkt[12], pkt[13]];
        let sender_ip = [pkt[14], pkt[15], pkt[16], pkt[17]];
        let target_ip = [pkt[24], pkt[25], pkt[26], pkt[27]];

        if op == 2 && sender_ip == self.gateway_ip {
            // ARP Reply from gateway!
            self.gateway_mac = Some(sender_mac);
        } else if op == 1 && target_ip == self.ip {
            // Respond to ARP Request for our IP
            let mut reply = [0u8; 42];
            reply[0..6].copy_from_slice(&sender_mac);
            reply[6..12].copy_from_slice(&nic.mac);
            reply[12..14].copy_from_slice(&ETHERTYPE_ARP.to_be_bytes());
            reply[14..16].copy_from_slice(&1u16.to_be_bytes());
            reply[16..18].copy_from_slice(&ETHERTYPE_IPV4.to_be_bytes());
            reply[18] = 6;
            reply[19] = 4;
            reply[20..22].copy_from_slice(&2u16.to_be_bytes()); // Reply
            reply[22..28].copy_from_slice(&nic.mac);
            reply[28..32].copy_from_slice(&self.ip);
            reply[32..38].copy_from_slice(&sender_mac);
            reply[38..42].copy_from_slice(&sender_ip);
            nic.send_frame(&reply);
        }
    }

    fn handle_ipv4(&mut self, _nic: &mut VirtioNetDevice, _src_mac: &[u8], ip_pkt: &[u8], ping_start_ticks: Option<u64>) {
        if ip_pkt.len() < 20 {
            return;
        }
        let ihl = ((ip_pkt[0] & 0x0F) as usize) * 4;
        let proto = ip_pkt[9];
        if proto == 1 && ip_pkt.len() >= ihl + 8 {
            // ICMP
            let icmp = &ip_pkt[ihl..];
            if icmp[0] == 0 {
                self.ping_ok = true;
                if let Some(t0) = ping_start_ticks {
                    let dt = ticks().saturating_sub(t0);
                    self.last_rtt_ms = (dt * 10).max(1);
                }
            }
        } else if proto == 17 && ip_pkt.len() >= ihl + 8 {
            // UDP
            let udp = &ip_pkt[ihl..];
            let dst_port = u16::from_be_bytes([udp[2], udp[3]]);
            let udp_len = u16::from_be_bytes([udp[4], udp[5]]) as usize;
            if dst_port == LOCAL_UDP_PORT && udp_len > 8 && udp.len() >= udp_len {
                self.udp_received += 1;
                if let Ok(text) = core::str::from_utf8(&udp[8..udp_len]) {
                    self.parse_continuum_message(text);
                }
            }
        }
    }

    fn parse_continuum_message(&mut self, text: &str) {
        if let Some(rest) = text.strip_prefix("AUDIO|") {
            let mut parts = rest.split('|');
            if let Some(lvl) = parts.next().and_then(|s| s.parse::<u8>().ok()) {
                self.mic_level = lvl.min(100);
            }
            if let Some(spk) = parts.next() {
                self.ai_speaking = spk == "1";
            }
            if let Some(lst) = parts.next() {
                self.mic_listening = lst == "1";
            }
            return;
        }
        if let Some(rest) = text.strip_prefix("HELLO_ACK|") {
            self.continuum_online = true;
            let mut parts = rest.split('|');
            if let Some(prov) = parts.next() {
                self.ai_provider = String::from(prov);
            }
            if let Some(date_s) = parts.next() {
                self.synced_date = String::from(date_s);
            }
            if let Some(secs_s) = parts.next() {
                if let Ok(secs) = secs_s.trim().parse::<u64>() {
                    self.synced_secs_base = Some(secs);
                    self.synced_at_uptime = ticks() / 100;
                }
            }
            return;
        }
        if let Some(rest) = text.strip_prefix("CMD|") {
            self.continuum_online = true;
            let mut parts = rest.splitn(4, '|');
            let prov = parts.next().unwrap_or("ai");
            let skill = parts.next().unwrap_or("");
            let arg1 = parts.next().unwrap_or("");
            let arg2 = parts.next().unwrap_or("");
            self.ai_provider = String::from(prov);
            self.pending_skill = Some(SkillCommand {
                provider: String::from(prov),
                skill: String::from(skill),
                arg1: String::from(arg1),
                arg2: String::from(arg2),
            });
            return;
        }
        if let Some(rest) = text.strip_prefix("UI|") {
            self.continuum_online = true;
            let mut parts = rest.splitn(3, '|');
            let prov = parts.next().unwrap_or("ai");
            let title = parts.next().unwrap_or("Canvas Generativo");
            let spec = parts.next().unwrap_or("");
            let mut widgets = Vec::new();
            for line in spec.lines() {
                let mut f = line.split('|');
                match f.next() {
                    Some("KPI") => {
                        widgets.push(GenWidget::Kpi {
                            label: String::from(f.next().unwrap_or("")),
                            value: String::from(f.next().unwrap_or("")),
                            accent: String::from(f.next().unwrap_or("cyan")),
                        });
                    }
                    Some("BAR") => {
                        let label = String::from(f.next().unwrap_or(""));
                        let value_text = String::from(f.next().unwrap_or(""));
                        let pct = f.next().and_then(|s| s.parse::<usize>().ok()).unwrap_or(50).min(100);
                        let accent = String::from(f.next().unwrap_or("cyan"));
                        widgets.push(GenWidget::Bar { label, value_text, pct, accent });
                    }
                    Some("CHK") => {
                        let done = f.next().unwrap_or("0") == "1";
                        let text = String::from(f.next().unwrap_or(""));
                        widgets.push(GenWidget::Check { done, text });
                    }
                    Some("TXT") => {
                        widgets.push(GenWidget::Text(String::from(f.next().unwrap_or(""))));
                    }
                    _ => {}
                }
            }
            self.ai_provider = String::from(prov);
            self.last_response = Some(ContinuumResponse {
                provider: String::from(prov),
                title: String::from(title),
                body: String::new(),
                widgets,
            });
            self.has_new_response = true;
            return;
        }
        if let Some(rest) = text.strip_prefix("RESP|") {
            self.continuum_online = true;
            let mut parts = rest.splitn(3, '|');
            let prov = parts.next().unwrap_or("local");
            let title = parts.next().unwrap_or("Resposta de Intenção");
            let body = parts.next().unwrap_or("");
            self.ai_provider = String::from(prov);
            self.last_response = Some(ContinuumResponse {
                provider: String::from(prov),
                title: String::from(title),
                body: String::from(body),
                widgets: Vec::new(),
            });
            self.has_new_response = true;
        }
    }

    fn send_arp_request(&self, nic: &mut VirtioNetDevice, target_ip: [u8; 4]) {
        let mut frame = [0u8; 42];
        frame[0..6].copy_from_slice(&[0xFF; 6]); // Broadcast
        frame[6..12].copy_from_slice(&nic.mac);
        frame[12..14].copy_from_slice(&ETHERTYPE_ARP.to_be_bytes());
        frame[14..16].copy_from_slice(&1u16.to_be_bytes()); // Ethernet
        frame[16..18].copy_from_slice(&ETHERTYPE_IPV4.to_be_bytes());
        frame[18] = 6;
        frame[19] = 4;
        frame[20..22].copy_from_slice(&1u16.to_be_bytes()); // Request
        frame[22..28].copy_from_slice(&nic.mac);
        frame[28..32].copy_from_slice(&self.ip);
        frame[32..38].copy_from_slice(&[0; 6]);
        frame[38..42].copy_from_slice(&target_ip);
        nic.send_frame(&frame);
    }

    pub fn send_icmp_echo(&self, nic: &mut VirtioNetDevice, dst_mac: [u8; 6], dst_ip: [u8; 4], seq: u16) -> bool {
        let mut frame = [0u8; 14 + 20 + 16];
        frame[0..6].copy_from_slice(&dst_mac);
        frame[6..12].copy_from_slice(&nic.mac);
        frame[12..14].copy_from_slice(&ETHERTYPE_IPV4.to_be_bytes());

        // IPv4 Header (20 bytes)
        let ip = &mut frame[14..34];
        ip[0] = 0x45;
        ip[2..4].copy_from_slice(&(36u16).to_be_bytes());
        ip[4..6].copy_from_slice(&seq.to_be_bytes());
        ip[8] = 64; // TTL
        ip[9] = 1;  // ICMP
        ip[12..16].copy_from_slice(&self.ip);
        ip[16..20].copy_from_slice(&dst_ip);
        let ip_csum = ipv4_checksum(ip);
        ip[10..12].copy_from_slice(&ip_csum.to_be_bytes());

        // ICMP Echo Request (16 bytes)
        let icmp = &mut frame[34..50];
        icmp[0] = 8; // Echo Request
        icmp[1] = 0;
        icmp[4..6].copy_from_slice(&0x4E57u16.to_be_bytes()); // "NW"
        icmp[6..8].copy_from_slice(&seq.to_be_bytes());
        icmp[8..16].copy_from_slice(b"NEWERAOS");
        let icmp_csum = ipv4_checksum(icmp);
        icmp[2..4].copy_from_slice(&icmp_csum.to_be_bytes());

        nic.send_frame(&frame)
    }

    pub fn send_udp(
        &self,
        nic: &mut VirtioNetDevice,
        dst_mac: [u8; 6],
        dst_ip: [u8; 4],
        src_port: u16,
        dst_port: u16,
        payload: &[u8],
    ) -> bool {
        let udp_len = 8 + payload.len();
        let total_ip = 20 + udp_len;
        let total_eth = 14 + total_ip;
        if total_eth > 512 {
            return false;
        }
        let mut frame = [0u8; 512];
        frame[0..6].copy_from_slice(&dst_mac);
        frame[6..12].copy_from_slice(&nic.mac);
        frame[12..14].copy_from_slice(&ETHERTYPE_IPV4.to_be_bytes());

        let ip = &mut frame[14..34];
        ip[0] = 0x45;
        ip[2..4].copy_from_slice(&(total_ip as u16).to_be_bytes());
        ip[8] = 64;
        ip[9] = 17; // UDP
        ip[12..16].copy_from_slice(&self.ip);
        ip[16..20].copy_from_slice(&dst_ip);
        let ip_csum = ipv4_checksum(ip);
        ip[10..12].copy_from_slice(&ip_csum.to_be_bytes());

        let udp = &mut frame[34..34 + udp_len];
        udp[0..2].copy_from_slice(&src_port.to_be_bytes());
        udp[2..4].copy_from_slice(&dst_port.to_be_bytes());
        udp[4..6].copy_from_slice(&(udp_len as u16).to_be_bytes());
        udp[6..8].copy_from_slice(&0u16.to_be_bytes()); // Optional in IPv4
        udp[8..8 + payload.len()].copy_from_slice(payload);

        nic.send_frame(&frame[..total_eth])
    }
}

fn ipv4_checksum(data: &[u8]) -> u16 {
    let mut sum = 0u32;
    let mut i = 0;
    while i + 1 < data.len() {
        let word = u16::from_be_bytes([data[i], data[i + 1]]) as u32;
        sum += word;
        i += 2;
    }
    if i < data.len() {
        sum += (data[i] as u32) << 8;
    }
    while (sum >> 16) != 0 {
        sum = (sum & 0xFFFF) + (sum >> 16);
    }
    !(sum as u16)
}

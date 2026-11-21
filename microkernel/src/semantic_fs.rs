//! Bare-Metal SemanticFS v0.1 — Folderless persistent semantic storage directly on VirtIO-Blk sectors.
//! Sector 0: Superblock ("NWRSEM01" + entry_count)
//! Sectors 1..=64: Fixed 512-byte Semantic Memory Records persisted via real DMA writes.

extern crate alloc;

use alloc::string::String;
use alloc::vec::Vec;

use crate::drivers::virtio_blk::VirtioBlkDevice;

const MAGIC: &[u8; 8] = b"NWRSEM01";
const MAX_ENTRIES: usize = 64;

#[derive(Clone)]
pub struct SemanticRecord {
    pub id: u32,
    pub tags: String,
    pub title: String,
    pub content: String,
}

pub struct BareMetalSemanticFS {
    pub entry_count: u32,
    pub records: Vec<SemanticRecord>,
}

impl BareMetalSemanticFS {
    /// Mounts SemanticFS from physical VirtIO-Blk sectors (formats + seeds if new volume).
    pub fn mount(disk: &VirtioBlkDevice) -> Self {
        let mut sb = [0u8; 512];
        let mut fs = Self {
            entry_count: 0,
            records: Vec::new(),
        };

        if !disk.read_sector(0, &mut sb) {
            return fs;
        }

        if &sb[0..8] != MAGIC {
            // Format fresh folderless SemanticFS volume on disk via DMA
            fs.write_superblock(disk, 0);
            fs.store(
                disk,
                "contrato pdf joao",
                "Contrato Revisado com Joao",
                "Acordo Apache 2.0 valor R$ 12500 prazo 30 dias",
            );
            fs.store(
                disk,
                "viagem orcamento florianopolis",
                "Plano Viagem Florianopolis 5 Dias",
                "Orcamento R$ 4000 transporte hospedagem clima",
            );
            return fs;
        }

        let count = u32::from_le_bytes([sb[8], sb[9], sb[10], sb[11]]).min(MAX_ENTRIES as u32);
        fs.entry_count = count;

        for idx in 0..count {
            let mut sec = [0u8; 512];
            if disk.read_sector(1 + idx as u64, &mut sec) {
                if let Some(rec) = decode_record(&sec) {
                    fs.records.push(rec);
                }
            }
        }
        fs
    }

    fn write_superblock(&self, disk: &VirtioBlkDevice, count: u32) -> bool {
        let mut sb = [0u8; 512];
        sb[0..8].copy_from_slice(MAGIC);
        sb[8..12].copy_from_slice(&count.to_le_bytes());
        let banner = b" | NEWERA SEMANTICFS BARE-METAL V1";
        sb[12..12 + banner.len()].copy_from_slice(banner);
        disk.write_sector(0, &sb)
    }

    /// Persists a new semantic memory directly onto the next disk sector via DMA.
    pub fn store(&mut self, disk: &VirtioBlkDevice, tags: &str, title: &str, content: &str) -> bool {
        if (self.entry_count as usize) >= MAX_ENTRIES {
            return false;
        }
        let id = self.entry_count + 1;
        let rec = SemanticRecord {
            id,
            tags: String::from(tags),
            title: String::from(title),
            content: String::from(content),
        };
        let encoded = encode_record(&rec);
        let sector = 1 + self.entry_count as u64;
        if !disk.write_sector(sector, &encoded) {
            return false;
        }
        self.entry_count += 1;
        if !self.write_superblock(disk, self.entry_count) {
            return false;
        }
        self.records.push(rec);
        true
    }

    /// Folderless keyword & tag search across persisted disk memories.
    pub fn search(&self, query: &str) -> Vec<&SemanticRecord> {
        let q = query.to_ascii_lowercase();
        let terms: Vec<&str> = q.split_whitespace().filter(|w| w.len() >= 2).collect();
        if terms.is_empty() {
            return self.records.iter().collect();
        }
        let mut hits = Vec::new();
        for rec in &self.records {
            let hay_tags = rec.tags.to_ascii_lowercase();
            let hay_title = rec.title.to_ascii_lowercase();
            let hay_content = rec.content.to_ascii_lowercase();
            if terms
                .iter()
                .any(|t| hay_tags.contains(t) || hay_title.contains(t) || hay_content.contains(t))
            {
                hits.push(rec);
            }
        }
        hits
    }
}

fn copy_field(dst: &mut [u8], text: &str) {
    let bytes = text.as_bytes();
    let n = bytes.len().min(dst.len());
    dst[..n].copy_from_slice(&bytes[..n]);
}

fn read_field(src: &[u8]) -> String {
    let end = src.iter().position(|&b| b == 0).unwrap_or(src.len());
    String::from(core::str::from_utf8(&src[..end]).unwrap_or(""))
}

fn encode_record(rec: &SemanticRecord) -> [u8; 512] {
    let mut buf = [0u8; 512];
    buf[0..4].copy_from_slice(b"MEM1");
    buf[4..8].copy_from_slice(&rec.id.to_le_bytes());
    copy_field(&mut buf[8..72], &rec.tags);
    copy_field(&mut buf[72..136], &rec.title);
    copy_field(&mut buf[136..512], &rec.content);
    buf
}

fn decode_record(buf: &[u8; 512]) -> Option<SemanticRecord> {
    if &buf[0..4] != b"MEM1" {
        return None;
    }
    let id = u32::from_le_bytes([buf[4], buf[5], buf[6], buf[7]]);
    Some(SemanticRecord {
        id,
        tags: read_field(&buf[8..72]),
        title: read_field(&buf[72..136]),
        content: read_field(&buf[136..512]),
    })
}

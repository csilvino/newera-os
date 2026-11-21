# Arquitetura Técnica — Newera OS

O **Newera OS** é dividido em **duas camadas desacopladas**, mantendo o princípio central de que o microkernel bare-metal (`microkernel/`) **não depende do kernel Linux nem do Windows**.

---

## Camada 0 — Microkernel Bare-Metal (`microkernel/`, Rust `no_std`, UEFI x86_64)

Compilado diretamente para `BOOTX64.EFI` (~119 KB, zero crates externas):

| Módulo | Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **UEFI Boot & HAL** | `src/uefi.rs`, `src/main.rs` | Obtém framebuffer GOP Full HD, mapa de memória e chama `ExitBootServices`. |
| **Memória & Paginação** | `src/mm.rs`, `src/paging.rs` | Heap de kernel de 16 MiB + inspeção de tabelas PML4/CR3 (`NX`). |
| **CPU & Interrupções** | `src/arch.rs`, `src/interrupts.rs` | GDT 64-bit, IDT (256 vetores), PIC 8259, PIT 100 Hz (`IRQ0`), Teclado PS/2 (`IRQ1`), Mouse PS/2 (`IRQ12`). |
| **Ring-3 & Guardian** | `src/ring3.rs` | TSS 64-bit (`RSP0`), gateway `SYSCALL`/`SYSRETQ` (`MSR_LSTAR`) e checagem de capabilities em Ring-0. |
| **Drivers PCI / VirtIO** | `src/drivers/` | Barramento PCI (`0xCF8`/`0xCFC`), UART Serial (`0x3F8`), VirtIO-Blk DMA e VirtIO-Net DMA. |
| **SemanticFS Nativo** | `src/semantic_fs.rs` | Armazenamento sem pastas direto em setores do disco físico (superbloco `NWRSEM01`). |
| **Rede Nativa** | `src/net.rs` | Ethernet II + ARP + IPv4 + ICMP Ping + UDP (`:8766` Continuum). |
| **Compositor & UI** | `src/gfx.rs`, `src/ui.rs`, `src/font_atlas.rs` | Double-buffering Full HD, alpha-blending, Orbe JARVIS + VU meter, janelas arrastáveis e Interface Generativa (`KPI`/`BAR`/`CHK`/`TXT`). |

### Próximas fronteiras bare-metal (para a comunidade)
1. **Áudio nativo:** `Intel HD Audio (HDA)` / `USB xHCI Audio` em `microkernel/src/drivers/`.
2. **Rede real + TLS:** `Intel e1000/igb`, `Realtek r8169`, Wi-Fi e pilha `TCP/DNS/TLS 1.3` em `no_std`.
3. **Armazenamento & HID reais:** `NVMe`, `AHCI` e `USB xHCI (HID)` para hardware físico via pendrive.
4. **Userspace Ring-3 & Mídia:** loader `ELF64`, escalonador preemptivo SMP (APIC) e decodificação nativa de áudio/vídeo direto no framebuffer.
5. **Inferência local bare-metal:** execução de STT/LLM/TTS em Ring 3 (CPU AVX2/AVX-512 e futuros drivers abertos de GPU/NPU).

---

## Camada 1 — Ponte Continuum, Voz Neural & Runtime OIP (`kernel/` + `skills/` + `shell/`)

Comunica-se com o microkernel via protocolo UDP (`OIP-UDP`) e também fornece um runtime web completo do [Open Intent Protocol (OIP v0.1)](spec/open-intent-protocol.md):

| Subsistema | Diretório / Arquivo | Responsabilidade |
| :--- | :--- | :--- |
| **Continuum UDP Bridge** | `kernel/continuum_udp_bridge.py` | Conecta o microkernel via UDP `:8766` à IA local (Ollama/OpenAI-compatible), Skills plugáveis, conectores web e relógio real. |
| **Neural Voice Daemon** | `kernel/voice_daemon.py` | Hands-Free VAD sempre ativo, `faster-whisper` (CUDA/CPU), anti-eco, TTS neural PT-BR e player de vídeo YouTube. |
| **Plugin Skills** | `skills/*.py` | 12 skills auto-descobertas (clima, cotação, Wikipedia, calculadora, Pomodoro, YouTube, memória semântica e controle do microkernel). |
| **Intent Engine & OIP** | `kernel/intent_engine/`, `kernel/capabilities/` | Classificação de intenções, `CapabilityRegistry`, `DataWire`s e Física de Intenção. |
| **SemanticFS (Runtime)** | `kernel/semantic_fs/` | Object store SHA-256 + SQLite WAL + FTS5 + busca vetorial local. |
| **Guardian Sandbox** | `kernel/guardian/` | Identidade `Ed25519`, cofre `AES-256-GCM`, mascaramento de PII e audit log encadeado. |
| **Shell de Referência** | `shell/` | Interface React/TypeScript/Vite/Tailwind com Lentes Cognitivas e Time-Travel. |

# Newera OS — Bare-Metal Intent-Based Operating System

> **Uma nova saída para a computação pessoal — sem Linux, sem Windows, sem navegadores.**  
> Um Sistema Operacional aberto, escrito em **Rust `no_std` (UEFI x86_64)**, centrado em **intenção por voz**, **memória semântica sem pastas (`SemanticFS`)**, **interface generativa** e **soberania criptográfica (`Guardian`)**.

[![License](https://img.shields.io/badge/License-Apache_2.0-cyan.svg)](LICENSE)
[![Bare-Metal](https://img.shields.io/badge/Microkernel-Rust_no__std_UEFI_x86__64-orange.svg)](microkernel/)
[![Protocol](https://img.shields.io/badge/Protocol-OIP_v0.1-indigo.svg)](spec/open-intent-protocol.md)

---

## Por que o Newera OS NÃO usa o kernel Linux?

Embutir o kernel Linux sob uma interface bonita transformaria o projeto em mais uma distribuição Linux — **retornar ao passado em vez de seguir em frente**.

O **Newera OS** nasce como um **microkernel bare-metal autoral em Rust `no_std`** (zero crates externas, zero Linux, zero Windows), compilado diretamente para `BOOTX64.EFI` (~119 KB) e bootável em hardware UEFI real ou QEMU + OVMF.

Este repositório entrega uma **fundação funcional completa (v1.3)** — do boot UEFI até o desktop gráfico Full HD com voz neural e IA local — e **abre oficialmente as portas para a comunidade** construir os próximos drivers e subsistemas bare-metal de forma 100% independente.

---

## O que já funciona hoje (v1.3)

### Camada 0 — Microkernel Bare-Metal (`microkernel/`, Rust `no_std`, ~119 KB)
- **Boot UEFI x86_64 puro** (`src/uefi.rs`, `src/main.rs`) com `ExitBootServices`, mapa de memória física e heap próprio de 16 MiB (`src/mm.rs`).
- **Interrupções & Hardware (`src/interrupts.rs`, `src/arch.rs`):** GDT 64-bit, IDT 256 vetores, PIC 8259 remapeado, PIT Timer 100 Hz (`IRQ0`), teclado PS/2 (`IRQ1` com Shift) e mouse PS/2 (`IRQ12`).
- **Segurança & Isolamento (`src/paging.rs`, `src/ring3.rs`):** inspeção de paginação PML4/CR3 (`NX=true`), TSS 64-bit (`RSP0`), gateway `SYSCALL`/`SYSRETQ` (`MSR_LSTAR`) em assembly com **Guardian Capability Sandbox** validado em Ring-0.
- **Armazenamento Semântico Real (`src/drivers/virtio_blk.rs`, `src/semantic_fs.rs`):** driver DMA VirtIO-Blk com escrita/leitura persistente em disco físico e **SemanticFS sem pastas** (superbloco `NWRSEM01`).
- **Rede Nativa (`src/drivers/virtio_net.rs`, `src/net.rs`):** driver TX/RX DMA VirtIO-Net com pilha Ethernet II + ARP + IPv4 + ICMP Ping + UDP (`:8766` Continuum).
- **Compositor Gráfico & Desktop Voz-Primeiro (`src/gfx.rs`, `src/ui.rs`, `src/font_atlas.rs`):** renderização Full HD sem tearing (double-buffering), wallpaper Aurora, fontes anti-aliased PT-BR, barra de menu translúcida com relógio sincronizado, **Orbe JARVIS + Medidor VU ao vivo**, dock vetorial flutuante, janelas arrastáveis e widgets de Interface Generativa (`KPI`, `BAR`, `CHK`, `TXT`).

### Camada 1 — Ponte Continuum, Voz Neural & Skills (`kernel/` + `skills/` + `shell/`)
> **Nota importante de transparência:** enquanto o microkernel bare-metal ainda não possui drivers nativos de placa de som, Wi-Fi/TLS e GPU CUDA, o modo de desenvolvimento em QEMU utiliza a ponte **Continuum UDP** (`kernel/continuum_udp_bridge.py` + `kernel/voice_daemon.py`) rodando no host para provar a experiência completa de ponta a ponta.

- **Modo Voz-Primeiro Hands-Free:** detecção automática de voz (VAD), transcrição com `faster-whisper` (`base/float16`) em GPU CUDA, anti-eco e voz neural PT-BR (`pt-BR-AntonioNeural`).
- **IA Local 100% Gratuita:** integração com `qwen2.5:3b` via Ollama (GPU) + proxy de privacidade PII do Guardian.
- **12 Skills Plugáveis (`skills/*.py`):** clima ao vivo, cotação de moedas, busca web/Wikipedia, calculadora, Pomodoro, player de vídeo YouTube e controle nativo do microkernel (`save_memory`, `search_memory`, `open_surface`, `network_ping`).
- **Runtime Web de Referência (`kernel/app.py` + `shell/`):** implementação de referência do [Open Intent Protocol (OIP v0.1)](spec/open-intent-protocol.md) com Lentes Cognitivas, Física de Intenção e Time-Travel.

---

## Roadmap & Chamado à Comunidade — O que falta construir daqui pra frente

Para que o **Newera OS** rode **100% independente em um pendrive (sem Windows e sem Linux)** com voz, mídia, internet e IA nativos, a comunidade precisa construir os seguintes subsistemas diretamente sobre o `microkernel/`:

| # | Subsistema | O que precisa ser feito | Por que é essencial |
| :-: | :--- | :--- | :--- |
| **1** | **Driver de Áudio Nativo (Intel HDA / USB Audio)** | Implementar driver PCI para `Intel HD Audio (Azalia)` e/ou `xHCI + USB Audio` em `microkernel/src/drivers/`. | Captar o microfone (VAD/VU) e reproduzir áudio/TTS direto no hardware sem depender do host. |
| **2** | **Drivers de Rede Reais + Pilha TCP/TLS 1.3** | Drivers PCI para placas reais (`Intel e1000/igb`, `Realtek r8169`, posteriormente Wi-Fi) + camada TCP/DNS/TLS em Rust `no_std` (ex.: `smoltcp` / TLS próprio). | Conectar o microkernel direto à internet real (HTTPS, APIs, WebSockets, YouTube) sem ponte externa. |
| **3** | **Userspace Ring-3 & Decodificador de Mídia Nativo** | Loader ELF64 completo em Ring 3 + isolamento de processos + decodificadores de vídeo/áudio (H.264/VP9/AV1 + AAC/Opus) renderizando quadros direto no framebuffer do compositor. | Reproduzir vídeos e músicas dentro de janelas nativas do próprio Newera OS, eliminando navegadores. |
| **4** | **Drivers de Armazenamento & Entrada Modernos** | Drivers `NVMe` / `AHCI (SATA)` e `USB xHCI (HID)` para teclado/mouse USB reais (além de VirtIO/PS2). | Garantir boot completo e persistência do `SemanticFS` em notebooks e desktops modernos via pendrive. |
| **5** | **Motor de IA & GPU / NPU Nativo** | Runtime de inferência local (CPU AVX2/AVX-512 em Ring 3 primeiro; posteriormente drivers abertos de GPU como AMD/Intel/NVIDIA GSP) para STT (`Whisper`), LLM e TTS 100% offline no bare-metal. | Tornar o Newera OS um sistema cognitivo totalmente autônomo, soberano e sem nuvem. |
| **6** | **SMP (Multi-Core) & Agendador Preemptivo** | Inicialização de APIC/IOAPIC, ativação dos núcleos secundários (APs) e escalonador preemptivo para isolar UI, áudio, rede e IA sem travamentos. | Desempenho real de desktop moderno em hardware multicore. |

---

## Como Compilar e Rodar Hoje

### 1. Compilar o Microkernel Bare-Metal (`BOOTX64.EFI`)
Pré-requisito: Rust com target `x86_64-unknown-uefi` (`rustup target add x86_64-unknown-uefi`).

```powershell
.\scripts\build_microkernel.ps1
```
O binário UEFI será gerado em `build/esp/EFI/BOOT/BOOTX64.EFI`.

### 2. Rodar o Newera OS v1.3 (QEMU + OVMF + Ponte Continuum + Voz)
No Windows com WSL2 (Ubuntu com `qemu-system-x86`, `ovmf` e opcionalmente `ollama` com `qwen2.5:3b`):

```powershell
.\scripts\run_microkernel_wsl.ps1
```

### 3. Rodar o Runtime Web de Referência (OIP v0.1)
```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate  |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn kernel.app:app --host 0.0.0.0 --port 8765
```

---

## Estrutura do Repositório

```text
├── microkernel/        # Camada 0: Microkernel Bare-Metal UEFI x86_64 em Rust (no_std)
├── kernel/             # Camada 1: Runtime OIP, Ponte Continuum UDP, Voz Neural e Guardian
├── skills/             # Plugins/Skills auto-descobertos pelo motor de intenções
├── shell/              # Shell web de referência (React/Vite/Tailwind)
├── scripts/            # Scripts de build UEFI, geração de fontes e boot em QEMU/WSL2
├── spec/               # Especificação do Open Intent Protocol (OIP v0.1)
├── tests/              # Testes automatizados do runtime
└── ARCHITECTURE.md     # Visão arquitetural detalhada
```

---

## Como Contribuir

Se você é desenvolvedor de sistemas, entusiasta de Rust `no_std`, OSDev ou IA local e acredita que a computação pessoal merece um novo começo fora do legado de 40 anos:

1. Leia o [CONTRIBUTING.md](CONTRIBUTING.md) e o [ARCHITECTURE.md](ARCHITECTURE.md).
2. Escolha um dos itens do **Roadmap Bare-Metal** acima (ex.: driver `NVMe`, `Intel HDA`, `xHCI`, `e1000`, `ELF64 Ring-3` ou `SMP`).
3. Abra uma *Issue* ou *Pull Request* mantendo o princípio fundamental do projeto: **o microkernel (`microkernel/`) permanece 100% independente, sem Linux e sem Windows**.

Licenciado sob [Apache 2.0](LICENSE).

#!/usr/bin/env bash
set -e

mkdir -p /tmp/newera_esp/EFI/BOOT
cp /mnt/d/PythonProject/SO_Newera/build/esp/EFI/BOOT/BOOTX64.EFI /tmp/newera_esp/EFI/BOOT/BOOTX64.EFI

if [ ! -f /tmp/newera_semfs.img ]; then
    dd if=/dev/zero of=/tmp/newera_semfs.img bs=1M count=16 status=none
fi

echo "[1/3] Iniciando Ollama CUDA (Flash Attention + KV Q8_0) na RTX 3060..."
OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=30m ollama serve >/tmp/ollama.log 2>&1 &
OPID=$!

for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null; then
        break
    fi
    sleep 1
done

echo "[2/3] Pre-aquecendo qwen2.5:3b na VRAM da RTX 3060..."
(curl -s http://127.0.0.1:11434/api/generate -d '{"model":"qwen2.5:3b","prompt":"","keep_alive":"30m"}' >/dev/null 2>&1 &)

NEWERA_LLM_URL=http://127.0.0.1:11434/v1 NEWERA_LLM_MODEL=qwen2.5:3b \
    python3 /mnt/d/PythonProject/SO_Newera/kernel/continuum_udp_bridge.py &
BPID=$!

trap 'kill $BPID $OPID 2>/dev/null || true' EXIT
sleep 1

echo "[3/3] Dando boot no Newera OS Bare-Metal v0.8 (UEFI x86_64)..."
qemu-system-x86_64 \
    -machine q35 \
    -m 256M \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive format=raw,file=fat:rw:/tmp/newera_esp \
    -drive file=/tmp/newera_semfs.img,if=none,id=vd0,format=raw \
    -device virtio-blk-pci,drive=vd0,disable-modern=on \
    -netdev user,id=net0 \
    -device virtio-net-pci,netdev=net0,disable-modern=on \
    -serial stdio

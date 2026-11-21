Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Newera OS - Boot Bare-Metal Microkernel no QEMU (UEFI)  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
if (-not (Test-Path $qemu)) {
    $cmd = Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue
    if ($cmd) { $qemu = $cmd.Source } else {
        Write-Host "QEMU nao encontrado. Instale com: winget install SoftwareFreedomConservancy.QEMU" -ForegroundColor Red
        exit 1
    }
}

$ovmfCandidates = @(
    "C:\Program Files\qemu\share\edk2-x86_64-code.fd",
    "C:\Program Files\qemu\share\OVMF.fd"
)
$ovmf = $ovmfCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ovmf) {
    Write-Host "Firmware UEFI (edk2-x86_64-code.fd) nao encontrado em C:\Program Files\qemu\share\" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "build\esp\EFI\BOOT\BOOTX64.EFI")) {
    .\scripts\build_microkernel.ps1
}

Write-Host "Iniciando QEMU UEFI com firmware: $ovmf" -ForegroundColor Green
Write-Host "Log serial COM1 (0x3F8) sera exibido neste terminal..." -ForegroundColor Yellow

& $qemu `
    -machine q35 `
    -m 256M `
    -drive "if=pflash,format=raw,readonly=on,file=$ovmf" `
    -drive "format=raw,file=fat:rw:build/esp" `
    -serial stdio `
    -net none

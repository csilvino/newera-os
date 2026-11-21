Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Newera OS - Bare-Metal UEFI x86_64 Microkernel Builder  " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Push-Location microkernel
cargo build --target x86_64-unknown-uefi --release
$buildExit = $LASTEXITCODE
Pop-Location

if ($buildExit -ne 0) {
    Write-Host "Erro ao compilar o microkernel!" -ForegroundColor Red
    exit $buildExit
}

$efiSrc = "microkernel\target\x86_64-unknown-uefi\release\newera-kernel.efi"
$espDir = "build\esp\EFI\BOOT"
New-Item -ItemType Directory -Force -Path $espDir | Out-Null
Copy-Item -Force $efiSrc "$espDir\BOOTX64.EFI"

$sizeKb = [Math]::Round((Get-Item "$espDir\BOOTX64.EFI").Length / 1KB, 1)
Write-Host ""
Write-Host "SUCESSO! Binario UEFI bare-metal gerado:" -ForegroundColor Green
Write-Host "  -> $espDir\BOOTX64.EFI ($sizeKb KB)" -ForegroundColor White
Write-Host ""
Write-Host "Como dar boot real (zero Linux / zero Windows):" -ForegroundColor Yellow
Write-Host "  1. QEMU + OVMF: qemu-system-x86_64 -bios OVMF.fd -drive format=raw,file=fat:rw:build/esp -serial stdio" -ForegroundColor Gray
Write-Host "  2. Hardware Real / Pendrive: copie a pasta 'EFI' de 'build\esp' para um pendrive FAT32 e de boot via UEFI." -ForegroundColor Gray

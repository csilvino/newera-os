Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "  Newera OS v1.2 - Bare-Metal + Qwen 2.5 3B (RTX 3060) + Voz Neural PT  " -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

if (-not (Test-Path "build\esp\EFI\BOOT\BOOTX64.EFI")) {
    .\scripts\build_microkernel.ps1
}

Write-Host "[0/3] Iniciando Daemon de Voz Neural + Medidor VU Real (IPC livre de firewall)..." -ForegroundColor Magenta
$voiceProc = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "kernel\voice_daemon.py" -PassThru -WindowStyle Hidden

try {
    wsl -d Ubuntu-24.04 -u root -- bash /mnt/d/PythonProject/SO_Newera/scripts/launch_qemu_wsl.sh
} finally {
    if ($voiceProc -and -not $voiceProc.HasExited) {
        Stop-Process -Id $voiceProc.Id -Force -ErrorAction SilentlyContinue
    }
}

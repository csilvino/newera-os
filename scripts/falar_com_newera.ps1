Write-Host "=================================================================" -ForegroundColor Magenta
Write-Host "  Newera OS - Modo Microfone (faster-whisper + Voz Neural PT-BR) " -ForegroundColor Magenta
Write-Host "=================================================================" -ForegroundColor Magenta
Write-Host "Dica: pressione ENTER para falar por 5s no seu microfone!" -ForegroundColor Yellow

.\.venv\Scripts\python.exe kernel\voice_daemon.py --mic

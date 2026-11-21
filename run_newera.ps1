Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "  Newera OS - Intent-Based Operating System   " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "[1/3] Criando ambiente virtual Python..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\pip.exe install -r requirements.txt
}

if (-not (Test-Path ".\shell\dist\index.html")) {
    Write-Host "[2/3] Compilando interface Newera Shell..." -ForegroundColor Yellow
    Push-Location shell
    if (-not (Test-Path ".\node_modules")) { npm install }
    npm run build
    Pop-Location
}

Write-Host "[3/3] Iniciando Newera OS em http://localhost:8765 ..." -ForegroundColor Green
Write-Host "Dica: pressione Alt+X dentro do SO para abrir o Modo Desenvolvedor Raio-X." -ForegroundColor DarkCyan
Start-Process "http://localhost:8765"
.\.venv\Scripts\uvicorn.exe kernel.app:app --host 0.0.0.0 --port 8765

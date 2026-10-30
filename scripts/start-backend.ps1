# Levanta el backend (y sirve el panel compilado en http://127.0.0.1:8000)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")
$env:PYTHONUTF8 = "1"

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
if (-not (Test-Path $venvPython)) {
    Write-Host "No hay .venv: se usa el Python global. Para aislar dependencias corre setup.bat" -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $root "frontend\dist\index.html"))) {
    Write-Host "El frontend no esta compilado. Ejecuta: cd frontend; npm run build" -ForegroundColor Yellow
}

Write-Host "Backend en http://127.0.0.1:8000  (docs: /docs)" -ForegroundColor Green
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

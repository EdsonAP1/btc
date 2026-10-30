# Servidor de desarrollo del frontend (proxy /api -> :8000)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "frontend")
Write-Host "Frontend en http://localhost:5173" -ForegroundColor Green
npm run dev

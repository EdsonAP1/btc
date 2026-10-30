# Corre la suite de tests del backend
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")
$env:PYTHONUTF8 = "1"
python -m pytest tests -q

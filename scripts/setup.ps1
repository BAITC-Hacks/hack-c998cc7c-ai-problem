param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& $Python -m venv .venv
if ($LASTEXITCODE) { throw 'Python 3.11+ is required. Pass -Python with its full path.' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
Write-Host 'Dependencies installed. Models are separate: .\.venv\Scripts\python.exe scripts/download_model.py --model small'

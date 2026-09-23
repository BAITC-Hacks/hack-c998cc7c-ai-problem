$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:HOST = '127.0.0.1'
$env:PUBLIC_MODE = 'false'
$env:ALLOWED_HOSTS = 'localhost,127.0.0.1,[::1]'
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run scripts/setup.ps1 first.' }
Write-Output 'Starting local application on 127.0.0.1 (port from backend/.env, default 8000).'
& .\.venv\Scripts\python.exe backend/main.py
exit $LASTEXITCODE

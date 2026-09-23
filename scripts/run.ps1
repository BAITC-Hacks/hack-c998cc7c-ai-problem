$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:HOST = '127.0.0.1'
$env:PUBLIC_MODE = 'false'
$env:ALLOWED_HOSTS = 'localhost,127.0.0.1,[::1]'
Write-Output 'Local application: http://127.0.0.1:8000'
& .\.venv\Scripts\python.exe backend/main.py
exit $LASTEXITCODE

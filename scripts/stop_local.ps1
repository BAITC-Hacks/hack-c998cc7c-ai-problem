$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot '.cache/local/app.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No managed background local server.'; exit 0 }
$processId = [int](Get-Content -LiteralPath $pidFile -Raw)
if ($processId -le 0) { throw 'Invalid local process ID; stopping refused.' }
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
if ($process) {
    $expected = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.venv/Scripts/python.exe'))
    if ($process.ExecutablePath -ne $expected -or $process.CommandLine -notmatch '(?i)(?:^|[\s"''])backend[\\/]main\.py(?:[\s"'']|$)') {
        throw 'PID belongs to another process; stopping refused.'
    }
    taskkill /PID $processId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stop local server' }
}
Remove-Item -LiteralPath $pidFile
Write-Output 'Local background server stopped. Data preserved.'

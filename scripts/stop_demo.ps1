$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$accessFile = Join-Path $projectRoot '.cache/demo/access.json'
$access = Get-Content -LiteralPath $accessFile -Raw | ConvertFrom-Json
foreach ($processId in @($access.tunnel_pid, $access.app_pid)) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        $expectedPaths = @((Join-Path $projectRoot '.cache/bin/cloudflared.exe'), (Join-Path $projectRoot '.venv/Scripts/python.exe'))
        if ($process.Path -notin $expectedPaths) { throw "PID $processId belongs to a different process; stopping refused." }
        taskkill /PID $processId /T /F | Out-Null
    }
}
Write-Output 'Demo stopped. Local recordings and database are preserved.'

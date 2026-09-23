$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$accessFile = Join-Path $projectRoot '.cache/demo/access.json'
if (-not (Test-Path -LiteralPath $accessFile)) { Write-Output 'No managed demo.'; exit 0 }
$access = Get-Content -LiteralPath $accessFile -Raw | ConvertFrom-Json
$managedProcesses = @(
    @{ Id = $access.tunnel_pid; Created = $access.tunnel_created; Path = (Join-Path $projectRoot '.cache/bin/cloudflared.exe') },
    @{ Id = $access.app_pid; Created = $access.app_created; Path = (Join-Path $projectRoot '.venv/Scripts/python.exe') }
)
# Validate both identities before stopping either process.
foreach ($managed in $managedProcesses) {
    $processId = [int]$managed.Id
    if ($processId -le 0) { throw 'Invalid demo process ID; stopping refused.' }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        $expected = [System.IO.Path]::GetFullPath($managed.Path)
        $created = $process.StartTime.ToUniversalTime().ToFileTimeUtc().ToString()
        if ($process.Path -ne $expected -or -not $managed.Created -or $created -ne $managed.Created) {
            throw "PID $processId does not match its recorded process identity; stopping refused."
        }
    }
}
foreach ($managed in $managedProcesses) {
    $processId = [int]$managed.Id
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        if ($process.StartTime.ToUniversalTime().ToFileTimeUtc().ToString() -ne $managed.Created) {
            throw "PID $processId changed during shutdown; stopping refused."
        }
        taskkill /PID $processId /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to stop demo process $processId" }
    }
}
Remove-Item -LiteralPath $accessFile
Write-Output 'Demo stopped. Local recordings and database are preserved.'

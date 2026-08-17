param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment not found: $python"
}
if (-not (Test-Path (Join-Path $RepoRoot ".env"))) {
    throw ".env not found. Copy .env.example to .env and fill in Discord settings first."
}

# Keep logs locally for troubleshooting.
$logDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd"
$stdout = Join-Path $logDir "bot-$stamp.log"
$stderr = Join-Path $logDir "bot-$stamp.err.log"

# For the current sample-feed test configuration only, start a local static server.
$envText = Get-Content (Join-Path $RepoRoot ".env") -Raw
if ($envText -match 'CGV_FEED_URL\s*=\s*http://localhost:8000/sample_feed\.json') {
    $existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    if (-not $existing) {
        Start-Process -FilePath $python -ArgumentList "-m","http.server","8000","--directory",$RepoRoot -WindowStyle Hidden
        Start-Sleep -Seconds 2
    }
}

# Keep the process alive. Task Scheduler also restarts the wrapper if it exits unexpectedly.
while ($true) {
    try {
        & $python (Join-Path $RepoRoot "run.py") *>> $stdout
    }
    catch {
        $_ | Out-File -Append -FilePath $stderr
    }
    Start-Sleep -Seconds 10
}

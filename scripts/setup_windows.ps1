param(
    [switch]$SkipPowerSettings
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

Write-Host "[1/6] Checking Python..."
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) { throw "Python 3.11+ is required. Install Python and rerun this script." }
$version = & python -c "import sys; print('.'.join(map(str,sys.version_info[:3])))"
Write-Host "Python $version"

Write-Host "[2/6] Creating virtual environment..."
if (-not (Test-Path ".venv")) { & python -m venv .venv }
$venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "[3/6] Preparing .env..."
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Warning ".env was created. Fill DISCORD_BOT_TOKEN, DISCORD_GUILD_ID and DISCORD_ALERT_CHANNEL_ID before the bot can log in."
}

Write-Host "[4/6] Creating Windows Scheduled Task..."
$taskName = "YongsanIMAXWatcher"
$runner = Join-Path $RepoRoot "scripts\run_bot.ps1"
$psArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" -RepoRoot `"$RepoRoot`""
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 0) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggerLogon -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "[5/6] Configuring AC power settings..."
if (-not $SkipPowerSettings) {
    try {
        # AC power only: never sleep/hibernate while plugged in. Display may still turn off.
        powercfg /change standby-timeout-ac 0 | Out-Null
        powercfg /change hibernate-timeout-ac 0 | Out-Null
        Write-Host "AC sleep/hibernate disabled. Battery settings were not changed."
    } catch {
        Write-Warning "Could not change power settings automatically. Run PowerShell as Administrator if you want this applied."
    }
}

Write-Host "[6/6] Done."
Write-Host "Task name: $taskName"
Write-Host "Repo: $RepoRoot"
Write-Host ""
if ((Get-Content ".env" -Raw) -match 'DISCORD_BOT_TOKEN=\s*(\r?\n|$)') {
    Write-Warning "Bot token is still empty. Edit .env, then run: Start-ScheduledTask -TaskName '$taskName'"
} else {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Bot task started."
}

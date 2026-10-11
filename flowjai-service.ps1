<#
flowjai-service.ps1 - run flowjAI in the background and keep it healthy.

  start    Start the server hidden (no console window) if it isn't already running.
  stop     Stop the server and PAUSE the watchdog (for maintenance / updates).
  restart  Stop then start (used by the daily scheduled restart).
  check    Watchdog: if /health fails 3 times in a row, restart. If the server
           isn't running at all, start it. Does nothing while paused.
  status   Print whether the server is up.

Run by Task Scheduler through run-hidden.vbs (see install-autorestart.bat), or
by hand:  powershell -ExecutionPolicy Bypass -File flowjai-service.ps1 status

Logs: data\logs\watchdog.log (every action + reason, capped at 5 MB) and
data\flowjai.log (the app's own output, capped at 10 MB x 4 files). Check watchdog.log to see how often the
app actually hangs.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'restart', 'check', 'status')]
    [string]$Action = 'status',
    [int]$Port = 8000,
    [int]$FailThreshold = 3,         # consecutive failed checks before a restart
    [int]$HealthTimeoutSec = 15
)

# 'Continue', not 'Stop': in Windows PowerShell 5.1, any line a native program
# (alembic, taskkill) writes to stderr would otherwise abort the whole script.
$ErrorActionPreference = 'Continue'
$Root    = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Data    = Join-Path $Root 'data'
$Logs    = Join-Path $Data 'logs'
$Python  = Join-Path $Root 'venv\Scripts\python.exe'
# Packaged build (build-exe.bat output): the exe sits in this folder instead of a venv
$Exe     = Join-Path $Root 'flowjai-inventory.exe'
$ExeMode = (Test-Path $Exe) -and -not (Test-Path $Python)
$PidFile   = Join-Path $Data 'server.pid'
$FailFile  = Join-Path $Data 'watchdog.failures'
$PauseFile = Join-Path $Data 'watchdog.paused'
$WatchLog  = Join-Path $Logs 'watchdog.log'
$HealthUrl = "http://127.0.0.1:$Port/health"

New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Write-Log([string]$msg) {
    $line = "{0}  {1,-7}  {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Action, $msg
    if ((Test-Path $WatchLog) -and (Get-Item $WatchLog).Length -gt 5MB) {
        Move-Item -Force $WatchLog "$WatchLog.1"
    }
    Add-Content -Path $WatchLog -Value $line
    Write-Output $line
}

# One instance at a time: a 2-minute check must not collide with a restart in progress.
$mutex = New-Object System.Threading.Mutex($false, 'Local\flowjai-service')
if (-not $mutex.WaitOne(0)) { exit 0 }

function Test-Health {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec $HealthTimeoutSec
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

function Get-ListenerPids {
    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                 Select-Object -ExpandProperty OwningProcess -Unique)
    } catch { return @() }
}

function Stop-Server {
    $killed = @()
    $ids = @()
    if (Test-Path $PidFile) { $ids += [int](Get-Content $PidFile -ErrorAction SilentlyContinue) }
    $ids += Get-ListenerPids
    foreach ($id in ($ids | Where-Object { $_ } | Select-Object -Unique)) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        # Only ever kill flowjAI (Python or the packaged exe) - never another program on the port
        if ($p -and ($p.ProcessName -like 'python*' -or $p.ProcessName -like 'flowjai-inventory*')) {
            # /T also ends child processes
            & taskkill.exe /PID $id /T /F | Out-Null
            $killed += $id
        }
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    return $killed
}

function Start-ExeServer {
    # The exe runs its own migrations and refuses to start if they fail
    $proc = Start-Process -FilePath $Exe -ArgumentList '--lan', '--no-browser' -WorkingDirectory $Root -PassThru
    Set-Content -Path $PidFile -Value $proc.Id
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Health) { Write-Log "Server up (flowjai-inventory.exe, PID $($proc.Id))"; return $true }
        if ($proc.HasExited -and -not (Test-Health)) {
            Write-Log "ERROR: flowjai-inventory.exe exited during start-up (see data\flowjai.log)"
            return $false
        }
    }
    Write-Log "WARNING: flowjai-inventory.exe started but /health not answering after 90 s"
    return $false
}

function Start-Server {
    if ($ExeMode) { return Start-ExeServer }
    if (-not (Test-Path $Python)) {
        Write-Log "ERROR: $Python not found. Run launch.bat once to set up the Python environment."
        exit 1
    }
    $dbPath = (Join-Path $Data 'flowjai.db') -replace '\\', '/'
    $env:DATABASE_URL = "sqlite:///$dbPath"

    # Apply any pending database migrations first (same as launch.bat)
    Push-Location $Backend
    try { & $Python -m alembic upgrade head *> (Join-Path $Logs 'migrate.log') } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) {
        # Starting on a half-upgraded database gives silently empty screens
        Write-Log "ERROR: database upgrade failed - NOT starting. See data\logs\migrate.log"
        return $false
    }

    # Hidden window: nobody can click into it (QuickEdit freeze) or close it by accident.
    # Goes through run.py so output lands in data\flowjai.log, which is size-capped
    # (a plain stdout redirect here could grow without limit).
    $proc = Start-Process -FilePath $Python `
        -ArgumentList "`"$(Join-Path $Root 'run.py')`"", '--lan', '--no-browser', '--log-file' `
        -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    Set-Content -Path $PidFile -Value $proc.Id

    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        if ($proc.HasExited) { Write-Log "ERROR: server exited during start-up (see data\flowjai.log)"; return $false }
        if (Test-Health) { Write-Log "Server up (PID $($proc.Id))"; return $true }
    }
    Write-Log "WARNING: server started (PID $($proc.Id)) but /health not answering after 90 s"
    return $false
}

try {
    switch ($Action) {
        'status' {
            if (Test-Health) { Write-Output "flowjAI is running on port $Port" }
            else { Write-Output "flowjAI is NOT responding on port $Port" }
            if (Test-Path $PauseFile) { Write-Output "Watchdog is PAUSED (run 'start' to resume)" }
        }
        'start' {
            Remove-Item $PauseFile -ErrorAction SilentlyContinue
            if (Test-Health) { Write-Log 'Already running'; break }
            $leftover = Stop-Server
            if ($leftover.Count) { Write-Log "Cleared unresponsive process(es): $($leftover -join ', ')" }
            Start-Server | Out-Null
            Remove-Item $FailFile -ErrorAction SilentlyContinue
        }
        'stop' {
            Set-Content -Path $PauseFile -Value (Get-Date -Format s)
            $k = Stop-Server
            Write-Log "Stopped ($(if ($k.Count) { 'PID ' + ($k -join ', ') } else { 'nothing was running' })). Watchdog paused."
        }
        'restart' {
            if (Test-Path $PauseFile) { Write-Log 'Skipped scheduled restart: watchdog is paused'; break }
            $k = Stop-Server
            Write-Log "Restarting (stopped PID $($k -join ', '))"
            Start-Server | Out-Null
            Remove-Item $FailFile -ErrorAction SilentlyContinue
        }
        'check' {
            if (Test-Path $PauseFile) { break }
            if (Test-Health) { Remove-Item $FailFile -ErrorAction SilentlyContinue; break }

            if ((Get-ListenerPids).Count -eq 0) {
                Write-Log 'Server not running - starting it'
                Start-Server | Out-Null
                Remove-Item $FailFile -ErrorAction SilentlyContinue
                break
            }
            $n = 1
            if (Test-Path $FailFile) { $n = [int](Get-Content $FailFile) + 1 }
            Set-Content -Path $FailFile -Value $n
            Write-Log "Health check failed ($n of $FailThreshold) - server is running but not answering"
            if ($n -ge $FailThreshold) {
                $k = Stop-Server
                Write-Log "HUNG - restarting (killed PID $($k -join ', '))"
                Start-Server | Out-Null
                Remove-Item $FailFile -ErrorAction SilentlyContinue
            }
        }
    }
} finally {
    $mutex.ReleaseMutex()
}

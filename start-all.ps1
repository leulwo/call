# PaperFlow - start everything (Redis, API, Celery worker, frontend)
# Usage:  powershell -ExecutionPolicy Bypass -File F:\call\start-all.ps1

$ErrorActionPreference = "SilentlyContinue"
$Root = "F:\call"
$RedisDir = "$Root\.backend-runtime\redis\Redis-7.4.9-Windows-x64-msys2-with-Service"

function Test-Port($port) {
    (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) -ne $null
}

# ── 1. Redis ────────────────────────────────────────────────────────────────
if (Test-Port 6379) {
    Write-Host "[redis]    already running on 6379" -ForegroundColor DarkGray
} else {
    if (Get-Service -Name "Redis" -ErrorAction SilentlyContinue) {
        Start-Service -Name "Redis"
        Write-Host "[redis]    started Windows service" -ForegroundColor Green
    } else {
        Start-Process -FilePath "$RedisDir\redis-server.exe" `
            -ArgumentList @("--port", "6379", "--save", "--appendonly", "no") `
            -WindowStyle Hidden
        Write-Host "[redis]    started as background process (install the service to make it permanent - see stop-all.ps1 header)" -ForegroundColor Yellow
    }
}

# ── 2. Backend API (uvicorn) ───────────────────────────────────────────────
if (Test-Port 8000) {
    Write-Host "[api]      already running on 8000" -ForegroundColor DarkGray
} else {
    Start-Process -FilePath "$Root\.venv\Scripts\python.exe" `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") `
        -WorkingDirectory "$Root\backend" -WindowStyle Hidden `
        -RedirectStandardOutput "$Root\tmp\api.stdout.log" `
        -RedirectStandardError "$Root\tmp\api.stderr.log"
    Write-Host "[api]      starting uvicorn on 8000 (logs: tmp\api.stderr.log)" -ForegroundColor Green
}

# ── 3. Celery worker ────────────────────────────────────────────────────────
$celeryRunning = Get-CimInstance Win32_Process -Filter "Name='celery.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -match "celery.*-A worker" }
if ($celeryRunning) {
    Write-Host "[worker]   already running" -ForegroundColor DarkGray
} else {
    Start-Process -FilePath "$Root\.venv\Scripts\celery.exe" `
        -ArgumentList @("-A", "worker", "worker", "--pool=solo", "--loglevel=info") `
        -WorkingDirectory "$Root\backend" -WindowStyle Hidden `
        -RedirectStandardOutput "$Root\tmp\celery1.stdout.log" `
        -RedirectStandardError "$Root\tmp\celery1.stderr.log"
    Write-Host "[worker]   starting celery worker (logs: tmp\celery1.stderr.log)" -ForegroundColor Green
}

# ── 4. Frontend (Next.js dev) ───────────────────────────────────────────────
if (Test-Port 3000) {
    Write-Host "[frontend] already running on 3000" -ForegroundColor DarkGray
} else {
    Start-Process -FilePath "C:\Program Files\nodejs\node.exe" `
        -ArgumentList @("-r", "./patch-node24.js", "node_modules/next/dist/bin/next", "dev") `
        -WorkingDirectory "$Root\frontend" -WindowStyle Hidden `
        -RedirectStandardOutput "$Root\tmp\frontend.stdout.log" `
        -RedirectStandardError "$Root\tmp\frontend.stderr.log"
    Write-Host "[frontend] starting next dev on 3000 (logs: tmp\frontend.stdout.log)" -ForegroundColor Green
}

# ── Health wait ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Waiting for services..."
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $api = Test-Port 8000; $fe = Test-Port 3000; $rd = Test-Port 6379
    if ($api -and $fe -and $rd) { break }
    Start-Sleep -Seconds 2
}
Write-Host ""
Write-Host ("redis     : " + ($(if (Test-Port 6379) { "UP" } else { "DOWN" }))) 
Write-Host ("backend   : " + ($(if (Test-Port 8000) { "UP   http://localhost:8000" } else { "DOWN - check tmp\api.stderr.log" })))
Write-Host ("frontend  : " + ($(if (Test-Port 3000) { "UP   http://localhost:3000" } else { "DOWN - check tmp\frontend.stderr.log" })))

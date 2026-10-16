# PaperFlow - stop everything
# Usage:  powershell -ExecutionPolicy Bypass -File F:\call\stop-all.ps1
#
# NOTE: to make Redis permanent (survives reboots, no console needed), run this
# ONCE in an ADMINISTRATOR PowerShell:
#   & "F:\call\.backend-runtime\redis\Redis-7.4.9-Windows-x64-msys2-with-Service\RedisService.exe" install -c "F:\call\.backend-runtime\redis\Redis-7.4.9-Windows-x64-msys2-with-Service\redis.conf"
# Then Redis auto-starts with Windows and start-all.ps1 will simply use it.

$ErrorActionPreference = "SilentlyContinue"

# Stop frontend (next dev)
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "next/dist/bin/next" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "[frontend] stopped" -ForegroundColor Yellow

# Stop celery worker (shim + children)
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "celery.*-A worker" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "[worker]   stopped" -ForegroundColor Yellow

# Stop API (uvicorn)
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match "uvicorn app.main:app" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Write-Host "[api]      stopped" -ForegroundColor Yellow

# Stop redis background process (NOT the Windows service, if installed)
Get-Process -Name "redis-server" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "*Redis-7.4.9*" } |
    Stop-Process -Force
Write-Host "[redis]    stopped (background process; service install survives reboots)" -ForegroundColor Yellow

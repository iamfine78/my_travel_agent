# ============================================
# 智能旅行规划系统 · 本地启动脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File start.ps1
# 功能：1) 确保 Redis 在跑（Windows 原生版）  2) 启动后端 uvicorn
#      前端单独：cd frontend && npm run dev
# ============================================
$ErrorActionPreference = "Continue"
$RedisExe = "C:\Users\19674\redis-win\redis-server.exe"

# ---- 1. 检查 Redis 是否已在监听 6379 ----
$redisUp = Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue
if (-not $redisUp) {
    Write-Host "[1/3] Redis 未运行，启动中..." -ForegroundColor Yellow
    if (Test-Path $RedisExe) {
        Start-Process $RedisExe -ArgumentList "--port 6379" -WindowStyle Hidden
        Start-Sleep -Seconds 2
        Write-Host "      Redis 已启动" -ForegroundColor Green
    } else {
        Write-Host "      未找到 redis-server.exe，请检查 C:\Users\19674\redis-win" -ForegroundColor Red
    }
} else {
    Write-Host "[1/3] Redis 已在运行 (端口 6379)" -ForegroundColor Green
}

# ---- 2. 检查高德 Key 是否已配置 ----
$envFile = "C:\Users\19674\PycharmProjects\pythonProject2\backend\.env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Encoding UTF8
    $hasAmap = ($envContent | Select-String "^AMAP_WEB_KEY=.+").Count -gt 0
    if ($hasAmap) {
        Write-Host "[2/3] 高德 Key 已配置" -ForegroundColor Green
    } else {
        Write-Host "[2/3] 高德 Key 未配置！请注册 https://lbs.amap.com/ 并填入 backend/.env" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/3] backend/.env 不存在，请复制 backend/.env.example 并填写" -ForegroundColor Yellow
}

# ---- 3. 启动后端（uvicorn 热重载，代码改了自动重启） ----
Write-Host "[3/3] 启动后端 http://127.0.0.1:8000 ..." -ForegroundColor Green
Set-Location "C:\Users\19674\PycharmProjects\pythonProject2\backend"
& "C:\Users\19674\PycharmProjects\pythonProject2\.venv\Scripts\python.exe" -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

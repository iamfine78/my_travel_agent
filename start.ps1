# ============================================
# 智能旅行规划系统 · 本地启动脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File start.ps1
# 功能：1) 确保 Redis 在跑  2) 校验高德 Key  3) 启动后端 uvicorn
#      前端单独：cd frontend && npm run dev
# 说明：路径全部相对脚本自身（$PSScriptRoot），脚本可放在任意目录，无需改代码
# ============================================
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

# ---- 1. Redis：优先用 $env:REDIS_SERVER_EXE，其次 PATH 上的 redis-server ----
$redisUp = Get-NetTCPConnection -LocalPort 6379 -State Listen -ErrorAction SilentlyContinue
if ($redisUp) {
    Write-Host "[1/3] Redis 已在运行 (端口 6379)" -ForegroundColor Green
} else {
    $redisExe = $env:REDIS_SERVER_EXE
    if (-not $redisExe) {
        $cmd = Get-Command redis-server -ErrorAction SilentlyContinue
        if ($cmd) { $redisExe = $cmd.Source }
    }
    if ($redisExe -and (Test-Path $redisExe)) {
        Write-Host "[1/3] 启动 Redis: $redisExe" -ForegroundColor Yellow
        Start-Process $redisExe -ArgumentList "--port 6379" -WindowStyle Hidden
        Start-Sleep -Seconds 2
    } else {
        Write-Host "[1/3] 未找到 Redis。" -ForegroundColor Yellow
        Write-Host "      可设 `$env:REDIS_SERVER_EXE 指向 redis-server.exe，或用 Docker 起：docker compose up -d redis" -ForegroundColor DarkGray
        Write-Host "      后端会『优雅降级』继续工作，只是天气/POI 每次都要重查，较慢。" -ForegroundColor DarkGray
    }
}

# ---- 2. 校验高德 Key 是否已配置 ----
$envFile = Join-Path $Backend ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Encoding UTF8
    if (($envContent | Select-String "^AMAP_WEB_KEY=.+").Count -gt 0) {
        Write-Host "[2/3] 高德 Web Key 已配置" -ForegroundColor Green
    } else {
        Write-Host "[2/3] 高德 Web Key 未配置！注册 https://lbs.amap.com/ 后填入 backend/.env" -ForegroundColor Yellow
    }
} else {
    Write-Host "[2/3] backend/.env 不存在：请复制 backend/.env.example 并填写" -ForegroundColor Yellow
}

# ---- 3. 启动后端（uvicorn 热重载） ----
if (-not (Test-Path $Python)) {
    Write-Host "[3/3] 未找到虚拟环境：$Python" -ForegroundColor Red
    Write-Host "      请先执行：python -m venv .venv" -ForegroundColor DarkGray
    Write-Host "                .venv\Scripts\python.exe -m pip install -r backend\requirements.txt" -ForegroundColor DarkGray
    exit 1
}
Write-Host "[3/3] 启动后端 http://127.0.0.1:8000 ..." -ForegroundColor Green
Set-Location $Backend
& $Python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# ===== AI 驱动的研发质量前置平台 - 一键启动前后端 =====
# 用法：右键"使用 PowerShell 运行"，或双击 启动服务.bat
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

function Test-Listening([int]$port) {
    try {
        $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop
        return $true
    } catch { return $false }
}

# ---- 1/2 后端 ----
if (Test-Listening 8000) {
    Write-Host "[1/2] 后端已在运行，跳过" -ForegroundColor Yellow
} else {
    Write-Host "[1/2] 启动后端 (uvicorn :8000)..." -ForegroundColor Cyan
    & (Join-Path $backend "_start_backend.ps1")
}

# ---- 2/2 前端 ----
if (Test-Listening 5173) {
    Write-Host "[2/2] 前端已在运行，跳过" -ForegroundColor Yellow
} else {
    Write-Host "[2/2] 启动前端 (vite :5173)..." -ForegroundColor Cyan
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$frontend`" && npm run dev > dev_out.log 2> dev_err.log" -WindowStyle Hidden
}

# ---- 等待就绪（最多 40 秒）----
Write-Host "等待服务就绪" -NoNewline
$okB = Test-Listening 8000
$okF = Test-Listening 5173
foreach ($i in 1..40) {
    if (-not $okB) { $okB = Test-Listening 8000 }
    if (-not $okF) { $okF = Test-Listening 5173 }
    if ($okB -and $okF) { break }
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
}
Write-Host ""

# ---- 状态汇总 ----
Write-Host "=============================================" -ForegroundColor Green
if ($okB) { Write-Host "  后端  http://localhost:8000/docs   已就绪" -ForegroundColor Green }
else      { Write-Host "  后端  启动超时，请查看 backend/backend_err.log" -ForegroundColor Red }
if ($okF) { Write-Host "  前端  http://localhost:5173        已就绪" -ForegroundColor Green }
else      { Write-Host "  前端  启动超时，请查看 frontend/dev_err.log" -ForegroundColor Red }
Write-Host "  访问入口: http://localhost:5173" -ForegroundColor White
Write-Host "=============================================" -ForegroundColor Green

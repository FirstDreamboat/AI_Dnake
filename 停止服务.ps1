# ===== AI 驱动的研发质量前置平台 - 一键停止前后端 =====
# 用法：右键"使用 PowerShell 运行"，或双击 停止服务.bat
function Get-ListenPid([int]$port) {
    try {
        return Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop |
            Select-Object -ExpandProperty OwningProcess -Unique
    } catch { return @() }
}

function Stop-Service([int]$port, [string]$name) {
    $pids = Get-ListenPid $port
    if (-not $pids) {
        Write-Host "[$name] 未在运行" -ForegroundColor Yellow
        return
    }
    foreach ($p in $pids) {
        Write-Host "[$name] 停止进程树 (PID $p)..." -ForegroundColor Cyan
        # /T 连同子进程一起结束（vite 的 esbuild、uvicorn 工作进程等）
        taskkill /F /T /PID $p 2>$null | Out-Null
    }
    Start-Sleep -Milliseconds 500
    if (Get-ListenPid $port) {
        Write-Host "[$name] 停止失败，端口仍被占用，请手动检查" -ForegroundColor Red
    } else {
        Write-Host "[$name] 已停止" -ForegroundColor Green
    }
}

Stop-Service 5173 "前端"
Stop-Service 8000 "后端"
Write-Host "全部服务已关闭" -ForegroundColor Green

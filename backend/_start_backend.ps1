$root = "c:\Users\admin\Desktop\AI\backend"
Set-Location $root

# Idempotent guard: skip if port 8000 is already listening,
# otherwise the new uvicorn fails to bind ("Address already in use") and looks like a startup failure.
$occupied = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $existingPid = ($occupied | Select-Object -First 1).OwningProcess
    Write-Output "BACKEND ALREADY RUNNING (PID $existingPid) - skip duplicate start"
    exit 0
}

$err = Join-Path $root "backend_err.log"
$out = Join-Path $root "backend_out.log"
if (Test-Path $err) { Remove-Item $err -Force }
if (Test-Path $out) { Remove-Item $out -Force }
$p = Start-Process -FilePath "$root\venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
  -WorkingDirectory $root `
  -RedirectStandardError $err `
  -RedirectStandardOutput $out `
  -WindowStyle Hidden -PassThru
Start-Sleep 2
Write-Output "STARTED PID=$($p.Id)"

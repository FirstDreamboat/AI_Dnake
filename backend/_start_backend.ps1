$root = "c:\Users\admin\Desktop\AI\backend"
Set-Location $root
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

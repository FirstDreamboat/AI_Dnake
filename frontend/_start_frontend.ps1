$ErrorActionPreference = "Stop"
$root = "c:\Users\admin\Desktop\AI\frontend"
Set-Location $root
Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm", "run", "dev" `
    -WorkingDirectory $root `
    -RedirectStandardOutput "$root\frontend_start.log" `
    -RedirectStandardError "$root\frontend_err.log" `
    -WindowStyle Hidden
Write-Output "frontend start requested"

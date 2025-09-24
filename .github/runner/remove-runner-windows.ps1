param(
  [Parameter(Mandatory=$true)] [string]$RepoUrl,
  [Parameter(Mandatory=$true)] [string]$Token,
  [string]$InstallDir = "C:\actions-runner"
)
Set-Location $InstallDir
.\svc stop
cmd.exe /c ".\config.cmd remove --url $RepoUrl --token $Token"
.\svc uninstall
Set-Location \
Remove-Item -Recurse -Force $InstallDir
Write-Host "==> Runner eliminado." -ForegroundColor Yellow

param(
  [Parameter(Mandatory=$true)] [string]$RepoUrl,   # ej: https://github.com/USER/LBANK_bot
  [Parameter(Mandatory=$true)] [string]$Token,     # Registration token desde Settings > Actions > Runners > New runner
  [string]$RunnerName = "LBANK-WIN",
  [string]$Labels = "self-hosted,windows,bot",
  [string]$InstallDir = "C:\actions-runner"
)

Write-Host "==> Creating $InstallDir" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Set-Location $InstallDir

# Descarga la última versión estable (x64)
$runnerVersion = "2.317.0"
$pkg = "actions-runner-win-x64-$runnerVersion.zip"
Invoke-WebRequest -Uri "https://github.com/actions/runner/releases/download/v$runnerVersion/$pkg" -OutFile $pkg
Expand-Archive -Path $pkg -DestinationPath $InstallDir -Force

# Configurar runner (no interactivo)
cmd.exe /c ".\config.cmd --url $RepoUrl --token $Token --name $RunnerName --labels $Labels --unattended"

# Instalar como servicio y arrancar
.\svc install
Start-Sleep -Seconds 2
.\svc start

Write-Host "==> Runner instalado como servicio y en ejecución." -ForegroundColor Green
Write-Host "Labels: $Labels | Nombre: $RunnerName"

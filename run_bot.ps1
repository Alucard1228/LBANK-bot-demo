# run_bot.ps1
# Activa el entorno virtual y ejecuta el bot de trading

# Ruta al entorno virtual
$venvPath = ".\.venv\Scripts\Activate.ps1"

# Verificar si existe el entorno
if (Test-Path $venvPath) {
    Write-Host "Activando entorno virtual..." -ForegroundColor Green
    & $venvPath
} else {
    Write-Host "⚠️  Entorno virtual no encontrado. Creando uno nuevo..." -ForegroundColor Yellow
    python -m venv .venv
    & $venvPath
    pip install -r requirements.txt
}

# Instalar plotly si no está presente (por si acaso)
python -c "import plotly" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando plotly..." -ForegroundColor Cyan
    pip install plotly
}

Write-Host "Iniciando el bot de trading..." -ForegroundColor Green
python run_bot_realtime_auto.py
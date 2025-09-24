# LBANK_bot — GitHub Actions (15h/día)

## 💡 ¿Qué hace?
- Arranca el bot 3 veces al día (cada 5h) y lo deja corriendo **5h** por vez → **15h/día**.
- Sube el `operaciones.csv` como artifact al final de cada ejecución.
- Mantiene vivo el cron con un keep-alive semanal.

> Nota: GitHub-hosted runners limitan cada **job** a máx. **6h**; por eso dividimos en 3 bloques de 5h. [Ver límites oficiales].  
> [Límites: job 6h, workflow hasta 72h/35 días según doc].  

## 🔐 Configura Secrets (Settings → Secrets → Actions)
Crea estos **Repository secrets**:
- `LBANK_API_KEY` — (opcional en PAPER)
- `LBANK_API_SECRET` — (opcional en PAPER)
- `TELEGRAM_TOKEN` — token de tu bot
- `TELEGRAM_ALLOWED_IDS` — tu chat ID (o varios separados por coma)

## ▶️ Cómo usar
1. Sube el repo a GitHub con todo el código del bot y estos workflows.
2. En la pestaña **Actions**, habilita workflows si te lo pide.
3. O bien déjalo al cron; o dispara manual con **Run workflow**.

## 🗂️ Dónde ver resultados
- **Artifacts**: al final de cada ejecución, descarga `operaciones-<run_id>.zip` (contiene `operaciones.csv`).
- **Telegram**: verás alertas OPEN/TP/SL/resúmenes si configuraste el token/ID.

## 🛠️ Ajustes útiles
- Cambia el cron en `.github/workflows/run-bot-3x-per-day.yml` si quieres otros horarios (UTC).
- Para más/menos horas por bloque, ajusta `RUNTIME_SEC` (p. ej., 14 400 = 4 h).  
- Si tu cuenta usa **self-hosted runners**, puedes subir cada job a >6 h. [Ver doc].

## ⚠️ Límites importantes
- **Job execution time** (GitHub-hosted): máx. 6 h.  
- **Scheduled workflows** se especifican en **UTC** con cron POSIX.  

Referencias: límites 6 h job y cron programado.

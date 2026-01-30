$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)
$env:CONFIG_PATH = "$PWD\\config\\config.yaml"
$env:REDIS_URL = "redis://localhost:6379/0"

& .venv\\Scripts\\python.exe -m celery -A services.analyzer.worker worker --loglevel=info --queues=analyze_task --pool=solo

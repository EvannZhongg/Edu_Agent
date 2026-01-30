$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)
$env:CONFIG_PATH = "$PWD\\config\\config.yaml"
$env:REDIS_URL = "redis://localhost:6379/0"

& .venv\\Scripts\\python.exe -m celery -A services.parser.worker worker --loglevel=info --queues=parse_task --pool=solo

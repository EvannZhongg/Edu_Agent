$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)
$env:CONFIG_PATH = "$PWD\\config\\config.yaml"

$venvPython = ".venv\\Scripts\\python.exe"
$configPath = "config\\config.yaml"

$port = & $venvPython -c "import yaml; from pathlib import Path; cfg=yaml.safe_load(Path('$configPath').read_text(encoding='utf-8')) or {}; gateway=cfg.get('gateway', {}); print(gateway.get('port', 8000))"
$bindHost = & $venvPython -c "import yaml; from pathlib import Path; cfg=yaml.safe_load(Path('$configPath').read_text(encoding='utf-8')) or {}; gateway=cfg.get('gateway', {}); print(gateway.get('host', '0.0.0.0'))"

& $venvPython -m uvicorn services.gateway.app.main:app --host $bindHost --port $port

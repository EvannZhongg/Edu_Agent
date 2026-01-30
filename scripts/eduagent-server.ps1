$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$venvPython = ".venv\\Scripts\\python.exe"
$configPath = "config\\config.yaml"

$port = & $venvPython -c "import yaml; from pathlib import Path; cfg=yaml.safe_load(Path('$configPath').read_text(encoding='utf-8')) or {}; gateway=cfg.get('gateway', {}); print(gateway.get('port', 8000))"
$bindHost = & $venvPython -c "import yaml; from pathlib import Path; cfg=yaml.safe_load(Path('$configPath').read_text(encoding='utf-8')) or {}; gateway=cfg.get('gateway', {}); print(gateway.get('host', '0.0.0.0'))"

Write-Host "[EduAgent] Starting backend on $bindHost`:$port ..."
Start-Process -FilePath $venvPython -ArgumentList "-m", "uvicorn", "services.gateway.app.main:app", "--host", $bindHost, "--port", $port

Write-Host "[EduAgent] Starting parser worker ..."
Start-Process -FilePath $venvPython -ArgumentList "-m", "celery", "-A", "services.parser.worker", "worker", "--loglevel=info", "--queues=parse_task", "--pool=solo"

Write-Host "[EduAgent] Starting analyzer worker ..."
Start-Process -FilePath $venvPython -ArgumentList "-m", "celery", "-A", "services.analyzer.worker", "worker", "--loglevel=info", "--queues=analyze_task", "--pool=solo"

if (Test-Path "frontend\\package.json") {
  Write-Host "[EduAgent] Starting frontend ..."
  Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d frontend && npm run dev"
} else {
  Write-Host "[EduAgent] Frontend not found, skipped."
}

Write-Host "[EduAgent] All services started."

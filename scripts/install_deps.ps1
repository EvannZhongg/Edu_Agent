$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$venvPython = ".venv\\Scripts\\python.exe"
if (-not (Test-Path $venvPython)) {
  Write-Error "未找到 .venv\\Scripts\\python.exe，请先创建项目内虚拟环境。"
}

& $venvPython -m pip install -U pip
& $venvPython -m pip install -r services\\gateway\\requirements.txt
& $venvPython -m pip install -r services\\parser\\requirements.txt
& $venvPython -m pip install -r services\\analyzer\\requirements.txt

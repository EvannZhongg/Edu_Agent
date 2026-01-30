param(
  [string]$InstallPath = "F:\\Model\\mineru"
)

$ErrorActionPreference = "Stop"

New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
Set-Location -Path $InstallPath

if (-not (Test-Path ".venv\\Scripts\\python.exe")) {
  python -m venv .venv
}

& .venv\\Scripts\\python.exe -m pip install -U pip
& .venv\\Scripts\\python.exe -m pip install -U "magic-pdf"

Write-Host "MinerU 已安装到 $InstallPath"
Write-Host "如需配置 CLI 路径，请更新 config/config.yaml 的 mineru.cli_path"

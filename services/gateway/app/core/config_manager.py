from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

from .config_models import AppConfig


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


def _resolve_paths(data: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    base_dir = config_path.resolve().parent.parent
    storage = data.get("storage", {})
    for key in ("base_path", "lancedb_path", "sqlite_path"):
        if key in storage and isinstance(storage[key], str):
            p = Path(storage[key])
            if not p.is_absolute():
                storage[key] = str((base_dir / p).resolve())
    data["storage"] = storage

    toc = data.get("toc", {})
    if isinstance(toc.get("poppler_path"), str):
        p = Path(toc["poppler_path"])
        if not p.is_absolute():
            toc["poppler_path"] = str((base_dir / p).resolve())
    data["toc"] = toc
    return data


def load_config(path: str | None = None, overrides: Dict[str, Any] | None = None) -> AppConfig:
    config_path = Path(
        path
        or os.getenv("CONFIG_PATH", "./config/config.yaml")
    )
    data = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    if overrides:
        data = _deep_merge(data, overrides)

    data = _resolve_env(data)
    data = _resolve_paths(data, config_path)
    return AppConfig.model_validate(data)

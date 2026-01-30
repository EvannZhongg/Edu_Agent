from __future__ import annotations

import json
import os
import shlex
import subprocess
import sqlite3
import zipfile
import time
import base64
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import yaml
import requests
from celery import Celery
from dotenv import load_dotenv


def load_config() -> Dict[str, Any]:
    config_path = os.getenv("CONFIG_PATH", "./config/config.yaml")
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    data = _resolve_env(data)
    return _resolve_paths(data, Path(config_path))


def _update_document_status(config: Dict[str, Any], doc_id: str, **fields: Any) -> None:
    sqlite_path = config["storage"].get("sqlite_path", "./data/sqlite/app.db")
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    try:
        fields["updated_at"] = datetime.utcnow().isoformat()
        columns = ", ".join([f"{key}=?" for key in fields.keys()])
        values = list(fields.values()) + [doc_id]
        conn.execute(f"UPDATE documents SET {columns} WHERE id=?", values)
        conn.commit()
    finally:
        conn.close()


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


def build_command(config: Dict[str, Any], input_path: str, output_dir: str) -> list[str]:
    mineru_cfg = config.get("mineru", {})
    install_path = os.getenv("MINERU_INSTALL_PATH") or mineru_cfg.get("install_path")
    default_cli = "magic-pdf"
    if install_path:
        candidate = Path(install_path) / ".venv" / "Scripts" / "magic-pdf.exe"
        default_cli = str(candidate)

    cli = mineru_cfg.get("cli_path", default_cli)
    config_path = mineru_cfg.get("config_path", "./config/mineru_config.json")

    template = mineru_cfg.get("command_template")
    command = template.format(
        cli=cli,
        input=input_path,
        output=output_dir,
        config=config_path,
    )

    return shlex.split(command)


def _bool_to_str(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def parse_with_api(config: Dict[str, Any], input_path: str, output_dir: Path) -> Dict[str, Any]:
    mineru_cfg = config.get("mineru", {})
    base_url = mineru_cfg.get("api_base_url", "http://localhost:8002").rstrip("/")
    endpoint = mineru_cfg.get("api_endpoint", "/file_parse")
    url = f"{base_url}{endpoint}"

    params = mineru_cfg.get("api_params", {})
    data: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, (list, dict)):
            data[key] = json.dumps(value, ensure_ascii=False)
        else:
            data[key] = _bool_to_str(value)

    if not mineru_cfg.get("api_download_output", True):
        data["output_dir"] = str(output_dir)

    retries = int(mineru_cfg.get("api_retries", 3))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with open(input_path, "rb") as f:
                files = {"files": (Path(input_path).name, f, "application/pdf")}
                response = requests.post(
                    url,
                    data=data,
                    files=files,
                    timeout=(
                        mineru_cfg.get("api_connect_timeout_s", 30),
                        mineru_cfg.get("api_timeout_s", 3600),
                    ),
                )
            last_error = None
            break
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(5 * attempt)
            continue

    if last_error:
        raise last_error

    if response.status_code != 200:
        raise RuntimeError(f"MinerU API error {response.status_code}: {response.text}")

    payload = response.json()
    (output_dir / "api_response.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    filename_key = Path(input_path).stem
    middle_json_str = None
    result_data = None
    if isinstance(payload.get("results"), dict):
        if filename_key in payload["results"]:
            result_data = payload["results"][filename_key]
            middle_json_str = result_data.get("middle_json")
        elif payload["results"]:
            first_key = next(iter(payload["results"].keys()))
            result_data = payload["results"][first_key]
            middle_json_str = result_data.get("middle_json")

    md_saved = False
    if isinstance(result_data, dict):
        md_content = result_data.get("md_content")
        if md_content:
            md_path = output_dir / f"{Path(input_path).stem}.md"
            md_path.write_text(md_content, encoding="utf-8")
            md_saved = True

        images_map = result_data.get("images") or {}
        if isinstance(images_map, dict) and images_map:
            assets_dir = output_dir / "images"
            tables_dir = assets_dir / "tables"
            assets_dir.mkdir(parents=True, exist_ok=True)
            tables_dir.mkdir(parents=True, exist_ok=True)
            for img_name, img_b64 in images_map.items():
                try:
                    img_path = assets_dir / img_name
                    img_path.write_bytes(base64.b64decode(img_b64))
                except Exception:
                    continue

    if middle_json_str:
        try:
            middle_json = json.loads(middle_json_str)
        except Exception:
            middle_json = {"pdf_info": []}
        (output_dir / "middle.json").write_text(
            json.dumps(middle_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if isinstance(result_data, dict) and result_data.get("images"):
            _move_table_images(middle_json, output_dir / "images", output_dir / "images" / "tables")
        return {"api_mode": "json", "middle_json": True, "md_saved": md_saved}

    return {"api_mode": "json", "middle_json": False, "md_saved": md_saved, "keys": list(payload.keys())}


def _move_table_images(middle_json: Dict[str, Any], assets_dir: Path, tables_dir: Path) -> None:
    table_images: set[str] = set()
    for page in middle_json.get("pdf_info", []):
        for block in page.get("para_blocks", []):
            if str(block.get("type", "")).upper() == "TABLE":
                _extract_image_paths_from_block(block, table_images)
    for img_name in table_images:
        filename = Path(img_name).name
        src = assets_dir / filename
        dst = tables_dir / filename
        if src.exists():
            try:
                shutil.move(str(src), str(dst))
            except Exception:
                continue


def _extract_image_paths_from_block(block: Any, collected: set[str]) -> None:
    if isinstance(block, dict):
        image_path = block.get("image_path")
        if image_path:
            collected.add(image_path)
        for value in block.values():
            _extract_image_paths_from_block(value, collected)
    elif isinstance(block, list):
        for item in block:
            _extract_image_paths_from_block(item, collected)


load_dotenv()
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("edu_parser", broker=redis_url, backend=redis_url)


@celery_app.task(name="parse_task")
def parse_task(input_pdf: str, doc_id: str, doc_type: str = "textbook", target_doc_id: str | None = None) -> Dict[str, Any]:
    config = load_config()
    _update_document_status(config, doc_id, status="parsing", last_step="parse", error_message="")
    base_path = Path(config["storage"]["base_path"])
    output_dir = base_path / doc_id / config["mineru"]["output_subdir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    mineru_mode = config.get("mineru", {}).get("mode", "api")
    try:
        if mineru_mode == "api":
            api_result = parse_with_api(config, input_pdf, output_dir)
            result_payload = {
                "doc_id": doc_id,
                "output_dir": str(output_dir),
                "returncode": 0,
                "stdout": json.dumps(api_result, ensure_ascii=False),
                "stderr": "",
            }
        else:
            command = build_command(config, input_pdf, str(output_dir))
            result = subprocess.run(command, capture_output=True, text=True)
            result_payload = {
                "doc_id": doc_id,
                "output_dir": str(output_dir),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
    except Exception as exc:
        _update_document_status(config, doc_id, status="failed", last_step="parse", error_message=str(exc))
        raise

    pipeline_cfg = config.get("pipeline", {})
    if result_payload["returncode"] == 0:
        _update_document_status(config, doc_id, status="parsed", last_step="parse", error_message="")
    else:
        _update_document_status(
            config,
            doc_id,
            status="failed",
            last_step="parse",
            error_message=result_payload.get("stderr") or "parse failed",
        )

    if result_payload["returncode"] == 0 and pipeline_cfg.get("auto_analyze", False):
        if doc_type == "workbook":
            if pipeline_cfg.get("auto_workbook_bind", False) and target_doc_id:
                celery_app.send_task("workbook_task", args=[doc_id, target_doc_id], queue="analyze_task")
        else:
            celery_app.send_task("analyze_task", args=[doc_id], queue="analyze_task")

    return result_payload

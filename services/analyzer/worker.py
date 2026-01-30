from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

import yaml
from celery import Celery
from dotenv import load_dotenv

from .pipelines import (
    build_tree_from_middle_json,
    enrich_tree_with_llm,
    tree_to_markdown,
    segment_questions,
    bind_questions_to_tree,
)
from .pipelines.textbook import apply_toc_correction, index_tree
from .pipelines.content_align import fill_tree_content
from .pipelines.llm_client import segment_questions_llm, bind_questions_llm


load_dotenv()
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("edu_analyzer", broker=redis_url, backend=redis_url)


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    if isinstance(value, dict):
        return {k: _resolve_env(v) for k, v in value.items()}
    return value


def load_config() -> Dict[str, Any]:
    config_path = os.getenv("CONFIG_PATH", "./config/config.yaml")
    data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    data = _resolve_env(data)
    return _resolve_paths(data, Path(config_path))


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


def _upsert_tree(config: Dict[str, Any], doc_id: str, tree_json: str) -> None:
    sqlite_path = config["storage"].get("sqlite_path", "./data/sqlite/app.db")
    Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS document_trees (doc_id TEXT PRIMARY KEY, tree_json TEXT, updated_at TEXT)"
        )
        conn.execute(
            "INSERT INTO document_trees (doc_id, tree_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET tree_json=excluded.tree_json, updated_at=excluded.updated_at",
            (doc_id, tree_json, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def locate_middle_json(output_dir: Path) -> Path | None:
    candidates = list(output_dir.glob("**/*.json"))
    for name in ("middle.json", "middle_json.json", "middle_json"):
        for file in candidates:
            if name in file.name:
                return file
    return candidates[0] if candidates else None


@celery_app.task(name="analyze_task")
def analyze_task(doc_id: str, node_id: str | None = None):
    config = load_config()
    _update_document_status(config, doc_id, status="analyzing", last_step="analyze", error_message="")
    base_path = Path(config["storage"]["base_path"])
    output_dir = base_path / doc_id / config["mineru"]["output_subdir"]
    middle_json_path = locate_middle_json(output_dir)
    if not middle_json_path:
        _update_document_status(config, doc_id, status="failed", last_step="analyze", error_message="missing middle_json")
        return {"doc_id": doc_id, "status": "missing_middle_json"}

    try:
        middle_json = json.loads(middle_json_path.read_text(encoding="utf-8"))
        tree = build_tree_from_middle_json(middle_json, doc_id)
        pdf_path = None
        for candidate in output_dir.parent.glob("*.pdf"):
            pdf_path = str(candidate)
            break

        toc_precheck_path = output_dir / "toc_precheck.json"
        if toc_precheck_path.exists():
            toc_items = json.loads(toc_precheck_path.read_text(encoding="utf-8")).get("toc_tree") or []
            tree["toc"] = {"source": "vlm_precheck", "items": toc_items}
            toc_cfg = config.get("toc", {})
            if toc_items:
                if toc_cfg.get("align_mode") == "patcher":
                    from .pipelines.patcher import build_tree_from_toc

                    patched = build_tree_from_toc(
                        toc_items,
                        middle_json,
                        toc_cfg.get("min_similarity", 0.6),
                    )
                    patched["doc_id"] = doc_id
                    patched["toc"] = tree["toc"]
                    tree = patched
                elif toc_cfg.get("align_mode") == "llm":
                    from .pipelines.toc import align_titles_with_llm

                    tree = align_titles_with_llm(tree, toc_items, config)
                else:
                    from .pipelines.toc import align_titles

                    tree = align_titles(tree, toc_items, toc_cfg.get("min_similarity", 0.6))
        else:
            tree = apply_toc_correction(tree, middle_json, output_dir, config, pdf_path)
        tree = fill_tree_content(tree, middle_json, 0.8)
        # 先落盘结构化树（未填充分析）
        tree_path = base_path / doc_id / "knowledge_tree.json"
        tree_json = json.dumps(tree, ensure_ascii=False, indent=2)
        tree_path.write_text(tree_json, encoding="utf-8")
        _upsert_tree(config, doc_id, tree_json)

        # 再做 LLM 分析填充
        tree = enrich_tree_with_llm(tree, config)
        index_tree(tree, config)
    except Exception as exc:
        _update_document_status(config, doc_id, status="failed", last_step="analyze", error_message=str(exc))
        raise

    tree_path = base_path / doc_id / "knowledge_tree.json"
    tree_json = json.dumps(tree, ensure_ascii=False, indent=2)
    tree_path.write_text(tree_json, encoding="utf-8")
    _upsert_tree(config, doc_id, tree_json)

    md_path = base_path / doc_id / "knowledge_tree.md"
    md_path.write_text(tree_to_markdown(tree), encoding="utf-8")

    summary = tree.get("analysis_summary", {})
    status = "completed"
    if summary.get("failed"):
        status = "completed_with_errors"
    _update_document_status(
        config,
        doc_id,
        status=status,
        last_step="analyze",
        error_message="",
        result_path=str(tree_path),
    )
    return {"doc_id": doc_id, "status": "completed", "tree_path": str(tree_path)}


@celery_app.task(name="toc_precheck")
def toc_precheck(doc_id: str, pdf_path: str):
    config = load_config()
    toc_cfg = config.get("toc", {})
    if not toc_cfg.get("enable", True) or not toc_cfg.get("use_vlm", True):
        return {"doc_id": doc_id, "status": "skipped"}

    output_dir = Path(config["storage"]["base_path"]) / doc_id / config["mineru"]["output_subdir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from .pipelines.pdf_images import load_pdf_images_range
        from .pipelines.llm_client import extract_toc_from_image_page

        k = int(toc_cfg.get("scan_k_pages", 5))
        extend_max = int(toc_cfg.get("extend_max_pages", 3))
        dpi = toc_cfg.get("pdf_dpi", 150)
        poppler = toc_cfg.get("poppler_path")

        toc_items = []
        last_is_toc = False

        def check_page(page_no: int) -> bool:
            images_b64 = load_pdf_images_range(pdf_path, page_no, page_no, dpi, poppler)
            if not images_b64:
                return False
            data_url = f"data:image/jpeg;base64,{images_b64[0]}"
            result = extract_toc_from_image_page(data_url, config)
            items = result.get("items", []) or []
            if result.get("has_toc") and items:
                toc_items.extend(items)
                return True
            return False

        for page_no in range(1, k + 1):
            last_is_toc = check_page(page_no)

        extra = 0
        while last_is_toc and extra < extend_max:
            page_no = k + extra + 1
            last_is_toc = check_page(page_no)
            extra += 1

        toc_precheck_path = output_dir / "toc_precheck.json"
        toc_precheck_path.write_text(
            json.dumps({"toc_tree": toc_items}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"doc_id": doc_id, "status": "completed", "count": len(toc_items)}
    except Exception as exc:
        return {"doc_id": doc_id, "status": "failed", "error": str(exc)}


@celery_app.task(name="workbook_task")
def workbook_task(workbook_id: str, target_doc_id: str):
    config = load_config()
    _update_document_status(config, workbook_id, status="binding", last_step="workbook_bind", error_message="")
    base_path = Path(config["storage"]["base_path"])
    output_dir = base_path / workbook_id / config["mineru"]["output_subdir"]
    middle_json_path = locate_middle_json(output_dir)
    if not middle_json_path:
        _update_document_status(config, workbook_id, status="failed", last_step="workbook_bind", error_message="missing middle_json")
        return {"workbook_id": workbook_id, "status": "missing_middle_json"}

    try:
        middle_json = json.loads(middle_json_path.read_text(encoding="utf-8"))
        blocks = []
        for page in middle_json.get("pdf_info", []):
            for block in page.get("para_blocks", []):
                block = dict(block)
                block["page_id"] = page.get("page_id")
                blocks.append(block)

        if config.get("pipeline", {}).get("use_llm_segmentation", True):
            questions = segment_questions_llm(blocks, config)
            if not questions:
                questions = segment_questions(blocks)
        else:
            questions = segment_questions(blocks)

        tree_path = base_path / target_doc_id / "knowledge_tree.json"
        if not tree_path.exists():
            _update_document_status(config, workbook_id, status="failed", last_step="workbook_bind", error_message="missing tree")
            return {"workbook_id": workbook_id, "status": "missing_tree"}

        tree = json.loads(tree_path.read_text(encoding="utf-8"))
        if config.get("pipeline", {}).get("use_llm_binding", True):
            bindings = bind_questions_llm(questions, tree, config)
            if not bindings:
                bindings = bind_questions_to_tree(questions, tree)
        else:
            bindings = bind_questions_to_tree(questions, tree)

        binding_path = base_path / workbook_id / "question_bindings.json"
        binding_path.write_text(json.dumps(bindings, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        _update_document_status(config, workbook_id, status="failed", last_step="workbook_bind", error_message=str(exc))
        raise

    _update_document_status(
        config,
        workbook_id,
        status="completed",
        last_step="workbook_bind",
        error_message="",
        result_path=str(binding_path),
    )
    return {"workbook_id": workbook_id, "status": "completed", "binding_path": str(binding_path)}

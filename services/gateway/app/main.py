from __future__ import annotations

import os
import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

from .core.config_manager import load_config
from .core.celery_app import create_celery
from .core.llm_client import embed_texts
from .core.rag import search_lancedb, generate_answer
from .db import LanceDBClient, create_sqlite_engine, create_session_factory, init_db, session_scope, Document


load_dotenv()
app = FastAPI(title="Edu Gateway")
celery_app = create_celery()

# 预先加载配置用于 CORS（必须在启动前添加中间件）
_boot_config = load_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_boot_config.gateway.cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConfigOverride(BaseModel):
    data: Dict[str, Any]


class TreePayload(BaseModel):
    data: Dict[str, Any]


class ChatQuery(BaseModel):
    query: str
    doc_ids: list[str] | None = None
    mode: str = "hybrid"
    top_k: int | None = None

@app.on_event("startup")
def startup():
    config = load_config()
    sqlite_path = Path(config.storage.sqlite_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_sqlite_engine(str(sqlite_path))
    init_db(engine)
    session_factory = create_session_factory(engine)

    app.state.config = config
    app.state.session_factory = session_factory
    app.state.lancedb = LanceDBClient(config.storage.lancedb_path).connect()



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/config/global")
def get_global_config():
    config = load_config()
    return config.model_dump()


@app.post("/api/config/project/{project_id}")
def set_project_config(project_id: str, override: ConfigOverride):
    config = load_config(overrides=override.data)
    return {"project_id": project_id, "effective_config": config.model_dump()}


@app.post("/api/upload")
def upload_pdf(
    file: UploadFile = File(...),
    doc_type: str = Form("textbook"),
    target_doc_id: str | None = Form(None),
):
    config = app.state.config
    base_path = Path(config.storage.base_path)
    doc_id = str(uuid.uuid4())
    doc_dir = base_path / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)

    input_path = doc_dir / file.filename
    hasher = hashlib.sha256()
    with input_path.open("wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            f.write(chunk)
    file_hash = hasher.hexdigest()

    with session_scope(app.state.session_factory) as session:
        existing = (
            session.query(Document)
            .filter(Document.file_hash == file_hash)
            .order_by(Document.created_at.desc())
            .first()
        )
        if existing:
            shutil.rmtree(doc_dir, ignore_errors=True)
            if existing.status != "completed":
                task = celery_app.send_task(
                    "parse_task",
                    args=[existing.source_path or str(input_path), existing.id, existing.doc_type, existing.target_doc_id],
                    queue="parse_task",
                )
                return {
                    "doc_id": existing.id,
                    "status": existing.status,
                    "dedup": True,
                    "message": "已存在相同文档，未完成流程，已自动续跑",
                    "task_id": task.id,
                }
            return {
                "doc_id": existing.id,
                "status": existing.status,
                "dedup": True,
                "message": "已存在相同文档，跳过重复处理",
            }

    with session_scope(app.state.session_factory) as session:
        session.add(
            Document(
                id=doc_id,
                filename=file.filename,
                file_hash=file_hash,
                status="uploaded",
                doc_type=doc_type,
                target_doc_id=target_doc_id or "",
                source_path=str(input_path),
                result_path="",
            )
        )

    task = celery_app.send_task(
        "parse_task",
        args=[str(input_path), doc_id, doc_type, target_doc_id],
        queue="parse_task",
    )
    # 目录预检：并行调用 VLM 目录抽取
    if doc_type == "textbook":
        celery_app.send_task(
            "toc_precheck",
            args=[doc_id, str(input_path)],
            queue="analyze_task",
        )
    return {"doc_id": doc_id, "task_id": task.id, "status": "queued"}


@app.get("/api/tasks/{task_id}/status")
def task_status_placeholder(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "status": result.status, "result": result.result}


@app.get("/api/doc/{doc_id}/status")
def document_status(doc_id: str):
    with session_scope(app.state.session_factory) as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return {
            "doc_id": doc.id,
            "status": doc.status,
            "last_step": doc.last_step,
            "error_message": doc.error_message,
            "updated_at": doc.updated_at,
        }


@app.get("/api/docs")
def list_documents():
    config = app.state.config
    base_path = Path(config.storage.base_path)
    with session_scope(app.state.session_factory) as session:
        docs = session.query(Document).order_by(Document.created_at.desc()).all()
        return [
            {
                "doc_id": d.id,
                "filename": d.filename,
                "status": d.status,
                "doc_type": d.doc_type,
                "result_path": d.result_path,
                "updated_at": d.updated_at,
                "last_step": d.last_step,
                "error_message": d.error_message,
                "has_tree": (base_path / d.id / "knowledge_tree.json").exists(),
            }
            for d in docs
        ]


@app.delete("/api/doc/{doc_id}")
def delete_document(doc_id: str):
    config = app.state.config
    base_path = Path(config.storage.base_path)
    doc_dir = base_path / doc_id
    with session_scope(app.state.session_factory) as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        session.delete(doc)
    shutil.rmtree(doc_dir, ignore_errors=True)
    return {"doc_id": doc_id, "status": "deleted"}


@app.get("/api/doc/{doc_id}/tree")
def get_tree_placeholder(doc_id: str):
    config = app.state.config
    tree_path = Path(config.storage.base_path) / doc_id / "knowledge_tree.json"
    if tree_path.exists():
        import json

        return {"doc_id": doc_id, "tree": json.loads(tree_path.read_text(encoding="utf-8"))}
    return {"doc_id": doc_id, "tree": None}


@app.post("/api/doc/{doc_id}/node/{node_id}/regenerate")
def regenerate_node_placeholder(doc_id: str, node_id: str):
    task = celery_app.send_task("analyze_task", args=[doc_id, node_id], queue="analyze_task")
    return {"doc_id": doc_id, "node_id": node_id, "task_id": task.id, "status": "queued"}


@app.put("/api/doc/{doc_id}/tree/structure")
def update_tree_structure_placeholder(doc_id: str, payload: TreePayload):
    config = app.state.config
    tree_path = Path(config.storage.base_path) / doc_id / "knowledge_tree.json"
    tree_path.write_text(
        payload.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {"doc_id": doc_id, "status": "updated", "path": str(tree_path)}


@app.post("/api/doc/{doc_id}/resume")
def resume_document(doc_id: str):
    with session_scope(app.state.session_factory) as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")

        if not doc.source_path:
            raise HTTPException(status_code=400, detail="缺少原始文件路径，无法恢复")

        if doc.last_step == "parse":
            task = celery_app.send_task(
                "parse_task",
                args=[doc.source_path, doc.id, doc.doc_type, doc.target_doc_id],
                queue="parse_task",
            )
            return {"doc_id": doc.id, "task_id": task.id, "status": "requeued", "step": "parse"}
        if doc.last_step == "analyze":
            task = celery_app.send_task("analyze_task", args=[doc.id], queue="analyze_task")
            return {"doc_id": doc.id, "task_id": task.id, "status": "requeued", "step": "analyze"}
        if doc.last_step == "workbook_bind":
            task = celery_app.send_task("workbook_task", args=[doc.id, doc.target_doc_id], queue="analyze_task")
            return {"doc_id": doc.id, "task_id": task.id, "status": "requeued", "step": "workbook_bind"}

        # 若无 last_step 记录但未完成，默认重新走解析
        if doc.status != "completed":
            task = celery_app.send_task(
                "parse_task",
                args=[doc.source_path, doc.id, doc.doc_type, doc.target_doc_id],
                queue="parse_task",
            )
            return {"doc_id": doc.id, "task_id": task.id, "status": "requeued", "step": "parse"}

        raise HTTPException(status_code=400, detail="当前状态不可恢复或缺少步骤信息")


@app.post("/api/chat/query")
def chat_query(payload: ChatQuery):
    config = app.state.config
    embed_cfg = config.models.embedding
    vectors = embed_texts(
        embed_cfg.base_url,
        embed_cfg.api_key,
        embed_cfg.model_name,
        [payload.query],
    )
    embedding = vectors[0] if vectors else []
    top_k = payload.top_k or config.rag.top_k
    results = search_lancedb(app.state.lancedb, embedding, payload.doc_ids, top_k)
    answer = generate_answer(payload.query, results, config.model_dump())
    return {"answer": answer, "hits": results}

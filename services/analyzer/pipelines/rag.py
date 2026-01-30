from __future__ import annotations

from typing import Any, Dict, List

import lancedb
import pyarrow as pa

from .llm_client import embed_texts


def chunk_text(text: str, size: int, overlap: int) -> List[str]:
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _iter_nodes(nodes: List[Dict[str, Any]]):
    for node in nodes:
        yield node
        if node.get("children"):
            yield from _iter_nodes(node["children"])


def _ensure_table(db, name: str, schema: pa.Schema):
    if name in db.table_names():
        return db.open_table(name)
    return db.create_table(name, schema=schema)


def index_tree_into_lancedb(tree: Dict[str, Any], config: Dict[str, Any]) -> None:
    if not config.get("rag", {}).get("enable", True):
        return

    db = lancedb.connect(config["storage"]["lancedb_path"])
    dim = config["models"]["embedding"]["dimension"]

    text_schema = pa.schema(
        [
            ("vector", pa.list_(pa.float32(), dim)),
            ("doc_id", pa.string()),
            ("node_id", pa.string()),
            ("text", pa.string()),
            ("knowledge_points", pa.string()),
            ("is_question", pa.bool_()),
        ]
    )
    table_schema = pa.schema(
        [
            ("vector", pa.list_(pa.float32(), dim)),
            ("doc_id", pa.string()),
            ("node_id", pa.string()),
            ("image_path", pa.string()),
            ("html_code", pa.string()),
            ("summary", pa.string()),
        ]
    )

    text_table = _ensure_table(db, "text_chunks", text_schema)
    table_table = _ensure_table(db, "table_summaries", table_schema)

    doc_id = tree.get("doc_id", "")
    if doc_id:
        text_table.delete(f"doc_id = '{doc_id}'")
        table_table.delete(f"doc_id = '{doc_id}'")

    chunk_size = config["rag"]["chunk_size"]
    overlap = config["rag"]["chunk_overlap"]

    text_records: List[Dict[str, Any]] = []
    for node in _iter_nodes(tree.get("nodes", [])):
        raw_text = "\n".join(node.get("raw_text", []))
        knowledge_points = ""
        if isinstance(node.get("analysis"), dict):
            knowledge_points = str(node["analysis"].get("knowledge_points", ""))
        for chunk in chunk_text(raw_text, chunk_size, overlap):
            text_records.append(
                {
                    "doc_id": doc_id,
                    "node_id": node.get("node_id"),
                    "text": chunk,
                    "knowledge_points": knowledge_points,
                    "is_question": False,
                }
            )

    if text_records:
        try:
            vectors = embed_texts([r["text"] for r in text_records], config)
            for record, vec in zip(text_records, vectors):
                record["vector"] = vec
            text_table.add(text_records)
        except Exception:
            return

    table_records: List[Dict[str, Any]] = []
    for node in _iter_nodes(tree.get("nodes", [])):
        for table in node.get("content_refs", {}).get("tables", []):
            html = table.get("html") or ""
            summary = html[:500]
            table_records.append(
                {
                    "doc_id": doc_id,
                    "node_id": node.get("node_id"),
                    "image_path": table.get("image_path") or "",
                    "html_code": html,
                    "summary": summary,
                }
            )

    if table_records:
        try:
            vectors = embed_texts([r["summary"] for r in table_records], config)
            for record, vec in zip(table_records, vectors):
                record["vector"] = vec
            table_table.add(table_records)
        except Exception:
            return

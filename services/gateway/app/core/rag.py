from __future__ import annotations

from typing import Any, Dict, List, Optional

from .llm_client import chat_complete, embed_texts, safe_json

from pathlib import Path
import os


def _filter_clause(field: str, values: List[str]) -> str:
    quoted = ",".join([f"'{v}'" for v in values])
    return f"{field} IN ({quoted})"


def search_lancedb(db, embedding: List[float], doc_ids: Optional[List[str]], top_k: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if "text_chunks" in db.table_names():
        table = db.open_table("text_chunks")
        query = table.search(embedding).limit(top_k)
        if doc_ids:
            query = query.where(_filter_clause("doc_id", doc_ids))
        results.extend(query.to_list())
    if "table_summaries" in db.table_names():
        table = db.open_table("table_summaries")
        query = table.search(embedding).limit(top_k)
        if doc_ids:
            query = query.where(_filter_clause("doc_id", doc_ids))
        results.extend(query.to_list())
    return results


def generate_answer(query: str, contexts: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    llm_cfg = config["models"]["llm"]
    prompt_path = config.get("prompts", {}).get("rag_answer")
    system_prompt = (
        Path(prompt_path).read_text(encoding="utf-8")
        if prompt_path and os.path.exists(prompt_path)
        else "根据检索片段回答问题，输出 JSON(answer, sources)。"
    )
    context_text = "\n".join(
        [f"[{c.get('doc_id')}#{c.get('node_id')}] {c.get('text') or c.get('summary')}" for c in contexts]
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"问题：{query}\n检索片段：\n{context_text[:12000]}"},
    ]
    content = chat_complete(llm_cfg["base_url"], llm_cfg["api_key"], llm_cfg["model_name"], messages)
    payload = safe_json(content)
    if payload:
        return payload
    return {"answer": content, "sources": []}

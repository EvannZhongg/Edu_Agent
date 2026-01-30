from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .llm_client import extract_knowledge
from concurrent.futures import ThreadPoolExecutor, as_completed
from .toc import build_toc, align_titles, align_titles_with_llm
from .patcher import build_tree_from_toc
from .rag import index_tree_into_lancedb


TITLE_TYPES = {"TITLE", "TITLE_BLOCK"}
TEXT_TYPES = {"TEXT", "PARA", "PARAGRAPH"}
IMAGE_TYPES = {"IMAGE", "FIGURE"}
TABLE_TYPES = {"TABLE"}


def _normalize_type(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.upper()
    return str(value).upper()


def _extract_para_blocks(middle_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for page in middle_json.get("pdf_info", []):
        page_index = page.get("page_id")
        for block in page.get("para_blocks", []):
            block_copy = dict(block)
            block_copy["page_id"] = page_index
            blocks.append(block_copy)
    return blocks


def _new_node(node_id: str, title: str, level: int) -> Dict[str, Any]:
    return {
        "node_id": node_id,
        "title": title,
        "level": level,
        "page_range": [],
        "status": "pending",
        "content_refs": {"text_blocks": [], "images": [], "tables": []},
        "analysis": None,
        "raw_text": [],
        "children": [],
    }


def _update_page_range(node: Dict[str, Any], page_id: int | None) -> None:
    if page_id is None:
        return
    pages = node["page_range"]
    if not pages:
        node["page_range"] = [page_id, page_id]
    else:
        node["page_range"][0] = min(node["page_range"][0], page_id)
        node["page_range"][1] = max(node["page_range"][1], page_id)


def build_tree_from_middle_json(middle_json: Dict[str, Any], doc_id: str) -> Dict[str, Any]:
    blocks = _extract_para_blocks(middle_json)
    nodes: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []
    counters = [0, 0, 0, 0, 0, 0]

    for block in blocks:
        block_type = _normalize_type(block.get("type"))
        text = (block.get("text") or "").strip()
        level = int(block.get("level") or 1)
        page_id = block.get("page_id")
        block_id = block.get("id") or block.get("block_id")

        if block_type in TITLE_TYPES:
            counters[level - 1] += 1
            for i in range(level, len(counters)):
                counters[i] = 0
            node_id = "chapter_" + "_".join(str(c) for c in counters[:level])
            node = _new_node(node_id, text or f"章节 {node_id}", level)
            _update_page_range(node, page_id)

            while stack and stack[-1]["level"] >= level:
                stack.pop()
            if stack:
                stack[-1]["children"].append(node)
            else:
                nodes.append(node)
            stack.append(node)
            continue

        if not stack:
            root = _new_node("chapter_1", "未归类", 1)
            nodes.append(root)
            stack.append(root)

        current = stack[-1]
        _update_page_range(current, page_id)

        if block_type in TEXT_TYPES:
            current["content_refs"]["text_blocks"].append(
                {"id": block_id, "text": text, "page_id": page_id}
            )
            if text:
                current["raw_text"].append(text)
        elif block_type in IMAGE_TYPES:
            current["content_refs"]["images"].append(
                {"id": block_id, "path": block.get("image_path"), "page_id": page_id}
            )
        elif block_type in TABLE_TYPES:
            current["content_refs"]["tables"].append(
                {
                    "id": block_id,
                    "html": block.get("html"),
                    "image_path": block.get("image_path"),
                    "page_id": page_id,
                }
            )
        else:
            if text:
                current["raw_text"].append(text)

    return {"doc_id": doc_id, "nodes": nodes}


def _iter_nodes(node_list: List[Dict[str, Any]]):
    for node in node_list:
        yield node
        if node.get("children"):
            yield from _iter_nodes(node["children"])


def enrich_tree_with_llm(tree: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    nodes = [n for n in _iter_nodes(tree["nodes"])]
    max_workers = int(config.get("pipeline", {}).get("llm_concurrency", 2))
    stats = {"analyzed": 0, "failed": 0, "skipped": 0}

    def _analyze(node: Dict[str, Any]):
        if node.get("analysis"):
            stats["skipped"] += 1
            return node
        text = "\n".join(node.get("raw_text", []))
        if not text:
            stats["skipped"] += 1
            return node
        try:
            node["analysis"] = extract_knowledge(text, config, node.get("type"), node.get("title"))
            node["status"] = "analyzed"
            stats["analyzed"] += 1
        except Exception as exc:
            node["analysis"] = {"error": str(exc)}
            node["status"] = "failed"
            stats["failed"] += 1
        return node

    if max_workers <= 1:
        for node in nodes:
            _analyze(node)
        return tree

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_analyze, n) for n in nodes]
        for _ in as_completed(futures):
            pass
    tree["analysis_summary"] = stats
    return tree


def apply_toc_correction(tree: Dict[str, Any], middle_json: Dict[str, Any], output_dir: Path, config: Dict[str, Any], pdf_path: str | None = None) -> Dict[str, Any]:
    toc_items, source = build_toc(middle_json, output_dir, config, pdf_path)
    tree["toc"] = {"source": source, "items": toc_items}
    toc_cfg = config.get("toc", {})
    if toc_items:
        if toc_cfg.get("align_mode") == "patcher":
            patched = build_tree_from_toc(
                toc_items,
                middle_json,
                toc_cfg.get("min_similarity", 0.6),
            )
            patched["doc_id"] = tree.get("doc_id")
            patched["toc"] = tree["toc"]
            return patched
        if toc_cfg.get("align_mode") == "llm":
            tree = align_titles_with_llm(tree, toc_items, config)
        else:
            tree = align_titles(tree, toc_items, toc_cfg.get("min_similarity", 0.6))
    return tree


def index_tree(tree: Dict[str, Any], config: Dict[str, Any]) -> None:
    index_tree_into_lancedb(tree, config)


def save_tree(tree: Dict[str, Any], output_path: Path) -> None:
    output_path.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

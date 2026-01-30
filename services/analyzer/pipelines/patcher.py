from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    from Levenshtein import ratio as levenshtein_ratio
except Exception:  # pragma: no cover
    levenshtein_ratio = None

from difflib import SequenceMatcher


def _similarity(a: str, b: str) -> float:
    if levenshtein_ratio:
        return float(levenshtein_ratio(a, b))
    return SequenceMatcher(None, a, b).ratio()


def flatten_para_blocks(middle_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for page in middle_json.get("pdf_info", []):
        page_idx = page.get("page_id", page.get("page_idx", 0))
        for block in page.get("para_blocks", []):
            block = dict(block)
            block["_page_idx"] = page_idx
            text = (block.get("text") or "").strip()
            block["_raw_text"] = text
            flat.append(block)
    return flat


def build_tree_from_toc(
    toc_items: List[Dict[str, Any]],
    middle_json: Dict[str, Any],
    threshold: float = 0.8,
) -> Dict[str, Any]:
    flat_blocks = flatten_para_blocks(middle_json)
    nodes: List[Dict[str, Any]] = []
    cursor = 0

    for toc_item in toc_items:
        title = toc_item.get("title", "").strip()
        level = int(toc_item.get("level", 1))
        node = {
            "node_id": f"toc_{len(nodes)+1}",
            "title": title,
            "level": level,
            "type": toc_item.get("type"),
            "page_range": [],
            "status": "pending",
            "content_refs": {"text_blocks": [], "images": [], "tables": []},
            "analysis": None,
            "raw_text": [],
            "children": [],
            "_start_index": None,
        }

        best_score = 0.0
        best_idx = None
        search_window = flat_blocks[cursor : cursor + 500]
        for idx, block in enumerate(search_window):
            if block.get("type") not in ["TITLE", "TEXT", "PARA", "PARAGRAPH", "TITLE_BLOCK", "title", "text"]:
                continue
            score = _similarity(title, block.get("_raw_text", ""))
            if score > best_score:
                best_score = score
                best_idx = cursor + idx
        if best_idx is not None and best_score >= threshold:
            node["_start_index"] = best_idx
            cursor = best_idx + 1
        nodes.append(node)

    for i, node in enumerate(nodes):
        if node["_start_index"] is None:
            continue
        start_idx = node["_start_index"]
        end_idx = len(flat_blocks)
        for j in range(i + 1, len(nodes)):
            if nodes[j]["_start_index"] is not None:
                end_idx = nodes[j]["_start_index"]
                break
        content_blocks = flat_blocks[start_idx + 1 : end_idx]
        for block in content_blocks:
            text = (block.get("text") or "").strip()
            page_id = block.get("_page_idx")
            if text:
                node["raw_text"].append(text)
                node["content_refs"]["text_blocks"].append(
                    {"id": block.get("id"), "text": text, "page_id": page_id}
                )
            if block.get("type") in ["IMAGE", "FIGURE"]:
                node["content_refs"]["images"].append(
                    {"id": block.get("id"), "path": block.get("image_path"), "page_id": page_id}
                )
            if block.get("type") in ["TABLE"]:
                node["content_refs"]["tables"].append(
                    {
                        "id": block.get("id"),
                        "html": block.get("html"),
                        "image_path": block.get("image_path"),
                        "page_id": page_id,
                    }
                )
        del node["_start_index"]

    return {"nodes": _build_tree(nodes)}


def _build_tree(flat_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stack: List[Dict[str, Any]] = []
    roots: List[Dict[str, Any]] = []
    for node in flat_nodes:
        level = int(node.get("level", 1))
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        if stack:
            stack[-1]["children"].append(node)
        else:
            roots.append(node)
        stack.append(node)
    return roots

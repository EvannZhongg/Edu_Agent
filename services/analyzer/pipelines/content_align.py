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


def _extract_text_from_block(block: Dict[str, Any]) -> str:
    text = block.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    lines = block.get("lines") or []
    parts: List[str] = []
    for line in lines:
        for span in line.get("spans", []):
            parts.append(span.get("content", ""))
    return "".join(parts).strip()


def _flatten_blocks(middle_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    for page in middle_json.get("pdf_info", []):
        page_idx = page.get("page_id", page.get("page_idx", 0))
        for block in page.get("para_blocks", []):
            block = dict(block)
            block["_page"] = page_idx
            block["_text"] = _extract_text_from_block(block)
            flat.append(block)
    return flat


def _normalize_type(value: Any) -> str:
    if value is None:
        return ""
    return str(value).upper()


def fill_tree_content(
    tree: Dict[str, Any],
    middle_json: Dict[str, Any],
    threshold: float = 0.8,
    window: int = 1000,
) -> Dict[str, Any]:
    flat_blocks = _flatten_blocks(middle_json)

    def locate_anchors(nodes: List[Dict[str, Any]], start_idx: int) -> int:
        cursor = start_idx
        for node in nodes:
            title = (node.get("title") or "").strip()
            match_idx = None
            best_score = 0.0
            search_window = flat_blocks[cursor : cursor + window]
            for i, block in enumerate(search_window):
                btype = _normalize_type(block.get("type"))
                if btype not in {"TITLE", "TEXT", "PARA", "PARAGRAPH", "TITLE_BLOCK"}:
                    continue
                score = _similarity(title, block.get("_text", ""))
                if score > best_score:
                    best_score = score
                    match_idx = cursor + i
                if best_score >= threshold:
                    break
            if match_idx is not None and best_score >= threshold:
                node["_start_index"] = match_idx
                cursor = match_idx + 1
            else:
                node["_start_index"] = None
            if node.get("children"):
                child_start = node["_start_index"] if node["_start_index"] is not None else cursor
                cursor = max(cursor, locate_anchors(node["children"], child_start))
        return cursor

    def slice_content(nodes: List[Dict[str, Any]], end_limit: int) -> None:
        for i, node in enumerate(nodes):
            start_idx = node.get("_start_index")
            if start_idx is None:
                continue

            next_start = end_limit
            if i + 1 < len(nodes) and nodes[i + 1].get("_start_index") is not None:
                next_start = nodes[i + 1]["_start_index"]

            actual_end = next_start
            if node.get("children"):
                first_child_start = next_start
                for child in node["children"]:
                    if child.get("_start_index") is not None:
                        first_child_start = child["_start_index"]
                        break
                slice_content(node["children"], next_start)
                actual_end = first_child_start

            content_blocks = flat_blocks[start_idx:actual_end]

            node.setdefault("content_refs", {"text_blocks": [], "images": [], "tables": []})
            node["raw_text"] = []
            for block in content_blocks:
                btype = _normalize_type(block.get("type"))
                page_id = block.get("_page")
                if btype in {"TEXT", "PARA", "PARAGRAPH"}:
                    text = block.get("_text", "")
                    if text:
                        node["raw_text"].append(text)
                        node["content_refs"]["text_blocks"].append(
                            {"id": block.get("id"), "text": text, "page_id": page_id}
                        )
                elif btype in {"IMAGE", "FIGURE"}:
                    node["content_refs"]["images"].append(
                        {"id": block.get("id"), "path": block.get("image_path"), "page_id": page_id}
                    )
                elif btype == "TABLE":
                    node["content_refs"]["tables"].append(
                        {
                            "id": block.get("id"),
                            "html": block.get("html"),
                            "image_path": block.get("image_path"),
                            "page_id": page_id,
                        }
                    )

            node["status"] = "filled"

    locate_anchors(tree.get("nodes", []), 0)
    slice_content(tree.get("nodes", []), len(flat_blocks))
    return tree

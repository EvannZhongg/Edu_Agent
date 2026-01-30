from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .llm_client import extract_toc_from_images, extract_toc_from_text, align_toc_llm
from .pdf_images import load_pdf_images


TOC_KEYWORDS = ["目录", "contents", "table of contents"]


def _page_text_score(page: Dict[str, Any]) -> int:
    score = 0
    text = " ".join([b.get("text", "") for b in page.get("para_blocks", [])])
    for kw in TOC_KEYWORDS:
        if kw.lower() in text.lower():
            score += 5
    score += len(re.findall(r"\.{3,}", text))
    return score


def select_toc_pages(middle_json: Dict[str, Any], max_pages: int) -> List[int]:
    pages = middle_json.get("pdf_info", [])
    scored = [(i, _page_text_score(p)) for i, p in enumerate(pages)]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [idx for idx, score in scored if score > 0][:max_pages]
    if not top:
        return list(range(min(max_pages, len(pages))))
    return top


def collect_page_text(middle_json: Dict[str, Any], page_ids: List[int]) -> str:
    lines: List[str] = []
    for idx in page_ids:
        if idx < 0 or idx >= len(middle_json.get("pdf_info", [])):
            continue
        page = middle_json["pdf_info"][idx]
        for block in page.get("para_blocks", []):
            text = (block.get("text") or "").strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def collect_page_images(output_dir: Path, page_ids: List[int]) -> List[str]:
    candidates = list(output_dir.glob("**/*.*"))
    images = [p for p in candidates if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    if not images:
        return []
    selected: List[str] = []
    for page_id in page_ids:
        for img in images:
            if str(page_id) in img.name:
                selected.append(str(img))
                break
    if not selected:
        selected = [str(p) for p in images[: min(len(images), len(page_ids))]]
    return selected


def build_toc(middle_json: Dict[str, Any], output_dir: Path, config: Dict[str, Any], pdf_path: str | None = None) -> Tuple[List[Dict[str, Any]], str]:
    toc_cfg = config.get("toc", {})
    if not toc_cfg.get("enable", True):
        return [], "disabled"

    page_ids = select_toc_pages(middle_json, toc_cfg.get("max_pages", 20))
    images = collect_page_images(output_dir, page_ids) if toc_cfg.get("use_vlm", True) else []
    if images:
        return extract_toc_from_images(images, config), "vlm"

    if toc_cfg.get("use_vlm", True) and pdf_path:
        try:
            images_b64 = load_pdf_images(
                pdf_path,
                toc_cfg.get("scan_k_pages", 5),
                toc_cfg.get("pdf_dpi", 150),
                toc_cfg.get("poppler_path"),
            )
            if images_b64:
                data_urls = [f"data:image/jpeg;base64,{b64}" for b64 in images_b64]
                return extract_toc_from_images(data_urls, config), "vlm_pdf"
        except Exception:
            pass

    if toc_cfg.get("use_text_fallback", True):
        text = collect_page_text(middle_json, page_ids)
        return extract_toc_from_text(text, config), "text"

    return [], "none"


def _flatten_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for node in nodes:
        result.append(node)
        if node.get("children"):
            result.extend(_flatten_tree(node["children"]))
    return result


def align_titles(tree: Dict[str, Any], toc_items: List[Dict[str, Any]], min_similarity: float = 0.6) -> Dict[str, Any]:
    from difflib import SequenceMatcher

    nodes = _flatten_tree(tree.get("nodes", []))
    for toc_item in toc_items:
        title = toc_item.get("title")
        level = toc_item.get("level", 1)
        if not title:
            continue
        candidates = [n for n in nodes if n.get("level") == level]
        best = None
        best_score = 0.0
        for n in candidates:
            score = SequenceMatcher(None, n.get("title", ""), title).ratio()
            if score > best_score:
                best_score = score
                best = n
        if best and best_score >= min_similarity:
            best["title"] = title
    return tree


def align_titles_with_llm(tree: Dict[str, Any], toc_items: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
    nodes = _flatten_tree(tree.get("nodes", []))
    lite_nodes = [{"node_id": n.get("node_id"), "title": n.get("title"), "level": n.get("level")} for n in nodes]
    mappings = align_toc_llm(lite_nodes, toc_items, config)
    mapping_dict = {m.get("node_id"): m.get("new_title") for m in mappings}
    for node in nodes:
        new_title = mapping_dict.get(node.get("node_id"))
        if new_title:
            node["title"] = new_title
    return tree

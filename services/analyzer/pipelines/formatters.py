from __future__ import annotations

from typing import Any, Dict, List


def _node_to_markdown(node: Dict[str, Any], level: int, lines: List[str]) -> None:
    title = node.get("title") or "未命名章节"
    prefix = "#" * max(1, min(level, 6))
    lines.append(f"{prefix} {title}")
    for child in node.get("children", []):
        _node_to_markdown(child, level + 1, lines)


def tree_to_markdown(tree: Dict[str, Any]) -> str:
    lines: List[str] = []
    for node in tree.get("nodes", []):
        _node_to_markdown(node, 1, lines)
    return "\n\n".join(lines)

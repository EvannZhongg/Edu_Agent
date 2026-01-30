from __future__ import annotations

from typing import Any, Dict, List


def segment_questions(para_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    for idx, block in enumerate(para_blocks, start=1):
        questions.append(
            {
                "question_id": f"q_{idx}",
                "block_ids": [block.get("id") or block.get("block_id")],
                "text": block.get("text") or "",
                "page_id": block.get("page_id"),
            }
        )
    return questions


def bind_questions_to_tree(questions: List[Dict[str, Any]], tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    bindings: List[Dict[str, Any]] = []
    for q in questions:
        bindings.append(
            {
                "question_id": q["question_id"],
                "target_node_id": tree.get("nodes", [{}])[0].get("node_id") if tree.get("nodes") else None,
                "confidence": 0.0,
                "reasoning": "placeholder",
            }
        )
    return bindings

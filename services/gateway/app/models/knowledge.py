from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel


class ContentRefs(BaseModel):
    text_blocks: List[str] = []
    images: List[str] = []
    tables: List[dict] = []


class KnowledgeNode(BaseModel):
    node_id: str
    title: str
    level: int
    page_range: List[int]
    status: str = "pending"
    content_refs: ContentRefs = ContentRefs()
    analysis: Optional[Any] = None


class KnowledgeTree(BaseModel):
    doc_id: str
    nodes: List[KnowledgeNode]

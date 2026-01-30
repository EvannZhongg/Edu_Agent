from __future__ import annotations

import base64
import json
from typing import Any, Dict, List

import os
from pathlib import Path

import requests
import time


def _post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int = 60, retries: int = 1, backoff_s: int = 2) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(backoff_s * attempt)
            continue
    raise last_error if last_error else RuntimeError("request failed")


def _chat_complete(base_url: str, api_key: str, model: str, messages: List[Dict[str, Any]], temperature: float = 0.2, timeout: int = 60, retries: int = 1, backoff_s: int = 2) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    data = _post_json(url, api_key, payload, timeout=timeout, retries=retries, backoff_s=backoff_s)
    return data["choices"][0]["message"]["content"]


def _safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    return {}


def _load_prompt(config: Dict[str, Any], key: str, fallback: str) -> str:
    prompts = config.get("prompts", {})
    path = prompts.get(key)
    if path and os.path.exists(path):
        return Path(path).read_text(encoding="utf-8")
    return fallback


def extract_knowledge(text: str, config: Dict[str, Any], node_type: str | None = None, title: str | None = None) -> dict:
    llm_cfg = config["models"]["llm"]
    max_chars = int(llm_cfg.get("max_chars", 3000))
    prompt_key = "knowledge"
    if node_type == "expansion":
        prompt_key = "knowledge_expansion"
    elif node_type == "meta":
        prompt_key = "knowledge_meta"
    system_prompt = _load_prompt(config, prompt_key, "请从文本中提取知识点，输出 JSON。")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"章节标题：{title or ''}\n\n{text[:max_chars]}"},
    ]
    content = _chat_complete(
        llm_cfg["base_url"],
        llm_cfg["api_key"],
        llm_cfg["model_name"],
        messages,
        timeout=int(llm_cfg.get("request_timeout_s", 120)),
        retries=int(llm_cfg.get("max_retries", 3)),
        backoff_s=int(llm_cfg.get("retry_backoff_s", 5)),
    )
    payload = _safe_json(content)
    return {
        "knowledge_points": payload.get("knowledge_points", []),
        "formulas": payload.get("formulas", []),
        "definitions": payload.get("definitions", []),
        "raw_length": len(text),
    }


def extract_toc_from_text(text: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    llm_cfg = config["models"]["llm"]
    system_prompt = _load_prompt(
        config,
        "toc_text",
        "抽取目录，输出 JSON items。",
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text[:16000]},
    ]
    content = _chat_complete(
        llm_cfg["base_url"],
        llm_cfg["api_key"],
        llm_cfg["model_name"],
        messages,
        timeout=int(llm_cfg.get("request_timeout_s", 120)),
        retries=int(llm_cfg.get("max_retries", 3)),
        backoff_s=int(llm_cfg.get("retry_backoff_s", 5)),
    )
    payload = _safe_json(content)
    return payload.get("items", [])


def extract_toc_from_images(image_paths: List[str], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    vlm_cfg = config["models"]["vlm"]
    system_prompt = _load_prompt(
        config,
        "toc_images",
        "从目录页图片抽取目录结构，输出 JSON items。",
    )
    parts: List[Dict[str, Any]] = [{"type": "text", "text": system_prompt}]
    for item in image_paths:
        if isinstance(item, str) and item.startswith("data:image"):
            parts.append({"type": "image_url", "image_url": {"url": item}})
            continue
        if isinstance(item, str) and item.strip() and not item.startswith("data:"):
            with open(item, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    messages = [{"role": "user", "content": parts}]
    content = _chat_complete(
        vlm_cfg["base_url"],
        vlm_cfg["api_key"],
        vlm_cfg["model_name"],
        messages,
        timeout=int(config.get("models", {}).get("llm", {}).get("request_timeout_s", 120)),
        retries=int(config.get("models", {}).get("llm", {}).get("max_retries", 3)),
        backoff_s=int(config.get("models", {}).get("llm", {}).get("retry_backoff_s", 5)),
    )
    payload = _safe_json(content)
    if isinstance(payload, list):
        return payload
    return payload.get("items", [])


def extract_toc_from_image_page(image_data_url: str, config: Dict[str, Any]) -> Dict[str, Any]:
    vlm_cfg = config["models"]["vlm"]
    system_prompt = _load_prompt(
        config,
        "toc_images",
        "抽取目录结构并返回 has_toc 与 items。",
    )
    parts: List[Dict[str, Any]] = [
        {"type": "text", "text": system_prompt},
        {"type": "image_url", "image_url": {"url": image_data_url}},
    ]
    messages = [{"role": "user", "content": parts}]
    content = _chat_complete(
        vlm_cfg["base_url"],
        vlm_cfg["api_key"],
        vlm_cfg["model_name"],
        messages,
        timeout=int(config.get("models", {}).get("llm", {}).get("request_timeout_s", 120)),
        retries=int(config.get("models", {}).get("llm", {}).get("max_retries", 3)),
        backoff_s=int(config.get("models", {}).get("llm", {}).get("retry_backoff_s", 5)),
    )
    payload = _safe_json(content)
    if isinstance(payload, list):
        return {"has_toc": True if payload else False, "items": payload}
    return {"has_toc": bool(payload.get("has_toc")), "items": payload.get("items", [])}


def align_toc_llm(nodes: List[Dict[str, Any]], toc_items: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    llm_cfg = config["models"]["llm"]
    system_prompt = _load_prompt(
        config,
        "toc_align",
        "对齐目录与节点标题，输出 JSON mappings。",
    )
    payload = json.dumps({"nodes": nodes, "toc": toc_items}, ensure_ascii=False)[:16000]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload},
    ]
    content = _chat_complete(
        llm_cfg["base_url"],
        llm_cfg["api_key"],
        llm_cfg["model_name"],
        messages,
        timeout=int(llm_cfg.get("request_timeout_s", 120)),
        retries=int(llm_cfg.get("max_retries", 3)),
        backoff_s=int(llm_cfg.get("retry_backoff_s", 5)),
    )
    data = _safe_json(content)
    return data.get("mappings", [])


def segment_questions_llm(blocks: List[Dict[str, Any]], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    llm_cfg = config["models"]["llm"]
    system_prompt = _load_prompt(
        config,
        "question_segment",
        "根据题号与位置切题，输出 JSON questions。",
    )
    payload = json.dumps(blocks, ensure_ascii=False)[:16000]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload},
    ]
    content = _chat_complete(
        llm_cfg["base_url"],
        llm_cfg["api_key"],
        llm_cfg["model_name"],
        messages,
        timeout=int(llm_cfg.get("request_timeout_s", 120)),
        retries=int(llm_cfg.get("max_retries", 3)),
        backoff_s=int(llm_cfg.get("retry_backoff_s", 5)),
    )
    data = _safe_json(content)
    return data.get("questions", [])


def bind_questions_llm(questions: List[Dict[str, Any]], tree: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    llm_cfg = config["models"]["llm"]
    system_prompt = _load_prompt(
        config,
        "question_bind",
        "为题目选择章节节点，输出 JSON bindings。",
    )
    payload = json.dumps({"questions": questions, "tree": tree}, ensure_ascii=False)[:16000]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload},
    ]
    content = _chat_complete(
        llm_cfg["base_url"],
        llm_cfg["api_key"],
        llm_cfg["model_name"],
        messages,
        timeout=int(llm_cfg.get("request_timeout_s", 120)),
        retries=int(llm_cfg.get("max_retries", 3)),
        backoff_s=int(llm_cfg.get("retry_backoff_s", 5)),
    )
    data = _safe_json(content)
    return data.get("bindings", [])


def embed_texts(texts: List[str], config: Dict[str, Any]) -> List[List[float]]:
    embed_cfg = config["models"]["embedding"]
    url = embed_cfg["base_url"].rstrip("/") + "/embeddings"
    max_batch = int(embed_cfg.get("max_batch_size", 64))
    max_chars = int(embed_cfg.get("max_chars", 2000))

    cleaned = []
    for t in texts:
        if not t:
            continue
        t = t.strip()
        if not t:
            continue
        cleaned.append(t[:max_chars])

    vectors: List[List[float]] = []
    for i in range(0, len(cleaned), max_batch):
        batch = cleaned[i : i + max_batch]
        payload = {"model": embed_cfg["model_name"], "input": batch}
        data = _post_json(
            url,
            embed_cfg["api_key"],
            payload,
            timeout=int(config.get("models", {}).get("llm", {}).get("request_timeout_s", 120)),
            retries=int(config.get("models", {}).get("llm", {}).get("max_retries", 3)),
            backoff_s=int(config.get("models", {}).get("llm", {}).get("retry_backoff_s", 5)),
        )
        vectors.extend([item["embedding"] for item in data.get("data", [])])

    return vectors

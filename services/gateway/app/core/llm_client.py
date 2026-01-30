from __future__ import annotations

import json
from typing import Any, Dict, List

import requests


def _post_json(url: str, api_key: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def chat_complete(base_url: str, api_key: str, model: str, messages: List[Dict[str, Any]]) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    data = _post_json(url, api_key, payload)
    return data["choices"][0]["message"]["content"]


def embed_texts(base_url: str, api_key: str, model: str, texts: List[str]) -> List[List[float]]:
    url = base_url.rstrip("/") + "/embeddings"
    payload = {"model": model, "input": texts}
    data = _post_json(url, api_key, payload)
    return [item["embedding"] for item in data.get("data", [])]


def safe_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
    return {}

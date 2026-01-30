from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import List

from pdf2image import convert_from_path


def encode_image_base64(image_obj) -> str:
    buffered = io.BytesIO()
    image_obj.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def _resolve_poppler_path(poppler_path: str | None) -> str | None:
    if not poppler_path:
        return None
    p = Path(poppler_path)
    if p.is_absolute():
        return str(p)
    config_path = Path(os.getenv("CONFIG_PATH", "config/config.yaml")).resolve()
    base_dir = config_path.parent.parent
    return str((base_dir / p).resolve())


def load_pdf_images(pdf_path: str, k: int, dpi: int, poppler_path: str | None = None) -> List[str]:
    return load_pdf_images_range(pdf_path, 1, k, dpi, poppler_path)


def load_pdf_images_range(
    pdf_path: str,
    first_page: int,
    last_page: int,
    dpi: int,
    poppler_path: str | None = None,
) -> List[str]:
    resolved = _resolve_poppler_path(poppler_path)
    images = convert_from_path(
        pdf_path,
        first_page=first_page,
        last_page=last_page,
        dpi=dpi,
        poppler_path=resolved,
    )
    return [encode_image_base64(img) for img in images]

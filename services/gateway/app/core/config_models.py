from __future__ import annotations

from pydantic import BaseModel, Field


class StorageConfig(BaseModel):
    base_path: str = Field(default="./data/shared")
    lancedb_path: str = Field(default="./data/lancedb")
    sqlite_path: str = Field(default="./data/sqlite/app.db")


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]


class LLMConfig(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model_name: str
    context_window: int | None = None


class VLMConfig(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model_name: str


class EmbeddingConfig(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model_name: str
    dimension: int


class ModelsConfig(BaseModel):
    llm: LLMConfig
    vlm: VLMConfig
    embedding: EmbeddingConfig


class MinerUConfig(BaseModel):
    mode: str = "api"
    api_base_url: str = "http://localhost:8002"
    api_endpoint: str = "/file_parse"
    api_timeout_s: int = 600
    api_download_output: bool = True
    api_response_zip: bool = True
    api_params: dict = {}
    install_path: str = "F:/Model/mineru"
    cli_path: str = "F:/Model/mineru/.venv/Scripts/magic-pdf.exe"
    config_path: str = "./config/mineru_config.json"
    output_subdir: str = "mineru_output"
    command_template: str = "{cli} --input {input} --output {output} --config {config}"


class PipelineConfig(BaseModel):
    auto_analyze: bool = True
    auto_workbook_bind: bool = False
    use_llm_segmentation: bool = True
    use_llm_binding: bool = True
    llm_concurrency: int = 2


class TocConfig(BaseModel):
    enable: bool = True
    max_pages: int = 20
    use_vlm: bool = True
    use_text_fallback: bool = True
    align_mode: str = "simple"
    min_similarity: float = 0.6
    scan_k_pages: int = 5
    extend_max_pages: int = 3
    pdf_dpi: int = 150
    poppler_path: str | None = None


class RagConfig(BaseModel):
    enable: bool = True
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 6


class AppConfig(BaseModel):
    storage: StorageConfig
    gateway: GatewayConfig
    models: ModelsConfig
    mineru: MinerUConfig
    pipeline: PipelineConfig
    toc: TocConfig
    rag: RagConfig
    prompts: dict = {}

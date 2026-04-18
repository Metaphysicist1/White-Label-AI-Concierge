from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, Field


class SlotFieldConfig(BaseModel):
    name: str
    type: str
    description: str


class SlotSchemaConfig(BaseModel):
    model_name: str
    required_fields: List[SlotFieldConfig]


class LeadStorageConfig(BaseModel):
    backend: Literal["sqlite"] = "sqlite"
    sqlite_path: str


class LeadCaptureConfig(BaseModel):
    storage: LeadStorageConfig
    slot_schema: SlotSchemaConfig


class RagLanguageConfig(BaseModel):
    input: str = "mixed"
    target_retrieval: str = "de"


class RagConfig(BaseModel):
    document_path: str
    web_data_path: str = "scraper/data/knowledge.json"
    persist_directory: str
    collection_name: str
    top_k: int = 4
    languages: RagLanguageConfig = Field(default_factory=RagLanguageConfig)


class RouterConfig(BaseModel):
    intents: List[str]
    descriptions: Dict[str, str]


class PersonaConfig(BaseModel):
    system_prompt: str


class BrandConfig(BaseModel):
    name: str
    locale: str = "en-US"


class DomainConfig(BaseModel):
    brand: BrandConfig
    persona: PersonaConfig
    rag: RagConfig
    lead_capture: LeadCaptureConfig
    router: RouterConfig


@lru_cache(maxsize=1)
def load_domain_config(config_path: str = "config/domain_config.yaml") -> DomainConfig:
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    return DomainConfig.model_validate(raw)

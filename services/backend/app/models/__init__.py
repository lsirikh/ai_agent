"""
Backend Models Package

Phase 10.3: Model Catalogs for Dynamic Selection
"""
from .llm_models import LLM_MODELS, get_models_by_vram

__all__ = ["LLM_MODELS", "get_models_by_vram"]

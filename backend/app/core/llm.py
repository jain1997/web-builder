"""
Inference Abstraction Layer.

Factory that returns a cached LangChain BaseChatModel.
Each (provider, model_tier, temperature, streaming) combination is
instantiated once and reused — no new API client per node call.
"""

from __future__ import annotations

from typing import Dict, Tuple

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings

# Module-level cache: (model_tier, temperature, streaming) → model instance
_cache: Dict[Tuple, BaseChatModel] = {}


def get_llm(
    temperature: float = 0.2,
    streaming: bool = True,
    model_tier: str = "large",
) -> BaseChatModel:
    """
    Return a cached chat model instance.

    Args:
        temperature:  Sampling temperature.
        streaming:    Whether to stream tokens.
        model_tier:   "large" → configured LLM_MODEL (default gpt-4o)
                      "small" → gpt-4o-mini
    """
    cache_key = (settings.LLM_PROVIDER.lower(), model_tier, temperature, streaming)

    if cache_key in _cache:
        return _cache[cache_key]

    provider = settings.LLM_PROVIDER.lower()

    if provider == "openai":
        if model_tier == "large":
            model_name = settings.LLM_MODEL
        elif model_tier == "small":
            model_name = "gpt-5-mini-2025-08-07"
        else:
            raise ValueError(f"Unsupported model_tier: '{model_tier}'. Use 'large' or 'small'.")

        instance = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            streaming=streaming,
            api_key=settings.OPENAI_API_KEY,
        )
    # ── Future providers ────────────────────────────────────────────
    # elif provider == "ollama":
    #     from langchain_community.chat_models import ChatOllama
    #     instance = ChatOllama(model=settings.LLM_MODEL, temperature=temperature)
    else:
        raise ValueError(
            f"Unsupported LLM provider: '{provider}'. Supported: openai."
        )

    _cache[cache_key] = instance
    return instance

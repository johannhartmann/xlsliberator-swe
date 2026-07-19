"""Bounded model configuration for the public autonomous showcase."""

from __future__ import annotations

from typing import Final

from deepagents import SystemPromptConfig
from langchain_core.language_models import ModelProfile

from ..utils.model import ModelKwargs

SHOWCASE_CONTEXT_WINDOW_TOKENS: Final[int] = 8_000
SHOWCASE_MAX_OUTPUT_TOKENS: Final[int] = 768
SHOWCASE_MAX_INPUT_TOKENS: Final[int] = SHOWCASE_CONTEXT_WINDOW_TOKENS - SHOWCASE_MAX_OUTPUT_TOKENS


def showcase_model_profile() -> ModelProfile:
    """Describe the constrained GitHub Models endpoint used by the showcase."""

    return {
        "max_input_tokens": SHOWCASE_MAX_INPUT_TOKENS,
        "max_output_tokens": SHOWCASE_MAX_OUTPUT_TOKENS,
        "text_inputs": True,
        "text_outputs": True,
        "tool_calling": True,
        "structured_output": True,
    }


def bound_showcase_model_kwargs(kwargs: ModelKwargs) -> ModelKwargs:
    """Apply the endpoint's joint input and output budget."""

    bounded: ModelKwargs = kwargs.copy()
    bounded["max_tokens"] = SHOWCASE_MAX_OUTPUT_TOKENS
    bounded["profile"] = showcase_model_profile()
    return bounded


def showcase_system_prompt(prefix: str | None = None) -> SystemPromptConfig:
    """Drop the general coding base prompt from the bounded showcase graph."""

    prompt: SystemPromptConfig = {"base": None}
    if prefix:
        prompt["prefix"] = prefix
    return prompt

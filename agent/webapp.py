"""Compatibility entrypoint for the FastAPI application."""

from .xlsliberator.settings import apply_environment_defaults

apply_environment_defaults()

from .api.app import app  # noqa: E402

__all__ = ["app"]

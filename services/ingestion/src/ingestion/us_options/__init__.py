"""Fail-closed US options research ingestion."""

from ingestion.us_options.pipeline import import_option_sentiment

__all__ = ["import_option_sentiment"]

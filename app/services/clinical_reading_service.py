"""Backward-compatible import path; new consumers use get_reading()."""
from app.services.clinical_reading import ClinicalReadingService

__all__ = ["ClinicalReadingService"]

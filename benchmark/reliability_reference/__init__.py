"""Portable TfL reliability-reference public interface."""

from .models import RunResult
from .runner import run_case

VERSION = "0.2.0"
CONTRACT_VERSION = "1"

__all__ = ["CONTRACT_VERSION", "VERSION", "RunResult", "run_case"]

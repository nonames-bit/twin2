"""Módulo core con contratos e interfaces base."""
from src.core.contracts import CanonicalRecord, TelemetryRecord
from src.core.base_adapter import BaseAdapter

__all__ = ["CanonicalRecord", "TelemetryRecord", "BaseAdapter"]

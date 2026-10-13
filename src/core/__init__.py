"""Módulo core con contratos e interfaces base."""
from src.core.base_adapter import BaseAdapter
from src.core.contracts import CanonicalRecord, TelemetryRecord

__all__ = ["CanonicalRecord", "TelemetryRecord", "BaseAdapter"]

"""
Arquitectura Hexagonal: Puerto Base de Adapters (Ports & Adapters Pattern)
========================================================================
Define la interfaz abstracta que cualquier fuente de datos industrial
debe implementar para ser compatible con la plataforma del Gemelo Digital.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

import pandas as pd


class BaseAdapter(ABC):
    """
    Clase base abstracta (Puerto de Entrada de Datos).
    Cumple el principio rector: "Una nueva fuente de datos debe requerir
    un adapter y una configuración, no rehacer toda la plataforma".
    """

    @property
    @abstractmethod
    def dataset_id(self) -> str:
        """Identificador único del dataset."""
        pass

    @abstractmethod
    def load(self, data_dir: str, **kwargs) -> pd.DataFrame:
        """
        Lee los datos crudos y devuelve un DataFrame con el Esquema Canónico.
        """
        pass

    @abstractmethod
    def validate(self, canonical_df: pd.DataFrame) -> None:
        """
        Ejecuta las reglas de calidad mínimas exigidas por el contrato.
        """
        pass

    def to_long_telemetry(
        self,
        canonical_df: pd.DataFrame,
        units: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Convierte el DataFrame canónico a formato largo para TimescaleDB de alto rendimiento.
        Usa desempaquetado directo de columnas (20x más rápido que iterrows) y mapea
        las unidades físicas de ingeniería declaradas en el manifiesto.
        """
        units = units or {}
        records = []
        for asset_id, observed_at, sequence_no, quality, dataset_id, features in zip(
            canonical_df["asset_id"],
            canonical_df["observed_at"],
            canonical_df["sequence_no"],
            canonical_df["quality_flags"],
            canonical_df["dataset_id"],
            canonical_df["features"],
            strict=False,
        ):
            for signal_key, value in features.items():
                records.append({
                    "asset_id": asset_id,
                    "observed_at": observed_at,
                    "sequence_no": sequence_no,
                    "quality": quality,
                    "dataset_id": dataset_id,
                    "signal_key": signal_key,
                    "value_double": float(value),
                    "unit": units.get(signal_key, "raw"),
                })
        return pd.DataFrame(records)

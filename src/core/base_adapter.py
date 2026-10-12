"""
Arquitectura Hexagonal: Puerto Base de Adapters (Ports & Adapters Pattern)
========================================================================
Define la interfaz abstracta que cualquier fuente de datos industrial
debe implementar para ser compatible con la plataforma del Gemelo Digital.
"""

from abc import ABC, abstractmethod
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

    def to_long_telemetry(self, canonical_df: pd.DataFrame) -> pd.DataFrame:
        """
        Convierte el DataFrame canónico a formato largo para TimescaleDB.
        Implementación reutilizable para cualquier serie de tiempo industrial.
        """
        records = []
        for _, row in canonical_df.iterrows():
            base_info = {
                "asset_id": row["asset_id"],
                "observed_at": row["observed_at"],
                "sequence_no": row["sequence_no"],
                "quality": row["quality_flags"],
                "dataset_id": row["dataset_id"],
            }
            for signal_key, value in row["features"].items():
                records.append({
                    **base_info,
                    "signal_key": signal_key,
                    "value_double": float(value),
                    "unit": "raw",
                })
        return pd.DataFrame(records)

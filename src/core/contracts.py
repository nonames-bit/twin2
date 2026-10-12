"""
Módulo de Contratos y Esquemas de Dominio (Domain Contracts)
============================================================
Define las estructuras formales y tipadas de datos mediante Pydantic.
Garantiza que cualquier dato que viaje por la plataforma cumpla
estrictamente el contrato canónico y las reglas de idempotencia.
"""

from datetime import datetime
from typing import Dict, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class CanonicalRecord(BaseModel):
    """
    Contrato Canónico Unificado (Capa A -> Capa B).
    Representa una observación normalizada de un activo industrial.
    """
    asset_id: str = Field(
        ...,
        description="Identificador único y estable del equipo físico (ej: 'cmapss_1')"
    )
    sequence_no: int = Field(
        ...,
        ge=1,
        description="Número de ciclo operacional o paso temporal (estrictamente >= 1)"
    )
    observed_at: datetime = Field(
        ...,
        description="Marca temporal (timestamp) de la observación"
    )
    dataset_id: str = Field(
        ...,
        description="Identificador del dataset fuente (ej: 'cmapss_fd001')"
    )
    modality: Literal["timeseries", "image"] = Field(
        default="timeseries",
        description="Modalidad de los datos: serie temporal o imagen de inspección"
    )
    media_ref: Optional[str] = Field(
        default=None,
        description="URI del archivo multimedia en S3/MinIO (None para series de sensores)"
    )
    features: Dict[str, float] = Field(
        ...,
        description="Diccionario de lecturas de sensores normalizadas por clave y valor"
    )
    target: Optional[float] = Field(
        default=None,
        description="Etiqueta objetivo (RUL con tope, modo de falla o anomalía)"
    )
    split_hint: Literal["train", "test", "val"] = Field(
        default="train",
        description="Indicio de partición original del dataset"
    )
    quality_flags: str = Field(
        default="OK",
        description="Indicador de calidad de datos ('OK' o motivo de advertencia)"
    )

    @field_validator("features")
    @classmethod
    def validate_features_not_empty(cls, v: Dict[str, float]) -> Dict[str, float]:
        if not v:
            raise ValueError("El diccionario de features no puede estar vacío.")
        return v


class TelemetryRecord(BaseModel):
    """
    Contrato Operacional de Telemetría en Formato Largo (Capa B -> TimescaleDB).
    Estructura para la hypertable de series temporales en base de datos.
    """
    asset_id: str
    observed_at: datetime
    sequence_no: int
    signal_key: str
    value_double: float
    unit: str = "raw"
    quality: str = "OK"
    dataset_id: str

    @property
    def natural_key(self) -> str:
        """
        Clave natural de idempotencia según la arquitectura (pág. 13 del PDF):
        dataset_id + asset_id + sequence_no + signal_key.
        Garantiza que reenviar un mensaje no cree duplicados en base de datos.
        """
        return f"{self.dataset_id}::{self.asset_id}::{self.sequence_no}::{self.signal_key}"

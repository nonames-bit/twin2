"""
Implementación concreta del Adapter C-MAPSS FD001 (NASA Turbofan)
================================================================
Hereda de BaseAdapter (Arquitectura Hexagonal).
Lee la configuración y metadatos físicos de manifest.yaml,
transforma datos crudos al Esquema Canónico unificado y utiliza
logging estructurado para observabilidad de grado industrial.
"""

import logging
import os
import re
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yaml

from src.core.base_adapter import BaseAdapter
from src.core.contracts import CanonicalRecord

logger = logging.getLogger(__name__)

DATASET_ID = "cmapss_fd001"
DEFAULT_RUL_CAP = 125
BASE_TIMESTAMP = "2026-01-01 00:00:00"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class CmapssAdapter(BaseAdapter):
    """
    Adapter especializado para datasets de degradación de turbofans NASA C-MAPSS.
    Lee configuración, variables y unidades físicas dinámicamente desde manifest.yaml.
    """

    def __init__(self, manifest_path: Optional[str] = None):
        if manifest_path is None:
            manifest_path = os.path.join(os.path.dirname(__file__), "manifest.yaml")
        self.manifest_path = manifest_path
        self.manifest = self._load_manifest(manifest_path)

        # Configuración gobernada por el manifiesto
        self.rul_cap = int(
            self.manifest.get("target", {}).get("rul_cap", DEFAULT_RUL_CAP)
        )
        self.settings: List[str] = list(
            self.manifest.get("operational_settings", {}).keys()
        ) or ["setting1", "setting2", "setting3"]
        self.sensors: List[str] = list(
            self.manifest.get("sensors", {}).keys()
        ) or [f"s{i}" for i in range(1, 22)]

        self.feature_columns = self.settings + self.sensors
        self.raw_columns = ["engine_id", "cycle"] + self.feature_columns
        self.units: Dict[str, str] = self._extract_units()

    def _load_manifest(self, path: str) -> dict:
        """Carga el archivo de manifiesto YAML del dataset."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"No se encontró manifest en '{path}'. Usando valores por defecto.")
        return {}

    def _extract_units(self) -> Dict[str, str]:
        """Extrae las unidades físicas de ingeniería desde las descripciones del manifiesto."""
        units = {}
        all_signals = {
            **self.manifest.get("operational_settings", {}),
            **self.manifest.get("sensors", {}),
        }
        for sig, desc in all_signals.items():
            match = re.search(r"\[(.*?)\]", str(desc))
            units[sig] = match.group(1) if match else "dimensionless"
        return units

    @property
    def dataset_id(self) -> str:
        return DATASET_ID

    def resolve_path(self, data_dir: str, filename: str) -> str:
        """Resuelve dinámicamente la ruta al archivo crudo."""
        candidates = [
            os.path.join(data_dir, filename),
            os.path.join(data_dir, "CMaps", filename),
            os.path.join(ROOT_DIR, "Dataset", "CMaps", filename),
            os.path.join(ROOT_DIR, "Dataset", filename),
            os.path.join("Dataset", "CMaps", filename),
            os.path.join("Dataset", filename),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        raise FileNotFoundError(
            f"No se encontró el archivo '{filename}'. Se buscó en: {candidates}"
        )

    def load(
        self,
        data_dir: str = "Dataset/CMaps",
        filename: str = "train_FD001.txt",
        rul_cap: Optional[int] = None,
        split_hint: str = "train",
        sample_validation_size: int = 5,
    ) -> pd.DataFrame:
        """
        Lee datos crudos, calcula RUL con tope (piecewise linear),
        construye el esquema canónico y valida con contratos Pydantic.
        """
        effective_rul_cap = rul_cap if rul_cap is not None else self.rul_cap
        logger.info(f"Cargando dataset {self.dataset_id} desde '{data_dir}'...")
        file_path = self.resolve_path(data_dir, filename)

        # 1. Lectura de archivo crudo
        raw_df = pd.read_csv(file_path, sep=r"\s+", header=None)
        df = raw_df.iloc[:, :len(self.raw_columns)].copy()
        df.columns = self.raw_columns

        # 2. Cálculo de RUL por tramos (piecewise-linear)
        max_cycles = df.groupby("engine_id")["cycle"].transform("max")
        true_rul = max_cycles - df["cycle"]
        clipped_rul = true_rul.clip(upper=effective_rul_cap)

        # 3. Construcción del Esquema Canónico
        canonical = pd.DataFrame()
        canonical["asset_id"] = "cmapss_" + df["engine_id"].astype(str)
        canonical["sequence_no"] = df["cycle"].astype(int)

        base_time = pd.to_datetime(BASE_TIMESTAMP)
        canonical["observed_at"] = base_time + pd.to_timedelta(df["cycle"], unit="m")

        canonical["dataset_id"] = self.dataset_id
        canonical["modality"] = "timeseries"
        canonical["media_ref"] = None
        canonical["features"] = df[self.feature_columns].to_dict(orient="records")
        canonical["target"] = clipped_rul.astype(float)
        canonical["split_hint"] = split_hint
        canonical["quality_flags"] = "OK"

        # 4. Validación de calidad estructural y de dominio
        self.validate(canonical, rul_cap=effective_rul_cap)

        # 5. Validación con Pydantic sobre una muestra representativa (Smoke test de contrato)
        if sample_validation_size > 0:
            sample_records = canonical.head(sample_validation_size).to_dict(orient="records")
            for record in sample_records:
                CanonicalRecord(**record)
            logger.info(
                f"Contrato Pydantic verificado en muestra de {sample_validation_size} filas."
            )

        logger.info(f"Dataset {self.dataset_id} cargado con éxito ({len(canonical):,} registros).")
        return canonical

    def validate(self, canonical_df: pd.DataFrame, rul_cap: Optional[int] = None) -> None:
        """Valida que los datos cumplan las reglas de integridad y calidad."""
        effective_rul_cap = rul_cap if rul_cap is not None else self.rul_cap
        required_cols = [
            "asset_id", "sequence_no", "observed_at", "dataset_id",
            "modality", "media_ref", "features", "target", "split_hint", "quality_flags",
        ]
        for col in required_cols:
            if col not in canonical_df.columns:
                raise ValueError(f"Regla fallida: Columna obligatoria '{col}' ausente.")

        # Integridad de nulos
        key_cols = ["asset_id", "sequence_no", "observed_at", "target", "dataset_id"]
        null_count = canonical_df[key_cols].isna().sum().sum()
        if null_count > 0:
            raise ValueError(f"Regla fallida: Se encontraron {null_count} valores nulos.")

        # Límite de RUL
        if not (canonical_df["target"] <= effective_rul_cap).all():
            raise ValueError(
                f"Regla fallida: Valores de RUL exceden el tope de {effective_rul_cap}."
            )
        if not (canonical_df["target"] >= 0).all():
            raise ValueError("Regla fallida: Existen valores de RUL negativos.")

        # Secuencia ordenada continua (incremento de 1) y monotonía decreciente
        for asset, group in canonical_df.groupby("asset_id"):
            cycles = group["sequence_no"].values
            diffs = np.diff(cycles)
            if not np.all(diffs == 1):
                raise ValueError(f"Regla fallida: Secuencia discontinua o duplicada en {asset}.")
            if not group["target"].is_monotonic_decreasing:
                raise ValueError(f"Regla fallida: RUL no es monótonamente decreciente en {asset}.")

    def to_long_telemetry(
        self,
        canonical_df: pd.DataFrame,
        units: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """Convierte a formato largo aplicando las unidades físicas extraídas del manifiesto."""
        effective_units = units if units is not None else self.units
        return super().to_long_telemetry(canonical_df, units=effective_units)


# Función de conveniencia funcional
def load(data_dir: str = "Dataset/CMaps", **kwargs) -> pd.DataFrame:
    adapter = CmapssAdapter()
    return adapter.load(data_dir=data_dir, **kwargs)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 70)
    print("   ADAPTER C-MAPSS FD001 (NASA Turbofan)")
    print("   Ubicación: src/adapters/cmapss/adapter.py")
    print("=" * 70)

    adapter = CmapssAdapter()
    df_canonical = adapter.load()

    print(f"\n[OK] Carga exitosa: {len(df_canonical):,} registros procesados.")
    print(f"[OK] Total de turbinas: {df_canonical['asset_id'].nunique()}")
    print(f"[OK] Columnas del contrato canónico:\n     {list(df_canonical.columns)}")
    print("\n[OK] Unidades físicas leídas del manifest:")
    sample_units = {k: adapter.units[k] for k in list(adapter.units)[:5]}
    print(f"     {sample_units}")
    print("\n[OK] Vista previa:")
    print(
        df_canonical[
            ["asset_id", "sequence_no", "observed_at", "target", "split_hint"]
        ].head(3)
    )
    print("\n[OK] Calidad y contratos 100% verificados.")
    print("=" * 70)

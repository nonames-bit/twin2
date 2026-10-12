"""
Punto de Entrada del Adapter C-MAPSS FD001 (NASA Turbofan)
==========================================================
Actúa como interfaz de conveniencia y compatibilidad hacia el
paquete modular `src.adapters.cmapss.adapter.CmapssAdapter`.
"""

import logging
import os
import sys
import pandas as pd

# Asegurar que la ruta raíz esté disponible en sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.adapters.cmapss.adapter import (
    CmapssAdapter,
    DATASET_ID,
    DEFAULT_RUL_CAP,
    RAW_COLUMNS,
    SETTINGS,
    SENSORS,
    FEATURE_COLUMNS,
)

# Instancia singleton del adapter
_adapter = CmapssAdapter()


def load(
    data_dir: str = "Dataset/CMaps",
    filename: str = "train_FD001.txt",
    rul_cap: int = DEFAULT_RUL_CAP,
    split_hint: str = "train",
) -> pd.DataFrame:
    """Función de conveniencia para cargar el dataset."""
    return _adapter.load(
        data_dir=data_dir,
        filename=filename,
        rul_cap=rul_cap,
        split_hint=split_hint,
    )


def validate_canonical(df: pd.DataFrame, rul_cap: int = DEFAULT_RUL_CAP) -> None:
    """Función de conveniencia para validar el esquema canónico."""
    _adapter.validate(df, rul_cap=rul_cap)


def to_long_telemetry(canonical_df: pd.DataFrame) -> pd.DataFrame:
    """Función de conveniencia para convertir a formato largo (TimescaleDB)."""
    return _adapter.to_long_telemetry(canonical_df)


if __name__ == "__main__":
    # Configurar logging legible para consola
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 70)
    print("   PRUEBA DEL ADAPTER C-MAPSS FD001 (Fase 1 - Gemelo Digital)")
    print("   Arquitectura: Hexagonal (Ports & Adapters) + Contratos Pydantic")
    print("=" * 70)

    data_dir = os.path.join(BASE_DIR, "Dataset", "CMaps")
    df_canonical = load(data_dir=data_dir)

    print(f"\n[OK] Carga exitosa: {len(df_canonical):,} registros procesados.")
    print(f"[OK] Total de motores (activos) únicos: {df_canonical['asset_id'].nunique()}")
    print(f"[OK] Columnas generadas:\n     {list(df_canonical.columns)}")
    print(f"\n[OK] Vista previa de las primeras 3 filas:")
    print(df_canonical[["asset_id", "sequence_no", "observed_at", "target", "split_hint"]].head(3))
    print("\n[OK] Todas las reglas de calidad pasaron satisfactoriamente.")
    print("=" * 70)
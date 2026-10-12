"""
Pruebas automatizadas (Unit Tests) para el Adapter C-MAPSS FD001
================================================================
Valida los criterios de salida de la Fase 1 según la Propuesta v0.3:
1. Esquema canónico completo y nombres de columnas estandarizados.
2. Ausencia de valores nulos.
3. RUL con tope máximo de 125 (piecewise-linear).
4. RUL decreciente monotónicamente por motor.
5. Secuencia de ciclos estrictamente creciente sin duplicados.
6. Cobertura de activos esperada (100 motores en FD001).
"""

import os
import pytest
import pandas as pd
import numpy as np
from adapter import load, DEFAULT_RUL_CAP, DATASET_ID


@pytest.fixture(scope="module")
def canonical_data():
    """Fixture que carga los datos canónicos una sola vez para todos los tests."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "Dataset", "CMaps")
    return load(data_dir=data_dir)


def test_schema_columns(canonical_data):
    """Verifica que todas las columnas del contrato canónico estén presentes."""
    expected_cols = [
        "asset_id",
        "sequence_no",
        "observed_at",
        "dataset_id",
        "modality",
        "media_ref",
        "features",
        "target",
        "split_hint",
        "quality_flags",
    ]
    assert list(canonical_data.columns) == expected_cols


def test_no_null_values(canonical_data):
    """Verifica ausencia total de valores nulos en columnas obligatorias."""
    key_columns = ["asset_id", "sequence_no", "observed_at", "dataset_id", "target"]
    assert canonical_data[key_columns].isna().sum().sum() == 0


def test_rul_cap_respected(canonical_data):
    """Verifica que ningún valor de RUL supere el tope de 125 ni sea negativo."""
    assert (canonical_data["target"] <= DEFAULT_RUL_CAP).all()
    assert (canonical_data["target"] >= 0).all()


def test_rul_monotonic_decreasing(canonical_data):
    """Verifica que el RUL sea monótonamente decreciente para cada turbina."""
    for asset_id, group in canonical_data.groupby("asset_id"):
        assert group["target"].is_monotonic_decreasing, (
            f"El RUL del motor {asset_id} no decrece monotónicamente."
        )


def test_sequence_integrity(canonical_data):
    """Verifica que los ciclos de cada motor sean continuos, crecientes y sin duplicados."""
    for asset_id, group in canonical_data.groupby("asset_id"):
        cycles = group["sequence_no"].values
        diffs = np.diff(cycles)
        # Cada paso de ciclo debe incrementarse exactamente en 1
        assert np.all(diffs == 1), f"Discontinuidad en la secuencia del motor {asset_id}."


def test_dataset_cardinality(canonical_data):
    """Verifica que el dataset FD001 contenga exactamente los 100 motores de la NASA."""
    assert canonical_data["asset_id"].nunique() == 100
    assert canonical_data["dataset_id"].iloc[0] == DATASET_ID
    assert canonical_data["modality"].iloc[0] == "timeseries"

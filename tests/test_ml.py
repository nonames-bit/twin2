"""
Pruebas Unitarias para el Módulo de Machine Learning (Fase 3)
=============================================================
Valida:
1. Métricas industriales (RMSE, MAE y penalización asimétrica de la NASA).
2. Pipeline de características (rolling features y escalado sin fuga).
3. Inferencia de RUL con intervalos conformales calibrados (MAPIE).
"""

import os

import joblib
import numpy as np
import pandas as pd
import pytest

from src.ml.features import CmapssFeaturePipeline
from src.ml.metrics import compute_mae, compute_nasa_score, compute_rmse


def test_evaluation_metrics_symmetry_and_nasa_penalty():
    """
    Verifica que la función de puntuación de la NASA penalice con mayor
    severidad una predicción tardía (sobreestimar RUL -> peligro)
    que una predicción temprana (subestimar RUL -> conservador).
    """
    y_true = np.array([50.0])

    # Error tardío (predijo 60 -> pensó que le quedaban 10 ciclos más de los reales)
    y_late = np.array([60.0])
    score_late = compute_nasa_score(y_true, y_late)

    # Error temprano (predijo 40 -> pensó que le quedaban 10 ciclos menos de los reales)
    y_early = np.array([40.0])
    score_early = compute_nasa_score(y_true, y_early)

    # Ambas tienen el mismo MAE y RMSE
    assert compute_mae(y_true, y_late) == compute_mae(y_true, y_early) == 10.0
    assert compute_rmse(y_true, y_late) == compute_rmse(y_true, y_early) == 10.0

    # Pero la NASA penaliza el retraso mucho más severamente
    assert score_late > score_early


def test_feature_pipeline_rolling_and_scaling():
    """
    Verifica la correcta generación de ventanas móviles por activo y ausencia de nulos.
    """
    n_cycles = 10
    sample_data = {
        "asset_id": ["cmapss_1"] * n_cycles,
        "sequence_no": list(range(1, n_cycles + 1)),
        "target": list(range(n_cycles, 0, -1)),
    }
    for i in range(1, 22):
        sample_data[f"s{i}"] = np.linspace(100.0, 150.0, n_cycles)
    for i in range(1, 4):
        sample_data[f"setting{i}"] = [0.0] * n_cycles

    df = pd.DataFrame(sample_data)
    pipeline = CmapssFeaturePipeline(window_size=3)

    X_scaled, y, feature_names = pipeline.fit_transform(df)

    assert X_scaled.shape[0] == n_cycles
    assert len(feature_names) > 24  # Sensores + settings + rolling features
    assert not np.isnan(X_scaled).any()
    assert len(y) == n_cycles


def test_trained_model_inference():
    """
    Verifica que el modelo exportado genere predicciones e intervalos conformales válidos.
    """
    model_path = os.path.join(
        os.path.dirname(__file__), "..", "models", "cmapss_rul_model.joblib"
    )
    if not os.path.exists(model_path):
        pytest.skip("Modelo no entrenado localmente. Omitiendo prueba de inferencia.")

    artifact = joblib.load(model_path)
    model = artifact["model"]
    pipeline = artifact["pipeline"]

    dummy_input = np.zeros((1, len(pipeline.fitted_feature_names)))
    y_pred, y_pis = model.predict_interval(dummy_input)

    assert y_pred.shape == (1,)
    assert y_pis.shape == (1, 2, 1)

    lower = y_pis[0, 0, 0]
    upper = y_pis[0, 1, 0]
    assert lower <= upper

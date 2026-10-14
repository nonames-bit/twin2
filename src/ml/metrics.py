"""
Métricas de Evaluación de Modelos para Mantenimiento Predictivo (RUL)
=====================================================================
Implementa:
1. RMSE (Root Mean Squared Error)
2. MAE (Mean Absolute Error)
3. Función de Puntuación Asimétrica de la NASA (NASA Scoring Function):
   Penaliza con mayor severidad las predicciones tardías (optimistas / peligrosas)
   que las predicciones tempranas (conservadoras).

   Fórmula oficial:
   d = y_pred - y_true
   S = sum( e^(-d/13) - 1 ) para d < 0  (predicción tardía)
   S = sum( e^(d/10) - 1 )  para d >= 0 (predicción temprana)
"""

import numpy as np


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcula el Error Cuadrático Medio Raíz (RMSE)."""
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


def compute_mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Calcula el Error Absoluto Medio (MAE)."""
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def compute_nasa_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Calcula la función de puntuación asimétrica de la NASA para RUL.
    Valores menores indican un mejor rendimiento del modelo en seguridad operativa.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_pred_arr = np.asarray(y_pred, dtype=float)
    diff = y_pred_arr - y_true_arr

    # d < 0: predicción tardía (sobreestimó vida restante -> peligroso)
    late_mask = diff < 0
    # d >= 0: predicción temprana (subestimó vida restante -> conservador)
    early_mask = diff >= 0

    scores = np.zeros_like(diff)
    scores[late_mask] = np.exp(-diff[late_mask] / 13.0) - 1.0
    scores[early_mask] = np.exp(diff[early_mask] / 10.0) - 1.0

    return float(np.sum(scores))

"""
Pipeline de Entrenamiento y Calibración Conformal para RUL (NASA C-MAPSS FD001)
================================================================================
Entrena y compara:
1. Modelo Base (Linear / Ridge Regression)
2. Modelo Avanzado (XGBoost Regressor)
3. Cuantificación de Incertidumbre con Conformal Prediction (MAPIE 90% de confianza)
4. Evaluación oficial contra el conjunto de prueba de la NASA (test_FD001 + RUL_FD001)
5. Persistencia del artefacto listo para producción en 'models/cmapss_rul_model.joblib'
"""

import logging
import os
import re
from typing import Dict, Tuple

import joblib
import numpy as np
import pandas as pd
from mapie.regression import SplitConformalRegressor
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor

from src.adapters.cmapss.adapter import CmapssAdapter
from src.ml.features import CmapssFeaturePipeline
from src.ml.metrics import compute_mae, compute_nasa_score, compute_rmse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS_DIR = os.path.join(ROOT_DIR, "models")


def split_by_asset(
    df: pd.DataFrame,
    train_ratio: float = 0.8,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide los activos por turbinas completas (Group Split) para prevenir fuga de datos.
    """
    assets = sorted(
        df["asset_id"].unique(),
        key=lambda x: int(re.sub(r"\D", "", x)) if re.sub(r"\D", "", x) else 0,
    )
    n_train = int(len(assets) * train_ratio)
    train_assets = set(assets[:n_train])
    val_assets = set(assets[n_train:])

    train_df = df[df["asset_id"].isin(train_assets)].copy()
    val_df = df[df["asset_id"].isin(val_assets)].copy()

    logger.info(
        f"Group Split: {len(train_assets)} motores en train ({len(train_df)} ciclos), "
        f"{len(val_assets)} motores en val ({len(val_df)} ciclos)."
    )
    return train_df, val_df


def load_nasa_test_set(
    pipeline: CmapssFeaturePipeline,
    data_dir: str = "Dataset/CMaps",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Carga el conjunto de prueba oficial de la NASA (test_FD001.txt + RUL_FD001.txt).
    Toma el último ciclo observado de cada motor de test y su RUL real correspondiente.
    """
    test_path = os.path.join(data_dir, "test_FD001.txt")
    rul_path = os.path.join(data_dir, "RUL_FD001.txt")

    if not (os.path.exists(test_path) and os.path.exists(rul_path)):
        logger.warning(
            "Archivos de test oficial de NASA no encontrados. Omitiendo evaluación test."
        )
        return np.array([]), np.array([])

    adapter = CmapssAdapter()
    raw_df = pd.read_csv(test_path, sep=r"\s+", header=None)
    df = raw_df.iloc[:, :len(adapter.raw_columns)].copy()
    df.columns = adapter.raw_columns
    df["asset_id"] = "cmapss_test_" + df["engine_id"].astype(str)
    df["sequence_no"] = df["cycle"].astype(int)

    # RUL real al final de la secuencia de prueba
    true_ruls = pd.read_csv(rul_path, sep=r"\s+", header=None)[0].values
    true_ruls_clipped = np.clip(true_ruls, 0, adapter.rul_cap)

    # Calcular rolling features sobre las secuencias de test
    flat_test = pipeline.compute_rolling_features(df)

    # Extraer el último ciclo de cada activo ordenado numéricamente por motor
    last_rows = (
        flat_test.groupby("engine_id")
        .last()
        .reset_index()
        .sort_values("engine_id")
    )
    X_test_last = pipeline.scaler.transform(
        last_rows[pipeline.fitted_feature_names].values
    )

    return X_test_last, true_ruls_clipped


def train_and_evaluate(
    data_dir: str = "Dataset/CMaps",
    confidence_level: float = 0.90,
) -> Dict:
    """
    Ejecuta el flujo completo de entrenamiento, calibración conformal y evaluación.
    """
    logger.info("=" * 70)
    logger.info("   INICIANDO ENTRENAMIENTO DE IA: MODELO RUL CON INCERTIDUMBRE")
    logger.info("=" * 70)

    # 1. Cargar dataset canónico
    adapter = CmapssAdapter()
    df_canonical = adapter.load(data_dir=data_dir)

    # 2. División limpia por activos (sin fuga de datos)
    train_df, val_df = split_by_asset(df_canonical, train_ratio=0.8)

    # 3. Pipeline de características (ajustado exclusivamente en train)
    pipeline = CmapssFeaturePipeline(window_size=5)
    X_train, y_train, feature_names = pipeline.fit_transform(train_df)
    X_val, y_val = pipeline.transform(val_df)

    logger.info(f"Matriz de features generada con {len(feature_names)} variables.")

    # 4. Modelo Base: Ridge Regression
    logger.info("\n[1/3] Entrenando Modelo Base (Ridge Regression)...")
    baseline = Ridge(alpha=10.0)
    baseline.fit(X_train, y_train)
    y_pred_base = np.clip(baseline.predict(X_val), 0, adapter.rul_cap)

    base_rmse = compute_rmse(y_val, y_pred_base)
    base_mae = compute_mae(y_val, y_pred_base)
    base_nasa = compute_nasa_score(y_val, y_pred_base)
    logger.info(
        f"  -> Baseline Val: RMSE={base_rmse:.2f} ciclos | MAE={base_mae:.2f} | "
        f"Score NASA={base_nasa:,.1f}"
    )

    # 5. Modelo Avanzado: XGBoost Regressor
    logger.info("\n[2/3] Entrenando Modelo Avanzado (XGBoost Regressor)...")
    xgb = XGBRegressor(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
    )
    xgb.fit(X_train, y_train)
    y_pred_xgb = np.clip(xgb.predict(X_val), 0, adapter.rul_cap)

    xgb_rmse = compute_rmse(y_val, y_pred_xgb)
    xgb_mae = compute_mae(y_val, y_pred_xgb)
    xgb_nasa = compute_nasa_score(y_val, y_pred_xgb)
    logger.info(
        f"  -> XGBoost Val:  RMSE={xgb_rmse:.2f} ciclos | MAE={xgb_mae:.2f} | "
        f"Score NASA={xgb_nasa:,.1f}"
    )

    # 6. Cuantificación de Incertidumbre: Conformal Prediction (MAPIE)
    logger.info(
        f"\n[3/3] Calibrando Intervalos Conformales con MAPIE (Confianza {confidence_level:.0%})..."
    )
    mapie = SplitConformalRegressor(
        estimator=xgb,
        confidence_level=confidence_level,
        prefit=True,
    )
    mapie.conformalize(X_val, y_val)

    # 7. Evaluación en Conjunto de Prueba Oficial de la NASA
    X_test_last, y_test = load_nasa_test_set(pipeline, data_dir=data_dir)
    test_metrics = {}
    if len(X_test_last) > 0:
        y_test_pred, y_test_intervals = mapie.predict_interval(X_test_last)
        y_test_pred = np.clip(y_test_pred, 0, adapter.rul_cap)
        y_test_lower = np.clip(y_test_intervals[:, 0, 0], 0, adapter.rul_cap)
        y_test_upper = np.clip(y_test_intervals[:, 1, 0], 0, adapter.rul_cap)

        test_rmse = compute_rmse(y_test, y_test_pred)
        test_mae = compute_mae(y_test, y_test_pred)
        test_nasa = compute_nasa_score(y_test, y_test_pred)
        coverage = float(np.mean((y_test >= y_test_lower) & (y_test <= y_test_upper)))

        test_metrics = {
            "test_rmse": test_rmse,
            "test_mae": test_mae,
            "test_nasa_score": test_nasa,
            "empirical_coverage_90": coverage,
        }

        logger.info("\n" + "=" * 55)
        logger.info("   RESULTADOS EN TEST OFICIAL NASA C-MAPSS (100 Turbinas)")
        logger.info("=" * 55)
        logger.info(f"   RMSE:               {test_rmse:.2f} ciclos")
        logger.info(f"   MAE:                {test_mae:.2f} ciclos")
        logger.info(f"   Score NASA:         {test_nasa:,.1f}")
        logger.info(f"   Cobertura (90%):    {coverage:.1%}")
        logger.info("=" * 55)

    # 8. Guardar Artefacto del Modelo
    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, "cmapss_rul_model.joblib")

    artifact = {
        "model": mapie,
        "base_estimator": xgb,
        "pipeline": pipeline,
        "confidence_level": confidence_level,
        "model_version": "v1.0.0-xgb-mapie",
        "feature_names": feature_names,
        "metrics": {
            "val_rmse": xgb_rmse,
            "val_mae": xgb_mae,
            "val_nasa_score": xgb_nasa,
            **test_metrics,
        },
    }
    joblib.dump(artifact, model_path)
    logger.info(f"\n[OK] Modelo y pipeline exportados exitosamente a:\n     '{model_path}'")
    return artifact


if __name__ == "__main__":
    train_and_evaluate()

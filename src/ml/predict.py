"""
Servicio de Inferencia en Tiempo Real y Persistencia Predictiva
==============================================================
Carga el modelo calibrado (XGBoost + MAPIE), extrae la telemetría reciente
del motor seleccionado desde TimescaleDB, genera la predicción de RUL con
intervalo de confianza al 90%, y persiste el resultado en la tabla 'prediction'.
"""

import logging
import os
import time
from typing import Dict, Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

from src.adapters.cmapss.adapter import DEFAULT_RUL_CAP
from src.simulation.ingestor import get_db_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_PATH = os.path.join(ROOT_DIR, "models", "cmapss_rul_model.joblib")


class RulPredictorService:
    """
    Servicio de inferencia industrial para estimación de RUL con cuantificación de incertidumbre.
    """

    def __init__(self, model_path: str = MODEL_PATH, engine=None):
        self.model_path = model_path
        self._engine = engine
        self._artifact: Optional[Dict] = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine

    def load_model(self) -> None:
        """Carga el artefacto entrenado (pipeline + modelo MAPIE)."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"No se encontró el modelo en '{self.model_path}'. "
                f"Ejecuta 'py -m src.ml.train' primero."
            )
        self._artifact = joblib.load(self.model_path)
        logger.info(f"Modelo {self._artifact['model_version']} cargado exitosamente.")

    def fetch_recent_telemetry(
        self, asset_id: str, dataset_id: str = "cmapss_fd001", lookback_cycles: int = 20
    ) -> pd.DataFrame:
        """
        Recupera los ciclos recientes del activo desde TimescaleDB para alimentar el rolling window.
        """
        query = text("""
            WITH recent_cycles AS (
                SELECT DISTINCT sequence_no
                FROM telemetry
                WHERE asset_id = :asset_id AND dataset_id = :dataset_id
                ORDER BY sequence_no DESC
                LIMIT :lookback
            )
            SELECT asset_id, observed_at, sequence_no, signal_key, value_double
            FROM telemetry
            WHERE asset_id = :asset_id
              AND dataset_id = :dataset_id
              AND sequence_no IN (SELECT sequence_no FROM recent_cycles)
            ORDER BY sequence_no ASC;
        """)

        with self.engine.connect() as conn:
            df_long = pd.read_sql(
                query,
                conn,
                params={
                    "asset_id": asset_id,
                    "dataset_id": dataset_id,
                    "lookback": lookback_cycles,
                },
            )

        if df_long.empty:
            raise ValueError(
                f"No hay telemetría en TimescaleDB para '{asset_id}' en '{dataset_id}'."
            )

        # Pivotar de formato largo a ancho
        pivoted = df_long.pivot_table(
            index=["asset_id", "observed_at", "sequence_no"],
            columns="signal_key",
            values="value_double",
        ).reset_index()
        pivoted.columns.name = None

        return pivoted

    def predict_for_asset(
        self,
        asset_id: str = "cmapss_1",
        dataset_id: str = "cmapss_fd001",
    ) -> Dict:
        """
        Ejecuta la inferencia de RUL y persiste la predicción en TimescaleDB.
        """
        if self._artifact is None:
            self.load_model()

        pipeline = self._artifact["pipeline"]
        model = self._artifact["model"]
        model_version = self._artifact["model_version"]

        start_time = time.perf_counter()

        # 1. Obtener telemetría reciente
        df_pivoted = self.fetch_recent_telemetry(asset_id, dataset_id)

        # 2. Generar rolling features
        df_features = pipeline.compute_rolling_features(df_pivoted)
        latest_row = df_features.iloc[-1:]

        for col in pipeline.fitted_feature_names:
            if col not in latest_row.columns:
                latest_row[col] = 0.0

        X_input = pipeline.scaler.transform(latest_row[pipeline.fitted_feature_names].values)

        # 3. Inferencia Conformal con MAPIE
        y_pred, y_pis = model.predict_interval(X_input)

        estimate = float(np.clip(y_pred[0], 0, DEFAULT_RUL_CAP))
        lower_bound = float(np.clip(y_pis[0, 0, 0], 0, DEFAULT_RUL_CAP))
        upper_bound = float(np.clip(y_pis[0, 1, 0], 0, DEFAULT_RUL_CAP))

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        current_sequence = int(latest_row["sequence_no"].iloc[0])
        current_observed_at = latest_row["observed_at"].iloc[0]

        # 4. Persistir en tabla 'prediction'
        insert_sql = text("""
            INSERT INTO prediction (
                asset_id, sequence_no, observed_at, model_version,
                estimate, lower_bound, upper_bound, latency_ms, dataset_id
            ) VALUES (
                :asset_id, :sequence_no, :observed_at, :model_version,
                :estimate, :lower_bound, :upper_bound, :latency_ms, :dataset_id
            )
            RETURNING prediction_id;
        """)

        with self.engine.begin() as conn:
            result = conn.execute(
                insert_sql,
                {
                    "asset_id": asset_id,
                    "sequence_no": current_sequence,
                    "observed_at": current_observed_at,
                    "model_version": model_version,
                    "estimate": round(estimate, 1),
                    "lower_bound": round(lower_bound, 1),
                    "upper_bound": round(upper_bound, 1),
                    "latency_ms": round(latency_ms, 2),
                    "dataset_id": dataset_id,
                },
            )
            pred_id = result.scalar()

        prediction_result = {
            "prediction_id": pred_id,
            "asset_id": asset_id,
            "sequence_no": current_sequence,
            "observed_at": str(current_observed_at),
            "rul_estimate": round(estimate, 1),
            "lower_bound_90": round(lower_bound, 1),
            "upper_bound_90": round(upper_bound, 1),
            "latency_ms": round(latency_ms, 2),
            "model_version": model_version,
        }

        logger.info(
            f"[PREDICCION RUL] Activo: {asset_id} (Ciclo #{current_sequence}) -> "
            f"RUL: {estimate:.1f} ciclos [IC 90%: {lower_bound:.1f} - {upper_bound:.1f}] "
            f"(Latencia: {latency_ms:.1f}ms)"
        )
        return prediction_result


if __name__ == "__main__":
    predictor = RulPredictorService()
    predictor.predict_for_asset("cmapss_1")

"""
Ingeniería de Características (Feature Engineering) para RUL en Turbofans
========================================================================
1. Selección de sensores informativos:
   Descarta los 7 sensores constantes sin señal de degradación en FD001
   (s1, s5, s6, s10, s16, s18, s19) y retiene los 14 sensores físicos activos:
   s2, s3, s4, s7, s8, s9, s11, s12, s13, s14, s15, s17, s20, s21.

2. Generación de características temporales:
   - Valores instantáneos de sensores activos y consignas.
   - Medias móviles (Rolling Mean) con ventana W para suavizar ruido de adquisición.
   - Desviaciones estándar móviles (Rolling Std) para capturar dispersión de vibración/temperatura.

3. Escalado preventivo contra fuga de información (Leakage-Safe):
   El scaler se ajusta estrictamente sobre el conjunto de entrenamiento (fit en train)
   y solo transforma validación/test.
"""

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

# Los 14 sensores que varían con la degradación termodinámica en C-MAPSS FD001
INFORMATIVE_SENSORS: List[str] = [
    "s2", "s3", "s4", "s7", "s8", "s9",
    "s11", "s12", "s13", "s14", "s15", "s17", "s20", "s21"
]
SETTINGS: List[str] = ["setting1", "setting2", "setting3"]
DEFAULT_BASE_FEATURES: List[str] = SETTINGS + INFORMATIVE_SENSORS


class CmapssFeaturePipeline:
    """
    Pipeline de extracción y normalización de features para modelos de RUL.
    """

    def __init__(
        self,
        base_features: Optional[List[str]] = None,
        window_size: int = 5,
    ):
        self.base_features = base_features or DEFAULT_BASE_FEATURES
        self.window_size = window_size
        self.scaler = StandardScaler()
        self.fitted_feature_names: List[str] = []
        self._is_fitted = False

    def flatten_canonical_df(self, canonical_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplana el DataFrame canónico expandiendo el diccionario 'features' a columnas.
        """
        features_expanded = pd.DataFrame(
            canonical_df["features"].tolist(), index=canonical_df.index
        )
        meta_cols = ["asset_id", "sequence_no"]
        if "target" in canonical_df.columns:
            meta_cols.append("target")

        flat_df = pd.concat([canonical_df[meta_cols], features_expanded], axis=1)
        return flat_df

    def compute_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calcula medias y desviaciones móviles por activo (asset_id) para evitar mezclar motores.
        """
        engineered_dfs = []
        for _, group in df.groupby("asset_id"):
            group_sorted = group.sort_values("sequence_no").copy()

            # Agregar rolling features sobre sensores informativos
            for col in INFORMATIVE_SENSORS:
                if col in group_sorted.columns:
                    roll = group_sorted[col].rolling(window=self.window_size, min_periods=1)
                    group_sorted[f"{col}_roll_mean"] = roll.mean()
                    group_sorted[f"{col}_roll_std"] = roll.std().fillna(0.0)

            engineered_dfs.append(group_sorted)

        result_df = pd.concat(engineered_dfs, axis=0).reset_index(drop=True)
        return result_df

    def fit_transform(
        self,
        df: pd.DataFrame,
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Ajusta el scaler sobre los datos de entrenamiento y devuelve matriz X, y, y nombres.
        """
        if "features" in df.columns:
            flat_df = self.flatten_canonical_df(df)
        else:
            flat_df = df.copy()

        df_features = self.compute_rolling_features(flat_df)

        feature_cols = [
            c for c in df_features.columns
            if c not in ("asset_id", "sequence_no", "target", "observed_at", "dataset_id")
        ]
        self.fitted_feature_names = feature_cols

        X_raw = df_features[feature_cols].values
        X_scaled = self.scaler.fit_transform(X_raw)
        self._is_fitted = True

        y = df_features["target"].values if "target" in df_features.columns else np.array([])
        return X_scaled, y, self.fitted_feature_names

    def transform(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Transforma datos de validación/test o inferencia usando el scaler previamente ajustado.
        """
        if not self._is_fitted:
            raise RuntimeError(
                "El pipeline debe ser ajustado con fit_transform() antes de llamar a transform()."
            )

        if "features" in df.columns:
            flat_df = self.flatten_canonical_df(df)
        else:
            flat_df = df.copy()

        df_features = self.compute_rolling_features(flat_df)

        for col in self.fitted_feature_names:
            if col not in df_features.columns:
                df_features[col] = 0.0

        X_raw = df_features[self.fitted_feature_names].values
        X_scaled = self.scaler.transform(X_raw)

        y = df_features["target"].values if "target" in df_features.columns else np.array([])
        return X_scaled, y

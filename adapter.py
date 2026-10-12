"""
Adapter de C-MAPSS FD001 (NASA Turbofan Engine Degradation Simulation)
======================================================================
Propósito:
    Transformar los datos crudos de telemetría de turbinas de avión de la NASA
    al "Esquema Canónico" unificado de la plataforma de Gemelo Digital (Fase 1).

Reglas del contrato (según Propuesta v0.3):
    1. asset_id: Identificador único y estable del equipo (ej: 'cmapss_1').
    2. observed_at: Timestamp sintético (base temporal + secuencia en minutos).
    3. sequence_no: Número de ciclo operacional (ordenado y sin duplicados).
    4. dataset_id: Identificador del dataset ('cmapss_fd001').
    5. features: Diccionario de mediciones físicas (settings operacionales + 21 sensores).
    6. modality: 'timeseries' (serie temporal).
    7. media_ref: None (no aplica para sensores continuos).
    8. target: RUL (Remaining Useful Life) con tope (cap) de 125 ciclos.
    9. split_hint: 'train' o 'test'.
    10. quality_flags: Indicador de calidad ('OK' / 0).
"""

import os
from typing import Optional
import numpy as np
import pandas as pd

# -------------------------------------------------------------------------
# CONSTANTES Y METADATOS DEL DATASET C-MAPSS
# -------------------------------------------------------------------------
DATASET_ID = "cmapss_fd001"
DEFAULT_RUL_CAP = 125
BASE_TIMESTAMP = "2026-01-01 00:00:00"

# Nombres originales de las 26 columnas en los archivos de la NASA
SETTINGS = ["setting1", "setting2", "setting3"]
SENSORS = [f"s{i}" for i in range(1, 22)]
RAW_COLUMNS = ["engine_id", "cycle"] + SETTINGS + SENSORS
FEATURE_COLUMNS = SETTINGS + SENSORS


def resolve_file_path(data_dir: str, filename: str = "train_FD001.txt") -> str:
    """
    Localiza el archivo de datos tanto si se pasa la ruta raíz 'Dataset'
    como si se pasa directamente 'Dataset/CMaps'.
    """
    candidates = [
        os.path.join(data_dir, filename),
        os.path.join(data_dir, "CMaps", filename),
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
    data_dir: str = "Dataset/CMaps",
    filename: str = "train_FD001.txt",
    rul_cap: int = DEFAULT_RUL_CAP,
    split_hint: str = "train"
) -> pd.DataFrame:
    """
    Carga, procesa, valida y convierte los datos crudos de C-MAPSS FD001
    al Esquema Canónico unificado del Gemelo Digital.

    Parámetros:
        data_dir: Carpeta donde residen los datos crudos.
        filename: Nombre del archivo a cargar (por defecto 'train_FD001.txt').
        rul_cap: Tope máximo para el RUL en etapas tempranas (default: 125 ciclos).
        split_hint: Etiqueta de partición ('train' o 'test').

    Retorna:
        pd.DataFrame con el esquema canónico completo.
    """
    # ---------------------------------------------------------------------
    # 1. LECTURA DEL ARCHIVO CRUDO (Raw Layer)
    # ---------------------------------------------------------------------
    file_path = resolve_file_path(data_dir, filename)
    
    # sep=r'\s+' maneja la separación por uno o más espacios en blanco.
    # header=None indica que no hay fila de encabezado en el texto plano.
    raw_df = pd.read_csv(file_path, sep=r'\s+', header=None)
    
    # Nos quedamos con las primeras 26 columnas (evita columnas vacías por espacios al final)
    df = raw_df.iloc[:, :len(RAW_COLUMNS)].copy()
    df.columns = RAW_COLUMNS

    # ---------------------------------------------------------------------
    # 2. CÁLCULO DEL TARGET: RUL CON TOPE POR TRAMOS (RUL piecewise-linear)
    # ---------------------------------------------------------------------
    # En C-MAPSS train, la turbina opera hasta fallar.
    # El ciclo máximo registrado de cada motor es su punto exacto de falla.
    max_cycles = df.groupby("engine_id")["cycle"].transform("max")
    
    # RUL real = ciclo final de falla - ciclo actual
    true_rul = max_cycles - df["cycle"]
    
    # Aplicamos el tope (piecewise linear): RUL = min(true_rul, rul_cap)
    # En etapas tempranas no hay degradación detectable; el tope estabiliza el modelo.
    clipped_rul = true_rul.clip(upper=rul_cap)

    # ---------------------------------------------------------------------
    # 3. CONSTRUCCIÓN DEL ESQUEMA CANÓNICO (Canonical Layer)
    # ---------------------------------------------------------------------
    canonical = pd.DataFrame()

    # asset_id: Identificador único y legible del motor (ej: 'cmapss_1')
    canonical["asset_id"] = "cmapss_" + df["engine_id"].astype(str)

    # sequence_no: Número de ciclo dentro de la corrida del equipo
    canonical["sequence_no"] = df["cycle"].astype(int)

    # observed_at: Timestamp sintético (fecha base + ciclo en minutos)
    base_time = pd.to_datetime(BASE_TIMESTAMP)
    canonical["observed_at"] = base_time + pd.to_timedelta(df["cycle"], unit="m")

    # dataset_id: Identificador formal del dataset
    canonical["dataset_id"] = DATASET_ID

    # modality: Tipo de señal ('timeseries' para telemetría industrial)
    canonical["modality"] = "timeseries"

    # media_ref: Referencia a archivo multimedia (None en telemetría pura)
    canonical["media_ref"] = None

    # features: Empaquetado de settings y lecturas de sensores en diccionarios
    canonical["features"] = df[FEATURE_COLUMNS].to_dict(orient="records")

    # target: RUL calculado con tope
    canonical["target"] = clipped_rul.astype(float)

    # split_hint: Indica si los datos pertenecen al conjunto de entrenamiento o prueba
    canonical["split_hint"] = split_hint

    # quality_flags: Indicador de calidad del registro ('OK' si no hay anomalías de carga)
    canonical["quality_flags"] = "OK"

    # ---------------------------------------------------------------------
    # 4. VALIDACIONES DE CALIDAD (Data Quality Rules)
    # ---------------------------------------------------------------------
    validate_canonical(canonical, rul_cap=rul_cap)

    return canonical


def validate_canonical(df: pd.DataFrame, rul_cap: int = DEFAULT_RUL_CAP) -> None:
    """
    Ejecuta las reglas mínimas de calidad exigidas en la arquitectura:
    1. Esquema: Todas las columnas requeridas existen.
    2. Integridad: Ausencia de valores nulos en columnas obligatorias.
    3. Secuencia: Ciclos ordenados y sin duplicados por activo.
    4. Target: RUL decreciente monotónicamente y acotado por rul_cap.
    """
    required_cols = [
        "asset_id", "sequence_no", "observed_at", "dataset_id",
        "modality", "features", "target", "split_hint", "quality_flags"
    ]
    for col in required_cols:
        assert col in df.columns, f"Regla fallida: Columna obligatoria '{col}' ausente."

    # Regla 1: Ausencia de valores nulos en campos clave
    mandatory_no_nulls = ["asset_id", "sequence_no", "observed_at", "target", "dataset_id"]
    null_counts = df[mandatory_no_nulls].isna().sum().sum()
    assert null_counts == 0, f"Regla fallida: Se encontraron {null_counts} valores nulos en columnas clave."

    # Regla 2: Tope de RUL respetado
    assert (df["target"] <= rul_cap).all(), f"Regla fallida: Existen valores de RUL mayores al tope ({rul_cap})."
    assert (df["target"] >= 0).all(), "Regla fallida: Existen valores de RUL negativos."

    # Regla 3: Secuencia ordenada sin duplicados y monótonamente decreciente en target
    for asset, group in df.groupby("asset_id"):
        # Secuencia creciente sin duplicados
        cycles = group["sequence_no"].values
        assert np.all(np.diff(cycles) > 0), f"Regla fallida: Secuencia con saltos o duplicados en {asset}."

        # RUL monótonamente decreciente (<=)
        assert group["target"].is_monotonic_decreasing, (
            f"Regla fallida: RUL no es monótonamente decreciente en {asset}."
        )


def to_long_telemetry(canonical_df: pd.DataFrame) -> pd.DataFrame:
    """
    Convierte el formato canónico a formato 'largo' (long telemetry)
    para almacenamiento en TimescaleDB (Fase 2):
    telemetry(asset_id, observed_at, sequence_no, signal_key, value_double, unit, quality, dataset_id)
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


if __name__ == "__main__":
    print("=" * 70)
    print("   PRUEBA DEL ADAPTER C-MAPSS FD001 (Fase 1 - Gemelo Digital)")
    print("=" * 70)
    
    data_directory = os.path.join(os.path.dirname(__file__), "Dataset", "CMaps")
    df_canonical = load(data_dir=data_directory)
    
    print(f"\n[OK] Carga exitosa: {len(df_canonical):,} registros procesados.")
    print(f"[OK] Total de motores (activos) únicos: {df_canonical['asset_id'].nunique()}")
    print(f"[OK] Columnas generadas:\n     {list(df_canonical.columns)}")
    print(f"\n[OK] Vista previa de las primeras 3 filas:")
    print(df_canonical[["asset_id", "sequence_no", "observed_at", "target", "split_hint"]].head(3))
    print("\n[OK] Todas las reglas de calidad pasaron satisfactoriamente.")
    print("=" * 70)
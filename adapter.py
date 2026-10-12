import os
import pandas as pd
import numpy as np

# Definición de columnas estándar para C-MAPSS
COLS = ["engine_id", "cycle", "setting1", "setting2", "setting3"] + [f"s{i}" for i in range(1, 22)]

def load(data_dir, rul_cap=125):
    # 1. Definimos la ruta de train_FD001.txt
    file_path = os.path.join(data_dir, 'train_FD001.txt')
    
    # Leemos el archivo. sep='\s+' maneja los espacios variables.
    # header=None porque no tiene nombres de columna nativos.
    df = pd.read_csv(file_path, sep='\s+', header=None)
    
    # 2. Tomamos solo las primeras 26 columnas para evitar columnas fantasma y asignamos nombres
    df = df.iloc[:, :len(COLS)]
    df.columns = COLS
    
    # 3. Calculamos el RUL (Remaining Useful Life) con tope (rul_cap)
    # max_cycle para cada motor
    df['max_cycle'] = df.groupby('engine_id')['cycle'].transform('max')
    # El RUL real es max_cycle - ciclo actual
    df['rul'] = df['max_cycle'] - df['cycle']
    # Aplicamos el límite
    df['rul'] = df['rul'].clip(upper=rul_cap)
    
    # 4. Armamos el esquema canónico
    canonical_df = pd.DataFrame()
    
    # timestamp sintético: una fecha inicial ficticia + ciclo actual en minutos
    base_date = pd.to_datetime('2026-01-01 00:00:00')
    canonical_df['timestamp'] = base_date + pd.to_timedelta(df['cycle'], unit='m')
    
    # asset_id como string (identificador único del motor)
    canonical_df['asset_id'] = df['engine_id'].astype(str)
    
    # Nombre estático del dataset
    canonical_df['dataset'] = 'cmapss_fd001'
    
    # Agrupamos las características s1..s21 en una sola columna como diccionarios
    sensor_cols = [f"s{i}" for i in range(1, 22)]
    canonical_df['features'] = df[sensor_cols].to_dict(orient='records')
    
    # Guardamos el target final
    canonical_df['target'] = df['rul']
    
    # 5. Validación
    # Validamos que no haya NaNs en el dataset
    assert canonical_df.isna().sum().sum() == 0, "¡Se encontraron valores nulos en el dataset canónico!"
    
    # Validamos que el RUL sea decreciente por motor (puede estancarse al inicio por el tope, pero no aumentar)
    for engine, group in canonical_df.groupby('asset_id'):
        # is_monotonic_decreasing devuelve True si es constantemente menor o igual al anterior
        assert group['target'].is_monotonic_decreasing, f"El RUL del motor {engine} no es monótonamente decreciente"
        
    print("¡Validación exitosa! Todos los checks pasaron sin problemas.")
    return canonical_df
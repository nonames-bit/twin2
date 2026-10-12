# Guía de Construcción: Ignition Perspective - Gemelo Digital 🏭✈️

Esta guía te acompaña paso a paso para diseñar tu primer dashboard industrial en **Ignition Perspective** conectado a **TimescaleDB**.

---

## 🚀 Paso 1: Abrir Ignition Designer

1. En tu navegador en **http://localhost:8089**, haz clic en el botón superior derecho: **"Get Designer"** o **"Launch Designer"**.
2. Se descargará o abrirá el ejecutable del **Ignition Designer Launcher**.
3. Selecciona tu Gateway local (`http://localhost:8089`).
4. Inicia sesión con:
   * **Usuario**: `admin`
   * **Contraseña**: `12334`

---

## 📁 Paso 2: Crear un Nuevo Proyecto

1. En la ventana del Designer, haz clic en **"Create New Project..."**.
2. Completa los campos básicos:
   * **Project Name**: `DigitalTwin`
   * **Title**: `Gemelo Digital - Turbinas C-MAPSS`
   * **Default Database**: `twin` *(la conexión que creamos previamente)*
3. Haz clic en **Create Project**.

---

## ⚡ Paso 3: Configurar las Named Queries

En el panel izquierdo del Designer (**Project Browser**):
1. Despliega **Named Queries**.
2. Haz clic derecho sobre *Named Queries* -> **New Folder** -> Nómbrala: `Twin`.
3. Adentro de la carpeta `Twin`, crea las siguientes 4 consultas haciendo clic derecho -> **New Named Query**:

### 1. `Twin/active_assets`
* **Query Type**: Query
* **Database Connection**: `twin` (o por defecto del proyecto)
* **Parameters**: *(Ninguno)*
* **SQL Query**:
```sql
SELECT DISTINCT 
    asset_id AS value,
    'Turbina ' || asset_id AS label,
    MAX(sequence_no) AS max_cycle
FROM telemetry
GROUP BY asset_id
ORDER BY asset_id ASC;
```

---

### 2. `Twin/turbofan_kpis`
* **Query Type**: Query
* **Database Connection**: `twin`
* **Parameters**:
  * Name: `assetId` | Type: `String`
* **SQL Query**:
```sql
WITH latest_seq AS (
    SELECT MAX(sequence_no) AS max_seq
    FROM telemetry
    WHERE asset_id = :assetId
)
SELECT 
    t.asset_id,
    t.sequence_no AS current_cycle,
    MAX(t.observed_at) AS last_observed_at,
    MAX(CASE WHEN t.signal_key = 's2' THEN t.value_double END) AS lpc_temp_s2,
    MAX(CASE WHEN t.signal_key = 's4' THEN t.value_double END) AS lpt_temp_s4,
    MAX(CASE WHEN t.signal_key = 's7' THEN t.value_double END) AS hpc_press_s7,
    MAX(CASE WHEN t.signal_key = 's8' THEN t.value_double END) AS fan_speed_s8,
    CASE 
        WHEN t.sequence_no > 160 THEN 'Critico'
        WHEN t.sequence_no > 100 THEN 'Alerta'
        ELSE 'Normal'
    END AS health_status
FROM telemetry t
JOIN latest_seq ls ON t.sequence_no = ls.max_seq
WHERE t.asset_id = :assetId
GROUP BY t.asset_id, t.sequence_no;
```

---

### 3. `Twin/telemetry_trend`
* **Query Type**: Query
* **Database Connection**: `twin`
* **Parameters**:
  * Name: `assetId` | Type: `String`
  * Name: `startCycle` | Type: `Integer`
  * Name: `endCycle` | Type: `Integer`
* **SQL Query**:
```sql
SELECT 
    observed_at,
    sequence_no AS cycle,
    MAX(CASE WHEN signal_key = 's2' THEN value_double END) AS temp_lpc_s2,
    MAX(CASE WHEN signal_key = 's3' THEN value_double END) AS temp_hpc_s3,
    MAX(CASE WHEN signal_key = 's4' THEN value_double END) AS temp_lpt_s4,
    MAX(CASE WHEN signal_key = 's7' THEN value_double END) AS press_hpc_s7,
    MAX(CASE WHEN signal_key = 's8' THEN value_double END) AS rpm_fan_s8
FROM telemetry
WHERE asset_id = :assetId
  AND sequence_no BETWEEN :startCycle AND :endCycle
GROUP BY observed_at, sequence_no
ORDER BY sequence_no ASC;
```

---

### 4. `Twin/latest_sensors`
* **Query Type**: Query
* **Database Connection**: `twin`
* **Parameters**:
  * Name: `assetId` | Type: `String`
* **SQL Query**:
```sql
WITH latest_seq AS (
    SELECT MAX(sequence_no) AS max_seq
    FROM telemetry
    WHERE asset_id = :assetId
)
SELECT 
    t.signal_key,
    t.value_double,
    t.unit,
    t.quality,
    t.observed_at
FROM telemetry t
JOIN latest_seq ls ON t.sequence_no = ls.max_seq
WHERE t.asset_id = :assetId
ORDER BY 
    CASE 
        WHEN t.signal_key LIKE 'setting%' THEN 1 
        ELSE 2 
    END,
    t.signal_key;
```

---

## 🎨 Paso 4: Diseñar la Pantalla Perspective (`Turbofan_Overview`)

1. En el Project Browser, ve a **Perspective -> Views**.
2. Clic derecho -> **New View...**:
   * Name: `Turbofan_Overview`
   * Root Container: **Flex Container** (Dirección: Column)
3. Agrega los siguientes componentes arrastrándolos desde la paleta:

### 1. Fila Superior: Selector de Motor
* Arrastra un componente **Dropdown**.
* En la propiedad `props.options`: haz un **Binding** a Named Query -> `Twin/active_assets`.
* En `props.value`: pon por defecto `'cmapss_1'`.

### 2. Fila de KPIs (Flex Row con tarjetas)
* **Tarjeta 1 (Ciclo de Operación)**: Muestra el ciclo actual.
* **Tarjeta 2 (Temperatura LPT `s4`)**: Enlaza al valor `lpt_temp_s4` con sufijo `°R`.
* **Tarjeta 3 (Estado de Salud)**: Enlaza a `health_status`. Si es `'Critico'`, aplica color de fondo rojo; si es `'Normal'`, verde.

### 3. Gráfica de Tendencia (TimeSeries Chart)
* Arrastra un componente **TimeSeries Chart** o **Chart**.
* Enlaza los datos a `Twin/telemetry_trend` pasando como parámetro el motor seleccionado en el Dropdown.
* Configura los trazos (Pens) para las temperaturas `temp_lpc_s2` y `temp_lpt_s4`.

### 4. Tabla de Instrumentación (Table)
* Arrastra una **Table**.
* Enlaza la propiedad `props.data` a la Named Query `Twin/latest_sensors`.
* Verás en vivo las 24 mediciones de sensores del motor.

-- =====================================================================
-- Named Query: Twin/latest_sensors
-- Propósito: Listar todas las señales y sensores del último ciclo del motor
-- Parámetros: :assetId (String, ej: 'cmapss_1')
-- Tipo de retorno: Dataset (24 filas: 3 settings + 21 sensores)
-- Base de datos: twin
-- =====================================================================

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

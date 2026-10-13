-- =====================================================================
-- Named Query: Twin/turbofan_kpis
-- Propósito: Obtener los indicadores clave (KPIs) del motor seleccionado
-- Parámetros: :assetId (String, ej: 'cmapss_1')
-- Tipo de retorno: Scalar o Dataset (1 fila)
-- Base de datos: twin
-- =====================================================================

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
    -- Estado de salud calculado por degradación térmica real de la turbina (LPT Temp s4)
    CASE 
        WHEN MAX(CASE WHEN t.signal_key = 's4' THEN t.value_double END) >= 1418.0 THEN 'Critico'
        WHEN MAX(CASE WHEN t.signal_key = 's4' THEN t.value_double END) >= 1408.0 THEN 'Alerta'
        ELSE 'Normal'
    END AS health_status
FROM telemetry t
JOIN latest_seq ls ON t.sequence_no = ls.max_seq
WHERE t.asset_id = :assetId
GROUP BY t.asset_id, t.sequence_no;

-- =====================================================================
-- Named Query: Twin/telemetry_trend
-- Propósito: Obtener histórico de sensores térmicos y de presión para gráfica
-- Parámetros: 
--     :assetId (String, ej: 'cmapss_1')
--     :startCycle (Integer, default: 1)
--     :endCycle (Integer, default: 200)
-- Tipo de retorno: Dataset (Series de tiempo)
-- Base de datos: twin
-- =====================================================================

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

-- =====================================================================
-- Named Query: Twin/turbofan_prediction
-- Propósito: Obtener la predicción de RUL más reciente con su intervalo de incertidumbre al 90%
-- Parámetros: :assetId (String, ej: 'cmapss_1')
-- Tipo de retorno: Dataset (1 fila)
-- Base de datos: twin
-- =====================================================================

SELECT 
    prediction_id,
    asset_id,
    sequence_no,
    observed_at,
    estimate AS rul_cycles,
    lower_bound AS rul_lower_90,
    upper_bound AS rul_upper_90,
    latency_ms,
    model_version,
    -- Estado prescriptivo industrial según el RUL restante
    CASE 
        WHEN estimate <= 15.0 THEN 'Parada Inmediata'
        WHEN estimate <= 45.0 THEN 'Mantenimiento Requerido'
        ELSE 'Operación Segura'
    END AS prescriptive_action
FROM prediction
WHERE asset_id = :assetId
ORDER BY sequence_no DESC, prediction_id DESC
LIMIT 1;

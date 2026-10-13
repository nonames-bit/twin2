-- =====================================================================
-- Named Query: Twin/active_assets
-- Propósito: Listar los activos disponibles para el selector desplegable (Dropdown)
-- Parámetros: Ninguno
-- Tipo de retorno: Dataset (value, label)
-- Base de datos: twin
-- =====================================================================

SELECT DISTINCT 
    asset_id AS value,
    'Turbina ' || asset_id AS label
FROM telemetry
GROUP BY asset_id
ORDER BY asset_id ASC;

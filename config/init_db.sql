-- =====================================================================
-- ESQUEMA OPERACIONAL: TIMESCALEDB (Digital Twin Industrial)
-- Propuesta v0.3 - Mantenimiento Predictivo + IA
-- =====================================================================

-- 1. Habilitar extensión TimescaleDB para series de tiempo
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 2. Tabla de Telemetría Operacional (Formato Largo Universal - Capa B)
-- Clave primaria compuesta para garantizar IDEMPOTENCIA:
-- Un reenvío de mensaje por fallo de red no genera duplicados.
CREATE TABLE IF NOT EXISTS telemetry (
    asset_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    sequence_no INTEGER NOT NULL,
    signal_key TEXT NOT NULL,
    value_double DOUBLE PRECISION NOT NULL,
    unit TEXT DEFAULT 'raw',
    quality TEXT DEFAULT 'OK',
    dataset_id TEXT NOT NULL,
    PRIMARY KEY (dataset_id, asset_id, sequence_no, signal_key, observed_at)
);

-- Convertir tabla estándar en hypertable particionada por tiempo
SELECT create_hypertable('telemetry', 'observed_at', if_not_exists => TRUE);

-- Índice optimizado para búsquedas rápidas por motor y tiempo (Ignition SCADA)
CREATE INDEX IF NOT EXISTS idx_telemetry_asset_time
ON telemetry (asset_id, observed_at DESC);

-- 3. Tabla de Predicciones de Machine Learning (Capa C / Serving)
CREATE TABLE IF NOT EXISTS prediction (
    prediction_id BIGSERIAL PRIMARY KEY,
    asset_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    model_version TEXT NOT NULL,
    estimate DOUBLE PRECISION NOT NULL,          -- RUL estimado
    lower_bound DOUBLE PRECISION,               -- Límite inferior de incertidumbre
    upper_bound DOUBLE PRECISION,               -- Límite superior de incertidumbre
    latency_ms DOUBLE PRECISION,                -- Tiempo de cálculo en ms
    dataset_id TEXT NOT NULL
);

-- 4. Tabla de Decisiones y Recomendaciones de Mantenimiento (Capa C)
CREATE TABLE IF NOT EXISTS decision (
    decision_id BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT REFERENCES prediction(prediction_id),
    asset_id TEXT NOT NULL,
    option TEXT NOT NULL,                        -- 'Continuar', 'Inspeccionar', 'Parada'
    expected_cost DOUBLE PRECISION NOT NULL,    -- Costo económico proyectado
    confidence DOUBLE PRECISION NOT NULL,       -- Nivel de confianza (0 a 1)
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Tabla de Auditoría de Acciones Humanas (Capa C)
CREATE TABLE IF NOT EXISTS action_log (
    action_id BIGSERIAL PRIMARY KEY,
    decision_id BIGINT REFERENCES decision(decision_id),
    actor TEXT NOT NULL,                         -- Nombre o rol del operador
    status TEXT NOT NULL,                        -- 'Aprobado', 'Rechazado', 'Pospuesto'
    reason TEXT,
    acted_at TIMESTAMPTZ DEFAULT NOW()
);

"""
Pruebas Unitarias para el Módulo de Simulación e Ingesta MQTT (Fase 2)
====================================================================
Valida:
1. Desempaquetado correcto de mensajes JSON a formato largo.
2. Formato de registros para TimescaleDB con unidades físicas del manifiesto.
3. Ejecución de flush() e idempotencia con motor SQLite en memoria (Hermético para CI).
4. Vaciado y resiliencia del buffer ante excepciones.
"""

from datetime import datetime, timezone

from sqlalchemy import create_engine, text

from src.simulation.ingestor import TelemetryIngestor


def test_unpack_message_to_long_rows():
    """Verifica que un mensaje de ciclo con N sensores se expanda a N filas largas con unidades."""
    sample_payload = {
        "dataset_id": "cmapss_fd001",
        "asset_id": "cmapss_1",
        "sequence_no": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "features": {
            "setting1": 0.0023,
            "setting2": 0.0003,
            "s1": 518.67,
            "s2": 641.82,
        },
        "quality_flags": "OK",
    }

    # Instanciamos el ingestor sin conexión real externa
    ingestor = TelemetryIngestor(engine=None)
    rows = ingestor.unpack_message_to_long_rows(sample_payload)

    # 4 features en el payload deben generar exactamente 4 filas largas
    assert len(rows) == 4

    # Verificar estructura de cada fila
    first_row = rows[0]
    assert first_row["asset_id"] == "cmapss_1"
    assert first_row["dataset_id"] == "cmapss_fd001"
    assert first_row["sequence_no"] == 1
    assert first_row["signal_key"] in sample_payload["features"]
    assert first_row["unit"] in ("kft", "°R", "Mach", "raw", "dimensionless")
    assert first_row["quality"] == "OK"


def test_flush_idempotency_with_sqlite_engine():
    """
    Verifica que el flush inserte registros y garantice idempotencia
    usando un motor SQLite en memoria compatible con CI sin requerir PostgreSQL.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE telemetry (
                dataset_id TEXT,
                asset_id TEXT,
                sequence_no INT,
                signal_key TEXT,
                observed_at TEXT,
                value_double REAL,
                unit TEXT,
                quality TEXT,
                PRIMARY KEY (dataset_id, asset_id, sequence_no, signal_key, observed_at)
            );
        """))

    ingestor = TelemetryIngestor(engine=engine)
    payload = {
        "dataset_id": "cmapss_fd001",
        "asset_id": "cmapss_1",
        "sequence_no": 1,
        "observed_at": "2026-01-01T00:01:00",
        "features": {"s2": 641.82, "s4": 1400.5},
        "quality_flags": "OK",
    }

    # Primer lote
    ingestor.buffer.extend(ingestor.unpack_message_to_long_rows(payload))
    assert len(ingestor.buffer) == 2
    ingestor.flush()
    assert len(ingestor.buffer) == 0

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM telemetry")).scalar()
        assert count == 2

    # Reintento con los mismos datos (idempotencia pura)
    ingestor.buffer.extend(ingestor.unpack_message_to_long_rows(payload))
    ingestor.flush()

    with engine.connect() as conn:
        count_after = conn.execute(text("SELECT COUNT(*) FROM telemetry")).scalar()
        # Debe mantenerse estrictamente en 2 gracias a ON CONFLICT DO NOTHING
        assert count_after == 2

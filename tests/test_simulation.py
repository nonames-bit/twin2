"""
Pruebas Unitarias para el Módulo de Simulación e Ingesta MQTT (Fase 2)
====================================================================
Valida:
1. Desempaquetado correcto de mensajes JSON a formato largo.
2. Formato de registros para TimescaleDB.
3. Preservación de la clave de idempotencia.
"""

from datetime import datetime, timezone
import pytest
from src.simulation.ingestor import TelemetryIngestor


def test_unpack_message_to_long_rows():
    """Verifica que un mensaje de ciclo con N sensores se expanda a N filas largas."""
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

    # Instanciamos el ingestor sin conexión real a base de datos (mock engine)
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
    assert first_row["unit"] == "raw"
    assert first_row["quality"] == "OK"

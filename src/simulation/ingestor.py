"""
Ingestor de Telemetría Industrial (MQTT -> TimescaleDB)
======================================================
Propósito:
    Escucha los tópicos de telemetría de Mosquitto MQTT en tiempo real,
    desempaqueta las señales al formato largo universal y las persiste
    en la hipertabla de TimescaleDB con garantía estricta de idempotencia.
"""

import json
import logging
import os
import sys
import time
from typing import Dict, List
from dotenv import load_dotenv
from paho.mqtt import client as mqtt
from sqlalchemy import create_engine, text

# Configuración de rutas para imports absolutos
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.contracts import TelemetryRecord

load_dotenv()
logger = logging.getLogger(__name__)

TOPIC_PATTERN = "industry/telemetry/#"
BATCH_SIZE = 50
FLUSH_INTERVAL_SEC = 3.0


def get_db_engine():
    """Crea la conexión a la base de datos PostgreSQL / TimescaleDB."""
    user = os.getenv("POSTGRES_USER", "twin")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "twin")
    
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url, pool_pre_ping=True)


class TelemetryIngestor:
    """Consumidor MQTT que persiste telemetría en TimescaleDB en formato largo."""

    def __init__(self, engine=None):
        self.engine = engine or get_db_engine()
        self.buffer: List[Dict] = []
        self.last_flush = time.time()

    def unpack_message_to_long_rows(self, payload: dict) -> List[Dict]:
        """
        Desempaqueta un mensaje JSON canónico a múltiples registros en formato largo
        (una fila por señal, activo e instante).
        """
        rows = []
        asset_id = payload["asset_id"]
        observed_at = payload["observed_at"]
        sequence_no = int(payload["sequence_no"])
        dataset_id = payload["dataset_id"]
        quality = payload.get("quality_flags", "OK")
        features = payload.get("features", {})

        for signal_key, value in features.items():
            record = TelemetryRecord(
                asset_id=asset_id,
                observed_at=observed_at,
                sequence_no=sequence_no,
                signal_key=signal_key,
                value_double=float(value),
                unit="raw",
                quality=quality,
                dataset_id=dataset_id,
            )
            rows.append(record.model_dump())
        return rows

    def flush(self) -> None:
        """Inserta los registros acumulados en TimescaleDB con idempotencia."""
        if not self.buffer:
            return

        insert_sql = text("""
            INSERT INTO telemetry (
                asset_id, observed_at, sequence_no, signal_key,
                value_double, unit, quality, dataset_id
            ) VALUES (
                :asset_id, :observed_at, :sequence_no, :signal_key,
                :value_double, :unit, :quality, :dataset_id
            )
            ON CONFLICT (dataset_id, asset_id, sequence_no, signal_key, observed_at)
            DO NOTHING;
        """)

        with self.engine.begin() as conn:
            conn.execute(insert_sql, self.buffer)

        logger.info(f"[DB Flush] {len(self.buffer)} lecturas de sensores persistidas con idempotencia.")
        self.buffer.clear()
        self.last_flush = time.time()

    def process_message(self, client, userdata, message) -> None:
        """Callback ejecutado al recibir un mensaje del Broker MQTT."""
        try:
            raw_text = message.payload.decode("utf-8")
            data = json.loads(raw_text)
            long_rows = self.unpack_message_to_long_rows(data)
            self.buffer.extend(long_rows)

            if len(self.buffer) >= BATCH_SIZE or (time.time() - self.last_flush) >= FLUSH_INTERVAL_SEC:
                self.flush()
        except Exception as e:
            logger.error(f"Error al procesar mensaje MQTT: {e}", exc_info=True)


def start_ingestion():
    """Inicia el servicio ingestor suscrito al broker MQTT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    host = os.getenv("MQTT_BROKER_HOST", "localhost")
    port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    ingestor = TelemetryIngestor()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twin-ingestor")
    client.on_message = ingestor.process_message

    logger.info(f"Conectando Ingestor al Broker MQTT en {host}:{port}...")
    client.connect(host, port, keepalive=60)
    client.subscribe(TOPIC_PATTERN, qos=1)
    logger.info(f"Suscrito exitosamente al patrón: '{TOPIC_PATTERN}'")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Deteniendo Ingestor...")
        ingestor.flush()
    finally:
        client.disconnect()


if __name__ == "__main__":
    start_ingestion()

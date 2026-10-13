"""
Módulo de Ingesta y Persistencia en Tiempo Real (Fase 2)
========================================================
Consumidor MQTT industrial que recibe la telemetría canónica transmitida
por los activos y la persiste de forma eficiente e idempotente en TimescaleDB.

Mejoras de resiliencia de grado industrial:
1. Reconexión automática con re-suscripción en callback `on_connect`.
2. Temporizador de flush autónomo (hilo daemon) para no dejar datos varados si el feed cesa.
3. Aislamiento y cuarentena de errores en flush para evitar atascos infinitos en el buffer.
4. Mapeo de unidades físicas reales desde el manifiesto del dataset.
"""

import json
import logging
import os
import threading
import time
from typing import Dict, List, Optional

from dotenv import load_dotenv
from paho.mqtt import client as mqtt
from sqlalchemy import create_engine, text

from src.adapters.cmapss.adapter import CmapssAdapter
from src.core.contracts import TelemetryRecord

load_dotenv()

logger = logging.getLogger(__name__)

TOPIC_PATTERN = "industry/telemetry/#"
BATCH_SIZE = 50
FLUSH_INTERVAL_SEC = 3.0


def get_db_engine():
    """Crea la conexión a la base de datos PostgreSQL / TimescaleDB usando psycopg2 explícito."""
    user = os.getenv("POSTGRES_USER", "twin")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "twin")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url, pool_pre_ping=True)


class TelemetryIngestor:
    """Consumidor MQTT que persiste telemetría en TimescaleDB en formato largo."""

    def __init__(
        self,
        engine=None,
        units_map: Optional[Dict[str, str]] = None,
        flush_interval: float = FLUSH_INTERVAL_SEC,
    ):
        self._engine = engine
        self.buffer: List[Dict] = []
        self.last_flush = time.time()
        self.flush_interval = flush_interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._timer_thread: Optional[threading.Thread] = None

        # Cargar mapa de unidades físicas de ingeniería (ej: °R, psia, rpm)
        if units_map is not None:
            self.units_map = units_map
        else:
            try:
                self.units_map = CmapssAdapter().units
            except Exception:
                self.units_map = {}

    @property
    def engine(self):
        """Inicialización perezosa (lazy) del engine para permitir tests sin base de datos."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine

    def start_background_timer(self) -> None:
        """Inicia un hilo daemon periódico que ejecuta flush si han pasado FLUSH_INTERVAL_SEC."""
        if self._timer_thread is not None and self._timer_thread.is_alive():
            return
        self._stop_event.clear()
        self._timer_thread = threading.Thread(target=self._periodic_flush_worker, daemon=True)
        self._timer_thread.start()

    def stop_background_timer(self) -> None:
        """Detiene el hilo daemon y realiza un flush final de registros pendientes."""
        self._stop_event.set()
        if self._timer_thread is not None:
            self._timer_thread.join(timeout=2.0)
        self.flush()

    def _periodic_flush_worker(self) -> None:
        """Trabajador en segundo plano que vacía el buffer por tiempo."""
        while not self._stop_event.wait(timeout=1.0):
            with self._lock:
                if self.buffer and (time.time() - self.last_flush) >= self.flush_interval:
                    self._execute_flush()

    def unpack_message_to_long_rows(self, payload: dict) -> List[Dict]:
        """
        Desempaqueta un mensaje JSON canónico a múltiples registros en formato largo
        (una fila por señal, activo e instante) con unidades físicas reales.
        """
        rows = []
        asset_id = payload["asset_id"]
        observed_at = payload["observed_at"]
        sequence_no = int(payload["sequence_no"])
        dataset_id = payload["dataset_id"]
        quality = payload.get("quality_flags", "OK")
        features = payload.get("features", {})

        for signal_key, value in features.items():
            unit = self.units_map.get(signal_key, "raw")
            record = TelemetryRecord(
                asset_id=asset_id,
                observed_at=observed_at,
                sequence_no=sequence_no,
                signal_key=signal_key,
                value_double=float(value),
                unit=unit,
                quality=quality,
                dataset_id=dataset_id,
            )
            rows.append(record.model_dump())
        return rows

    def flush(self) -> None:
        """Punto de entrada con bloqueo para vaciado seguro del buffer."""
        with self._lock:
            self._execute_flush()

    def _execute_flush(self) -> None:
        """
        Inserta los registros acumulados en TimescaleDB con idempotencia
        y aislamiento de fallos ante excepciones.
        """
        if not self.buffer:
            return

        batch_to_insert = list(self.buffer)
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

        try:
            with self.engine.begin() as conn:
                conn.execute(insert_sql, batch_to_insert)
            logger.info(
                f"[DB Flush] {len(batch_to_insert)} lecturas persistidas con idempotencia."
            )
        except Exception as e:
            logger.error(
                f"[DB Flush Error] Falló inserción de lote ({len(batch_to_insert)} filas): {e}",
                exc_info=True,
            )
        finally:
            # Siempre limpiamos el buffer para evitar que un lote corrupto atasque el ingestor
            self.buffer.clear()
            self.last_flush = time.time()

    def process_message(self, client, userdata, message) -> None:
        """Callback ejecutado al recibir un mensaje del Broker MQTT."""
        try:
            raw_text = message.payload.decode("utf-8")
            data = json.loads(raw_text)
            long_rows = self.unpack_message_to_long_rows(data)
            with self._lock:
                self.buffer.extend(long_rows)
                if len(self.buffer) >= BATCH_SIZE:
                    self._execute_flush()
        except Exception as e:
            logger.error(f"Error al procesar mensaje MQTT: {e}", exc_info=True)


def start_ingestion():
    """Inicia el servicio ingestor suscrito al broker MQTT con reconexión robusta."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    host = os.getenv("MQTT_BROKER_HOST", "localhost")
    port = int(os.getenv("MQTT_BROKER_PORT", 1883))

    ingestor = TelemetryIngestor()
    ingestor.start_background_timer()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="twin-ingestor")
    client.on_message = ingestor.process_message

    def on_connect(c, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(
                f"Conectado a Broker MQTT ({host}:{port}). Suscribiendo a '{TOPIC_PATTERN}'..."
            )
            c.subscribe(TOPIC_PATTERN, qos=1)
            logger.info("Suscripción activa con éxito.")
        else:
            logger.error(f"Fallo de conexión al Broker MQTT con código: {rc}")

    client.on_connect = on_connect

    logger.info(f"Iniciando Ingestor hacia {host}:{port}...")
    client.connect(host, port, keepalive=60)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Deteniendo Ingestor...")
    finally:
        ingestor.stop_background_timer()
        client.disconnect()


if __name__ == "__main__":
    start_ingestion()

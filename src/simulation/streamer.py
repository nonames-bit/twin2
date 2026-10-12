"""
Simulador y Emulador de Telemetría Industrial (Streamer MQTT)
============================================================
Propósito:
    Reproduce las lecturas de sensores de las turbinas C-MAPSS ciclo a ciclo
    publicando mensajes JSON en el Broker MQTT (Eclipse Mosquitto).
    Actúa como si fuera el PLC físico o la tarjeta de adquisición en vuelo.

Tópico de publicación:
    industry/telemetry/{dataset_id}/{asset_id}
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional
from dotenv import load_dotenv
from paho.mqtt import client as mqtt

# Configuración de rutas para imports absolutos
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.adapters.cmapss.adapter import CmapssAdapter

load_dotenv()
logger = logging.getLogger(__name__)


def create_mqtt_client(host: str, port: int, client_id: str = "twin-streamer") -> mqtt.Client:
    """Crea y conecta un cliente MQTT con manejo de reconexión."""
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.connect(host, port, keepalive=60)
    client.loop_start()
    return client


def stream_telemetry(
    asset_filter: Optional[str] = "cmapss_1",
    rate_sec: float = 0.5,
    repeat: bool = False,
    broker_host: Optional[str] = None,
    broker_port: Optional[int] = None,
) -> None:
    """
    Carga el dataset canónico de C-MAPSS y publica sus ciclos de vuelo por MQTT.
    """
    host = broker_host or os.getenv("MQTT_BROKER_HOST", "localhost")
    port = int(broker_port or os.getenv("MQTT_BROKER_PORT", 1883))

    logger.info(f"Conectando Streamer al Broker MQTT en {host}:{port}...")
    client = create_mqtt_client(host, port)

    # 1. Cargar datos usando nuestro Adapter probado
    adapter = CmapssAdapter()
    df_canonical = adapter.load()

    # Si se especificó un motor específico (ej: 'cmapss_1')
    if asset_filter:
        df_canonical = df_canonical[df_canonical["asset_id"] == asset_filter]
        logger.info(f"Filtrando telemetría exclusivamente para el motor '{asset_filter}'.")

    records = df_canonical.to_dict(orient="records")
    total_records = len(records)
    logger.info(f"Iniciando emisión de {total_records} ciclos de vuelo a {rate_sec}s por mensaje.")

    try:
        while True:
            for i, row in enumerate(records, 1):
                topic = f"industry/telemetry/{row['dataset_id']}/{row['asset_id']}"
                payload = {
                    "dataset_id": row["dataset_id"],
                    "asset_id": row["asset_id"],
                    "sequence_no": int(row["sequence_no"]),
                    "observed_at": row["observed_at"].isoformat(),
                    "features": row["features"],
                    "quality_flags": row["quality_flags"],
                }

                client.publish(topic, json.dumps(payload), qos=1)
                logger.info(
                    f"[{i}/{total_records}] {row['asset_id']} Ciclo #{row['sequence_no']:03d} -> Tópico: {topic}"
                )
                time.sleep(rate_sec)

            if not repeat:
                logger.info("Transmisión finalizada con éxito.")
                break
            logger.info("Secuencia terminada. Reiniciando simulación en bucle...")
    except KeyboardInterrupt:
        logger.info("Transmisión detenida por el usuario.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Emulador de Telemetría Industrial MQTT")
    parser.add_argument("--asset", type=str, default="cmapss_1", help="ID del motor a transmitir")
    parser.add_argument("--rate", type=float, default=0.5, help="Segundos entre cada ciclo de vuelo")
    parser.add_argument("--repeat", action="store_true", help="Repetir infinitamente en bucle")
    args = parser.parse_args()

    stream_telemetry(asset_filter=args.asset, rate_sec=args.rate, repeat=args.repeat)

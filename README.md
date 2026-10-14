# Digital Twin: Predictive Maintenance & Industrial SCADA 🏭✈️

Plataforma de Gemelo Digital industrial para mantenimiento predictivo que conecta señales de telemetría de turbofans (**NASA C-MAPSS FD001**) a través de streaming **MQTT**, persistencia en base de datos de series temporales (**TimescaleDB**) y visualización y supervisión operativa en tiempo real con **Ignition Perspective**.

---

## 🏛️ Arquitectura del Sistema

```text
  [ C-MAPSS Raw Data ]
          │
          ▼
  ┌────────────────────────────────────────────────┐
  │  CmapssAdapter (src/adapters/cmapss/)          │
  │  • Arquitectura Hexagonal (Ports & Adapters)   │
  │  • Gobierno por Manifiesto (manifest.yaml)    │
  │  • Contratos Pydantic & Clave Idempotente      │
  └───────────────────────┬────────────────────────┘
                          │ (CanonicalRecord)
                          ▼
             [ MQTT Streamer (PLC Emulado) ]
                          │
                          │ Tópico: industry/telemetry/cmapss_fd001/{asset_id}
                          ▼
            [ Eclipse Mosquitto Broker :1883 ]
                          │
                          ▼
  ┌────────────────────────────────────────────────┐
  │  TelemetryIngestor (src/simulation/ingestor.py)│
  │  • Auto-reconexión segura en on_connect        │
  │  • Desempaquetado a formato largo con unidades │
  │  • Buffer con vaciado periódico autónomo       │
  │  • Inserción idempotente (ON CONFLICT DO NOTH) │
  └───────────────────────┬────────────────────────┘
                          │
                          ▼
             [ TimescaleDB Hypertable :5432 ]
                          │
                          │ JDBC Connection
                          ▼
  ┌────────────────────────────────────────────────┐
  │  Ignition Perspective SCADA Gateway :8089     │
  │  • Selector dinámico de turbina                │
  │  • KPIs en vivo (Ciclo, Temp LPT, Salud)       │
  │  • Tendencias históricas (TimeSeriesChart)     │
  │  • Auditoría de 24 sensores (Table)            │
  └────────────────────────────────────────────────┘
```

---

## 🚦 Estado de Implementación & Roadmap

| Fase | Componente | Estado | Descripción |
|---|---|---|---|
| **Fase 1** | Dominio Canónico & Hexagonal | ✅ **Completado** | Adapter C-MAPSS, Pydantic contracts, manifest gobernando unidades físicas y RUL cap a 125. |
| **Fase 2** | Streaming MQTT & Persistencia | ✅ **Completado** | Mosquitto broker, TimescaleDB hypertable, Ingestor resiliente con reconexión y tests herméticos. |
| **Fase 4** | SCADA Ignition Perspective | ✅ **Completado** | Named queries optimizadas, tarjetas de estado térmico, tendencias temporales y tabla de sensores. |
| **Fase 3** | Machine Learning & Incertidumbre | ✅ **Completado** | XGBoost + MAPIE Conformal (91.0% cobertura, RMSE 17.22 ciclos en 100 turbinas NASA), inferencia en vivo y persistencia en TimescaleDB. |
| **Fase 5** | Visión & Asistente RAG | ⏳ **Roadmap** | Inspección visual superficial de anomalías y recuperación de manuales técnicos para mantenimiento. |

---

## 📁 Estructura del Repositorio

```text
├── .github/workflows/
│   └── ci.yml                         # Pipeline CI: Ruff linter + Pytest + Coverage
├── config/
│   ├── init_db.sql                    # Esquema TimescaleDB: hypertables, prediction, audit
│   └── mosquitto/mosquitto.conf       # Configuración broker MQTT (puerto 1883, allow_anonymous)
├── docs/
│   └── ignition_perspective_guide.md  # Guía paso a paso para configurar Ignition Perspective
├── scada/named_queries/
│   ├── active_assets.sql              # Consulta de activos con orden natural numérico
│   ├── latest_sensors.sql             # Snapshot de los 24 sensores del último ciclo
│   ├── telemetry_trend.sql            # Histórico termodinámico para gráficas temporales
│   └── turbofan_kpis.sql              # KPIs y estado de salud basado en degradación física
├── src/
│   ├── core/
│   │   ├── base_adapter.py            # Puerto Hexagonal y conversión a formato largo
│   │   └── contracts.py               # Contratos Pydantic (CanonicalRecord, TelemetryRecord)
│   ├── adapters/cmapss/
│   │   ├── adapter.py                 # Adapter C-MAPSS gobernado dinámicamente por manifiesto
│   │   └── manifest.yaml              # Metadatos físicos, rangos y unidades (°R, psia, rpm)
│   └── simulation/
│       ├── streamer.py                # Emulador MQTT en tiempo real ciclo por ciclo
│       └── ingestor.py                # Ingestor resiliente a TimescaleDB con buffer temporal
├── tests/
│   ├── fixtures/
│   │   └── train_FD001.txt            # Fixture sintético para tests herméticos sin datos externos
│   ├── test_adapter.py                # Pruebas unitarias de esquema, contratos y RUL
│   └── test_simulation.py             # Pruebas de desempaquetado, flush e idempotencia SQLite
├── docker-compose.yml                 # Servicios contenerizados (TimescaleDB, Mosquitto, Ignition)
├── pyproject.toml                     # Metadatos del paquete (PEP 621) y configs de herramientas
├── requirements.txt                   # Dependencias de producción
├── requirements-dev.txt               # Dependencias de testing y calidad (pytest, ruff)
└── README.md
```

---

## 🚀 Inicio Rápido (Quickstart Local)

### 1. Clonar e Instalar Entorno
```bash
git clone https://github.com/nonames-bit/twin2.git
cd twin2

# Instalar dependencias en modo editable
pip install -r requirements-dev.txt
pip install -e .
```

### 2. Ejecutar Pruebas Automatizadas y Calidad
```bash
# Linter de código (0 advertencias)
ruff check .

# Suite completa de tests unitarios (100% hermética sin dependencias externas)
pytest -v
```

### 3. Levantar Infraestructura Industrial (Docker)
```bash
cp .env.example .env
docker compose up -d
```
Servicios levantados:
- **TimescaleDB**: `localhost:5432` (Base de datos: `twin`)
- **Mosquitto MQTT**: `localhost:1883`
- **Ignition Gateway**: `http://localhost:8089`

### 4. Transmitir Telemetría en Vivo
En una terminal, arranca el consumidor:
```bash
python -m src.simulation.ingestor
```
En otra terminal, arranca la transmisión del motor `cmapss_1`:
```bash
python -m src.simulation.streamer --asset cmapss_1 --rate 0.2
```

### 5. Visualizar en Ignition Perspective
Abre tu navegador en:
```text
http://localhost:8089/data/perspective/client/DigitalTwin
```
Podrás interactuar con el selector de turbinas, ver las tarjetas de KPIs actualizadas en tiempo real, navegar por la curva de degradación térmica e inspeccionar las lecturas de los 24 sensores.

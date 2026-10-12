# Digital Twin para Mantenimiento Predictivo + IA 🏭✈️

Una plataforma cloud y multimodal que convierte señales industriales e imágenes en histórico, predicciones con incertidumbre, decisiones de mantenimiento comparables y explicaciones técnicas integradas en **Ignition Perspective**.

---

## 🎯 Objetivo de la Plataforma
Demostrar un recorrido end-to-end de grado industrial:
1. **Ingeniería de Datos**: Ingestión, limpieza y traducción a contrato canónico con validación rigurosa.
2. **Streaming en Tiempo Real (OT/IT)**: Emisión de telemetría por **MQTT** y almacenamiento en base de datos de series temporales (**TimescaleDB**).
3. **Machine Learning & MLOps**: Modelos de regresión de RUL (Remaining Useful Life), clasificación y estimación de incertidumbre (**MLflow** + **MAPIE**).
4. **Visión Industrial**: Detección de anomalías en piezas superficiales (MVTec AD / EfficientAD).
5. **Decisión e IA Generativa**: Asistente técnico con **RAG** (Retrieval-Augmented Generation) y manuales técnicos.
6. **SCADA Industrial**: Operación, supervisión y dashboards en **Ignition Perspective**.

---

## 🚀 Estado Actual: Fase 1 (Contrato y Adapter C-MAPSS)

En esta fase completamos la **Capa A** (Ingesta y Preparación):
- **Dataset**: NASA C-MAPSS FD001 (100 turbinas turbofan operando hasta la falla).
- **Target**: RUL (Remaining Useful Life) con función lineal por tramos (*piecewise linear*) y tope en 125 ciclos.
- **Contrato Canónico**: Esquema universal (`asset_id`, `sequence_no`, `observed_at`, `dataset_id`, `modality`, `media_ref`, `features`, `target`, `split_hint`, `quality_flags`).
- **Idempotencia**: Clave natural definida por `dataset + activo + secuencia + señal`.

---

## 📁 Estructura del Proyecto

```text
├── .gitignore             # Exclusión de archivos crudos pesados y temporales
├── README.md              # Documentación general del proyecto
├── manifest.yaml          # Metadatos físicos, sensores y reglas de calidad
├── adapter.py             # Adaptador de ingesta C-MAPSS al esquema canónico
└── tests/
    └── test_adapter.py    # Suite de pruebas automatizadas (pytest)
```

---

## 🧪 Cómo Ejecutar las Pruebas

Para validar el adapter y comprobar las reglas de calidad de datos:

```bash
# Ejecutar directamente el adapter
py adapter.py

# Ejecutar las pruebas unitarias automatizadas
py -m pytest -v
```

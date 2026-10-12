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

## 🏛️ Buenas Prácticas de Arquitectura y Software Implementadas

Este proyecto aplica estándares de ingeniería de software de nivel de producción:
- **Arquitectura Hexagonal (Ports & Adapters)**:
  - Puerto de entrada: [`src/core/base_adapter.py`](src/core/base_adapter.py).
  - Adaptador concreto: [`src/adapters/cmapss/adapter.py`](src/adapters/cmapss/adapter.py).
  - Principio rector cumplido: *Agregar una nueva fuente de datos requiere solo un adapter y una configuración, sin modificar el resto de la plataforma*.
- **Contratos de Dominio con Pydantic**:
  - Modelos fuertemente tipados ([`CanonicalRecord`](src/core/contracts.py) y [`TelemetryRecord`](src/core/contracts.py)).
  - Validación de tipos y restricciones en tiempo de ejecución.
  - Clave natural de idempotencia: `dataset_id::asset_id::sequence_no::signal_key`.
- **Observabilidad con Logging Estructurado**:
  - Se sustituye el uso de `print()` por el módulo estándar `logging` con niveles de severidad (`INFO`, `WARNING`, `ERROR`).
- **Pruebas Automatizadas (TDD / Unit Testing)**:
  - Suite de pruebas con `pytest` en [`tests/test_adapter.py`](tests/test_adapter.py) que valida esquema, nulos, reglas de negocio y cardinalidad.
- **Integración Continua (CI/CD)**:
  - Pipeline de GitHub Actions en [`.github/workflows/ci.yml`](.github/workflows/ci.yml) para ejecutar tests y control de calidad en cada push.
- **Empaquetado Moderno**:
  - Configuración declarativa en [`pyproject.toml`](pyproject.toml) (PEP 621) y gestión de dependencias en `requirements.txt` / `requirements-dev.txt`.

---

## 📁 Estructura del Proyecto

```text
├── .github/
│   └── workflows/
│       └── ci.yml                     # Pipeline de CI (GitHub Actions)
├── src/
│   ├── core/
│   │   ├── base_adapter.py            # Interfaz abstracta (Puerto / Arquitectura Hexagonal)
│   │   └── contracts.py               # Modelos Pydantic (Esquema Canónico e Idempotencia)
│   └── adapters/
│       └── cmapss/
│           ├── adapter.py             # Implementación concreta C-MAPSS FD001
│           └── manifest.yaml          # Metadatos físicos de sensores y reglas
├── tests/
│   └── test_adapter.py                # Suite de pruebas automatizadas (pytest)
├── pyproject.toml                     # Configuración moderna del paquete (PEP 621)
├── requirements.txt                   # Dependencias de producción
├── requirements-dev.txt               # Dependencias de desarrollo y testing
└── README.md                          # Documentación del proyecto
```

---

## 🧪 Cómo Ejecutar las Pruebas

```bash
# 1. Ejecutar el adapter directamente
py src/adapters/cmapss/adapter.py

# 2. Ejecutar la suite completa de pruebas unitarias
py -m pytest -v
```

# Dashboard: vistas, reglas de diseño y estructura detallada

Capa BI sobre los dos libros de auditoría. **Los libros Excel son la fuente de verdad**; el ETL (Python) solo lee, normaliza, agrega y concilia; el HTML solo visualiza. Ninguna regla de auditoría vive en JavaScript.

```
Captura mensual de extractos (Gmail → Apps Script → Google Drive)
        ↓
Auditoría trimestral (libros Excel)  →  scripts/refresh_dashboard.py  →  data/*.json + data/dashboard_data.js  →  index.html
        ↓                                                                     ↓
Informes PDF trimestrales (deliverables/AAAA)                       Continuidad histórica → Auditoría anual
```

- 2025 = línea base (congelada, con copia y hash en `source/archive/2025_baseline/`).
- 2026 = auditoría trimestral recurrente (Q1–Q3 auditados el 6-oct-2026; Q4 se audita en enero de 2027).
- Años futuros = misma arquitectura: se agregan filas a los libros y una columna `Qn-AAAA` en las hojas `Historico_*`. No se toca código.

## Estructura de la carpeta

```
Financial Audit Dashboard/
├── index.html                      Aplicación (8 vistas, en español; rediseño v3 nov-2026)
├── css/styles.css                  Tema sobrio: un acento azul marino, grises; rojo solo para excepciones abiertas de riesgo alto y errores
├── js/                             data.js (motor SUMA/CONTEO) · names.js (nombres comerciales) · filters.js · charts.js · tables.js · app.js · vendor/Chart.js
├── data/                           GENERADO por el ETL — no editar
│   ├── metadata.json  credit_cards.json  bank_cash.json  exceptions.json  timeline.json
│   ├── continuity.json  product_utility.json  data_quality.json  treasury.json
│   └── dashboard_data.js           Todo lo anterior en un archivo (funciona con doble clic, sin servidor)
├── source/
│   ├── Sistema_Auditoria_TC.xlsx   Libro de tarjetas (multianual) — fuente de verdad
│   ├── Auditoria_Bancos.xlsx       Libro de bancos y efectivo (multianual) — fuente de verdad
│   └── archive/
│       ├── 2025_baseline/          Copias congeladas de ambos libros al cierre 2025 + MANIFEST_SHA256.txt
│       └── pass1_2026-10-06/       Libros tal como quedaron antes de la 2ª pasada de cierre Q1–Q3 2026
├── deliverables/AAAA/              Informes PDF trimestrales (el cronograma los detecta automáticamente)
├── validation/                     Validacion_AAAA-MM-DD (15 controles del sistema) y Validacion_Cierre_AAAA-MM-DD (cierre A–P)
├── continuity/                     CSV interinos de 2025 — REEMPLAZADOS por hojas del libro TC (se conservan como historia)
├── docs/audit_skill/              Metodología de la skill financial-account-audit (preflight, TC, bancos, conciliación/utilidad, excepciones, salidas/Notion)
├── work/<período>/                 GENERADO por audit_pipeline.py: preflight_<p>.md/json, audit_state.json, declarations.json (opcional)
├── scripts/
│   ├── refresh_dashboard.py        ETL v2 (multianual, por configuración)
│   ├── treasury_inputs.py          Insumos mensuales de tesorería: sync (agrega meses a Tesoreria_Input) y check
│   ├── build_quarterly_reports.py  Informes PDF trimestrales desde data/*.json
│   ├── audit_pipeline.py           Preflight GO/NO-GO, orden de fases, respaldo, verificación del dashboard (skill financial-account-audit)
│   ├── audit_sources.json          Registro de productos, ciclo de vida y rutas de evidencia (editar al abrir/cerrar/migrar un producto)
│   ├── tests/test_audit_pipeline.py Pruebas del preflight con fixtures temporales
│   ├── validate_system.py          Validación de 15 controles del sistema + cierre A–P (PASS / WARNING / ERROR)
│   ├── config.json                 Rutas, años, entregables, estados, materialidad, archivo baseline
│   ├── refresh_dashboard.bat       Doble clic: refresh
│   └── cierre_trimestral.bat       Refresh + PDF + refresh + validación (p. ej. `cierre_trimestral.bat 2026 4`)
├── PROCEDIMIENTO_TRIMESTRAL.md      Paso a paso de cada trimestre
├── ARQUITECTURA.md                  Decisiones de arquitectura multianual (v2)
└── ARCHITECTURE_2026.md             Evaluación previa (histórico; reemplazada por ARQUITECTURA.md)
```

## Uso

```
python scripts/refresh_dashboard.py          # o doble clic en scripts\refresh_dashboard.bat
```
Luego abra `index.html`. Requiere Python 3.9+ con `openpyxl` (y `reportlab` para los PDF).

**Importante:** después de editar un libro, ábralo en Excel y **guárdelo** antes del refresh (el ETL lee los valores calculados; un libro guardado sin recalcular produce advertencias `NO_CACHED_VALUE`).

## Vistas (v3, nov-2026)

Navegación lateral. Las vistas principales muestran pocas cifras, nombres comerciales de productos y nada de referencias a hojas; el detalle completo queda en secciones plegables. El Control de auditoría conserva toda la trazabilidad.

| Vista | Contenido |
|---|---|
| Tesorería | Vista inicial (Treasury Control Tower). Franja con el cierre y los parámetros; 5 KPIs (liquidez total, posición neta de caja, meses de cobertura vs reserva, utilización de cupo, costo bancario); liquidez por cuenta a fin de mes; liquidez vs deuda de tarjetas vs reserva objetivo por trimestre; costo bancario por trimestre; "Requiere atención"; rendimiento de la caja y caja ociosa; contraparte y seguro de depósitos; líneas de crédito por tarjeta. Plegables: todas las métricas por trimestre, tarjetas cerradas, insumos mensuales. Lee `Metricas_Tesoreria` sin recalcular |
| Resumen | Franja de estado (trimestres auditados, excepciones, conciliaciones, próximo cierre); 4 KPIs (consumo con tarjeta, costo neto de tarjetas, saldo de efectivo, rendimientos); consumo por trimestre vs año anterior y naturaleza del consumo; saldo de efectivo a fin de mes y flujos; valor neto por producto; "Requiere atención" (excepciones abiertas o en monitoreo, productos con valor neto negativo, consumo sin clasificar); panel lateral con estado de auditoría, excepciones, integridad y próximos cierres |
| Tarjetas de crédito | 5 KPIs; consumo por tarjeta; compras por categoría; tendencia trimestral; resumen por tarjeta y trimestre. Plegables: comparativo, extractos, beneficios, transacciones, excepciones de tarjetas |
| Bancos y efectivo | 5 KPIs; flujo mensual; saldo por cuenta; movimientos de capital interno; saldos al cierre. Plegables: comparativo, continuidad de saldos, transferencias internas, pagos de tarjetas, movimientos materiales, movimientos, excepciones de bancos |
| Productos | 4 KPIs; valor neto por producto (costos, beneficios, neto); composición de costos y beneficios; detalle por producto; Fiducuenta de pagos de tarjeta. Plegables: beneficio teórico vs real, estrategia de uso, detalle mensual de la fiducuenta, catálogo, detalle mensual |
| Control › Excepciones | Abiertas, en monitoreo, resueltas, hallazgos de años anteriores; una tabla del año con vistas (todas, abiertas, monitoreo, cerradas en la actualización, resueltas); hallazgos anteriores plegables |
| Control › Cronograma y continuidad | Cronograma por trimestre y módulo; continuidad por categoría; hallazgo anterior → excepción nueva. Plegables: detalle por período, controles trimestrales, matriz, reglas de contexto, ciclo de vida, calendario y marco de controles |
| Control › Calidad de datos | Estado del refresh; controles y conciliaciones; advertencias y errores; controles no PASS; cobertura de extractos. Plegables: todos los controles, conciliaciones, fuentes y registros, metodología y definiciones (incluye reglas de cálculo y definiciones de cada KPI) |

Nombres de productos: `js/names.js` traduce el nombre del libro (p. ej. "Bancolombia Visa (*6907)") al nombre comercial ("Visa Infinite") por los últimos 4 dígitos. Los libros y los JSON no cambian. Producto nuevo = una fila en `names.js`.

Período: selector de año y trimestre en la cabecera; los demás filtros en el panel "Filtros". Filtros: Año, Trimestre, Mes, Banco, Producto/cuenta, Tarjeta, Categoría, Tipo de flujo, Estado de excepción, Riesgo y Módulo. Las opciones salen de los datos. Los comparativos usan el mismo alcance del año anterior (p. ej. Q1–Q3 2026 vs Q1–Q3 2025).

## Reglas de diseño

* **Sin segunda lógica de auditoría.** Cada KPI se define en `metadata.metric_definitions` (copia declarativa de los SUMIFS del libro). JavaScript los aplica de forma genérica.
* **Conciliado en cada refresh.** 188 conciliaciones contra Historico_Trimestral, Resumen_Trimestral, Flujos_Economicos (2025), Historico_Trimestral_Bancos, Balance_Continuity, Resumen y Fiducuenta_TC vs Productos_Financieros.
* **Hallazgos históricos ≠ excepciones actuales.** `Año < current_audit_year` ⇒ hallazgo histórico; nunca cuenta en excepciones abiertas actuales. Si vuelve a fallar, se abre una excepción nueva con `Hallazgo relacionado`. Los IDs no se reutilizan (el siguiente ID se muestra en Resumen).
* **Estados normalizados** (Open / Monitor / Explained / No Action Required / Closed) según `config.json › status_normalization`, conservando el estado original. `Monitor` = sin acción correctiva, con seguimiento; no cuenta como abierta. La columna `Estado anterior` del registro central permite mostrar qué se cerró en cada actualización.
* **Sin extracto ≠ problema.** `Cobertura_Extractos` (libro TC) clasifica cada producto-mes: Con extracto · Sin actividad — no requiere extracto · Sin actividad observada · Producto migrado — extracto final no disponible · Producto cerrado · No abierto · Falta extracto — requerido. Solo la última es ERROR y genera excepción.
* **A prueba de fallos.** Si falta una hoja o columna requerida, el refresh se detiene, conserva los JSON anteriores y el dashboard muestra el error.
* **Solo lectura.** SHA-256 de cada libro antes y después del refresh.

## Compatibilidad con 2025

El ETL v2 también procesa los libros originales de 2025 (archivados) sin cambios: `python scripts/refresh_dashboard.py --check --tc source/archive/2025_baseline/Sistema_Auditoria_TC_2025_baseline.xlsx --bank source/archive/2025_baseline/Auditoria_Bancos_2025_baseline.xlsx` → 77 conciliaciones OK.

## Tesorería (Treasury Control Tower)

* **Tesoreria_Input** (libro TC): una fila por mes con saldos de fin de mes (*9910 y fiducuentas), gasto externo, GMF, intereses, rendimientos netos, retención y rentabilidad E.A. informada. Valores azules copiados de `Auditoria_Bancos.xlsx` por `scripts/treasury_inputs.py`; el ETL los concilia celda a celda en cada refresh (categoría "Tesorería (insumos)").
* **Metricas_Tesoreria** (libro TC): matriz Clave × `Qn-AAAA` con fórmulas sobre Tesoreria_Input, Extractos_Input, Historico_Trimestral, Maestro_Productos y los parámetros `T_*` de Parametros (filas 30–35); debajo, la tabla "Líneas de crédito". El dashboard lee los valores calculados por la columna Clave.
* Supuestos editables: reserva objetivo (meses de gasto), saldo operativo de ahorros, tasa de ahorros, tope del seguro de depósitos Fogafín (por persona y entidad) y tasa de referencia (opcional). Los valores viven en la hoja Parametros del libro, no en el código.
* El costo de oportunidad de la caja ociosa es una estimación con metodología propuesta; no es un costo contable.

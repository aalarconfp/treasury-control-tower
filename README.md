# Financial Account Audit Dashboard

Sistema de auditoría trimestral de cuentas financieras personales (tarjetas de crédito, cuentas de ahorro, fiducuentas y efectivo). Los libros Excel de auditoría son la fuente de verdad; un ETL en Python los lee en modo solo lectura, los concilia y genera los datos de un dashboard HTML estático y los informes PDF trimestrales.

> Este repositorio contiene **solo código y documentación**. Los libros, extractos, datos generados, informes y el registro de productos viven fuera del control de versiones y están excluidos por `.gitignore`.

## Problema que resuelve

Con muchas tarjetas, cuentas y emisores, es fácil que falte un extracto, que una comisión pase sin revisar o que se cierre un trimestre con cifras que no cuadran. El sistema:

- verifica antes de auditar que toda la evidencia del período exista (*preflight* GO / NO-GO por producto y mes);
- impone el orden de las fases y bloquea el cierre si algo falla;
- concilia en cada refresh (188 conciliaciones) contra los resúmenes de los propios libros;
- separa hallazgos históricos de excepciones actuales y controla su continuidad entre años;
- publica un dashboard de 7 vistas y los informes PDF trimestrales a partir de los mismos datos.

## Arquitectura (resumen)

```
Extractos (Gmail → Apps Script → Drive) + Money Pro + Splitwise
        │
        ▼
audit_pipeline.py  preflight GO / NO-GO ─► fases P7–P18 en orden
        │
        ▼
Libros Excel (fuente de verdad) ─► refresh_dashboard.py (ETL, solo lectura, SHA-256)
                                          │
                     data/*.json + dashboard_data.js ─► index.html (7 vistas)
                                          │
                build_quarterly_reports.py (PDF) ─► validate_system.py (15 controles + cierre A–P)
```

Regla central: **ninguna regla de auditoría vive en JavaScript**. Excel clasifica y decide; el ETL lee, agrega y concilia; el HTML solo visualiza. Detalle en [`ARQUITECTURA.md`](ARQUITECTURA.md) y [`docs/dashboard.md`](docs/dashboard.md).

## Tecnología

Python ≥ 3.9 (probado con 3.14) · `openpyxl` · `reportlab` · `pypdf` (o `pdftotext` de Poppler) · HTML/CSS/JS sin framework ni build · [Chart.js](https://www.chartjs.org/) 4.4.4 incluido en `js/vendor/` (licencia MIT). Ver [`requirements.txt`](requirements.txt).

## Estructura

```
├── README.md · requirements.txt · .gitignore · .gitattributes
├── index.html · css/ · js/          dashboard estático (abre con doble clic, sin servidor)
├── scripts/
│   ├── audit_pipeline.py            preflight GO/NO-GO, orden de fases, respaldo, control de excepciones
│   ├── refresh_dashboard.py         ETL multianual: libros → data/*.json
│   ├── build_quarterly_reports.py   informes PDF trimestrales
│   ├── validate_system.py           validación del sistema y del cierre
│   ├── config.json                  rutas, años, materialidad, estados
│   ├── repo_safety_check.py         control previo a cada commit
│   ├── *.bat                        atajos para Windows
│   └── tests/test_audit_pipeline.py
├── examples/audit_sources.example.json   registro de productos sanitizado
├── docs/                            dashboard y metodología de auditoría (docs/audit_skill/)
├── PROCEDIMIENTO_TRIMESTRAL.md      paso a paso de cada trimestre
└── ARQUITECTURA.md                  decisiones de la arquitectura multianual
```

Carpetas locales no versionadas: `source/` (libros Excel), `data/` (salida del ETL), `deliverables/` (PDF), `validation/`, `work/<período>/`, `continuity/`, `archive/` y `scripts/audit_sources.json` (registro real de productos).

## Uso

```
pip install -r requirements.txt
copy examples\audit_sources.example.json scripts\audit_sources.json   # y adaptarlo a sus productos
python scripts/audit_pipeline.py preflight --period 2026Q4
python scripts/refresh_dashboard.py
```

Luego abra `index.html`. El cierre completo (refresh + PDF + validación) es `scripts\cierre_trimestral.bat 2026 4`. Los extractos PDF protegidos se leen con la contraseña en la variable de entorno `AUDIT_PDF_PASSWORD`, solo durante la sesión; nunca se guarda.

Después de editar un libro, ábralo en Excel y **guárdelo** antes del refresh: el ETL lee los valores calculados.

## Workflow trimestral

1. Mensual: solo captura y archivo de extractos (no hay auditoría mensual).
2. Exportar Money Pro, Splitwise y, si aplica, Puntos Colombia.
3. Preflight → con GO, actualizar los libros (fases P7–P14).
4. Refresh del dashboard → informes PDF → validación del cierre.

Paso a paso en [`PROCEDIMIENTO_TRIMESTRAL.md`](PROCEDIMIENTO_TRIMESTRAL.md).

## Testing

```
python scripts/tests/test_audit_pipeline.py
```

16 escenarios del preflight (GO, NO-GO por extracto o fuente faltante, PDF protegido, migración de producto, auditoría anual, orden de fases, hallazgos históricos). Usan fixtures temporales y el registro sanitizado de `examples/`: no necesitan datos privados, red ni Notion.

Antes de cada commit:

```
python scripts/repo_safety_check.py
```

## Seguridad

- `.gitignore` en modo *allowlist*: solo se versiona lo que está listado; cualquier archivo nuevo queda fuera por defecto.
- Nunca se versionan Excel, CSV, PDF, Word, imágenes, comprimidos ni JSON con resultados.
- El ETL abre los libros en solo lectura y verifica su SHA-256 antes y después de cada refresh.
- Sin credenciales en el código; la contraseña de los PDF solo vive en una variable de entorno de la sesión.
- Los productos se identifican por los últimos 4 dígitos (`*1234`), nunca por el número completo.

## Estado actual

- Auditoría 2025 (línea base congelada) y Q1–Q3 2026: cerradas. Q4 2026 se audita en enero de 2027.
- Preflight, ETL, dashboard v3, informes PDF y validación: operativos.
- El ETL está adaptado a la estructura de hojas de los libros del autor; reutilizarlo con otros libros requiere ajustar `config.json`, el registro de productos y `js/names.js`.

## Roadmap

- Conjunto de datos de demostración sintético para ver el dashboard sin datos reales.
- CI (GitHub Actions) con las pruebas, el control de seguridad y escaneo de secretos.
- Pruebas del ETL con libros sintéticos.

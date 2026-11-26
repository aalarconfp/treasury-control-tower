---
name: financial-account-audit
description: Ejecuta el cierre trimestral o anual de Financial Account Audit (tarjetas de crédito + bancos y efectivo) con preflight GO/NO-GO de extractos, Money Pro, Splitwise y Datacrédito, actualización de los dos libros Excel, informes PDF separados, refresh del dashboard HTML y Review en Notion. Usar con "Ejecuta Financial Account Audit para Q4 2026", "auditoría anual 2026" o similar.
---

# Financial Account Audit — cierre trimestral y anual

Orquesta el sistema existente; **no lo reconstruye**. Fuente de verdad: los libros Excel y la evidencia documental. El dashboard visualiza. Notion guarda el resumen ejecutivo, el seguimiento y las decisiones.

**Validar antes de analizar · Conciliar antes de concluir · Actualizar antes de reportar · Verificar antes de cerrar · Notion al final.**

## 0. Ubicación y componentes (una sola fuente por responsabilidad)
Raíz del proyecto (PC del usuario): `<FINANCE_DATA_ROOT>\Informacion Bancaria\Financial Audit Dashboard\`, donde `<FINANCE_DATA_ROOT>` es la carpeta de finanzas personales en Google Drive. Evidencia: carpeta padre `Informacion Bancaria\` (`evidence_root` en `scripts\audit_sources.json`).

| Responsabilidad | Componente |
|---|---|
| Preflight GO/NO-GO, orden de fases, respaldo, verificación del dashboard, control de excepciones históricas | `scripts\audit_pipeline.py` + registro `scripts\audit_sources.json` (productos, ciclo de vida, rutas, fuentes) |
| Pruebas del preflight y de los bloqueos | `scripts\tests\test_audit_pipeline.py` (fixtures temporales; nunca datos reales) |
| Tarjetas (consumo, costos, beneficios, pagos, excepciones TC) | `source\Sistema_Auditoria_TC.xlsx` — incluye el **registro central** `Excepciones_Central` |
| Bancos, ahorros, fiducuentas, efectivo, transferencias, rendimientos | `source\Auditoria_Bancos.xlsx` |
| ETL → dashboard | `scripts\refresh_dashboard.py` (config `scripts\config.json`) → `data\*.json`, `data\dashboard_data.js` → `index.html` |
| Informes PDF | `scripts\build_quarterly_reports.py` → `deliverables\<AAAA>\` |
| Validación del sistema y de cierre | `scripts\validate_system.py` → `validation\` |
| Procedimiento humano | `PROCEDIMIENTO_TRIMESTRAL.md`, `README.md`, `ARQUITECTURA.md` |
| Metodología detallada (leer en cada ejecución) | `docs\audit_skill\` — `evidence_requirements.md` · `credit_card_audit.md` · `bank_cash_audit.md` · `reconciliation_and_utility.md` · `exception_management.md` · `outputs_dashboard_notion.md` |

Los dos libros **no se combinan** ni se crean libros por trimestre. Si un componente no está donde dice esta tabla, inspeccionar con `device_list_dir` y usar la ruta real; no crear duplicados.

## 1. Entorno
- **Cowork (habitual):** pedir acceso a `<FINANCE_DATA_ROOT>\Informacion Bancaria` si no está conectada (`device_request_folder_access`). `device_list_dir` recursivo; `device_stage_files` de `Financial Audit Dashboard\scripts\*`, `docs\audit_skill\*`, los dos libros, y la evidencia del período (y de los meses ya cerrados del mismo año). Ejecutar los scripts en la copia preparada (`/mnt/user-data/uploads/Informacion Bancaria/...`). Devolver resultados con `device_commit_files` (con `expectedMtimeMs` para los libros).
- **PC:** `cd "…\Financial Audit Dashboard"` y `python scripts\audit_pipeline.py …`.
- **Contraseña de los PDF** (la que exige el emisor): solo en memoria, variable de entorno `AUDIT_PDF_PASSWORD`. Si no se conoce en la sesión, pedirla. Nunca escribirla en archivos, logs, JSON, Notion ni mensajes.
- Leer los módulos de `docs\audit_skill\` antes de la fase que los usa.

## 2. Tipo de auditoría y período (P0)
- "Q4 2026", "2026Q4", "cuarto trimestre 2026" ⇒ **trimestral** (`--period 2026Q4`). "Anual 2026", "cierre del año 2026" ⇒ **anual** (`--period 2026`).
- **No existen auditorías mensuales independientes.** El proceso mensual es solo captura y archivo de extractos (Gmail → Apps Script → Drive). Si piden "auditoría de octubre", explicar que se audita en el cierre trimestral y ofrecer solo un preflight informativo del trimestre en curso.
- Calendario: Q1 en abril, Q2 en julio, Q3 en octubre, Q4 en enero del año siguiente (`config.json › schedule`). La anual se ejecuta después del cierre Q4.
- Nada está fijo en un año: el período sale de la solicitud; productos y rutas, de `audit_sources.json`.

## 3. Orden obligatorio de fases (no alterar)
| Fase | Qué | Cómo |
|---|---|---|
| P0–P6 | Período, estructura, extractos, Money Pro, Splitwise, Datacrédito y condicionales, **GO / NO-GO** | `python scripts/audit_pipeline.py preflight --period <p>` → `work\<p>\preflight_<p>.md/json`, `audit_state.json`. Mostrar el resultado al usuario. Módulo: `evidence_requirements.md` |
| P7 | Auditoría de tarjetas | `credit_card_audit.md` |
| P8 | Auditoría de bancos y efectivo | `bank_cash_audit.md` |
| P9 | Conciliación cruzada | `reconciliation_and_utility.md` |
| P10 | Utilidad de productos y controles históricos (Puntos Colombia / Primax) | `reconciliation_and_utility.md` |
| P11 | Excepciones y continuidad | `exception_management.md` |
| P12 | Actualizar los dos workbooks (respaldo + hash antes; integridad después) | `audit_pipeline.py backup`; `outputs_dashboard_notion.md` |
| P13 | Validación de datos | `refresh_dashboard.py --check`, `validate_system.py` |
| P14 | Informes separados TC y Bancos | `build_quarterly_reports.py` |
| P15 | Refresh y validación del dashboard | `refresh_dashboard.py` → `audit_pipeline.py verify-dashboard` + `check-exceptions` + revisión en navegador |
| P16 | Reporte ejecutivo para Notion | plantilla en `outputs_dashboard_notion.md` |
| P17 | Notion: deduplicación, escritura, verificación | idem |
| P18 | Informe final de ejecución | idem |

Cada fase P7–P18: `python scripts/audit_pipeline.py phase --period <p> --start Pn` (el script **rechaza** fases fuera de orden, sin GO, después de un bloqueo, o Notion sin P15 OK) y al terminar `--done Pn --result PASS|WARNING|BLOCKED --note "<resumen>"`. `status` muestra el tablero. No marcar una fase como hecha sin haberla hecho.

## 4. Reglas de detención (BLOCKER)
Detener la ejecución completa si: faltan extractos necesarios (clase C) · archivos dañados/ilegibles (B) · cobertura de un producto activo no determinable (F) · falta Money Pro · falta Splitwise para la conciliación requerida · falta otra fuente crítica sin alternativa suficiente · discrepancias estructurales en los datos · identidad o período de un libro no verificable (hash distinto al del preflight sin explicación) · el ETL no actualiza · las métricas principales no concilian · no se puede verificar la integridad de las actualizaciones.

Al detenerse entregar exactamente: (1) fase de detención, (2) motivo, (3) archivos/fuentes faltantes con la ruta esperada, (4) productos y períodos afectados, (5) qué debe hacer el usuario, (6) qué **no** se ejecutó (análisis, libros, informes, dashboard, Notion), (7) cómo reanudar (volver a correr el preflight del mismo período). No continuar, no estimar, no escribir el reporte de cierre en Notion. "WARNING" nunca justifica saltarse un requisito obligatorio.

## 5. Severidades
- **BLOCKER:** impide una auditoría fiable del período o del módulo ⇒ NO-GO.
- **WARNING:** limita una conclusión concreta (p. ej. Datacrédito faltante para confirmar una migración ⇒ esa conclusión queda PENDIENTE; equivalencia Primax pendiente ⇒ redenciones ESTIMADAS; producto sin canal de extracto ⇒ costo no verificable). Se documenta en el informe y en la conclusión afectada.
- **INFO:** sin efecto material.
- **Ejecución parcial:** solo con `--partial-scope tc|bank` cuando los bloqueos no afectan a ese módulo (p. ej. falta Splitwise ⇒ se puede auditar bancos). Todo queda etiquetado **PARCIAL**; no hay informe consolidado completo ni Review de cierre en Notion.

## 6. Reglas permanentes
1. No inventar datos, saldos, tasas, beneficios, puntos, fechas ni clasificaciones; lo no verificable es "Sin evidencia" / "No determinado" / "Pending validation".
2. "Sin extracto ≠ problema": producto sin actividad (D), cerrado o migrado con evidencia (E) o no abierto (N) no genera falso positivo. Pero una **migración no es un cierre**: el nuevo emisor debe emitir extracto.
3. Taxonomía bancaria: transferencia interna ≠ ingreso; capital entre cuentas propias ≠ gasto; rendimiento de fiducuenta = ingreso financiero; pago de tarjeta ≠ gasto económico; capital familiar administrado = de terceros.
4. Excepciones: registro central único; IDs nunca reutilizados; históricos resueltos no se reabren (excepción nueva vinculada); no cerrar sin evidencia ni mantener abierta sin motivo; `Estado anterior` + `Evidencia nueva` + `Conclusión de auditoría` en cada cambio.
5. 2025 (y todo año cerrado) permanece congelado salvo corrección histórica autorizada explícitamente.
6. No duplicar lógica de auditoría en JavaScript; el dashboard solo muestra lo que el ETL lee del Excel.
7. Evidencia que llega después de un cierre (detectada por el preflight) obliga a reevaluar la conclusión afectada en el siguiente cierre, con trazabilidad.
8. No recomendar cancelar productos automáticamente: presentar costo, uso y beneficio real.
9. Costo de oportunidad: no se calcula sin metodología aprobada.

## 7. Auditoría anual
`--period <AAAA>`. Preflight anual: 12 meses de cobertura, los **cuatro cierres trimestrales** (estado COMPLETED en `work\<AAAA>Qn\` o, para trimestres anteriores a esta skill, PDFs trimestrales emitidos), Datacrédito posterior al 31-dic (obligatorio: inventario de productos abiertos/cerrados), reporte anual de costos Bancolombia (WARNING si falta). La anual **consolida y no sustituye** los trimestres: no se rehacen cruces ya documentados; se revisan continuidad anual de saldos, excepciones del año (abiertas, cerradas, carry-forward a la matriz de continuidad del año siguiente con columnas `<AAAA>_Status/<AAAA>_Linked_Exception`), hallazgos materiales, utilidad anual por producto y costos del emisor. Salidas: `Informe_Auditoria_TC_<AAAA>.pdf`, `Informe_Auditoria_Bancos_<AAAA>.pdf`, Review anual en Notion. Al cerrar el año: copiar ambos libros a `source\archive\<AAAA>_baseline\` con SHA-256, registrarlo en `config.json › archive` y cambiar `current_audit_year`.

## 8. Notion (resumen; detalle en `outputs_dashboard_notion.md`)
Personal Operating System › Reviews. Nombre `Qn AAAA Financial Account Audit Review` (Quarterly; Date = rango del trimestre) a partir de la plantilla "Financial Account Audit Review". Buscar antes de escribir y **actualizar** la del período si existe (Planned o Completed); nunca duplicar. Proyecto canónico: "Bank Statement AI Audit". Decisions solo con decisiones explícitas; Ideas con Status Inbox. Escribir solo con autorización explícita del usuario para ese período (o autorización permanente registrada), con P15 en PASS/WARNING y ejecución no parcial. Releer cada página después de escribir. Si no existe el siguiente período como Planned, crearlo una vez.

## 9. Salida final (P18)
A período · B preflight · C fuentes verificadas · D archivos incorporados · E tarjetas · F bancos · G conciliaciones cruzadas · H excepciones nuevas/cerradas/pendientes · I libros (hash antes/después, respaldo) · J informes · K dashboard · L Notion · M controles PASS/WARNING/ERROR · N limitaciones · O próximo período — separando fases completadas, pendientes y bloqueadas, y cambios aplicados y no aplicados.

## 10. Mantenimiento
- Producto nuevo, cerrado o migrado ⇒ editar `scripts\audit_sources.json` (segmento con `from`/`to`, adaptador y `event` con fecha y evidencia) y correr `python scripts\tests\test_audit_pipeline.py` (debe dar todo PASS).
- Cambios al código de producción solo si son necesarios, con compatibilidad y documentados en `ARQUITECTURA.md`.

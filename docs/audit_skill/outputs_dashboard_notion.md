# Fases F–I — Libros, validación, informes, dashboard y Notion (P12–P18)

## P12 — Actualizar los dos workbooks
Antes:
1. Verificar identidad: ruta `source\Sistema_Auditoria_TC.xlsx` / `source\Auditoria_Bancos.xlsx`, hojas esperadas, SHA-256 = el del preflight (`workbooks[].sha256`). Si el libro cambió desde el preflight (el usuario lo guardó), volver a prepararlo y comparar; nunca editar una copia vieja.
2. Respaldo: `python scripts\audit_pipeline.py backup --period <p>` → `source\archive\pre_<p>_<fecha>\` con `MANIFEST_SHA256.txt`.
3. Identificar las tablas/rangos a modificar; no tocar filas de otros períodos ni las hojas 2025.
En Cowork: editar con openpyxl sobre la copia preparada; recalcular con `python3 /mnt/skills/public/xlsx/scripts/recalc.py <libro> 240` (el ETL lee valores calculados); confirmar 0 errores de fórmula. Si el archivo está abierto en Excel (`saveBackBlocked`), pedir cerrarlo antes de escribir. Escribir con `device_commit_files` y `expectedMtimeMs` del staging.
Después: fórmulas sin error, recálculo hecho, tablas extendidas (BaseTx, PF_Catalogo, PF_Tabla), IDs únicos, continuidad de saldos, y **2025 intacto** (filas de Base_Movimientos 2025 y hojas 2025 sin cambios; `validate_system.py` lo comprueba contra el baseline con SHA-256). El usuario debe abrir y guardar ambos libros en Excel antes del siguiente refresh si se recalcularon fuera de Excel.

## P13 — Validación de datos
`python scripts\refresh_dashboard.py --check` (0 errores, conciliaciones Excel vs ETL sin fallas) y `python scripts\validate_system.py --browser-results validation\browser_checks.json` → `validation\Validacion_<fecha>.md` (15 controles) y `validation\Validacion_Cierre_<fecha>.md` (A–P: extractos, pagos, saldos, intereses, beneficios, costos, excepciones cerradas, nuevas, inactivos, cerrados/migrados, Fiducuenta TC, utilidad, dashboard, filtros, ETL, 2025 intacto). Cualquier ERROR ⇒ P13 BLOCKED. Las métricas principales que no concilian ⇒ BLOCKED.

## P14 — Informes separados
`python scripts\build_quarterly_reports.py --year <AAAA> --quarter <n>` → `deliverables\<AAAA>\Auditoria_Trimestral_TC_Q<n>_<AAAA>.pdf` y `Auditoria_Trimestral_Bancos_Q<n>_<AAAA>.pdf` (resumen ejecutivo, período, cobertura, indicadores, conciliaciones, hallazgos, excepciones con estado antes → ahora, acciones, limitaciones, controles). Nunca un informe único operativo. Un PDF ya emitido no se sobrescribe sin conservar la versión anterior (`_v<n>` o archivo previo en `archive`). Anual: `Informe_Auditoria_TC_<AAAA>.pdf` e `Informe_Auditoria_Bancos_<AAAA>.pdf` (nombres en `config.json › deliverables`). No se emite informe definitivo con P13 BLOCKED.

## P15 — Dashboard
Arquitectura fija: Excel → `scripts\refresh_dashboard.py` → `data\*.json` + `data\dashboard_data.js` → `index.html`. Sin lógica de auditoría en JavaScript. Ejecutar el refresh **después** de P12/P13, luego `python scripts\audit_pipeline.py verify-dashboard --period <p>` (refresh OK, 0 conciliaciones fallidas, DQ sin ERROR, período presente en TC y Bancos, refresh posterior al preflight). Revisar en el navegador (Playwright/Chromium en Cowork; `validation\browser_checks.json`): 8 pestañas sin errores, filtros, y que los años anteriores sigan presentes. Si falla ⇒ P15 BLOCKED: la auditoría **no** está terminada y Notion no se escribe.

## P16 — Reporte ejecutivo para Notion
Breve (lectura de 2–3 min), en **inglés** (idioma del POS), con la plantilla de la review: header (Period · Report type · Close date · Sources · Project) · 1 Executive Summary · 2 Scope · 3 Key Findings (Resolved / Requires follow-up / Pending evidence / Real financial risk) · 4 Key Metrics (solo cifras conciliadas del período, con fuente) · 5 Decisions Required ("No material decisions required at this stage." si no hay) · 6 Next Actions (máx. 5: acción, motivo, prioridad, estado, fecha solo si se justifica) · 7 System Status · Conclusion. Sin tablas de transacciones. Si una excepción cambió después de emitir el PDF, usar el estado vigente del libro y decirlo.

## P17 — Notion (Personal Operating System)
Principio: **"Reviews generate. Other databases store."** Flujo: auditoría validada → reporte ejecutivo → Review → Projects / Decisions / Ideas solo si corresponde.
- **Reviews** `collection://3ba6815d-f0f7-80e7-bfd5-000be5f4cdcd` (Name, Date, Frequency, Status Planned/Completed/Superseded, Description). Convención: `Qn AAAA Financial Account Audit Review` (anual: `AAAA Financial Account Audit — Annual Review`), Frequency Quarterly/Annual, Date = rango del período, icono 🧾. Plantilla: página "Financial Account Audit Review" (TEMPLATE) en Reviews. Q3 2026 Completed; Q4 2026 creada como Planned (oct–dic).
- **Projects** `collection://3ba6815d-f0f7-80cd-ab42-000bb5e2a841` — proyecto canónico "Bank Statement AI Audit" (Done; se le agregan actualizaciones, no se crea otro).
- **Decisions** `collection://3ba6815d-f0f7-800d-992f-000bbbc201eb` (solo decisiones explícitas del usuario; Status Accepted). **Ideas** `collection://3ba6815d-f0f7-801d-b19d-000bcfeea048` (Status Inbox).
- Si los IDs cambiaron, localizar por nombre con notion-search.

Deduplicación (antes de escribir): consultar Reviews por `Name LIKE '%Financial Account Audit%'` y por rango de fecha del período; títulos alternativos ("Financial Account Audit — Qn AAAA", "Auditoría … Qn"). Excluir la plantilla (Description empieza con "TEMPLATE", sin Date ni Status). Si existe la del período (Planned o Completed) ⇒ **actualizarla** (contenido y Status), nunca crear otra; si hay más de un candidato ⇒ detenerse y preguntar. Para Projects/Decisions/Ideas: buscar equivalentes por título y contenido; actualizar el canónico en vez de duplicar.

Autorización (procedimiento vigente del POS): escribir en Notion solo si la solicitud del período lo autoriza explícitamente (p. ej. "…y actualiza Notion") o existe una autorización permanente registrada por el usuario. Sin autorización: entregar el reporte y la clasificación, y pedir confirmación. Nunca con P15 BLOCKED ni con ejecución PARCIAL.

Después de escribir: volver a leer cada página tocada y confirmar propiedades y contenido; solo entonces `phase --done P17 --result PASS`. Status = Completed solo cuando todo quedó guardado. Si el período siguiente no existe como Planned, crearlo (una sola vez) con Date = rango del siguiente trimestre.

## P18 — Informe final de ejecución (respuesta al usuario)
A período · B preflight (GO/NO-GO, PARCIAL) · C fuentes verificadas · D archivos incorporados · E estado TC · F estado bancos · G conciliaciones cruzadas · H excepciones nuevas / cerradas / pendientes · I libros (hashes antes/después, respaldo) · J informes · K dashboard · L Notion (escrito/verificado o no y por qué) · M controles PASS/WARNING/ERROR · N limitaciones · O próximo período. Separar: fases completadas / pendientes / bloqueadas · cambios aplicados / no aplicados. Nunca declarar "completa" si falta una fase obligatoria.

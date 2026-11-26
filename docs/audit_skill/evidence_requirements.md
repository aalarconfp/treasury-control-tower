# Evidencia y preflight (fases P1–P6)

Motor: `scripts\audit_pipeline.py preflight` + registro `scripts\audit_sources.json`. El script **decide**; Claude no reinterpreta un NO-GO.

## Rutas reales (PC del usuario)
| Componente | Ruta |
|---|---|
| Raíz de evidencia | `<FINANCE_DATA_ROOT>\Informacion Bancaria\` (carpeta de finanzas personales en Google Drive) |
| Proyecto / dashboard | `…\Informacion Bancaria\Financial Audit Dashboard\` (`index.html`, `css\`, `js\`, `data\`, `scripts\`, `source\`, `deliverables\<AAAA>\`, `validation\`, `continuity\`, `work\<período>\`) |
| Configuración ETL | `scripts\config.json` (no está en la raíz) |
| Libros (fuente de verdad) | `source\Sistema_Auditoria_TC.xlsx` · `source\Auditoria_Bancos.xlsx` · baseline 2025 congelado en `source\archive\2025_baseline\` |
| TC Bancolombia (*6907, *7744, *7935, *8457) | `Tarjetas de Credito\Bancolombia\<AAAA>\Documento_<AAAAMM>_*.zip` → `{tarjeta}_{MES}{AAAA}.xlsx` (hojas PESOS y DOLARES) |
| TC Occidente *7547 | `Tarjetas de Credito\Banco de Occidente\<AAAA>\ExtractosUnificados<AAAAMMDD>.pdf` (fecha de emisión ≈ mes siguiente al corte; el de diciembre está en la carpeta del año siguiente) |
| TC *5933 | Itaú hasta jul-2026: `Tarjetas de Credito\Banco Itau\<AAAA>\*.pdf` (multiextracto; período en "Periodo de facturación") · Banco de Bogotá desde ago-2026: `Tarjetas de Credito\Banco de Bogota\MM_AAAA_*.pdf` |
| RappiCard | `Tarjetas de Credito\RappiPay\File_000*.pdf` (período en "Desde … Hasta …"; el emisor solo emite con actividad) |
| Ahorros *9910 | `Cuentas Bancarias\Cuenta de Ahorros\Extracto_<AAAAMM>_Cuentas_de ahorro_9910.xlsx` (trimestral, mes de cierre) |
| Fiducuentas | `Cuentas Bancarias\Fiducuentas\<AAAA>\Documento_<AAAAMM>_*.zip` → `{cuenta13}_{MES}{AAAA}.xlsx` (detalle por cuenta, desde mar-2026); antes `Extracto_<AAAAMM>_Fiducuenta_6191.xlsx`; `Extracto_<AAAAMM>_Tapa_Resumen_4120.xlsx` es solo resumen |
| Money Pro | `Money Pro Transactions - <período>.csv` en la raíz (`;`, fecha M/D/AAAA, columnas Date…Agent) |
| Splitwise | `SplitWise\*_<AAAA-MM-DD>_export*.csv` (fecha de export en el nombre) |
| Datacrédito | `DataCredito\Reporte DataCredito M-D-AA.pdf` (imagen; se lee visualmente) |
| Puntos Colombia | `Puntos Colombia\Puntos Colombia *.xlsx` (portal limita a 250 filas) · auditoría Primax `Puntos Colombia\Auditoria Primax 2024-2026\` |
| Beneficios | `Tarjetas de Credito\Beneficios\*.docx|pdf` |
| Costos anuales Bancolombia | `Cuentas Bancarias\Reportes Costos\Reporte_<AAAA>12_AnualCostosBancolombia_4120.xlsx` |
| Captura mensual | Gmail → Google Apps Script (`Tarjetas de Credito\Bank Statement Intake.gscript`) → Drive. **No hay auditoría mensual.** |

No existe un manifiesto de extractos: el preflight genera uno por período (`work\<período>\preflight_<período>.json|md`).

## Ejecución
- **En el PC:** `set AUDIT_PDF_PASSWORD=<clave>` (solo la sesión) y `python scripts\audit_pipeline.py preflight --period 2026Q4`.
- **En Cowork:** (1) `device_list_dir` recursivo de `Informacion Bancaria`; (2) `device_stage_files` de los archivos del período (y de los meses ya cerrados del mismo año para detectar evidencia tardía) + `Financial Audit Dashboard\scripts\*` + los dos libros; (3) `python3 scripts/audit_pipeline.py preflight --period <p> --evidence-root "/mnt/user-data/uploads/Informacion Bancaria" --dashboard-root <copia>`. Los PDF se abren con la contraseña que exige el emisor **solo en memoria**: obtenerla en la sesión (si no se conoce, pedirla), pasarla por variable de entorno, **nunca** escribirla en archivos, logs, Notion ni mensajes.

## Clases de cobertura (por producto × mes)
| Clase | Significado | Severidad |
|---|---|---|
| A | Localizado y legible | INFO |
| B | Localizado pero ilegible/incompleto (zip dañado, PDF sin contraseña) | **BLOCKER** |
| C | No localizado y requerido (producto activo) | **BLOCKER** |
| D | Sin actividad, no requiere extracto (regla automática con saldos 0 antes y después, o declaración del usuario **con evidencia** en `work\<p>\declarations.json`) | INFO |
| D_OBS | Sin actividad observada y sin canal de extracto (NuBank *3910, Falabella *7874): costo no verificable | WARNING |
| E | Cerrado o migrado según el ciclo de vida con evidencia | INFO |
| F | Estado no determinable (sin segmento de ciclo de vida, declaración sin evidencia) | **BLOCKER** |
| N | No abierto en el mes | INFO |

D, D_OBS, E y F **no son equivalentes**. Una migración (*5933 Itaú → Banco de Bogotá) **no** es un cierre: el producto sigue activo y exige extracto del nuevo emisor.

`declarations.json` (opcional, lo llena el usuario): `[{"product":"TC-RAPPI","month":"2026-11","class":"D","evidence":"app RappiPay: sin movimientos, saldo 0"}]`. Una declaración sin evidencia se convierte en F.

## Fuentes y requisito
| Fuente | Requisito | Si falta |
|---|---|---|
| Extractos de productos activos | Obligatoria | NO-GO (P2) |
| Money Pro (cubre el período hasta ≤5 días del cierre, columnas completas) | Obligatoria | NO-GO (P3) |
| Splitwise (export con fecha ≥ fin del período) | Obligatoria para gastos compartidos/CxC | NO-GO (P4). Solo con `--partial-scope bank` se permite el módulo bancos, etiquetado PARCIAL, sin consolidado ni Notion de cierre |
| Datacrédito | Condicional: cierre/migración en el período; **obligatoria en la anual** | Conclusión del producto PENDIENTE (WARNING acotado); anual: NO-GO |
| Puntos Colombia | Condicional | Beneficio de puntos "Sin evidencia"; export de 250 filas → posible truncamiento (WARNING) |
| Control Primax (`Control_Equivalencias`) | Control histórico | Equivalencia "Pendiente" ⇒ redenciones Primax ESTIMADAS; **no** cambiar `Parametros!B19` |
| Beneficios del usuario | Condicional | Usar fuentes oficiales con fecha de verificación |
| Reporte anual de costos | Anual | WARNING |

## Reglas metodológicas de las fuentes
- Money Pro registra **solo la parte personal** de gastos compartidos; `Wallet` agrupa varias tarjetas y cuentas. La falta de coincidencia exacta no es por sí misma una diferencia.
- Compras familiares y gastos de terceros se tratan aparte (Splitwise = aproximación agregada por período; no exigir cruce uno a uno).
- Rendimientos de fiducuentas ≠ transferencias de capital. Pagos de tarjeta ≠ gasto económico.
- Capital familiar administrado (consignación 61M jun-2026, fiducuenta *0452) **no es producto propio** (respuesta del usuario a EX-43/44/45).

## Evidencia tardía
El preflight revisa también los meses ya cerrados del mismo año: extractos que el libro no cita en `Extractos_Input › Archivo` y huecos de cobertura que siguen abiertos. Son WARNING del período actual, pero **obligan a reevaluar** la conclusión del producto en el cierre anterior (nueva excepción vinculada si cambia la conclusión). Ejemplo: el extracto de septiembre de una tarjeta migrada a un nuevo emisor llega después del cierre Q3 y muestra saldo e intereses de mora; falta además el de agosto.

## Salida obligatoria si NO-GO
```
FINANCIAL ACCOUNT AUDIT — PREFLIGHT
Período: <Qn AAAA | Anual AAAA> · Resultado: NO-GO
Detenido en: P6 (motivos en P2/P3/P4/P5)
Faltantes: <producto · mes · archivo esperado · ruta>
Qué hacer: <descargar / reexportar / declarar con evidencia>
No ejecutado: auditoría, libros, informes, dashboard, Notion.
Reanudar: volver a correr el preflight del mismo período.
```

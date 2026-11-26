# Procedimiento trimestral de auditoría

Frecuencias: **mensual** = solo captura de extractos · **trimestral** = auditoría · **anual** = consolidación.

| Trimestre | Período | Ejecución | Entregables |
|---|---|---|---|
| Q1 | ene–mar | abril | `Auditoria_Trimestral_TC_Q1_AAAA.pdf`, `Auditoria_Trimestral_Bancos_Q1_AAAA.pdf` |
| Q2 | abr–jun | julio | ídem Q2 |
| Q3 | jul–sep | octubre | ídem Q3 |
| Q4 | oct–dic | enero del año siguiente | ídem Q4 + informe anual |

## Ejecución con Claude (skill financial-account-audit)
Instrucción: "Ejecuta Financial Account Audit para Qn AAAA" (o "anual AAAA"). Claude corre primero `python scripts\audit_pipeline.py preflight --period AAAAQn` y **se detiene si el resultado es NO-GO** (extracto, Money Pro o Splitwise faltante). Solo con GO ejecuta las fases P7–P18 en orden (el script rechaza saltos). Para reanudar tras un NO-GO: agregar la evidencia y volver a pedir la ejecución. Metodología en `docs\audit_skill\`.

## 0. Mensual (sin auditoría)
1. Gmail → Apps Script → Drive → `<FINANCE_DATA_ROOT>\Informacion Bancaria\…` (extractos de todas las tarjetas activas, *9910 y fiducuentas).
2. Verifique que llegó un extracto por producto activo. Lo que falte se descarga del portal del banco **antes** del cierre trimestral (una tarjeta sin extracto genera excepción de cobertura y sus costos quedan "Sin evidencia").

## 1. Preparar el trimestre
1. Exportar Money Pro (`Transactions - AAAA Qn.csv`, separador `;`) y Splitwise del período.
2. Exportar Puntos Colombia (si hubo puntos o redenciones).
3. Confirmar que no hay períodos previos con estado `Pendiente` en la pestaña Cronograma.

## 2. Libro de tarjetas — `source/Sistema_Auditoria_TC.xlsx`
1. **Base_Transacciones**: agregar las filas del trimestre al final de la tabla `BaseTx` (IDs `TC-nnnn` consecutivos; nunca reutilizar). Copiar las fórmulas de la fila anterior (Año, Trimestre, Mes, Familiar/Personal/No determinado, Es compra, Es reversión). Ampliar el rango de la tabla si Excel no lo hace solo.
2. Clasificar cada línea: Tipo de movimiento, Categoría, Naturaleza (Personal / Familiar / No determinado), Estado Money Pro, SW ID. Reglas de cruce: Money Pro ±1 COP y ±3 días (probable ±1 % / ±10 días); Splitwise ±5 días.
3. **Extractos_Input**: una fila por corte y moneda (saldo anterior, compras, pagos, intereses corrientes y de mora, nuevo saldo, cupo). Resultado debe quedar `OK`. Los cortes en USD se registran con Moneda = USD: sus intereses no se suman al total COP (Historico_Trimestral filtra Moneda = "COP").
3b. **Cobertura_Extractos**: una fila por producto y mes con el motivo cuando no hay extracto (sin actividad, migrado, cerrado, no abierto). Solo "Falta extracto — requerido" genera excepción. Extractos Bancolombia: zips mensuales `Documento_AAAAMM_*.zip` con `{tarjeta}_{MES}{AAAA}.xlsx` (hojas PESOS y DOLARES).
4. **Beneficios_Input**: cashback/puntos según extracto, según Money Pro y esperado según maestro.
5. **CxC_Input**: gastos cargados y reembolsos de Splitwise del trimestre.
6. **Parametros**: `Año auditado` y `Trimestre auditado`. Revise Resumen_Trimestral y Revision_Productos.
7. **Historico_Trimestral**: si el trimestre es nuevo, insertar la columna `Qn-AAAA` copiando las fórmulas de la columna anterior (el ETL detecta las columnas `Qn-AAAA` automáticamente).
8. **Productos_Financieros**: agregar las filas mensuales del trimestre por producto (copiar fórmulas de tarjetas con extracto; para fiducuentas y productos sin extracto, valores con fuente y evidencia; sin evidencia = celda vacía, nunca un estimado).
9. **Continuidad_Hallazgos**: agregar las columnas `AAAA_Status` / `AAAA_Linked_Exception` al iniciar un año nuevo; actualizar el estado de cada hallazgo histórico.
10. **Controles_Trimestrales**: registrar M-01…M-08 y T-01…T-08 con PASS / WARNING / ERROR, detalle y excepción.

## 3. Libro de bancos — `source/Auditoria_Bancos.xlsx`
1. **Base_Movimientos**: agregar filas (IDs `BA-nnnn` consecutivos) **debajo** del último registro. Las hojas 2025 apuntan a las filas 5–663 y quedan congeladas.
2. Clasificar: Clasificación, Subclase, Flujo económico (Interno, Pago TC, Inversión (capital), Ingreso de inversión, externo…), Tratamiento, Contraparte, Match tipo, Money Pro.
3. Fiducuentas: con extracto detallado por cuenta (`{cuenta}_{MES}{AAAA}.xlsx`) cada traslado con la *9910 se concilia por cuenta y fecha (Match tipo `Exact Match`, Contraparte `Fiducuenta *nnnn`) y **Transferencias_Mensuales** lista el detalle con la atribución de capital a pagos de tarjeta. Si solo hay "Tapa resumen", registro agregado mensual (Match tipo `Monthly aggregate`).
4. **Balance_Continuity**: saldo inicial + movimientos = saldo final (quiebre > $2 = excepción).
5. **Pagos_TC_Trimestral**, **Materiales_Trimestral** (todo movimiento ≥ COP 1.000.000 con conclusión), **Fiducuenta_TC** (capital, intereses, retención, saldo promedio, tasa observada, días de permanencia, capital a pagos TC; costo de oportunidad solo con metodología).
6. **Historico_Trimestral_Bancos**: columna `Qn-AAAA` nueva. **Controles_Trimestrales**: T-BA01…T-BA12.

## 3b. Tesorería — hojas `Tesoreria_Input` y `Metricas_Tesoreria` del libro TC
1. Con el libro de bancos cerrado y guardado en Excel: `python scripts/treasury_inputs.py sync`. Respalda el libro TC en `source/archive/pre_tesoreria_sync_AAAA-MM-DD/` y agrega a **Tesoreria_Input** los meses nuevos (saldos de fin de mes, gasto externo, GMF, intereses, rendimientos, retención y rentabilidad E.A. de la fiducuenta). `python scripts/treasury_inputs.py check` solo compara.
2. **Metricas_Tesoreria**: copiar la última columna `Qn-AAAA` a la derecha y cambiar el encabezado. Año y trimestre se leen del encabezado; la fila "Resultado de controles" debe quedar en OK.
3. Revisar en **Parametros** (filas 30–35) la reserva objetivo, el saldo operativo de ahorros, la tasa de ahorros, el tope Fogafín y, si se usa, la tasa de referencia del trimestre.
4. Cuenta nueva material (otro banco): agregar una columna en Tesoreria_Input y en `scripts/treasury_inputs.py`, y ajustar las filas de liquidez y concentración de Metricas_Tesoreria.

## 4. Excepciones (registro central único: `Excepciones_Central` del libro TC)
- ID siguiente = el que muestra el dashboard (Resumen → "Siguiente ID de excepción"). Nunca reutilizar IDs.
- Campos: ID, Año, Trimestre, Fecha, Origen, Producto, Banco, Concepto, Monto, Tipo de monto, Categoría, Tipo, Riesgo, Money Pro, Splitwise, Explicación, Acción, Evidencia, Estado, Hallazgo relacionado.
- Estados: Open → Monitor / Explained / No Action Required / Closed. Antes de cambiar un estado, copiar el estado vigente en **Estado anterior** y documentar **Evidencia nueva** y **Conclusión de auditoría**; registrar fecha y comentario de cierre.
- No mantener abierta una excepción solo porque existía; no cerrarla solo porque apareció un documento: el documento debe resolver la causa.
- Un hallazgo de un año anterior **no** se reabre: si el control vuelve a fallar, crear una excepción nueva y escribir el ID histórico en `Hallazgo relacionado`.
- Materialidad: COP 1.000.000, sin ignorar patrones repetidos de menor valor.
- Origen de excepciones bancarias debe contener "Bancari" (p. ej. "Auditoría trimestral Cuentas Bancarias Qn AAAA").

## 5. Guardar, refrescar, emitir y validar
1. Abrir ambos libros en Excel y **guardar** (recalcula los valores que lee el ETL).
2. Ejecutar `scripts\cierre_trimestral.bat AAAA n` (equivale a: refresh → `build_quarterly_reports.py --year AAAA --quarter n` → refresh → `validate_system.py`, que escribe también `validation/Validacion_Cierre_AAAA-MM-DD.md` con las validaciones A–P).
3. Revisar en el dashboard: Tesorería (controles de la hoja en OK, alertas), Calidad de Datos (0 ERROR, conciliaciones OK, incluidas las de Tesorería (insumos)), Cronograma (trimestre "Completado"), Excepciones.
4. Responder las excepciones abiertas en el libro (Explicación / Estado / Comentario de cierre) y volver a refrescar.

## 6. Cierre anual (enero)
Auditar Q4 como cualquier trimestre; emitir `Informe_Auditoria_TC_AAAA.pdf` e `Informe_Auditoria_Bancos_AAAA.pdf` en `deliverables/AAAA/`; copiar ambos libros a `source/archive/AAAA_baseline/` con su SHA-256 y registrarlo en `config.json › archive`; cambiar `current_audit_year` al año nuevo.

## Reglas que no cambian
- No inventar saldos, tasas, intereses, beneficios, puntos, costos, fechas, transacciones, explicaciones ni clasificaciones: usar "Sin evidencia" / "No determinado".
- Separar: movimiento · flujo económico · transferencia interna · pago de tarjeta · inversión · ingreso · gasto. El capital transferido a fiducuentas no es ingreso ni gasto; solo el rendimiento es ingreso.
- Puntos: solo se monetizan con el valor realizado de redenciones verificadas (`Parametros › Valor por punto`).
- Las contraseñas de los PDF de extractos no se escriben en ningún archivo.

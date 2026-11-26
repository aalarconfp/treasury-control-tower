# Fase A — Auditoría de tarjetas de crédito (P7) · `source\Sistema_Auditoria_TC.xlsx`

Solo después de GO. Se conserva la estructura del libro: hojas `Instrucciones, Parametros, Resumen_Trimestral, Revision_Productos, Excepciones_Central, Historico_Trimestral, CrossCheck_Maestro, Maestro_Productos, Cobertura_Extractos, Beneficios_Input, CxC_Input, Framework_<AAAA>, Calendario_Arquitectura, Ciclo_Vida_Productos, Productos_Financieros, Controles_Trimestrales, Continuidad_Hallazgos, Base_Transacciones (tabla BaseTx), Extractos_Input`. Nunca se crea un libro por trimestre ni hojas paralelas.

## Carga de evidencia
1. **Extractos_Input**: una fila por corte **y moneda** (COP / USD). Copiar las fórmulas R–W de la fila anterior. `Resultado` debe quedar `OK` o `Utilización > umbral`; cualquier otro valor es diferencia aritmética o de continuidad (saldo anterior ≠ nuevo saldo del corte previo) y se investiga antes de seguir.
2. **Base_Transacciones**: filas nuevas al final de `BaseTx` (IDs `TC-nnnn` consecutivos, nunca reutilizados; ampliar la referencia de la tabla). Fórmulas de Año, Trimestre, Mes, Familiar/Personal/No determinado, Es compra, Es reversión copiadas de la fila anterior.
3. **Cobertura_Extractos**: una fila por producto-mes con el estado del preflight (Con extracto · Sin actividad — no requiere extracto · Sin actividad observada · Producto migrado — extracto final no disponible · Producto cerrado · No abierto · Falta extracto — requerido) y su evidencia.
4. **Beneficios_Input** (cashback, puntos según extracto / Money Pro / esperado), **CxC_Input** (Splitwise: cargados y reembolsos del trimestre), **Parametros** (`Año auditado`, `Trimestre auditado`).

## Reglas de lectura de extractos (aprendidas)
- Bancolombia: números "1.234.567,00" o "1,234,567.00"; período tipo "15 abr" / "18 may. 2026" (inferir el año del corte). En "Movimientos antes del período" solo cuentan las cuotas `1/x`; `k/36` son cuotas re-facturadas. Las compras internacionales se difieren a 36 cuotas por defecto aunque se paguen completas (Internacional = "Sí").
- USD: el valor COP se toma con la TRM implícita del pago USD que las canceló; los intereses USD **no** se suman al total COP (Historico filtra `Moneda = "COP"`).
- Clasificación: `Pago` solo si el valor es negativo o es un ABONO ("PAGO FACTURA MOVIL" positivo **no** es pago). "APLICACION SALDO A FAVOR" no es reversión. Fondeo de bróker con tarjeta (XTB) = "Inversión (fondeo con tarjeta)", Es compra = No. Saldos a favor / ajustes / devoluciones = "Ajuste".
- Cruce Money Pro: ±1 COP y ±3 días (probable ±1 % / ±10 días); en USD exigir palabra clave del comercio. Splitwise ±5 días. Los cruces de trimestres anteriores **no se rehacen** (cambiarían por orden de proceso): los nuevos movimientos se cruzan contra lo que queda libre.
- Productos migrados (*5933 desde ago-2026, Banco de Bogotá): mismo ID de producto, nuevo emisor; extracto del nuevo emisor obligatorio.

## Controles (registrar en `Controles_Trimestrales`, Año/Trimestre/Control/Resultado/Detalle/Excepción/Fecha)
M-01 cobertura · M-02 pagos a tiempo/intereses · M-03 posibles duplicados · M-04 compras sin clasificar · M-05 cargos financieros (intereses, mora, seguros, cuotas de manejo) · M-06 comercios/montos inusuales · M-07 registro en Money Pro de cargos y beneficios · M-08 utilización de cupo (umbral `Parametros`) · T-01 personal vs familiar/CxC · T-02 suscripciones · T-03 variación QoQ y YTD · T-04 diferidos · T-05 cross-check del maestro · T-06 conciliación de beneficios · T-07 costo-beneficio por producto · T-08 revisión de productos (sin uso con costo, exoneraciones por vencer).

## Materialidad y criterio
- Materialidad COP 1.000.000 (`scripts\config.json › materiality_cop`); los patrones repetidos de bajo valor (cuotas, seguros, intereses de mora, suscripciones) se evalúan aunque sean pequeños.
- "No determinado" = compra sin registro en Money Pro ni Splitwise. Se reporta % del consumo por trimestre.
- Antes de abrir una excepción: revisar `Continuidad_Hallazgos` y `Excepciones_Central` (ver `exception_management.md`).

## Salida de la fase
`phase --done P7 --result PASS|WARNING|BLOCKED --note "<resumen>"`. BLOCKED si un extracto no cuadra aritméticamente y no se puede explicar, o si un pago/consumo material no puede soportarse con la evidencia del período.

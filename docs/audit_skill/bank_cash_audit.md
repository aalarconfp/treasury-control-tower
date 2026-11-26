# Fase B — Bancos y efectivo (P8) · `source\Auditoria_Bancos.xlsx`

Libro separado del de tarjetas (nunca se combinan). Hojas 2025 congeladas: `Resumen, Inventario, Transferencias_Internas, Pagos_TC, Flujos_Economicos, Reembolsos_Familiares, MoneyPro_Comparacion, Rendimientos, Comisiones_Impuestos, Movimientos_Materiales, Excepciones, Framework…, Automatizacion` (apuntan a las filas 5–663 de Base_Movimientos). Hojas multianuales: `Base_Movimientos, Resumen_Trimestral_Bancos, Historico_Trimestral_Bancos, Balance_Continuity, Transferencias_Mensuales, Pagos_TC_Trimestral, Materiales_Trimestral, Fiducuenta_TC, Controles_Trimestrales, Notas_Metodologia`.

## Carga
1. **Base_Movimientos** (encabezado fila 4): filas nuevas **debajo** del último registro, IDs `BA-nnnn` consecutivos. Columnas: Cuenta, Banco, Archivo extracto, Fecha, Mes, Trimestre, Descripción, Valor, Entrada, Salida, Saldo después, Clasificación, Subclase, Flujo económico, Tratamiento, Confianza, Contraparte, Match tipo, Match ref, Money Pro estado/ref, Material (≥1M), Excepción, Nota, Año.
2. **Balance_Continuity**: saldo inicial + movimientos = saldo final por cuenta y período (quiebre > COP 2 = excepción).
3. **Fiducuentas**: con extracto detallado por cuenta, cada traslado con la *9910 se concilia por cuenta y fecha (Match tipo `Exact Match`, Contraparte `Fiducuenta *nnnn`). Solo con "Tapa resumen": registro agregado mensual (`Monthly aggregate`). Saldo final = anterior + aportes − retiros + rendimientos netos − retención.
4. **Fiducuenta_TC**: capital, intereses, retención, saldo promedio, tasa observada, días de permanencia y capital destinado a pagos TC (retiros seguidos de pagos de tarjeta en la *9910 el mismo día o el siguiente; si varias cuentas retiran el mismo día, reparto proporcional). Fiducuenta TC = *6191 (confirmada por evidencia). Costo de oportunidad: **no se calcula** sin metodología aprobada.
5. **Pagos_TC_Trimestral**, **Materiales_Trimestral** (todo movimiento ≥ COP 1.000.000 con conclusión), **Transferencias_Mensuales**, **Historico_Trimestral_Bancos** (columna `Qn-AAAA` nueva copiando fórmulas).

## Taxonomía obligatoria (nunca mezclar)
Movimiento bancario · Transferencia interna · Flujo económico · Ingreso económico · Gasto económico · Pago de tarjeta · Movimiento de inversión · Rendimiento financiero.
- Una transferencia interna **no** es ingreso; el traslado de capital entre cuentas propias **no** es gasto.
- Los intereses / rendimientos netos de fiducuentas **sí** son ingreso financiero; la retención es un anticipo de impuesto.
- Pagos de tarjeta = cancelación de pasivo propio (se excluyen de ingresos y gastos).
- **Capital familiar administrado** (consignación 61M jun-2026, retiros de devolución EX-44, fiducuenta *0452): flujo de **terceros**, no ingreso/gasto ni rendimiento propio; sus rendimientos se separan según el reparto acordado (pendiente de definir: "probablemente 50/50").

## Controles (`Controles_Trimestrales`)
T-BA01 cobertura · T-BA02 continuidad de saldos · T-BA03 transferencias internas · T-BA04 pagos de tarjetas · T-BA05 ingresos externos · T-BA06 gastos externos materiales · T-BA07 rendimientos · T-BA08 comisiones / GMF · T-BA09 movimientos inusuales · T-BA10 cross-check del maestro · T-BA11 reembolsos familiares · T-BA12 control de doble conteo.

Excepciones bancarias: Origen debe contener "Bancari" (p. ej. "Auditoría trimestral Cuentas Bancarias Qn AAAA") y se registran en el **registro central** (`Excepciones_Central` del libro TC); el registro `Excepciones` del libro de bancos es 2025 y no se duplica.

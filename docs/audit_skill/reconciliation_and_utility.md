# Fases C y D — Conciliación cruzada (P9) y utilidad de productos (P10)

## Conciliación cruzada
| Lado A | Lado B | Regla | Resultado |
|---|---|---|---|
| Pago de tarjeta en *9910 (Pagos_TC_Trimestral) | Abono en el extracto TC (Base_Transacciones, Tipo Pago) | Monto exacto, fecha −1/+6 días; USD con TRM implícita | `Exact Match` + TxnID; si no cruza → excepción solo si hay extracto (sin extracto es un problema de cobertura, no de pago) |
| Traslado *9910 → fiducuenta | ADICION en el extracto de la fiducuenta | Por cuenta y fecha | `Exact Match` (detalle) o `Aggregate Match` (Tapa) |
| Retiro de fiducuenta | Entrada en *9910 | Por cuenta y fecha | Igual |
| Rendimientos netos de fiducuenta | Money Pro (Interest Income) | El usuario registra **neto** (intereses − retención); comparar neto con neto por mes | Diferencia documentada (no es error si el criterio es neto) |
| Gasto familiar en tarjeta | Splitwise / reembolsos (CxC_Input, Reembolsos familiares) | Agregado por período | Diferencias documentadas; no exigir cruce uno a uno |
| Productos cerrados/migrados | Datacrédito / extracto del nuevo emisor | Fecha del evento | Conclusión confirmada solo con evidencia; si falta, PENDIENTE |

Una diferencia se cierra **solo con evidencia**. Una excepción se registra una sola vez en el registro central aunque afecte a los dos libros.

## Utilidad de productos (`Productos_Financieros`)
Catálogo (ID_Producto … Comentario + estrategia: Estado de cobertura, Beneficio_Principal, Condición_Beneficio, Uso_Recomendado, No_Conviene_Para, Limitaciones, Costo_Relevante, Puntos por COP (teórico), Cashback teórico, Fuente_Beneficio, Fecha_Verificación) y tabla mensual (Año … Comentario + Beneficio potencial (teórico), Estado de cobertura, Con uso).
- **Tarjetas:** cuotas de manejo, seguros, intereses, otros cargos → Costo total; cashback, descuentos, puntos monetizados, otros beneficios → Beneficios totales; Valor neto; ROI = valor neto / costo (n/a si costo 0).
- **Cuentas y fiducuentas:** saldo promedio, intereses generados, retención, rendimiento neto, rendimiento observado (mensual y E.A.), interés por COP 1M. Las transferencias de capital no son beneficio.
- **Real ≠ teórico:** "Beneficio potencial (teórico)" (condiciones oficiales × consumo) es referencia, nunca ingreso. Las condiciones oficiales se verifican en la web del emisor con fecha; si el sitio no responde, se usan extractos o el documento del usuario y se dice.
- Productos sin extracto: costos "Sin evidencia" (no se estiman).
- **Capital familiar (*0452):** sus rendimientos no son valor propio completo; hasta definir el reparto, marcarlos como "capital de terceros — reparto pendiente" y excluirlos de KPIs propios.
- No se recomienda cancelar un producto automáticamente: se presenta costo, uso y beneficio real para que el usuario decida.

## Puntos Colombia y control histórico Primax
- Valor por punto = `Parametros!B19` (hoy 6,3148, derivado de redenciones 2026 que incluyen Primax a 7,0).
- La auditoría Primax 2024-2026 (`Puntos Colombia\Auditoria Primax 2024-2026\`) dejó: 20 redenciones confirmadas (96.816 pts), 19 en Money Pro (falta 08-jul-2024, 3.167 pts); ajustes Money Pro **pendientes de aprobación**; equivalencia Primax **pendiente** de comprobante (escenario B: 7 COP/pt hasta 31-dic-2025, 6 desde 2026; efecto neto 0).
- Regla: cada redención se valora con la equivalencia **vigente y verificada** en `Control_Equivalencias`. Si la fila del aliado/período está "Pendiente", el valor se marca **ESTIMADO** y `B19` no se cambia hasta tener comprobante (factura electrónica Primax o detalle en la app). El preflight lo reporta como WARNING en cada período.
- Trimestralmente: conciliar el export de Puntos Colombia (Redemption) vs Money Pro (Fidelity Points Earned): mismo conteo, residuo 0 con la tasa vigente. Puntos **ganados** (devengo, ×B19) y **redimidos** (realización) son bases distintas: no se suman en un mismo KPI.
- Tratamiento recomendado (pendiente de adopción por el usuario): la pierna de gasto de los puntos de combustible va a `Transportation: Motorcycle Fuel`, no a `To Savings`.

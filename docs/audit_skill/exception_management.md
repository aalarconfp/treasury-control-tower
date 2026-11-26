# Fase E — Excepciones y continuidad (P11)

Registro central único: `Sistema_Auditoria_TC.xlsx › Excepciones_Central` (consolida tarjetas y bancos). Matriz de continuidad: `Continuidad_Hallazgos` (encabezado fila 4). Ciclo de vida: `Ciclo_Vida_Productos` (encabezado fila 4).

## Estados
`Open` · `Monitor` (sin acción correctiva, con seguimiento; no cuenta como abierta) · `Explained` · `No Action Required` · `Closed`. Normalización en `scripts\config.json › status_normalization`.

## Al cambiar un estado (obligatorio)
1. Copiar el estado vigente en **Estado anterior**.
2. Escribir **Evidencia nueva** (archivo, fecha, cifra) y **Conclusión de auditoría**.
3. Actualizar `Fecha último cambio de estado` y, si cierra, `Comentario de cierre`.
4. Las respuestas del usuario en `Comentario de cierre` son evidencia del usuario: se respetan, pero si nueva evidencia documental las contradice, se abre una excepción nueva vinculada (no se reescribe el historial).

## Reglas
- **No** mantener abierta una excepción solo porque existía; **no** cerrarla solo porque apareció un documento: el documento debe resolver la causa.
- No cerrar una excepción porque desapareció de un informe.
- IDs `EX-nn` nunca se reutilizan; el siguiente ID lo da el dashboard (Resumen) o `continuity.json › next_exception_id`.
- Hallazgos de años anteriores (Año < año de auditoría) son **históricos**: nunca cuentan como abiertos actuales. Categorías de continuidad: A Resuelto — no reabrir · B Resuelto — monitorear · C Control recurrente · D Abierto / carry forward · E Reemplazado por nuevo control · F Contexto histórico.
- Si un hallazgo histórico vuelve a ocurrir: **excepción nueva** con `Hallazgo relacionado = EX-xx` y actualizar `<AAAA>_Status / <AAAA>_Linked_Exception` en Continuidad_Hallazgos. Control automático: `python scripts\audit_pipeline.py check-exceptions` (después del refresh).
- Una sola entrada por problema en el registro central, aunque afecte a los dos libros. Excepciones de bancos: Origen con "Bancari".
- Campos: ID, Año, Trimestre, Fecha detección, Origen, Fecha, Tarjeta/Cuenta, Comercio/Movimiento, Monto (COP), Tipo de monto, Categoría, Tipo, Riesgo (HIGH/MEDIUM/LOW/INFO), Money Pro, Splitwise, Explicación, Acción, Evidencia, TxnID, Estado, Fecha último cambio, Comentario de cierre, Banco, Producto, Hallazgo relacionado, Estado anterior, Evidencia nueva, Conclusión de auditoría.

## Pendientes conocidos
Los pendientes concretos de cada cierre (con cifras reales) están en `work\PENDIENTES.md`, que es privado y no se versiona. Leerlo al iniciar cada cierre y actualizarlo al terminar.

# Arquitectura multianual (v2 — 6-oct-2026)

## Decisión: base multianual única (no carpetas por año)

| Opción | Ventajas | Desventajas | Decisión |
|---|---|---|---|
| Carpetas `source/2025`, `source/2026` con un libro por año | Separación física | Duplica estructura, fórmulas, maestros y controles; comparativos entre años requieren unir libros; el ETL tendría que fusionar | Descartada |
| **Un libro multianual por módulo + archivo baseline congelado** | Una sola fuente de verdad; comparativos nativos (columnas `Qn-AAAA`); sin duplicación; proceso trimestral = agregar filas | Hay que proteger el rango histórico | **Elegida** |

Protección de 2025: (1) las hojas 2025 del libro de bancos apuntan a `Base_Movimientos!$5:$663` y las filas 2026+ se agregan debajo; (2) copias congeladas en `source/archive/2025_baseline/` con SHA-256 en `config.json › archive` y verificación automática en cada refresh; (3) `validate_system.py` compara las métricas 2025 del libro vigente contra la copia baseline (0 diferencias al 6-oct-2026).

## Cambios por componente

| Componente | Antes (v1) | Ahora (v2) |
|---|---|---|
| Libro bancos | `Auditoria_Bancos_2025.xlsx` (config apuntaba a un archivo inexistente) | `Auditoria_Bancos.xlsx` multianual: columna Año en Base_Movimientos; hojas nuevas Resumen_Trimestral_Bancos, Historico_Trimestral_Bancos, Transferencias_Mensuales, Pagos_TC_Trimestral, Materiales_Trimestral, Fiducuenta_TC, Controles_Trimestrales; Balance_Continuity con secciones 2026 |
| Libro TC | Excepciones EX-01…EX-33; continuidad en CSV | Excepciones EX-34…EX-48 con Banco, Producto, Tipo de monto, Hallazgo relacionado; hojas nuevas Continuidad_Hallazgos, Ciclo_Vida_Productos, Productos_Financieros, Controles_Trimestrales; Historico_Trimestral Q1-2025…Q3-2026 con comparativos; parámetro de valor por punto |
| ETL | 8 referencias fijas a "Auditoria_Bancos_2025.xlsx"; hojas `Framework_2026` por nombre | Rutas desde config; hojas por patrón; años desde la columna Año; columnas `Qn-AAAA` y `AAAA_Status` dinámicas; 8 datasets (+ product_utility, data_quality); 188 conciliaciones; compatible con los libros 2025 originales |
| Dashboard | Inglés, 6 pestañas + DQ | Español, 8 pestañas; filtros de Año, Trimestre, Mes, Banco, Producto, Tarjeta, Categoría, Tipo de flujo, Estado, Riesgo, Módulo; comparativos interanuales con el mismo alcance |
| Continuidad | CSV borrador | Hoja del libro (fuente), categorías A–F, estado por año, vínculo a excepción nueva |
| Entregables | Detectados por nombre | Generados por `build_quarterly_reports.py` en `deliverables/AAAA/`; el cronograma pasa a "Completado" automáticamente |

## Contrato de datos (`window.AUDIT_DATA`)
`metadata` · `credit_cards` · `bank_cash` · `exceptions` · `timeline` · `continuity` · `product_utility` · `data_quality`.

## Separación de responsabilidades
- **Excel**: clasificaciones, naturalezas, riesgos, excepciones, continuidad, resultados de controles, utilidad por producto.
- **ETL**: lectura, tipado, agregación con los mismos criterios de los SUMIFS, conciliación, calidad de datos, estado del cronograma (por existencia de entregables).
- **HTML/JS**: filtros y SUMA/CONTEO/razones sobre las definiciones del contrato.

## Supuestos vigentes
- Fiducuenta TC = fiducuenta *6191 (Money Pro la etiqueta "Fiducuenta TC" desde abril; ver excepción INFO EX-48). Si es otra, cambie `Tipo de producto` en Productos_Financieros y refresque.
- Valor por punto Puntos Colombia = 6,3148 COP (promedio ponderado de 4 redenciones verificadas; rango 6,04–7,00).
- Los PDF "Tapa resumen" de la Fiduciaria no traen detalle: la conciliación con la *9910 es agregada mensual.

## Segunda pasada de cierre Q1–Q3 2026 (6-oct-2026)

* Nueva hoja `Cobertura_Extractos` (libro TC) como fuente única del motivo de cobertura por producto-mes; el ETL la lee (opcional) y Calidad de Datos solo marca ERROR para "Falta extracto — requerido".
* `Excepciones_Central` agrega `Estado anterior`, `Evidencia nueva` y `Conclusión de auditoría`; nuevo estado `Monitor`. El ETL calcula `closed_this_update` (estado anterior abierto → actual no abierto) sin reglas adicionales en JavaScript.
* `Productos_Financieros`: columnas de estrategia en el catálogo (Beneficio_Principal, Condición_Beneficio, Uso_Recomendado, No_Conviene_Para, Limitaciones, Costo_Relevante, Fuente_Beneficio, Fecha_Verificación) y columnas mensuales `Beneficio potencial (teórico)`, `Estado de cobertura`, `Con uso (1=sí)`.
* Métrica de intereses TC: solo Moneda = COP (la misma regla en Historico_Trimestral, Resumen_Trimestral y `TC_METRICS`).
* `norm()` del ETL conserva la precisión de razones/tasas (|v| < 1); los montos siguen a 2 decimales.
* Los libros previos a la segunda pasada quedan en `source/archive/pass1_2026-10-06/`.

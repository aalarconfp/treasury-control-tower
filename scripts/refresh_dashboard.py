#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_dashboard.py — ETL Excel → JSON del Financial Account Audit System (v2, multianual).

    Excel (fuente de verdad)  →  este script  →  data/*.json + data/dashboard_data.js  →  index.html

Reglas
------
* Los libros Excel son SOLO de entrada: se abren en modo lectura (openpyxl, data_only=True) y se verifica
  su hash SHA-256 antes y después del refresh. Nunca se escriben.
* Ninguna lógica de auditoría se reimplementa aquí: clasificaciones, naturalezas, riesgos, excepciones,
  continuidad y resultados de controles vienen del Excel. El ETL solo normaliza tipos, selecciona campos,
  agrega con los mismos criterios de los SUMIFS del libro y concilia contra los totales del propio libro.
* Años, trimestres, meses, productos y cuentas salen de los datos (columna Año / Fecha). Ningún año
  está fijo en la lógica: el año actual y el año base vienen de scripts/config.json (o se infieren).
* Si falta una hoja o columna requerida, el script se detiene, conserva los JSON anteriores y escribe el
  error en data/metadata.json (el dashboard lo muestra).

Uso
---
    python scripts/refresh_dashboard.py            # usa scripts/config.json
    python scripts/refresh_dashboard.py --check    # solo valida (no escribe JSON)

Requiere: Python 3.9+, openpyxl
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import sys
from collections import OrderedDict, defaultdict

try:
    import openpyxl
except ImportError:  # pragma: no cover
    sys.exit("ERROR: falta openpyxl.  Ejecute:  pip install openpyxl")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import treasury_inputs  # noqa: E402  (definición única de los insumos de tesorería)
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "scripts", "config.json")
SCHEMA_VERSION = "2.0"
RISK_ORDER = ["HIGH", "MEDIUM", "LOW", "INFO"]

# --------------------------------------------------------------------------------------
# Contrato de datos del lado Excel. "required" faltante → ERROR (se detiene). "optional" → aviso.
# Las hojas se buscan por nombre exacto o por patrón (para no depender del año en el nombre).
# --------------------------------------------------------------------------------------
TC_SCHEMA = {
    "Parametros": {"kind": "kv"},
    "Base_Transacciones": {
        "required": ["TxnID", "Fecha", "Año", "Trimestre", "Mes", "Banco", "Producto", "Tarjeta", "Comercio normalizado", "Moneda", "Valor COP",
                     "Tipo de movimiento", "Categoría", "Estado Money Pro", "Naturaleza", "Familiar COP", "Personal COP", "No determinado COP",
                     "Es compra", "Es reversión", "Excepción"],
        "optional": ["Archivo extracto", "Autorización", "Descripción", "Valor original", "Cuotas", "Fuente categoría", "Internacional", "MP ID", "SW ID", "SW descripción"],
        "id": "TxnID", "id_pattern": r"^TC-\d+$"},
    "Excepciones_Central": {
        "required": ["ID", "Año", "Trimestre", "Origen", "Fecha", "Tarjeta", "Comercio", "Monto (COP)", "Categoría", "Tipo", "Riesgo", "Money Pro",
                     "Splitwise", "Explicación", "Acción", "Estado"],
        "optional": ["Fecha detección", "Evidencia", "TxnID", "Fecha último cambio de estado", "Comentario de cierre", "Banco", "Producto", "Tipo de monto",
                     "Hallazgo relacionado", "Estado anterior", "Evidencia nueva", "Conclusión de auditoría"],
        "id": "ID", "id_pattern": r"^EX-\d+$"},
    "Extractos_Input": {
        "required": ["Año", "Trimestre", "Banco", "Producto", "Tarjeta", "Moneda", "Fecha corte", "Cupo", "Intereses corrientes", "Intereses mora",
                     "Nuevo saldo", "Utilización", "Resultado"],
        "optional": ["Archivo", "Saldo anterior", "Compras / cargos", "Avances", "Otros cargos", "Pagos y abonos", "Dif. aritmética", "Dif. continuidad"]},
    "Beneficios_Input": {
        "required": ["Año", "Trimestre", "Mes", "Producto", "Beneficio según extracto", "Redimido / abonado según extracto", "Beneficio según Money Pro",
                     "Beneficio esperado (maestro)"],
        "optional": ["Diferencia extracto vs Money Pro (redimido)", "Diferencia recibido vs esperado", "Nota"]},
    "CxC_Input": {"required": ["Año", "Trimestre", "Mes", "Gastos cargados en Splitwise", "Reembolsos recibidos", "Neto"], "optional": ["Clave período"]},
    "Maestro_Productos": {
        "required": ["Banco", "Franquicia", "No. maestro", "Plan", "Cupo", "Cuota actual", "Beneficio", "Estado maestro", "Producto en base (si aplica)"],
        "optional": ["Tasa M.V.", "Día corte", "Día pago", "Cuota real", "Exoneración", "Expedición", "Fin exoneración"]},
    "Revision_Productos": {
        "required": ["Producto (base)", "No. maestro", "Estado maestro", "Consumo trimestre", "¿Uso?", "Cuotas de manejo trimestre", "Seguros trimestre",
                     "Utilización máxima", "Alerta", "Cuota actual (maestro)"],
        "optional": ["Cortes en el trimestre", "Costo sin uso", "Fin exoneración (maestro)", "Exoneración vence ≤ ventana", "Cuota promedio cobrada"]},
    "Historico_Trimestral": {"kind": "matrix", "label_col": "Indicador"},
    "Resumen_Trimestral": {"kind": "free"},
    "Calendario_Arquitectura": {"required": ["Período auditado", "Mes de ejecución", "Entregables", "Alimenta"], "optional": []},
    "re:^Framework": {"required": ["ID", "Frecuencia", "Control", "Objetivo", "Criterio de excepción", "Importancia"],
                      "optional": ["Fuente", "Regla", "Automatizable por reglas", "Requiere IA"], "id": "ID", "alias_key": "Framework"},
    "CrossCheck_Maestro": {"required": ["Producto", "Atributo", "Maestro", "Resultado"], "optional": ["Extracto / Datacrédito / Money Pro", "Comentario", "Período revisado"]},
}
TC_OPTIONAL_SHEETS = {
    "Continuidad_Hallazgos": {"required": ["Record_Type", "Finding_ID", "Original_Year", "Source", "Original_Status", "Continuity_Category", "Carry_Forward_Rule"],
                              "optional": ["Original_Quarter", "Original_Description", "Original_Risk", "Respuesta_Usuario", "Resolution", "Evidence", "Control_Ref",
                                           "Context_Match_Field", "Context_Match_Pattern", "Baseline_Status", "Notes"], "id": "Finding_ID", "dynamic": r"^\d{4}_(Status|Linked_Exception)$"},
    "Ciclo_Vida_Productos": {"required": ["Tarjeta", "Status"], "optional": ["Producto", "Banco", "Tipo de producto", "Opening_Date", "Closure_Date", "Replaced_By",
                                                                            "Historical_Audit", "Evidence", "Notes"], "id": "Tarjeta"},
    "Controles_Trimestrales": {"required": ["Año", "Trimestre", "Control", "Resultado"], "optional": ["Descripción", "Detalle / evidencia", "Excepción", "Fecha ejecución"]},
    "Cobertura_Extractos": {"required": ["Año", "Mes", "ID_Producto", "Producto", "Estado de cobertura", "Requiere extracto"],
                            "optional": ["Evidencia del estado", "Excepción"]},
}
# Estados de cobertura que NO son problema (sin extracto ≠ problema). Solo "Falta extracto — requerido" es ERROR.
COVERAGE_OK = ("Con extracto", "Sin actividad", "Producto migrado", "Producto cerrado", "No abierto", "Sin actividad observada")
BANK_SCHEMA = {
    "Base_Movimientos": {
        "required": ["ID", "Cuenta", "Banco", "Fecha", "Mes", "Trimestre", "Descripción (extracto)", "Valor", "Entrada", "Salida", "Saldo después", "Clasificación",
                     "Subclase", "Flujo económico", "Tratamiento", "Contraparte", "Match tipo", "Money Pro estado", "Material (≥1M)", "Excepción"],
        "optional": ["Archivo extracto", "Confianza", "Match ref", "Money Pro ref", "Nota", "Año"], "id": "ID", "id_pattern": r"^BA-\d+$"},
    "Movimientos_Materiales": {"required": ["ID", "Cuenta", "Fecha", "Descripción", "Valor", "Clasificación", "Subclase", "Contraparte", "Match", "Money Pro",
                                            "Excepción", "Conclusión"], "optional": [], "id": "ID"},
    "Excepciones": {"required": ["ID", "Año", "Trimestre", "Origen", "Fecha", "Cuenta / producto", "Banco", "Movimiento", "Monto (COP)", "Categoría", "Tipo", "Riesgo",
                                 "Money Pro", "Splitwise", "Explicación", "Acción", "Evidencia", "Estado"],
                    "optional": ["Fecha detección", "Ref. base", "Fecha último cambio", "Comentario de cierre", "Tipo de monto", "Hallazgo relacionado"],
                    "id": "ID", "id_pattern": r"^EX-\d+$"},
    "Inventario": {"required": ["Banco", "Cuenta", "Tipo", "Moneda", "Estado producto", "Cobertura"],
                   "optional": ["Período con extracto", "Extractos", "Saldo inicial", "Saldo final", "Actividad", "Tratamiento / observaciones"],
                   "alias": {"Cobertura": r"^Cobertura", "Saldo inicial": r"^Saldo inicial", "Saldo final": r"^Saldo final", "Actividad": r"^Actividad"}},
    "Transferencias_Internas": {"required": ["Origen", "Destino", "Fecha salida", "Fecha entrada", "Monto", "ID *9910", "ID contraparte", "Estado"],
                                "optional": ["#", "Desfase (días)", "Evidencia"]},
    "Flujos_Economicos": {"kind": "free"},
    "Balance_Continuity": {"kind": "free"},
    "Resumen": {"kind": "free"},
    "CrossCheck_Maestro": {"required": ["Producto", "Atributo", "Maestro", "Resultado"], "optional": ["Extracto / Datacrédito / Money Pro", "Comentario"]},
    "re:^Framework": {"required": ["ID", "Control", "Objetivo", "Criterio de excepción"], "optional": ["Fuente", "Procedimiento", "Automatizable por reglas", "Evidencia a archivar"],
                      "id": "ID", "alias_key": "Framework"},
    "Notas_Metodologia": {"kind": "free"},
}
BANK_OPTIONAL_SHEETS = {
    "Controles_Trimestrales": TC_OPTIONAL_SHEETS["Controles_Trimestrales"],
    "Pagos_TC_Trimestral": {"required": ["ID *9910", "Fecha", "Año", "Trimestre", "Tarjeta / producto", "Monto pagado", "Estado"], "optional": ["TxnID auditoría TC", "Excepción"], "id": "ID *9910",
                            "id_pattern": r"^BA-\d+$"},
    "Materiales_Trimestral": {"required": ["ID", "Cuenta", "Fecha", "Año", "Trimestre", "Descripción", "Valor", "Clasificación", "Conclusión"],
                              "optional": ["Subclase", "Contraparte", "Match", "Money Pro", "Excepción"], "id": "ID", "id_pattern": r"^BA-\d+$"},
    "Transferencias_Mensuales": {"required": ["Año", "Mes", "*9910 → Fiducuentas", "Adiciones Fiducuentas", "Fiducuentas → *9910", "Retiros Fiducuentas", "Estado"],
                                 "optional": ["Dif. aportes", "Dif. retiros", "Nota"]},
    "Fiducuenta_TC": {"required": ["Cuenta", "Número", "Tipo de producto", "Año", "Trimestre", "Mes", "Saldo inicial", "Capital aportado", "Capital retirado",
                                   "Intereses generados (rend. netos)", "Retención", "Saldo final"],
                      "optional": ["Saldo promedio simple", "Interés / saldo promedio (mensual)", "Tasa efectiva observada E.A.", "Rentabilidad informada E.A.",
                                   "Interés por COP 1M mantenido", "Días promedio de permanencia (rotación)", "Capital destinado a pagos TC (atribuible)",
                                   "% del retiro usado para TC", "Resultado neto (intereses − retención)", "Money Pro registrado", "Dif. neto vs Money Pro",
                                   "Costo de oportunidad", "Evidencia"], "id": "Cuenta", "id_pattern": r"^Fiducuenta", "stop_blank": True},
    "Historico_Trimestral_Bancos": {"kind": "matrix", "label_col": "Indicador"},
}

# Métricas = los SUMIFS del libro expresados de forma declarativa (mismos criterios en ETL y dashboard).
TC_METRICS = OrderedDict([
    ("gross_spend", {"label": "Consumo bruto", "source": "Base_Transacciones", "agg": "sum", "field": "Valor COP", "where": {"Es compra": "Sí"}, "excel": "SUMIFS(Valor COP; Es compra=\"Sí\")"}),
    ("reversals", {"label": "Reversiones", "source": "Base_Transacciones", "agg": "sum", "field": "Valor COP", "where": {"Es reversión": "Sí"}, "excel": "SUMIFS(Valor COP; Es reversión=\"Sí\")"}),
    ("purchases", {"label": "Número de compras", "source": "Base_Transacciones", "agg": "count", "where": {"Es compra": "Sí"}, "excel": "COUNTIFS(Es compra=\"Sí\")"}),
    ("family", {"label": "Familiar / compartido", "source": "Base_Transacciones", "agg": "sum", "field": "Familiar COP", "where": {}, "excel": "SUM(Familiar COP)"}),
    ("personal", {"label": "Personal", "source": "Base_Transacciones", "agg": "sum", "field": "Personal COP", "where": {}, "excel": "SUM(Personal COP)"}),
    ("undetermined", {"label": "No determinado", "source": "Base_Transacciones", "agg": "sum", "field": "No determinado COP", "where": {}, "excel": "SUM(No determinado COP)"}),
    ("fees", {"label": "Cuotas de manejo", "source": "Base_Transacciones", "agg": "sum", "field": "Valor COP", "where": {"Tipo de movimiento": "Cuota de manejo"}, "excel": "SUMIFS(Valor COP; Tipo=\"Cuota de manejo\")"}),
    ("insurance", {"label": "Seguros", "source": "Base_Transacciones", "agg": "sum", "field": "Valor COP", "where": {"Tipo de movimiento": "Seguro"}, "excel": "SUMIFS(Valor COP; Tipo=\"Seguro\")"}),
    ("interest", {"label": "Intereses", "source": "Extractos_Input", "agg": "sum", "field": ["Intereses corrientes", "Intereses mora"], "where": {"Moneda": "COP"}, "excel": "SUMIFS(Intereses corrientes; Moneda=\"COP\")+SUMIFS(Intereses mora; Moneda=\"COP\")"}),
    ("benefits", {"label": "Beneficios", "source": "Beneficios_Input", "agg": "sum", "field": "Beneficio según extracto", "where": {}, "excel": "SUM(Beneficio según extracto)"}),
])
TC_HIST_MAP = {"gross_spend": "Consumo bruto", "reversals": "Reversiones", "purchases": "Número de compras", "family": "Familiar atribuible", "personal": "Personal estimado",
               "undetermined": "No determinado", "fees": "Cuotas de manejo", "insurance": "Seguros", "interest": "Intereses", "benefits": "Beneficios verificados", "net_cost": "Costo neto"}
BANK_METRICS = OrderedDict([
    ("gross_in", {"label": "Entradas brutas", "source": "Base_Movimientos", "agg": "sum", "field": "Entrada", "where": {}, "excel": "SUM(Entrada)"}),
    ("gross_out", {"label": "Salidas brutas", "source": "Base_Movimientos", "agg": "sum", "field": "Salida", "where": {}, "excel": "SUM(Salida)"}),
    ("external_in", {"label": "Entradas externas", "source": "Base_Movimientos", "agg": "sum", "field": "Entrada", "where": {"Tratamiento": "Flujo económico externo"}, "excel": "SUMIFS(Entrada; Tratamiento=\"Flujo económico externo\")"}),
    ("external_out", {"label": "Salidas externas", "source": "Base_Movimientos", "agg": "sum", "field": "Salida", "where": {"Tratamiento": "Flujo económico externo"}, "excel": "SUMIFS(Salida; Tratamiento=\"Flujo económico externo\")"}),
    ("internal_in", {"label": "Transferencias internas (entradas)", "source": "Base_Movimientos", "agg": "sum", "field": "Entrada", "where": {"Flujo económico": "Interno"}, "excel": "SUMIFS(Entrada; Flujo=\"Interno\")"}),
    ("internal_out", {"label": "Transferencias internas (salidas)", "source": "Base_Movimientos", "agg": "sum", "field": "Salida", "where": {"Flujo económico": "Interno"}, "excel": "SUMIFS(Salida; Flujo=\"Interno\")"}),
    ("investment_in", {"label": "Inversión — retiros", "source": "Base_Movimientos", "agg": "sum", "field": "Entrada", "where": {"Flujo económico": "Inversión (capital)"}, "excel": "SUMIFS(Entrada; Flujo=\"Inversión (capital)\")"}),
    ("investment_out", {"label": "Inversión — aportes", "source": "Base_Movimientos", "agg": "sum", "field": "Salida", "where": {"Flujo económico": "Inversión (capital)"}, "excel": "SUMIFS(Salida; Flujo=\"Inversión (capital)\")"}),
    ("card_payments", {"label": "Pagos de tarjetas", "source": "Base_Movimientos", "agg": "sum", "field": "Salida", "where": {"Flujo económico": "Pago TC"}, "excel": "SUMIFS(Salida; Flujo=\"Pago TC\")"}),
    ("investment_income", {"label": "Intereses y rendimientos", "source": "Base_Movimientos", "agg": "sum", "field": "Entrada", "where": {"Flujo económico": "Ingreso de inversión"}, "excel": "SUMIFS(Entrada; Flujo=\"Ingreso de inversión\")"}),
    ("material_count", {"label": "Movimientos ≥ 1M", "source": "Base_Movimientos", "agg": "count", "where": {"Material (≥1M)": "Sí"}, "excel": "COUNTIFS(Material=\"Sí\")"}),
    ("unmatched", {"label": "Sin conciliar (Match tipo)", "source": "Base_Movimientos", "agg": "count", "where": {"Match tipo": {"startswith": "Unmatched"}}, "excel": "COUNTIFS(Match tipo=\"Unmatched*\")"}),
])
CATEGORIES = OrderedDict([("A", "A. Resuelto — no reabrir"), ("B", "B. Resuelto pero monitorear"), ("C", "C. Control recurrente"), ("D", "D. Abierto / carry forward"),
                          ("E", "E. Reemplazado por nuevo control"), ("F", "F. Contexto histórico")])
EXC_GROUP = {"A": "historico_resuelto", "B": "historico_resuelto", "C": "recurrente", "D": "carry_forward", "E": "historico_resuelto", "F": "historico_resuelto"}
SPANISH_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
                  "octubre": 10, "noviembre": 11, "diciembre": 12}


# ======================================================================================
class Log:
    def __init__(self):
        self.errors, self.warnings, self.info, self.checks = [], [], [], []

    def error(self, code, msg, **ctx):
        self.errors.append({"code": code, "message": msg, **ctx})

    def warn(self, code, msg, **ctx):
        self.warnings.append({"code": code, "message": msg, **ctx})

    def note(self, code, msg, **ctx):
        self.info.append({"code": code, "message": msg, **ctx})

    def check(self, name, category, source_a, value_a, source_b, value_b, tol=1.0):
        ok = value_a is not None and value_b is not None and abs(float(value_a) - float(value_b)) <= tol
        self.checks.append({"check": name, "category": category, "a": {"source": source_a, "value": _r(value_a)}, "b": {"source": source_b, "value": _r(value_b)},
                            "difference": _r((value_a or 0) - (value_b or 0)) if value_a is not None and value_b is not None else None,
                            "status": "PASS" if ok else "ERROR"})
        if not ok:
            self.warn("RECON_FAIL", f"Conciliación fallida: {name}", a=source_a, b=source_b, value_a=_r(value_a), value_b=_r(value_b))
        return ok


def _r(v, n=2):
    return round(v, n) if isinstance(v, float) else v


def norm(v):
    if v is None:
        return None
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float):
        # montos a 2 decimales; razones/tasas (|v| < 1) conservan precisión (antes 8,26% se mostraba 8,00%)
        return round(v, 2) if abs(v) >= 1 else round(v, 8)
    if isinstance(v, str):
        s = v.strip()
        return s if s != "" else None
    return v


def to_num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def quarter_tags(label):
    """'Q1–Q4' → [1,4] (sin expandir, igual que COUNTIFS("*Q"&n&"*")); 'Q2–Q3' → [2,3]; 'Anual' → []."""
    return sorted({int(x) for x in re.findall(r"Q([1-4])", str(label or ""))})


def quarter_span(label):
    """Rango expandido para filtros del dashboard: 'Q1–Q3' → [1,2,3]."""
    t = quarter_tags(label)
    if len(t) == 2 and re.search(r"Q\d\s*[–-]\s*Q\d", str(label)):
        return list(range(t[0], t[1] + 1))
    return t


# ======================================================================================
def find_sheet(wb, key):
    if key.startswith("re:"):
        pat = re.compile(key[3:])
        hits = [s for s in wb.sheetnames if pat.search(s)]
        return hits[0] if hits else None
    return key if key in wb.sheetnames else None


def find_header_row(ws, required, alias=None, max_scan=40):
    alias = alias or {}
    for idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), start=1):
        cells = [str(c).strip() if c is not None else "" for c in row]
        hits = sum(1 for req in required if req in cells or (req in alias and any(re.match(alias[req], c) for c in cells)))
        if hits >= max(2, int(len(required) * 0.6)):
            return idx, cells
    return None, None


def read_table(wb, sheet, spec, log, wb_label, optional_sheet=False):
    if sheet is None or sheet not in wb.sheetnames:
        if not optional_sheet:
            log.error("MISSING_SHEET", f"Falta la hoja '{sheet}' en {wb_label}", workbook=wb_label, sheet=sheet)
        return None
    ws = wb[sheet]
    required, optional, alias = spec.get("required", []), spec.get("optional", []), spec.get("alias", {})
    hdr_row, cells = find_header_row(ws, required, alias)
    if hdr_row is None:
        log.error("HEADER_NOT_FOUND", f"No se encontró el encabezado en {wb_label}!{sheet}", workbook=wb_label, sheet=sheet)
        return None
    colmap = {}
    for want in required + optional:
        idx = cells.index(want) if want in cells else next((i for i, c in enumerate(cells) if want in alias and re.match(alias[want], c)), None)
        if idx is None:
            if want in required:
                log.error("MISSING_COLUMN", f"Falta la columna requerida '{want}' en {wb_label}!{sheet}", workbook=wb_label, sheet=sheet, column=want)
            else:
                log.note("MISSING_OPTIONAL_COLUMN", f"Columna opcional '{want}' ausente en {wb_label}!{sheet}", workbook=wb_label, sheet=sheet, column=want)
            continue
        colmap[want] = idx
    if spec.get("dynamic"):
        for i, c in enumerate(cells):
            if re.match(spec["dynamic"], c):
                colmap[c] = i
    if any(e["code"] == "MISSING_COLUMN" and e.get("sheet") == sheet and e.get("workbook") == wb_label for e in log.errors):
        return None
    key = spec.get("id") or required[0]
    id_pat = re.compile(spec["id_pattern"]) if spec.get("id_pattern") else None
    out = []
    for r_i, row in enumerate(ws.iter_rows(min_row=hdr_row + 1, values_only=True), start=hdr_row + 1):
        kval = row[colmap[key]] if colmap.get(key) is not None and colmap[key] < len(row) else None
        if kval is None or (isinstance(kval, str) and kval.strip() == ""):
            if id_pat and not spec.get("stop_blank"):
                continue
            break
        if id_pat and not id_pat.match(str(kval).strip()):
            continue
        rec = OrderedDict((name, row[idx] if idx < len(row) else None) for name, idx in colmap.items())
        rec["_row"] = r_i
        out.append(rec)
    return out


def read_kv(wb, sheet):
    kv = OrderedDict()
    if sheet in wb.sheetnames:
        for row in wb[sheet].iter_rows(values_only=True):
            if row and row[0] is not None and len(row) > 1 and row[1] is not None:
                kv[str(row[0]).strip()] = row[1]
    return kv


def read_label_matrix(wb, sheet, label, log, wb_label):
    """Matriz Indicador × columnas 'Qn-AAAA' (detectadas dinámicamente; otras columnas se ignoran)."""
    if sheet not in wb.sheetnames:
        return {"periods": [], "rows": {}}
    ws = wb[sheet]
    hdr, cols, res = None, {}, OrderedDict()
    for row in ws.iter_rows(values_only=True):
        if hdr is None:
            if row and row[0] == label:
                hdr = True
                cols = {v.strip(): i for i, v in enumerate(row) if isinstance(v, str) and re.fullmatch(r"Q[1-4]-\d{4}", v.strip())}
            continue
        if not row or row[0] is None:
            break
        res[str(row[0]).strip()] = {p: (norm(row[i]) if i < len(row) else None) for p, i in cols.items()}
    if hdr is None:
        log.warn("HIST_HEADER", f"No se encontró el encabezado '{label}' en {wb_label}!{sheet}")
    return {"periods": list(cols.keys()), "rows": res}


def find_label_row(wb, sheet, label, startswith=False):
    if sheet not in wb.sheetnames:
        return None
    for row in wb[sheet].iter_rows(values_only=True):
        if row and row[0] is not None:
            a = str(row[0]).strip()
            if a == label or (startswith and a.startswith(label)):
                return row
    return None


def matches(rec, where):
    for k, cond in where.items():
        v = rec.get(k)
        if isinstance(cond, dict):
            if "startswith" in cond and not (isinstance(v, str) and v.startswith(cond["startswith"])):
                return False
        elif v != cond:
            return False
    return True


def agg(records, mdef):
    rows = [r for r in records if matches(r, mdef.get("where", {}))]
    if mdef["agg"] == "count":
        return float(len(rows))
    fields = mdef["field"] if isinstance(mdef["field"], list) else [mdef["field"]]
    return float(sum((to_num(r.get(f)) or 0.0) for r in rows for f in fields))


def clean(rows):
    return [OrderedDict((k, norm(v)) for k, v in r.items() if k != "_row") for r in (rows or [])]


# ======================================================================================
# EXTRACCIÓN
# ======================================================================================
def read_schema(wb, schema, log, label):
    t = {}
    for key, spec in schema.items():
        sheet = find_sheet(wb, key)
        name = spec.get("alias_key") or key
        if spec.get("kind") in ("kv", "free", "matrix"):
            if sheet is None:
                log.error("MISSING_SHEET", f"Falta la hoja '{key}' en {label}", workbook=label, sheet=key)
            continue
        if sheet is None:
            log.error("MISSING_SHEET", f"Falta la hoja '{key}' en {label}", workbook=label, sheet=key)
            continue
        t[name] = read_table(wb, sheet, spec, log, label)
    return t


def extract_tc(wb, log, label):
    t = read_schema(wb, TC_SCHEMA, log, label)
    if log.errors:
        return None
    params = read_kv(wb, "Parametros")
    txns, nocache = [], []
    for r in t["Base_Transacciones"]:
        rec = OrderedDict((k, norm(v)) for k, v in r.items() if k != "_row")
        fecha = r.get("Fecha")
        if not isinstance(fecha, (dt.datetime, dt.date)):
            log.warn("INVALID_DATE", f"Base_Transacciones fila {r['_row']}: Fecha inválida", row=r["_row"], id=rec.get("TxnID"))
        if rec.get("Año") is None and isinstance(fecha, (dt.datetime, dt.date)):
            rec["Año"] = fecha.year; nocache.append(r["_row"])
        if rec.get("Trimestre") is None and isinstance(fecha, (dt.datetime, dt.date)):
            rec["Trimestre"] = (fecha.month - 1) // 3 + 1; nocache.append(r["_row"])
        if isinstance(rec.get("Año"), float):
            rec["Año"] = int(rec["Año"])
        if isinstance(rec.get("Trimestre"), float):
            rec["Trimestre"] = int(rec["Trimestre"])
        if rec.get("Tarjeta") is not None:
            rec["Tarjeta"] = str(rec["Tarjeta"]).split(".")[0].zfill(4)
        for f in ("Valor COP", "Familiar COP", "Personal COP", "No determinado COP", "Valor original"):
            if f in rec and rec[f] is not None and not isinstance(rec[f], (int, float)):
                rec[f] = to_num(rec[f])
        rec["Excepción IDs"] = re.findall(r"EX-\d+", rec.get("Excepción") or "")
        txns.append(rec)
    if nocache:
        log.warn("NO_CACHED_VALUE", f"Base_Transacciones: {len(set(nocache))} filas sin valor calculado en Año/Trimestre (libro guardado sin recalcular). "
                 "Se derivaron con YEAR/ROUNDUP(MONTH/3). Abra el libro en Excel, guárdelo y refresque.", rows=sorted(set(nocache))[:50])
    statements = []
    for r in t["Extractos_Input"]:
        rec = OrderedDict((k, norm(v)) for k, v in r.items() if k != "_row")
        fc = r.get("Fecha corte")
        rec["Mes"] = fc.strftime("%Y-%m") if isinstance(fc, (dt.datetime, dt.date)) else None
        for k in ("Año", "Trimestre"):
            if isinstance(rec.get(k), float):
                rec[k] = int(rec[k])
        statements.append(rec)
    benefits = clean(t["Beneficios_Input"])
    for b in benefits:
        for k in ("Año", "Trimestre"):
            if isinstance(b.get(k), float):
                b[k] = int(b[k])
    hist = read_label_matrix(wb, "Historico_Trimestral", "Indicador", log, label)
    resumen = OrderedDict()
    for lab in ["Consumo bruto", "Reversiones", "Número de compras", "Familiar / compartido atribuible", "Personal estimado", "No determinado", "Cuotas de manejo", "Seguros",
                "Intereses (resumen de extractos)", "Beneficios verificados (extracto)", "Costo neto (negativo = beneficio neto)", "HIGH", "MEDIUM", "LOW", "INFO",
                "Excepciones abiertas (todas las fechas)", "Estado general", "% no determinado del consumo"]:
        row = find_label_row(wb, "Resumen_Trimestral", lab)
        if row is not None:
            resumen[lab] = {"current": norm(row[1]) if len(row) > 1 else None, "previous": norm(row[2]) if len(row) > 2 else None}
    opt = {}
    for sheet, spec in TC_OPTIONAL_SHEETS.items():
        opt[sheet] = read_table(wb, sheet, spec, log, label, optional_sheet=True)
    pf = read_productos_financieros(wb, log, label)
    treasury = read_treasury(wb, log, label)
    return {"treasury": treasury, "params": {k: (v if isinstance(v, float) else norm(v)) for k, v in params.items()}, "transactions": txns, "statements": statements, "benefits": benefits, "cxc": clean(t["CxC_Input"]),
            "master": clean(t["Maestro_Productos"]), "review": clean(t["Revision_Productos"]), "crosscheck": clean(t["CrossCheck_Maestro"]),
            "framework": clean(t["Framework"]), "calendar": clean(t["Calendario_Arquitectura"]), "exceptions_raw": t["Excepciones_Central"], "historico": hist,
            "resumen": resumen, "continuity_sheet": opt.get("Continuidad_Hallazgos"), "lifecycle_sheet": opt.get("Ciclo_Vida_Productos"),
            "controls": clean(opt.get("Controles_Trimestrales")), "productos": pf, "coverage": clean(opt.get("Cobertura_Extractos"))}


def read_productos_financieros(wb, log, label):
    """Hoja Productos_Financieros: catálogo (encabezado ID_Producto … Comentario) + tabla mensual (encabezado Año … Comentario)."""
    if "Productos_Financieros" not in wb.sheetnames:
        log.warn("MISSING_SHEET", f"No existe Productos_Financieros en {label}: la página Utilidad de Productos queda vacía.")
        return {"catalog": [], "monthly": []}
    ws = wb["Productos_Financieros"]
    rows = list(ws.iter_rows(values_only=True))
    cat, mon, mode, hdr = [], [], None, None
    for row in rows:
        if row and row[0] == "ID_Producto":
            mode, hdr = "cat", [str(c).strip() if c else "" for c in row]
            continue
        if row and row[0] == "Año" and row[3] == "ID_Producto":
            mode, hdr = "mon", [str(c).strip() if c else "" for c in row]
            continue
        if mode and (not row or row[0] is None):
            if mode == "cat":
                mode = None
            continue
        if mode == "cat":
            cat.append(OrderedDict((h, norm(v)) for h, v in zip(hdr, row) if h))
        elif mode == "mon":
            mon.append(OrderedDict((h, norm(v)) for h, v in zip(hdr, row) if h))
    for m in mon:
        for k in ("Año", "Trimestre"):
            if isinstance(m.get(k), float):
                m[k] = int(m[k])
    if not cat or not mon:
        log.warn("PRODUCTS_EMPTY", "Productos_Financieros sin catálogo o sin tabla mensual.")
    return {"catalog": cat, "monthly": mon}


TREASURY_PARAMS = OrderedDict([("reserve_months", "Reserva de liquidez objetivo (meses de gasto)"), ("operating_balance", "Saldo operativo máximo en ahorros *9910 (COP)"),
                               ("savings_rate", "Tasa E.A. cuenta de ahorros *9910"), ("deposit_insurance_cap", "Tope seguro de depósitos Fogafín por persona y entidad (COP)"),
                               ("reference_rate", "Tasa de referencia E.A. (opcional, p. ej. CDT 90 días)"), ("utilization_threshold", "Umbral utilización de cupo")])


def read_treasury(wb, log, label):
    """Hojas de tesorería del libro TC (opcionales): Metricas_Tesoreria (matriz por Clave + líneas de crédito) y Tesoreria_Input."""
    if "Metricas_Tesoreria" not in wb.sheetnames or treasury_inputs.SHEET not in wb.sheetnames:
        log.warn("MISSING_SHEET", f"{label}: faltan Metricas_Tesoreria o {treasury_inputs.SHEET}; la vista Tesorería queda vacía.")
        return None
    rows = list(wb["Metricas_Tesoreria"].iter_rows(values_only=True))
    hdr_i = next((i for i, r in enumerate(rows) if r and r[0] == "Clave" and len(r) > 1 and r[1] == "Indicador"), None)
    if hdr_i is None:
        log.error("HEADER_NOT_FOUND", f"No se encontró el encabezado Clave / Indicador en {label}!Metricas_Tesoreria", workbook=label, sheet="Metricas_Tesoreria")
        return None
    hdr = rows[hdr_i]
    pcols = [(j, str(v).strip()) for j, v in enumerate(hdr) if isinstance(v, str) and re.fullmatch(r"Q[1-4]-\d{4}", v.strip())]
    dcol = next((j for j, v in enumerate(hdr) if v == "Definición"), None)
    metrics, sections, section, nocache = OrderedDict(), [], None, []
    for r in rows[hdr_i + 1:]:
        if not r or (r[0] is None and r[1] is None):
            continue
        if r[0] == "Líneas de crédito":
            break
        if r[0] is None and isinstance(r[1], str):
            section = r[1].strip(); sections.append(section); continue
        key = str(r[0]).strip()
        if key.startswith("_"):
            continue
        vals = OrderedDict()
        for j, per in pcols:
            v = r[j] if j < len(r) else None
            if v is None:
                nocache.append(f"{key} {per}")
            vals[per] = _r(v, 6) if isinstance(v, float) else (None if v in ("n/d", "") else v)
        metrics[key] = OrderedDict([("label", norm(r[1])), ("unit", norm(r[2])), ("section", section), ("values", vals),
                                    ("definition", norm(r[dcol]) if dcol is not None and dcol < len(r) else None)])
    if nocache:
        log.warn("NO_CACHED_VALUE", f"Metricas_Tesoreria: {len(nocache)} celdas sin valor calculado (libro guardado sin recalcular). Abra el libro en Excel, guárdelo y refresque.",
                 cells=nocache[:20])
    fac, fh = [], None
    for i, r in enumerate(rows):
        if r and r[0] == "N°" and len(r) > 2 and r[1] == "Banco":
            fh = [str(c).strip() if c else "" for c in r]
            for rr in rows[i + 1:]:
                if not rr or not isinstance(rr[0], (int, float)):
                    break
                if not rr[1]:
                    continue
                fac.append(OrderedDict((h, (None if v == "n/d" else norm(v))) for h, v in zip(fh, rr) if h and h != "N°"))
            break
    if fh is None:
        log.warn("TREASURY_NO_FACILITIES", "Metricas_Tesoreria sin la tabla 'Líneas de crédito'.")
    inputs = treasury_inputs.read_sheet(wb) or []
    for x in inputs:
        for k in list(x):
            if isinstance(x[k], (dt.datetime, dt.date)):
                x[k] = x[k].strftime("%Y-%m-%d")
    return {"periods": [p for _, p in pcols], "sections": sections, "metrics": metrics, "facilities": fac, "inputs": inputs}


def build_treasury(tc, derived, log):
    """Dataset de la vista Tesorería: valores de Metricas_Tesoreria tal como los calcula Excel + conciliación de Tesoreria_Input vs libro de bancos."""
    tr = tc.get("treasury")
    if not tr:
        return OrderedDict([("metadata", {"available": False}), ("periods", []), ("metrics", {}), ("facilities", []), ("monthly", [])])
    if derived is not None:
        diffs, missing = treasury_inputs.compare(tr["inputs"], derived)
        by = {x["_mes"]: x for x in tr["inputs"]}
        for d in derived:
            s_ = by.get(d["Mes"])
            if s_ is None:
                continue
            for field, label in treasury_inputs.FIELD_LABEL.items():
                a, b = to_num(s_.get(label)), d.get(field)
                if a is None and b is None:
                    continue
                log.check(f"Tesorería {d['Mes']} · {label}", "Tesorería (insumos)", "Auditoria_Bancos (derivado)", b, f"Tesoreria_Input · {label}", a,
                          tol=1e-6 if field == "fidu_rate" else 1.0)
        if missing:
            log.warn("TREASURY_MONTHS_MISSING", f"Tesoreria_Input no tiene {len(missing)} mes(es) que sí están en el libro de bancos: {', '.join(missing)}. "
                     "Ejecute: python scripts/treasury_inputs.py sync", months=missing)
    monthly = []
    for x in tr["inputs"]:
        monthly.append(OrderedDict([("Año", x.get("Año")), ("Trimestre", x.get("Trimestre")), ("Mes", x["_mes"])] +
                                   [(f, to_num(x.get(lab))) for f, lab in treasury_inputs.FIELD_LABEL.items()] + [("liquidity", to_num(x.get("Liquidez total")))]))
    params = OrderedDict((k, tc["params"].get(v)) for k, v in TREASURY_PARAMS.items())
    for p in tr["periods"]:
        st = (tr["metrics"].get("chk_status") or {}).get("values", {}).get(p)
        if st not in (None, "OK"):
            log.warn("TREASURY_CONTROL", f"Metricas_Tesoreria {p}: resultado de controles = {st}")
    return OrderedDict([
        ("metadata", {"available": True, "source": "Sistema_Auditoria_TC.xlsx › Metricas_Tesoreria / Tesoreria_Input", "params": params, "sections": tr["sections"],
                      "rules": ["Todas las cifras se leen de Metricas_Tesoreria tal como las calcula Excel; el dashboard no recalcula.",
                                "Tesoreria_Input se concilia en cada refresh contra Auditoria_Bancos (saldos de fin de mes, GMF, intereses, rendimientos, retención y gasto externo).",
                                "Costo de oportunidad: estimación con metodología propuesta (saldo ocioso × diferencial de tasas); no es un costo contable."]}),
        ("periods", tr["periods"]), ("metrics", tr["metrics"]), ("facilities", tr["facilities"]), ("monthly", monthly)])


def extract_bank(wb, log, label):
    t = read_schema(wb, BANK_SCHEMA, log, label)
    if log.errors:
        return None
    moves = []
    for r in t["Base_Movimientos"]:
        rec = OrderedDict((k, norm(v)) for k, v in r.items() if k != "_row")
        fecha = r.get("Fecha")
        rec["Año"] = int(rec["Año"]) if isinstance(rec.get("Año"), (int, float)) else (fecha.year if isinstance(fecha, (dt.datetime, dt.date)) else None)
        if rec["Año"] is None:
            log.warn("INVALID_DATE", f"Base_Movimientos fila {r['_row']}: Fecha inválida", row=r["_row"], id=rec.get("ID"))
        for f in ("Valor", "Entrada", "Salida", "Saldo después"):
            if rec.get(f) is not None and not isinstance(rec[f], (int, float)):
                rec[f] = to_num(rec[f])
        if rec.get("Entrada") is None and isinstance(rec.get("Valor"), (int, float)):
            rec["Entrada"] = max(rec["Valor"], 0.0); rec["Salida"] = max(-rec["Valor"], 0.0)
            log.warn("NO_CACHED_VALUE", f"Base_Movimientos {rec.get('ID')}: Entrada/Salida sin valor calculado; derivadas de Valor.")
        rec["Trimestre_n"] = int(rec["Trimestre"][1]) if isinstance(rec.get("Trimestre"), str) and re.fullmatch(r"Q[1-4]", rec["Trimestre"]) else None
        rec["Excepción IDs"] = re.findall(r"EX-\d+", rec.get("Excepción") or "")
        moves.append(rec)
    # Balance continuity (todas las secciones; formato 9910: H/M, formato Fiducuenta: J/O)
    bc = []
    for row in wb["Balance_Continuity"].iter_rows(values_only=True):
        if row and isinstance(row[0], str) and (row[0].startswith("Bancolombia *") or row[0].startswith("Fiducuenta *")) and isinstance(row[1], str) and row[1] not in ("Período", "Mes"):
            fidu = row[0].startswith("Fiducuenta")
            per = row[1]
            m = re.match(r"Q([1-4])-(\d{4})", per)
            year = int(m.group(2)) if m else (int(per[:4]) if re.match(r"\d{4}-\d{2}", per) else None)
            bc.append({"Cuenta": row[0], "Período": per, "Año": year, "Desde": norm(row[2]), "Hasta": norm(row[3]), "Saldo inicial": norm(row[4]),
                       "Saldo final extracto": norm(row[9] if fidu else row[7]), "Estado": norm(row[14] if fidu else row[12]),
                       "Intereses": norm(row[13]) if not fidu else norm(row[7]), "Saldo promedio": norm(row[14]) if not fidu else None})
    fe = {}
    for lab in ["Total Gross Bank Movements", "Interno", "Pago TC", "Inversión (capital)", "Total External Economic Flows"]:
        row = find_label_row(wb, "Flujos_Economicos", lab)
        if row is not None:
            fe[lab] = {"Entradas": norm(row[1]), "Salidas": norm(row[2])}
    res = OrderedDict()
    for lab in ["Movimientos en la base consolidada", "Control doble conteo (debe ser 0)", "HIGH", "MEDIUM", "LOW", "INFO"]:
        row = find_label_row(wb, "Resumen", lab, startswith=True)
        res[lab] = norm(row[1]) if row is not None and len(row) > 1 else None
    title = (find_label_row(wb, "Resumen", "Auditoría Anual", startswith=True) or [None])[0]
    notes = [norm(r[0]) for r in wb["Notas_Metodologia"].iter_rows(values_only=True) if r and r[0]]
    cal = []
    fw = find_sheet(wb, "re:^Framework")
    for row in wb[fw].iter_rows(values_only=True):
        if row and isinstance(row[0], str) and re.match(r"^Q[1-4]-\d{4}", row[0].strip()):
            cal.append({"Período": row[0].strip(), "Ejecución": norm(row[1])})
    opt = {s: read_table(wb, s, spec, log, label, optional_sheet=True) for s, spec in BANK_OPTIONAL_SHEETS.items() if spec.get("kind") != "matrix"}
    hist = read_label_matrix(wb, "Historico_Trimestral_Bancos", "Indicador", log, label)
    inventory = [r for r in clean(t["Inventario"]) if not str(r.get("Banco") or "").startswith("Saldo agregado")]
    return {"transactions": moves, "material_2025": clean(t["Movimientos_Materiales"]), "inventory": inventory, "transfers_2025": clean(t["Transferencias_Internas"]),
            "crosscheck": clean(t["CrossCheck_Maestro"]), "framework": clean(t["Framework"]), "calendar": cal, "exceptions_raw": t["Excepciones"],
            "balance_continuity": bc, "flujos_2025": fe, "resumen_2025": res, "title": norm(title), "notes": notes, "controls": clean(opt.get("Controles_Trimestrales")),
            "card_payments": clean(opt.get("Pagos_TC_Trimestral")), "material": clean(opt.get("Materiales_Trimestral")),
            "transfers_monthly": clean(opt.get("Transferencias_Mensuales")), "fiducuentas": clean(opt.get("Fiducuenta_TC")), "historico": hist}


# ======================================================================================
# EXCEPCIONES (registro central único + registro bancario 2025 congelado)
# ======================================================================================
def _exc_record(r, src_sheet, cfg):
    if src_sheet == "Excepciones_Central":
        acct, concept, ref, last, bank = r.get("Tarjeta"), r.get("Comercio"), r.get("TxnID"), r.get("Fecha último cambio de estado"), r.get("Banco")
    else:
        acct, concept, ref, last, bank = r.get("Cuenta / producto"), r.get("Movimiento"), r.get("Ref. base"), r.get("Fecha último cambio"), r.get("Banco")
    estado = norm(r.get("Estado"))
    estado_norm = cfg.get("status_normalization", {}).get(estado, estado)
    rec = OrderedDict([
        ("ID", norm(r.get("ID"))), ("Año", int(r["Año"]) if isinstance(r.get("Año"), (int, float)) else norm(r.get("Año"))), ("Trimestre", norm(r.get("Trimestre"))),
        ("Fecha detección", norm(r.get("Fecha detección"))), ("Origen", norm(r.get("Origen"))), ("Fecha", norm(r.get("Fecha"))), ("Cuenta/Tarjeta", norm(acct)),
        ("Banco", norm(bank)), ("Producto", norm(r.get("Producto"))), ("Concepto", norm(concept)), ("Monto (COP)", to_num(r.get("Monto (COP)"))),
        ("Tipo de monto", norm(r.get("Tipo de monto"))), ("Categoría", norm(r.get("Categoría"))), ("Tipo", norm(r.get("Tipo"))), ("Riesgo", norm(r.get("Riesgo"))),
        ("Money Pro", norm(r.get("Money Pro"))), ("Splitwise", norm(r.get("Splitwise"))), ("Explicación", norm(r.get("Explicación"))), ("Acción", norm(r.get("Acción"))),
        ("Evidencia", norm(r.get("Evidencia"))), ("Referencia", norm(ref)), ("Estado", estado_norm), ("Estado original", estado), ("Fecha último cambio", norm(last)),
        ("Comentario de cierre", norm(r.get("Comentario de cierre"))), ("Hallazgo relacionado", norm(r.get("Hallazgo relacionado"))),
        ("Estado anterior", cfg.get("status_normalization", {}).get(norm(r.get("Estado anterior")), norm(r.get("Estado anterior")))),
        ("Evidencia nueva", norm(r.get("Evidencia nueva"))), ("Conclusión de auditoría", norm(r.get("Conclusión de auditoría")))])
    return rec


def build_exceptions(tc, bank, cfg, log, tc_label, bank_label):
    bank_pat = cfg.get("bank_origin_pattern", "Bancari")
    tc_rows = [(_exc_record(r, "Excepciones_Central", cfg), r["_row"]) for r in tc["exceptions_raw"]]
    ba_rows = [(_exc_record(r, "Excepciones", cfg), r["_row"]) for r in bank["exceptions_raw"]]
    for regname, rows in (("Excepciones_Central", tc_rows), ("Excepciones", ba_rows)):
        seen = defaultdict(int)
        for rec, row in rows:
            seen[rec["ID"]] += 1
            for f in ("Año", "Riesgo", "Estado"):
                if rec.get(f) in (None, ""):
                    log.warn("REQUIRED_EMPTY", f"{regname} {rec['ID']}: campo '{f}' vacío", sheet=regname, id=rec["ID"])
            if rec.get("Riesgo") and rec["Riesgo"] not in RISK_ORDER:
                log.warn("UNKNOWN_RISK", f"{regname} {rec['ID']}: riesgo desconocido '{rec['Riesgo']}'", id=rec["ID"])
            if rec["Estado"] not in cfg.get("preferred_statuses", []) and rec["Estado"] not in cfg.get("open_statuses", []):
                log.note("STATUS_NOT_PREFERRED", f"{rec['ID']}: estado '{rec['Estado']}' fuera de la lista preferida", id=rec["ID"])
        for i, n in seen.items():
            if n > 1:
                log.error("DUPLICATE_ID", f"ID de excepción duplicado {i} dentro de {regname}", sheet=regname, id=i)
    by_id = OrderedDict()
    for rec, row in tc_rows:
        rec["Source"] = "Bank & Cash" if bank_pat in (rec.get("Origen") or "") else "Credit Card"
        rec["present_in"] = [f"{tc_label} › Excepciones_Central (fila {row})"]
        by_id[rec["ID"]] = rec
    compare = ["Año", "Trimestre", "Origen", "Monto (COP)", "Riesgo", "Explicación", "Estado"]
    diffs_all = []
    for rec, row in ba_rows:
        rec["Source"] = "Bank & Cash"
        loc = f"{bank_label} › Excepciones (fila {row})"
        if rec["ID"] in by_id:
            other = by_id[rec["ID"]]
            diffs = [f for f in compare if (other.get(f) or None) != (rec.get(f) or None)]
            # comentario del usuario: se conservan ambos (el central es el registro único)
            if rec.get("Comentario de cierre") and rec["Comentario de cierre"] != other.get("Comentario de cierre"):
                other["Comentario (registro bancos)"] = rec["Comentario de cierre"]
                diffs.append("Comentario de cierre")
            if diffs:
                diffs_all.append((rec["ID"], diffs))
            other["present_in"].append(loc)
            other["duplicate_consistent"] = not diffs
        else:
            rec["present_in"] = [loc]
            by_id[rec["ID"]] = rec
    if diffs_all:
        log.warn("REGISTER_DIFFERENCES", "Diferencias entre Excepciones_Central y el registro de Auditoria_Bancos › Excepciones (se usa el central como registro único): "
                 + "; ".join(f"{i}: {', '.join(d)}" for i, d in diffs_all), ids=[i for i, _ in diffs_all])
    out = []
    open_st = cfg.get("open_statuses", ["Open", "Review"])
    for rec in by_id.values():
        rec["quarter_tags"] = quarter_tags(rec.get("Trimestre"))
        rec["quarter_span"] = quarter_span(rec.get("Trimestre"))
        rec["is_open"] = rec.get("Estado") in open_st
        rec["is_monitor"] = rec.get("Estado") == "Monitor"
        prev = rec.get("Estado anterior")
        rec["changed_this_update"] = bool(prev) and prev != rec.get("Estado")
        rec["closed_this_update"] = bool(prev) and prev in open_st and not rec["is_open"]
        rec["risk_rank"] = RISK_ORDER.index(rec["Riesgo"]) if rec.get("Riesgo") in RISK_ORDER else 9
        out.append(rec)
    out.sort(key=lambda r: int(re.sub(r"\D", "", r["ID"]) or 0))
    return out, diffs_all


# ======================================================================================
# CONTINUIDAD
# ======================================================================================
def read_continuity(cfg, tc, log):
    c = cfg.get("continuity", {})
    out = {"findings": [], "context_rules": [], "lifecycle": [], "source": {}, "status_years": []}
    rows = tc.get("continuity_sheet")
    if rows is not None:
        rows = clean(rows)
        out["source"]["findings"] = "Sistema_Auditoria_TC › Continuidad_Hallazgos"
    else:
        import csv
        path = resolve(c.get("findings_csv", "continuity/Findings_Continuity_2025.csv"))
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = [{k: (v.strip() or None) if isinstance(v, str) else v for k, v in r.items()} for r in csv.DictReader(f)]
            out["source"]["findings"] = os.path.relpath(path, ROOT) + " (CSV interino)"
            log.warn("CONTINUITY_CSV", "Se usa el CSV interino de continuidad: falta la hoja Continuidad_Hallazgos.")
        else:
            log.warn("CONTINUITY_MISSING", "Sin matriz de continuidad (ni hoja ni CSV).")
    years = sorted({int(m.group(1)) for r in rows for k in r for m in [re.match(r"^(\d{4})_Status$", k)] if m})
    out["status_years"] = years
    for r in rows:
        if r.get("Original_Year") is not None:
            try:
                r["Original_Year"] = int(float(r["Original_Year"]))
            except (TypeError, ValueError):
                log.warn("CONTINUITY_YEAR", f"Continuidad {r.get('Finding_ID')}: Original_Year no numérico")
        code = (r.get("Continuity_Category") or "")[:1]
        r["category_code"] = code if code in CATEGORIES else "?"
        if code not in CATEGORIES:
            log.warn("CONTINUITY_CATEGORY", f"Continuidad {r.get('Finding_ID')}: categoría desconocida '{r.get('Continuity_Category')}'")
        # estado y excepción vinculada del año más reciente disponible (sin fijar el año)
        for y in sorted(years, reverse=True):
            if r.get(f"{y}_Status"):
                r["Latest_Status_Year"], r["Latest_Status"] = y, r.get(f"{y}_Status")
                r["Latest_Linked_Exception"] = r.get(f"{y}_Linked_Exception")
                break
        if not r.get("Latest_Status"):  # compatibilidad con el CSV v1 (columnas Status_AAAA)
            v1 = sorted((int(m.group(1)), k) for k in r for m in [re.match(r"^Status_(\d{4})$", k)] if m and r.get(k))
            if v1:
                r["Latest_Status_Year"], r["Latest_Status"] = v1[-1][0], r.get(v1[-1][1])
        (out["context_rules"] if (r.get("Record_Type") or "").lower().startswith("context") else out["findings"]).append(r)
    lc = tc.get("lifecycle_sheet")
    if lc is not None:
        out["lifecycle"] = clean(lc)
        out["source"]["lifecycle"] = "Sistema_Auditoria_TC › Ciclo_Vida_Productos"
    for r in out["lifecycle"]:
        if r.get("Tarjeta") is not None:
            r["Tarjeta"] = str(r["Tarjeta"]).split(".")[0].zfill(4)
    ids = [r["Finding_ID"] for r in out["findings"] + out["context_rules"]]
    for d in sorted({i for i in ids if ids.count(i) > 1}):
        log.error("DUPLICATE_ID", f"Continuidad: Finding_ID duplicado {d}")
    return out


def apply_continuity(exceptions, cont, current_year, log):
    base = {r["Finding_ID"]: r for r in cont["findings"]}
    for e in exceptions:
        b = base.get(e["ID"])
        y = e.get("Año") if isinstance(e.get("Año"), int) else None
        e["is_historical"] = bool(y is not None and y < current_year)
        e["continuity"] = None
        if b:
            e["continuity"] = {"code": b["category_code"], "category": b.get("Continuity_Category"), "rule": b.get("Carry_Forward_Rule"),
                               "latest_status": b.get("Latest_Status"), "latest_year": b.get("Latest_Status_Year"), "linked": b.get("Latest_Linked_Exception"),
                               "resolution": b.get("Resolution"), "response": b.get("Respuesta_Usuario")}
            if b.get("Original_Year") and y and b["Original_Year"] != y:
                log.error("BASELINE_YEAR_MISMATCH", f"{e['ID']}: Original_Year {b['Original_Year']} ≠ Año {y} (posible reutilización de ID)")
        elif e["is_historical"]:
            log.warn("HISTORICAL_NOT_IN_BASELINE", f"{e['ID']} ({y}) es histórica y no tiene fila en Continuidad_Hallazgos.")
        if e["is_historical"]:
            code = (e["continuity"] or {}).get("code", "?")
            e["group"] = EXC_GROUP.get(code, "historico_resuelto")
            e["register_class"] = "Hallazgo histórico"
        else:
            e["group"] = "actual"
            e["register_class"] = "Excepción actual"
        e["counts_in_current_kpis"] = not e["is_historical"]
        e["counts_in_current_open"] = (not e["is_historical"]) and e["is_open"]
    for fid in base:
        if not any(e["ID"] == fid for e in exceptions):
            log.warn("BASELINE_ORPHAN", f"Continuidad {fid}: no existe esa ID en los registros")
    return exceptions


def context_hits(tc, bank, cont, current_year):
    rules = [r for r in cont["findings"] + cont["context_rules"] if r.get("Context_Match_Pattern") and r.get("Context_Match_Field")]
    hits = []

    def m(rule, text):
        try:
            return text is not None and re.search(rule["Context_Match_Pattern"], str(text), flags=re.IGNORECASE) is not None
        except re.error:
            return False
    for t in tc["transactions"]:
        if isinstance(t.get("Año"), int) and t["Año"] >= current_year:
            for r in rules:
                if r["Context_Match_Field"] != "Extractos_Input" and any(m(r, t.get(f)) for f in r["Context_Match_Field"].split("|") if f in t):
                    hits.append({"record_id": t["TxnID"], "dataset": "Base_Transacciones", "date": t.get("Fecha"), "amount": t.get("Valor COP"),
                                 "text": t.get("Comercio normalizado"), "finding_id": r["Finding_ID"], "rule": r.get("Carry_Forward_Rule")})
    for s in tc["statements"]:
        if isinstance(s.get("Año"), int) and s["Año"] >= current_year and ((s.get("Intereses corrientes") or 0) > 0 or (s.get("Intereses mora") or 0) > 0):
            for r in rules:
                if r["Context_Match_Field"] == "Extractos_Input":
                    hits.append({"record_id": f"{s.get('Producto')} {s.get('Fecha corte')}", "dataset": "Extractos_Input", "date": s.get("Fecha corte"),
                                 "amount": (s.get("Intereses corrientes") or 0) + (s.get("Intereses mora") or 0), "text": "Intereses en extracto",
                                 "finding_id": r["Finding_ID"], "rule": r.get("Carry_Forward_Rule")})
    for mv in bank["transactions"]:
        if isinstance(mv.get("Año"), int) and mv["Año"] >= current_year:
            for r in rules:
                if any(m(r, mv.get(f)) for f in r["Context_Match_Field"].split("|") if f in mv):
                    hits.append({"record_id": mv["ID"], "dataset": "Base_Movimientos", "date": mv.get("Fecha"), "amount": mv.get("Valor"),
                                 "text": mv.get("Descripción (extracto)"), "finding_id": r["Finding_ID"], "rule": r.get("Carry_Forward_Rule")})
    return hits


def lifecycle_alerts(tc, cont, log):
    alerts = []
    for lc in cont["lifecycle"]:
        st, cd = lc.get("Status"), lc.get("Closure_Date")
        if st in ("Closed", "Replaced") and cd:
            for t in tc["transactions"]:
                if t.get("Tarjeta") == lc["Tarjeta"] and t.get("Fecha") and t["Fecha"] > cd and t.get("Es compra") == "Sí":
                    alerts.append({"severity": "HIGH", "card": lc["Tarjeta"], "record": t["TxnID"], "date": t["Fecha"], "amount": t.get("Valor COP"),
                                   "message": f"Actividad en *{lc['Tarjeta']} después de su cierre ({cd})"})
    for a in alerts:
        log.warn("CLOSED_CARD_ACTIVITY", "HIGH — " + a["message"] + f" ({a['record']}, {a['date']})", severity="HIGH")
    return alerts


def next_exception_id(exceptions):
    nums = [int(m.group(1)) for e in exceptions for m in [re.match(r"EX-(\d+)$", e["ID"] or "")] if m]
    return f"EX-{(max(nums) if nums else 0) + 1:02d}"


# ======================================================================================
# DATASETS
# ======================================================================================
def period_keys(records, yk="Año", qk="Trimestre"):
    return sorted({(r[yk], r[qk]) for r in records if isinstance(r.get(yk), int) and isinstance(r.get(qk), int)})


def tc_period_aggregates(tc):
    src = {"Base_Transacciones": tc["transactions"], "Extractos_Input": tc["statements"], "Beneficios_Input": tc["benefits"]}
    out = OrderedDict()
    for (y, q) in period_keys(tc["transactions"]):
        m = OrderedDict()
        for k, d in TC_METRICS.items():
            m[k] = agg([r for r in src[d["source"]] if r.get("Año") == y and r.get("Trimestre") == q], d)
        m["net_cost"] = m["fees"] + m["insurance"] + m["interest"] - m["benefits"]
        out[f"Q{q}-{y}"] = m
    return out


def build_credit_cards(tc, exceptions, cont):
    txns = tc["transactions"]
    cards = OrderedDict()
    for m in tc["master"]:
        prod = m.get("Producto en base (si aplica)")
        key = prod if prod and not str(prod).startswith("(") else f"{m.get('Banco')} {m.get('Franquicia')} ({m.get('No. maestro')})"
        cards[key] = {"Producto": key, "Banco": m.get("Banco"), "No. maestro": m.get("No. maestro"), "Plan": m.get("Plan"), "Franquicia": m.get("Franquicia"),
                      "Cupo": m.get("Cupo"), "Cuota actual": m.get("Cuota actual"), "Beneficio": m.get("Beneficio"), "Estado maestro": m.get("Estado maestro"), "in_base": False}
    for r in txns:
        p = r["Producto"]
        if p not in cards:
            cards[p] = {"Producto": p, "Banco": r["Banco"], "No. maestro": None, "Estado maestro": None, "in_base": True}
        cards[p]["in_base"] = True
        cards[p]["Banco base"] = r["Banco"]
    for c in cards.values():
        c["tokens"] = sorted(set(re.findall(r"\d{4}", f"{c['Producto']} {c.get('No. maestro') or ''}")))
    card_summary = []
    for (y, q) in period_keys(txns):
        for p in cards:
            rows = [r for r in txns if r["Año"] == y and r["Trimestre"] == q and r["Producto"] == p]
            st = [s for s in tc["statements"] if s.get("Año") == y and s.get("Trimestre") == q and s.get("Producto") == p]
            bn = [b for b in tc["benefits"] if b.get("Año") == y and b.get("Trimestre") == q and b.get("Producto") == p]
            row = OrderedDict([("Año", y), ("Trimestre", q), ("Producto", p), ("Banco", cards[p].get("Banco base") or cards[p].get("Banco"))])
            for mk in ("gross_spend", "purchases", "family", "personal", "undetermined", "fees", "insurance"):
                row[mk] = _r(agg(rows, TC_METRICS[mk]))
            row["interest"] = _r(agg(st, TC_METRICS["interest"]))
            row["benefits"] = _r(agg(bn, TC_METRICS["benefits"]))
            row["net_cost"] = _r(row["fees"] + row["insurance"] + row["interest"] - row["benefits"])
            utils = [s["Utilización"] for s in st if isinstance(s.get("Utilización"), (int, float)) and s.get("Moneda") == "COP"]
            row["max_utilization"] = max(utils) if utils else None
            row["statements"] = len([s for s in st if s.get("Moneda") == "COP"])
            if any(row[k] for k in ("gross_spend", "fees", "insurance", "interest", "benefits")) or st:
                card_summary.append(row)
    params = tc["params"]
    return OrderedDict([
        ("metadata", {"parameters": params, "parameter_period": params.get("Etiqueta"),
                      "thresholds": {k: v for k, v in params.items() if k.startswith(("Umbral", "Ventana", "Valor por punto"))},
                      "metric_definitions": TC_METRICS,
                      "net_cost_rule": "Costo neto = Cuotas de manejo + Seguros + Intereses − Beneficios (extracto). Igual a Historico_Trimestral · 'Costo neto'."}),
        ("cards", list(cards.values())), ("transactions", txns), ("statements", tc["statements"]), ("card_summary", card_summary),
        ("benefits", tc["benefits"]), ("receivables", tc["cxc"]), ("product_review", {"period": params.get("Etiqueta"), "rows": tc["review"]}),
        ("master", tc["master"]), ("master_crosscheck", tc["crosscheck"]), ("resumen_trimestral", {"period": params.get("Etiqueta"), "rows": tc["resumen"]}),
        ("historico_trimestral", tc["historico"]), ("exceptions", [e["ID"] for e in exceptions if e["Source"] == "Credit Card"]),
    ])


def build_bank(bank, exceptions):
    mv = bank["transactions"]
    accounts = sorted({m["Cuenta"] for m in mv})
    monthly = []
    for (y, mes) in sorted({(m["Año"], m["Mes"]) for m in mv if m.get("Mes") and m.get("Año")}):
        rows = [m for m in mv if m["Año"] == y and m["Mes"] == mes]
        row = OrderedDict([("Año", y), ("Mes", mes), ("Trimestre", rows[0]["Trimestre_n"])])
        for k in ("external_in", "external_out", "internal_in", "internal_out", "investment_in", "investment_out", "card_payments", "gross_in", "gross_out", "investment_income"):
            row[k] = _r(agg(rows, BANK_METRICS[k]))
        monthly.append(row)
    balances = []
    for a in accounts:
        rows = sorted([m for m in mv if m["Cuenta"] == a], key=lambda m: (m["Fecha"] or "", m["ID"]))
        line_bal = [m for m in rows if isinstance(m.get("Saldo después"), (int, float))]
        for mes in sorted({m["Mes"] for m in rows if m.get("Mes")}):
            mr = [m for m in line_bal if m["Mes"] == mes]
            if mr:
                balances.append({"Cuenta": a, "Mes": mes, "Año": mr[-1]["Año"], "Trimestre": mr[-1]["Trimestre_n"], "Saldo final": mr[-1]["Saldo después"], "Fuente": "Base_Movimientos (saldo de la última línea)"})
    # Fiducuentas sin detalle: saldo final desde el resumen del extracto (Fiducuenta_TC / Balance_Continuity)
    for f in bank["fiducuentas"]:
        acct = "Bancolombia " + f["Cuenta"]
        if not any(b["Cuenta"] == acct and b["Mes"] == f["Mes"] for b in balances):
            balances.append({"Cuenta": acct, "Mes": f["Mes"], "Año": f["Año"], "Trimestre": int(str(f["Trimestre"]).lstrip("Q")), "Saldo final": f["Saldo final"],
                             "Fuente": "Extracto Fiduciaria (resumen)"})
    for bcr in bank["balance_continuity"]:
        if bcr["Cuenta"].startswith("Fiducuenta") and bcr["Año"]:
            acct = "Bancolombia " + bcr["Cuenta"]
            if not any(b["Cuenta"] == acct and b["Mes"] == bcr["Período"] for b in balances):
                balances.append({"Cuenta": acct, "Mes": bcr["Período"], "Año": bcr["Año"], "Trimestre": (int(bcr["Período"][5:7]) - 1) // 3 + 1,
                                 "Saldo final": bcr["Saldo final extracto"], "Fuente": "Balance_Continuity"})
    balances.sort(key=lambda b: (b["Cuenta"], b["Mes"]))
    return OrderedDict([
        ("metadata", {"title": bank["title"], "metric_definitions": BANK_METRICS, "methodology_notes": bank["notes"]}),
        ("accounts", bank["inventory"]), ("transactions", mv), ("monthly_cashflow", monthly), ("monthly_balances", balances),
        ("internal_transfers", {"monthly": bank["transfers_monthly"], "matrix_2025": bank["transfers_2025"]}),
        ("card_payments", bank["card_payments"]), ("material_movements", bank["material"] or bank["material_2025"]), ("material_2025", bank["material_2025"]),
        ("balance_continuity", bank["balance_continuity"]), ("historico_trimestral", bank["historico"]), ("flujos_2025", bank["flujos_2025"]),
        ("master_crosscheck", bank["crosscheck"]), ("exceptions", [e["ID"] for e in exceptions if e["Source"] == "Bank & Cash"]),
    ])


def build_products(tc, bank, cfg):
    pf = tc["productos"]
    cat = pf["catalog"]
    mon = pf["monthly"]
    fid = bank["fiducuentas"]
    tc_id = next((c["ID_Producto"] for c in cat if (c.get("Tipo de producto") or "").lower() == "fiducuenta tc"), None)
    tc_num = next((c.get("Número") for c in cat if c["ID_Producto"] == tc_id), None)
    for f in fid:
        f["Trimestre_n"] = int(str(f.get("Trimestre") or "Q0").lstrip("Q") or 0)
        f["is_tc"] = str(f.get("Número")) == str(tc_num)
    rate = tc["params"].get("Valor por punto Puntos Colombia (COP)")
    return OrderedDict([
        ("metadata", {"fiducuenta_tc_id": tc_id, "fiducuenta_tc_numero": tc_num, "points_cop": rate,
                      "rules": ["Costo total = cuotas de manejo + intereses pagados + seguros + otros costos (GMF / retención).",
                                "Beneficios totales = cashback + descuentos + puntos monetizados + otros beneficios + intereses ganados.",
                                "Valor neto = beneficios totales − costo total. ROI = valor neto / costo total (solo tarjetas; n/a si el costo es 0).",
                                "Puntos monetizados = puntos ganados × valor realizado por punto (Parametros). Beneficios sin metodología no se monetizan.",
                                "Capital transferido a/desde fiducuentas = movimiento interno (no es ingreso ni gasto). Solo el rendimiento es ingreso financiero.",
                                "Beneficio potencial (teórico) = consumo × puntos por COP del catálogo × valor del punto, o beneficio esperado del maestro; Beneficio real = beneficios verificados en extracto.",
                                "Costo de oportunidad: no se calcula (no hay metodología aprobada)."]}),
        ("catalog", cat), ("monthly", mon), ("fiducuentas", fid), ("coverage", tc.get("coverage") or [])])


def build_timeline(tc, bank, exceptions, cfg, sources, log):
    today = dt.date.today()
    years = sorted({r["Año"] for r in tc["transactions"] if isinstance(r.get("Año"), int)} | {m["Año"] for m in bank["transactions"] if isinstance(m.get("Año"), int)} | {today.year})
    controls = {"tc": tc["controls"] or [], "bank": bank["controls"] or []}
    sched = cfg.get("schedule", {"quarterly_execution_month": {"1": 4, "2": 7, "3": 10, "4": 1}})
    qexec = {int(k): v for k, v in sched.get("quarterly_execution_month", {}).items()}

    def deliverable(key, y, q):
        pat = cfg["deliverables"][key]["annual" if q is None else "quarterly"].format(Y=y, Q=q or "")
        hits = []
        for base in cfg.get("deliverable_search_dirs", ["."]):
            hits += glob.glob(os.path.join(os.path.normpath(os.path.join(ROOT, base)), "**", pat), recursive=True)
        if hits:
            h = sorted(hits)[0]
            return {"file": os.path.basename(h), "path": os.path.relpath(h, ROOT), "modified": dt.datetime.fromtimestamp(os.path.getmtime(h)).strftime("%Y-%m-%d %H:%M")}
        reg = (cfg.get("deliverable_registry", {}).get(key, {}) or {}).get(f"Q{q}-{y}" if q else f"Anual {y}")
        return {"file": reg, "path": None, "modified": None, "declared": True} if reg else None

    rows = []
    for y in years:
        for key, label, recs, qf in (("tc", "Tarjetas de crédito", tc["transactions"], "Trimestre"), ("bank", "Bancos y efectivo", bank["transactions"], "Trimestre_n")):
            src = "Credit Card" if key == "tc" else "Bank & Cash"
            for q in (1, 2, 3, 4, None):
                n = sum(1 for r in recs if r.get("Año") == y and (q is None or r.get(qf) == q))
                ex = [e for e in exceptions if e["Source"] == src and e.get("Año") == y and (q is None or q in e["quarter_span"])]
                ctl = [c for c in controls[key] if c.get("Año") == y and (q is None or str(c.get("Trimestre")) == f"Q{q}")]
                dlv = deliverable(key, y, q)
                ex_m = qexec.get(q) if q else 1
                ex_y = y + 1 if (q in (4, None)) else y
                coverage = None
                if not dlv and q is not None:
                    annual = deliverable(key, y, None)
                    if annual:
                        dlv, coverage = annual, "Cubierto por el informe anual"
                if coverage is None:
                    coverage = f"{n} registros · {len(ctl)} controles" + (f" ({sum(1 for c in ctl if c.get('Resultado') == 'ERROR')} ERROR, "
                                                                        f"{sum(1 for c in ctl if c.get('Resultado') == 'WARNING')} WARNING)" if ctl else "")
                if dlv:
                    status = "Completado"
                elif n or ex or ctl:
                    status = "En auditoría"
                elif (today.year, today.month) >= (ex_y, ex_m):
                    status = "Pendiente"
                else:
                    status = "No iniciado"
                if y < min(years) or (n == 0 and not ex and not dlv and y < cfg.get("baseline_year", y)):
                    continue
                rows.append(OrderedDict([("year", y), ("quarter", q), ("period", f"Q{q}-{y}" if q else f"Anual {y}"), ("module", label), ("source", src),
                                         ("status", status), ("planned_execution", f"{ex_y}-{ex_m:02d}"), ("records_loaded", n), ("exceptions", len(ex)),
                                         ("high_exceptions", sum(1 for e in ex if e.get("Riesgo") == "HIGH")), ("open_exceptions", sum(1 for e in ex if e["is_open"])),
                                         ("controls", len(ctl)), ("controls_error", sum(1 for c in ctl if c.get("Resultado") == "ERROR")),
                                         ("controls_warning", sum(1 for c in ctl if c.get("Resultado") == "WARNING")),
                                         ("execution_date", max((c.get("Fecha ejecución") or "" for c in ctl), default=None) or (dlv or {}).get("modified")),
                                         ("deliverable", (dlv or {}).get("file")), ("deliverable_path", (dlv or {}).get("path")), ("deliverable_declared", bool(dlv and dlv.get("declared"))),
                                         ("coverage", coverage)]))
    return OrderedDict([
        ("status_rule", ["Completado = existe el entregable (PDF) en las carpetas configuradas o declarado en deliverable_registry (un trimestre sin informe propio queda cubierto por el informe anual del año).",
                         "En auditoría = hay datos, excepciones o resultados de controles del período, pero no el entregable.",
                         "Pendiente = ya pasó el mes de ejecución planeado y no hay datos.", "No iniciado = el mes de ejecución aún no llega."]),
        ("controls_tc", tc["framework"]), ("controls_bank", bank["framework"]), ("control_results", controls["tc"] + controls["bank"]),
        ("calendar_tc", tc["calendar"]), ("calendar_bank", bank["calendar"]), ("periods", rows)])


# ======================================================================================
# CONCILIACIONES Y CALIDAD DE DATOS
# ======================================================================================
def reconcile(tc, bank, exceptions, cfg, log):
    aggs = tc_period_aggregates(tc)
    hist = tc["historico"]
    for period in hist.get("periods", []):
        if period not in aggs:
            log.warn("HIST_PERIOD_NO_DATA", f"Historico_Trimestral tiene la columna {period} pero Base_Transacciones no tiene filas de ese período")
            continue
        for mk, lab in TC_HIST_MAP.items():
            hv = to_num((hist["rows"].get(lab) or {}).get(period))
            if hv is None:
                log.warn("NO_CACHED_VALUE", f"Historico_Trimestral '{lab}' {period} sin valor calculado")
                continue
            log.check(f"TC {period} · {lab}", "Métricas Excel vs ETL", "ETL (Base_Transacciones/Extractos/Beneficios)", aggs[period][mk], f"Historico_Trimestral · {lab}", hv)
    for period in aggs:
        if period not in hist.get("periods", []):
            log.warn("HIST_COLUMN_MISSING", f"Falta la columna {period} en Historico_Trimestral (agregue una columna por trimestre auditado)")
    lab = tc["params"].get("Etiqueta")
    rmap = {"gross_spend": "Consumo bruto", "purchases": "Número de compras", "family": "Familiar / compartido atribuible", "personal": "Personal estimado",
            "undetermined": "No determinado", "fees": "Cuotas de manejo", "insurance": "Seguros", "interest": "Intereses (resumen de extractos)",
            "benefits": "Beneficios verificados (extracto)", "net_cost": "Costo neto (negativo = beneficio neto)"}
    if lab in aggs:
        for mk, rl in rmap.items():
            rv = to_num((tc["resumen"].get(rl) or {}).get("current"))
            if rv is not None:
                log.check(f"TC {lab} · {rl}", "Métricas Excel vs ETL", "ETL", aggs[lab][mk], f"Resumen_Trimestral · {rl}", rv)
    try:
        y, q = int(tc["params"]["Año auditado"]), int(tc["params"]["Trimestre auditado (1–4)"])
        for risk in RISK_ORDER:
            n = sum(1 for e in exceptions if e["Source"] == "Credit Card" and e.get("Año") == y and q in e["quarter_tags"] and e.get("Riesgo") == risk)
            rv = to_num((tc["resumen"].get(risk) or {}).get("current"))
            if rv is not None:
                log.check(f"TC excepciones {lab} · {risk}", "Excepciones", "Registro central", n, f"Resumen_Trimestral · {risk}", rv, tol=0)
        open_st = cfg.get("open_statuses", ["Open", "Review"])
        n_open = sum(1 for e in exceptions if e["Source"] == "Credit Card" and e.get("Estado original") in open_st)
        rv = to_num((tc["resumen"].get("Excepciones abiertas (todas las fechas)") or {}).get("current"))
        if rv is not None:
            log.check("TC excepciones abiertas (todas las fechas)", "Excepciones", "Registro central", n_open, "Resumen_Trimestral · Excepciones abiertas", rv, tol=0)
    except (KeyError, TypeError, ValueError):
        log.warn("PARAMS", "Parametros: año/trimestre auditado no legibles")
    mv = bank["transactions"]
    base_year = cfg.get("baseline_year")
    if base_year:
        mvb = [m for m in mv if m.get("Año") == base_year]
        fe = bank["flujos_2025"]
        for mk, lab2, side in [("gross_in", "Total Gross Bank Movements", "Entradas"), ("gross_out", "Total Gross Bank Movements", "Salidas"), ("internal_in", "Interno", "Entradas"),
                               ("internal_out", "Interno", "Salidas"), ("card_payments", "Pago TC", "Salidas"), ("investment_in", "Inversión (capital)", "Entradas"),
                               ("investment_out", "Inversión (capital)", "Salidas"), ("external_in", "Total External Economic Flows", "Entradas"),
                               ("external_out", "Total External Economic Flows", "Salidas")]:
            fv = to_num((fe.get(lab2) or {}).get(side))
            if fv is not None:
                log.check(f"Bancos {base_year} · {lab2} · {side}", "Métricas Excel vs ETL", f"ETL (Base_Movimientos, Año={base_year})", agg(mvb, BANK_METRICS[mk]), f"Flujos_Economicos · {lab2} · {side}", fv)
        rv = to_num(bank["resumen_2025"].get("Movimientos en la base consolidada"))
        if rv is not None:
            log.check(f"Bancos {base_year} · número de movimientos", "Métricas Excel vs ETL", f"Base_Movimientos (Año={base_year})", len(mvb), "Resumen · Movimientos", rv, tol=0)
        for risk in RISK_ORDER:
            rv = to_num(bank["resumen_2025"].get(risk))
            if rv is not None:
                n = sum(1 for e in exceptions if e["Source"] == "Bank & Cash" and e.get("Año") == base_year and e.get("Riesgo") == risk)
                log.check(f"Bancos {base_year} excepciones · {risk}", "Excepciones", "Registro central", n, f"Resumen · {risk}", rv, tol=0)
    # Historico_Trimestral_Bancos (todas las columnas Qn-AAAA)
    hb = bank["historico"]
    hmap = {"Gross entradas — *9910": ("gross_in", {"Cuenta": "Bancolombia *9910"}), "Gross salidas — *9910": ("gross_out", {"Cuenta": "Bancolombia *9910"}),
            "Transferencias internas — entradas": ("internal_in", {}), "Transferencias internas — salidas": ("internal_out", {}), "Pagos de tarjeta de crédito": ("card_payments", {}),
            "Inversión (capital) — entradas": ("investment_in", {}), "Inversión (capital) — salidas": ("investment_out", {}),
            "Ingreso de inversión (intereses y rendimientos)": ("investment_income", {})}
    for period in hb.get("periods", []):
        qn, yy = int(period[1]), int(period[3:])
        rows = [m for m in mv if m.get("Año") == yy and m.get("Trimestre_n") == qn]
        for lab3, (mk, extra) in hmap.items():
            hv = to_num((hb["rows"].get(lab3) or {}).get(period))
            if hv is not None:
                log.check(f"Bancos {period} · {lab3}", "Métricas Excel vs ETL", "ETL (Base_Movimientos)", agg([m for m in rows if matches(m, extra)], BANK_METRICS[mk]), f"Historico_Trimestral_Bancos · {lab3}", hv)
    # saldos: última línea de la *9910 por período vs Balance_Continuity
    for b in bank["balance_continuity"]:
        if b["Cuenta"] == "Bancolombia *9910" and b.get("Hasta"):
            hasta = str(b["Hasta"]).replace("/", "-")
            rows = sorted([m for m in mv if m["Cuenta"] == "Bancolombia *9910" and (m.get("Fecha") or "") <= hasta and isinstance(m.get("Saldo después"), (int, float))],
                          key=lambda m: (m["Fecha"], m["ID"]))
            if rows:
                log.check(f"Bancos · saldo *9910 {b['Período']}", "Saldos", "Base_Movimientos · último Saldo después", rows[-1]["Saldo después"], f"Balance_Continuity · {b['Período']}", b["Saldo final extracto"])
        if b.get("Estado") and b["Estado"] != "OK":
            log.warn("BALANCE_BREAK", f"Balance_Continuity {b['Cuenta']} {b['Período']}: estado {b['Estado']}")
    # Fiducuenta_TC vs Balance_Continuity (dos capturas del mismo resumen) y vs Productos_Financieros
    pf_mon = tc["productos"]["monthly"]
    cat = {c["ID_Producto"]: c for c in tc["productos"]["catalog"]}
    for f in bank["fiducuentas"]:
        pid = next((k for k, c in cat.items() if str(c.get("Número")) == str(f.get("Número"))), None)
        row = next((m for m in pf_mon if m.get("ID_Producto") == pid and m.get("Mes") == f.get("Mes")), None)
        if row is not None:
            log.check(f"Productos · intereses {f['Cuenta']} {f['Mes']}", "Diferencias entre registros", "Productos_Financieros · Intereses ganados", to_num(row.get("Intereses ganados")),
                      "Fiducuenta_TC · Intereses generados", to_num(f.get("Intereses generados (rend. netos)")), tol=0.01)
    reg = {e["ID"] for e in exceptions}
    for name, recs in (("Base_Transacciones", tc["transactions"]), ("Base_Movimientos", mv)):
        missing = sorted({x for r in recs for x in r["Excepción IDs"] if x not in reg})
        if missing:
            log.warn("ORPHAN_EXCEPTION_REF", f"{name} referencia IDs de excepción inexistentes: {', '.join(missing)}")
    return aggs


def data_quality(tc, bank, exceptions, cont, sources, hashes_ok, cfg, log, reg_diffs, alerts, hits):
    checks = []

    def add(category, name, status, detail, source=None):
        checks.append({"category": category, "check": name, "status": status, "detail": detail, "source": source})
    add("Hojas faltantes", "Hojas requeridas presentes en ambos libros", "ERROR" if any(e["code"] == "MISSING_SHEET" for e in log.errors) else "PASS",
        "; ".join(e["message"] for e in log.errors if e["code"] == "MISSING_SHEET") or "Todas las hojas del contrato están presentes")
    missing_opt = [w for w in log.warnings if w["code"] == "MISSING_SHEET"]
    add("Hojas faltantes", "Hojas opcionales del sistema multianual (continuidad, ciclo de vida, productos, controles)", "WARNING" if missing_opt else "PASS",
        "; ".join(w["message"] for w in missing_opt) or "Presentes")
    add("Columnas faltantes", "Columnas requeridas", "ERROR" if any(e["code"] == "MISSING_COLUMN" for e in log.errors) else "PASS",
        "; ".join(e["message"] for e in log.errors if e["code"] == "MISSING_COLUMN") or "Todas presentes")
    opt_cols = [i for i in log.info if i["code"] == "MISSING_OPTIONAL_COLUMN"]
    add("Columnas faltantes", "Columnas opcionales", "WARNING" if opt_cols else "PASS", f"{len(opt_cols)} columnas opcionales ausentes" if opt_cols else "Todas presentes")
    for name, recs, key in (("Base_Transacciones", tc["transactions"], "TxnID"), ("Base_Movimientos", bank["transactions"], "ID")):
        ids = [r[key] for r in recs]
        dup = sorted({i for i in ids if ids.count(i) > 1})
        add("IDs duplicados", f"IDs únicos en {name}", "ERROR" if dup else "PASS", ", ".join(dup) or f"{len(ids)} IDs únicos")
    ids = [e["ID"] for e in exceptions]
    add("Excepciones duplicadas", "IDs únicos en el registro central", "ERROR" if len(ids) != len(set(ids)) else "PASS", f"{len(ids)} excepciones, {len(set(ids))} IDs únicos")
    cur = [e for e in exceptions if not e["is_historical"]]
    hist = [e for e in exceptions if e["is_historical"]]
    copies = [f"{c['ID']}≈{h['ID']}" for c in cur for h in hist if (c.get("Concepto") or "").upper() == (h.get("Concepto") or "").upper() and c.get("Monto (COP)") == h.get("Monto (COP)")]
    add("Excepciones duplicadas", "Ningún hallazgo histórico copiado como excepción actual", "ERROR" if copies else "PASS", ", ".join(copies) or f"{len(cur)} actuales vs {len(hist)} históricas")
    reused = [e["ID"] for e in cur if any(e["ID"] == h["ID"] for h in hist)]
    add("Excepciones duplicadas", "IDs históricos no reutilizados", "ERROR" if reused else "PASS", ", ".join(reused) or "Sin reutilización")
    bad_rel = [f"{e['ID']}→{e.get('Hallazgo relacionado')}" for e in cur if e.get("Hallazgo relacionado")
               and not all(x in {h['ID'] for h in hist} for x in re.findall(r"EX-\d+", e["Hallazgo relacionado"]))]
    add("Inconsistencias", "'Hallazgo relacionado' apunta a hallazgos históricos existentes", "ERROR" if bad_rel else "PASS", ", ".join(bad_rel) or "Sin referencias inválidas")
    leak = [e["ID"] for e in hist if e["counts_in_current_open"]]
    add("Inconsistencias", "Hallazgos históricos excluidos de 'excepciones abiertas actuales'", "ERROR" if leak else "PASS", ", ".join(leak) or "OK")
    nostat = [e["ID"] for e in exceptions if e["Estado"] not in cfg.get("preferred_statuses", []) + cfg.get("open_statuses", [])]
    add("Inconsistencias", "Estados de excepción normalizados (Open / Monitor / Explained / No Action Required / Closed)", "WARNING" if nostat else "PASS", ", ".join(nostat) or "OK")
    add("Diferencias entre registros", "Registro central vs registro de Auditoria_Bancos", "WARNING" if reg_diffs else "PASS",
        "; ".join(f"{i}: {', '.join(d)}" for i, d in reg_diffs) or "Sin diferencias")
    rec_fail = [c for c in log.checks if c["status"] != "PASS"]
    add("Diferencias entre registros", "Conciliaciones Excel vs ETL", "ERROR" if rec_fail else "PASS", f"{len(log.checks) - len(rec_fail)} de {len(log.checks)} OK" + (": " + "; ".join(c["check"] for c in rec_fail[:10]) if rec_fail else ""))
    mat = [m for m in bank["transactions"] if m.get("Material (≥1M)") == "Sí" and m.get("Cuenta") == "Bancolombia *9910"]
    reviewed = {m["ID"] for m in bank["material"]} | {m["ID"] for m in bank["material_2025"]}
    nrev = [m["ID"] for m in mat if m["ID"] not in reviewed and m.get("Año") != cfg.get("baseline_year")]
    add("Movimientos materiales", "Movimientos ≥ 1M de la *9910 revisados individualmente", "WARNING" if nrev else "PASS", ", ".join(nrev[:20]) or f"{len(mat)} movimientos ≥ 1M; todos revisados")
    unr = [m for m in bank["material"] if (m.get("Conclusión") or "") == "Revisar"]
    add("Movimientos materiales", "Movimientos materiales sin conclusión", "WARNING" if unr else "PASS", ", ".join(m["ID"] for m in unr) or "OK")
    unc = [t["TxnID"] for t in tc["transactions"] if t.get("Es compra") == "Sí" and not t.get("Naturaleza")]
    add("Inconsistencias", "Compras con Naturaleza asignada", "ERROR" if unc else "PASS", ", ".join(unc[:20]) or "OK")
    unc_b = [m["ID"] for m in bank["transactions"] if not m.get("Clasificación") or m.get("Clasificación") == "No determinado"]
    add("Inconsistencias", "Movimientos bancarios con clasificación", "WARNING" if unc_b else "PASS", ", ".join(unc_b[:20]) or "OK")
    stm_bad = [f"{s['Producto']} {s['Fecha corte']}: {s['Resultado']}" for s in tc["statements"] if s.get("Resultado") not in ("OK", "Utilización > umbral")]
    add("Inconsistencias", "Aritmética y continuidad de extractos TC", "ERROR" if stm_bad else "PASS", "; ".join(stm_bad[:10]) or f"{len(tc['statements'])} cortes OK")
    bc_bad = [f"{b['Cuenta']} {b['Período']}" for b in bank["balance_continuity"] if b.get("Estado") not in ("OK", None)]
    add("Inconsistencias", "Continuidad de saldos bancarios", "ERROR" if bc_bad else "PASS", ", ".join(bc_bad) or f"{len(bank['balance_continuity'])} períodos OK")
    add("Inconsistencias", "Actividad en tarjetas cerradas después del cierre", "ERROR" if alerts else "PASS", f"{len(alerts)} alertas" if alerts else "Sin actividad posterior al cierre")
    cov = tc.get("coverage") or []
    cur_y = cfg.get("current_audit_year")
    cov_cur = [c for c in cov if c.get("Año") == cur_y]
    miss = [f"{c['Producto']} {c['Mes']}" for c in cov_cur if str(c.get("Estado de cobertura") or "").startswith("Falta extracto")]
    unk = [f"{c['Producto']} {c['Mes']}: {c.get('Estado de cobertura')}" for c in cov_cur if not str(c.get("Estado de cobertura") or "").startswith(COVERAGE_OK + ("Falta extracto",))]
    by = defaultdict(int)
    for c in cov_cur:
        by[str(c.get("Estado de cobertura")).split(" (")[0]] += 1
    add("Cobertura de extractos", "Extractos requeridos disponibles (sin extracto ≠ problema: inactivo, cerrado, migrado o no abierto no generan ERROR)",
        "ERROR" if miss else ("WARNING" if unk else "PASS"), "; ".join(miss + unk) or " · ".join(f"{k}: {v}" for k, v in sorted(by.items())), "Cobertura_Extractos")
    nores = [f"{c['Producto']} {c['Mes']}" for c in cov_cur if c.get("Estado de cobertura") != "Con extracto" and not c.get("Evidencia del estado")]
    add("Cobertura de extractos", "Cada producto-mes sin extracto tiene motivo documentado", "WARNING" if nores else "PASS", ", ".join(nores[:20]) or f"{len(cov_cur)} producto-mes clasificados", "Cobertura_Extractos")
    keys = [(s.get("Tarjeta"), s.get("Moneda"), s.get("Mes")) for s in tc["statements"]]
    dupk = sorted({f"{k[0]} {k[1]} {k[2]}" for k in keys if keys.count(k) > 1})
    add("Cobertura de extractos", "Extractos o períodos duplicados (tarjeta · moneda · corte)", "ERROR" if dupk else "PASS", ", ".join(dupk) or f"{len(keys)} cortes únicos", "Extractos_Input")
    cp_rows = [p for p in (bank.get("card_payments") or []) if p.get("Año") == cur_y]
    pay_nost = [p["ID *9910"] for p in cp_rows if not str(p.get("Estado") or "").startswith("Exact Match")]
    add("Cobertura de extractos", "Pagos *9910 a tarjetas sin extracto que los soporte", "WARNING" if pay_nost else "PASS", ", ".join(pay_nost) or f"{len(cp_rows)} pagos conciliados con extracto", "Pagos_TC_Trimestral")
    st_cur = [s for s in tc["statements"] if s.get("Año") == cur_y]
    st_nopay = [f"{s['Tarjeta']} {s['Moneda']} {s['Mes']}" for s in st_cur if (to_num(s.get("Pagos y abonos")) or 0) == 0 and (to_num(s.get("Saldo anterior")) or 0) > 0]
    add("Cobertura de extractos", "Extractos con saldo anterior > 0 y sin pago registrado en el período", "WARNING" if st_nopay else "PASS", ", ".join(st_nopay) or f"{len(st_cur)} cortes {cur_y} con pago o sin saldo", "Extractos_Input")
    lc = cont.get("lifecycle") or []
    mig = [f"{l.get('Tarjeta')} ({l.get('Status')})" for l in lc if str(l.get("Status") or "").lower().startswith(("migr", "closed", "cerr"))]
    act_after = [a for a in alerts]
    add("Cobertura de extractos", "Tarjetas cerradas o migradas sin actividad posterior", "ERROR" if act_after else "PASS", ", ".join(mig) or "Sin productos cerrados/migrados", "Ciclo_Vida_Productos")
    add("Hashes", "Libros sin cambios durante el refresh (SHA-256 antes = después)", "PASS" if hashes_ok else "ERROR", "; ".join(f"{s['file']}: {s['sha256'][:12]}…" for s in sources))
    for s in sources:
        age = (dt.datetime.now() - dt.datetime.strptime(s["modified"], "%Y-%m-%d %H:%M:%S")).days
        add("Frescura de fuentes", f"Última modificación de {s['file']}", "WARNING" if age > cfg.get("freshness_days", 100) else "PASS", f"{s['modified']} (hace {age} días)")
    for key, arch in (cfg.get("archive") or {}).items():
        for wbk, info in (arch or {}).items():
            if isinstance(info, dict) and info.get("path"):
                p = resolve(info["path"])
                if not os.path.exists(p):
                    add("Hashes", f"Archivo baseline {key} · {wbk}", "WARNING", f"No encontrado: {info['path']}")
                else:
                    ok = sha256(p) == info.get("sha256")
                    add("Hashes", f"Archivo baseline {key} · {wbk} íntegro", "PASS" if ok else "ERROR", f"{info['path']} {'coincide con' if ok else 'NO coincide con'} el hash registrado")
    add("Advertencias", "Advertencias del ETL", "WARNING" if log.warnings else "PASS", f"{len(log.warnings)} advertencias")
    add("Errores", "Errores del ETL", "ERROR" if log.errors else "PASS", f"{len(log.errors)} errores")
    summ = {s: sum(1 for c in checks if c["status"] == s) for s in ("PASS", "WARNING", "ERROR")}
    return {"summary": summ, "checks": checks, "reconciliation": log.checks, "controls": (tc["controls"] or []) + (bank["controls"] or []),
            "context_hits": hits, "closed_card_alerts": alerts}


# ======================================================================================
def load_config():
    cfg = {"sources": {"tc": "source/Sistema_Auditoria_TC.xlsx", "bank": "source/Auditoria_Bancos.xlsx"}, "deliverable_search_dirs": ["."],
           "deliverables": {"tc": {"annual": "Informe_Auditoria_TC_{Y}.pdf", "quarterly": "Auditoria_Trimestral_TC_Q{Q}_{Y}.pdf"},
                            "bank": {"annual": "Informe_Auditoria_Bancos_{Y}.pdf", "quarterly": "Auditoria_Trimestral_Bancos_Q{Q}_{Y}.pdf"}},
           "open_statuses": ["Open", "Review"], "preferred_statuses": ["Open", "Monitor", "Explained", "No Action Required", "Closed"],
           "status_normalization": {"Corrected": "Closed"}, "bank_origin_pattern": "Bancari", "materiality_cop": 1000000}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    for k in ("tc", "bank"):
        if isinstance(cfg["sources"].get(k), dict):
            cfg["sources"][k] = cfg["sources"][k]["path"]
    return cfg


def resolve(path):
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(ROOT, path))


def write_json(name, obj):
    path = os.path.join(DATA_DIR, name)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


DATASETS = ("metadata", "credit_cards", "bank_cash", "exceptions", "timeline", "continuity", "product_utility", "data_quality", "treasury")


def _write_bundle():
    parts = {}
    for name in DATASETS:
        p = os.path.join(DATA_DIR, name + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                parts[name] = json.load(f)
    with open(os.path.join(DATA_DIR, "dashboard_data.js"), "w", encoding="utf-8") as f:
        f.write("/* GENERADO por scripts/refresh_dashboard.py — no editar. Refleja data/*.json */\n")
        f.write("window.AUDIT_DATA = ")
        json.dump(parts, f, ensure_ascii=False, default=str)
        f.write(";\n")


def fail(meta, log, msg):
    meta.update({"status": "FAILED", "errors": log.errors, "warnings": log.warnings, "info": log.info, "message": msg})
    write_json("metadata.json", meta)
    _write_bundle()
    print("REFRESH FALLIDO:")
    for e in log.errors:
        print("  ERROR", e["code"], "-", e["message"])
    return 2


def main(argv=None):
    ap = argparse.ArgumentParser(description="Refresca los datasets del dashboard desde los libros Excel (solo lectura).")
    ap.add_argument("--tc"); ap.add_argument("--bank")
    ap.add_argument("--check", action="store_true", help="Solo validar; no escribe JSON")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    cfg = load_config()
    log = Log()
    os.makedirs(DATA_DIR, exist_ok=True)
    paths = {"tc": resolve(args.tc or cfg["sources"]["tc"]), "bank": resolve(args.bank or cfg["sources"]["bank"])}
    for k, p in paths.items():
        if not os.path.exists(p):
            log.error("SOURCE_NOT_FOUND", f"No se encontró el libro fuente ({k}): {p}. Revise scripts/config.json › sources.")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = OrderedDict([("schema_version", SCHEMA_VERSION), ("system_name", cfg.get("system_name", "Financial Account Audit System")), ("last_refresh", now)])
    if log.errors:
        return fail(meta, log, "Refresh abortado: no se encontraron los libros fuente.")
    sources = []
    for k, p in paths.items():
        sources.append({"role": k, "file": os.path.basename(p), "path": os.path.relpath(p, ROOT), "sha256": sha256(p), "bytes": os.path.getsize(p),
                        "modified": dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M:%S")})
    before = {s["path"]: s["sha256"] for s in sources}
    wb_tc = openpyxl.load_workbook(paths["tc"], data_only=True)
    wb_ba = openpyxl.load_workbook(paths["bank"], data_only=True)
    sources[0]["sheets"], sources[1]["sheets"] = wb_tc.sheetnames, wb_ba.sheetnames
    tc_label, bank_label = sources[0]["file"], sources[1]["file"]
    tc = extract_tc(wb_tc, log, tc_label)
    bank = extract_bank(wb_ba, log, bank_label) if not log.errors else None
    try:
        treasury_derived = treasury_inputs.derive_monthly(wb_ba) if bank is not None else None
    except ValueError as e:
        treasury_derived = None
        log.warn("TREASURY_DERIVE", f"No se pudieron derivar los insumos de tesorería del libro de bancos: {e}")
    wb_tc.close(); wb_ba.close()
    hashes_ok = all(sha256(resolve(p)) == h for p, h in before.items())
    if not hashes_ok:
        log.error("SOURCE_MODIFIED", "Un libro fuente cambió durante el refresh.")
    meta["sources"] = sources
    if log.errors or tc is None or bank is None:
        return fail(meta, log, "Refresh abortado: se conservan los datasets anteriores. Corrija los errores y vuelva a ejecutar.")
    exceptions, reg_diffs = build_exceptions(tc, bank, cfg, log, tc_label, bank_label)
    data_years = sorted({r["Año"] for r in tc["transactions"] if isinstance(r.get("Año"), int)} | {m["Año"] for m in bank["transactions"] if isinstance(m.get("Año"), int)})
    current_year = int(cfg.get("current_audit_year") or (max(data_years) if data_years else dt.date.today().year))
    cfg.setdefault("baseline_year", min(data_years) if data_years else current_year - 1)
    cont = read_continuity(cfg, tc, log)
    apply_continuity(exceptions, cont, current_year, log)
    hits = context_hits(tc, bank, cont, current_year)
    alerts = lifecycle_alerts(tc, cont, log)
    if log.errors:
        return fail(meta, log, "Refresh abortado: se conservan los datasets anteriores.")
    cc = build_credit_cards(tc, exceptions, cont)
    bk = build_bank(bank, exceptions)
    pu = build_products(tc, bank, cfg)
    tre = build_treasury(tc, treasury_derived, log)
    aggs = reconcile(tc, bank, exceptions, cfg, log)
    cc["quarter_summary"] = [OrderedDict([("period", p), ("Año", int(p[3:])), ("Trimestre", int(p[1]))] + [(k, _r(v)) for k, v in m.items()]) for p, m in aggs.items()]
    timeline = build_timeline(tc, bank, exceptions, cfg, sources, log)
    dq = data_quality(tc, bank, exceptions, cont, sources, hashes_ok, cfg, log, reg_diffs, alerts, hits)
    years = sorted(set(data_years) | {e["Año"] for e in exceptions if isinstance(e.get("Año"), int)})
    try:
        cp = {"year": int(tc["params"]["Año auditado"]), "quarter": int(tc["params"]["Trimestre auditado (1–4)"]), "label": tc["params"].get("Etiqueta")}
    except (KeyError, TypeError, ValueError):
        cp = None
    counts = OrderedDict((code, sum(1 for r in cont["findings"] if r["category_code"] == code)) for code in list(CATEGORIES) + ["?"])
    cont_json = OrderedDict([
        ("metadata", {"current_audit_year": current_year, "baseline_year": cfg["baseline_year"], "sources": cont["source"], "categories": CATEGORIES,
                      "status_years": cont["status_years"], "principle": "Un hallazgo previo da contexto; no exime ni reabre automáticamente.",
                      "next_exception_id": next_exception_id(exceptions)}),
        ("category_counts", counts), ("matrix", cont["findings"]), ("context_rules", cont["context_rules"]), ("card_lifecycle", cont["lifecycle"]),
        ("context_hits", hits), ("closed_card_alerts", alerts)])
    exc_json = OrderedDict([
        ("metadata", {"current_audit_year": current_year, "risk_order": RISK_ORDER, "open_statuses": cfg.get("open_statuses"),
                      "status_normalization": cfg.get("status_normalization"), "next_exception_id": next_exception_id(exceptions),
                      "rules": ["Excepción actual = Año ≥ año de auditoría actual (config). Las de años anteriores son hallazgos históricos y nunca cuentan en KPIs actuales.",
                                "Grupo de hallazgos históricos según Continuidad_Hallazgos: A/B/E/F = resuelto o contexto; C = control recurrente; D = carry forward.",
                                "Origen con 'Bancari' = módulo Bancos y efectivo (misma regla que Resumen_Trimestral).",
                                "Estado normalizado según config (p. ej. 'Corrected' → 'Closed'); el estado original se conserva.",
                                "Monitor = sin acción correctiva pero con seguimiento; no cuenta como abierta.",
                                "Cerrada durante esta actualización = 'Estado anterior' abierto y estado actual no abierto (columna Estado anterior del registro central)."]}),
        ("exceptions", exceptions)])
    records = OrderedDict([("transacciones_tc", len(cc["transactions"])), ("extractos_tc", len(cc["statements"])), ("movimientos_bancarios", len(bk["transactions"])),
                           ("excepciones", len(exceptions)), ("excepciones_actuales", sum(1 for e in exceptions if not e["is_historical"])),
                           ("hallazgos_historicos", sum(1 for e in exceptions if e["is_historical"])), ("productos", len(pu["catalog"])),
                           ("filas_utilidad", len(pu["monthly"])), ("meses_tesoreria", len(tre["monthly"])), ("metricas_tesoreria", len(tre["metrics"])), ("controles_registrados", len(dq["controls"])), ("periodos_cronograma", len(timeline["periods"]))])
    n_fail = sum(1 for c in log.checks if c["status"] != "PASS")
    meta.update(OrderedDict([
        ("status", "OK" if not n_fail and not log.warnings else "OK_WITH_WARNINGS"), ("years", years), ("current_audit_year", current_year),
        ("baseline_year", cfg["baseline_year"]), ("current_period", cp), ("materiality_cop", cfg.get("materiality_cop")), ("records", records),
        ("reconciliation", {"passed": len(log.checks) - n_fail, "failed": n_fail}), ("dq_summary", dq["summary"]),
        ("errors", log.errors), ("warnings", log.warnings), ("info", log.info)]))
    if args.check:
        print(json.dumps({"status": meta["status"], "dq": dq["summary"], "reconciliation": meta["reconciliation"], "warnings": len(log.warnings)}, ensure_ascii=False))
        return 0
    for name, obj in (("credit_cards.json", cc), ("bank_cash.json", bk), ("exceptions.json", exc_json), ("timeline.json", timeline), ("continuity.json", cont_json),
                      ("product_utility.json", pu), ("data_quality.json", dq), ("treasury.json", tre), ("metadata.json", meta)):
        write_json(name, obj)
    _write_bundle()
    print(f"Refresh OK  {now}")
    for k, v in records.items():
        print(f"  {k:28s} {v}")
    print(f"  conciliaciones: {meta['reconciliation']['passed']} OK, {n_fail} con diferencia")
    print(f"  calidad de datos: {dq['summary']}")
    print(f"  año actual: {current_year}  ·  siguiente ID de excepción: {cont_json['metadata']['next_exception_id']}")
    print(f"  advertencias: {len(log.warnings)}")
    for w in log.warnings[:20]:
        print("  WARN", w["code"], "-", w["message"][:180])
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
treasury_inputs.py — insumos mensuales de tesorería (Treasury Control Tower).

El libro de tarjetas (Sistema_Auditoria_TC.xlsx) consolida las métricas de tesorería en la hoja
Metricas_Tesoreria. Los datos bancarios que esas fórmulas necesitan viven en Auditoria_Bancos.xlsx, así que
se copian como valores (azul) a la hoja Tesoreria_Input del libro TC: una fila por mes.

Este módulo es la ÚNICA definición de cómo se derivan esos valores del libro de bancos. Lo usan:
  * este script (comando `sync`), para agregar los meses nuevos a Tesoreria_Input al cierre de cada trimestre;
  * refresh_dashboard.py, para conciliar en cada refresh Tesoreria_Input contra el libro de bancos.

Criterios (los mismos SUMIFS de Historico_Trimestral_Bancos):
  Saldo ahorros *9910     = "Saldo después" de la última línea del mes en Base_Movimientos (si no hay
                            movimientos, se arrastra el saldo anterior).
  Saldo fiducuentas       = "Saldo final extracto" de Balance_Continuity (0 antes de la apertura).
  Gasto externo bancario  = Salida con Flujo económico = "Gasto externo".
  GMF 4x1000              = Salida con Subclase = "GMF 4x1000".
  Intereses *9910         = Entrada con Subclase = "Intereses cuenta de ahorros".
  Rendimientos netos      = Entrada con Subclase que empieza por "Rendimiento neto Fiducuenta".
  Retención en la fuente  = Salida con Subclase que empieza por "Retención en la fuente".
  Rentabilidad E.A.       = "Rentabilidad neta E.A. (extracto)" de la Fiducuenta *6191 en Balance_Continuity.

Uso
---
    python scripts/treasury_inputs.py check   # compara Tesoreria_Input con el libro de bancos (no escribe)
    python scripts/treasury_inputs.py sync    # respalda el libro TC y agrega los meses que falten

Después de `sync`, abra Sistema_Auditoria_TC.xlsx en Excel, guárdelo y ejecute el refresh del dashboard.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
from collections import OrderedDict

try:
    import openpyxl
    from openpyxl.styles import Font
except ImportError:  # pragma: no cover
    sys.exit("ERROR: falta openpyxl.  Ejecute:  pip install openpyxl")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = "Tesoreria_Input"
SAVINGS = "Bancolombia *9910"
FIDUS = ["Fiducuenta *6191", "Fiducuenta *0934", "Fiducuenta *0452"]

# Columnas de Tesoreria_Input (encabezado en la fila 4). "kind": input = valor azul copiado del libro de bancos.
COLUMNS = OrderedDict([
    ("Año", {"kind": "key"}),
    ("Trimestre", {"kind": "key"}),
    ("Mes (n)", {"kind": "key"}),
    ("Mes", {"kind": "key"}),
    ("Saldo ahorros *9910", {"kind": "input", "field": "savings"}),
    ("Saldo Fiducuenta *6191", {"kind": "input", "field": "fidu_6191"}),
    ("Saldo Fiducuenta *0934", {"kind": "input", "field": "fidu_0934"}),
    ("Saldo Fiducuenta *0452", {"kind": "input", "field": "fidu_0452"}),
    ("Liquidez total", {"kind": "formula"}),
    ("Gasto externo bancario", {"kind": "input", "field": "external_spend"}),
    ("GMF 4x1000", {"kind": "input", "field": "gmf"}),
    ("Intereses *9910", {"kind": "input", "field": "savings_interest"}),
    ("Rendimientos netos fiducuentas", {"kind": "input", "field": "fidu_yield"}),
    ("Retención en la fuente fiducuentas", {"kind": "input", "field": "withholding"}),
    ("Rentabilidad E.A. fiducuenta (extracto)", {"kind": "input", "field": "fidu_rate"}),
    ("Fuente", {"kind": "text"}),
])
FIELD_LABEL = {v["field"]: k for k, v in COLUMNS.items() if v.get("field")}


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", ""))
        except ValueError:
            return None
    return None


def _month_key(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m")
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}", v.strip()):
        return v.strip()
    return None


def _header(ws, first, max_scan=12):
    for r in range(1, max_scan + 1):
        row = [c.value for c in ws[r]]
        if row and row[0] == first:
            return r, {str(v).strip(): i for i, v in enumerate(row) if v is not None}
    return None, None


def derive_monthly(wb_bank):
    """Valores mensuales de tesorería desde Auditoria_Bancos.xlsx (abierto con data_only=True)."""
    ws = wb_bank["Base_Movimientos"]
    hr, idx = _header(ws, "ID")
    if hr is None:
        raise ValueError("Base_Movimientos: no se encontró el encabezado (columna ID)")
    need = ["Cuenta", "Fecha", "Mes", "Entrada", "Salida", "Saldo después", "Subclase", "Flujo económico", "Valor"]
    miss = [c for c in need if c not in idx]
    if miss:
        raise ValueError(f"Base_Movimientos: faltan columnas {miss}")
    moves = []
    for n, row in enumerate(ws.iter_rows(min_row=hr + 1, values_only=True)):
        if not row or row[idx["Cuenta"]] is None:
            continue
        mes = _month_key(row[idx["Mes"]]) or _month_key(row[idx["Fecha"]])
        if not mes:
            continue
        val = _num(row[idx["Valor"]])
        ent, sal = _num(row[idx["Entrada"]]), _num(row[idx["Salida"]])
        if ent is None and val is not None:  # libro guardado sin recalcular
            ent, sal = max(val, 0.0), max(-val, 0.0)
        fecha = row[idx["Fecha"]]
        moves.append({"n": n, "cuenta": row[idx["Cuenta"]], "fecha": fecha if isinstance(fecha, (dt.datetime, dt.date)) else None, "mes": mes,
                      "in": ent or 0.0, "out": sal or 0.0, "saldo": _num(row[idx["Saldo después"]]),
                      "sub": str(row[idx["Subclase"]] or ""), "flujo": str(row[idx["Flujo económico"]] or "")})
    months = sorted({m["mes"] for m in moves})
    # Balance_Continuity: filas de fiducuentas por mes (secciones B y D)
    fidu_bal, fidu_rate = {}, {}
    for row in wb_bank["Balance_Continuity"].iter_rows(values_only=True):
        if row and isinstance(row[0], str) and row[0].strip() in FIDUS and _month_key(row[1]):
            mk = _month_key(row[1])
            fidu_bal[(row[0].strip(), mk)] = _num(row[9])
            if row[0].strip() == FIDUS[0] and _num(row[15]) is not None:
                fidu_rate[mk] = _num(row[15])
    out, last_sav = [], None
    for mk in months:
        mv = [m for m in moves if m["mes"] == mk]
        sav_lines = sorted([m for m in mv if m["cuenta"] == SAVINGS and m["saldo"] is not None],
                           key=lambda m: (m["fecha"] or dt.datetime.min, m["n"]))
        if sav_lines:
            last_sav = sav_lines[-1]["saldo"]
        y, mo = int(mk[:4]), int(mk[5:])
        rec = OrderedDict([("Año", y), ("Trimestre", (mo - 1) // 3 + 1), ("Mes (n)", mo), ("Mes", mk)])
        rec["savings"] = last_sav
        for f in FIDUS:
            rec["fidu_" + f[-4:]] = fidu_bal.get((f, mk), 0.0) or 0.0
        rec["external_spend"] = sum(m["out"] for m in mv if m["flujo"] == "Gasto externo")
        rec["gmf"] = sum(m["out"] for m in mv if m["sub"] == "GMF 4x1000")
        rec["savings_interest"] = sum(m["in"] for m in mv if m["sub"] == "Intereses cuenta de ahorros")
        rec["fidu_yield"] = sum(m["in"] for m in mv if m["sub"].startswith("Rendimiento neto Fiducuenta"))
        rec["withholding"] = sum(m["out"] for m in mv if m["sub"].startswith("Retención en la fuente"))
        rec["fidu_rate"] = fidu_rate.get(mk)
        out.append(rec)
    return out


def read_sheet(wb_tc):
    """Filas de Tesoreria_Input (valores calculados). Devuelve lista de dicts con las claves de COLUMNS."""
    if SHEET not in wb_tc.sheetnames:
        return None
    ws = wb_tc[SHEET]
    hr, idx = _header(ws, "Año")
    if hr is None:
        return None
    rows = []
    for r in ws.iter_rows(min_row=hr + 1, values_only=True):
        if not r or not isinstance(r[0], (int, float)):
            continue
        rec = OrderedDict((k, r[i] if i < len(r) else None) for k, i in idx.items())
        rec["_mes"] = _month_key(rec.get("Mes")) or f"{int(r[0])}-{int(rec.get('Mes (n)') or 0):02d}"
        rows.append(rec)
    return rows


def compare(sheet_rows, derived, tol=1.0):
    """Diferencias campo a campo entre Tesoreria_Input y el libro de bancos."""
    by = {r["_mes"]: r for r in sheet_rows}
    diffs, missing = [], []
    for d in derived:
        s = by.get(d["Mes"])
        if s is None:
            missing.append(d["Mes"])
            continue
        for field, label in FIELD_LABEL.items():
            a, b = _num(s.get(label)), d.get(field)
            t = 1e-6 if field == "fidu_rate" else tol
            if b is None and a is None:
                continue
            if a is None or b is None or abs(a - b) > t:
                diffs.append({"Mes": d["Mes"], "campo": label, "Tesoreria_Input": a, "Auditoria_Bancos": b})
    return diffs, missing


def _style_row(ws, r):
    blue = Font(name="Arial", size=10, color="FF0000FF")
    black = Font(name="Arial", size=10)
    for c, (name, spec) in enumerate(COLUMNS.items(), start=1):
        cell = ws.cell(r, c)
        cell.font = blue if spec["kind"] == "input" else black
        if name == "Rentabilidad E.A. fiducuenta (extracto)":
            cell.number_format = "0.00%"
        elif spec["kind"] in ("input", "formula"):
            cell.number_format = "#,##0;\\(#,##0\\);\\-"


def write_row(ws, r, d, source):
    keys = list(COLUMNS)
    vals = {"Año": d["Año"], "Trimestre": d["Trimestre"], "Mes (n)": d["Mes (n)"], "Mes": d["Mes"], "Fuente": source}
    for field, label in FIELD_LABEL.items():
        v = d.get(field)
        vals[label] = round(v, 2) if isinstance(v, float) and field != "fidu_rate" else v
    for c, k in enumerate(keys, start=1):
        if COLUMNS[k]["kind"] == "formula":
            ws.cell(r, c, f"=SUM(E{r}:H{r})")
        else:
            ws.cell(r, c, vals.get(k))
    _style_row(ws, r)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Insumos mensuales de tesorería (Tesoreria_Input) desde Auditoria_Bancos.xlsx")
    ap.add_argument("cmd", choices=["check", "sync"])
    ap.add_argument("--tc", default=os.path.join(ROOT, "source", "Sistema_Auditoria_TC.xlsx"))
    ap.add_argument("--bank", default=os.path.join(ROOT, "source", "Auditoria_Bancos.xlsx"))
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    derived = derive_monthly(openpyxl.load_workbook(a.bank, data_only=True))
    rows = read_sheet(openpyxl.load_workbook(a.tc, data_only=True))
    if rows is None:
        sys.exit(f"ERROR: el libro TC no tiene la hoja {SHEET}.")
    diffs, missing = compare(rows, derived)
    print(f"Meses en el libro de bancos: {len(derived)} · en {SHEET}: {len(rows)} · faltantes: {missing or 'ninguno'}")
    for d in diffs:
        print(f"  DIF {d['Mes']} · {d['campo']}: Tesoreria_Input={d['Tesoreria_Input']} · Auditoria_Bancos={d['Auditoria_Bancos']}")
    if a.cmd == "check":
        return 1 if (diffs or missing) else 0
    if not missing:
        print("Nada que agregar. Las diferencias en meses existentes se corrigen a mano (celdas azules) después de revisarlas.")
        return 0
    stamp = dt.date.today().isoformat()
    bdir = os.path.join(os.path.dirname(a.tc), "archive", f"pre_tesoreria_sync_{stamp}")
    os.makedirs(bdir, exist_ok=True)
    shutil.copy2(a.tc, os.path.join(bdir, os.path.basename(a.tc)))
    wb = openpyxl.load_workbook(a.tc)
    ws = wb[SHEET]
    hr, _ = _header(ws, "Año")
    last = hr
    for r in range(hr + 1, ws.max_row + 1):
        if isinstance(ws.cell(r, 1).value, (int, float)):
            last = r
    for d in [x for x in derived if x["Mes"] in missing]:
        last += 1
        if isinstance(ws.cell(last, 1).value, str):  # no pisar notas al pie
            ws.insert_rows(last)
        write_row(ws, last, d, f"Auditoria_Bancos.xlsx (sync {stamp})")
    wb.save(a.tc)
    print(f"Agregados {len(missing)} mes(es). Respaldo en {os.path.relpath(bdir, ROOT)}. Abra el libro en Excel, guárdelo y refresque el dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

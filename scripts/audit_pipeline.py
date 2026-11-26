#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_pipeline.py — Preflight (GO / NO-GO) y control de fases de Financial Account Audit.

NO calcula cifras de auditoría: decide si cada fase puede ejecutarse y deja trazabilidad.
La auditoría la ejecuta Claude sobre los libros Excel (fuente de verdad) siguiendo la skill
`financial-account-audit`. Este script solo:
  1. preflight   — localiza extractos y fuentes, arma la matriz de cobertura y emite GO / NO-GO.
  2. phase       — impide ejecutar fases fuera de orden o después de un bloqueo.
  3. backup      — respalda los dos libros (con SHA-256) antes de modificarlos.
  4. verify-dashboard — verifica el refresh del ETL (metadata/data_quality) y lo registra.
  5. check-exceptions — detecta hallazgos históricos reabiertos o IDs reutilizados.
  6. status      — muestra el estado de la ejecución.

Uso (en el PC, desde la carpeta Financial Audit Dashboard):
    set AUDIT_PDF_PASSWORD=...        (solo en la sesión; nunca se guarda)
    python scripts\\audit_pipeline.py preflight --period 2026Q4
    python scripts\\audit_pipeline.py preflight --period 2026          (anual)
    python scripts\\audit_pipeline.py phase --period 2026Q4 --start P7
    python scripts\\audit_pipeline.py phase --period 2026Q4 --done P7 --result PASS --note "..."
En Cowork: los archivos se preparan (device_stage_files) y se pasa --evidence-root a la copia.

Códigos de salida: 0 = GO / acción permitida · 2 = NO-GO / BLOQUEADO · 3 = fase fuera de orden.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DASH_ROOT = os.path.dirname(HERE)
REGISTRY = os.path.join(HERE, "audit_sources.json")
MON = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
MON_ALT = {"SEPT": 9, "SET": 9}
PHASES = [
    ("P0", "Identificar período y tipo de auditoría"), ("P1", "Inspeccionar estructura y fuentes"), ("P2", "Preflight de extractos"),
    ("P3", "Preflight de Money Pro"), ("P4", "Preflight de Splitwise"), ("P5", "Preflight de Datacrédito y fuentes condicionales"),
    ("P6", "Evaluación GO / NO-GO"), ("P7", "Auditoría de tarjetas"), ("P8", "Auditoría de bancos y efectivo"), ("P9", "Conciliación cruzada"),
    ("P10", "Utilidad de productos y controles históricos"), ("P11", "Excepciones y continuidad"), ("P12", "Actualización de los dos workbooks"),
    ("P13", "Validación de datos"), ("P14", "Informes separados TC y Bancos"), ("P15", "Refresh y validación del dashboard"),
    ("P16", "Reporte ejecutivo para Notion"), ("P17", "Notion: deduplicación, escritura y verificación"), ("P18", "Informe final de ejecución")]
PHASE_IDS = [p for p, _ in PHASES]
SEV_ORDER = {"INFO": 0, "WARNING": 1, "BLOCKER": 2}
CLASS_TXT = {
    "A": "Extracto localizado y legible", "B": "Extracto localizado pero ilegible o incompleto", "C": "Extracto no localizado (requerido)",
    "D": "Sin actividad — no requiere extracto", "D_OBS": "Sin actividad observada — sin canal de extracto (costo no verificable)",
    "E": "Producto cerrado o migrado", "F": "Estado no determinable", "N": "Producto no abierto en el mes"}
CLASS_SEV = {"A": "INFO", "B": "BLOCKER", "C": "BLOCKER", "D": "INFO", "D_OBS": "WARNING", "E": "INFO", "F": "BLOCKER", "N": "INFO"}


# ---------------------------------------------------------------------------------------------- período
class Period:
    def __init__(self, text):
        t = str(text).strip().upper().replace("-", "").replace(" ", "")
        m = re.fullmatch(r"(\d{4})Q([1-4])", t) or re.fullmatch(r"Q([1-4])(\d{4})", t)
        if m:
            y, q = (int(m.group(1)), int(m.group(2))) if t[0] != "Q" else (int(m.group(2)), int(m.group(1)))
            self.kind, self.year, self.quarter = "quarterly", y, q
            self.months = [(y, mm) for mm in range(3 * q - 2, 3 * q + 1)]
            self.key, self.label = f"{y}Q{q}", f"Q{q} {y}"
        elif re.fullmatch(r"(\d{4})(FY|ANUAL|ANNUAL)?", t):
            y = int(t[:4])
            self.kind, self.year, self.quarter = "annual", y, None
            self.months = [(y, mm) for mm in range(1, 13)]
            self.key, self.label = f"{y}", f"Anual {y}"
        else:
            raise SystemExit(f"Período no reconocido: {text!r}. Use 2026Q4, Q4 2026 o 2026 (anual).")
        self.start = dt.date(self.months[0][0], self.months[0][1], 1)
        ly, lm = self.months[-1]
        self.end = (dt.date(ly + (lm == 12), lm % 12 + 1, 1) - dt.timedelta(days=1))


def ym(s):
    y, m = s.split("-")
    return int(y), int(m)


def ym_str(y, m):
    return f"{y}-{m:02d}"


def fill(tpl, y, m):
    return tpl.replace("{Y}", str(y)).replace("{M}", f"{m:02d}").replace("{MON}", MON[m - 1]).replace("{QM}", f"{m:02d}")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------- PDF
def pdf_text(path, password):
    """Texto de un PDF. Usa pdftotext (poppler) o pypdf. Devuelve (texto | None, motivo)."""
    exe = shutil.which("pdftotext")
    if exe:
        cmd = [exe, "-layout"] + (["-upw", password] if password else []) + [path, "-"]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.decode("utf-8", "replace"), None
        err = r.stderr.decode("utf-8", "replace")
        if "password" in err.lower():
            return None, "PDF protegido: falta o no coincide la contraseña (variable de entorno)"
        return None, f"pdftotext no pudo leerlo: {err.strip()[:120]}"
    try:
        import pypdf  # noqa
        rd = pypdf.PdfReader(path)
        if rd.is_encrypted and not (password and rd.decrypt(password)):
            return None, "PDF protegido: falta o no coincide la contraseña (variable de entorno)"
        return "\n".join((p.extract_text() or "") for p in rd.pages), None
    except ImportError:
        return None, "No hay lector de PDF (instale poppler o pypdf)"
    except Exception as e:  # PDF dañado
        return None, f"PDF ilegible: {e}"


def month_from_name(tok):
    tok = tok.upper().strip(".")
    if tok in MON_ALT:
        return MON_ALT[tok]
    return MON.index(tok[:3]) + 1 if tok[:3] in MON else None


def statement_month_from_pdf(adapter, text, path):
    """(año, mes) del período facturado según el emisor, o None."""
    if adapter == "itau_pdf":
        m = re.search(r"Periodo de facturaci[oó]n\s+\d{2}/\d{2}/\d{4}\s+al\s+(\d{2})/(\d{2})/(\d{4})", text)
        return (int(m.group(3)), int(m.group(2))) if m else None
    if adapter == "bdb_pdf":
        m = re.search(r"Del\s+\d{2}/[A-Z]{3}/\d{4}\s+al\s+(\d{2})/([A-Z]{3})/(\d{4})", text)
        return (int(m.group(3)), month_from_name(m.group(2))) if m else None
    if adapter == "rappi_pdf":
        m = re.search(r"Hasta\s+(\d{1,2})\s+([a-zA-Z]{3,4})\.?\s+(\d{4})", text)
        return (int(m.group(3)), month_from_name(m.group(2))) if m else None
    if adapter == "occidente_pdf":
        m = re.search(r"FECHA DE CORTE\s*:\s*(\d{2})/(\d{2})/(\d{4})", text)
        return (int(m.group(3)), int(m.group(2))) if m else None
    return None


def rappi_balances(text):
    def num(s):
        return float(s.replace(".", "").replace(",", ".")) if s else None
    a = re.search(r"Saldo periodo anterior\s+\$\s?([\d\.,]+)", text)
    t = re.search(r"Pago total\s+\$\s?([\d\.,]+)", text.split("Detalle pago total")[-1]) if "Detalle pago total" in text else None
    return {"saldo_anterior": num(a.group(1)) if a else None, "pago_total": num(t.group(1)) if t else None}


# ---------------------------------------------------------------------------------------------- localizar extractos
class Finder:
    def __init__(self, root, password):
        self.root, self.password, self.pdf_cache = root, password, {}

    def _dir(self, folder, y):
        out = []
        if "{Y+}" in folder:
            for yy in (y, y + 1):
                out.append(os.path.join(self.root, folder.replace("{Y+}", str(yy))))
        else:
            out.append(os.path.join(self.root, folder.replace("{Y}", str(y))))
        return [d for d in out if os.path.isdir(d)]

    def pdf_index(self, seg, y):
        """Mapa (año, mes) -> [archivos] para un adaptador PDF; además lista de ilegibles."""
        found, unreadable = {}, []
        for d in self._dir(seg["folder"], y):
            for p in sorted(glob.glob(os.path.join(d, seg.get("glob", "*.pdf")))):
                if p not in self.pdf_cache:
                    self.pdf_cache[p] = pdf_text(p, self.password)
                txt, why = self.pdf_cache[p]
                if txt is None:
                    hint = None
                    if seg["adapter"] == "occidente_pdf":
                        m = re.search(r"(\d{4})(\d{2})(\d{2})", os.path.basename(p))
                        if m:
                            yy, mm = int(m.group(1)), int(m.group(2))
                            hint = (yy, mm - 1) if mm > 1 else (yy - 1, 12)
                    if seg["adapter"] == "bdb_pdf":
                        m = re.match(r"(\d{2})_(\d{4})_", os.path.basename(p))
                        hint = (int(m.group(2)), int(m.group(1))) if m else None
                    unreadable.append({"file": p, "why": why, "hint": hint})
                    continue
                if seg.get("card") and seg["card"] not in txt.replace(" ", ""):
                    continue
                key = statement_month_from_pdf(seg["adapter"], txt, p)
                if key:
                    found.setdefault(key, []).append(p)
        return found, unreadable

    def locate(self, seg, y, m):
        """Devuelve dict(status A/B/C, files, note, extra)."""
        ad = seg["adapter"]
        if ad == "file_name":
            files = [p for d in self._dir(seg["folder"], y) for p in glob.glob(os.path.join(d, fill(seg["pattern"], y, m)))]
            return self._xlsx_check(files)
        if ad == "zip_member":
            member = fill(seg["member"], y, m)
            zips = [p for d in self._dir(seg["folder"], y) for p in glob.glob(os.path.join(d, fill(seg["zip_glob"], y, m)))]
            hits, bad = [], []
            for z in zips:
                try:
                    with zipfile.ZipFile(z) as zf:
                        if member in zf.namelist():
                            data = zf.read(member)
                            if len(data) < 200:
                                bad.append(f"{os.path.basename(z)}!{member} (vacío)")
                            else:
                                hits.append(f"{z}!{member}")
                except zipfile.BadZipFile:
                    bad.append(f"{os.path.basename(z)} (zip dañado)")
            if hits:
                return {"status": "A", "files": hits, "note": "" if len(hits) == 1 else "duplicado"}
            if bad:
                return {"status": "B", "files": bad, "note": "archivo localizado pero dañado/vacío"}
            return {"status": "C", "files": [], "note": f"no se encontró {member} en {fill(seg['zip_glob'], y, m)}"}
        if ad.endswith("_pdf"):
            idx, unreadable = self.pdf_index(seg, y)
            hits = idx.get((y, m), [])
            if hits:
                return {"status": "A", "files": hits, "note": "" if len(hits) == 1 else "duplicado de período"}
            cand = [u for u in unreadable if u["hint"] in (None, (y, m))]
            if cand:
                return {"status": "B", "files": [u["file"] for u in cand], "note": "; ".join(sorted({u['why'] for u in cand}))}
            return {"status": "C", "files": [], "note": "ningún extracto del emisor cubre este mes"}
        return {"status": None, "files": [], "note": ""}

    @staticmethod
    def _xlsx_check(files):
        if not files:
            return {"status": "C", "files": [], "note": "archivo no encontrado"}
        ok, bad = [], []
        for p in files:
            try:
                with zipfile.ZipFile(p) as zf:
                    zf.testzip()
                ok.append(p)
            except Exception:
                bad.append(p)
        if ok:
            return {"status": "A", "files": ok, "note": "" if len(ok) == 1 else "duplicado"}
        return {"status": "B", "files": bad, "note": "xlsx dañado"}


# ---------------------------------------------------------------------------------------------- preflight
def segment_for(prod, y, m):
    k = ym_str(y, m)
    seg = None
    for s in prod["segments"]:
        if s["from"] <= k and (not s.get("to") or k <= s["to"]):
            seg = s
    return seg


def load_declarations(workdir):
    p = os.path.join(workdir, "declarations.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def months_needed(period, prod):
    if prod.get("frequency") == "quarterly":
        if period.kind == "quarterly":
            return [period.months[-1]]
        return [(period.year, q * 3) for q in range(1, 5)]
    return period.months


def coverage(period, reg, finder, declarations):
    rows, notes = [], []
    decl = {(d["product"], d["month"]): d for d in declarations}
    for prod in reg["products"]:
        prev_rappi = None
        for (y, m) in months_needed(period, prod):
            k = ym_str(y, m)
            row = {"product": prod["id"], "name": prod["name"], "mask": prod["mask"], "module": prod["module"], "month": k,
                   "bank": None, "status": None, "files": [], "observations": ""}
            if k < prod.get("opened", "1900-01"):
                row.update(status="N", observations=f"abierto en {prod['opened']}")
                rows.append(row)
                continue
            seg = segment_for(prod, y, m)
            if seg is None:
                row.update(status="F", observations="no hay segmento de ciclo de vida para el mes (actualice audit_sources.json)")
                rows.append(row)
                continue
            row["bank"] = seg["bank"]
            if seg["adapter"] == "closed":
                ev = seg.get("event", {})
                row.update(status="E", observations=f"cerrado {ev.get('date')} · evidencia: {ev.get('evidence', 'pendiente')}")
            elif seg["adapter"] == "none":
                row.update(status="D_OBS", observations=seg.get("no_source_reason", ""))
            else:
                r = finder.locate(seg, y, m)
                row.update(status=r["status"], files=r["files"], observations=r["note"])
                if prod.get("statements_only_with_activity") and seg["adapter"] == "rappi_pdf":
                    if r["status"] == "A":
                        txt = finder.pdf_cache.get(r["files"][0], (None, None))[0] or ""
                        bal = rappi_balances(txt)
                        row["balances"] = bal
                        prev_rappi = bal
                    elif r["status"] == "C":
                        nxt = None
                        idx = {}
                        for yy in (y - 1, y, y + 1):
                            idx.update(finder.pdf_index(seg, yy)[0])
                        later = sorted(kk for kk in idx if kk > (y, m))
                        earlier = sorted(kk for kk in idx if kk < (y, m))
                        if later:
                            nxt = rappi_balances(finder.pdf_cache[idx[later[0]][0]][0])
                        if earlier and prev_rappi is None:
                            prev_rappi = rappi_balances(finder.pdf_cache[idx[earlier[-1]][0]][0])
                        if prev_rappi and prev_rappi.get("pago_total") == 0 and (nxt is None or nxt.get("saldo_anterior") == 0):
                            row.update(status="D", observations="emisor solo emite extracto con actividad; saldo 0 antes y después del vacío"
                                       + ("" if nxt else " (provisional: confirmar con el siguiente extracto)"))
                if seg.get("event") and r["status"] in ("A", "C") and seg["event"].get("type") == "migrated":
                    row["observations"] = (row["observations"] + " · " if row["observations"] else "") + f"emisor nuevo desde {seg['event']['date']}"
            d = decl.get((prod["id"], k))
            if d and row["status"] in ("C", "F", "D_OBS"):
                row.update(status=d["class"], observations=f"DECLARADO por el usuario: {d.get('evidence', '')}")
                if not d.get("evidence"):
                    row.update(status="F", observations="declaración sin evidencia: no se acepta")
            row["class_text"] = CLASS_TXT.get(row["status"], "?")
            row["severity"] = CLASS_SEV.get(row["status"], "BLOCKER")
            rows.append(row)
    for row in rows:
        row.setdefault("class_text", CLASS_TXT.get(row["status"], "?"))
        row.setdefault("severity", CLASS_SEV.get(row["status"], "BLOCKER"))
    return rows


def read_csv_dates(path, date_col, fmt):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()
    lines = raw.splitlines()
    hdr_i = next((i for i, l in enumerate(lines) if l.split(";")[0].strip() == date_col or l.split(",")[0].strip() == date_col), None)
    if hdr_i is None:
        return None, [], "no se encontró la fila de encabezado"
    delim = ";" if lines[hdr_i].count(";") > lines[hdr_i].count(",") else ","
    rdr = csv.reader(lines[hdr_i:], delimiter=delim)
    hdr = next(rdr)
    dates = []
    for r in rdr:
        if not r or not r[0].strip():
            continue
        try:
            dates.append(dt.datetime.strptime(r[0].strip(), fmt).date())
        except ValueError:
            continue
    return hdr, dates, None


def check_csv_source(key, src, period, root):
    files = sorted(glob.glob(os.path.join(root, src.get("folder", ""), src["glob"])))
    res = {"source": key, "label": src["label"], "requirement": src["requirement"], "expected": os.path.join(src.get("folder", ""), src["glob"]),
           "files": [], "status": "NOT_FOUND", "severity": "BLOCKER", "detail": "", "consequence": src.get("consequence", "")}
    if not files:
        res["detail"] = "no se encontró ningún archivo"
        return res
    best = None
    for p in files:
        hdr, dates, err = read_csv_dates(p, src["columns"][0], src["date_format"])
        info = {"file": p, "rows": len(dates)}
        if err or not dates:
            info["error"] = err or "sin fechas legibles"
            res["files"].append(info)
            continue
        miss = [c for c in src["columns"] if c not in [h.strip() for h in hdr]]
        info.update(first=str(min(dates)), last=str(max(dates)), missing_columns=miss)
        exp = None
        if src.get("export_date_regex"):
            mm = re.search(src["export_date_regex"], os.path.basename(p))
            exp = dt.date.fromisoformat(mm.group(1)) if mm else None
            info["export_date"] = str(exp) if exp else None
        in_period = [d for d in dates if period.start <= d <= period.end]
        info["rows_in_period"] = len(in_period)
        covers_start = min(dates) <= period.start + dt.timedelta(days=10)
        if key == "moneypro":
            covers_end = max(dates) >= period.end - dt.timedelta(days=src.get("max_gap_days_end", 5))
        else:
            covers_end = (exp is not None and exp >= period.end) or max(dates) >= period.end
        info["covers"] = bool(covers_start and covers_end and not miss and in_period)
        res["files"].append(info)
        if info["covers"] and (best is None or info["rows_in_period"] > best["rows_in_period"]):
            best = info
    if best:
        res.update(status="OK", severity="INFO", detail=f"{os.path.basename(best['file'])}: {best['first']} → {best['last']}, {best['rows_in_period']} filas en el período")
    else:
        bad = res["files"][-1] if res["files"] else {}
        why = []
        if bad.get("missing_columns"):
            why.append(f"faltan columnas {bad['missing_columns']}")
        if bad.get("error"):
            why.append(bad["error"])
        if bad.get("last"):
            why.append(f"cubre {bad.get('first')} → {bad.get('last')}{' (export ' + bad['export_date'] + ')' if bad.get('export_date') else ''}; el período termina {period.end}")
        res.update(status="INCOMPLETE", severity="BLOCKER", detail="; ".join(why) or "no cubre el período")
    return res


def check_conditional(reg, period, root, cov_rows, workbook_tc):
    out = []
    S = reg["sources"]
    # Datacrédito: productos cerrados / migrados en el período (o siempre en la anual)
    events = []
    for prod in reg["products"]:
        for s in prod["segments"]:
            ev = s.get("event")
            if ev and period.start <= dt.date.fromisoformat(ev["date"]) + dt.timedelta(days=1) <= period.end + dt.timedelta(days=1):
                events.append((prod, ev))
    dc_files = sorted(glob.glob(os.path.join(root, S["datacredito"]["folder"], S["datacredito"]["glob"])))
    dc_dates = []
    for p in dc_files:
        m = re.search(S["datacredito"]["date_regex"], os.path.basename(p))
        if m:
            mo, d, yy = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
            dc_dates.append((dt.date(yy, mo, d), p))
    latest = max(dc_dates) if dc_dates else None
    if period.kind == "annual":
        ok = latest and latest[0] >= period.end
        out.append({"source": "datacredito", "label": S["datacredito"]["label"], "requirement": "mandatory (anual)", "status": "OK" if ok else "MISSING",
                    "severity": "INFO" if ok else "BLOCKER", "files": [latest[1]] if latest else [],
                    "detail": f"reporte {latest[0]}" if latest else "no hay reporte", "consequence": "Anual: sin Datacrédito posterior al cierre no se confirma el inventario de productos."})
    for prod, ev in events:
        ok = latest and latest[0] >= dt.date.fromisoformat(ev["date"])
        out.append({"source": "datacredito", "label": f"Datacrédito — {prod['id']} {ev['type']} {ev['date']}", "requirement": "conditional",
                    "status": "OK" if ok else "MISSING", "severity": "INFO" if ok else "WARNING", "files": [latest[1]] if latest else [],
                    "detail": (f"reporte {latest[0]} posterior al evento" if ok else "no hay reporte posterior al evento") + f" · {ev.get('note', '')}",
                    "consequence": S["datacredito"]["consequence"], "scope": prod["id"]})
    # Puntos Colombia
    pc = sorted(glob.glob(os.path.join(root, S["puntos"]["folder"], S["puntos"]["glob"])))
    pc_res = {"source": "puntos", "label": S["puntos"]["label"], "requirement": "conditional", "files": pc, "consequence": S["puntos"]["consequence"]}
    if not pc:
        pc_res.update(status="MISSING", severity="WARNING", detail="no hay export")
    else:
        try:
            import openpyxl
            info = []
            for p in pc:
                wb = openpyxl.load_workbook(p, read_only=True)
                try:
                    rows = [r for r in wb.worksheets[0].iter_rows(values_only=True)]
                finally:
                    wb.close()  # read_only mantiene el archivo abierto; en Windows impide borrarlo
                dates = []
                for r in rows:
                    v = r[0]
                    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                        dates.append(dt.date.fromisoformat(v))
                    elif isinstance(v, (dt.date, dt.datetime)):
                        dates.append(v if isinstance(v, dt.date) else v.date())
                info.append((p, len(dates), min(dates) if dates else None, max(dates) if dates else None))
            cov = [i for i in info if i[2] and i[2] <= period.start and i[3] >= period.end - dt.timedelta(days=20)]
            capped = [i for i in info if i[1] >= S["puntos"]["row_cap"]]
            same = len({sha256(p) for p in pc}) < len(pc)
            det = "; ".join(f"{os.path.basename(p)}: {n} mov. {a} → {b}" for p, n, a, b in info)
            if capped:
                det += f" · export con {S['puntos']['row_cap']} filas (tope del portal: puede estar truncado)"
            if same:
                det += " · hay exports idénticos con nombres distintos"
            pc_res.update(status="OK" if cov else "INCOMPLETE", severity="WARNING" if (capped or same or not cov) else "INFO", detail=det)
        except Exception as e:
            pc_res.update(status="UNREADABLE", severity="WARNING", detail=str(e))
    out.append(pc_res)
    # Control histórico Primax
    pm = S["primax_control"]
    p = os.path.join(root, pm["workbook"])
    res = {"source": "primax_control", "label": pm["label"], "requirement": "historical_control", "files": [p] if os.path.exists(p) else [], "consequence": pm["consequence"]}
    if not os.path.exists(p):
        res.update(status="MISSING", severity="WARNING", detail="no se encontró la auditoría Primax; valorar redenciones como 'Sin evidencia'")
    else:
        import openpyxl
        ws = openpyxl.load_workbook(p, data_only=True)[pm["sheet"]]
        pend = []
        for r in ws.iter_rows(values_only=True):
            if r and len(r) >= 9 and str(r[1] or "").strip() == "Primax" and "pendiente" in str(r[8] or "").lower():
                pend.append(f"{r[3]:%Y-%m-%d}→{(r[4].strftime('%Y-%m-%d') if isinstance(r[4], dt.datetime) else 'vigente')}" if isinstance(r[3], dt.datetime) else str(r[3]))
        res.update(status="PENDING" if pend else "OK", severity="WARNING" if pend else "INFO",
                   detail=(f"equivalencia Primax PENDIENTE para {', '.join(pend)}: valorar como ESTIMADO; no cambiar Parametros!B19 sin comprobante" if pend else "equivalencias verificadas"))
    out.append(res)
    # Beneficios (informativo)
    bf = sorted(glob.glob(os.path.join(root, S["beneficios"]["folder"], S["beneficios"]["glob"])))
    out.append({"source": "beneficios", "label": S["beneficios"]["label"], "requirement": "conditional", "status": "OK" if bf else "MISSING", "severity": "INFO",
                "files": bf, "detail": f"{len(bf)} documento(s)", "consequence": S["beneficios"]["consequence"]})
    # Anual: reporte de costos del emisor
    if period.kind == "annual":
        cb = S["costos_bancolombia"]
        f = os.path.join(root, cb["folder"], fill(cb["pattern"], period.year, 12))
        ok = os.path.exists(f)
        out.append({"source": "costos_bancolombia", "label": cb["label"], "requirement": "annual", "status": "OK" if ok else "MISSING",
                    "severity": "INFO" if ok else "WARNING", "files": [f] if ok else [], "detail": os.path.basename(f), "consequence": cb["consequence"]})
    return out


def unincorporated_evidence(period, cov_rows, workbook_tc):
    """Extractos de tarjetas localizados que el libro no cita en Extractos_Input (Archivo)."""
    if not workbook_tc or not os.path.exists(workbook_tc):
        return []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(workbook_tc, read_only=True, data_only=True)
        try:
            rows = list(wb["Extractos_Input"].iter_rows(values_only=True))
        finally:
            wb.close()
        hdr_i = next(i for i, r in enumerate(rows[:10]) if r and "Archivo" in r)
        ai = rows[hdr_i].index("Archivo")
        cited = " ".join(str(r[ai]) for r in rows[hdr_i + 1:] if r and r[ai])
    except Exception:
        return []
    out = []
    for r in cov_rows:
        if r["module"] != "tc" or r["status"] != "A":
            continue
        for f in r["files"]:
            base = os.path.basename(f.split("!")[-1])
            stem = os.path.basename(f.split("!")[0])
            if base not in cited and stem not in cited:
                out.append({"product": r["product"], "month": r["month"], "file": f})
    return out


def prior_period_evidence(period, reg, finder, workbook_tc):
    """Evidencia de meses YA auditados del mismo año que el libro no incorpora (p. ej. extracto llegado después del cierre)."""
    if period.kind != "quarterly" or period.quarter == 1:
        return []
    prev = Period(f"{period.year}Q1")
    prev.months = [(period.year, mm) for mm in range(1, period.months[0][1])]
    rows = coverage(prev, {"products": [p for p in reg["products"] if p["module"] == "tc"]}, finder, [])
    out = unincorporated_evidence(prev, rows, workbook_tc)
    out += [{"product": r["product"], "month": r["month"], "file": None, "gap": True} for r in rows if r["status"] in ("B", "C", "F")]
    return out


def quarterly_closes_for_annual(period, dash_root):
    out = []
    for q in range(1, 5):
        st = os.path.join(dash_root, "work", f"{period.year}Q{q}", "audit_state.json")
        state = None
        if os.path.exists(st):
            with open(st, encoding="utf-8") as f:
                state = json.load(f).get("overall")
        pdfs = [os.path.exists(os.path.join(dash_root, "deliverables", str(period.year), f"Auditoria_Trimestral_{m}_Q{q}_{period.year}.pdf")) for m in ("TC", "Bancos")]
        ok = state == "COMPLETED" or (state is None and all(pdfs))
        out.append({"quarter": f"Q{q}", "state": state or ("LEGACY (PDFs emitidos)" if all(pdfs) else "SIN CIERRE"), "ok": ok})
    return out


def load_registry(path):
    """Registro de productos. Es privado (no versionado); el repositorio trae examples/audit_sources.example.json."""
    if not os.path.exists(path):
        sys.exit(f"No existe el registro de productos {path}. Copie examples/audit_sources.example.json a "
                 "scripts/audit_sources.json y adáptelo a sus productos, o use --registry.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_preflight(args):
    reg = load_registry(args.registry)
    period = Period(args.period)
    dash = os.path.abspath(args.dashboard_root)
    root = os.path.abspath(args.evidence_root or os.path.join(dash, reg["evidence_root"]))
    workdir = os.path.join(dash, "work", period.key)
    os.makedirs(workdir, exist_ok=True)
    pw = os.environ.get(reg.get("pdf_password_env", "AUDIT_PDF_PASSWORD"))
    finder = Finder(root, pw)
    wb_tc = os.path.join(dash, reg["workbooks"]["tc"])
    wb_bank = os.path.join(dash, reg["workbooks"]["bank"])
    issues = []

    def issue(sev, phase, text, scope="global"):
        issues.append({"severity": sev, "phase": phase, "scope": scope, "text": text})

    # P1 estructura
    wbs = []
    for k, p in (("tc", wb_tc), ("bank", wb_bank)):
        ok = os.path.exists(p)
        wbs.append({"role": k, "path": p, "exists": ok, "sha256": sha256(p) if ok else None,
                    "modified": dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds") if ok else None})
        if not ok:
            issue("BLOCKER", "P1", f"No existe el libro {k}: {p}")
    if not os.path.isdir(root):
        issue("BLOCKER", "P1", f"No existe la carpeta de evidencia {root}")
    for need in ("scripts/refresh_dashboard.py", "scripts/build_quarterly_reports.py", "scripts/validate_system.py", "scripts/config.json"):
        if not os.path.exists(os.path.join(dash, need)):
            issue("BLOCKER", "P1", f"Falta {need}")
    # P2 extractos
    cov = coverage(period, reg, finder, load_declarations(workdir)) if os.path.isdir(root) else []
    for r in cov:
        if r["severity"] in ("BLOCKER", "WARNING"):
            issue(r["severity"], "P2", f"{r['product']} {r['month']}: {r['class_text']}{' — ' + r['observations'] if r['observations'] else ''}", r["product"])
        if "duplicado" in (r.get("observations") or ""):
            issue("WARNING", "P2", f"{r['product']} {r['month']}: {len(r['files'])} archivos para el mismo período — elegir el oficial y documentarlo", r["product"])
    # P3/P4 fuentes obligatorias
    src = []
    for key in ("moneypro", "splitwise"):
        s = check_csv_source(key, reg["sources"][key], period, root)
        src.append(s)
        if s["severity"] != "INFO":
            ph = "P3" if key == "moneypro" else "P4"
            scope = "global" if key == "moneypro" else "tc:gastos compartidos/CxC"
            issue(s["severity"], ph, f"{s['label']}: {s['detail']}. {s['consequence']}", scope)
    # P5 condicionales
    cond = check_conditional(reg, period, root, cov, wb_tc)
    for c in cond:
        if c["severity"] != "INFO":
            issue(c["severity"], "P5", f"{c['label']}: {c['detail']}. {c.get('consequence', '')}", c.get("scope", "global"))
    late = prior_period_evidence(period, reg, finder, wb_tc)
    for e in late:
        if e.get("gap"):
            issue("WARNING", "P5", f"Hueco de cobertura en un período ya cerrado: {e['product']} {e['month']} sigue sin extracto. "
                  "La conclusión de ese producto en el cierre anterior debe reevaluarse cuando llegue el extracto.", e["product"])
        else:
            issue("WARNING", "P5", f"Evidencia posterior al cierre no incorporada: {e['product']} {e['month']} ({os.path.basename(e['file'].split('!')[0])}). "
                  "Reevaluar la conclusión de ese producto antes de cerrar el período.", e["product"])
    annual = None
    if period.kind == "annual":
        annual = quarterly_closes_for_annual(period, dash)
        for a in annual:
            if not a["ok"]:
                issue("BLOCKER", "P5", f"Anual: {a['quarter']} {period.year} sin cierre trimestral ({a['state']}). La anual consolida; no sustituye los trimestres.")
    # P6 GO / NO-GO
    blockers = [i for i in issues if i["severity"] == "BLOCKER"]
    partial_ok = False
    if args.partial_scope and blockers:
        mod = args.partial_scope
        partial_ok = all(not (i["scope"] == "global" or i["scope"].startswith(mod) or
                              any(r["product"] == i["scope"] and r["module"] == mod for r in cov)) for i in blockers)
    decision = "GO" if not blockers else ("GO-PARCIAL" if partial_ok else "NO-GO")
    result = {
        "type": period.kind, "period": period.label, "period_key": period.key, "from": str(period.start), "to": str(period.end),
        "executed_at": dt.datetime.now().isoformat(timespec="seconds"), "evidence_root": root, "dashboard_root": dash, "workbooks": wbs,
        "coverage": cov, "sources": src, "conditional": cond, "late_evidence": late, "annual_quarters": annual,
        "issues": issues, "decision": decision, "partial_scope": args.partial_scope if decision == "GO-PARCIAL" else None,
        "counts": {c: sum(1 for r in cov if r["status"] == c) for c in CLASS_TXT},
        "pdf_password_provided": bool(pw)}
    with open(os.path.join(workdir, f"preflight_{period.key}.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(workdir, f"preflight_{period.key}.md"), "w", encoding="utf-8") as f:
        f.write(render_preflight(result))
    st = load_state(workdir, period)
    now = result["executed_at"]
    for p in ("P0", "P1", "P2", "P3", "P4", "P5"):
        sev = max([SEV_ORDER[i["severity"]] for i in issues if i["phase"] == p] or [0])
        st["phases"][p] = {"status": "DONE", "result": ["PASS", "WARNING", "BLOCKED"][sev], "at": now}
    st["phases"]["P6"] = {"status": "DONE", "result": decision, "at": now}
    st["overall"] = "GO" if decision == "GO" else ("PARTIAL" if decision == "GO-PARCIAL" else "BLOCKED")
    st["blocked_reason"] = None if decision != "NO-GO" else "Preflight NO-GO"
    st["preflight"] = f"preflight_{period.key}.json"
    save_state(workdir, st)
    print(render_preflight(result, short=True))
    return 0 if decision != "NO-GO" else 2


def render_preflight(r, short=False):
    L = [f"FINANCIAL ACCOUNT AUDIT — PREFLIGHT", f"Tipo: {r['type']} · Período: {r['period']} ({r['from']} → {r['to']}) · Ejecutado: {r['executed_at']}",
         f"RESULTADO: {r['decision']}" + (f" (solo módulo {r['partial_scope']}; el consolidado NO queda completo)" if r.get("partial_scope") else ""), ""]
    L.append("Workbooks: " + " · ".join(f"{w['role']}={'OK' if w['exists'] else 'NO EXISTE'} ({(w['sha256'] or '')[:12]})" for w in r["workbooks"]))
    L.append("Cobertura: " + " · ".join(f"{k} {CLASS_TXT[k]}: {v}" for k, v in r["counts"].items() if v))
    L.append(f"Contraseña PDF provista: {'sí' if r['pdf_password_provided'] else 'NO (los PDF protegidos quedan ilegibles)'}")
    bl = [i for i in r["issues"] if i["severity"] == "BLOCKER"]
    wn = [i for i in r["issues"] if i["severity"] == "WARNING"]
    if bl:
        L += ["", "BLOQUEOS (impiden la auditoría):"] + [f"  {n}. [{i['phase']}] {i['text']}" for n, i in enumerate(bl, 1)]
    if wn:
        L += ["", "ADVERTENCIAS (limitan conclusiones específicas):"] + [f"  - [{i['phase']}] {i['text']}" for i in wn]
    if short:
        if r["decision"] == "NO-GO":
            L += ["", "Proceso detenido en P6. No se analizaron transacciones, no se modificaron libros, dashboard ni Notion."]
        return "\n".join(L)
    L += ["", "## Matriz de cobertura (producto × mes)", "", "| Producto | Mes | Banco | Clase | Archivo(s) | Observaciones |", "|---|---|---|---|---|---|"]
    for c in r["coverage"]:
        L.append(f"| {c['product']} {c['mask']} | {c['month']} | {c['bank'] or ''} | {c['status']} — {c['class_text']} | "
                 f"{'; '.join(os.path.basename(f.split('!')[0]) + ('!' + f.split('!')[1] if '!' in f else '') for f in c['files'])} | {c['observations']} |")
    L += ["", "## Fuentes", "", "| Fuente | Requisito | Estado | Detalle | Consecuencia si falta |", "|---|---|---|---|---|"]
    for s in r["sources"] + r["conditional"]:
        L.append(f"| {s['label']} | {s['requirement']} | {s['status']} ({s['severity']}) | {s.get('detail', '')} | {s.get('consequence', '')} |")
    if r.get("annual_quarters"):
        L += ["", "## Cierres trimestrales (anual)"] + [f"- {a['quarter']}: {a['state']}" for a in r["annual_quarters"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------------------------- estado de fases
def load_state(workdir, period):
    p = os.path.join(workdir, "audit_state.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"period": period.label, "period_key": period.key, "type": period.kind, "overall": "NEW", "phases": {}, "log": []}


def save_state(workdir, st):
    with open(os.path.join(workdir, "audit_state.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def can_start(st, ph):
    """(ok, motivo). Orden estricto; nada después de un bloqueo; nada sin GO."""
    if st.get("overall") == "BLOCKED":
        return False, f"La ejecución está BLOQUEADA ({st.get('blocked_reason')}). Resuelva y vuelva a correr el preflight."
    i = PHASE_IDS.index(ph)
    if i <= 6:
        return False, "P0–P6 los ejecuta 'preflight'."
    if st["phases"].get("P6", {}).get("result") not in ("GO", "GO-PARCIAL"):
        return False, "No hay GO del preflight."
    for prev in PHASE_IDS[7:i]:
        p = st["phases"].get(prev, {})
        if p.get("status") != "DONE":
            return False, f"La fase {prev} no está terminada."
        if p.get("result") == "BLOCKED":
            return False, f"La fase {prev} quedó BLOQUEADA."
    if ph == "P17":
        p15 = st["phases"].get("P15", {})
        if p15.get("result") != "PASS" and p15.get("result") != "WARNING":
            return False, "Notion solo se escribe con el dashboard refrescado y validado (P15)."
        if st.get("overall") == "PARTIAL":
            return False, "Ejecución PARCIAL: no se escribe el reporte de cierre en Notion."
    return True, ""


def run_phase(args):
    period = Period(args.period)
    workdir = os.path.join(os.path.abspath(args.dashboard_root), "work", period.key)
    os.makedirs(workdir, exist_ok=True)
    st = load_state(workdir, period)
    now = dt.datetime.now().isoformat(timespec="seconds")
    if args.start:
        ok, why = can_start(st, args.start)
        if not ok:
            print(f"FASE {args.start} RECHAZADA: {why}")
            return 3
        st["phases"][args.start] = {"status": "RUNNING", "at": now}
        st["log"].append(f"{now} start {args.start}")
        save_state(workdir, st)
        print(f"FASE {args.start} ({dict(PHASES)[args.start]}) autorizada.")
        return 0
    if args.done:
        if st["phases"].get(args.done, {}).get("status") != "RUNNING":
            print(f"FASE {args.done}: no estaba en curso (use --start primero).")
            return 3
        res = args.result or "PASS"
        st["phases"][args.done] = {"status": "DONE", "result": res, "at": now, "note": args.note}
        st["log"].append(f"{now} done {args.done} {res} {args.note or ''}")
        if res == "BLOCKED":
            st["overall"], st["blocked_reason"] = "BLOCKED", f"{args.done}: {args.note}"
        elif args.done == "P18":
            st["overall"] = "COMPLETED" if st.get("overall") == "GO" else st.get("overall")
        save_state(workdir, st)
        print(f"FASE {args.done} registrada: {res}. Estado global: {st['overall']}")
        return 2 if res == "BLOCKED" else 0
    return run_status(args)


def run_status(args):
    period = Period(args.period)
    st = load_state(os.path.join(os.path.abspath(args.dashboard_root), "work", period.key), period)
    print(f"FINANCIAL ACCOUNT AUDIT — {st['period']} · estado {st['overall']}" + (f" · {st.get('blocked_reason')}" if st.get("blocked_reason") else ""))
    for p, name in PHASES:
        s = st["phases"].get(p, {})
        print(f"  {p:4s} {name:52s} {s.get('status', 'PENDIENTE'):9s} {s.get('result', '')}")
    return 0


# ---------------------------------------------------------------------------------------------- respaldo, dashboard, excepciones
def run_backup(args):
    reg = load_registry(args.registry)
    period = Period(args.period)
    dash = os.path.abspath(args.dashboard_root)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(dash, "source", "archive", f"pre_{period.key}_{stamp}")
    os.makedirs(dest, exist_ok=True)
    lines = []
    for k, rel in reg["workbooks"].items():
        src = os.path.join(dash, rel)
        shutil.copy2(src, dest)
        lines.append(f"{sha256(src)}  {os.path.basename(src)}")
    with open(os.path.join(dest, "MANIFEST_SHA256.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Respaldo en {dest}\n" + "\n".join(lines))
    return 0


def run_verify_dashboard(args):
    period = Period(args.period)
    dash = os.path.abspath(args.dashboard_root)
    workdir = os.path.join(dash, "work", period.key)
    st = load_state(workdir, period)
    problems = []
    try:
        meta = json.load(open(os.path.join(dash, "data", "metadata.json"), encoding="utf-8"))
        dq = json.load(open(os.path.join(dash, "data", "data_quality.json"), encoding="utf-8"))
        cc = json.load(open(os.path.join(dash, "data", "credit_cards.json"), encoding="utf-8"))
        bk = json.load(open(os.path.join(dash, "data", "bank_cash.json"), encoding="utf-8"))
    except Exception as e:
        problems.append(f"no se pudieron leer los datasets: {e}")
        meta = dq = cc = bk = {}
    if meta:
        if meta.get("status") == "FAILED":
            problems.append(f"el último refresh FALLÓ: {meta.get('message')}")
        if (meta.get("reconciliation") or {}).get("failed"):
            problems.append(f"{meta['reconciliation']['failed']} conciliaciones Excel vs ETL fallidas")
        if (dq.get("summary") or {}).get("ERROR"):
            problems.append(f"Calidad de datos con {dq['summary']['ERROR']} ERROR")
        qs = [f"Q{q}-{period.year}" for q in ([period.quarter] if period.quarter else range(1, 5))]
        have_tc = {r["period"] for r in cc.get("quarter_summary", [])}
        have_bk = set((bk.get("historico_trimestral") or {}).get("periods", []))
        miss = [q for q in qs if q not in have_tc or q not in have_bk]
        if miss:
            problems.append(f"el dashboard no tiene {', '.join(miss)} en ambos módulos")
        last = meta.get("last_refresh")
        p6 = st["phases"].get("P6", {}).get("at")
        if last and p6 and last < p6.replace("T", " "):
            problems.append(f"el refresh ({last}) es anterior al preflight ({p6}): refresque después de actualizar los libros")
    res = "BLOCKED" if problems else "PASS"
    now = dt.datetime.now().isoformat(timespec="seconds")
    st["phases"]["P15"] = {"status": "DONE", "result": res, "at": now, "note": "; ".join(problems) or "refresh OK, conciliaciones OK, período presente en TC y Bancos"}
    if problems:
        st["overall"], st["blocked_reason"] = "BLOCKED", "P15: " + "; ".join(problems)
    save_state(workdir, st)
    print(f"DASHBOARD {res}" + ("".join(f"\n  - {p}" for p in problems) if problems else ""))
    return 2 if problems else 0


def run_check_exceptions(args):
    dash = os.path.abspath(args.dashboard_root)
    ex = json.load(open(os.path.join(dash, "data", "exceptions.json"), encoding="utf-8"))["exceptions"]
    cont = json.load(open(os.path.join(dash, "data", "continuity.json"), encoding="utf-8"))
    cats = {r["Finding_ID"]: r.get("category_code") for r in cont.get("matrix", [])}
    bad = []
    for e in ex:
        if e.get("is_historical") and e.get("is_open") and cats.get(e["ID"]) in ("A", "E", "F"):
            bad.append(f"{e['ID']} (categoría {cats.get(e['ID'])}) aparece ABIERTO: un hallazgo resuelto no se reabre; cree una excepción nueva vinculada")
    ids = [e["ID"] for e in ex]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        bad.append(f"IDs duplicados: {dup}")
    print("EXCEPCIONES " + ("ERROR\n  - " + "\n  - ".join(bad) if bad else f"OK ({len(ex)} registros; ningún histórico resuelto reabierto)"))
    return 2 if bad else 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("preflight", "phase", "status", "backup", "verify-dashboard", "check-exceptions"):
        s = sub.add_parser(name)
        s.add_argument("--period", required=name != "check-exceptions")
        s.add_argument("--dashboard-root", default=DASH_ROOT)
        s.add_argument("--registry", default=REGISTRY)
        if name == "preflight":
            s.add_argument("--evidence-root", default=None, help="Carpeta 'Informacion Bancaria' (o su copia preparada en Cowork)")
            s.add_argument("--partial-scope", choices=["tc", "bank"], default=None, help="Permite ejecutar SOLO un módulo si los bloqueos no lo afectan (resultado PARCIAL)")
        if name == "phase":
            s.add_argument("--start")
            s.add_argument("--done")
            s.add_argument("--result", choices=["PASS", "WARNING", "BLOCKED"])
            s.add_argument("--note")
    a = ap.parse_args(argv)
    return {"preflight": run_preflight, "phase": run_phase, "status": run_status, "backup": run_backup,
            "verify-dashboard": run_verify_dashboard, "check-exceptions": run_check_exceptions}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_system.py — validación final del sistema (15 controles PASS / WARNING / ERROR).

    python scripts/validate_system.py                 # escribe validation/Validacion_<fecha>.md y .json
    python scripts/validate_system.py --browser-results validation/browser_checks.json   # añade pruebas del navegador

Se ejecuta después de refresh_dashboard.py. No modifica los libros (solo lectura). Ejecuta el ETL dos veces
en modo --check para probar que el refresh es repetible sin tocar código.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import refresh_dashboard as R  # noqa: E402

RESULTS = []


def add(n, name, status, detail):
    RESULTS.append({"n": n, "control": name, "status": status, "detail": detail})


def worst(*s):
    return "ERROR" if "ERROR" in s else "WARNING" if "WARNING" in s else "PASS"


def J(name):
    with open(os.path.join(ROOT, "data", name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser-results", default=None)
    args = ap.parse_args(argv)
    cfg = R.load_config()
    meta, cc, bk, ex, tl, ct, pu, dq = (J(n) for n in R.DATASETS[:8])
    exc = ex["exceptions"]
    cy = meta.get("current_audit_year")
    by = meta.get("baseline_year")

    # 1. Estructura
    errs = [e for e in meta.get("errors", []) if e["code"] in ("MISSING_SHEET", "MISSING_COLUMN", "HEADER_NOT_FOUND")]
    new_sheets = {"tc": ["Continuidad_Hallazgos", "Ciclo_Vida_Productos", "Productos_Financieros", "Controles_Trimestrales"],
                  "bank": ["Controles_Trimestrales", "Fiducuenta_TC", "Pagos_TC_Trimestral", "Materiales_Trimestral", "Transferencias_Mensuales", "Historico_Trimestral_Bancos", "Resumen_Trimestral_Bancos"]}
    miss = [f"{s['file']}:{x}" for s in meta["sources"] for x in new_sheets[s["role"]] if x not in s.get("sheets", [])]
    add(1, "Estructura de ambos Excel", "ERROR" if errs else "WARNING" if miss else "PASS",
        f"Contrato del ETL: {len(errs)} errores de hoja/columna. Hojas del sistema 2026 ausentes: {', '.join(miss) or 'ninguna'}. "
        + " · ".join(f"{s['file']}: {len(s.get('sheets', []))} hojas" for s in meta["sources"]))

    # 2. IDs duplicados
    d = [c for c in dq["checks"] if c["category"] in ("IDs duplicados", "Excepciones duplicadas")]
    add(2, "IDs duplicados", worst(*[c["status"] for c in d]), "; ".join(f"{c['check']}: {c['detail']}" for c in d))

    # 3. Excepciones
    cur = [e for e in exc if not e["is_historical"]]
    req = ["ID", "Año", "Trimestre", "Fecha", "Origen", "Producto", "Banco", "Concepto", "Tipo de monto", "Categoría", "Tipo", "Riesgo", "Money Pro", "Splitwise", "Explicación", "Acción", "Evidencia", "Estado"]
    empty = [f"{e['ID']}:{f}" for e in cur for f in req if e.get(f) in (None, "")]
    bad_st = [e["ID"] for e in exc if e["Estado"] not in cfg["preferred_statuses"]]
    leak = [e["ID"] for e in exc if e["is_historical"] and e.get("counts_in_current_open")]
    nums = sorted(int(e["ID"][3:]) for e in exc)
    gaps = [n for n in range(nums[0], nums[-1] + 1) if n not in nums] if nums else []
    st = "ERROR" if leak else "WARNING" if (empty or bad_st or gaps) else "PASS"
    add(3, "Excepciones", st, f"{len(cur)} actuales ({cy}), {len(exc) - len(cur)} históricas. Campos vacíos en actuales: {', '.join(empty[:12]) or 'ninguno'}. "
        f"Estados fuera de Open/Explained/No Action Required/Closed: {', '.join(bad_st) or 'ninguno'}. Históricas en 'abiertas actuales': {', '.join(leak) or 'ninguna'}. "
        f"Huecos de numeración: {gaps or 'ninguno'}. Siguiente ID: {ex['metadata']['next_exception_id']}.")

    # 4. Continuidad
    hist = [e for e in exc if e["is_historical"]]
    nocat = [e["ID"] for e in hist if not e.get("continuity")]
    links = [(m["Finding_ID"], x) for m in ct["matrix"] for x in re.findall(r"EX-\d+", str(m.get("Latest_Linked_Exception") or ""))]
    badlink = [f"{a}→{b}" for a, b in links if b not in {e["ID"] for e in cur}]
    rel = [f"{e['ID']}→{x}" for e in cur for x in re.findall(r"EX-\d+", e.get("Hallazgo relacionado") or "") if x not in {h['ID'] for h in hist}]
    reopened = [e["ID"] for e in hist if e.get("Año") == cy]
    add(4, "Continuidad", "ERROR" if (badlink or rel or reopened) else "WARNING" if nocat else "PASS",
        f"{len(hist)} hallazgos {by} clasificados A–F: {ct['category_counts']}. Sin categoría: {nocat or 'ninguno'}. "
        f"Vínculos matriz→excepción actual: {len(links)} (inválidos: {badlink or 'ninguno'}). 'Hallazgo relacionado' inválidos: {rel or 'ninguno'}. "
        f"Fuente: {ct['metadata']['sources'].get('findings')}.")

    # 5. Q1–Q3 del año actual
    qs = sorted({t["Trimestre"] for t in cc["transactions"] if t["Año"] == cy})
    det = []
    sts = []
    for q in qs:
        ntc = sum(1 for t in cc["transactions"] if t["Año"] == cy and t["Trimestre"] == q)
        nbk = sum(1 for m in bk["transactions"] if m["Año"] == cy and m["Trimestre_n"] == q)
        nst = sum(1 for s in cc["statements"] if s.get("Año") == cy and s.get("Trimestre") == q)
        stm_bad = [s for s in cc["statements"] if s.get("Año") == cy and s.get("Trimestre") == q and s.get("Resultado") not in ("OK", "Utilización > umbral")]
        ctl = [c for c in tl["control_results"] if c.get("Año") == cy and c.get("Trimestre") == f"Q{q}"]
        per = [p for p in tl["periods"] if p["year"] == cy and p["quarter"] == q]
        done = all(p["status"] == "Completado" for p in per)
        sts.append("ERROR" if (not ntc or not nbk or stm_bad) else "WARNING" if (not ctl or not done) else "PASS")
        det.append(f"Q{q}: {ntc} tx TC, {nst} extractos, {nbk} mov. bancarios, {len(ctl)} controles ({sum(1 for c in ctl if c['Resultado'] == 'ERROR')} ERROR), "
                   f"entregables {'completos' if done else 'pendientes'}")
    add(5, f"Q1–Q3 {cy}", worst(*sts) if qs else "ERROR", "; ".join(det) + ". Los controles en ERROR son hallazgos de auditoría (cobertura, depósitos sin soporte), no fallas del sistema.")

    # 6. Métricas Excel vs ETL
    rc = meta["reconciliation"]
    cats = {}
    for c in dq["reconciliation"]:
        cats.setdefault(c["category"], [0, 0])[0 if c["status"] == "PASS" else 1] += 1
    add(6, "Métricas Excel vs ETL", "ERROR" if rc["failed"] else "PASS", f"{rc['passed']} conciliaciones OK, {rc['failed']} fallidas · " + "; ".join(f"{k}: {v[0]} OK / {v[1]} fallidas" for k, v in cats.items()))

    # 7–8. Dashboard y filtros (estático + pruebas del navegador si existen)
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    tabs = re.findall(r'data-page="(\w+)"', html)
    bundle = open(os.path.join(ROOT, "data", "dashboard_data.js"), encoding="utf-8").read()
    missing_ds = [n for n in R.DATASETS if f'"{n}"' not in bundle[:200000] and f'"{n}":' not in bundle]
    br = None
    if args.browser_results and os.path.exists(args.browser_results):
        with open(args.browser_results, encoding="utf-8") as f:
            br = json.load(f)
    s7 = "ERROR" if (len(tabs) != 8 or missing_ds) else "PASS"
    d7 = f"{len(tabs)} pestañas: {', '.join(tabs)}. Datasets en dashboard_data.js: {len(R.DATASETS) - len(missing_ds)}/{len(R.DATASETS)}."
    if br:
        s7 = worst(s7, "ERROR" if br.get("js_errors") else "PASS", "ERROR" if any(not v for v in br.get("tabs_rendered", {}).values()) else "PASS")
        d7 += f" Navegador (Chromium headless): pestañas renderizadas {sum(1 for v in br['tabs_rendered'].values() if v)}/{len(br['tabs_rendered'])}, errores JS: {len(br.get('js_errors', []))}."
    else:
        s7 = worst(s7, "WARNING")
        d7 += " Sin prueba de navegador adjunta."
    add(7, "Dashboard", s7, d7)
    if br:
        f = br.get("filters", {})
        add(8, "Filtros", "ERROR" if f.get("mismatches") else "PASS",
            f"{f.get('combinations', 0)} combinaciones Año×Trimestre comparadas (KPIs del dashboard vs quarter_summary del ETL): {len(f.get('mismatches', []))} diferencias. "
            f"Filtros disponibles: {', '.join(f.get('labels', []))}. Opciones de año desde datos: {f.get('years')}.")
    else:
        add(8, "Filtros", "WARNING", "Sin prueba de navegador adjunta (ejecute la prueba de filtros).")

    # 9. Español
    english = [r"\bOverview\b", r"\bCredit Cards\b", r"Bank &amp; Cash", r"\bExceptions\b", r"\bAudit (Continuity|Timeline)\b", r"Reset filters", r">All<", r"No records", r"\bSearch\b<",
               r"Data refreshed", r"\bNext ›", r"‹ Prev", r"not applicable", r"\brecords?\b\"", r"Data quality"]
    hits = []
    for p in [os.path.join(ROOT, "index.html")] + glob.glob(os.path.join(ROOT, "js", "*.js")):
        txt = open(p, encoding="utf-8").read()
        for pat in english:
            for m in re.finditer(pat, txt):
                hits.append(f"{os.path.basename(p)}: {m.group(0)}")
    add(9, "Español", "WARNING" if hits else "PASS", ("Cadenas en inglés visibles: " + "; ".join(hits[:10])) if hits else
        "Sin cadenas de interfaz en inglés en index.html y js/*.js (los nombres de columnas internas se conservan; los códigos de riesgo HIGH/MEDIUM/LOW se muestran como ALTO/MEDIO/BAJO).")

    # 10. Fiducuenta TC
    tcp = [c for c in pu["catalog"] if (c.get("Tipo de producto") or "").lower() == "fiducuenta tc"]
    rows_tc = [f for f in pu["fiducuentas"] if f.get("is_tc")]
    pchk = [c for c in dq["reconciliation"] if c["check"].startswith("Productos · intereses")]
    cap_leak = [f"{m['Producto']} {m['Mes']}" for m in pu["monthly"] if "fiducuenta" in str(m.get("Tipo de producto")).lower()
                and abs((m.get("Beneficios totales") or 0) - (m.get("Intereses ganados") or 0)) > 0.01]
    confirmed = any("CONFIRMADO POR EVIDENCIA" in str(c.get("Comentario") or "").upper() for c in tcp)
    s10 = "ERROR" if (len(tcp) != 1 or cap_leak or any(c["status"] != "PASS" for c in pchk)) else ("PASS" if confirmed else "WARNING")
    add(10, "Fiducuenta TC", s10, f"Productos tipificados 'Fiducuenta TC': {[c['ID_Producto'] for c in tcp]} ({len(rows_tc)} meses). Intereses Productos_Financieros = Fiducuenta_TC: "
        f"{sum(1 for c in pchk if c['status'] == 'PASS')}/{len(pchk)}. Capital tratado como beneficio: {cap_leak or 'ninguno'}. "
        + ("Identificación CONFIRMADA POR EVIDENCIA (catálogo)." if confirmed else "WARNING: la identificación de la cuenta sigue siendo un supuesto editable."))

    # 11. Costos vs beneficios
    bad = []
    for m in pu["monthly"]:
        c = sum((m.get(k) or 0) for k in ("Cuotas de manejo", "Intereses pagados", "Seguros", "Otros costos"))
        b = sum((m.get(k) or 0) for k in ("Cashback", "Descuentos", "Puntos monetizados", "Otros beneficios", "Intereses ganados"))
        if abs(c - (m.get("Costo total") or 0)) > 0.02 or abs(b - (m.get("Beneficios totales") or 0)) > 0.02 or abs(b - c - (m.get("Valor neto") or 0)) > 0.02:
            bad.append(f"{m['ID_Producto']} {m['Mes']}")
    sinev = sum(1 for m in pu["monthly"] if any(m.get(k) is None for k in ("Cuotas de manejo", "Intereses pagados", "Seguros")))
    pts = [m for m in pu["monthly"] if (m.get("Puntos ganados") or 0) and abs((m.get("Puntos ganados") or 0) * pu["metadata"]["points_cop"] - (m.get("Puntos monetizados") or 0)) > 0.6]
    add(11, "Costos vs beneficios", "ERROR" if bad or pts else "WARNING" if sinev else "PASS",
        f"{len(pu['monthly'])} filas producto-mes: costo total, beneficios y valor neto cuadran ({len(bad)} diferencias). Puntos × {pu['metadata']['points_cop']} COP/pt: {len(pts)} diferencias. "
        f"{sinev} filas con costos 'Sin evidencia' — no se estimaron: " + ", ".join(f"{k} ({v})" for k, v in sorted(__import__('collections').Counter(m['Producto'] for m in pu['monthly'] if any(m.get(k) is None for k in ('Cuotas de manejo', 'Intereses pagados', 'Seguros'))).items()))
        + ". Productos sin uso y sin extracto: el costo de mantenerlos no es verificable sin extracto o certificado del emisor.")

    # 12. 2025 vs 2026 (baseline intacta e igual)
    arch = (cfg.get("archive") or {}).get(f"{by}_baseline", {})
    det, s12 = [], []
    for role, info in arch.items():
        p = R.resolve(info["path"])
        ok = os.path.exists(p) and sha(p) == info["sha256"]
        s12.append("PASS" if ok else "ERROR")
        det.append(f"{role}: archivo baseline {'íntegro' if ok else 'NO íntegro/ausente'}")
    if arch and all(x == "PASS" for x in s12):
        import openpyxl
        log = R.Log()
        tcb = R.extract_tc(openpyxl.load_workbook(R.resolve(arch["tc"]["path"]), data_only=True), log, "baseline")
        bkb = R.extract_bank(openpyxl.load_workbook(R.resolve(arch["bank"]["path"]), data_only=True), log, "baseline")
        aggb = R.tc_period_aggregates(tcb)
        now = {r["period"]: r for r in cc["quarter_summary"]}
        diffs = [f"{p}.{k}" for p, m in aggb.items() if p.endswith(str(by)) for k, v in m.items() if abs(v - (now.get(p, {}).get(k) or 0)) > 0.01]
        mvb = bkb["transactions"]
        mvn = [m for m in bk["transactions"] if m["Año"] == by]
        bdiff = [k for k in ("gross_in", "gross_out", "external_in", "external_out", "internal_out", "card_payments") if abs(R.agg(mvb, R.BANK_METRICS[k]) - R.agg(mvn, R.BANK_METRICS[k])) > 0.01]
        idb = {m["ID"] for m in mvb}; idn = {m["ID"] for m in mvn}
        exb = {e["ID"] for e in R.build_exceptions(tcb, bkb, cfg, R.Log(), "b", "b")[0]}
        exn = {e["ID"] for e in exc if e.get("Año") == by}
        s12.append("ERROR" if (diffs or bdiff or idb != idn or exb != exn) else "PASS")
        det.append(f"Métricas {by} libro nuevo vs baseline: TC {len(diffs)} diferencias en {len([p for p in aggb if p.endswith(str(by))])} trimestres; bancos {len(bdiff)} diferencias; "
                   f"IDs de movimientos {by} idénticos: {idb == idn} ({len(idn)}); IDs de excepciones {by} idénticos: {exb == exn} ({len(exn)})")
    yoy = [p for p in cc["historico_trimestral"]["periods"]]
    det.append(f"Comparativos disponibles (Historico_Trimestral): {', '.join(yoy)}")
    add(12, f"{by} vs {cy}", worst(*s12) if s12 else "WARNING", "; ".join(det))

    # 13. Source files
    s13, d13 = [], []
    for s in meta["sources"]:
        p = R.resolve(s["path"])
        ok = os.path.exists(p) and sha(p) == s["sha256"]
        s13.append("PASS" if ok else "ERROR")
        d13.append(f"{s['path']} existe y su SHA-256 coincide con el refresh: {ok}")
    hchk = [c for c in dq["checks"] if c["category"] in ("Hashes", "Frescura de fuentes")]
    s13 += [c["status"] for c in hchk]
    add(13, "Source files", worst(*s13), "; ".join(d13) + " · " + "; ".join(f"{c['check']}: {c['status']}" for c in hchk))

    # 14. Configuración
    need = ["sources", "baseline_year", "current_audit_year", "deliverables", "deliverable_search_dirs", "continuity", "status_normalization", "preferred_statuses", "materiality_cop", "archive"]
    raw = json.load(open(os.path.join(ROOT, "scripts", "config.json"), encoding="utf-8"))
    miss = [k for k in need if k not in raw]
    years_ok = cy in meta["years"] and by in meta["years"]
    src_ok = all(os.path.exists(R.resolve(p)) for p in (raw["sources"]["tc"], raw["sources"]["bank"]))
    add(14, "Configuración", "ERROR" if (miss or not src_ok) else "WARNING" if not years_ok else "PASS",
        f"Claves faltantes: {miss or 'ninguna'}. Fuentes existen: {src_ok}. Año base {raw.get('baseline_year')} y actual {raw.get('current_audit_year')} presentes en los datos: {years_ok}. "
        f"Patrones de entregables: {raw['deliverables']['tc']['quarterly']}, {raw['deliverables']['bank']['quarterly']}.")

    # 15. Refresh repetible sin modificar código
    outs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "refresh_dashboard.py"), "--check"], capture_output=True, text=True)
        outs.append((r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]))
    same = outs[0] == outs[1] and outs[0][0] == 0
    yr_lit = []
    for p in glob.glob(os.path.join(ROOT, "js", "*.js")) + [os.path.join(ROOT, "scripts", "refresh_dashboard.py")]:
        if "vendor" in p:
            continue
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            code = line.split("//")[0] if p.endswith(".js") else line.split("#")[0]
            if re.search(r"(?<![\w.-])20[2-3]\d(?![\w-])", code):
                yr_lit.append(f"{os.path.basename(p)}:{i}")
    add(15, "Refresh repetible sin modificar código", "ERROR" if not same else "WARNING" if yr_lit else "PASS",
        f"Dos ejecuciones consecutivas del ETL (--check): {outs[0][1]} | idénticas: {same}. Literales de año en la lógica (JS/ETL): {yr_lit or 'ninguno'}. "
        "Nuevos trimestres/años se agregan como filas en los libros y una columna Qn-AAAA en las hojas Historico_*; el dashboard toma años, trimestres, meses, productos y cuentas de los datos.")

    ap_results = closing_checks(cy, cc, bk, exc, pu, dq, meta, {r["n"]: r for r in RESULTS})
    summ = {k: sum(1 for r in RESULTS if r["status"] == k) for k in ("PASS", "WARNING", "ERROR")}
    out_dir = os.path.join(ROOT, "validation")
    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    with open(os.path.join(out_dir, f"Validacion_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({"fecha": dt.datetime.now().isoformat(timespec="seconds"), "resumen": summ, "controles": RESULTS, "refresh": meta["last_refresh"]}, f, ensure_ascii=False, indent=1)
    md = [f"# Validación final del sistema — {stamp}", "", f"Refresh de datos: {meta['last_refresh']} · Resultado: **{summ['PASS']} PASS · {summ['WARNING']} WARNING · {summ['ERROR']} ERROR**", "",
          "| # | Control | Resultado | Evidencia |", "|---|---|---|---|"]
    for r in RESULTS:
        md.append(f"| {r['n']} | {r['control']} | **{r['status']}** | {r['detail'].replace('|', '/')} |")
    with open(os.path.join(out_dir, f"Validacion_{stamp}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    sap = {k: sum(1 for r in ap_results if r["status"] == k) for k in ("PASS", "WARNING", "ERROR")}
    with open(os.path.join(out_dir, f"Validacion_Cierre_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump({"fecha": dt.datetime.now().isoformat(timespec="seconds"), "resumen": sap, "controles": ap_results, "refresh": meta["last_refresh"]}, f, ensure_ascii=False, indent=1)
    md = [f"# Validación de cierre (A–P) — {stamp}", "", f"Refresh de datos: {meta['last_refresh']} · Resultado: **{sap['PASS']} PASS · {sap['WARNING']} WARNING · {sap['ERROR']} ERROR**", "",
          "| # | Validación | Resultado | Evidencia |", "|---|---|---|---|"]
    md += [f"| {r['n']} | {r['control']} | **{r['status']}** | {r['detail'].replace('|', '/')} |" for r in ap_results]
    with open(os.path.join(out_dir, f"Validacion_Cierre_{stamp}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    for r in ap_results:
        print(f" {r['n']}. {r['status']:7s} {r['control']}")
    print("cierre A–P:", sap)
    for r in RESULTS:
        print(f"{r['n']:>2}. {r['status']:7s} {r['control']}")
    print(summ)
    return 1 if summ["ERROR"] or sap["ERROR"] else 0


def closing_checks(cy, cc, bk, exc, pu, dq, meta, base):
    """Validación de cierre A–P (segunda pasada). Solo lee los datasets del ETL; no recalcula reglas de auditoría."""
    out = []
    A = lambda n, name, st, det: out.append({"n": n, "control": name, "status": st, "detail": det})
    chk = {c["check"]: c for c in dq["checks"]}
    rec = dq["reconciliation"]
    st = [x for x in cc["statements"] if x.get("Año") == cy]
    cov = [c for c in pu.get("coverage", []) if c.get("Año") == cy]
    miss = [c for c in cov if str(c.get("Estado de cobertura")).startswith("Falta")]
    bad = [f"{x['Producto']} {x['Mes']}: {x['Resultado']}" for x in st if x.get("Resultado") not in ("OK", "Utilización > umbral")]
    cards = sorted({f"*{x['Tarjeta']}" for x in st})
    A("A", "Extractos", "ERROR" if miss or bad else "PASS", f"{len(st)} cortes {cy} ({', '.join(cards)}); aritmética y continuidad: {len(bad)} diferencias {bad[:5] or ''}. "
      f"Cobertura: {len(cov)} producto-mes clasificados, {len(miss)} 'Falta extracto — requerido'.")
    pays = [x for x in bk["card_payments"] if x.get("Año") == cy]
    nok = [x["ID *9910"] for x in pays if not str(x.get("Estado")).startswith("Exact Match")]
    A("B", "Pagos", "ERROR" if nok else "PASS", f"{len(pays)} pagos *9910 → tarjetas en {cy}: {len(pays) - len(nok)} Exact Match contra el abono del extracto; sin conciliar: {nok or 'ninguno'}.")
    bc = [b for b in bk["balance_continuity"] if b.get("Año") == cy]
    bcb = [f"{b['Cuenta']} {b['Período']}" for b in bc if b.get("Estado") not in ("OK", None)]
    A("C", "Saldos", "ERROR" if bcb or bad else "PASS", f"Continuidad de saldos bancarios/fiducuentas {cy}: {len(bc)} períodos, {len(bcb)} diferencias. Saldos TC: saldo anterior = nuevo saldo del corte previo en {len(st) - len(bad)}/{len(st)} cortes.")
    ri = [c for c in rec if "Intereses" in c["check"] and str(cy) in c["check"]]
    usd = [f"*{x['Tarjeta']} {x['Mes']}: USD {x.get('Intereses corrientes')}" for x in st if x.get("Moneda") == "USD" and (x.get("Intereses corrientes") or 0)]
    A("D", "Intereses", "ERROR" if any(c["status"] != "PASS" for c in ri) else "PASS", f"Intereses TC en COP conciliados Excel vs ETL: {sum(1 for c in ri if c['status'] == 'PASS')}/{len(ri)}. "
      f"Intereses en dólares fuera del total COP y documentados aparte (EX-50): {usd or 'ninguno'}.")
    rb = [c for c in rec if "Beneficios" in c["check"] and str(cy) in c["check"]]
    teo = sum(m.get("Beneficio potencial (teórico)") or 0 for m in pu["monthly"] if m.get("Año") == cy)
    A("E", "Beneficios", "ERROR" if any(c["status"] != "PASS" for c in rb) else ("PASS" if base[11]["status"] != "ERROR" else "ERROR"),
      f"Beneficios verificados conciliados: {sum(1 for c in rb if c['status'] == 'PASS')}/{len(rb)}. Beneficio teórico {cy} (no es ingreso, solo referencia): {teo:,.0f}. Puntos valorados a {pu['metadata'].get('points_cop')} COP/pt.")
    rf = [c for c in rec if re.search(r"Cuotas|Seguros|Costo neto", c["check"]) and str(cy) in c["check"]]
    A("F", "Costos", "ERROR" if any(c["status"] != "PASS" for c in rf) else "PASS", f"Cuotas, seguros y costo neto {cy} conciliados: {sum(1 for c in rf if c['status'] == 'PASS')}/{len(rf)}. Costo de oportunidad: no calculado (sin metodología aprobada).")
    cl = [e for e in exc if e.get("closed_this_update")]
    nev = [e["ID"] for e in cl if not e.get("Evidencia nueva") or not e.get("Conclusión de auditoría")]
    A("G", "Excepciones cerradas", "ERROR" if nev else "PASS", f"{len(cl)} cerradas/explicadas en esta actualización ({', '.join(e['ID'] + ' ' + str(e.get('Estado anterior')) + '→' + e['Estado'] for e in cl)}); sin evidencia nueva o conclusión: {nev or 'ninguna'}.")
    new = [e for e in exc if e.get("Año") == cy and not e.get("Estado anterior")]
    nnew = [e["ID"] for e in new if not e.get("Evidencia nueva") or not e.get("Conclusión de auditoría") or not e.get("Riesgo")]
    A("H", "Nuevas excepciones", "ERROR" if nnew else "PASS", f"Nuevas: {', '.join(e['ID'] + ' (' + e['Estado'] + ')' for e in new) or 'ninguna'}; sin evidencia/conclusión/riesgo: {nnew or 'ninguna'}. "
      f"Siguiente ID libre: {chk.get('IDs únicos en el registro central', {}).get('detail', '')}.")
    ina = [c for c in cov if str(c.get("Estado de cobertura")).startswith("Sin actividad")]
    openids = {e["ID"] for e in exc if e.get("is_open")}
    ina_bad = [f"{c['Producto']} {c['Mes']}" for c in ina if c.get("Requiere extracto") == "Sí" or set(re.findall(r"EX-\d+", str(c.get("Excepción") or ""))) & openids]
    A("I", "Productos inactivos", "ERROR" if ina_bad else "PASS", f"{len(ina)} producto-mes sin actividad clasificados sin exigir extracto ni excepción abierta (los vínculos a excepciones cerradas, p. ej. EX-36, son trazabilidad) ({len({c['Producto'] for c in ina})} productos); inconsistentes: {ina_bad or 'ninguno'}.")
    cm = [c for c in cov if re.search(r"migrado|cerrado", str(c.get("Estado de cobertura")), re.I)]
    al = chk.get("Tarjetas cerradas o migradas sin actividad posterior", {})
    A("J", "Productos cerrados/migrados", "ERROR" if al.get("status") == "ERROR" else "PASS", f"{len(cm)} producto-mes cerrados/migrados ({', '.join(sorted({c['Producto'] for c in cm}))}); actividad posterior al cierre: {al.get('status')}. Ciclo de vida: {al.get('detail')}.")
    A("K", "Fiducuenta TC", base[10]["status"], base[10]["detail"])
    A("L", "Utilidad de productos", base[11]["status"], base[11]["detail"])
    A("M", "Dashboard", base[7]["status"], base[7]["detail"] + " " + base[9]["detail"][:120])
    A("N", "Filtros", base[8]["status"], base[8]["detail"])
    A("O", "ETL", worst(base[6]["status"], base[15]["status"]), base[6]["detail"] + " · " + base[15]["detail"])
    A("P", "2025 intacto", base[12]["status"], base[12]["detail"])
    return out


if __name__ == "__main__":
    sys.exit(main())

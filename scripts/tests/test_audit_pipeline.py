#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas controladas de audit_pipeline.py con fixtures temporales (nunca toca datos reales).

    python scripts/tests/test_audit_pipeline.py

Escenarios (skill financial-account-audit, sección de pruebas):
  A todo disponible → GO                        B falta extracto de tarjeta activa → NO-GO
  C falta Money Pro → NO-GO (P3)                D falta Splitwise → NO-GO; con --partial-scope bank → GO-PARCIAL sin Notion
  E falta Datacrédito para una migración → GO con conclusión PENDIENTE del producto
  F producto sin actividad → sin falso positivo  G hallazgo histórico resuelto no se reabre
  H refresh del dashboard falla → BLOQUEADO, Notion rechazado
  J auditoría anual → exige los 4 cierres trimestrales y Datacrédito posterior al cierre
  + orden de fases: no se puede saltar una fase.
(I — Review ya existe en Notion — se prueba en vivo, en solo lectura, desde la skill.)
Requiere: openpyxl, reportlab, y pdftotext o pypdf.
"""
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
import audit_pipeline as AP  # noqa: E402
import openpyxl  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

# Registro sanitizado y versionado: las pruebas no dependen de scripts/audit_sources.json (privado).
REG = os.path.join(os.path.dirname(SCRIPTS), "examples", "audit_sources.example.json")
MON = AP.MON
RESULTS = []


def xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w", **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as f:
        f.write(data)


def pdf(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = canvas.Canvas(path)
    y = 800
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 16
    c.save()


def build_fixture(base, year=2026, months=range(1, 13), rappi_gap=(3, 4, 5, 6, 7)):
    ev = os.path.join(base, "Informacion Bancaria")
    dash = os.path.join(ev, "Financial Audit Dashboard")
    stmt = xlsx_bytes([["Extracto de prueba"], ["Saldo anterior", 0], ["Nuevo saldo", 0]] + [["fila", i] for i in range(30)])
    for m in months:
        k = f"{year}{m:02d}"
        # Bancolombia TC
        zp = os.path.join(ev, "Tarjetas de Credito", "Bancolombia", str(year), f"Documento_{k}_1.zip")
        os.makedirs(os.path.dirname(zp), exist_ok=True)
        with zipfile.ZipFile(zp, "w") as z:
            for card in ("6907", "7744", "7935", "8457"):
                z.writestr(f"{card}_{MON[m - 1]}{year}.xlsx", stmt)
        # Occidente (archivo con fecha del mes siguiente)
        ny, nm = (year, m + 1) if m < 12 else (year + 1, 1)
        pdf(os.path.join(ev, "Tarjetas de Credito", "Banco de Occidente", str(ny), f"ExtractosUnificados{ny}{nm:02d}03.pdf"),
            ["TARJETA No. 400000-*-*****7547", f"FECHA DE CORTE : 28/{m:02d}/{year}"])
        # Itaú hasta jul, Banco de Bogotá desde ago
        if m <= 7:
            pdf(os.path.join(ev, "Tarjetas de Credito", "Banco Itau", str(year), f"Itau_extracto_{m}.pdf"),
                [f"Periodo de facturacion 01/{m:02d}/{year} al 28/{m:02d}/{year}", "Tarjeta No. ************5933"])
        else:
            pdf(os.path.join(ev, "Tarjetas de Credito", "Banco de Bogota", f"{m:02d}_{year}_000.pdf"),
                [f"Del 01/{MON[m - 1]}/{year} al 28/{MON[m - 1]}/{year}", "No. **** **** **** 6931"])
        # RappiCard: solo con actividad
        if m not in rappi_gap:
            mon = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"][m - 1]
            prev0 = m - 1 in rappi_gap or m == 1
            pdf(os.path.join(ev, "Tarjetas de Credito", "RappiPay", f"File_{m}.pdf"),
                [f"Desde 01 {mon} {year}   Hasta 28 {mon} {year}", "Detalle pago total",
                 f"Saldo periodo anterior $ {'0,00' if prev0 else '1.000,00'}", f"Pago total $ {'0,00' if m + 1 in rappi_gap else '1.000,00'}"])
        # Fiducuentas
        fz = os.path.join(ev, "Cuentas Bancarias", "Fiducuentas", str(year), f"Documento_{k}_9.zip")
        if m >= 3:
            os.makedirs(os.path.dirname(fz), exist_ok=True)
            with zipfile.ZipFile(fz, "w") as z:
                for acct, opened in (("9990000006191", 3), ("9990000000934", 3), ("9990000000452", 7)):
                    if m >= opened:
                        z.writestr(f"{acct}_{MON[m - 1]}{year}.xlsx", stmt)
        else:
            write(os.path.join(ev, "Cuentas Bancarias", "Fiducuentas", str(year), f"Extracto_{k}_Fiducuenta_6191.xlsx"), stmt)
        if m % 3 == 0:
            write(os.path.join(ev, "Cuentas Bancarias", "Cuenta de Ahorros", f"Extracto_{k}_Cuentas_de ahorro_9910.xlsx"), stmt)
    last_m = max(months)
    end = dt.date(year, last_m, 28)
    # Money Pro y Splitwise
    mp = ["Date;Time;Amount;Currency;Account;Account (to);Amount received;Currency;Category;Description;Transaction Type;Agent"]
    sw = ["Note: does not include group expenses,,,,,,", ",,,,,,", "Date,Description,Category,Cost,Currency,Persona A,Persona B"]
    d = dt.date(year, min(months), 1)
    while d <= end + dt.timedelta(days=3):
        mp.append(f"{d.month}/{d.day}/{d.year};1:00 PM;10,000;$;Wallet;;;;Food;x;Expense;y")
        if d.day in (5, 20):
            sw.append(f"{d.month}/{d.day}/{d.year},Cena,Dining out,50000,COP,25000,-25000")
        d += dt.timedelta(days=1)
    write(os.path.join(ev, f"Money Pro Transactions - {year} test.csv"), "\n".join(mp) + "\n")
    exp = end + dt.timedelta(days=5)
    write(os.path.join(ev, "SplitWise", f"familia_{exp.isoformat()}_export.csv"), "\n".join(sw) + "\n")
    pdf(os.path.join(ev, "DataCredito", f"Reporte DataCredito {exp.month}-{exp.day}-{str(exp.year)[2:]}.pdf"), ["Reporte"])
    # Puntos Colombia (pocas filas: no truncado) y control Primax verificado
    write(os.path.join(ev, "Puntos Colombia", f"Puntos Colombia {year}.xlsx"),
          xlsx_bytes([["Titular"], ["Fecha", "x"]] + [[f"{year}-{m:02d}-15", "Exito", "", "", "Sale", "1", "30"] for m in months] + [[f"{year - 1}-12-15", "Exito"]]))
    wbp = openpyxl.Workbook()
    ws = wbp.active
    ws.title = "Control_Equivalencias"
    ws.append(["Programa", "Comercio / aliado", "COP por punto", "Vigente desde", "Vigente hasta", "Método", "Fuente", "Fecha verif.", "Estado"])
    ws.append(["Puntos Colombia", "Primax", 6, dt.datetime(2024, 1, 1), None, "puntos × tasa", "factura", dt.datetime(2026, 10, 1), "Verificado"])
    p = os.path.join(ev, "Puntos Colombia", "Auditoria Primax 2024-2026", "Auditoria_PuntosColombia_Primax_2024-2026.xlsx")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    wbp.save(p)
    write(os.path.join(ev, "Tarjetas de Credito", "Beneficios", "Beneficios.docx"), b"PK")
    write(os.path.join(ev, "Cuentas Bancarias", "Reportes Costos", f"Reporte_{year}12_AnualCostosBancolombia_4120.xlsx"), stmt)
    # Dashboard: libros mínimos + scripts requeridos
    wbt = openpyxl.Workbook()
    ws = wbt.active
    ws.title = "Extractos_Input"
    ws.append(["Extractos"]); ws.append([]); ws.append([])
    ws.append(["Año", "Archivo"])
    os.makedirs(os.path.join(dash, "source"), exist_ok=True)
    wbt.save(os.path.join(dash, "source", "Sistema_Auditoria_TC.xlsx"))
    openpyxl.Workbook().save(os.path.join(dash, "source", "Auditoria_Bancos.xlsx"))
    for s in ("refresh_dashboard.py", "build_quarterly_reports.py", "validate_system.py", "config.json"):
        write(os.path.join(dash, "scripts", s), "# fixture\n")
    return ev, dash


def run(dash, ev, period, *extra):
    return AP.main(["preflight", "--period", period, "--dashboard-root", dash, "--evidence-root", ev, "--registry", REG] + list(extra))


def pre(dash, key):
    with open(os.path.join(dash, "work", key, f"preflight_{key}.json"), encoding="utf-8") as f:
        return json.load(f)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def fresh(year_months=range(1, 13), **kw):
    base = tempfile.mkdtemp(prefix="faa_test_")
    ev, dash = build_fixture(base, months=year_months, **kw)
    return base, ev, dash


def main():
    os.environ.pop("AUDIT_PDF_PASSWORD", None)
    # A
    base, ev, dash = fresh(range(1, 10))
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    check("A · todo disponible → GO", rc == 0 and r["decision"] == "GO", f"decision={r['decision']} bloqueos={[i['text'] for i in r['issues'] if i['severity'] == 'BLOCKER']}")
    check("F · RappiCard sin actividad (jul) → D, sin falso positivo", any(c["product"] == "TC-RAPPI" and c["month"] == "2026-07" and c["status"] == "D" for c in r["coverage"]))
    check("orden · P9 antes de P7 rechazada", AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", "P9"]) == 3)
    check("orden · P7 autorizada tras GO", AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", "P7"]) == 0)
    # H: refresh falla → bloqueado y Notion rechazado
    for ph in ["P7", "P8", "P9", "P10", "P11", "P12", "P13", "P14"]:
        if ph != "P7":
            AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", ph])
        AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--done", ph, "--result", "PASS"])
    os.makedirs(os.path.join(dash, "data"), exist_ok=True)
    write(os.path.join(dash, "data", "metadata.json"), json.dumps({"status": "FAILED", "message": "falta hoja Extractos_Input", "last_refresh": "2099-01-01 00:00:00"}))
    for n in ("data_quality", "credit_cards", "bank_cash"):
        write(os.path.join(dash, "data", f"{n}.json"), "{}")
    rc_h = AP.main(["verify-dashboard", "--period", "2026Q3", "--dashboard-root", dash])
    rc_n = AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", "P17"])
    check("H · refresh fallido → P15 BLOQUEADO y Notion rechazado", rc_h == 2 and rc_n == 3)
    shutil.rmtree(base)
    # B: falta el extracto de ago de la Amex (tarjeta activa)
    base, ev, dash = fresh(range(1, 10))
    zp = os.path.join(ev, "Tarjetas de Credito", "Bancolombia", "2026", "Documento_202608_1.zip")
    with zipfile.ZipFile(zp, "w") as z:
        for card in ("6907", "7744", "8457"):
            z.writestr(f"{card}_AGO2026.xlsx", xlsx_bytes([["x", i] for i in range(40)]))
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    blk = [i["text"] for i in r["issues"] if i["severity"] == "BLOCKER"]
    st = json.load(open(os.path.join(dash, "work", "2026Q3", "audit_state.json"), encoding="utf-8"))
    check("B · falta extracto de tarjeta activa → NO-GO", rc == 2 and r["decision"] == "NO-GO" and any("TC-7935 2026-08" in t for t in blk), "; ".join(blk))
    check("B · tras NO-GO no se puede iniciar P7", AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", "P7"]) == 3 and st["overall"] == "BLOCKED")
    shutil.rmtree(base)
    # B2: PDF protegido sin contraseña → ilegible (clase B) → NO-GO
    base, ev, dash = fresh(range(1, 10))
    tgt = os.path.join(ev, "Tarjetas de Credito", "Banco de Occidente", "2026", "ExtractosUnificados20260803.pdf")
    c = canvas.Canvas(tgt, encrypt="clave-de-prueba")
    c.drawString(40, 800, "TARJETA No. 400000-*-*****7547")
    c.drawString(40, 780, "FECHA DE CORTE : 28/07/2026")
    c.save()
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    row = [c for c in r["coverage"] if c["product"] == "TC-7547" and c["month"] == "2026-07"]
    check("B2 · PDF protegido sin contraseña → ilegible (B) → NO-GO", rc == 2 and row and row[0]["status"] == "B", str(row))
    os.environ["AUDIT_PDF_PASSWORD"] = "clave-de-prueba"
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    row = [c for c in r["coverage"] if c["product"] == "TC-7547" and c["month"] == "2026-07"]
    os.environ.pop("AUDIT_PDF_PASSWORD", None)
    check("B2 · con la contraseña en la variable de entorno → legible (A)", row and row[0]["status"] == "A", str(row))
    shutil.rmtree(base)
    # C: falta Money Pro
    base, ev, dash = fresh(range(1, 10))
    for f in os.listdir(ev):
        if f.startswith("Money Pro"):
            os.remove(os.path.join(ev, f))
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    check("C · falta Money Pro → NO-GO en P3", rc == 2 and any(i["phase"] == "P3" and i["severity"] == "BLOCKER" for i in r["issues"]))
    shutil.rmtree(base)
    # D: falta Splitwise
    base, ev, dash = fresh(range(1, 10))
    shutil.rmtree(os.path.join(ev, "SplitWise"))
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    rc2 = run(dash, ev, "2026Q3", "--partial-scope", "bank")
    r2 = pre(dash, "2026Q3")
    for ph in AP.PHASE_IDS[7:15]:
        AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", ph])
        AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--done", ph, "--result", "PASS"])
    st = json.load(open(os.path.join(dash, "work", "2026Q3", "audit_state.json"), encoding="utf-8"))
    st["phases"]["P15"] = {"status": "DONE", "result": "PASS"}
    st["phases"]["P16"] = {"status": "DONE", "result": "PASS"}
    json.dump(st, open(os.path.join(dash, "work", "2026Q3", "audit_state.json"), "w", encoding="utf-8"))
    rc_n = AP.main(["phase", "--period", "2026Q3", "--dashboard-root", dash, "--start", "P17"])
    check("D · falta Splitwise → NO-GO (P4)", rc == 2 and r["decision"] == "NO-GO" and any(i["phase"] == "P4" for i in r["issues"]))
    check("D · --partial-scope bank → GO-PARCIAL y Notion rechazado", rc2 == 0 and r2["decision"] == "GO-PARCIAL" and rc_n == 3)
    shutil.rmtree(base)
    # E: falta Datacrédito para la migración de la *5933 (ago-2026)
    base, ev, dash = fresh(range(1, 10))
    shutil.rmtree(os.path.join(ev, "DataCredito"))
    rc = run(dash, ev, "2026Q3")
    r = pre(dash, "2026Q3")
    dc = [i for i in r["issues"] if "Datacrédito" in i["text"]]
    check("E · sin Datacrédito → GO con conclusión de la migración TC-5933 → TC-6931 PENDIENTE (WARNING acotado)",
          rc == 0 and r["decision"] == "GO" and dc and all(i["severity"] == "WARNING" and i["scope"] in ("TC-5933", "TC-6931") for i in dc), "; ".join(i["text"] for i in dc))
    shutil.rmtree(base)
    # G: hallazgo histórico resuelto no se reabre
    base = tempfile.mkdtemp(prefix="faa_test_")
    dash = os.path.join(base, "dash")
    os.makedirs(os.path.join(dash, "data"))
    ex = {"exceptions": [{"ID": "EX-01", "is_historical": True, "is_open": False}, {"ID": "EX-34", "is_historical": False, "is_open": False}]}
    cont = {"matrix": [{"Finding_ID": "EX-01", "category_code": "A"}]}
    write(os.path.join(dash, "data", "exceptions.json"), json.dumps(ex))
    write(os.path.join(dash, "data", "continuity.json"), json.dumps(cont))
    ok1 = AP.main(["check-exceptions", "--dashboard-root", dash]) == 0
    ex["exceptions"][0]["is_open"] = True
    write(os.path.join(dash, "data", "exceptions.json"), json.dumps(ex))
    ok2 = AP.main(["check-exceptions", "--dashboard-root", dash]) == 2
    check("G · histórico resuelto (cat. A) no se reabre: detectado si aparece abierto", ok1 and ok2)
    shutil.rmtree(base)
    # J: anual
    base, ev, dash = fresh(range(1, 13))
    for q in (1, 2, 3):
        for mod in ("TC", "Bancos"):
            write(os.path.join(dash, "deliverables", "2026", f"Auditoria_Trimestral_{mod}_Q{q}_2026.pdf"), b"%PDF")
    rc = run(dash, ev, "2026")
    r = pre(dash, "2026")
    q4_blocked = any("Q4 2026 sin cierre" in i["text"] for i in r["issues"])
    os.makedirs(os.path.join(dash, "work", "2026Q4"), exist_ok=True)
    write(os.path.join(dash, "work", "2026Q4", "audit_state.json"), json.dumps({"overall": "COMPLETED", "phases": {}}))
    rc2 = run(dash, ev, "2026")
    r2 = pre(dash, "2026")
    dc_ok = any(c["source"] == "datacredito" and c["requirement"].startswith("mandatory") for c in r2["conditional"])
    check("J · anual sin cierre Q4 → NO-GO", rc == 2 and q4_blocked)
    check("J · anual con Q1–Q3 (legado) + Q4 COMPLETED → GO; Datacrédito obligatorio; 12 meses evaluados",
          rc2 == 0 and r2["decision"] == "GO" and dc_ok and len({c["month"] for c in r2["coverage"]}) == 12,
          f"decision={r2['decision']} bloqueos={[i['text'] for i in r2['issues'] if i['severity'] == 'BLOCKER']}")
    shutil.rmtree(base)

    w = max(len(n) for n, _, _ in RESULTS)
    print("\nPRUEBAS financial-account-audit")
    for n, ok, d in RESULTS:
        print(f"  {'PASS' if ok else 'FAIL'}  {n.ljust(w)}" + (f"\n        {d}" if (d and not ok) else ""))
    nf = sum(1 for _, ok, _ in RESULTS if not ok)
    print(f"{len(RESULTS) - nf}/{len(RESULTS)} PASS")
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())

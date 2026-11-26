#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_quarterly_reports.py — genera los informes trimestrales en PDF a partir de data/*.json.

    python scripts/build_quarterly_reports.py --year 2026 --quarter 3          # un trimestre
    python scripts/build_quarterly_reports.py --year 2026 --quarter 1 2 3      # varios

Reglas: el PDF solo presenta lo que el ETL leyó de los libros (ya conciliado contra Historico_Trimestral /
Historico_Trimestral_Bancos). No calcula clasificaciones ni estima valores faltantes: lo que no tiene
evidencia aparece como "Sin evidencia". Ejecute primero refresh_dashboard.py.

Salida: deliverables/<año>/Auditoria_Trimestral_TC_Q<q>_<año>.pdf y Auditoria_Trimestral_Bancos_Q<q>_<año>.pdf
(nombres según config.json › deliverables; la carpeta está dentro de deliverable_search_dirs, así que el
cronograma del dashboard marca el período como "Completado" en el siguiente refresh).

Requiere: reportlab
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

FONT, FONTB = "Helvetica", "Helvetica-Bold"
for cand in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf"):
    if os.path.exists(cand):
        bold = cand.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf").replace("arial.ttf", "arialbd.ttf").replace("Arial.ttf", "Arial Bold.ttf")
        try:
            pdfmetrics.registerFont(TTFont("Body", cand))
            pdfmetrics.registerFont(TTFont("BodyB", bold if os.path.exists(bold) else cand))
            FONT, FONTB = "Body", "BodyB"
            break
        except Exception:
            pass

INK, MUTED, LINE, HEAD = colors.HexColor("#141413"), colors.HexColor("#6b6a65"), colors.HexColor("#dcdbd5"), colors.HexColor("#f0efec")
RISK_C = {"HIGH": colors.HexColor("#d03b3b"), "MEDIUM": colors.HexColor("#d9661f"), "LOW": colors.HexColor("#c08a00"), "INFO": colors.HexColor("#6b6a65")}
RES_C = {"PASS": colors.HexColor("#0b7f0b"), "WARNING": colors.HexColor("#c08a00"), "ERROR": colors.HexColor("#d03b3b")}
ST = {
    "h1": ParagraphStyle("h1", fontName=FONTB, fontSize=16, leading=20, textColor=INK, spaceAfter=2),
    "sub": ParagraphStyle("sub", fontName=FONT, fontSize=9, leading=12, textColor=MUTED, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName=FONTB, fontSize=11, leading=14, textColor=INK, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName=FONT, fontSize=8.6, leading=11.5, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName=FONT, fontSize=7.4, leading=9.4, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName=FONT, fontSize=7.2, leading=9, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName=FONTB, fontSize=7.2, leading=9, textColor=INK),
}


def load(name):
    with open(os.path.join(DATA, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cop(v, dec=0):
    if v is None or v == "":
        return "Sin evidencia"
    if not num(v):
        return str(v)
    s = f"{abs(v):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−$" if v < 0 else "$") + s


def pct(v, d=1):
    return "—" if not num(v) else f"{v * 100:.{d}f}%".replace(".", ",")


def var(a, b):
    return "—" if not (num(a) and num(b)) or not b else (("+" if a / b - 1 >= 0 else "−") + f"{abs(a / b - 1) * 100:.1f}%".replace(".", ","))


def P(t, s="cell"):
    return Paragraph(str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), ST[s])


def table(rows, widths, head=True, num_cols=(), color_col=None, color_map=None):
    data = [[P(c, "cellb" if (head and i == 0) else "cell") if not isinstance(c, Paragraph) else c for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    sty = [("GRID", (0, 0), (-1, -1), 0.3, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if head:
        sty.append(("BACKGROUND", (0, 0), (-1, 0), HEAD))
    for c in num_cols:
        sty.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(sty))
    if color_col is not None and color_map:
        for i, r in enumerate(rows[1:], start=1):
            col = color_map.get(str(r[color_col]))
            if col:
                data[i][color_col] = Paragraph(f'<font color="{col.hexval()}"><b>{r[color_col]}</b></font>', ST["cell"])
        t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
        t.setStyle(TableStyle(sty))
    return t


def footer(meta, title):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(MUTED)
        w, h = doc.pagesize
        canvas.drawString(12 * mm, 8 * mm, f"{title} · generado {dt.datetime.now():%Y-%m-%d %H:%M} desde data/*.json (refresh {meta.get('last_refresh')}) · fuente de verdad: libros Excel")
        canvas.drawRightString(w - 12 * mm, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()
    return draw


def q_of(t):
    m = re.findall(r"Q([1-4])", str(t or ""))
    return [int(x) for x in m]


def exc_in(e, y, q, source):
    return e.get("Source") == source and e.get("Año") == y and q in (e.get("quarter_span") or [])


def controls(meta_ctrl, y, q, prefix_re):
    return [c for c in meta_ctrl if c.get("Año") == y and str(c.get("Trimestre")) == f"Q{q}" and re.match(prefix_re, str(c.get("Control") or ""))]


def common_header(story, title, y, q, meta, scope):
    story.append(Paragraph(title, ST["h1"]))
    srcs = " · ".join(f"{s['file']} (SHA-256 {s['sha256'][:12]}…, modificado {s['modified']})" for s in meta.get("sources", []))
    story.append(Paragraph(f"Período auditado: Q{q}-{y} ({scope}) · Fecha de emisión: {dt.date.today():%d/%m/%Y} · Fuentes: {srcs}", ST["sub"]))


ES = {'Open': 'Abierta', 'Review': 'En revisión', 'Explained': 'Explicada', 'No Action Required': 'Sin acción requerida', 'Closed': 'Cerrada', 'Monitor': 'Monitorear'}


def exceptions_block(story, excs, W):
    if not excs:
        story.append(Paragraph("Sin excepciones registradas para este trimestre.", ST["p"]))
        return
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    rows = [["ID", "Riesgo", "Cuenta / tarjeta", "Concepto", "Monto", "Tipo de monto", "Conclusión de auditoría / acción", "Estado (antes → ahora)", "Hallazgo relacionado"]]
    for e in sorted(excs, key=lambda e: (e.get("is_open") is not True, order.get(e.get("Riesgo"), 9), -(e.get("Monto (COP)") or 0))):
        st = ES.get(e.get("Estado"), e.get("Estado"))
        if e.get("Estado anterior") and e.get("Estado anterior") != e.get("Estado"):
            st = f"{ES.get(e['Estado anterior'], e['Estado anterior'])} → {st}"
        rows.append([e["ID"], e.get("Riesgo"), e.get("Cuenta/Tarjeta"), e.get("Concepto"), cop(e.get("Monto (COP)")) if e.get("Monto (COP)") else "—", e.get("Tipo de monto") or "",
                     e.get("Conclusión de auditoría") or e.get("Acción"), st, e.get("Hallazgo relacionado") or ""])
    story.append(table(rows, [W * x for x in (.05, .055, .11, .15, .075, .09, .29, .085, .095)], num_cols=(4,), color_col=1, color_map=RISK_C))
    story.append(Spacer(1, 3))
    story.append(Paragraph("Detalle completo (explicación, evidencia, Money Pro, Splitwise) en Sistema_Auditoria_TC.xlsx › Excepciones_Central y en la pestaña Excepciones del dashboard.", ST["small"]))


def controls_block(story, ctl, W):
    if not ctl:
        story.append(Paragraph("No hay resultados de controles registrados para el trimestre en Controles_Trimestrales.", ST["p"]))
        return
    rows = [["Control", "Descripción", "Resultado", "Detalle / evidencia", "Excepción"]]
    for c in ctl:
        rows.append([c.get("Control"), c.get("Descripción"), c.get("Resultado"), c.get("Detalle / evidencia"), c.get("Excepción") or ""])
    story.append(table(rows, [W * x for x in (.06, .17, .07, .6, .1)], color_col=2, color_map=RES_C))


def continuity_block(story, excs, cont, W):
    links = []
    for e in excs:
        for h in re.findall(r"EX-\d+", e.get("Hallazgo relacionado") or ""):
            m = next((x for x in cont["matrix"] if x["Finding_ID"] == h), {})
            links.append([h, m.get("Continuity_Category") or "", (m.get("Original_Description") or "")[:90], e["ID"], m.get("Carry_Forward_Rule") or ""])
    if not links:
        story.append(Paragraph("Ninguna excepción del trimestre está vinculada a hallazgos históricos.", ST["p"]))
        return
    story.append(Paragraph("Los hallazgos históricos dan contexto; no se reabren. Cuando el control vuelve a fallar se registra una excepción nueva con el vínculo:", ST["p"]))
    story.append(Spacer(1, 3))
    story.append(table([["Hallazgo histórico", "Categoría de continuidad", "Descripción original", "Excepción nueva", "Regla de continuidad"]] + links,
                       [W * x for x in (.08, .16, .3, .08, .38)]))


def status_line(excs):
    n = lambda f: sum(1 for e in excs if f(e))
    return (f"Estado actual: {n(lambda e: e.get('is_open'))} abiertas, {n(lambda e: e.get('is_monitor'))} en monitoreo, "
            f"{n(lambda e: not e.get('is_open') and not e.get('is_monitor'))} explicadas / cerradas / sin acción requerida "
            f"({n(lambda e: e.get('closed_this_update'))} cerradas en la actualización de cierre con nueva evidencia).")


def summary_line(excs, ctl):
    r = {k: sum(1 for e in excs if e.get("Riesgo") == k) for k in ("HIGH", "MEDIUM", "LOW", "INFO")}
    c = {k: sum(1 for x in ctl if x.get("Resultado") == k) for k in ("PASS", "WARNING", "ERROR")}
    return r, c


# --------------------------------------------------------------------------------------
def report_tc(y, q, d, out):
    meta, cc, ex, cont, pu = d["metadata"], d["credit_cards"], d["exceptions"]["exceptions"], d["continuity"], d["product_utility"]
    W = landscape(A4)[0] - 24 * mm
    per, prev = f"Q{q}-{y}", f"Q{q}-{y - 1}"
    qs = {r["period"]: r for r in cc["quarter_summary"]}
    if per not in qs:
        print(f"  (sin datos de tarjetas para {per}; no se genera)")
        return None
    a, b = qs[per], qs.get(prev, {})
    excs = [e for e in ex if exc_in(e, y, q, "Credit Card")]
    ctl = controls(d["timeline"]["control_results"], y, q, r"^[MT]-\d")
    r, c = summary_line(excs, ctl)
    title = f"Auditoría Trimestral — Tarjetas de Crédito — {per}"
    story = []
    common_header(story, title, y, q, meta, "trimestral; Q4 se audita en enero del año siguiente")
    story.append(Paragraph("1. Resumen ejecutivo", ST["h2"]))
    und_pct = a["undetermined"] / a["gross_spend"] if a["gross_spend"] else None
    bullets = [
        f"Consumo bruto {cop(a['gross_spend'])} en {int(a['purchases'])} compras ({var(a['gross_spend'], b.get('gross_spend'))} vs {prev}). Personal {cop(a['personal'])}, familiar {cop(a['family'])}, no determinado {cop(a['undetermined'])} ({pct(und_pct)} del consumo).",
        f"Costo neto {cop(a['net_cost'])} = cuotas {cop(a['fees'])} + seguros {cop(a['insurance'])} + intereses {cop(a['interest'], 2)} − beneficios {cop(a['benefits'], 2)}. Solo incluye cargos de los extractos cargados.",
        f"Excepciones del trimestre: {len(excs)} (HIGH {r['HIGH']}, MEDIUM {r['MEDIUM']}, LOW {r['LOW']}, INFO {r['INFO']}). {status_line(excs)} Controles: {c['PASS']} PASS, {c['WARNING']} WARNING, {c['ERROR']} ERROR.",
    ]
    hi = [e for e in excs if e.get("Riesgo") == "HIGH" and e.get("is_open")]
    if hi:
        bullets.append("Prioridad: " + "; ".join(f"{e['ID']} — {e.get('Concepto')}" for e in hi) + ".")
    for t in bullets:
        story.append(Paragraph("• " + t, ST["p"]))
    story.append(Paragraph("2. Indicadores del trimestre (mismos criterios que Historico_Trimestral; conciliados por el ETL)", ST["h2"]))
    labels = [("gross_spend", "Consumo bruto"), ("reversals", "Reversiones"), ("purchases", "Número de compras"), ("personal", "Personal"), ("family", "Familiar / compartido"),
              ("undetermined", "No determinado"), ("fees", "Cuotas de manejo"), ("insurance", "Seguros"), ("interest", "Intereses"), ("benefits", "Beneficios (extracto)"), ("net_cost", "Costo neto")]
    rows = [["Indicador", per, prev, "Variación"]]
    for k, l in labels:
        fa, fb = a.get(k), b.get(k)
        f = (lambda v: f"{int(v):,}".replace(",", ".") if num(v) else "—") if k == "purchases" else (lambda v: cop(v, 2) if num(v) else "—")
        rows.append([l, f(fa), f(fb) if b else "Sin datos", var(fa, fb) if b else "—"])
    story.append(table(rows, [W * .3, W * .2, W * .2, W * .12], num_cols=(1, 2, 3)))
    story.append(Paragraph("3. Detalle por tarjeta", ST["h2"]))
    cs = [x for x in cc["card_summary"] if x["Año"] == y and x["Trimestre"] == q]
    rows = [["Tarjeta", "Consumo", "Compras", "Personal", "Familiar", "No det.", "Cuotas", "Seguros", "Intereses", "Beneficios", "Costo neto", "Utiliz. máx.", "Extractos"]]
    for x in sorted(cs, key=lambda x: -x["gross_spend"]):
        rows.append([x["Producto"], cop(x["gross_spend"]), int(x["purchases"]), cop(x["personal"]), cop(x["family"]), cop(x["undetermined"]), cop(x["fees"]), cop(x["insurance"]),
                     cop(x["interest"], 2), cop(x["benefits"], 2), cop(x["net_cost"], 2), pct(x.get("max_utilization")), x.get("statements")])
    story.append(table(rows, [W * .17] + [W * .069] * 12, num_cols=tuple(range(1, 13))))
    story.append(Paragraph("4. Cobertura y aritmética de extractos", ST["h2"]))
    st = [s for s in cc["statements"] if s.get("Año") == y and s.get("Trimestre") == q]
    rows = [["Corte", "Tarjeta", "Moneda", "Saldo anterior", "Compras / cargos", "Pagos", "Intereses", "Nuevo saldo", "Utiliz.", "Resultado"]]
    for s in sorted(st, key=lambda s: (s.get("Producto") or "", s.get("Fecha corte") or "")):
        rows.append([s.get("Fecha corte"), s.get("Producto"), s.get("Moneda"), cop(s.get("Saldo anterior"), 2), cop(s.get("Compras / cargos"), 2), cop(s.get("Pagos y abonos"), 2),
                     cop((s.get("Intereses corrientes") or 0) + (s.get("Intereses mora") or 0), 2), cop(s.get("Nuevo saldo"), 2), pct(s.get("Utilización")), s.get("Resultado")])
    story.append(table(rows, [W * x for x in (.07, .2, .05, .1, .1, .1, .08, .1, .06, .1)], num_cols=(3, 4, 5, 6, 7, 8)))
    months = [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    cov = [c for c in pu.get("coverage", []) if c.get("Mes") in months and c.get("Estado de cobertura") != "Con extracto"]
    if cov:
        story.append(Paragraph("Productos-mes sin extracto y su motivo (Cobertura_Extractos). 'Sin extracto' no es por sí mismo un problema: solo 'Falta extracto — requerido' genera excepción.", ST["small"]))
        grp = {}
        for c in cov:
            grp.setdefault((c["Producto"], c["Estado de cobertura"], c.get("Excepción") or ""), []).append(c["Mes"][5:])
        story.append(table([["Producto", "Estado de cobertura", "Meses", "Excepción"]] + [[k[0], k[1], ", ".join(v), k[2]] for k, v in grp.items()], [W * .25, W * .4, W * .12, W * .1]))
    else:
        story.append(Paragraph("Todos los productos con actividad tienen extracto en el trimestre.", ST["small"]))
    story.append(PageBreak())
    story.append(Paragraph("5. Resultado de los controles trimestrales", ST["h2"]))
    controls_block(story, ctl, W)
    story.append(Paragraph("6. Excepciones del trimestre", ST["h2"]))
    exceptions_block(story, excs, W)
    story.append(Paragraph("7. Continuidad con hallazgos históricos", ST["h2"]))
    continuity_block(story, excs, cont, W)
    story.append(Paragraph("8. Utilidad de las tarjetas en el trimestre (Productos_Financieros)", ST["h2"]))
    mon = [m for m in pu["monthly"] if m.get("Año") == y and m.get("Trimestre") == q and "tarjeta" in str(m.get("Tipo de producto") or "").lower()]
    agg = {}
    for m in mon:
        g = agg.setdefault(m["Producto"], {"c": 0, "b": 0, "n": 0, "cons": 0, "pts": 0, "sin": 0})
        g["c"] += m.get("Costo total") or 0; g["b"] += m.get("Beneficios totales") or 0; g["n"] += m.get("Valor neto") or 0
        g["cons"] += m.get("Consumo asociado") or 0; g["pts"] += m.get("Puntos monetizados") or 0
        g["sin"] += 1 if any(m.get(k) is None for k in ("Cuotas de manejo", "Intereses pagados", "Seguros")) else 0
    rows = [["Tarjeta", "Consumo", "Costo total", "Beneficios", "de ellos: puntos", "Valor neto", "ROI", "Meses sin evidencia de costos"]]
    for p_, g in sorted(agg.items(), key=lambda kv: -kv[1]["n"]):
        rows.append([p_, cop(g["cons"]) if g["cons"] else "Sin evidencia", cop(g["c"], 2), cop(g["b"], 2), cop(g["pts"], 2), cop(g["n"], 2), pct(g["n"] / g["c"]) if g["c"] else "n/a", g["sin"]])
    story.append(table(rows, [W * x for x in (.24, .1, .1, .1, .1, .1, .08, .12)], num_cols=(1, 2, 3, 4, 5, 6, 7)))
    story.append(Paragraph(f"Puntos valorados a {pu['metadata'].get('points_cop')} COP/punto (valor realizado en redenciones verificadas; Parametros del libro TC). Beneficios cualitativos no se monetizan.", ST["small"]))
    story.append(Paragraph("9. Supuestos y limitaciones", ST["h2"]))
    for t in assumptions(ex, y, "Credit Card"):
        story.append(Paragraph("• " + t, ST["p"]))
    return build(out, story, title, meta)


def report_bank(y, q, d, out):
    meta, bk, ex, cont, pu = d["metadata"], d["bank_cash"], d["exceptions"]["exceptions"], d["continuity"], d["product_utility"]
    W = landscape(A4)[0] - 24 * mm
    per, prev = f"Q{q}-{y}", f"Q{q}-{y - 1}"
    hist = bk["historico_trimestral"]
    if per not in hist.get("periods", []):
        print(f"  (Historico_Trimestral_Bancos no tiene {per}; no se genera)")
        return None
    excs = [e for e in ex if exc_in(e, y, q, "Bank & Cash")]
    ctl = controls(d["timeline"]["control_results"], y, q, r"^T-BA")
    r, c = summary_line(excs, ctl)
    H = hist["rows"]
    g = lambda lab, p: (H.get(lab) or {}).get(p)
    title = f"Auditoría Trimestral — Bancos y Efectivo — {per}"
    story = []
    common_header(story, title, y, q, meta, "cuenta de ahorros *9910 y fiducuentas")
    story.append(Paragraph("1. Resumen ejecutivo", ST["h2"]))
    bullets = [
        f"Entradas brutas *9910 {cop(g('Gross entradas — *9910', per), 2)} y salidas brutas {cop(g('Gross salidas — *9910', per), 2)}. Pagos de tarjeta {cop(g('Pagos de tarjeta de crédito', per), 2)}; intereses y rendimientos {cop(g('Ingreso de inversión (intereses y rendimientos)', per), 2)}.",
        "Las transferencias *9910 ↔ fiducuentas son capital interno (no ingreso ni gasto); solo el rendimiento neto es ingreso financiero.",
        f"Excepciones del trimestre: {len(excs)} (HIGH {r['HIGH']}, MEDIUM {r['MEDIUM']}, LOW {r['LOW']}, INFO {r['INFO']}). {status_line(excs)} Controles: {c['PASS']} PASS, {c['WARNING']} WARNING, {c['ERROR']} ERROR.",
    ]
    hi = [e for e in excs if e.get("Riesgo") in ("HIGH", "MEDIUM") and e.get("is_open")]
    if hi:
        bullets.append("Prioridad: " + "; ".join(f"{e['ID']} ({e['Riesgo']}) — {e.get('Concepto')}" for e in hi) + ".")
    for t in bullets:
        story.append(Paragraph("• " + t, ST["p"]))
    story.append(Paragraph("2. Indicadores del trimestre (Historico_Trimestral_Bancos del libro; conciliados por el ETL)", ST["h2"]))
    rows = [["Indicador", per, prev, "Variación"]]
    for lab, vals in H.items():
        a_, b_ = vals.get(per), vals.get(prev)
        isn = "(n°)" in lab
        f = (lambda v: f"{int(v):,}".replace(",", ".") if num(v) else ("—" if v is None else str(v))) if isn else (lambda v: cop(v, 2) if num(v) else ("—" if v is None else str(v)))
        rows.append([lab, f(a_), f(b_) if prev in hist["periods"] else "Sin datos", var(a_, b_)])
    story.append(table(rows, [W * .38, W * .17, W * .17, W * .1], num_cols=(1, 2, 3)))
    story.append(Paragraph("3. Continuidad de saldos", ST["h2"]))
    months = [f"{y}-{m:02d}" for m in range(3 * q - 2, 3 * q + 1)]
    bc = [x for x in bk["balance_continuity"] if x.get("Período") == per or x.get("Período") in months]
    rows = [["Cuenta", "Período", "Saldo inicial", "Saldo final extracto", "Intereses / rendimientos", "Estado"]]
    for x in bc:
        rows.append([x["Cuenta"], x["Período"], cop(x.get("Saldo inicial"), 2), cop(x.get("Saldo final extracto"), 2), cop(x.get("Intereses"), 2) if x.get("Intereses") is not None else "—", x.get("Estado")])
    story.append(table(rows, [W * x for x in (.22, .1, .15, .15, .15, .08)], num_cols=(2, 3, 4)))
    story.append(Paragraph("4. Transferencias internas *9910 ↔ fiducuentas", ST["h2"]))
    tr = [x for x in bk["internal_transfers"]["monthly"] if x.get("Mes") in months]
    rows = [["Mes", "*9910 → fiducuentas", "Adiciones (fiducia)", "Dif.", "Fiducuentas → *9910", "Retiros (fiducia)", "Dif.", "Estado"]]
    for x in tr:
        rows.append([x["Mes"], cop(x.get("*9910 → Fiducuentas")), cop(x.get("Adiciones Fiducuentas")), cop(x.get("Dif. aportes")), cop(x.get("Fiducuentas → *9910")), cop(x.get("Retiros Fiducuentas")), cop(x.get("Dif. retiros")), x.get("Estado")])
    story.append(table(rows, [W * x for x in (.08, .13, .13, .07, .13, .13, .07, .14)], num_cols=(1, 2, 3, 4, 5, 6)))
    story.append(Paragraph("5. Pagos de tarjetas desde la *9910", ST["h2"]))
    pg = [x for x in bk["card_payments"] if x.get("Año") == y and str(x.get("Trimestre")) == f"Q{q}"]
    agg = {}
    for x in pg:
        k = (x.get("Tarjeta / producto"), x.get("Estado"))
        a = agg.setdefault(k, [0, 0.0]); a[0] += 1; a[1] += x.get("Monto pagado") or 0
    rows = [["Tarjeta", "Estado de conciliación", "Pagos", "Monto"]] + [[k[0], k[1], v[0], cop(v[1], 2)] for k, v in sorted(agg.items(), key=lambda kv: -kv[1][1])]
    story.append(table(rows, [W * .3, W * .35, W * .08, W * .15], num_cols=(2, 3)))
    story.append(PageBreak())
    story.append(Paragraph(f"6. Movimientos materiales (≥ {cop(meta.get('materiality_cop'))})", ST["h2"]))
    mat = [x for x in bk["material_movements"] if x.get("Año") == y and str(x.get("Trimestre")) == f"Q{q}"]
    rows = [["ID", "Fecha", "Cuenta", "Descripción", "Valor", "Clasificación", "Conclusión", "Excepción"]]
    for x in sorted(mat, key=lambda x: x.get("Fecha") or ""):
        rows.append([x["ID"], x.get("Fecha"), x.get("Cuenta"), x.get("Descripción"), cop(x.get("Valor"), 2), x.get("Clasificación"), x.get("Conclusión"), x.get("Excepción") or ""])
    story.append(table(rows, [W * x for x in (.06, .07, .13, .2, .1, .12, .24, .07)], num_cols=(4,)) if mat else Paragraph("Sin movimientos materiales en el trimestre.", ST["p"]))
    story.append(Paragraph("7. Fiducuenta TC y fiducuentas", ST["h2"]))
    fid = [x for x in pu["fiducuentas"] if x.get("Año") == y and str(x.get("Trimestre")) == f"Q{q}"]
    rows = [["Cuenta", "Mes", "Saldo inicial", "Aportes", "Retiros", "Rend. netos", "Retención", "Saldo final", "Tasa obs. E.A.", "A pagos TC", "Money Pro", "Dif. vs MP"]]
    for x in fid:
        rows.append([x["Cuenta"] + (" (TC)" if x.get("is_tc") else ""), x["Mes"], cop(x.get("Saldo inicial"), 2), cop(x.get("Capital aportado")), cop(x.get("Capital retirado")),
                     cop(x.get("Intereses generados (rend. netos)"), 2), cop(x.get("Retención"), 2), cop(x.get("Saldo final"), 2), pct(x.get("Tasa efectiva observada E.A."), 2),
                     cop(x.get("Capital destinado a pagos TC (atribuible)")) if num(x.get("Capital destinado a pagos TC (atribuible)")) else (x.get("Capital destinado a pagos TC (atribuible)") or ""),
                     cop(x.get("Money Pro registrado"), 2), cop(x.get("Dif. neto vs Money Pro"), 2)])
    story.append(table(rows, [W * x for x in (.12, .06, .09, .08, .08, .08, .07, .09, .07, .09, .08, .08)], num_cols=tuple(range(2, 12))) if fid else Paragraph("Sin fiducuentas en el trimestre.", ST["p"]))
    story.append(Paragraph(f"Fiducuenta TC = {pu['metadata'].get('fiducuenta_tc_id')} (confirmada por evidencia: función observada en los extractos detallados y etiqueta 'Fiducuenta TC' en Money Pro; EX-48 cerrada). «A pagos TC» = atribución exacta por cuenta y fecha con los extractos detallados. Costo de oportunidad: no calculado (sin metodología ni tasa alternativa evidenciada).", ST["small"]))
    story.append(Paragraph("8. Resultado de los controles trimestrales", ST["h2"]))
    controls_block(story, ctl, W)
    story.append(Paragraph("9. Excepciones del trimestre", ST["h2"]))
    exceptions_block(story, excs, W)
    story.append(Paragraph("10. Continuidad con hallazgos históricos", ST["h2"]))
    continuity_block(story, excs, cont, W)
    story.append(Paragraph("11. Supuestos y limitaciones", ST["h2"]))
    for t in assumptions(ex, y, "Bank & Cash"):
        story.append(Paragraph("• " + t, ST["p"]))
    return build(out, story, title, meta)


def assumptions(ex, y, source):
    base = ["Fuente de verdad: los libros Excel. Este informe se genera desde los datasets del ETL, conciliados contra las hojas resumen del libro.",
            "Ningún saldo, tasa, interés, beneficio, costo, fecha, transacción ni clasificación se estimó: lo faltante figura como 'Sin evidencia' o 'No determinado' y genera excepción de cobertura.",
            "Materialidad: movimientos ≥ COP 1.000.000 revisados individualmente; patrones repetidos de menor valor se evalúan en los controles."]
    for e in ex:
        if e.get("Source") == source and e.get("Año") == y and re.search(r"supuesto|limitaci|resumen", f"{e.get('Tipo')} {e.get('Concepto')}", re.I):
            base.append(f"{e['ID']}: {e.get('Concepto')} — {e.get('Explicación')}")
    return base


def build(out, story, title, meta):
    os.makedirs(os.path.dirname(out), exist_ok=True)
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=11 * mm, bottomMargin=14 * mm, title=title,
                            author="Sistema de Auditoría de Cuentas Financieras", subject=title)
    fn = footer(meta, title)
    doc.build(story, onFirstPage=fn, onLaterPages=fn)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera los informes trimestrales en PDF desde data/*.json")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--quarter", type=int, nargs="+", required=True)
    ap.add_argument("--out", default=None, help="Carpeta de salida (por defecto deliverables/<año>)")
    args = ap.parse_args(argv)
    with open(os.path.join(ROOT, "scripts", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    d = {n: load(n) for n in ("metadata", "credit_cards", "bank_cash", "exceptions", "timeline", "continuity", "product_utility")}
    if d["metadata"].get("status") == "FAILED":
        sys.exit("El último refresh falló: corrija los errores y ejecute refresh_dashboard.py antes de emitir informes.")
    out_dir = args.out or os.path.join(ROOT, "deliverables", str(args.year))
    for q in args.quarter:
        for key, fn in (("tc", report_tc), ("bank", report_bank)):
            name = cfg["deliverables"][key]["quarterly"].format(Y=args.year, Q=q)
            p = fn(args.year, q, d, os.path.join(out_dir, name))
            if p:
                print("OK", os.path.relpath(p, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())

/* app.js — enrutador y renderizado de vistas (v3, rediseño nov-2026).
   Vistas principales (Resumen, Tarjetas, Bancos, Productos): pocas cifras, nombres comerciales, sin referencias a hojas.
   Control de auditoría (Excepciones, Cronograma y continuidad, Calidad de datos): detalle completo y trazabilidad.
   Visualiza las clasificaciones del libro; solo filtra y agrega (SUMA / CONTEO / razones). Ninguna regla de auditoría vive aquí. */
(function () {
  "use strict";
  const D = window.Data, F = window.Filters, C = window.Charts, T = window.Tables, N = window.Names;
  const fmt = D.fmt, esc = fmt.esc;
  const PAGES = ["tesoreria", "resumen", "tarjetas", "bancos", "productos", "excepciones", "cronograma", "calidad"];
  const ALIAS = { utilidad: "productos", continuidad: "cronograma" };
  const TITLES = { tesoreria: "Tesorería", resumen: "Resumen", tarjetas: "Tarjetas de crédito", bancos: "Bancos y efectivo", productos: "Productos", excepciones: "Excepciones", cronograma: "Cronograma y continuidad", calidad: "Calidad de datos" };
  const CONTROL = ["excepciones", "cronograma", "calidad"];
  const ui = { ccMeasure: "gross_spend", excView: "todas", dqAll: false };

  /* ---------- vocabulario de presentación ---------- */
  const ESTADO = { "Open": "Abierta", "Review": "En revisión", "Explained": "Explicada", "No Action Required": "Sin acción requerida", "Closed": "Cerrada", "Corrected": "Corregida", "Monitor": "En monitoreo" };
  const MODULO = { "Credit Card": "Tarjetas", "Bank & Cash": "Bancos" };
  const RIESGO_TXT = { HIGH: "Alto", MEDIUM: "Medio", LOW: "Bajo", INFO: "Info" };
  const CAT_SHORT = { A: "Resuelto · no reabrir", B: "Resuelto · monitorear", C: "Control recurrente", D: "Carry forward", E: "Reemplazado por control", F: "Contexto histórico", "?": "Sin clasificar" };
  const COL = { cur: "#1f3a5f", prev: "#c9c9c4", fam: "#7d8fa6", und: "#d6d6d2", neg: "#8a8a85", line: "#3a3a37" };

  /* ---------- formato ---------- */
  const num = v => typeof v === "number" && isFinite(v);
  const nz = v => num(v) ? v : 0;
  const dec = (v, d) => Math.abs(v).toFixed(d).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const M = v => !num(v) ? "—" : v < 0 ? `(${fmt.int(Math.round(-v))})` : fmt.int(Math.round(v));         // COP, cifra completa
  const K = v => M(v);
  const CP = v => !num(v) ? "—" : v < 0 ? `(${fmt.int(Math.round(-v))})` : fmt.int(Math.round(v));          // COP
  const pct = (v, d = 1) => fmt.pct(v, d);
  const nm = p => esc(N.name(p));
  const nmRef = p => { const n = N.name(p), r = N.ref(p); return `${esc(n)}${r && !n.includes(r) ? ` <span class="ref-s">${esc(r)}</span>` : ""}`; };
  const estadoTxt = s => ESTADO[s] || s || "—";
  const qOf = r => r.Trimestre_n !== undefined ? r.Trimestre_n : (typeof r.Trimestre === "number" ? r.Trimestre : Number(String(r.Trimestre || "").replace("Q", "")));
  const CY = () => D.currentYear;
  const excProd = e => { const t = N.text(e.Producto); return t !== String(e.Producto || "") ? t : N.text(e["Cuenta/Tarjeta"] || e.Producto); };
  const catCode = e => (e.continuity && e.continuity.code) || "?";
  const short = (t, n = 140) => { t = String(t || "").replace(/\s+/g, " ").trim(); return t.length > n ? t.slice(0, n - 1).replace(/\s\S*$/, "") + "…" : t; };
  const src = tip => tip ? `<span class="src" tabindex="0" data-tip="${esc(tip)}">i</span>` : "";

  /* ---------- componentes ---------- */
  function kpi(label, value, unit, sub, o = {}) {
    return `<div class="kpi ${o.sm ? "sm" : ""} ${o.alert ? "alert" : ""}"><span class="l">${esc(label)}${o.tip ? src(o.tip) : ""}</span><span class="v num">${value}</span>${unit ? `<span class="u">${unit}</span>` : ""}${sub ? `<span class="d num">${sub}</span>` : ""}</div>`;
  }
  const card = (title, body, o = {}) => `<section class="card"><header><h2>${esc(title)}</h2>${o.unit ? `<span class="unit">${o.unit}</span>` : ""}${o.right ? `<div class="right">${o.right}</div>` : ""}</header>${o.flush ? `<div class="flush">${body}</div>` : `<div class="body">${body}</div>`}${o.note ? `<div class="foot-note">${o.note}</div>` : ""}</section>`;
  const more = (title, body, o = {}) => `<details class="more" ${o.open ? "open" : ""}><summary><span>${esc(title)}</span>${o.meta ? `<span class="muted">${o.meta}</span>` : ""}</summary><div class="inner">${o.pad ? `<div class="body">${body}</div>` : body}</div></details>`;
  const legend = items => `<div class="legend">${items.map(i => `<span><i class="${i.line ? "line" : ""}" style="background:${i.color}"></i>${esc(i.label)}</span>`).join("")}</div>`;
  const pill = (txt, cls, title) => `<span class="pill ${cls || ""}" ${title ? `title="${esc(title)}"` : ""}>${esc(txt)}</span>`;
  const resPill = r => pill(r || "—", r === "PASS" ? "ok" : r === "WARNING" ? "low" : r === "ERROR" ? "high" : "");
  const tlPill = s => pill(s || "—", { "Completado": "ok", "En auditoría": "blue", "Pendiente": "medium" }[s] || "");
  const riskTxt = e => e.Riesgo ? `<span class="risk ${esc(e.Riesgo)} ${e.is_open ? "open" : ""}">${esc(RIESGO_TXT[e.Riesgo] || e.Riesgo)}</span>` : "";
  const statusPill = e => pill(estadoTxt(e.Estado), e.is_open ? (e.Riesgo === "HIGH" ? "high" : "medium") : e.is_monitor ? "blue" : "ok",
    e["Estado original"] && e["Estado original"] !== e.Estado ? `Estado en el libro: ${e["Estado original"]}` : "");
  const catTxt = code => `<span class="muted" title="${esc((D.cont && D.cont.metadata.categories[code]) || CAT_SHORT[code])}">${esc((code !== "?" ? code + " · " : "") + CAT_SHORT[code])}</span>`;

  /* ---------- alcance y comparativos (siempre por filtro; nunca reclasifica) ---------- */
  const selYear = () => F.get("year") ? Number(F.get("year")) : null;
  const selQ = () => F.get("quarter") ? Number(F.get("quarter")) : null;
  function quartersIn(year, rows) { const s = new Set(); (rows || []).forEach(r => { if (r.Año === year) s.add(qOf(r)); }); return [...s].filter(Boolean).sort(); }
  function prevScope(rows, kind) {
    const y = selYear(); if (!y || !D.years.includes(y - 1)) return null;
    const base = kind === "bank" ? F.bankRows(rows, { ignoreYear: true }) : kind === "pu" ? F.puRows(rows, { ignoreYear: true }) : F.tcRows(rows, { ignoreYear: true });
    const qs = selQ() ? [selQ()] : quartersIn(y, kind === "bank" ? D.bank.transactions : D.cc.transactions);
    const m = F.get("month");
    return base.filter(r => r.Año === y - 1 && qs.includes(qOf(r)) && (!m || !r.Mes || r.Mes.slice(5) === m.slice(5)));
  }
  function qRange(y, kind) {
    const qs = selQ() ? [selQ()] : quartersIn(y, kind === "bank" ? D.bank.transactions : D.cc.transactions);
    if (!qs.length) return String(y);
    if (qs.length === 4) return String(y);
    return qs.length === 1 ? `Q${qs[0]}-${y}` : `Q${qs[0]}–Q${qs[qs.length - 1]} ${y}`;
  }
  const scopeLabel = kind => { const y = selYear(); if (!y) return "Todos los períodos"; const m = F.get("month"); return m ? F.monthLabel(m) : qRange(y, kind); };
  function prevLabelFor(kind) { const y = selYear(); if (!y || !D.years.includes(y - 1)) return ""; const qs = selQ() ? [selQ()] : quartersIn(y, kind === "bank" ? D.bank.transactions : D.cc.transactions); return qs.length === 4 || !qs.length ? String(y - 1) : qs.length === 1 ? `Q${qs[0]}-${y - 1}` : `Q${qs[0]}–Q${qs[qs.length - 1]} ${y - 1}`; }
  function vs(cur, prev, o = {}) {
    if (prev === null || prev === undefined || !num(cur)) return "";
    const lbl = o.label || prevLabelFor(o.kind);
    if (!prev) return `vs ${o.fmt ? o.fmt(prev) : M(prev)} en ${esc(lbl)}`;
    return `${fmt.signedPct(cur / prev - 1)} vs ${o.fmt ? o.fmt(prev) : M(prev)} en ${esc(lbl)}`;
  }
  function latestBalances(rows) {
    const by = D.groupBy(rows, r => r.Cuenta), out = [];
    by.forEach((list, acc) => { list.sort((a, b) => String(a.Mes).localeCompare(String(b.Mes))); const l = list[list.length - 1]; if (num(l["Saldo final"])) out.push({ Cuenta: acc, Mes: l.Mes, Saldo: l["Saldo final"], Fuente: l.Fuente }); });
    return out;
  }
  // tarjetas: medidas del período
  function ccScope(o = {}) {
    const tx = F.tcRows(D.cc.transactions, o), txNC = F.tcRows(D.cc.transactions, Object.assign({ ignoreCategory: true }, o));
    const st = F.tcRows(D.cc.statements, Object.assign({ ignoreCategory: true }, o)), bn = F.tcRows(D.cc.benefits, Object.assign({ ignoreCategory: true }, o));
    const m = { gross: D.ccm("gross_spend", tx), purchases: D.ccm("purchases", tx), personal: D.ccm("personal", tx), family: D.ccm("family", tx), und: D.ccm("undetermined", tx),
      fees: D.ccm("fees", txNC), ins: D.ccm("insurance", txNC), intr: D.ccm("interest", st), ben: D.ccm("benefits", bn) };
    m.fin = m.fees + m.ins + m.intr; m.net = m.fin - m.ben;
    return { tx, st, bn, m };
  }
  function ccPrev() {
    const px = prevScope(D.cc.transactions); if (!px) return null;
    const pst = prevScope(D.cc.statements), pbn = prevScope(D.cc.benefits);
    const m = { gross: D.ccm("gross_spend", px), purchases: D.ccm("purchases", px), fees: D.ccm("fees", px), ins: D.ccm("insurance", px), intr: D.ccm("interest", pst), ben: D.ccm("benefits", pbn) };
    m.fin = m.fees + m.ins + m.intr; m.net = m.fin - m.ben; return m;
  }
  // productos: agregado por producto en el alcance
  const PU_COST = ["Cuotas de manejo", "Intereses pagados", "Seguros", "Otros costos"];
  const PU_BEN = ["Cashback", "Descuentos", "Puntos monetizados", "Otros beneficios", "Intereses ganados"];
  function puProducts(rows) {
    const cat = D.pu.catalog, by = D.groupBy(rows, r => r.ID_Producto);
    return [...by].map(([id, list]) => {
      const c = cat.find(x => x.ID_Producto === id) || {};
      const o = { id, Producto: list[0].Producto, Banco: list[0].Banco, Tipo: list[0]["Tipo de producto"], Función: list[0].Función || c.Función, Estado: c.Estado || list[0].Estado, meses: list.length, cat: c };
      PU_COST.concat(PU_BEN, ["Consumo asociado", "Puntos ganados", "Costo total", "Beneficios totales", "Valor neto", "Beneficio potencial (teórico)", "Con uso (1=sí)"]).forEach(k => { o[k] = D.sum(list, k); });
      const sp = list.map(r => r["Saldo promedio"]).filter(num); o["Saldo promedio"] = sp.length ? sp.reduce((a, b) => a + b, 0) / sp.length : null;
      o.isCard = /tarjeta/i.test(o.Tipo || ""); o.isAcct = /cuenta|fiducuenta/i.test(o.Tipo || "");
      o.ROI = o.isCard && o["Costo total"] ? o["Valor neto"] / o["Costo total"] : null;
      o.costPct = o["Consumo asociado"] ? o["Costo total"] / o["Consumo asociado"] : null;
      o.teorico = o["Beneficio potencial (teórico)"]; o.captura = o.teorico ? o["Beneficios totales"] / o.teorico : null;
      o.mesesUso = o["Con uso (1=sí)"];
      o.cobertura = c[Object.keys(c).find(k => /^Estado de cobertura \d{4}$/.test(k))] || D.uniq(list.map(r => r["Estado de cobertura"])).join(" · ");
      o.fuentes = c["Fuente costos"] ? `${c["Fuente costos"]} / ${c["Fuente beneficios"]}` : list[0].Fuente;
      return o;
    }).sort((a, b) => b["Valor neto"] - a["Valor neto"]);
  }
  const isFidu = p => /fiducuenta/i.test(p.Tipo || "") || (N.find(p.Producto) || {}).kind === "fiducuenta";
  function rankList(prod, o = {}) {
    const list = prod.filter(p => (p["Costo total"] || p["Beneficios totales"]) && !isFidu(p));
    if (!list.length) return `<div class="empty">Sin productos con costos o beneficios en el período.</div>`;
    const mx = Math.max(...list.map(p => Math.abs(p["Valor neto"]))) || 1;
    const bar = p => `<div class="bar-cell"><div class="bar ${p["Valor neto"] < 0 ? "neg" : ""}" style="width:${Math.max(0.5, Math.abs(p["Valor neto"]) / mx * 100).toFixed(1)}%"></div></div>`;
    if (o.wide) return `<div class="rank wide"><span class="h">Producto</span><span class="h r">Costos</span><span class="h r">Beneficios</span><span class="h bar-cell"></span><span class="h r">Valor neto</span>
      ${list.map(p => `<span>${nmRef(p.Producto)}</span><span class="r">${K(p["Costo total"])}</span><span class="r">${K(p["Beneficios totales"])}</span>${bar(p)}<span class="r" ${p["Valor neto"] < 0 ? 'style="font-weight:700"' : ""}>${K(p["Valor neto"])}</span>`).join("")}</div>`;
    return `<div class="rank">${list.map(p => `<span>${nmRef(p.Producto)}</span>${bar(p)}<span class="r">${K(p["Valor neto"])}</span>`).join("")}</div>`;
  }

  /* ---------- cabecera, período, pie ---------- */
  function renderPeriod() {
    const host = document.getElementById("period");
    const apY = F.applies("year"), apQ = F.applies("quarter");
    const y = F.state.year, q = F.state.quarter;
    const qs = F.options("quarter");
    host.innerHTML = `<label class="sr" for="p-year" style="display:none">Año</label><select id="p-year" ${apY ? "" : "disabled"} aria-label="Año"><option value="">Todos los años</option>${D.years.map(v => `<option value="${v}" ${String(v) === y ? "selected" : ""}>${v}</option>`).join("")}</select>
      <select id="p-q" ${apQ ? "" : "disabled"} aria-label="Trimestre"><option value="">Año completo</option>${qs.map(o => `<option value="${esc(o[0])}" ${o[0] === q ? "selected" : ""}>${esc(o[1])}</option>`).join("")}</select>`;
    host.querySelector("#p-year").addEventListener("change", e => F.set("year", e.target.value));
    host.querySelector("#p-q").addEventListener("change", e => F.set("quarter", e.target.value));
    const pl = prevLabelFor(F.page === "bancos" ? "bank" : "tc");
    document.getElementById("cmp-label").textContent = F.page === "tesoreria" ? (trPeriod().prev ? `vs ${trPeriod().prev}` : "") : !CONTROL.includes(F.page) && pl ? `vs ${pl}` : "";
    const n = ["month", "bank", "product", "card", "category", "flow", "status", "risk", "source"].filter(k => F.applies(k) && F.get(k)).length;
    document.getElementById("btn-filters").textContent = n ? `Filtros (${n})` : "Filtros";
  }
  function renderChrome() {
    const m = D.meta || {};
    const dq = m.dq_summary || {}, fails = (m.reconciliation || {}).failed || 0, errs = (m.errors || []).length;
    document.getElementById("side-foot").innerHTML = `Datos al ${esc(fmt.date(m.last_refresh).slice(0, 10))}<br>${errs || dq.ERROR || fails ? '<span style="color:var(--high)">Revisar calidad de datos</span>' : `Integridad: ${fmt.int((m.reconciliation || {}).passed)} conciliaciones OK`}`;
    const open = D.exceptions.filter(e => !e.is_historical && e.is_open).length;
    document.getElementById("nav-exc").textContent = open ? String(open) : "";
    document.getElementById("nav-dq").textContent = errs || dq.ERROR ? "!" : "";
    const ban = document.getElementById("banner");
    if (m.status === "FAILED") ban.innerHTML = `<div class="banner error"><b>El último refresh falló</b> (${fmt.date(m.last_refresh)}). Se muestran los datos anteriores. ${(m.errors || []).map(e => "<br>• " + esc(e.message)).join("")}</div>`;
    else if (fails) ban.innerHTML = `<div class="banner warn"><b>${fails} conciliación(es) fallida(s).</b> Revise <a href="#calidad">Calidad de datos</a> antes de usar las cifras.</div>`;
    else ban.innerHTML = "";
  }
  function renderFoot(p) {
    const m = D.meta || {};
    const el = document.getElementById("foot");
    if (CONTROL.includes(p)) el.innerHTML = `Fuente de verdad: ${(m.sources || []).map(s => `${esc(s.file)} (modificado ${fmt.date(s.modified)})`).join(" · ")}. Refresh ${fmt.date(m.last_refresh)} · esquema v${esc(m.schema_version || "")}.`;
    else if (p === "tesoreria") el.innerHTML = `Cifras en COP. Período: ${esc(trPeriod().cur || "—")} (cierre de trimestre). Fuente: Sistema_Auditoria_TC.xlsx › Metricas_Tesoreria y Tesoreria_Input, conciliada contra Auditoria_Bancos.xlsx. Datos al ${esc(fmt.date(m.last_refresh).slice(0, 10))}.`;
    else el.innerHTML = `Cifras en COP. Período: ${esc(scopeLabel(p === "bancos" ? "bank" : "tc"))}. Datos al ${esc(fmt.date(m.last_refresh).slice(0, 10))}. Origen y conciliaciones en <a href="#calidad">Calidad de datos</a>.`;
  }

  /* ---------- estado de auditoría (compartido) ---------- */
  function auditState() {
    const yr = selYear() || CY();
    const per = D.tl.periods.filter(p => p.year === yr);
    const quarters = [1, 2, 3, 4].map(q => ({ q, rows: per.filter(p => p.quarter === q) }));
    const done = quarters.filter(x => x.rows.length && x.rows.every(p => p.status === "Completado"));
    const lastExec = D.uniq(per.filter(p => p.status === "Completado").map(p => p.execution_date)).sort().pop();
    const pending = D.tl.periods.filter(p => p.year >= yr && p.status !== "Completado").sort((a, b) => String(a.planned_execution).localeCompare(String(b.planned_execution)) || (a.quarter || 9) - (b.quarter || 9));
    const next = pending.find(p => p.quarter);
    const deliv = per.filter(p => p.deliverable && (p.deliverable_path || p.deliverable_declared)).length;
    return { yr, per, quarters, done, lastExec, pending, next, deliv };
  }
  function excState(list) {
    const cur = list.filter(e => !e.is_historical);
    const c = { cur, open: cur.filter(e => e.is_open), mon: cur.filter(e => e.is_monitor) };
    c.byState = D.uniq(cur.map(e => e.Estado)).map(s => [s, cur.filter(e => e.Estado === s).length]).sort((a, b) => b[1] - a[1]);
    c.highOpen = cur.filter(e => e.Riesgo === "HIGH" && e.is_open).length; c.high = cur.filter(e => e.Riesgo === "HIGH").length;
    return c;
  }
  function railHTML() {
    const a = auditState(), x = excState(D.exceptions.filter(e => e.Año === a.yr || !e.is_historical)), m = D.meta, dq = m.dq_summary || {}, rc = m.reconciliation || {};
    const mods = ["Credit Card", "Bank & Cash"];
    const cell = (q, mod) => { const p = a.per.find(r => r.quarter === q && r.source === mod); if (!p) return "—"; return p.status === "No iniciado" ? `<span class="muted">${esc(F.monthLabel(p.planned_execution))}</span>` : esc(p.status); };
    const annual = mods.map(mod => a.per.find(p => !p.quarter && p.source === mod)).filter(Boolean);
    return `
      <section class="card"><h2>Estado de auditoría ${a.yr}</h2>
        <div class="kv"><div><span>Trimestres auditados</span><span class="num">${a.done.length} de 4</span></div></div>
        <div class="progress"><span style="width:${a.done.length / 4 * 100}%"></span></div>
        <table class="mini"><thead><tr><th>Período</th><th>Tarjetas</th><th>Bancos</th></tr></thead><tbody>
          ${a.quarters.map(({ q }) => `<tr><td>Q${q}</td><td>${cell(q, mods[0])}</td><td>${cell(q, mods[1])}</td></tr>`).join("")}
          ${annual.length ? `<tr><td>Anual</td>${mods.map(mod => { const p = annual.find(r => r.source === mod); return `<td>${p ? esc(p.status) : "—"}</td>`; }).join("")}</tr>` : ""}
        </tbody></table>
        <span class="small muted">${a.deliv} informe(s) emitido(s)${a.lastExec ? ` · última ejecución ${esc(fmt.date(a.lastExec))}` : ""}</span>
      </section>
      <section class="card"><h2>Excepciones ${a.yr}</h2>
        <div class="big2 num"><div><div class="v">${x.open.length}</div><div class="l">Abiertas</div></div><div><div class="v">${x.mon.length}</div><div class="l">En monitoreo</div></div></div>
        <div class="kv num">${x.byState.filter(([s]) => s !== "Open" && s !== "Review" && s !== "Monitor").map(([s, n]) => `<div><span>${esc(estadoTxt(s))}</span><span>${n}</span></div>`).join("")}<div class="tot"><span>Total</span><span>${x.cur.length}</span></div></div>
        <span class="small muted">${x.high} de riesgo alto${x.high ? (x.highOpen ? `, ${x.highOpen} abierta(s)` : ", todas resueltas") : ""}</span>
        <a class="small" href="#excepciones">Ver excepciones</a>
      </section>
      <section class="card"><h2>Integridad de datos</h2>
        <div class="kv num"><div><span>Conciliaciones</span><span>${fmt.int(rc.passed)} / ${fmt.int((rc.passed || 0) + (rc.failed || 0))}</span></div>
          <div><span>Controles PASS</span><span>${fmt.int(dq.PASS)}</span></div><div><span>Advertencias</span><span>${fmt.int(dq.WARNING)}</span></div><div><span>Errores</span><span>${fmt.int(dq.ERROR)}</span></div></div>
        <a class="small" href="#calidad">Ver calidad de datos</a>
      </section>
      ${a.pending.length ? `<section class="card"><h2>Próximos cierres</h2><div class="kv">${a.pending.slice(0, 4).map(p => `<div><span>${esc(p.period)} · ${esc(MODULO[p.source] || p.module)}</span><span class="muted">${esc(F.monthLabel(p.planned_execution))}</span></div>`).join("")}</div></section>` : ""}`;
  }

  /* ======================================================================================
     1. RESUMEN
     ====================================================================================== */
  function renderResumen() {
    const el = document.getElementById("page-resumen");
    const { m } = ccScope(), pm = ccPrev();
    const mv = F.bankRows(D.bank.transactions), pmv = prevScope(D.bank.transactions, "bank");
    const bal = latestBalances(F.bankRows(D.bank.monthly_balances)), balT = bal.reduce((s, b) => s + b.Saldo, 0);
    const isFid = c => (N.find(c) || {}).kind === "fiducuenta";
    const fidT = bal.filter(b => isFid(b.Cuenta)).reduce((s, b) => s + b.Saldo, 0);
    const lastM = bal.map(b => b.Mes).sort().pop();
    const inc = D.bkm("investment_income", mv), pinc = pmv ? D.bkm("investment_income", pmv) : null;
    const a = auditState(), x = excState(D.exceptions), rc = D.meta.reconciliation || {};
    const doneTxt = a.done.length ? `Q${a.done[0].q}${a.done.length > 1 ? "–Q" + a.done[a.done.length - 1].q : ""} ${a.yr} auditados` : `Sin trimestres auditados en ${a.yr}`;
    const prod = puProducts(F.puRows(D.pu.monthly));
    const negs = prod.filter(p => p["Valor neto"] < 0);
    const mvNP = F.bankRows(D.bank.transactions), rows3 = [["Entradas externas", "external_in", 1], ["Salidas externas", "external_out", -1], ["Pagos de tarjetas", "card_payments", -1]];
    // atención: solo lo que pide una decisión o seguimiento
    const att = [];
    x.open.forEach(e => att.push(["Abierta", `${e.ID} · ${e.Concepto || ""}`, `${excProd(e)}${e.Acción ? " · " + short(e.Acción, 110) : ""}`]));
    x.mon.forEach(e => att.push(["Monitoreo", `${e.ID} · ${e.Concepto || ""}`, `${excProd(e)}${num(e["Monto (COP)"]) && e["Monto (COP)"] ? ` · COP ${CP(e["Monto (COP)"])}` : ""}${e.Acción ? " · " + short(e.Acción, 90) : ""}`]));
    negs.sort((p, q) => p["Valor neto"] - q["Valor neto"]).forEach(p => att.push(["Decisión", `${N.name(p.Producto)}: valor neto (${K(-p["Valor neto"])})`, `Costos ${K(p["Costo total"])} · beneficios ${K(p["Beneficios totales"])}.${p.cat.Comentario ? " " + short(p.cat.Comentario, 110) : ""}`]));
    if (m.gross && m.und / m.gross > 0.05) att.push(["Dato", `${pct(m.und / m.gross)} del consumo sin clasificar`, `COP ${M(m.und)} sin naturaleza personal o familiar.`]);
    if ((D.meta.dq_summary || {}).ERROR || rc.failed) att.push(["Datos", "Controles de calidad con error", "Ver Calidad de datos antes de usar las cifras."]);
    // gráfico trimestral por año
    const y = selYear() || CY(), yrs = [y - 1, y].filter(v => D.years.includes(v));
    const txA = F.tcRows(D.cc.transactions, { ignoreYear: true, ignoreQuarter: true });
    const qsum = (yy, q) => D.ccm("gross_spend", txA.filter(r => r.Año === yy && qOf(r) === q));
    // saldo fin de mes (último saldo conocido de cada cuenta)
    const mbA = F.bankRows(D.bank.monthly_balances, { ignoreYear: true, ignoreQuarter: true, ignoreMonth: true });
    const months = D.uniq(mbA.map(r => r.Mes)).sort(), lastBy = {}, series = months.map(mo => { mbA.filter(r => r.Mes === mo).forEach(r => { lastBy[r.Cuenta] = r["Saldo final"]; }); return Object.values(lastBy).reduce((s, v) => s + nz(v), 0); });

    el.innerHTML = `<div class="layout"><div class="col-main">
      <div class="strip"><span><b>${esc(doneTxt)}</b>${a.lastExec ? ` el ${esc(fmt.date(a.lastExec))}` : ""}</span><span>${x.open.length} excepciones abiertas · ${x.mon.length} en monitoreo</span><span>${fmt.int(rc.passed)} de ${fmt.int((rc.passed || 0) + (rc.failed || 0))} conciliaciones OK</span>${a.next ? `<span>Próximo cierre: ${esc(a.next.period)}, ${esc(F.monthLabel(a.next.planned_execution))}</span>` : ""}</div>
      <div class="grid g4">
        ${kpi("Consumo con tarjeta", M(m.gross), `COP · ${esc(scopeLabel())}`, vs(m.gross, pm && pm.gross))}
        ${kpi("Costo neto de tarjetas", M(m.net), "COP · costos financieros − beneficios", `Costos ${M(m.fin)} · beneficios ${M(m.ben)}`)}
        ${kpi("Saldo de efectivo", bal.length ? M(balT) : "—", `COP · al ${esc(F.monthLabel(lastM) || "—")}, ${bal.length} cuenta(s)`, bal.length ? `Fiducuentas ${M(fidT)} · ahorros ${M(balT - fidT)}` : "")}
        ${kpi("Rendimientos e intereses", M(inc), `COP · ${esc(scopeLabel("bank"))}`, vs(inc, pinc, { kind: "bank" }))}
      </div>
      <div class="grid g2">
        ${card("Consumo con tarjeta por trimestre", `${legend(yrs.map(v => ({ label: String(v), color: v === y ? COL.cur : COL.prev })))}<div class="chart-box"><canvas id="ch-r1"></canvas></div>
          <div style="margin-top:12px"><span class="small muted">Naturaleza del consumo · ${esc(scopeLabel())}</span>
          <div class="split" style="margin:6px 0">${m.gross ? [[m.personal, COL.cur], [m.family, COL.fam], [m.und, COL.und]].map(([v, c]) => `<span style="width:${(v / m.gross * 100).toFixed(1)}%;background:${c}"></span>`).join("") : ""}</div>
          <div class="small num" style="display:flex;flex-wrap:wrap;gap:4px 16px">${m.gross ? `<span>Personal ${M(m.personal)} (${pct(m.personal / m.gross)})</span><span>Familiar ${M(m.family)} (${pct(m.family / m.gross)})</span><span>No determinado ${M(m.und)} (${pct(m.und / m.gross)})</span>` : ""}</div></div>`, { unit: "COP" })}
        ${card("Saldo de efectivo a fin de mes", `${legend([{ label: "Año seleccionado", color: COL.cur }, { label: "Años anteriores", color: COL.prev }])}<div class="chart-box"><canvas id="ch-r2"></canvas></div>
          <table class="mini" style="margin-top:12px"><thead><tr><th>Flujos (COP)</th><th class="num">${esc(scopeLabel("bank"))}</th>${pmv ? `<th class="num">${esc(prevLabelFor("bank"))}</th>` : ""}</tr></thead><tbody>
          ${rows3.map(([l, k, sg]) => `<tr><td>${l}</td><td class="num">${M(sg * D.bkm(k, mvNP))}</td>${pmv ? `<td class="num">${M(sg * D.bkm(k, pmv))}</td>` : ""}</tr>`).join("")}</tbody></table>`, { unit: "COP" })}
      </div>
      <div class="grid g2">
        ${card(negs.length ? `Valor neto por producto: ${negs.length} resta${negs.length > 1 ? "n" : ""} valor` : "Valor neto por producto", rankList(prod) + `<p class="note">Total ${K(prod.filter(p => !isFidu(p)).reduce((s, p) => s + p["Valor neto"], 0))}. Sin fiducuentas (no tienen costo de manejo). Gris = el costo supera el beneficio.</p>`, { unit: `COP · ${esc(scopeLabel())}` })}
        ${card("Requiere atención", att.length ? `<div class="att">${att.slice(0, 6).map(([k, t, d]) => `<div><span class="k">${esc(k)}</span><div><div class="t">${esc(t)}</div><div class="x">${esc(d)}</div></div></div>`).join("")}</div>` : `<div class="empty">Nada pendiente en el período.</div>`, { right: `<a class="small" href="#excepciones">Ver excepciones</a>` })}
      </div>
    </div><aside class="rail">${railHTML()}</aside></div>`;
    if (yrs.length) C.bar("ch-r1", ["Q1", "Q2", "Q3", "Q4"], yrs.map(v => ({ label: String(v), data: [1, 2, 3, 4].map(q => qsum(v, q) || null), backgroundColor: v === y ? COL.cur : COL.prev })), { fmt: v => M(v, 1) });
    else C.empty("ch-r1");
    if (months.length) C.bar("ch-r2", months.map(mo => F.monthLabel(mo)), [{ label: "Saldo", data: series, backgroundColor: months.map(mo => Number(mo.slice(0, 4)) === y ? COL.cur : COL.prev) }], { fmt: v => M(v, 1) });
    else C.empty("ch-r2");
  }


  /* ======================================================================================
     0. TESORERÍA (Treasury Control Tower) — lee Metricas_Tesoreria tal como la calcula Excel; no recalcula.
     ====================================================================================== */
  function trPeriod() {
    const ps = (D.tr && D.tr.periods) || [];
    const y = selYear(), q = selQ();
    let cur = null;
    if (y && q) cur = ps.includes(`Q${q}-${y}`) ? `Q${q}-${y}` : null;
    else if (y) cur = ps.filter(p => p.endsWith(String(y))).pop() || null;
    else cur = ps[ps.length - 1] || null;
    const i = ps.indexOf(cur);
    const yoy = cur ? `${cur.slice(0, 3)}${Number(cur.slice(3)) - 1}` : null;
    return { ps, cur, prev: i > 0 ? ps[i - 1] : null, yoy: yoy && ps.includes(yoy) ? yoy : null };
  }
  const trv = (k, p) => { const m = D.tr.metrics[k]; return m && p ? m.values[p] : null; };
  const trUnit = k => (D.tr.metrics[k] || {}).unit || "";
  function trFmt(k, v) {
    if (!num(v)) return v === null || v === undefined ? "—" : esc(v);
    const u = trUnit(k);
    if (/%/.test(u)) return pct(v, /E\.A\./.test(u) ? 2 : 1);
    if (u === "meses") return dec(v, 1);
    if (u === "n°") return fmt.int(v);
    return M(v);
  }
  function trDelta(k, cur, prev, lbl, o = {}) {
    const a = trv(k, cur), b = trv(k, prev);
    if (!num(a) || !num(b) || !prev) return "";
    if (/%|meses/.test(trUnit(k))) { const d = a - b; return `${d >= 0 ? "+" : "−"}${/%/.test(trUnit(k)) ? dec(d * 100, 1) + " pp" : dec(d, 1) + " meses"} vs ${esc(lbl)}`; }
    return b ? `${fmt.signedPct(a / Math.abs(b) - (b < 0 ? -1 : 1))} vs ${esc(lbl)}` : `vs ${M(b)} en ${esc(lbl)}`;
  }
  function renderTesoreria() {
    const el = document.getElementById("page-tesoreria");
    if (!D.tr || !D.tr.metadata || !D.tr.metadata.available) {
      el.innerHTML = `<div class="banner warn">No hay datos de tesorería. Agregue las hojas Tesoreria_Input y Metricas_Tesoreria al libro de tarjetas, guárdelo en Excel y ejecute el refresh.</div>`; return;
    }
    const { ps, cur, prev, yoy } = trPeriod();
    if (!cur) { el.innerHTML = `<div class="empty">Metricas_Tesoreria no tiene columna para el período seleccionado. Períodos disponibles: ${esc(ps.join(", "))}.</div>`; return; }
    const v = k => trv(k, cur), P = D.tr.metadata.params || {};
    const reserveM = P.reserve_months, opBal = P.operating_balance;
    const gap = v("reserve_gap"), util = v("cc_util"), runway = v("runway");
    const chk = v("chk_status");
    const cmpCols = [cur, prev, yoy].filter(Boolean);
    const cmpHead = `<th></th>${cmpCols.map(p => `<th class="num">${esc(p)}</th>`).join("")}`;
    const tbl = keys => `<table class="mini"><thead><tr>${cmpHead}</tr></thead><tbody>${keys.map(k => `<tr><td>${esc((D.tr.metrics[k] || {}).label || k)}${src((D.tr.metrics[k] || {}).definition)}</td>${cmpCols.map(p => `<td class="num">${trFmt(k, trv(k, p))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    // líneas de crédito
    const fac = (D.tr.facilities || []).filter(f => f["Estado maestro"] === "Activa");
    const facClosed = (D.tr.facilities || []).filter(f => f["Estado maestro"] !== "Activa");
    const facName = f => N.find(f["Producto en base"] || "") ? N.name(f["Producto en base"]) : (N.find(f.Tarjeta || "") ? N.name(f.Tarjeta) : `${f.Banco} ${f.Plan || ""}`.trim());
    const facRows = list => list.map(f => `<tr><td>${esc(facName(f))} <span class="ref-s">${esc(f.Tarjeta || "")}</span></td><td class="num">${M(f["Cupo (maestro)"])}</td>
      <td class="num">${num(f["Saldo último corte"]) ? M(f["Saldo último corte"]) : "—"}</td><td class="num">${num(f["Utilización último corte"]) ? pct(f["Utilización último corte"]) : "—"}</td>
      <td class="num">${num(f["Días corte → pago"]) ? fmt.int(f["Días corte → pago"]) : "—"}</td><td class="num">${num(f["Plazo sin intereses máx. (días)"]) ? fmt.int(f["Plazo sin intereses máx. (días)"]) : "—"}</td>
      <td class="num">${num(f["Saldo máximo recomendado (30%)"]) ? M(f["Saldo máximo recomendado (30%)"]) : "—"}</td><td class="num">${num(f["Margen hasta 30%"]) ? M(f["Margen hasta 30%"]) : "—"}</td>
      <td class="num">${num(f["Tasa E.A."]) ? pct(f["Tasa E.A."], 1) : "—"}</td><td class="num">${M(f["Cuota de manejo actual"])}</td></tr>`).join("");
    const facHead = `<thead><tr><th>Tarjeta</th><th class="num">Cupo (maestro)</th><th class="num">Saldo último corte</th><th class="num">Utilización</th><th class="num">Días corte → pago</th><th class="num">Plazo máx. sin intereses</th><th class="num">Saldo máx. 30%</th><th class="num">Margen hasta 30%</th><th class="num">Tasa E.A.</th><th class="num">Cuota de manejo</th></tr></thead>`;
    const noStmt = fac.filter(f => !num(f["Saldo último corte"]));
    // atención (solo lectura de las métricas)
    const att = [];
    if (num(gap) && gap < 0) att.push(["Liquidez", `Déficit frente a la reserva de ${fmt.int(reserveM)} meses: (${M(-gap)})`, `Cobertura de ${dec(runway, 1)} meses con el gasto promedio de los últimos 4 trimestres.`]);
    if (num(v("cp_over_cap")) && v("cp_over_cap") > 0) att.push(["Contraparte", `${M(v("cp_over_cap"))} en ahorros por encima del tope Fogafín`, "El seguro de depósitos cubre hasta el tope por persona y entidad."]);
    if (num(v("idle_close")) && v("idle_close") > 0) att.push(["Rendimiento", `Caja ociosa en ahorros al cierre: ${M(v("idle_close"))}`, `Saldo sobre el operativo de ${M(opBal)}. Costo de oportunidad estimado del trimestre: ${M(v("opp_cost"))}.`]);
    if (num(v("cc_interest")) && v("cc_interest") > 0) att.push(["Tarjetas", `Intereses de tarjetas pagados: ${M(v("cc_interest"))}`, "Meta: 0. Revise la excepción del trimestre."]);
    if (num(v("cc_room_max")) && v("cc_room_max") < 0) att.push(["Tarjetas", `Utilización agregada ${pct(util)}: por encima del máximo de ${pct(v("cc_util_limit"), 0)}`, `Reduzca el saldo al corte en ${M(-v("cc_room_max"))} o páguelo antes de la fecha de corte; el saldo reportado es el del corte.`]);
    else if (num(v("cc_room_ideal")) && v("cc_room_ideal") < 0) att.push(["Tarjetas", `Utilización agregada ${pct(util)}: sobre la meta de ${pct(v("cc_util_ideal"), 0)}`, `Dentro del máximo de ${pct(v("cc_util_limit"), 0)}. Exceso sobre la meta: ${M(-v("cc_room_ideal"))}.`]);
    if (num(v("cc_over")) && v("cc_over") > 0) att.push(["Tarjetas", `${fmt.int(v("cc_over"))} corte(s) sobre el umbral de utilización (${pct(P.utilization_threshold, 0)})`, `Utilización máxima de un corte: ${pct(v("cc_util_max"))}.`]);
    if (noStmt.length) att.push(["Datos", `${noStmt.length} tarjeta(s) activa(s) sin extracto en el sistema`, noStmt.map(facName).join(", ") + ". Su saldo no entra en la deuda ni en la utilización."]);
    if (chk && chk !== "OK") att.push(["Datos", `Controles de Metricas_Tesoreria: ${chk}`, "Revise que el trimestre tenga 3 meses en Tesoreria_Input y columna en Historico_Trimestral."]);

    el.innerHTML = `<div class="stack">
      <div class="strip"><span><b>Cierre ${esc(cur)}</b></span><span>Reserva objetivo: ${fmt.int(reserveM)} meses de gasto</span><span>Saldo operativo en ahorros: ${M(opBal)}</span>
        <span>Controles de la hoja: ${esc(chk || "—")}</span><span>${fmt.int((D.meta.reconciliation || {}).passed)} conciliaciones OK (incluye insumos de tesorería)</span></div>
      <div class="grid g5">
        ${kpi("Liquidez total", M(v("liq_total")), "COP · ahorros + fiducuentas", trDelta("liq_total", cur, prev, prev), { tip: (D.tr.metrics.liq_total || {}).definition })}
        ${kpi("Posición neta de caja", M(v("net_cash")), "COP · liquidez − deuda de tarjetas", `Deuda de tarjetas ${M(v("cc_debt"))}`, { tip: (D.tr.metrics.net_cash || {}).definition })}
        ${kpi("Meses de cobertura", num(runway) ? dec(runway, 1) : "—", `meses · objetivo ${fmt.int(reserveM)}`, num(gap) ? (gap >= 0 ? `Exceso ${M(gap)} sobre la reserva` : `Déficit (${M(-gap)}) frente a la reserva`) : "", { alert: num(gap) && gap < 0, tip: (D.tr.metrics.runway || {}).definition })}
        ${kpi("Utilización de cupo", num(util) ? pct(util) : "—", `deuda ÷ cupo · máximo ${pct(v("cc_util_limit"), 0)}, ideal ${pct(v("cc_util_ideal"), 0)}`, num(v("cc_room_max")) ? (v("cc_room_max") >= 0 ? `Margen hasta ${pct(v("cc_util_limit"), 0)}: ${M(v("cc_room_max"))}` : `Exceso sobre ${pct(v("cc_util_limit"), 0)}: (${M(-v("cc_room_max"))})`) : "", { alert: num(util) && num(v("cc_util_limit")) && util > v("cc_util_limit"), tip: (D.tr.metrics.cc_util_limit || {}).definition })}
        ${kpi("Costo bancario", M(v("cost_total")), "COP · trimestre", num(v("cost_pct")) ? `${pct(v("cost_pct"), 2)} del gasto · ${trDelta("cost_total", cur, prev, prev) || ""}` : "", { tip: (D.tr.metrics.cost_total || {}).definition })}
      </div>
      <div class="grid g2">
        ${card("Liquidez por cuenta a fin de mes", `<div id="tr-leg1"></div><div class="chart-box"><canvas id="ch-tr1"></canvas></div>`, { unit: "COP" })}
        ${card("Liquidez, deuda de tarjetas y reserva objetivo", `${legend([{ label: "Liquidez total", color: COL.cur }, { label: "Deuda de tarjetas", color: COL.prev }, { label: "Reserva objetivo", color: COL.line, line: true }])}<div class="chart-box"><canvas id="ch-tr2"></canvas></div>`, { unit: "COP · cierre de trimestre" })}
      </div>
      <div class="grid g2">
        ${card("Costo bancario por trimestre", `${legend([{ label: "Cuotas de manejo", color: COL.cur }, { label: "Seguros", color: COL.fam }, { label: "Intereses", color: COL.line }, { label: "GMF 4x1000", color: COL.und }])}<div class="chart-box"><canvas id="ch-tr3"></canvas></div>`, { unit: "COP", note: `Retención en la fuente sobre rendimientos del trimestre: ${M(v("tax_wht"))} (anticipo de renta; no se suma al costo).` })}
        ${card("Requiere atención", att.length ? `<div class="att">${att.map(([k, t, d]) => `<div><span class="k">${esc(k)}</span><div><div class="t">${esc(t)}</div><div class="x">${esc(d)}</div></div></div>`).join("")}</div>` : `<div class="empty">Sin alertas de tesorería en el período.</div>`)}
      </div>
      <div class="grid g2">
        ${card("Rendimiento de la caja", tbl(["yld_income", "yld_avg_bal", "yld_ea", "yld_fidu_ea", "yld_ref", "idle_close", "opp_cost"]), { note: "Costo de oportunidad: estimación con metodología propuesta (saldo ocioso × diferencial de tasas fiducuenta vs ahorros); no es un costo contable." })}
        ${card("Contraparte y seguro de depósitos", tbl(["cp_insured", "cp_over_cap", "cp_fic", "cp_insured_pct", "cp_group_pct", "cxc_bal"]), { note: `Tope Fogafín por persona y entidad: ${M(P.deposit_insurance_cap)}. Las fiducuentas (fondos de inversión colectiva) no tienen seguro de depósitos.` })}
      </div>
      ${card("Líneas de crédito (tarjetas activas)", `<table class="mini">${facHead}<tbody>${facRows(fac)}<tr><td><b>Total</b></td><td class="num"><b>${M(D.sum(fac, "Cupo (maestro)"))}</b></td><td class="num"><b>${M(D.sum(fac, "Saldo último corte"))}</b></td><td colspan="7"></td></tr></tbody></table>`,
        { unit: "COP", note: "Saldo y utilización del último corte COP hasta el cierre auditado (cupo del extracto). Saldo máx. 30% = cupo × 30% (guía de DataCrédito Experian; aplica por tarjeta y en total, sobre el saldo reportado al corte). Plazo máx. sin intereses = 30 días + días entre corte y pago (aproximación). Cupo y tasas según el maestro." })}
      ${more("Todas las métricas de tesorería", `<div id="tr-all"></div>`, { meta: `${Object.keys(D.tr.metrics).length} indicadores · ${ps.length} trimestres` })}
      ${more("Tarjetas cerradas o canceladas", `<table class="mini">${facHead}<tbody>${facRows(facClosed)}</tbody></table>`, { pad: true, meta: `${facClosed.length}` })}
      ${more("Insumos mensuales (Tesoreria_Input)", `<div id="tr-in"></div>`, { meta: `${D.tr.monthly.length} meses · conciliados contra el libro de bancos` })}
    </div>`;

    // gráfico 1: liquidez por cuenta (mensual, apilado)
    const mo = D.tr.monthly.filter(r => !selYear() || r.Año <= selYear());
    const series = [["savings", "Ahorros *9910", COL.cur], ["fidu_6191", "Fiducuenta *6191", COL.fam], ["fidu_0934", "Fiducuenta *0934", "#a7a7a2"], ["fidu_0452", "Fiducuenta *0452", COL.und]];
    if (mo.length) {
      C.bar("ch-tr1", mo.map(r => F.monthLabel(r.Mes)), series.map(([k, l, c]) => ({ label: l, data: mo.map(r => r[k] || null), backgroundColor: c })), { stacked: true, fmt: v => M(v) });
      document.getElementById("tr-leg1").innerHTML = legend(series.map(([, l, c]) => ({ label: l, color: c })));
    } else C.empty("ch-tr1");
    // gráfico 2: trimestral
    const qp = ps.filter(p => ps.indexOf(p) <= ps.indexOf(cur));
    C.combo("ch-tr2", qp, [{ label: "Liquidez total", data: qp.map(p => trv("liq_total", p)), backgroundColor: qp.map(p => p === cur ? COL.cur : COL.fam) },
      { label: "Deuda de tarjetas", data: qp.map(p => trv("cc_debt", p)), backgroundColor: COL.prev }],
      [{ label: "Reserva objetivo", data: qp.map(p => trv("reserve_target", p)), borderColor: COL.line, backgroundColor: COL.line }], { fmt: v => M(v) });
    // gráfico 3: costo bancario
    C.bar("ch-tr3", qp, [["cost_fees", "Cuotas de manejo", COL.cur], ["cost_ins", "Seguros", COL.fam], ["cost_int", "Intereses", COL.line], ["cost_gmf", "GMF 4x1000", COL.und]]
      .map(([k, l, c]) => ({ label: l, data: qp.map(p => trv(k, p) || 0), backgroundColor: c })), { stacked: true, fmt: v => M(v) });
    // matriz completa
    const keys = Object.keys(D.tr.metrics);
    let lastSec = null;
    document.getElementById("tr-all").innerHTML = `<div class="body" style="overflow-x:auto"><table class="mini"><thead><tr><th>Indicador</th>${ps.map(p => `<th class="num" ${p === cur ? 'style="color:var(--accent)"' : ""}>${esc(p)}</th>`).join("")}</tr></thead><tbody>${keys.map(k => {
      const m = D.tr.metrics[k]; let h = "";
      if (m.section !== lastSec) { lastSec = m.section; h = `<tr><td colspan="${ps.length + 1}"><b>${esc(m.section || "")}</b></td></tr>`; }
      return h + `<tr><td>${esc(m.label)}${src(m.definition)}</td>${ps.map(p => `<td class="num">${trFmt(k, m.values[p])}</td>`).join("")}</tr>`;
    }).join("")}</tbody></table></div>`;
    T.render("tr-in", { rows: D.tr.monthly.slice().reverse(), pageSize: 24, columns: [{ key: "Mes", label: "Mes", fmt: x => F.monthLabel(x) },
      { key: "savings", label: "Ahorros *9910", num: true, fmt: CP }, { key: "fidu_6191", label: "Fid. *6191", num: true, fmt: CP }, { key: "fidu_0934", label: "Fid. *0934", num: true, fmt: CP },
      { key: "fidu_0452", label: "Fid. *0452", num: true, fmt: CP }, { key: "liquidity", label: "Liquidez", num: true, fmt: CP }, { key: "external_spend", label: "Gasto externo", num: true, fmt: CP },
      { key: "gmf", label: "GMF", num: true, fmt: CP }, { key: "savings_interest", label: "Intereses", num: true, fmt: CP }, { key: "fidu_yield", label: "Rend. netos", num: true, fmt: CP },
      { key: "withholding", label: "Retención", num: true, fmt: CP }, { key: "fidu_rate", label: "Fiducuenta E.A.", num: true, fmt: x => pct(x, 2) }] });
  }

  /* comparativo interanual leído de las matrices históricas del libro (sin recalcular) */
  function renderYoY(hostId, only) {
    const host = document.getElementById(hostId); if (!host) return;
    const blocks = [];
    const build = (hist, rowsWanted) => {
      const per = hist.periods || [];
      const ys = D.uniq(per.map(p => Number(p.slice(3)))).sort();
      if (ys.length < 2) return;
      const yB = selYear() && ys.includes(selYear()) ? selYear() : ys[ys.length - 1], yA = yB - 1;
      if (!ys.includes(yA)) return;
      const qList = [1, 2, 3, 4].filter(q => (!selQ() || q === selQ()) && per.includes(`Q${q}-${yB}`) && per.includes(`Q${q}-${yA}`));
      if (!qList.length) return;
      const head = `<tr><th>COP</th>${qList.map(q => `<th class="n">Q${q}-${yA}</th><th class="n">Q${q}-${yB}</th>`).join("")}<th class="n">${yA}</th><th class="n">${yB}</th><th class="n">Var.</th></tr>`;
      const body = rowsWanted.filter(r => hist.rows[r[0]]).map(([key, label, isInt]) => {
        const row = hist.rows[key]; let sA = 0, sB = 0;
        const f = v => isInt ? fmt.int(v) : M(v);
        const cells = qList.map(q => { const a = row[`Q${q}-${yA}`], b = row[`Q${q}-${yB}`]; sA += nz(a); sB += nz(b); return `<td class="n">${f(a)}</td><td class="n">${f(b)}</td>`; }).join("");
        return `<tr><td>${esc(label)}</td>${cells}<td class="n">${f(sA)}</td><td class="n">${f(sB)}</td><td class="n">${sA ? fmt.signedPct(sB / sA - 1) : "—"}</td></tr>`;
      }).join("");
      blocks.push(`<div class="tbl-wrap"><table class="t"><thead>${head}</thead><tbody>${body}</tbody></table></div>`);
    };
    if (only === "tc") build(D.cc.historico_trimestral, [["Consumo bruto", "Consumo"], ["Número de compras", "Número de compras", true], ["Personal estimado", "Personal"], ["Familiar atribuible", "Familiar"],
      ["No determinado", "No determinado"], ["Cuotas de manejo", "Cuotas de manejo"], ["Seguros", "Seguros"], ["Intereses", "Intereses"], ["Beneficios verificados", "Beneficios"], ["Costo neto", "Costo neto"]]);
    if (only === "bank") build(D.bank.historico_trimestral, [["Gross entradas — *9910", "Entradas brutas (ahorros)"], ["Gross salidas — *9910", "Salidas brutas (ahorros)"], ["Transferencias internas — salidas", "Transferencias internas"],
      ["Pagos de tarjeta de crédito", "Pagos de tarjetas"], ["Inversión (capital) — salidas", "Inversión — aportes"], ["Inversión (capital) — entradas", "Inversión — retiros"],
      ["Ingreso de inversión (intereses y rendimientos)", "Rendimientos e intereses"], ["Gastos externos", "Gastos externos"], ["Movimientos ≥ 1M (n°)", "Movimientos ≥ 1 M (n.º)", true]]);
    host.innerHTML = blocks.join("") || `<div class="empty">Se necesitan dos años con el mismo trimestre para comparar.</div>`;
  }

  /* ---------- excepciones: columnas y detalle ---------- */
  function excCols(o = {}) {
    const cols = [
      { key: "ID", label: "ID" },
      { key: "Riesgo", label: "Riesgo", html: riskTxt, sortValue: r => r.risk_rank },
      { key: "Trimestre", label: "Período", fmt: (v, r) => `${v ? v + " " : ""}${r.Año || ""}`.trim() },
      { key: "Source", label: "Módulo", fmt: v => MODULO[v] || v },
      { key: "Cuenta/Tarjeta", label: "Producto", cls: "clip", tip: r => excProd(r), fmt: (v, r) => excProd(r), text: r => excProd(r) + " " + (r["Cuenta/Tarjeta"] || "") },
      { key: "Concepto", label: "Concepto", cls: "clip", tip: r => r.Concepto },
      { key: "Monto (COP)", label: "Monto", num: true, fmt: v => num(v) && v !== 0 ? CP(v) : "" },
      { key: "Estado", label: "Estado", html: statusPill },
      { key: "Estado anterior", label: "Antes", html: r => r["Estado anterior"] && r["Estado anterior"] !== r.Estado ? `<span class="muted small">${esc(estadoTxt(r["Estado anterior"]))}</span>` : "" }
    ];
    return o.noSource ? cols.filter(c => c.key !== "Source") : cols;
  }
  function excDetail(e) {
    const f = [["Origen", e.Origen], ["Fecha", e.Fecha], ["Banco", e.Banco], ["Producto (libro)", e.Producto], ["Cuenta / tarjeta (libro)", e["Cuenta/Tarjeta"]], ["Categoría", e.Categoría], ["Tipo", e.Tipo], ["Tipo de monto", e["Tipo de monto"]], ["Money Pro", e["Money Pro"]], ["Splitwise", e.Splitwise],
      ["Conclusión de auditoría", e["Conclusión de auditoría"]], ["Evidencia nueva", e["Evidencia nueva"]], ["Estado anterior", e["Estado anterior"] ? estadoTxt(e["Estado anterior"]) : null],
      ["Explicación", e.Explicación], ["Acción", e.Acción], ["Evidencia", e.Evidencia], ["Referencia", e.Referencia], ["Detectada", e["Fecha detección"]], ["Último cambio", e["Fecha último cambio"]],
      ["Comentario de cierre", e["Comentario de cierre"]], ["Comentario (registro bancos)", e["Comentario (registro bancos)"]], ["Estado original", e["Estado original"]], ["Hallazgo relacionado", e["Hallazgo relacionado"]],
      ["Continuidad", e.continuity ? `${e.continuity.category || ""} — ${e.continuity.rule || ""}` : null], [`Estado ${(e.continuity && e.continuity.latest_year) || ""}`, e.continuity && e.continuity.latest_status],
      ["Excepción nueva vinculada", e.continuity && e.continuity.linked], ["Registrada en", (e.present_in || []).join(" · ")]];
    return `<div class="detail-grid">${f.filter(x => x[1] !== null && x[1] !== undefined && x[1] !== "").map(x => `<b>${esc(x[0])}</b><span>${esc(x[1])}</span>`).join("")}</div>`;
  }
  function excTable(host, rows, o = {}) {
    T.render(host, { rows: D.sortExceptions(rows), columns: excCols(o).concat(o.extra || []), rowId: r => r.ID, detail: excDetail, search: !!o.search, pageSize: o.pageSize || 0,
      rowClass: r => (r.is_historical ? "hist " : "") + (r.is_open && r.Riesgo === "HIGH" ? "row-alert" : ""), resetPage: true });
  }

  /* ======================================================================================
     2. TARJETAS DE CRÉDITO
     ====================================================================================== */
  function renderTarjetas() {
    const el = document.getElementById("page-tarjetas");
    const { tx, st, bn, m } = ccScope(), pm = ccPrev();
    const excs = F.excRows(D.exceptions, { source: "Credit Card" });
    const cur = excs.filter(e => !e.is_historical), hist = F.excRows(D.exceptions, { source: "Credit Card", ignoreYear: true, ignoreQuarter: true }).filter(e => e.is_historical);
    F.note(F.get("category") ? "La categoría filtra consumo y transacciones; cuotas, seguros, intereses y beneficios no se filtran por categoría." : "");
    const measures = [["gross_spend", "Consumo"], ["personal", "Personal"], ["family", "Familiar"], ["undetermined", "No determinado"], ["fees", "Cuotas"], ["insurance", "Seguros"], ["interest", "Intereses"], ["benefits", "Beneficios"]];
    const sum = F.tcRows(D.cc.card_summary, { ignoreCategory: true });
    el.innerHTML = `<div class="stack">
      <div class="grid g5">
        ${kpi("Consumo", M(m.gross), `COP · ${fmt.int(m.purchases)} compras`, vs(m.gross, pm && pm.gross))}
        ${kpi("Costos financieros", M(m.fin), "COP · cuotas, seguros e intereses", `Cuotas ${M(m.fees)} · seguros ${M(m.ins)} · intereses ${M(m.intr)}`)}
        ${kpi("Beneficios", M(m.ben), "COP · según extractos", vs(m.ben, pm && pm.ben))}
        ${kpi("Costo neto", M(m.net), "COP · costos − beneficios", pm ? `${M(pm.net)} en ${esc(prevLabelFor())}` : "")}
        ${kpi("Consumo sin clasificar", m.gross ? pct(m.und / m.gross) : "—", `del consumo · COP ${M(m.und)}`, "Ni personal ni familiar")}
      </div>
      <div class="grid g2">
        ${card("Consumo por tarjeta", `${legend([{ label: "Personal", color: COL.cur }, { label: "Familiar", color: COL.fam }, { label: "No determinado", color: COL.und }])}<div class="chart-box tall"><canvas id="ch-t1"></canvas></div>`, { unit: "COP" })}
        ${card("Compras por categoría", `<div class="chart-box tall"><canvas id="ch-t2"></canvas></div>`, { unit: "COP" })}
      </div>
      ${card("Tendencia trimestral", `<div class="chart-box"><canvas id="ch-t3"></canvas></div>`, { unit: "COP", right: `<div class="seg">${measures.map(([k, l]) => `<button type="button" data-ccm="${k}" aria-pressed="${ui.ccMeasure === k}">${l}</button>`).join("")}</div>` })}
      ${card("Resumen por tarjeta y trimestre", `<div id="t-sum"></div>`, { flush: true, unit: "COP" })}
      ${more("Comparativo con el año anterior", `<div id="t-cmp"></div>`)}
      ${more("Extractos", `<div id="t-st"></div>`, { meta: `${st.length} extractos` })}
      ${more("Beneficios por mes", `<div id="t-bn"></div>`, { meta: `${bn.length} registros` })}
      ${more("Transacciones", `<div id="t-tx"></div>`, { meta: `${fmt.int(tx.length)} registros` })}
      ${more("Excepciones de tarjetas", `<div class="group-h body" style="margin:0;padding:12px 18px 0">Año en curso</div><div id="t-exc"></div><div class="group-h body" style="margin:0;padding:12px 18px 0">Hallazgos de años anteriores</div><div id="t-hist"></div>`, { meta: `${cur.length} actuales · ${cur.filter(e => e.is_open).length} abiertas` })}
    </div>`;
    el.querySelectorAll("[data-ccm]").forEach(b => b.addEventListener("click", () => { ui.ccMeasure = b.dataset.ccm; renderTarjetas(); }));
    const prods = D.uniq(tx.map(t => t.Producto));
    const rowsP = prods.map(p => { const r = tx.filter(t => t.Producto === p); return { p, per: D.ccm("personal", r), fam: D.ccm("family", r), und: D.ccm("undetermined", r) }; })
      .filter(r => r.per + r.fam + r.und).sort((a, b) => (b.per + b.fam + b.und) - (a.per + a.fam + a.und));
    const f1 = v => M(v, 1);
    if (rowsP.length) C.bar("ch-t1", rowsP.map(r => N.name(r.p)), [{ label: "Personal", data: rowsP.map(r => r.per), backgroundColor: COL.cur },
      { label: "Familiar", data: rowsP.map(r => r.fam), backgroundColor: COL.fam }, { label: "No determinado", data: rowsP.map(r => r.und), backgroundColor: COL.und }], { stacked: true, horizontal: true, fmt: f1 });
    else C.empty("ch-t1");
    const buys = tx.filter(t => D.matches(t, D.ccDefs.gross_spend.where));
    const cats = [...D.groupBy(buys, t => t.Categoría || "Sin categoría")].map(([c, r]) => [c, D.sum(r, "Valor COP")]).sort((a, b) => b[1] - a[1]).slice(0, 12);
    if (cats.length) C.bar("ch-t2", cats.map(c => c[0]), [{ label: "Compras", data: cats.map(c => c[1]), backgroundColor: COL.cur }], { horizontal: true, fmt: f1 }); else C.empty("ch-t2");
    const txA = F.tcRows(D.cc.transactions, { ignoreYear: true, ignoreQuarter: true }), stA = F.tcRows(D.cc.statements, { ignoreYear: true, ignoreQuarter: true, ignoreCategory: true }), bnA = F.tcRows(D.cc.benefits, { ignoreYear: true, ignoreQuarter: true, ignoreCategory: true });
    const ks = D.uniq(txA.map(t => t.Año * 10 + t.Trimestre)).sort((a, b) => a - b);
    const srcFor = k => k === "interest" ? stA : k === "benefits" ? bnA : txA;
    const small = ["fees", "insurance", "interest", "benefits"].includes(ui.ccMeasure);
    if (ks.length) C.bar("ch-t3", ks.map(k => `Q${k % 10}-${Math.floor(k / 10)}`), [{ label: measures.find(x => x[0] === ui.ccMeasure)[1], data: ks.map(k => D.ccm(ui.ccMeasure, srcFor(ui.ccMeasure).filter(r => r.Año * 10 + qOf(r) === k))),
      backgroundColor: ks.map(k => (selYear() && Math.floor(k / 10) !== selYear()) ? COL.prev : COL.cur) }], { fmt: v => small ? M(v, 3) : M(v, 1) });
    else C.empty("ch-t3");
    T.render("t-sum", { rows: sum, search: true, pageSize: 20, sort: { key: "gross_spend", dir: "desc" },
      columns: [{ key: "Trimestre", label: "Período", fmt: (v, r) => `Q${v}-${r.Año}`, sortValue: r => r.Año * 10 + r.Trimestre }, { key: "Producto", label: "Tarjeta", html: r => nmRef(r.Producto), text: r => N.full(r.Producto) },
        { key: "gross_spend", label: "Consumo", num: true, fmt: CP }, { key: "purchases", label: "Compras", num: true, fmt: fmt.int }, { key: "personal", label: "Personal", num: true, fmt: CP },
        { key: "family", label: "Familiar", num: true, fmt: CP }, { key: "undetermined", label: "No det.", num: true, fmt: CP }, { key: "fees", label: "Cuotas", num: true, fmt: CP },
        { key: "insurance", label: "Seguros", num: true, fmt: CP }, { key: "interest", label: "Intereses", num: true, fmt: CP }, { key: "benefits", label: "Beneficios", num: true, fmt: CP },
        { key: "net_cost", label: "Costo neto", num: true, fmt: CP }, { key: "max_utilization", label: "Uso máx. cupo", num: true, fmt: v => pct(v) }],
      totals: (c, rows) => c.num && c.key !== "max_utilization" ? (c.key === "purchases" ? fmt.int(D.sum(rows, c.key)) : CP(D.sum(rows, c.key))) : c.key === "Trimestre" ? "Total" : "" });
    renderYoY("t-cmp", "tc");
    excTable("t-exc", cur, { noSource: true });
    excTable("t-hist", hist, { noSource: true, extra: [{ key: "cat", label: "Continuidad", html: r => catTxt(catCode(r)), sortValue: r => catCode(r) }] });
    T.render("t-st", { rows: st, search: true, pageSize: 20, sort: { key: "Fecha corte", dir: "desc" }, columns: [{ key: "Fecha corte", label: "Corte", fmt: fmt.date }, { key: "Producto", label: "Tarjeta", html: r => nmRef(r.Producto), text: r => N.full(r.Producto) }, { key: "Moneda", label: "Moneda" },
      { key: "Saldo anterior", label: "Saldo anterior", num: true, fmt: fmt.cop2 }, { key: "Compras / cargos", label: "Compras / cargos", num: true, fmt: fmt.cop2 }, { key: "Pagos y abonos", label: "Pagos", num: true, fmt: fmt.cop2 },
      { key: "Intereses corrientes", label: "Int. corrientes", num: true, fmt: fmt.cop2 }, { key: "Intereses mora", label: "Int. mora", num: true, fmt: fmt.cop2 }, { key: "Nuevo saldo", label: "Nuevo saldo", num: true, fmt: fmt.cop2 },
      { key: "Cupo", label: "Cupo", num: true, fmt: CP }, { key: "Utilización", label: "Uso cupo", num: true, fmt: v => pct(v) }, { key: "Resultado", label: "Resultado", html: r => pill(r.Resultado || "—", r.Resultado === "OK" ? "ok" : "low") }] });
    T.render("t-bn", { rows: bn, pageSize: 20, columns: [{ key: "Mes", label: "Mes", fmt: v => F.monthLabel(v) }, { key: "Producto", label: "Tarjeta", html: r => nmRef(r.Producto) }, { key: "Beneficio según extracto", label: "Según extracto", num: true, fmt: fmt.cop2 },
      { key: "Redimido / abonado según extracto", label: "Redimido", num: true, fmt: fmt.cop2 }, { key: "Beneficio según Money Pro", label: "Money Pro", num: true, fmt: fmt.cop2 },
      { key: "Beneficio esperado (maestro)", label: "Esperado", num: true, fmt: fmt.cop2 }, { key: "Diferencia recibido vs esperado", label: "Dif. vs esperado", num: true, fmt: fmt.cop2 }, { key: "Nota", label: "Nota", cls: "wrap" }],
      totals: (c, rows) => c.num ? fmt.cop2(D.sum(rows, c.key)) : c.key === "Mes" ? "Total" : "" });
    T.render("t-tx", { rows: tx, search: true, pageSize: 25, sort: { key: "Fecha", dir: "desc" }, rowId: r => r.TxnID,
      detail: r => `<div class="detail-grid">${["TxnID", "Producto", "Descripción", "Autorización", "Cuotas", "Moneda", "Valor original", "Internacional", "Estado Money Pro", "Fuente categoría", "MP ID", "SW ID", "SW descripción", "Archivo extracto"].filter(k => r[k] !== null && r[k] !== undefined && r[k] !== "").map(k => `<b>${esc(k)}</b><span>${esc(r[k])}</span>`).join("")}</div>`,
      columns: [{ key: "Fecha", label: "Fecha", fmt: fmt.date }, { key: "Producto", label: "Tarjeta", html: r => nm(r.Producto), text: r => N.full(r.Producto) }, { key: "Comercio normalizado", label: "Comercio", cls: "clip", tip: r => r["Comercio normalizado"] },
        { key: "Valor COP", label: "Valor", num: true, fmt: CP }, { key: "Tipo de movimiento", label: "Tipo" }, { key: "Categoría", label: "Categoría" }, { key: "Naturaleza", label: "Naturaleza" },
        { key: "Excepción", label: "Excepción", html: r => r.Excepción ? `<span class="chip warn">${esc(r.Excepción)}</span>` : "" }] });
  }

  /* ======================================================================================
     3. BANCOS Y EFECTIVO
     ====================================================================================== */
  function renderBancos() {
    const el = document.getElementById("page-bancos");
    const mv = F.bankRows(D.bank.transactions), mvNF = F.bankRows(D.bank.transactions, { ignoreFlow: true });
    const pmv = prevScope(D.bank.transactions, "bank");
    const b = k => D.bkm(k, mvNF), pb = k => pmv ? D.bkm(k, pmv) : null;
    const bal = latestBalances(F.bankRows(D.bank.monthly_balances)), balT = bal.reduce((s, x) => s + x.Saldo, 0);
    const lastM = bal.map(x => x.Mes).sort().pop();
    const excs = F.excRows(D.exceptions, { source: "Bank & Cash" });
    const cur = excs.filter(e => !e.is_historical), hist = F.excRows(D.exceptions, { source: "Bank & Cash", ignoreYear: true, ignoreQuarter: true }).filter(e => e.is_historical);
    F.note(F.get("flow") ? "El tipo de flujo filtra el gráfico mensual y la tabla de movimientos; los indicadores muestran todos los flujos." : "");
    const netExt = b("external_in") - b("external_out"), pNet = pmv ? pb("external_in") - pb("external_out") : null;
    const capRows = [["Ahorros → fiducuentas (transferencias internas)", "internal_out"], ["Fiducuentas → ahorros", "internal_in"], ["Aportes a inversión", "investment_out"], ["Retiros de inversión", "investment_in"]];
    el.innerHTML = `<div class="stack">
      <div class="grid g5">
        ${kpi("Saldo de efectivo", bal.length ? M(balT) : "—", `COP · al ${esc(F.monthLabel(lastM) || "—")}`, `${bal.length} cuenta(s)`)}
        ${kpi("Flujo externo neto", M(netExt), "COP · entradas − salidas externas", `Entradas ${M(b("external_in"))} · salidas ${M(b("external_out"))}`)}
        ${kpi("Pagos de tarjetas", M(b("card_payments")), "COP", vs(b("card_payments"), pb("card_payments"), { kind: "bank" }))}
        ${kpi("Rendimientos e intereses", M(b("investment_income")), "COP", vs(b("investment_income"), pb("investment_income"), { kind: "bank" }))}
        ${kpi("Movimientos ≥ 1 M", fmt.int(b("material_count")), "revisados uno a uno", `${fmt.int(b("unmatched"))} sin conciliar`)}
      </div>
      <div class="grid g2">
        ${card("Flujo mensual", `${legend([{ label: "Entradas externas", color: COL.cur }, { label: "Salidas externas", color: COL.fam }, { label: "Pagos de tarjetas", color: COL.line, line: true }])}<div class="chart-box"><canvas id="ch-b1"></canvas></div>`, { unit: "COP" })}
        ${card("Saldo por cuenta", `<div id="b-leg"></div><div class="chart-box"><canvas id="ch-b2"></canvas></div>`, { unit: "COP · fin de mes" })}
      </div>
      <div class="grid g2">
        ${card("Movimientos de capital interno", `<table class="mini"><thead><tr><th>No son ingreso ni gasto</th><th class="num">${esc(scopeLabel("bank"))}</th>${pmv ? `<th class="num">${esc(prevLabelFor("bank"))}</th>` : ""}</tr></thead><tbody>${capRows.map(([l, k]) => `<tr><td>${l}</td><td class="num">${M(b(k))}</td>${pmv ? `<td class="num">${M(pb(k))}</td>` : ""}</tr>`).join("")}</tbody></table>`, { unit: "COP" })}
        ${card("Saldos al cierre", `<table class="mini"><thead><tr><th>Cuenta</th><th>Mes</th><th class="num">Saldo</th></tr></thead><tbody>${bal.sort((x, y) => y.Saldo - x.Saldo).map(x => `<tr><td>${esc(N.name(x.Cuenta))}</td><td>${esc(F.monthLabel(x.Mes))}</td><td class="num">${M(x.Saldo)}</td></tr>`).join("")}<tr><td><b>Total</b></td><td></td><td class="num"><b>${M(balT)}</b></td></tr></tbody></table>`, { unit: "COP" })}
      </div>
      ${more("Comparativo con el año anterior", `<div id="b-cmp"></div>`)}
      ${more("Continuidad de saldos", `<div id="b-bc"></div>`)}
      ${more("Transferencias internas por mes", `<div id="b-tr"></div>`)}
      ${more("Pagos de tarjetas", `<div id="b-pg"></div>`)}
      ${more("Movimientos materiales", `<div id="b-mat"></div>`, { meta: `≥ COP ${CP(D.meta.materiality_cop)}` })}
      ${more("Movimientos", `<div id="b-mv"></div>`, { meta: `${fmt.int(mv.length)} registros` })}
      ${more("Excepciones de bancos", `<div class="group-h body" style="margin:0;padding:12px 18px 0">Año en curso</div><div id="b-exc"></div><div class="group-h body" style="margin:0;padding:12px 18px 0">Hallazgos de años anteriores</div><div id="b-hist"></div>`, { meta: `${cur.length} actuales · ${cur.filter(e => e.is_open).length} abiertas` })}
    </div>`;
    const months = D.uniq(mv.map(m => m.Mes)).sort();
    if (months.length) C.combo("ch-b1", months.map(m => F.monthLabel(m)),
      [{ label: "Entradas externas", data: months.map(mm => D.bkm("external_in", mv.filter(x => x.Mes === mm))), backgroundColor: COL.cur },
        { label: "Salidas externas", data: months.map(mm => D.bkm("external_out", mv.filter(x => x.Mes === mm))), backgroundColor: COL.fam }],
      [{ label: "Pagos de tarjetas", data: months.map(mm => D.bkm("card_payments", mv.filter(x => x.Mes === mm))), borderColor: COL.line, backgroundColor: COL.line }], { fmt: v => M(v, 1) });
    else C.empty("ch-b1");
    const mb = F.bankRows(D.bank.monthly_balances);
    const accs = D.uniq(mb.map(x => x.Cuenta)), ms = D.uniq(mb.map(x => x.Mes)).sort();
    const pal = [COL.cur, COL.fam, "#3a3a37", "#a7a7a2", "#5c6f87", "#bfc8d4"];
    if (ms.length) {
      C.line("ch-b2", ms.map(m => F.monthLabel(m)), accs.map((a, i) => ({ label: N.name(a), data: ms.map(m => { const r = mb.find(x => x.Cuenta === a && x.Mes === m); return r ? r["Saldo final"] : null; }), borderColor: pal[i % pal.length], backgroundColor: pal[i % pal.length] })), { fmt: v => M(v, 1) });
      document.getElementById("b-leg").innerHTML = legend(accs.map((a, i) => ({ label: N.name(a), color: pal[i % pal.length], line: true })));
    } else C.empty("ch-b2");
    renderYoY("b-cmp", "bank");
    T.render("b-bc", { rows: F.bankRows(D.bank.balance_continuity.map(r => Object.assign({ Mes: /^\d{4}-\d{2}$/.test(r.Período) ? r.Período : null, Trimestre_n: /^Q(\d)/.test(r.Período) ? Number(r.Período[1]) : (/^\d{4}-(\d{2})$/.test(r.Período) ? Math.ceil(Number(r.Período.slice(5)) / 3) : null) }, r))),
      pageSize: 25, columns: [{ key: "Cuenta", label: "Cuenta", fmt: v => N.name(v) }, { key: "Período", label: "Período" }, { key: "Desde", label: "Desde", fmt: fmt.date }, { key: "Hasta", label: "Hasta", fmt: fmt.date },
        { key: "Saldo inicial", label: "Saldo inicial", num: true, fmt: fmt.cop2 }, { key: "Saldo final extracto", label: "Saldo final", num: true, fmt: fmt.cop2 }, { key: "Intereses", label: "Intereses", num: true, fmt: fmt.cop2 },
        { key: "Estado", label: "Estado", html: r => pill(r.Estado || "—", r.Estado === "OK" ? "ok" : "high") }] });
    T.render("b-tr", { rows: F.bankRows(D.bank.internal_transfers.monthly || []), columns: [{ key: "Mes", label: "Mes", fmt: v => F.monthLabel(v) }, { key: "*9910 → Fiducuentas", label: "Ahorros → fiducuentas", num: true, fmt: CP },
      { key: "Adiciones Fiducuentas", label: "Adiciones (fiducia)", num: true, fmt: CP }, { key: "Dif. aportes", label: "Dif.", num: true, fmt: CP }, { key: "Fiducuentas → *9910", label: "Fiducuentas → ahorros", num: true, fmt: CP },
      { key: "Retiros Fiducuentas", label: "Retiros (fiducia)", num: true, fmt: CP }, { key: "Dif. retiros", label: "Dif.", num: true, fmt: CP },
      { key: "Estado", label: "Estado", html: r => pill(r.Estado || "—", /Match/.test(r.Estado || "") ? "ok" : "low") }, { key: "Nota", label: "Nota", cls: "wrap" }],
      totals: (c, rows) => c.num ? CP(D.sum(rows, c.key)) : c.key === "Mes" ? "Total" : "" });
    T.render("b-pg", { rows: F.bankRows(D.bank.card_payments || []), search: true, pageSize: 20, columns: [{ key: "Fecha", label: "Fecha", fmt: fmt.date },
      { key: "Tarjeta / producto", label: "Tarjeta", html: r => nm(r["Tarjeta / producto"]), text: r => N.full(r["Tarjeta / producto"]) }, { key: "Monto pagado", label: "Monto", num: true, fmt: fmt.cop2 }, { key: "Estado", label: "Estado", html: r => pill(r.Estado || "—", /^Matched|^Conciliado|exact/i.test(r.Estado || "") ? "ok" : "low") },
      { key: "ID *9910", label: "ID movimiento" }, { key: "TxnID auditoría TC", label: "ID tarjeta" }, { key: "Excepción", label: "Excepción", html: r => r.Excepción ? `<span class="chip warn">${esc(r.Excepción)}</span>` : "" }],
      totals: (c, rows) => c.key === "Monto pagado" ? fmt.cop2(D.sum(rows, c.key)) : c.key === "Fecha" ? "Total" : "" });
    T.render("b-mat", { rows: F.bankRows(D.bank.material_movements || []), search: true, pageSize: 20, sort: { key: "Fecha", dir: "desc" }, rowId: r => r.ID,
      detail: r => `<div class="detail-grid">${["ID", "Cuenta", "Descripción", "Contraparte", "Money Pro", "Conclusión"].filter(k => r[k]).map(k => `<b>${esc(k)}</b><span>${esc(r[k])}</span>`).join("")}</div>`,
      columns: [{ key: "Fecha", label: "Fecha", fmt: fmt.date }, { key: "Cuenta", label: "Cuenta", fmt: v => N.name(v) }, { key: "Descripción", label: "Descripción", cls: "clip", tip: r => r.Descripción },
        { key: "Valor", label: "Valor", num: true, fmt: CP }, { key: "Clasificación", label: "Clasificación" }, { key: "Conclusión", label: "Conclusión", cls: "clip", tip: r => r.Conclusión },
        { key: "Excepción", label: "Excepción", html: r => r.Excepción ? `<span class="chip warn">${esc(r.Excepción)}</span>` : "" }] });
    excTable("b-exc", cur, { noSource: true });
    excTable("b-hist", hist, { noSource: true, extra: [{ key: "cat", label: "Continuidad", html: r => catTxt(catCode(r)), sortValue: r => catCode(r) }] });
    T.render("b-mv", { rows: mv, search: true, pageSize: 25, sort: { key: "Fecha", dir: "desc" }, rowId: r => r.ID,
      detail: r => `<div class="detail-grid">${["ID", "Cuenta", "Subclase", "Contraparte", "Match tipo", "Match ref", "Money Pro estado", "Money Pro ref", "Confianza", "Nota", "Archivo extracto"].filter(k => r[k] !== null && r[k] !== undefined && r[k] !== "").map(k => `<b>${esc(k)}</b><span>${esc(r[k])}</span>`).join("")}</div>`,
      columns: [{ key: "Fecha", label: "Fecha", fmt: fmt.date }, { key: "Cuenta", label: "Cuenta", fmt: v => N.name(v) }, { key: "Descripción (extracto)", label: "Descripción", cls: "clip", tip: r => r["Descripción (extracto)"] },
        { key: "Valor", label: "Valor", num: true, fmt: fmt.cop2 }, { key: "Saldo después", label: "Saldo", num: true, fmt: fmt.cop2 }, { key: "Clasificación", label: "Clasificación" }, { key: "Flujo económico", label: "Tipo de flujo" },
        { key: "Excepción", label: "Excepción", html: r => r.Excepción ? `<span class="chip warn">${esc(r.Excepción)}</span>` : "" }],
      totals: (c, rows) => c.key === "Valor" ? fmt.cop2(D.sum(rows, "Valor")) : c.key === "Fecha" ? "Neto" : "" });
  }

  /* ======================================================================================
     4. PRODUCTOS
     ====================================================================================== */
  function renderProductos() {
    const el = document.getElementById("page-productos");
    const rows = F.puRows(D.pu.monthly), cat = D.pu.catalog, meta = D.pu.metadata || {};
    if (!D.pu.monthly.length) { el.innerHTML = card("Productos", `<div class="empty">Sin datos de utilidad de productos.</div>`); return; }
    const prod = puProducts(rows);
    const tot = k => prod.reduce((s, p) => s + nz(p[k]), 0);
    const negs = prod.filter(p => p["Valor neto"] < 0), active = prod.filter(p => p["Costo total"] || p["Beneficios totales"]);
    const vTeo = tot("teorico"), realTeo = prod.filter(p => p.teorico).reduce((t, p) => t + p["Beneficios totales"], 0);
    const prev = prevScope(D.pu.monthly, "pu");
    const fid = F.puRows(D.pu.fiducuentas.map(f => Object.assign({ Producto: "Bancolombia " + f.Cuenta, Banco: "Fiduciaria Bancolombia" }, f)), {}).filter(f => f.is_tc);
    const comp = PU_COST.map(k => [k, -tot(k)]).concat(PU_BEN.map(k => [k, tot(k)])).filter(x => x[1]);
    const linkify = t => esc(t || "").replace(/(https?:\/\/[^\s;,)]+)/g, u => `<a href="${u}" target="_blank" rel="noopener">${u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 40)}…</a>`);
    let fidHTML = `<div class="empty">Sin meses de la fiducuenta de pagos en el período.</div>`;
    if (fid.length) {
      const sInt = D.sum(fid, "Intereses generados (rend. netos)"), sRet = D.sum(fid, "Retención"), sOut = D.sum(fid, "Capital retirado"), sIn = D.sum(fid, "Capital aportado");
      const sTC = fid.reduce((s, f) => s + nz(f["Capital destinado a pagos TC (atribuible)"]), 0);
      const avg = fid.reduce((s, f) => s + nz(f["Saldo promedio simple"]), 0) / fid.length;
      fidHTML = `<div class="grid g4">
        ${kpi("Intereses generados", M(sInt, 3), "COP · netos de comisión", avg ? `≈ ${pct(Math.pow(1 + sInt / avg / fid.length, 12) - 1, 2)} E.A. observada` : "", { sm: true })}
        ${kpi("Saldo promedio", M(avg), "COP", `${fid.length} meses`, { sm: true })}
        ${kpi("Capital usado para pagar tarjetas", M(sTC), "COP", sOut ? `${pct(sTC / sOut)} de los retiros` : "", { sm: true })}
        ${kpi("Resultado neto", M(sInt - sRet, 3), "COP · intereses − retención", `Aportes ${M(sIn)} · retiros ${M(sOut)}`, { sm: true })}
      </div>`;
    }
    el.innerHTML = `<div class="stack">
      <div class="grid g4">
        ${kpi("Valor neto generado", M(tot("Valor neto")), `COP · ${esc(scopeLabel())}`, prev && prev.length ? `${M(D.sum(prev, "Valor neto"))} en ${esc(prevLabelFor())}` : "beneficios − costos")}
        ${kpi("Productos que restan valor", `${negs.length} de ${active.length}`, "con costos o beneficios en el período", negs.map(p => N.name(p.Producto)).join(", "))}
        ${kpi("Beneficios totales", M(tot("Beneficios totales")), "COP", `Costos ${M(tot("Costo total"))} · intereses ganados ${M(tot("Intereses ganados"))}`)}
        ${kpi("Beneficio real vs teórico", vTeo ? pct(realTeo / vTeo) : "—", "productos con beneficio teórico", vTeo ? `Real ${M(realTeo)} · teórico ${M(vTeo)}` : "")}
      </div>
      <div class="grid g2">
        ${card("Valor neto por producto", rankList(prod, { wide: true }) + `<p class="note">Sin fiducuentas (no tienen costo de manejo); su rendimiento está en el detalle por producto.</p>`, { unit: "COP" })}
        ${card("De dónde vienen costos y beneficios", `<div class="chart-box tall"><canvas id="ch-u2"></canvas></div>`, { unit: "COP · costos en negativo" })}
      </div>
      ${card("Detalle por producto", `<div id="u-rank"></div>`, { flush: true, unit: "COP" })}
      ${card("Fiducuenta de pagos de tarjeta", fidHTML, { unit: esc(N.name(meta.fiducuenta_tc_id || "6191")) })}
      ${more("Beneficio teórico vs real", `<div id="u-teo"></div>`)}
      ${more("Estrategia de uso por producto", `<div class="strat" id="u-strat"></div>`, { pad: true })}
      ${fid.length ? more("Fiducuenta de pagos: detalle mensual", `<div id="u-fid-t"></div>`) : ""}
      ${more("Catálogo de productos", `<div id="u-cat"></div>`)}
      ${more("Detalle mensual", `<div id="u-mon"></div>`, { meta: `${fmt.int(rows.length)} registros` })}
    </div>`;
    if (comp.length) C.bar("ch-u2", comp.map(x => x[0]), [{ label: "COP", data: comp.map(x => x[1]), backgroundColor: comp.map(x => x[1] < 0 ? COL.neg : COL.cur) }], { horizontal: true, fmt: v => M(v, 2) });
    else C.empty("ch-u2");
    T.render("u-rank", { rows: prod, sort: { key: "Valor neto", dir: "desc" }, rowId: r => r.id,
      detail: r => `<div class="detail-grid">${[["Cuotas de manejo", r["Cuotas de manejo"]], ["Intereses pagados", r["Intereses pagados"]], ["Seguros", r.Seguros], ["Otros costos", r["Otros costos"]], ["Cashback", r.Cashback], ["Descuentos", r.Descuentos], ["Puntos monetizados", r["Puntos monetizados"]], ["Otros beneficios", r["Otros beneficios"]], ["Intereses ganados", r["Intereses ganados"]]].map(x => `<b>${esc(x[0])}</b><span>${fmt.cop2(nz(x[1]))}</span>`).join("")}<b>Función</b><span>${esc(r.Función || "")}</span><b>Cobertura</b><span>${esc(r.cobertura)}</span><b>Nombre en el libro</b><span>${esc(r.Producto)}</span><b>Fuentes</b><span>${esc(r.fuentes || "")}</span></div>`,
      columns: [{ key: "Producto", label: "Producto", html: r => nmRef(r.Producto), text: r => N.full(r.Producto) }, { key: "Tipo", label: "Tipo" },
        { key: "consumo", label: "Consumo / saldo prom.", num: true, sortValue: r => r.isCard ? nz(r["Consumo asociado"]) : nz(r["Saldo promedio"]), html: r => r.isCard ? (r["Consumo asociado"] ? CP(r["Consumo asociado"]) : "") : (num(r["Saldo promedio"]) ? CP(r["Saldo promedio"]) : "") },
        { key: "Costo total", label: "Costos", num: true, fmt: CP }, { key: "Beneficios totales", label: "Beneficios", num: true, fmt: CP },
        { key: "Valor neto", label: "Valor neto", num: true, fmt: CP }, { key: "costPct", label: "Costo / consumo", num: true, fmt: v => v === null ? "" : pct(v, 2) }, { key: "ROI", label: "ROI", num: true, fmt: v => v === null ? "" : pct(v) },
        { key: "mesesUso", label: "Meses con uso", num: true, html: r => `${fmt.int(r.mesesUso)} / ${fmt.int(r.meses)}` },
        { key: "Estado", label: "Estado", cls: "clip", tip: r => `${r.Estado || ""} · ${r.cobertura || ""}` }],
      totals: (c, rs) => ["Costo total", "Beneficios totales", "Valor neto"].includes(c.key) ? CP(D.sum(rs, c.key)) : c.key === "Producto" ? "Total" : "" });
    T.render("u-teo", { rows: prod.filter(p => p.teorico || p["Beneficios totales"]), sort: { key: "teorico", dir: "desc" }, columns: [{ key: "Producto", label: "Producto", html: r => nm(r.Producto) },
      { key: "Beneficio_Principal", label: "Beneficio principal", cls: "clip", tip: r => r.cat.Beneficio_Principal, html: r => esc(r.cat.Beneficio_Principal || "") },
      { key: "Consumo asociado", label: "Consumo", num: true, fmt: v => v ? CP(v) : "" }, { key: "teorico", label: "Teórico", num: true, fmt: CP },
      { key: "Beneficios totales", label: "Real", num: true, fmt: CP }, { key: "gap", label: "Brecha", num: true, sortValue: r => r["Beneficios totales"] - r.teorico, html: r => r.teorico ? CP(r["Beneficios totales"] - r.teorico) : "" },
      { key: "captura", label: "% capturado", num: true, fmt: v => v === null ? "" : pct(v) }],
      totals: (c, rs) => ["teorico", "Beneficios totales", "Consumo asociado"].includes(c.key) ? CP(D.sum(rs, c.key)) : c.key === "Producto" ? "Total" : "" });
    const strat = cat.filter(c => c.Beneficio_Principal && (!F.get("bank") || c.Banco === F.get("bank")) && (!F.get("product") || c.Producto === F.get("product")));
    document.getElementById("u-strat").innerHTML = strat.map(c => `<div class="card-m"><h4>${nmRef(c.Producto)} <span class="muted small">${esc(c.Estado || "")}</span></h4><dl>
      ${[["Beneficio principal", c.Beneficio_Principal], ["Condición", c.Condición_Beneficio], ["Uso recomendado", c.Uso_Recomendado], ["No conviene para", c.No_Conviene_Para], ["Limitaciones", c.Limitaciones], ["Costo relevante", c.Costo_Relevante]].filter(x => x[1]).map(x => `<dt>${esc(x[0])}</dt><dd>${esc(x[1])}</dd>`).join("")}
      <dt>Fuente</dt><dd class="small">${linkify(c.Fuente_Beneficio)} · verificado ${esc(c.Fecha_Verificación || "")}</dd></dl></div>`).join("") || `<div class="empty">Sin productos en el alcance.</div>`;
    if (fid.length) T.render("u-fid-t", { rows: fid, columns: [{ key: "Mes", label: "Mes", fmt: v => F.monthLabel(v) }, { key: "Saldo inicial", label: "Saldo inicial", num: true, fmt: CP }, { key: "Capital aportado", label: "Aportes", num: true, fmt: CP },
      { key: "Capital retirado", label: "Retiros", num: true, fmt: CP }, { key: "Intereses generados (rend. netos)", label: "Intereses", num: true, fmt: fmt.cop2 }, { key: "Retención", label: "Retención", num: true, fmt: fmt.cop2 },
      { key: "Saldo final", label: "Saldo final", num: true, fmt: CP }, { key: "Saldo promedio simple", label: "Saldo prom.", num: true, fmt: CP }, { key: "Tasa efectiva observada E.A.", label: "Tasa obs. E.A.", num: true, fmt: v => pct(v, 2) },
      { key: "Rentabilidad informada E.A.", label: "Rent. informada", num: true, fmt: v => pct(v, 2) },
      { key: "Capital destinado a pagos TC (atribuible)", label: "A pagos TC", num: true, fmt: v => num(v) ? CP(v) : (v || "") }, { key: "% del retiro usado para TC", label: "% a TC", num: true, fmt: v => num(v) ? pct(v) : (v || "") }],
      totals: (c, rs) => ["Capital aportado", "Capital retirado", "Intereses generados (rend. netos)", "Retención", "Capital destinado a pagos TC (atribuible)"].includes(c.key) ? fmt.cop2(rs.reduce((s, r) => s + nz(r[c.key]), 0)) : c.key === "Mes" ? "Total" : "" });
    T.render("u-cat", { rows: cat.filter(c => (!F.get("bank") || c.Banco === F.get("bank")) && (!F.get("product") || c.Producto === F.get("product"))),
      columns: [{ key: "Producto", label: "Producto", html: r => nmRef(r.Producto) }, { key: "Banco", label: "Banco" }, { key: "Tipo de producto", label: "Tipo" }, { key: "Función", label: "Función", cls: "wrap" }, { key: "Estado", label: "Estado" }, { key: "Comentario", label: "Comentario", cls: "wrap" }] });
    T.render("u-mon", { rows: rows, search: true, pageSize: 25, rowId: r => r.ID_Producto + r.Mes, detail: r => `<div class="detail-grid"><b>Fuente</b><span>${esc(r.Fuente)}</span><b>Evidencia</b><span>${esc(r.Evidencia)}</span><b>Comentario</b><span>${esc(r.Comentario)}</span></div>`,
      columns: [{ key: "Mes", label: "Mes", fmt: v => F.monthLabel(v) }, { key: "Producto", label: "Producto", html: r => nm(r.Producto), text: r => N.full(r.Producto) }, { key: "Consumo asociado", label: "Consumo", num: true, fmt: v => num(v) ? CP(v) : "" },
        { key: "Saldo promedio", label: "Saldo prom.", num: true, fmt: v => num(v) ? CP(v) : "" }, { key: "Costo total", label: "Costo", num: true, fmt: fmt.cop2 },
        { key: "Beneficios totales", label: "Beneficio", num: true, fmt: fmt.cop2 }, { key: "Valor neto", label: "Neto", num: true, fmt: fmt.cop2 }, { key: "Puntos ganados", label: "Puntos", num: true, fmt: fmt.int }] });
  }

  /* ======================================================================================
     5. EXCEPCIONES (control de auditoría)
     ====================================================================================== */
  function renderExcepciones() {
    const el = document.getElementById("page-excepciones");
    const cur = F.excRows(D.exceptions).filter(e => !e.is_historical);
    const hist = F.excRows(D.exceptions, { ignoreYear: true, ignoreQuarter: true }).filter(e => e.is_historical);
    const VIEWS = [["todas", "Todas", cur], ["abiertas", "Abiertas", cur.filter(e => e.is_open)], ["monitor", "En monitoreo", cur.filter(e => e.is_monitor)],
      ["cerradas", "Cerradas en esta actualización", cur.filter(e => e.closed_this_update)], ["resueltas", "Resueltas", cur.filter(e => !e.is_open && !e.is_monitor)]];
    const view = VIEWS.find(v => v[0] === ui.excView) || VIEWS[0];
    const resolved = cur.filter(e => !e.is_open && !e.is_monitor).length;
    const g = k => hist.filter(e => e.group === k);
    F.note("Los hallazgos de años anteriores nunca se suman a las excepciones abiertas. Si vuelven a fallar, se abre una excepción nueva vinculada.");
    el.innerHTML = `<div class="stack">
      <div class="grid g4">
        ${kpi("Abiertas", fmt.int(cur.filter(e => e.is_open).length), `año ${CY()}`, `${cur.filter(e => e.is_open && e.Riesgo === "HIGH").length} de riesgo alto`, { alert: cur.some(e => e.is_open && e.Riesgo === "HIGH") })}
        ${kpi("En monitoreo", fmt.int(cur.filter(e => e.is_monitor).length), "sin acción pendiente, con seguimiento", "")}
        ${kpi("Resueltas", fmt.int(resolved), `de ${cur.length} excepciones del año`, `${cur.filter(e => e.closed_this_update).length} cerradas en la última actualización`)}
        ${kpi("Hallazgos de años anteriores", fmt.int(hist.length), "contexto, no cuentan como abiertas", `${g("carry_forward").length} con acción pendiente (carry forward)`)}
      </div>
      ${card(`Excepciones ${CY()}`, `<div id="ex-cur"></div>`, { flush: true, right: `<div class="seg">${VIEWS.map(([k, l, rs]) => `<button type="button" data-exv="${k}" aria-pressed="${view[0] === k}">${esc(l)} (${rs.length})</button>`).join("")}</div>` })}
      ${more("Hallazgos de años anteriores", `<div id="ex-hist"></div>`, { meta: `${g("carry_forward").length} carry forward · ${g("recurrente").length} controles recurrentes · ${g("historico_resuelto").length} resueltos / contexto` })}
    </div>`;
    el.querySelectorAll("[data-exv]").forEach(b => b.addEventListener("click", () => { ui.excView = b.dataset.exv; renderExcepciones(); }));
    excTable("ex-cur", view[2], { search: true, pageSize: 30 });
    const GRP = { carry_forward: "Carry forward", recurrente: "Control recurrente", historico_resuelto: "Resuelto / contexto" };
    excTable("ex-hist", hist, { search: true, pageSize: 30, extra: [{ key: "group", label: "Grupo", fmt: v => GRP[v] || v }, { key: "cat", label: "Continuidad", html: r => catTxt(catCode(r)), sortValue: r => catCode(r) },
      { key: "lat", label: `Estado ${CY()}`, cls: "clip", tip: r => r.continuity && r.continuity.latest_status, html: r => esc((r.continuity && r.continuity.latest_status) || "") },
      { key: "lnk", label: "Excepción nueva", html: r => r.continuity && r.continuity.linked ? `<span class="chip warn">${esc(r.continuity.linked)}</span>` : "" }] });
  }

  /* ======================================================================================
     6. CRONOGRAMA Y CONTINUIDAD
     ====================================================================================== */
  function renderCronograma() {
    const el = document.getElementById("page-cronograma");
    const y = selYear(), s = F.get("source"), r = F.get("risk");
    const per = D.tl.periods.filter(p => (!y || p.year === y) && (!s || p.source === s));
    const years = D.uniq(per.map(p => p.year)).sort();
    const ctl = D.tl.control_results.filter(c => !y || c.Año === y);
    const cls = st => st === "Completado" ? "done" : st === "En auditoría" ? "prog" : "wait";
    const tl = years.map(yy => ["Credit Card", "Bank & Cash"].filter(m => !s || m === s).map(mod => {
      const rows = [1, 2, 3, 4, null].map(q => per.find(p => p.year === yy && p.quarter === q && p.source === mod)).filter(Boolean);
      if (!rows.length) return "";
      return `<div class="tl-mod">${yy} · ${esc(MODULO[mod] === "Tarjetas" ? "Tarjetas de crédito" : "Bancos y efectivo")}</div><div class="tl">${rows.map(p => `<div class="tl-cell ${cls(p.status)}">
        <div class="p"><span>${esc(p.quarter ? "Q" + p.quarter : "Anual")}</span>${tlPill(p.status)}</div>
        <div class="row">${p.execution_date ? `Ejecutado ${esc(fmt.date(p.execution_date))}` : `Planeado ${esc(F.monthLabel(p.planned_execution))}`}</div>
        <div class="row">${p.deliverable ? esc(p.deliverable) : "Sin informe"}</div>
        <div class="row">${fmt.int(p.records_loaded)} registros · ${fmt.int(p.exceptions)} excepciones</div></div>`).join("")}</div>`;
    }).join("")).join("");
    let contHTML = `<div class="empty">Sin matriz de continuidad.</div>`, links = [];
    if (D.cont) {
      const cnt = D.cont.category_counts || {};
      D.exceptions.filter(e => !e.is_historical && e["Hallazgo relacionado"]).forEach(e => (e["Hallazgo relacionado"].match(/EX-\d+/g) || []).forEach(h => links.push({ hist: h, cur: e.ID })));
      D.cont.matrix.forEach(m => (String(m.Latest_Linked_Exception || "").match(/EX-\d+/g) || []).forEach(c => { if (!links.some(l => l.hist === m.Finding_ID && l.cur === c)) links.push({ hist: m.Finding_ID, cur: c }); }));
      links = links.map(l => { const h = D.excById[l.hist] || {}, c = D.excById[l.cur] || {}; const m = D.cont.matrix.find(x => x.Finding_ID === l.hist) || {};
        return { hist: l.hist, hdesc: m.Original_Description || h.Concepto, cat: m.category_code, cur: l.cur, cdesc: c.Concepto, crisk: c.Riesgo, cstate: c.Estado, cis_open: c.is_open, Source: c.Source || h.Source }; })
        .filter(x => (!s || x.Source === s) && (!r || x.crisk === r));
      contHTML = `<div class="kv num" style="max-width:520px">${Object.entries(D.cont.metadata.categories).map(([k, v]) => `<div><span>${esc(/^[A-F]\./.test(v) ? v : k + ". " + v)}</span><span>${fmt.int(cnt[k] || 0)}</span></div>`).join("")}</div><p class="note">${esc(D.cont.metadata.principle || "")}</p>`;
    }
    el.innerHTML = `<div class="stack">
      ${card("Cronograma de auditoría", tl || `<div class="empty">Sin períodos para los filtros.</div>`, { note: esc(D.tl.status_rule.join(" · ")) })}
      ${card("Continuidad de hallazgos", contHTML, { unit: "hallazgos de años anteriores por categoría" })}
      ${card("Hallazgo anterior → excepción nueva", `<div id="c-link"></div>`, { flush: true })}
      ${more("Detalle por período", `<div id="cr-t"></div>`)}
      ${more("Resultados de controles trimestrales", `<div id="cr-c"></div>`, { meta: `${ctl.length} controles · ${ctl.filter(c => c.Resultado !== "PASS").length} no PASS` })}
      ${D.cont ? more("Matriz de continuidad", `<div id="c-mat"></div>`) : ""}
      ${D.cont ? more("Reglas de contexto y coincidencias", `<div id="c-ctx"></div><div class="group-h body" style="margin:0;padding:12px 18px 0">Coincidencias ${CY()}</div><div id="c-hits"></div>`) : ""}
      ${D.cont ? more("Ciclo de vida de productos", `<div id="c-life"></div>`) : ""}
      ${more("Calendario y marco de controles", `<div class="group-h body" style="margin:0;padding:12px 18px 0">Calendario — tarjetas</div><div id="cr-k1"></div><div class="group-h body" style="margin:0;padding:12px 18px 0">Calendario — bancos</div><div id="cr-k2"></div><div class="group-h body" style="margin:0;padding:12px 18px 0">Marco de controles</div><div id="cr-f"></div>`)}
    </div>`;
    T.render("c-link", { rows: links, columns: [{ key: "hist", label: "Hallazgo anterior" }, { key: "cat", label: "Categoría", html: x => catTxt(x.cat || "?") }, { key: "hdesc", label: "Descripción original", cls: "clip", tip: x => x.hdesc },
      { key: "cur", label: "Excepción nueva" }, { key: "crisk", label: "Riesgo", fmt: v => RIESGO_TXT[v] || v || "" }, { key: "cdesc", label: "Concepto", cls: "clip", tip: x => x.cdesc },
      { key: "cstate", label: "Estado", html: x => x.cstate ? pill(estadoTxt(x.cstate), x.cis_open ? "medium" : "ok") : "" }] });
    T.render("cr-t", { rows: per, columns: [{ key: "period", label: "Período" }, { key: "module", label: "Módulo" }, { key: "planned_execution", label: "Planeado", fmt: v => F.monthLabel(v) },
      { key: "execution_date", label: "Ejecutado", fmt: fmt.date }, { key: "status", label: "Estado", html: p => tlPill(p.status) }, { key: "deliverable", label: "Informe", cls: "clip", tip: p => p.deliverable_path || (p.deliverable_declared ? "Declarado en config.json" : "") },
      { key: "coverage", label: "Cobertura", cls: "wrap" }, { key: "records_loaded", label: "Registros", num: true, fmt: fmt.int }, { key: "exceptions", label: "Excepciones", num: true }, { key: "high_exceptions", label: "Alto", num: true },
      { key: "controls_error", label: "Controles ERROR", num: true }, { key: "controls_warning", label: "WARNING", num: true }] });
    T.render("cr-c", { rows: ctl, search: true, pageSize: 30, columns: [{ key: "Año", label: "Año" }, { key: "Trimestre", label: "Trim." }, { key: "Control", label: "Control" }, { key: "Descripción", label: "Descripción", cls: "wrap" },
      { key: "Resultado", label: "Resultado", html: c => resPill(c.Resultado) }, { key: "Detalle / evidencia", label: "Detalle / evidencia", cls: "wrap" }, { key: "Excepción", label: "Excepción", html: c => c.Excepción ? `<span class="chip warn">${esc(c.Excepción)}</span>` : "" },
      { key: "Fecha ejecución", label: "Ejecutado", fmt: fmt.date }] });
    if (D.cont) {
      const cm = D.cont.metadata;
      const mat = D.cont.matrix.filter(x => (!s || x.Source === s) && (!r || x.Original_Risk === r));
      T.render("c-mat", { rows: mat, search: true, pageSize: 40, rowId: x => x.Finding_ID,
        detail: x => `<div class="detail-grid">${["Original_Description", "Respuesta_Usuario", "Resolution", "Evidence", "Carry_Forward_Rule", "Control_Ref", "Notes"].concat(cm.status_years.map(yy => yy + "_Status")).filter(k => x[k]).map(k => `<b>${esc({ Original_Description: "Descripción original", Respuesta_Usuario: "Respuesta del usuario", Resolution: "Resolución", Evidence: "Evidencia", Carry_Forward_Rule: "Regla de continuidad", Control_Ref: "Control", Notes: "Notas" }[k] || k.replace("_Status", " · estado"))}</b><span>${esc(x[k])}</span>`).join("")}</div>`,
        columns: [{ key: "Finding_ID", label: "ID" }, { key: "Original_Year", label: "Año" }, { key: "Original_Quarter", label: "Trim." }, { key: "Source", label: "Módulo", fmt: v => MODULO[v] || v },
          { key: "Original_Risk", label: "Riesgo", fmt: v => RIESGO_TXT[v] || v || "" }, { key: "Original_Description", label: "Descripción", cls: "clip", tip: x => x.Original_Description },
          { key: "Original_Status", label: "Estado original", fmt: estadoTxt }, { key: "category_code", label: "Categoría", html: x => catTxt(x.category_code) },
          { key: "Latest_Status", label: `Estado ${cm.status_years.slice(-1)[0] || ""}`, cls: "clip", tip: x => x.Latest_Status }, { key: "Latest_Linked_Exception", label: "Excepción vinculada", html: x => x.Latest_Linked_Exception ? `<span class="chip warn">${esc(x.Latest_Linked_Exception)}</span>` : "" }] });
      T.render("c-ctx", { rows: D.cont.context_rules.filter(x => !s || x.Source === s), columns: [{ key: "Finding_ID", label: "ID" }, { key: "Source", label: "Módulo", fmt: v => MODULO[v] || v },
        { key: "Original_Description", label: "Patrón", cls: "clip", tip: x => x.Original_Description }, { key: "Carry_Forward_Rule", label: "Regla", cls: "wrap" }, { key: "Latest_Status", label: "Estado", cls: "wrap" }] });
      T.render("c-hits", { rows: D.cont.context_hits, search: true, pageSize: 15, columns: [{ key: "finding_id", label: "Hallazgo" }, { key: "dataset", label: "Base" }, { key: "record_id", label: "Registro", cls: "clip", tip: x => x.record_id },
        { key: "date", label: "Fecha", fmt: fmt.date }, { key: "text", label: "Texto", cls: "clip", tip: x => x.text }, { key: "amount", label: "Monto", num: true, fmt: fmt.cop2 }, { key: "rule", label: "Regla", cls: "clip", tip: x => x.rule }] });
      T.render("c-life", { rows: D.cont.card_lifecycle, columns: [{ key: "Producto", label: "Producto", html: x => `${esc(N.name(x.Producto || x.Tarjeta))} <span class="ref-s">*${esc(x.Tarjeta)}</span>` }, { key: "Banco", label: "Banco" },
        { key: "Status", label: "Estado", fmt: v => ({ Active: "Activa", Closed: "Cerrada", Replaced: "Reemplazada" }[v] || v) },
        { key: "Opening_Date", label: "Apertura", fmt: fmt.date }, { key: "Closure_Date", label: "Cierre", fmt: fmt.date }, { key: "Replaced_By", label: "Reemplazada por" }, { key: "Evidence", label: "Evidencia", cls: "clip", tip: x => x.Evidence },
        { key: "Notes", label: "Notas", cls: "wrap" }] });
      if (D.cont.closed_card_alerts.length) el.insertAdjacentHTML("afterbegin", `<div class="banner error"><b>Actividad en tarjetas cerradas:</b> ${D.cont.closed_card_alerts.map(a => esc(a.message + " · " + a.record)).join("; ")}</div>`);
    }
    T.render("cr-k1", { rows: D.tl.calendar_tc, columns: [{ key: "Período auditado", label: "Período" }, { key: "Mes de ejecución", label: "Ejecución" }, { key: "Entregables", label: "Entregables", cls: "wrap" }, { key: "Alimenta", label: "Alimenta" }] });
    T.render("cr-k2", { rows: D.tl.calendar_bank, columns: [{ key: "Período", label: "Período" }, { key: "Ejecución", label: "Ejecución", cls: "wrap" }] });
    T.render("cr-f", { rows: D.tl.controls_tc.map(c => Object.assign({ mod: "Tarjetas" }, c)).concat(D.tl.controls_bank.map(c => Object.assign({ mod: "Bancos" }, c))), search: true, pageSize: 20,
      columns: [{ key: "mod", label: "Módulo" }, { key: "ID", label: "ID" }, { key: "Frecuencia", label: "Frecuencia" }, { key: "Control", label: "Control" }, { key: "Objetivo", label: "Objetivo", cls: "wrap" }, { key: "Criterio de excepción", label: "Criterio de excepción", cls: "wrap" }] });
  }

  /* ======================================================================================
     7. CALIDAD DE DATOS
     ====================================================================================== */
  function renderCalidad() {
    const el = document.getElementById("page-calidad");
    F.note("");
    const m = D.meta, dq = D.dq, rc = m.reconciliation || {}, sm = dq.summary || {};
    const cats = D.uniq(dq.checks.map(c => c.category));
    const RECORDS = { transacciones_tc: "Transacciones TC", extractos_tc: "Extractos TC", movimientos_bancarios: "Movimientos bancarios", excepciones: "Excepciones (total)", excepciones_actuales: "Excepciones actuales",
      hallazgos_historicos: "Hallazgos históricos", productos: "Productos", filas_utilidad: "Filas de utilidad", controles_registrados: "Controles registrados", periodos_cronograma: "Períodos en cronograma" };
    const w = [].concat((m.errors || []).map(x => Object.assign({ level: "ERROR" }, x)), (m.warnings || []).map(x => Object.assign({ level: "WARNING" }, x)), (m.info || []).map(x => Object.assign({ level: "INFO" }, x)));
    const notPass = dq.checks.filter(c => c.status !== "PASS");
    const fid = D.pu.fiducuentas.filter(f => f.is_tc);
    const dias = fid.map(f => f["Días promedio de permanencia (rotación)"]).filter(num);
    const opp = D.uniq(fid.map(f => f["Costo de oportunidad"]));
    const defs = (defsObj, mod) => Object.keys(defsObj).map(k => `<tr><td>${esc(mod)}</td><td>${esc(k)}</td><td class="wrap" style="white-space:pre-line">${esc(D.srcTip(k, defsObj))}</td></tr>`).join("");
    el.innerHTML = `<div class="stack">
      <div class="strip"><span><b>Estado del refresh:</b> ${esc({ OK: "OK", OK_WITH_WARNINGS: "OK con advertencias", FAILED: "Fallido" }[m.status] || m.status)}</span><span>Ejecutado ${esc(fmt.date(m.last_refresh))}</span><span>Libros de solo lectura, verificados con SHA-256</span></div>
      <div class="grid g5">
        ${kpi("Controles PASS", fmt.int(sm.PASS), "", "", { sm: true })}
        ${kpi("Advertencias", fmt.int(sm.WARNING), "", "", { sm: true })}
        ${kpi("Errores", fmt.int(sm.ERROR), "", "", { sm: true, alert: !!sm.ERROR })}
        ${kpi("Conciliaciones OK", fmt.int(rc.passed), "ETL vs hojas resumen del libro", "", { sm: true })}
        ${kpi("Conciliaciones fallidas", fmt.int(rc.failed), "", "", { sm: true, alert: !!rc.failed })}
      </div>
      ${card("Advertencias, errores y notas del refresh", `<div id="dq-w"></div>`, { flush: true })}
      ${card("Controles de calidad", `<div id="dq-np"></div>`, { flush: true, unit: notPass.length ? `${notPass.length} con advertencia o error` : "todos en PASS" })}
      ${card("Cobertura de extractos por producto y mes", `<div id="dq-cov"></div>`, { note: "✓ con extracto · Sin act. = sin actividad, no requiere extracto · Sin uso = sin actividad observada · Migr. = producto migrado · Cerr. = cerrado · N/A = no abierto · Falta = extracto requerido faltante (genera excepción)." })}
      ${more("Todos los controles de calidad", cats.map((c, i) => `<div class="group-h body" style="margin:0;padding:12px 18px 0">${esc(c)}</div><div id="dq-${i}"></div>`).join(""), { meta: `${dq.checks.length} controles` })}
      ${more("Conciliaciones Excel vs ETL", `<div id="dq-rc"></div>`, { meta: `${fmt.int(rc.passed)} OK · ${fmt.int(rc.failed)} fallidas` })}
      ${more("Fuentes y registros", `<div id="dq-src"></div><div class="body"><div class="kv num" style="max-width:420px">${Object.entries(m.records || {}).map(([k, v]) => `<div><span>${esc(RECORDS[k] || k.replace(/_/g, " "))}</span><span>${fmt.int(v)}</span></div>`).join("")}</div></div>`)}
      ${more("Metodología y definiciones", `<div class="body"><h4 style="margin:0 0 6px">Utilidad de productos</h4><ul class="plain">${(D.pu.metadata.rules || []).map(r => `<li>${esc(r)}</li>`).join("")}<li>Beneficios cualitativos (salas VIP, seguros de viaje, 2x1 no usados) se describen y no se monetizan.</li></ul>
        <h4 style="margin:14px 0 6px">Fiducuenta de pagos de tarjeta</h4><ul class="plain"><li>Días promedio de permanencia (estimación del libro: saldo promedio ÷ retiros diarios): ${dias.length ? fmt.int(dias.reduce((a, b) => a + b, 0) / dias.length) + " días" : "sin dato"}.</li><li>Costo de oportunidad: ${esc(opp.join(" · ") || "no calculado; sin metodología aprobada")}.</li><li>Capital aportado o retirado es movimiento interno: no es ingreso ni gasto.</li></ul>
        <h4 style="margin:14px 0 6px">Estados de excepción</h4><ul class="plain"><li>Abiertas = Open o Review. Monitor = sin acción correctiva, con seguimiento; no cuenta como abierta.</li><li>${esc((D.exc.metadata && D.exc.metadata.historical_rule) || "Los hallazgos de años anteriores son contexto y no cuentan como excepciones abiertas actuales.")}</li><li>Siguiente ID de excepción: ${esc(D.exc.metadata.next_exception_id || "—")}.</li></ul>
        <h4 style="margin:14px 0 6px">Nombres de productos</h4><p class="note" style="margin:0">El dashboard muestra nombres comerciales (js/names.js). Los libros conservan el nombre con número; el detalle de cada registro muestra el nombre del libro.</p></div>
        <div class="tbl-wrap"><table class="t"><thead><tr><th>Módulo</th><th>Indicador</th><th>Definición (equivalente en Excel)</th></tr></thead><tbody>${defs(D.ccDefs, "Tarjetas")}${defs(D.bkDefs, "Bancos")}</tbody></table></div>`)}
    </div>`;
    T.render("dq-w", { rows: w, search: w.length > 10, pageSize: 20, columns: [{ key: "level", label: "Nivel", html: r => pill(r.level, r.level === "ERROR" ? "high" : r.level === "WARNING" ? "low" : "") }, { key: "code", label: "Código" }, { key: "message", label: "Mensaje", cls: "wrap" }] });
    T.render("dq-np", { rows: notPass, columns: [{ key: "status", label: "Resultado", html: x => resPill(x.status) }, { key: "category", label: "Tipo" }, { key: "check", label: "Control" }, { key: "detail", label: "Detalle", cls: "wrap" }] });
    cats.forEach((c, i) => T.render("dq-" + i, { rows: dq.checks.filter(x => x.category === c), columns: [{ key: "status", label: "Resultado", html: x => resPill(x.status) }, { key: "check", label: "Control" }, { key: "detail", label: "Detalle", cls: "wrap" }] }));
    T.render("dq-src", { rows: m.sources || [], columns: [{ key: "role", label: "Libro", fmt: v => ({ tc: "Tarjetas", bank: "Bancos" }[v] || v) }, { key: "file", label: "Archivo" }, { key: "modified", label: "Modificado", fmt: fmt.date },
      { key: "bytes", label: "Bytes", num: true, fmt: fmt.int }, { key: "sha256", label: "SHA-256", cls: "clip", tip: r => r.sha256 }, { key: "sheets", label: "Hojas", cls: "clip", fmt: v => (v || []).join(", "), tip: r => (r.sheets || []).join(", ") }] });
    const cov = (D.pu.coverage || []).filter(c => !selYear() || c.Año === selYear());
    const covCls = st => /^Falta/.test(st) ? "high" : "";
    const covShort = st => /^Con extracto/.test(st) ? "✓" : /^Falta/.test(st) ? "Falta" : /migrado/i.test(st) ? "Migr." : /cerrado/i.test(st) ? "Cerr." : /^No abierto/.test(st) ? "N/A" : /^Sin actividad —/.test(st) ? "Sin act." : "Sin uso";
    const cmo = D.uniq(cov.map(c => c.Mes)).sort(), cp = D.uniq(cov.map(c => c.Producto));
    document.getElementById("dq-cov").innerHTML = cov.length ? `<div class="tbl-wrap"><table class="mini cov"><thead><tr><th>Producto</th>${cmo.map(mm => `<th>${esc(F.monthLabel(mm).slice(0, 3))}</th>`).join("")}</tr></thead><tbody>${cp.map(p => `<tr><td>${nmRef(p)}</td>${cmo.map(mm => { const c = cov.find(x => x.Producto === p && x.Mes === mm); return `<td>${c ? `<span class="${covCls(c["Estado de cobertura"]) ? "pill high" : covShort(c["Estado de cobertura"]) === "✓" ? "" : "muted"}" title="${esc(c["Estado de cobertura"] + (c["Evidencia del estado"] ? " · " + c["Evidencia del estado"] : "") + (c.Excepción ? " · " + c.Excepción : ""))}">${covShort(c["Estado de cobertura"])}</span>` : ""}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">Sin filas de cobertura en el alcance.</div>`;
    const n2 = v => typeof v === "number" ? fmt.cop2(v).replace("$", "") : (v ?? "");
    T.render("dq-rc", { rows: dq.reconciliation.map(c => ({ check: c.check, cat: c.category, status: c.status, a: c.a.source, av: c.a.value, b: c.b.source, bv: c.b.value, diff: c.difference })), search: true, pageSize: 30,
      columns: [{ key: "status", label: "Resultado", html: x => resPill(x.status) }, { key: "cat", label: "Tipo" }, { key: "check", label: "Conciliación" }, { key: "av", label: "ETL", num: true, fmt: n2 },
        { key: "bv", label: "Libro", num: true, fmt: n2 }, { key: "diff", label: "Dif.", num: true, fmt: n2 }, { key: "b", label: "Referencia en el libro", cls: "clip", tip: x => x.b }] });
  }

  /* ======================================================================================
     ENRUTADOR / ARRANQUE
     ====================================================================================== */
  const RENDER = { tesoreria: renderTesoreria, resumen: renderResumen, tarjetas: renderTarjetas, bancos: renderBancos, productos: renderProductos, excepciones: renderExcepciones, cronograma: renderCronograma, calidad: renderCalidad };
  function route() {
    let p = (location.hash || "#tesoreria").slice(1);
    if (ALIAS[p]) p = ALIAS[p];
    if (!PAGES.includes(p)) p = "tesoreria";
    F.page = p;
    document.querySelectorAll(".side a[data-page]").forEach(a => a.setAttribute("aria-current", a.dataset.page === p ? "page" : "false"));
    document.querySelectorAll(".page").forEach(s => s.classList.toggle("active", s.id === "page-" + p));
    document.getElementById("page-title").textContent = TITLES[p] + (p === "tesoreria" ? (trPeriod().cur ? " · " + trPeriod().cur : "") : CONTROL.includes(p) || !selYear() ? "" : " · " + scopeLabel(p === "bancos" ? "bank" : "tc"));
    document.getElementById("crumb").textContent = CONTROL.includes(p) ? "Treasury Control Tower / Control de auditoría" : "Treasury Control Tower";
    document.title = TITLES[p] + " · Treasury Control Tower";
    F.render(); renderPeriod();
    try { RENDER[p](); } catch (e) { console.error(e); document.getElementById("page-" + p).innerHTML = `<div class="banner error">Error al dibujar la vista: ${esc(e.message)}</div>`; }
    renderFoot(p);
  }
  function tooltips() {
    const tip = document.getElementById("tip");
    const show = t => { const r = t.getBoundingClientRect(); tip.textContent = t.dataset.tip; tip.classList.add("show");
      const w = tip.offsetWidth, h = tip.offsetHeight; let x = r.left, y = r.bottom + 6;
      if (x + w > innerWidth - 8) x = innerWidth - w - 8; if (y + h > innerHeight - 8) y = r.top - h - 6; tip.style.left = Math.max(8, x) + "px"; tip.style.top = y + "px"; };
    document.addEventListener("mouseover", e => { const t = e.target.closest("[data-tip]"); if (t) show(t); });
    document.addEventListener("mouseout", e => { if (e.target.closest("[data-tip]")) tip.classList.remove("show"); });
    document.addEventListener("focusin", e => { const t = e.target.closest("[data-tip]"); if (t) show(t); });
    document.addEventListener("focusout", () => tip.classList.remove("show"));
  }
  async function boot() {
    await D.load();
    tooltips();
    if (!D.ready) {
      const m = D.meta || {};
      document.getElementById("banner").innerHTML = `<div class="banner error"><b>No se encontraron los datos.</b> Ejecute <code>python scripts/refresh_dashboard.py</code> y recargue. ${(m.errors || []).map(e => "<br>• " + esc(e.message)).join("")}</div>`;
      return;
    }
    renderChrome();
    let fresh = true;
    try { fresh = !localStorage.getItem("fad-filtros-v2"); } catch (e) { /* sin almacenamiento */ }
    F.init();
    if (fresh && CY() && D.years.includes(CY())) F.state.year = String(CY());   // por defecto: año de auditoría actual
    F.onChange(route);
    const bf = document.getElementById("btn-filters"), fp = document.getElementById("filterpanel");
    bf.addEventListener("click", () => { const open = fp.hidden; fp.hidden = !open; bf.setAttribute("aria-expanded", String(open)); });
    document.getElementById("btn-print").addEventListener("click", () => window.print());
    window.addEventListener("hashchange", route);
    route();
  }
  boot();
})();

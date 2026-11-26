/* data.js — carga el contrato de datos y ofrece las ÚNICAS primitivas de agregación (SUMA / CONTEO / razones).
   Aquí no se escribe ningún criterio de clasificación: vienen de metadata.metric_definitions,
   que el ETL copia de los SUMIFS del propio libro. */
(function () {
  "use strict";
  const D = {
    raw: null,
    async load() {
      if (window.AUDIT_DATA && window.AUDIT_DATA.metadata) {
        this.raw = window.AUDIT_DATA;
      } else {
        const names = ["metadata", "credit_cards", "bank_cash", "exceptions", "timeline", "continuity", "product_utility", "data_quality", "treasury"];
        const out = {};
        for (const n of names) {
          try { const r = await fetch("data/" + n + ".json", { cache: "no-store" }); if (r.ok) out[n] = await r.json(); }
          catch (e) { /* se informa abajo */ }
        }
        this.raw = out;
      }
      const r = this.raw || {};
      this.meta = r.metadata || {};
      this.cc = r.credit_cards || null;
      this.bank = r.bank_cash || null;
      this.exc = r.exceptions || null;
      this.tl = r.timeline || null;
      this.cont = r.continuity || null;
      this.pu = r.product_utility || { catalog: [], monthly: [], fiducuentas: [], metadata: {} };
      this.dq = r.data_quality || { checks: [], reconciliation: [], summary: {} };
      this.tr = r.treasury || { metadata: { available: false }, periods: [], metrics: {}, facilities: [], monthly: [] };
      this.ready = !!(this.cc && this.bank && this.exc && this.tl);
      if (this.ready) this._index();
      return this;
    },
    _index() {
      this.ccDefs = this.cc.metadata.metric_definitions;
      this.bkDefs = this.bank.metadata.metric_definitions;
      this.cards = this.cc.cards;
      this.cardByProduct = Object.fromEntries(this.cards.map(c => [c.Producto, c]));
      this.exceptions = this.exc.exceptions;
      this.excById = Object.fromEntries(this.exceptions.map(e => [e.ID, e]));
      this.riskOrder = this.exc.metadata.risk_order;
      this.thresholds = this.cc.metadata.thresholds || {};
      this.currentYear = this.meta.current_audit_year || this.exc.metadata.current_audit_year || null;
      this.years = (this.meta.years || []).slice().sort();
      // excepciones de un ETL antiguo sin campos de continuidad → se tratan como actuales
      this.exceptions.forEach(e => { if (e.is_historical === undefined) { e.is_historical = false; e.counts_in_current_open = e.is_open; e.group = "actual"; } });
      // producto → IDs de excepción vinculadas por Base_Transacciones.Excepción
      this.excByProduct = {};
      for (const t of this.cc.transactions) for (const id of (t["Excepción IDs"] || [])) {
        (this.excByProduct[t.Producto] = this.excByProduct[t.Producto] || new Set()).add(id);
      }
      this.excByAccount = {};
      for (const m of this.bank.transactions) for (const id of (m["Excepción IDs"] || [])) {
        (this.excByAccount[m.Cuenta] = this.excByAccount[m.Cuenta] || new Set()).add(id);
      }
    },

    /* ---------- generic engine ---------- */
    matches(rec, where) {
      for (const k in (where || {})) {
        const c = where[k], v = rec[k];
        if (c && typeof c === "object") { if (c.startswith !== undefined && !(typeof v === "string" && v.startsWith(c.startswith))) return false; }
        else if (v !== c) return false;
      }
      return true;
    },
    metric(records, def) {
      let n = 0, s = 0;
      const fields = def.field === undefined ? [] : (Array.isArray(def.field) ? def.field : [def.field]);
      for (const r of records) {
        if (!this.matches(r, def.where)) continue;
        n++;
        for (const f of fields) { const v = r[f]; if (typeof v === "number") s += v; }
      }
      return def.agg === "count" ? n : s;
    },
    ccm(key, records) { return this.metric(records, this.ccDefs[key]); },
    bkm(key, records) { return this.metric(records, this.bkDefs[key]); },
    sum(records, field) { let s = 0; for (const r of records) if (typeof r[field] === "number") s += r[field]; return s; },
    groupBy(records, keyFn) { const m = new Map(); for (const r of records) { const k = keyFn(r); if (!m.has(k)) m.set(k, []); m.get(k).push(r); } return m; },
    uniq(arr) { return [...new Set(arr.filter(v => v !== null && v !== undefined && v !== ""))]; },

    srcTip(key, defs) {
      const d = defs[key]; if (!d) return "";
      const w = Object.entries(d.where || {}).map(([k, v]) => `${k} = ${typeof v === "object" ? "empieza por “" + v.startswith + "”" : "“" + v + "”"}`).join(" Y ");
      const f = d.agg === "count" ? "CONTAR" : "SUMA(" + (Array.isArray(d.field) ? d.field.join(" + ") : d.field) + ")";
      return `Fuente: ${d.source}\n${f}${w ? " DONDE " + w : ""}\nEquivalente Excel: ${d.excel}`;
    },

    /* ---------- vínculo de excepciones (solo enlace; nunca reclasifica) ---------- */
    excLinkedToCard(e, product) {
      const c = this.cardByProduct[product];
      const set = this.excByProduct[product];
      if (set && set.has(e.ID)) return true;
      if (!c || !e["Cuenta/Tarjeta"]) return false;
      return (c.tokens || []).some(t => e["Cuenta/Tarjeta"].includes(t));
    },
    excLinkedToAccount(e, cuenta) {
      const set = this.excByAccount[cuenta];
      if (set && set.has(e.ID)) return true;
      const tok = (cuenta.match(/\d{4}/g) || []);
      return !!e["Cuenta/Tarjeta"] && tok.some(t => e["Cuenta/Tarjeta"].includes(t));
    },
    sortExceptions(list) {
      const ro = this.riskOrder;
      return list.slice().sort((a, b) => {
        const ra = ro.indexOf(a.Riesgo), rb = ro.indexOf(b.Riesgo);
        if ((ra < 0 ? 9 : ra) !== (rb < 0 ? 9 : rb)) return (ra < 0 ? 9 : ra) - (rb < 0 ? 9 : rb);
        return (b["Monto (COP)"] || 0) - (a["Monto (COP)"] || 0);
      });
    }
  };

  /* ---------- formato ---------- */
  const nf0 = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
  const nf2 = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  D.fmt = {
    cop(v) { return (v === null || v === undefined || isNaN(v)) ? "—" : (v < 0 ? "−$" : "$") + nf0.format(Math.abs(Math.round(v))); },
    cop2(v) { return (v === null || v === undefined || isNaN(v)) ? "—" : (v < 0 ? "−$" : "$") + nf2.format(Math.abs(v)); },
    copShort(v) {
      if (v === null || v === undefined || isNaN(v)) return "—";
      const a = Math.abs(v), s = v < 0 ? "−$" : "$";
      if (a >= 1e9) return s + (a / 1e9).toFixed(2).replace(".", ",") + " MM";
      if (a >= 1e6) return s + (a / 1e6).toFixed(2).replace(".", ",") + " M";
      if (a >= 1e3) return s + nf0.format(Math.round(a / 1e3)) + " k";
      return s + nf0.format(Math.round(a));
    },
    int(v) { return (v === null || v === undefined || isNaN(v)) ? "—" : nf0.format(v); },
    pct(v, d = 1) { return (v === null || v === undefined || !isFinite(v)) ? "—" : (v * 100).toFixed(d).replace(".", ",") + "%"; },
    signedPct(v) { return (v === null || v === undefined || !isFinite(v)) ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + (Math.abs(v) * 100).toFixed(1).replace(".", ",") + "%"; },
    date(iso) { if (!iso) return "—"; const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!m) return iso; return `${m[3]}/${m[2]}/${m[1]}` + (m[4] ? ` ${m[4]}:${m[5]}` : ""); },
    esc(s) { return s === null || s === undefined ? "" : String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  };
  window.Data = D;
})();

/* filters.js — filtros globales persistentes. Las opciones se leen de los datos (sin años, trimestres,
   meses, tarjetas ni cuentas fijos en el código). Los filtros que no aplican a la página actual quedan
   deshabilitados con la etiqueta "no aplica". Solo filtran: nunca reclasifican. */
(function () {
  "use strict";
  const KEY = "fad-filtros-v2";
  const ALL = "";
  const NAMES = ["year", "quarter", "month", "bank", "product", "card", "category", "flow", "status", "risk", "source"];
  const APPLIES = {
    tesoreria: ["year", "quarter"],
    resumen: ["year", "quarter", "month", "status", "risk"],
    tarjetas: ["year", "quarter", "month", "bank", "product", "card", "category", "status", "risk"],
    bancos: ["year", "quarter", "month", "bank", "product", "flow", "status", "risk"],
    productos: ["year", "quarter", "month", "bank", "product"],
    excepciones: ["year", "quarter", "bank", "category", "status", "risk", "source"],
    cronograma: ["year", "source", "risk"],
    calidad: []
  };
  const LABELS = { year: "Año", quarter: "Trimestre", month: "Mes", bank: "Banco", product: "Producto / cuenta", card: "Tarjeta", category: "Categoría",
    flow: "Tipo de flujo", status: "Estado de excepción", risk: "Riesgo", source: "Módulo" };
  const PER_PAGE = ["bank", "product", "category"];   // dependen del universo de cada página
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const blank = () => { const s = {}; NAMES.forEach(n => { s[n] = PER_PAGE.includes(n) ? {} : ALL; }); return s; };

  const F = {
    page: "tesoreria",
    state: blank(),
    listeners: [],
    init() {
      try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s) this.state = Object.assign(blank(), s); } catch (e) { /* almacenamiento no disponible */ }
      this.render();
    },
    save() { try { localStorage.setItem(KEY, JSON.stringify(this.state)); } catch (e) { /* ignorar */ } },
    onChange(fn) { this.listeners.push(fn); },
    emit() { this.save(); this.render(); this.listeners.forEach(fn => fn()); },
    applies(name) { return (APPLIES[this.page] || []).includes(name); },
    get(name) {
      if (!this.applies(name)) return ALL;
      const v = this.state[name];
      return PER_PAGE.includes(name) ? ((v && v[this.page]) || ALL) : v;
    },
    set(name, value) {
      if (PER_PAGE.includes(name)) this.state[name][this.page] = value; else this.state[name] = value;
      if (name === "year" || name === "quarter") this.state.month = ALL;
      if (name === "bank") { this.state.product[this.page] = ALL; this.state.card = ALL; }
      if (name === "product") this.state.card = ALL;
      this.emit();
    },
    reset() { this.state = blank(); this.emit(); },
    monthLabel(m) { const x = /^(\d{4})-(\d{2})$/.exec(m || ""); return x ? `${MESES[Number(x[2]) - 1]}-${x[1]}` : m; },

    /* ---------- opciones desde los datos ---------- */
    options(name) {
      const D = window.Data, P = this.page;
      const y = this.state.year, q = this.state.quarter;
      const qn = r => r.Trimestre_n !== undefined ? r.Trimestre_n : (typeof r.Trimestre === "number" ? r.Trimestre : Number(String(r.Trimestre || "").replace("Q", "")));
      const okYQ = r => (!y || String(r.Año) === y) && (!q || String(qn(r)) === q);
      const b = this.get("bank"), p = this.get("product");
      const srcRows = () => P === "tarjetas" ? D.cc.transactions : P === "bancos" ? D.bank.transactions : P === "productos" ? D.pu.monthly : [];
      switch (name) {
        case "year": return D.years.map(v => [String(v), String(v)]);
        case "quarter": {
          const qs = new Set();
          D.cc.transactions.forEach(t => { if (!y || String(t.Año) === y) qs.add(t.Trimestre); });
          D.bank.transactions.forEach(m => { if (!y || String(m.Año) === y) qs.add(m.Trimestre_n); });
          D.exceptions.forEach(e => { if (!y || String(e.Año) === y) (e.quarter_span || []).forEach(t => qs.add(t)); });
          return [...qs].filter(Boolean).sort().map(v => [String(v), "Q" + v]);
        }
        case "month": {
          const ms = new Set();
          D.cc.transactions.forEach(t => { if (okYQ(t)) ms.add(t.Mes); });
          D.bank.transactions.forEach(m => { if (okYQ(m)) ms.add(m.Mes); });
          return [...ms].filter(Boolean).sort().map(v => [v, this.monthLabel(v)]);
        }
        case "bank":
          if (P === "excepciones") return D.uniq(D.exceptions.map(e => e.Banco)).sort().map(v => [v, v]);
          return D.uniq(srcRows().map(r => r.Banco)).sort().map(v => [v, v]);
        case "product": {
          const key = P === "bancos" ? "Cuenta" : "Producto";
          const N = window.Names;
          return D.uniq(srcRows().filter(r => !b || r.Banco === b).map(r => r[key])).map(v => [v, N ? N.full(v) : v]).sort((x, y) => x[1].localeCompare(y[1], "es"));
        }
        case "card": return D.uniq(D.cc.transactions.filter(t => (!b || t.Banco === b) && (!p || t.Producto === p)).map(t => t.Tarjeta)).sort().map(v => [v, "*" + v]);
        case "category":
          if (P === "excepciones") return D.uniq(D.exceptions.map(e => e.Categoría)).sort().map(v => [v, v]);
          return D.uniq(D.cc.transactions.map(t => t.Categoría)).sort().map(v => [v, v]);
        case "flow": return D.uniq(D.bank.transactions.map(m => m["Flujo económico"])).sort().map(v => [v, v]);
        case "source": return [["Credit Card", "Tarjetas de crédito"], ["Bank & Cash", "Bancos y efectivo"]];
        case "risk": return D.riskOrder.filter(r => D.exceptions.some(e => e.Riesgo === r)).map(v => [v, v]);
        case "status": {
          const st = D.uniq(D.exceptions.map(e => e.Estado)).sort();
          return [["__open", "Abiertas (Open + Review)"], ["__notopen", "No abiertas"]].concat(st.map(v => [v, v]));
        }
      }
      return [];
    },
    render() {
      const host = document.getElementById("filters");
      if (!host || !window.Data || !window.Data.ready) return;
      const esc = Data.fmt.esc;
      host.innerHTML = NAMES.filter(n => !["year", "quarter"].includes(n)).map(n => {
        const ap = this.applies(n);
        const cur = ap ? this.get(n) : ALL;
        const opts = ap ? this.options(n) : [];
        const valid = !cur || opts.some(o => o[0] === cur);
        return `<div class="f ${ap ? "" : "na"}"><label for="f-${n}">${LABELS[n]}</label>
          <select id="f-${n}" data-f="${n}" ${ap ? "" : "disabled"}>
            <option value="">${ap ? "Todos" : "—"}</option>
            ${opts.map(o => `<option value="${esc(o[0])}" ${o[0] === cur ? "selected" : ""}>${esc(o[1])}</option>`).join("")}
            ${!valid ? `<option value="${esc(cur)}" selected>${esc(cur)} (sin datos)</option>` : ""}
          </select></div>`;
      }).join("") + `<button class="reset" id="f-reset" type="button">Limpiar filtros</button><div class="filter-note" id="filter-note"></div>`;
      host.querySelectorAll("select[data-f]").forEach(s => s.addEventListener("change", e => this.set(e.target.dataset.f, e.target.value)));
      host.querySelector("#f-reset").addEventListener("click", () => this.reset());
    },
    note(text) { const n = document.getElementById("filter-note"); if (n) n.textContent = text || ""; },

    /* ---------- aplicación (solo filtra) ---------- */
    _yq(r, opt) {
      const y = this.get("year"), q = this.get("quarter"), m = this.get("month");
      const qn = r.Trimestre_n !== undefined ? r.Trimestre_n : (typeof r.Trimestre === "number" ? r.Trimestre : Number(String(r.Trimestre || "").replace("Q", "")));
      if (y && !opt.ignoreYear && String(r.Año) !== y) return false;
      if (q && !opt.ignoreQuarter && String(qn) !== q) return false;
      if (m && !opt.ignoreMonth && r.Mes && r.Mes !== m) return false;
      return true;
    },
    tcRows(rows, opt = {}) {
      const D = window.Data, b = this.get("bank"), p = this.get("product"), c = this.get("card"), cat = this.get("category");
      return rows.filter(r => {
        if (!this._yq(r, opt)) return false;
        const bank = r.Banco !== undefined ? r.Banco : (D.cardByProduct[r.Producto] || {})["Banco base"];
        if (b && bank !== b) return false;
        if (p && r.Producto !== p) return false;
        if (c && r.Tarjeta !== undefined && String(r.Tarjeta).replace("*", "") !== c) return false;
        if (cat && !opt.ignoreCategory && r.Categoría !== undefined && r.Categoría !== cat) return false;
        return true;
      });
    },
    bankRows(rows, opt = {}) {
      const b = this.get("bank"), a = this.get("product"), fl = this.get("flow");
      return rows.filter(r => {
        if (!this._yq(r, opt)) return false;
        if (b && r.Banco !== undefined && r.Banco !== b) return false;
        if (a && r.Cuenta !== undefined && r.Cuenta !== a) return false;
        if (fl && !opt.ignoreFlow && r["Flujo económico"] !== undefined && r["Flujo económico"] !== fl) return false;
        return true;
      });
    },
    puRows(rows, opt = {}) {
      const b = this.get("bank"), p = this.get("product");
      return rows.filter(r => this._yq(r, opt) && (!b || r.Banco === b) && (!p || r.Producto === p));
    },
    excRows(list, opt = {}) {
      const D = window.Data;
      const y = this.get("year"), q = this.get("quarter"), s = opt.source || this.get("source"), r = this.get("risk"), st = this.get("status");
      const b = this.get("bank"), a = this.get("product"), cat = this.get("category"), card = this.get("card");
      return list.filter(e => {
        if (y && !opt.ignoreYear && String(e.Año) !== y) return false;
        if (q && !opt.ignoreQuarter && !(e.quarter_span || e.quarter_tags || []).includes(Number(q))) return false;
        if (s && e.Source !== s) return false;
        if (r && e.Riesgo !== r) return false;
        if (st === "__open" && !e.is_open) return false;
        if (st === "__notopen" && e.is_open) return false;
        if (st && st[0] !== "_" && e.Estado !== st) return false;
        if (this.page === "excepciones") {
          if (b && e.Banco !== b) return false;
          if (cat && e.Categoría !== cat) return false;
        }
        if (this.page === "tarjetas") {
          if (card && !String(e["Cuenta/Tarjeta"] || "").includes(card) && !(D.excByProduct[a] && D.excByProduct[a].has(e.ID))) return false;
          if (a && !D.excLinkedToCard(e, a)) return false;
          if (b && !a) { const prods = D.uniq(D.cc.transactions.filter(t => t.Banco === b).map(t => t.Producto)); if (!prods.some(p => D.excLinkedToCard(e, p)) && e.Banco !== b) return false; }
        }
        if (this.page === "bancos") {
          if (a && !D.excLinkedToAccount(e, a)) return false;
          if (b && !a && !(e.Banco || "").includes(b) && !String(e["Cuenta/Tarjeta"] || "").includes(b)) return false;
        }
        return true;
      });
    },
    describe() {
      const parts = [];
      NAMES.forEach(n => {
        const v = this.get(n); if (!v) return;
        parts.push(n === "quarter" ? "Q" + v : n === "month" ? this.monthLabel(v) : n === "card" ? "*" + v :
          n === "product" && window.Names ? window.Names.name(v) : n === "status" ? ({ __open: "Abiertas", __notopen: "No abiertas" }[v] || v) : n === "source" ? ({ "Credit Card": "Tarjetas", "Bank & Cash": "Bancos" }[v] || v) : v);
      });
      return parts.length ? parts.join(" · ") : "Todos los períodos";
    }
  };
  window.Filters = F;
})();

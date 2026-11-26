/* tables.js — tabla ligera ordenable / con búsqueda / paginada (vanilla, sin dependencias). */
(function () {
  "use strict";
  const state = {};
  const T = {
    render(hostId, cfg) {
      const host = document.getElementById(hostId); if (!host) return;
      const st = state[hostId] = state[hostId] || { sort: cfg.sort || null, page: 0, q: "", open: new Set() };
      if (cfg.resetPage) st.page = 0;
      const esc = Data.fmt.esc;
      let rows = cfg.rows.slice();
      if (cfg.search && st.q) {
        const q = st.q.toLowerCase();
        rows = rows.filter(r => cfg.columns.some(c => String(c.text ? c.text(r) : (r[c.key] ?? "")).toLowerCase().includes(q))
          || (cfg.searchExtra && cfg.searchExtra(r).toLowerCase().includes(q)));
      }
      if (st.sort) {
        const col = cfg.columns.find(c => c.key === st.sort.key);
        if (col) {
          const sv = col.sortValue || (r => r[col.key]);
          const dir = st.sort.dir === "asc" ? 1 : -1;
          rows.sort((a, b) => {
            const x = sv(a), y = sv(b);
            if (x === y) return 0;
            if (x === null || x === undefined || x === "") return 1;
            if (y === null || y === undefined || y === "") return -1;
            return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "es", { numeric: true })) * dir;
          });
        }
      }
      const total = rows.length;
      const ps = cfg.pageSize || 0;
      const pages = ps ? Math.max(1, Math.ceil(total / ps)) : 1;
      if (st.page >= pages) st.page = pages - 1;
      const view = ps ? rows.slice(st.page * ps, st.page * ps + ps) : rows;
      const cols = cfg.columns;
      const hasDetail = !!cfg.detail;
      const head = `<tr>${hasDetail ? "<th></th>" : ""}${cols.map(c => {
        const s = st.sort && st.sort.key === c.key ? `<span class="arr">${st.sort.dir === "asc" ? "▲" : "▼"}</span>` : "";
        return `<th class="${c.num ? "n" : ""} ${c.nosort ? "" : "sortable"}" data-k="${esc(c.key)}" ${c.title ? `title="${esc(c.title)}"` : ""}>${esc(c.label)}${s}</th>`;
      }).join("")}</tr>`;
      const body = view.map((r, i) => {
        const id = cfg.rowId ? cfg.rowId(r) : String(i);
        const open = st.open.has(id);
        const tr = `<tr class="${cfg.rowClass ? cfg.rowClass(r) : ""}">${hasDetail ? `<td><button class="expand" data-id="${esc(id)}" aria-expanded="${open}" title="Detalle">${open ? "−" : "+"}</button></td>` : ""}${cols.map(c => {
          const v = r[c.key];
          const html = c.html ? c.html(r) : esc(c.fmt ? c.fmt(v, r) : (v ?? ""));
          return `<td class="${c.num ? "n" : ""} ${c.cls || ""}" ${c.tip ? `title="${esc(c.tip(r) || "")}"` : ""}>${html === "" ? '<span class="muted">—</span>' : html}</td>`;
        }).join("")}</tr>`;
        return tr + (hasDetail && open ? `<tr class="detail"><td></td><td colspan="${cols.length}">${cfg.detail(r)}</td></tr>` : "");
      }).join("");
      const foot = cfg.totals ? `<tr class="total">${hasDetail ? "<td></td>" : ""}${cols.map(c => `<td class="${c.num ? "n" : ""}">${cfg.totals(c, rows) ?? ""}</td>`).join("")}</tr>` : "";
      const tools = cfg.search || cfg.tools ? `<div class="tbl-tools">${cfg.tools || ""}${cfg.search ? `<div class="f"><label>Buscar</label><input type="search" class="tsearch" value="${esc(st.q)}" placeholder="ID, texto, monto…"></div>` : ""}<span class="count">${total} registro${total === 1 ? "" : "s"}</span></div>` : "";
      host.innerHTML = tools + `<div class="tbl-wrap"><table class="t"><thead>${head}</thead><tbody>${body || `<tr><td colspan="${cols.length + (hasDetail ? 1 : 0)}" class="empty">Sin registros para los filtros actuales.</td></tr>`}${foot}</tbody></table></div>` +
        (ps && pages > 1 ? `<div class="pager"><button data-p="prev" ${st.page === 0 ? "disabled" : ""}>‹ Anterior</button><span>Página ${st.page + 1} / ${pages}</span><button data-p="next" ${st.page >= pages - 1 ? "disabled" : ""}>Siguiente ›</button></div>` : "");
      host.querySelectorAll("th.sortable").forEach(th => th.addEventListener("click", () => {
        const k = th.dataset.k;
        st.sort = st.sort && st.sort.key === k ? { key: k, dir: st.sort.dir === "asc" ? "desc" : "asc" } : { key: k, dir: cols.find(c => c.key === k).num ? "desc" : "asc" };
        T.render(hostId, cfg);
      }));
      host.querySelectorAll("button.expand").forEach(b => b.addEventListener("click", () => {
        const id = b.dataset.id; st.open.has(id) ? st.open.delete(id) : st.open.add(id); T.render(hostId, cfg);
      }));
      host.querySelectorAll(".pager button").forEach(b => b.addEventListener("click", () => { st.page += b.dataset.p === "next" ? 1 : -1; T.render(hostId, cfg); }));
      const s = host.querySelector(".tsearch");
      if (s) s.addEventListener("input", e => { st.q = e.target.value; st.page = 0; const pos = e.target.selectionStart; T.render(hostId, cfg); const n = host.querySelector(".tsearch"); n.focus(); n.setSelectionRange(pos, pos); });
      if (cfg.after) cfg.after(host);
    },
    clearSort(hostId) { if (state[hostId]) state[hostId].sort = null; }
  };
  window.Tables = T;
})();

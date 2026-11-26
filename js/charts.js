/* charts.js — envoltorios sobrios de Chart.js. Un eje Y por gráfico; colores desde los tokens CSS. */
(function () {
  "use strict";
  const inst = {};
  if (window.Chart) { Chart.defaults.font.family = getComputedStyle(document.body || document.documentElement).fontFamily || "Calibri, Arial, sans-serif"; Chart.defaults.color = "#6b6b66"; }
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function base(yFmt) {
    const ink2 = css("--ink-2"), grid = css("--grid");
    return {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: css("--ink"), titleColor: css("--surface"), bodyColor: css("--surface"), padding: 8, boxPadding: 4,
          callbacks: { label: c => ` ${c.dataset.label}: ${yFmt(c.parsed.y !== undefined && c.chart.config.options.indexAxis !== "y" ? c.parsed.y : c.parsed.x)}` }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: ink2, font: { size: 11 } }, border: { color: css("--border-strong") } },
        y: { grid: { color: grid }, border: { display: false }, ticks: { color: ink2, font: { size: 11 }, callback: v => yFmt(v) } }
      }
    };
  }
  const C = {
    css,
    destroy(id) { if (inst[id]) { inst[id].destroy(); delete inst[id]; } },
    empty(id, msg) {
      this.destroy(id);
      const cv = document.getElementById(id); if (!cv) return;
      const box = cv.parentElement; box.querySelectorAll(".empty").forEach(n => n.remove());
      cv.style.display = "none";
      box.insertAdjacentHTML("beforeend", `<div class="empty">${msg || "Sin datos suficientes para los filtros actuales."}</div>`);
    },
    _prep(id) {
      this.destroy(id);
      const cv = document.getElementById(id); if (!cv) return null;
      cv.style.display = ""; cv.parentElement.querySelectorAll(".empty").forEach(n => n.remove());
      return cv;
    },
    bar(id, labels, datasets, opt = {}) {
      const cv = this._prep(id); if (!cv) return;
      const fmt = opt.fmt || Data.fmt.copShort;
      const o = base(fmt);
      if (opt.stacked) { o.scales.x.stacked = true; o.scales.y.stacked = true; }
      if (opt.horizontal) {
        o.indexAxis = "y";
        o.scales = { x: Object.assign(o.scales.y, { stacked: !!opt.stacked }), y: Object.assign(o.scales.x, { stacked: !!opt.stacked, ticks: { color: css("--ink-2"), font: { size: 11 }, autoSkip: false } }) };
        o.plugins.tooltip.callbacks.label = c => ` ${c.dataset.label}: ${fmt(c.parsed.x)}`;
      }
      inst[id] = new Chart(cv, {
        type: "bar",
        data: { labels, datasets: datasets.map(d => Object.assign({ borderRadius: 0, borderSkipped: "start", maxBarThickness: opt.horizontal ? 16 : 30,
          borderColor: css("--surface"), borderWidth: opt.stacked ? { top: 0, bottom: 0, left: opt.horizontal ? 0 : 0, right: opt.horizontal ? 2 : 0 } : 0 }, d)) },
        options: o
      });
    },
    line(id, labels, datasets, opt = {}) {
      const cv = this._prep(id); if (!cv) return;
      const o = base(opt.fmt || Data.fmt.copShort);
      if (opt.beginAtZero === false) o.scales.y.beginAtZero = false;
      inst[id] = new Chart(cv, {
        type: "line",
        data: { labels, datasets: datasets.map(d => Object.assign({ borderWidth: 1.5, pointRadius: 2, pointHoverRadius: 4, tension: 0, fill: false, spanGaps: false }, d)) },
        options: o
      });
    },
    combo(id, labels, bars, lineDs, opt = {}) {
      const cv = this._prep(id); if (!cv) return;
      const o = base(opt.fmt || Data.fmt.copShort);
      inst[id] = new Chart(cv, {
        data: { labels, datasets: bars.map(d => Object.assign({ type: "bar", borderRadius: 0, maxBarThickness: 22 }, d))
          .concat(lineDs.map(d => Object.assign({ type: "line", borderWidth: 2, pointRadius: 3, tension: 0 }, d))) },
        options: o
      });
    },
    scatter(id, pts, opt = {}) {
      const cv = this._prep(id); if (!cv) return;
      const f = Data.fmt.copShort, ink2 = css("--ink-2"), grid = css("--grid");
      const mx = Math.max(1, ...pts.map(p => Math.max(p.x, p.y))) * 1.08;
      inst[id] = new Chart(cv, {
        type: "scatter",
        data: { datasets: [
          { label: "Equilibrio (beneficio = costo)", data: [{ x: 0, y: 0 }, { x: mx, y: mx }], type: "line", borderColor: css("--border-strong"), borderDash: [4, 4], borderWidth: 1, pointRadius: 0 },
          { label: "Productos", data: pts, pointRadius: 6, pointHoverRadius: 8, backgroundColor: pts.map(p => p.net >= 0 ? css("--ok-mark") : css("--high")) }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false,
          plugins: { legend: { display: false }, tooltip: { backgroundColor: css("--ink"), titleColor: css("--surface"), bodyColor: css("--surface"), padding: 8,
            filter: c => c.datasetIndex === 1, callbacks: { title: c => c[0].raw.label, label: c => [` Costos: ${f(c.raw.x)}`, ` Beneficios: ${f(c.raw.y)}`, ` Valor neto: ${f(c.raw.net)}`] } } },
          scales: { x: { min: 0, max: mx, title: { display: !!opt.xTitle, text: opt.xTitle, color: ink2 }, grid: { color: grid }, ticks: { color: ink2, font: { size: 11 }, callback: v => f(v) } },
                    y: { min: 0, max: mx, title: { display: !!opt.yTitle, text: opt.yTitle, color: ink2 }, grid: { color: grid }, ticks: { color: ink2, font: { size: 11 }, callback: v => f(v) } } } },
        plugins: [{ id: "lbl", afterDatasetsDraw(ch) { const ctx = ch.ctx; ctx.save(); ctx.font = "11px sans-serif"; ctx.fillStyle = ink2;
          ch.getDatasetMeta(1).data.forEach((pt, i) => { const p = pts[i]; if (p.x || p.y) ctx.fillText(p.label.replace(/^(Bancolombia|Banco de) /, "").slice(0, 26), pt.x + 8, pt.y - 6); }); ctx.restore(); } }]
      });
    },
    legend(items) {
      return `<div class="legend">${items.map(i => `<span><i class="${i.line ? "line" : ""}" style="background:${i.color}"></i>${Data.fmt.esc(i.label)}</span>`).join("")}</div>`;
    }
  };
  window.Charts = C;
})();

/* names.js — nombres de presentación de tarjetas y cuentas (solo vocabulario visual).
   Los libros Excel y los JSON conservan el nombre con número; el dashboard muestra el nombre comercial
   y deja el número como referencia. Para agregar un producto: una fila con los últimos 4 dígitos
   que aparecen en el nombre del libro (todos los números históricos del plástico). */
(function () {
  "use strict";
  const ROWS = [
    // tarjetas de crédito
    { t: ["6907"], name: "Visa Infinite", bank: "Bancolombia", ref: "*6907", kind: "tc" },
    { t: ["7744"], name: "Mastercard Única Virtual", bank: "Bancolombia", ref: "*7744", kind: "tc" },
    { t: ["7935"], name: "Amex Blue", bank: "Bancolombia", ref: "*7935", kind: "tc" },
    { t: ["8457", "8357"], name: "Mastercard E-Card", bank: "Bancolombia", ref: "*8457", kind: "tc" },
    { t: ["5933", "7239"], name: "Itaú Visa Gold (cerrada)", bank: "Itaú", ref: "*5933", kind: "tc" },
    { t: ["6931"], name: "Banco de Bogotá Mastercard Oro", bank: "Banco de Bogotá", ref: "*6931", kind: "tc" },
    { t: ["7547"], name: "Credencial Occidente", bank: "Banco de Occidente", ref: "*7547", kind: "tc" },
    { t: ["2214", "1335"], name: "RappiCard Visa", bank: "RappiPay", ref: "*2214", kind: "tc" },
    { t: ["3910"], name: "Nu Mastercard Platinum", bank: "Nu", ref: "*3910", kind: "tc" },
    { t: ["7874"], name: "CMR Falabella", bank: "Banco Falabella", ref: "*7874", kind: "tc" },
    { t: ["8689", "5268"], name: "Tuya Mastercard", bank: "Tuya", ref: "*8689", kind: "tc" },
    { t: ["0422", "8258"], name: "Amex Platinum (cancelada)", bank: "Bancolombia", ref: "*0422", kind: "tc" },
    { t: ["8789"], name: "Mastercard Black (cancelada)", bank: "Bancolombia", ref: "*8789", kind: "tc" },
    // cuentas
    { t: ["9910"], name: "Ahorros Bancolombia", bank: "Bancolombia", ref: "*9910", kind: "cuenta" },
    { t: ["6191"], name: "Fiducuenta *6191", bank: "Fiduciaria Bancolombia", ref: "*6191", kind: "fiducuenta" },
    { t: ["0934"], name: "Fiducuenta *0934", bank: "Fiduciaria Bancolombia", ref: "*0934", kind: "fiducuenta" },
    { t: ["0452"], name: "Fiducuenta *0452", bank: "Fiduciaria Bancolombia", ref: "*0452", kind: "fiducuenta" },
    { t: ["6818"], name: "Ahorros Banco de Bogotá *6818", bank: "Banco de Bogotá", ref: "*6818", kind: "cuenta" },
    { t: ["7068"], name: "Ahorros Banco de Bogotá *7068", bank: "Banco de Bogotá", ref: "*7068", kind: "cuenta" },
    { t: ["0324"], name: "Ahorros Davibank *0324", bank: "Davibank", ref: "*0324", kind: "cuenta" }
  ];
  const cache = new Map();
  function find(raw) {
    const s = String(raw || "");
    if (cache.has(s)) return cache.get(s);
    const digits = s.match(/\d{4}/g) || [];
    const row = ROWS.find(r => r.t.some(t => digits.includes(t))) || null;
    cache.set(s, row);
    return row;
  }
  function suffix(raw) { return /saldo USD/i.test(String(raw || "")) ? " (USD)" : ""; }
  window.Names = {
    rows: ROWS,
    find,
    /* nombre comercial; si no hay alias, el texto original sin paréntesis de número */
    name(raw) { const r = find(raw); return r ? r.name + suffix(raw) : String(raw || ""); },
    ref(raw) { const r = find(raw); return r ? r.ref : ""; },
    full(raw) { const r = find(raw); return r ? `${r.name}${suffix(raw)} · ${r.ref}` : String(raw || ""); },
    /* reemplaza dentro de un texto libre (p. ej. "Itaú TC (*7239→*5933); Occidente Credencial (*7547)") */
    text(raw) {
      const str = String(raw || ""), digits = str.match(/\d{4}/g) || [], hit = [];
      digits.forEach(d => { const r = ROWS.find(x => x.t.includes(d)); if (r && !hit.includes(r)) hit.push(r); });
      return hit.length ? hit.map(r => r.name).join(", ") : str;
    }
  };
})();

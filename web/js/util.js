// أدوات عامة: التواريخ، المفاتيح الفريدة، تسميات الأنواع.
import { move } from "./keynav.js";

export function today() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function monthStart() {
  return today().slice(0, 8) + "01";
}

export function yearStart() {
  return today().slice(0, 4) + "-01-01";
}

/** مفتاح فريد لكل عملية (يمنع الترحيل المكرر حتى لو أعيد إرسال الطلب). */
export function newToken() {
  if (crypto.randomUUID) return crypto.randomUUID().replace(/-/g, "");
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function fmtDateTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export const DOC_LABEL = {
  sale: "فاتورة مبيعات",
  return: "مرتجع مبيعات",
  receipt: "سند قبض",
  payment: "سند صرف",
  opening: "رصيد افتتاحي",
};

export const MATERIAL_LABEL = { gold: "الذهب", diamond: "الألماس", wage: "الأجور" };
export const MATERIAL_SHORT = { gold: "ذهب", diamond: "ألماس", wage: "أجور" };
export const DIR_LABEL = { debit: "مدين", credit: "دائن", zero: "صفر" };
export const STATUS_LABEL = { debit: "مدين", credit: "دائن", settled: "مسدد", mixed: "مختلط" };

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** قراءة/حفظ آمن في التخزين المحلي (للمسودات والتفضيلات فقط). */
export const local = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem("jadeit:" + key);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem("jadeit:" + key, JSON.stringify(value));
    } catch { /* تجاهل */ }
  },
  remove(key) {
    try { localStorage.removeItem("jadeit:" + key); } catch { /* تجاهل */ }
  },
};

export function parseHashQuery() {
  const h = location.hash || "";
  const i = h.indexOf("?");
  return new URLSearchParams(i >= 0 ? h.slice(i + 1) : "");
}

export function go(route, params = {}) {
  const q = new URLSearchParams(params).toString();
  location.hash = "#/" + route + (q ? "?" + q : "");
}

/** نقل التركيز للخانة التالية/السابقة بنفس قواعد محرك التنقل الموحّد (keynav.js). */
export function focusNext(el, backwards = false) {
  return move(el, backwards ? -1 : 1);
}

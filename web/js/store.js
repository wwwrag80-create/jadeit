// الحالة العامة للتطبيق: المستخدم، الإعدادات، ذاكرة الحسابات، الإشعارات.
import { api } from "./api.js";

const { reactive } = Vue;

export const store = reactive({
  ready: false,
  needsSetup: false,
  me: null,
  settings: { system_name: "", working_karat: 18, wage_unit: "", diamond_unit: "قيراط" },
  permissions: {},
  accounts: [],
  accountsVersion: 0,
  toasts: [],
  // نافذة/لوحة مشتركة تُفتح من أي شاشة
  docViewId: null,
  accountPanelId: null,
  settingsOpen: false,
  karatDialog: false,
  print: null, // { title, pages }
  dataVersion: 0, // يزيد بعد كل ترحيل/تعديل/إلغاء لتحديث الشاشات المفتوحة
});

export function can(perm) {
  return !!store.me && (store.me.is_admin || store.me.permissions.includes(perm));
}

export function applyBoot(data) {
  store.me = data.me;
  store.settings = data.settings;
  store.permissions = data.permissions;
}

export async function loadAccounts() {
  store.accounts = await api.get("/api/accounts");
  store.accountsVersion++;
}

export function accountById(id) {
  return store.accounts.find((a) => a.id === Number(id)) || null;
}

export function dataChanged() {
  store.dataVersion++;
}

let toastSeq = 0;
export function toast(kind, title, body = "", opts = {}) {
  const id = ++toastSeq;
  store.toasts.push({ id, kind, title, body, actions: opts.actions || [] });
  const ms = opts.sticky ? 0 : (opts.duration || (kind === "error" ? 9000 : 5000));
  if (ms) setTimeout(() => dismissToast(id), ms);
  return id;
}

export function dismissToast(id) {
  const i = store.toasts.findIndex((t) => t.id === id);
  if (i >= 0) store.toasts.splice(i, 1);
}

export function toastError(e, title = "تعذر تنفيذ العملية") {
  toast("error", title, e && e.message ? e.message : String(e));
}

export function units() {
  return { gold: "جم", diamond: store.settings.diamond_unit || "قيراط", wage: store.settings.wage_unit || "" };
}

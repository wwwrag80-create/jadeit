// محرك التنقل بلوحة المفاتيح — يعمل في كل الشاشات والنوافذ دون استثناء.
//
//   Enter            ← الخانة التالية (وفي آخر خانة: زر الترحيل/الحفظ، ثم Enter عليه ينفّذ)
//   Shift+Enter      ← الخانة السابقة (وفي الملاحظات متعددة الأسطر: سطر جديد)
//   ↓  /  ↑          ← الخانة التالية / السابقة (وفي الجداول: نفس العمود في السطر التالي/السابق)
//   ←  /  →          ← الخانة التالية / السابقة (الواجهة من اليمين لليسار) عند طرف النص
//   ← → داخل مجموعة أزرار الاختيار (مثل العيار أو نوع المادة) ← تغيير الاختيار
//
// القواعد: مكوّن يعالج المفتاح بنفسه (مثل جدول المبيعات أو منتقي العميل) يستدعي preventDefault
// فيتجاهله هذا المحرك. الخانات للقراءة فقط والمعطّلة والمخفية لا يتوقف عندها التنقل.

const FIELD = "input:not([type=hidden]):not([type=file]):not([disabled]), select:not([disabled]), textarea:not([disabled])";
const CANDIDATES = `${FIELD}, [data-enter-stop], .seg > button`;

function visible(el) {
  if (!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)) return false;
  return getComputedStyle(el).visibility !== "hidden";
}

/** نطاق التنقل: النافذة المفتوحة الأعلى، أو الشاشة الحالية، أو بطاقة الدخول. */
export function scopeOf(el) {
  return (el && el.closest(".modal, .drawer, .login-card, .main")) || document.body;
}

function segRepresentative(seg) {
  const on = seg.querySelector(":scope > button.on:not([disabled])");
  return on || seg.querySelector(":scope > button:not([disabled])");
}

/** كل نقاط التوقف في النطاق بترتيب ظهورها. */
export function stops(scope) {
  const out = [];
  const seenSeg = new Set();
  for (const el of scope.querySelectorAll(CANDIDATES)) {
    if (el.closest("[data-nav-skip]")) continue;
    if (el.matches(".seg > button")) {
      const seg = el.parentElement;
      if (seenSeg.has(seg)) continue;
      const rep = segRepresentative(seg);
      if (!rep || !visible(rep)) continue;
      seenSeg.add(seg);
      out.push(rep);
      continue;
    }
    if (el.tabIndex < 0 || !visible(el)) continue;
    if (el.matches(FIELD) && el.readOnly) continue;
    if (el.matches("[data-enter-stop]") && el.disabled) continue;
    out.push(el);
  }
  return out;
}

function focusEl(el) {
  el.focus();
  if (el.tagName === "INPUT" && el.select && !["checkbox", "radio", "date"].includes(el.type)) {
    try { el.select(); } catch (e) { /* بعض الأنواع لا تدعم التحديد */ }
  }
}

/** ينقل التركيز للخانة التالية (dir=1) أو السابقة (dir=-1). يعيد true إن تحرك. */
export function move(from, dir) {
  const scope = scopeOf(from);
  const list = stops(scope);
  if (!list.length) return false;
  let target = null;
  const seg = from.closest(".seg");
  const idx = list.indexOf(seg ? segRepresentative(seg) : from);
  if (idx >= 0) target = list[idx + dir] || null;
  else {
    // العنصر الحالي ليس نقطة توقف (زر عادي مثلاً): نبحث حسب الموضع في الصفحة
    if (dir > 0) target = list.find((x) => from.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_FOLLOWING) || null;
    else target = list.slice().reverse().find((x) => from.compareDocumentPosition(x) & Node.DOCUMENT_POSITION_PRECEDING) || null;
  }
  if (!target) return false;
  focusEl(target);
  return true;
}

/** هل المؤشر عند طرف النص في اتجاه السهم؟ (← = للأمام في واجهة RTL) */
function atBoundary(el, forward) {
  let s;
  let e;
  try {
    s = el.selectionStart;
    e = el.selectionEnd;
  } catch (err) {
    return true;
  }
  if (s === null || s === undefined) return true;
  const len = el.value.length;
  if (len === 0 || (s === 0 && e === len)) return true;
  if (s !== e) return false;
  const rtl = getComputedStyle(el).direction === "rtl";
  const leftEdge = rtl ? len : 0;
  const rightEdge = rtl ? 0 : len;
  return forward ? s === leftEdge : s === rightEdge;
}

function textareaEdge(el, dir) {
  const s = el.selectionStart;
  return dir > 0 ? el.value.indexOf("\n", s) === -1 : el.value.lastIndexOf("\n", s - 1) === -1;
}

/** تحريك الاختيار داخل مجموعة أزرار (مثل اختيار العيار). */
function segStep(btn, dir) {
  const buttons = Array.from(btn.parentElement.querySelectorAll(":scope > button:not([disabled])"));
  const next = buttons[buttons.indexOf(btn) + dir];
  if (next) {
    next.focus();
    next.click();
  }
}

/** في الجداول المعلّمة data-nav-grid: ↑↓ تنتقل لنفس العمود في السطر المجاور. */
function gridVertical(el, dir) {
  const td = el.closest("td");
  const tr = el.closest("tr");
  if (!td || !tr || !tr.closest("table[data-nav-grid]")) return false;
  const col = Array.prototype.indexOf.call(tr.children, td);
  let row = dir > 0 ? tr.nextElementSibling : tr.previousElementSibling;
  while (row) {
    const cell = row.children[col];
    const target = cell && stops(cell)[0];
    if (target) { focusEl(target); return true; }
    const any = stops(row)[0];
    if (any) { focusEl(any); return true; }
    row = dir > 0 ? row.nextElementSibling : row.previousElementSibling;
  }
  return false;
}

function onKeydown(e) {
  if (e.defaultPrevented || e.isComposing || e.ctrlKey || e.altKey || e.metaKey) return;
  const el = document.activeElement;
  if (!el || el === document.body || !el.closest("#app")) return;
  const tag = el.tagName;
  const isSeg = el.matches(".seg > button");
  const k = e.key;

  if (k === "Enter") {
    if (isSeg) {
      e.preventDefault();
      el.click();
      move(el, e.shiftKey ? -1 : 1);
      return;
    }
    if (tag === "BUTTON" || tag === "A" || tag === "TR") return; // التفعيل الطبيعي (ترحيل، حفظ، فتح…)
    if (tag === "TEXTAREA" && e.shiftKey) return; // سطر جديد في الملاحظات
    if (tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") return;
    e.preventDefault();
    move(el, e.shiftKey ? -1 : 1);
    return;
  }

  if (k === "ArrowDown" || k === "ArrowUp") {
    const dir = k === "ArrowDown" ? 1 : -1;
    if (tag === "TEXTAREA" && !textareaEdge(el, dir)) return;
    if (!(tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA" || tag === "BUTTON" || tag === "TR")) return;
    e.preventDefault();
    if (gridVertical(el, dir)) return;
    move(el, dir);
    return;
  }

  if (k === "ArrowLeft" || k === "ArrowRight") {
    const forward = k === "ArrowLeft"; // الواجهة من اليمين لليسار: اليسار = التالي
    if (isSeg) {
      e.preventDefault();
      segStep(el, forward ? 1 : -1);
      return;
    }
    if (tag === "INPUT" && el.type === "date") return; // الأسهم تتنقل بين اليوم/الشهر/السنة
    if (tag === "SELECT" || tag === "BUTTON" || (tag === "INPUT" && (el.type === "checkbox" || el.type === "radio"))) {
      e.preventDefault();
      move(el, forward ? 1 : -1);
      return;
    }
    if ((tag === "INPUT" || tag === "TEXTAREA") && atBoundary(el, forward)) {
      e.preventDefault();
      move(el, forward ? 1 : -1);
    }
  }
}

let installed = false;
export function installKeyNav() {
  if (installed) return;
  installed = true;
  document.addEventListener("keydown", onKeydown);
}

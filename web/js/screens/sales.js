// الشاشة الثانية: المبيعات والمرتجعات — إدخال سريع لعدد كبير من الأسطر ثم ترحيل المستند مرة واحدة.
import { api, postWithRetry } from "../api.js";
import { store, can, toast, toastError, dataChanged, accountById, units } from "../store.js";
import { parse, fmt, fmtRate, wageTotal, fromStr, group } from "../num.js";
import { today, newToken, parseHashQuery, go, local, debounce, DOC_LABEL } from "../util.js";
import { DocSearch } from "../components/docs.js";
import { PostSummary, LastPosted } from "../components/post.js";
import { openPreview, docSpec } from "../components/print.js";
import { move } from "../keynav.js";

const { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;
let keySeq = 0;

export const SalesScreen = {
  name: "SalesScreen",
  components: { DocSearch, PostSummary, LastPosted },
  setup() {
    const mode = ref("sale");
    const accountId = ref(null);
    const account = ref(null); // بيانات حديثة من الخادم
    const date = ref(today());
    const notes = ref("");
    const description = ref("");
    const lines = ref([]);
    const token = ref(newToken());
    const nextNo = ref("");
    const linkMode = ref("linked");
    const originalId = ref(null);
    const exceptionReason = ref("");
    const invoices = ref([]);
    const invoiceFilter = ref("");
    const returnable = ref(null);
    const editDoc = ref(null);
    const showOriginalSnapshot = ref(false);
    const preview = ref(null);
    const busy = ref(false);
    const checking = ref(false);
    const lastPosted = ref(null);
    const showSearch = ref(false);
    const serverLineErrors = ref({});
    const activeRow = ref(0);
    const grid = ref(null);
    const picker = ref(null);
    const postBtn = ref(null);
    const u = computed(units);

    const canOverride = computed(() => can("docs.rate_override"));
    const canUnlinked = computed(() => can("docs.unlinked_return"));
    const canPost = computed(() => (editDoc.value ? can("docs.edit") : can("docs.post")));
    const isReturn = computed(() => mode.value === "return");
    const linked = computed(() => isReturn.value && linkMode.value === "linked");
    const defaultRate = computed(() => (account.value ? account.value.wage_rate : ""));
    const workingKarat = computed(() => (editDoc.value ? editDoc.value.working_karat : store.settings.working_karat));

    function newLine(extra = {}) {
      return { key: ++keySeq, id: null, run_no: "", gold: "", diamond: "", rate: defaultRate.value, rateTouched: false, original_line_id: null, ...extra };
    }
    function resetLines() { lines.value = [newLine()]; }

    // ------------------------------------------------------------ الحساب
    async function refreshAccount() {
      if (!accountId.value) { account.value = null; return; }
      try {
        account.value = await api.get(`/api/accounts/${accountId.value}`);
      } catch (e) { toastError(e); }
    }
    watch(accountId, async (id, old) => {
      await refreshAccount();
      if (!editDoc.value) {
        for (const l of lines.value) if (!l.id && !l.rateTouched) l.rate = defaultRate.value;
        if (old !== null && old !== undefined && id !== old && isReturn.value) { originalId.value = null; returnable.value = null; if (linked.value) resetLines(); }
      }
      if (isReturn.value) loadInvoices();
    });
    watch(mode, (m) => {
      if (editDoc.value) return;
      originalId.value = null;
      returnable.value = null;
      exceptionReason.value = "";
      if (m === "return") { linkMode.value = "linked"; loadInvoices(); resetLines(); }
      refreshNextNo();
    });
    watch(linkMode, () => { if (!editDoc.value) { originalId.value = null; returnable.value = null; resetLines(); } });

    async function loadInvoices() {
      if (!accountId.value || !isReturn.value) { invoices.value = []; return; }
      try { invoices.value = await api.get(`/api/accounts/${accountId.value}/sale-invoices`); } catch (e) { toastError(e); }
    }
    const invoiceOptions = computed(() => {
      const t = invoiceFilter.value.trim().toUpperCase();
      return invoices.value.filter((i) => (i.has_remaining || i.id === originalId.value) && (!t || i.doc_no.includes(t)));
    });
    let keepLinesOnce = false; // عند استعادة مسودة لا نمسح الأسطر المستعادة
    watch(originalId, async (id) => {
      if (!id) { returnable.value = null; return; }
      const keep = keepLinesOnce;
      keepLinesOnce = false;
      try {
        returnable.value = await api.get(`/api/documents/${id}/returnable`, { exclude: editDoc.value ? editDoc.value.id : "" });
        if (!editDoc.value && !keep) resetLinesForReturn();
      } catch (e) { toastError(e); }
    });
    function resetLinesForReturn() { lines.value = []; }
    const origById = computed(() => {
      const m = {};
      if (returnable.value) for (const l of returnable.value.lines) m[l.id] = l;
      return m;
    });
    function addOriginal(ol, full = true) {
      if (lines.value.some((l) => l.original_line_id === ol.id)) {
        toast("warning", "السطر مضاف مسبقاً", `رقم التشغيل ${ol.run_no || ol.line_no}`);
        return;
      }
      lines.value = lines.value.filter((l) => l.original_line_id || l.run_no || l.gold || l.diamond);
      lines.value.push(newLine({ run_no: ol.run_no, original_line_id: ol.id, rate: ol.rate,
        gold: full ? ol.remaining.gold : "", diamond: full ? ol.remaining.diamond : "" }));
    }
    function addAllRemaining() {
      if (!returnable.value) return;
      for (const ol of returnable.value.lines) if (!ol.fully_returned) addOriginal(ol, true);
    }

    // ------------------------------------------------------------ الحساب الفوري لكل سطر
    const calc = computed(() => lines.value.map((l, i) => {
      const out = { empty: false, err: "", gold: 0n, diamond: 0n, wage: 0n, rate: 0n };
      const g = parse(l.gold, 4), d = parse(l.diamond, 3), r = parse(l.rate, 3);
      out.empty = !l.original_line_id && !String(l.run_no).trim() && g.empty && d.empty;
      if (out.empty) return out;
      if (!g.ok) out.err = "الذهب: " + g.error;
      else if (!d.ok) out.err = "الألماس: " + d.error;
      else if (!r.ok) out.err = "الأجر: " + r.error;
      if (out.err) return out;
      out.gold = g.value; out.diamond = d.value; out.rate = r.value;
      if (g.value === 0n && d.value === 0n) out.err = "أدخل وزن الذهب أو الألماس";
      if (linked.value) {
        const ol = origById.value[l.original_line_id];
        if (!ol) { out.err = "اختر سطر الفاتورة الأصلية"; return out; }
        const remG = fromStr(ol.remaining.gold), remD = fromStr(ol.remaining.diamond), remW = fromStr(ol.remaining.wage);
        if (g.value > remG) out.err = `الذهب أكبر من المتبقي (${ol.remaining.gold})`;
        else if (d.value > remD) out.err = `الألماس أكبر من المتبقي (${ol.remaining.diamond})`;
        const w = wageTotal(g.value, r.value);
        out.wage = g.value > 0n && g.value === remG ? remW : (w < remW ? w : remW);
      } else {
        out.wage = wageTotal(g.value, r.value);
        const run = String(l.run_no).trim().toLowerCase();
        if (run && lines.value.some((o, j) => j < i && String(o.run_no).trim().toLowerCase() === run)) out.err = `رقم التشغيل «${l.run_no}» مكرر`;
      }
      if (serverLineErrors.value[i] && !out.err) out.err = serverLineErrors.value[i];
      return out;
    }));
    const totals = computed(() => {
      let g = 0n, d = 0n, w = 0n, n = 0;
      calc.value.forEach((c) => { if (!c.empty) { n++; g += c.gold; d += c.diamond; w += c.wage; } });
      return { gold: fmt(g, 4), diamond: fmt(d, 3), wage: fmt(w, 2), lines: n };
    });
    const errorCount = computed(() => calc.value.filter((c) => !c.empty && c.err).length);
    watch(lines, () => { serverLineErrors.value = {}; }, { deep: true });

    // ------------------------------------------------------------ لوحة المفاتيح داخل الجدول
    const cols = computed(() => {
      if (linked.value) return ["gold", "diamond"];
      return canOverride.value ? ["run_no", "gold", "diamond", "rate"] : ["run_no", "gold", "diamond"];
    });
    function focusCell(row, col) {
      nextTick(() => {
        const el = grid.value && grid.value.querySelector(`[data-row="${row}"][data-col="${col}"]`);
        if (el) { el.focus(); if (el.select) el.select(); }
      });
    }
    function addLine(focus = true) {
      lines.value.push(newLine());
      if (focus) focusCell(lines.value.length - 1, cols.value[0]);
    }
    function removeLine(i) {
      lines.value.splice(i, 1);
      if (!lines.value.length && !linked.value) lines.value.push(newLine());
      focusCell(Math.min(i, lines.value.length - 1), cols.value[0]);
    }
    // هل المؤشر عند طرف النص في اتجاه السهم؟ (في الجدول: ← العمود التالي، → العمود السابق)
    function atEdge(el, forward) {
      let s, en;
      try { s = el.selectionStart; en = el.selectionEnd; } catch (err) { return true; }
      if (s === null || s === undefined) return true;
      const len = el.value.length;
      if (len === 0 || (s === 0 && en === len)) return true;
      if (s !== en) return false;
      const rtl = getComputedStyle(el).direction === "rtl";
      return forward ? s === (rtl ? len : 0) : s === (rtl ? 0 : len);
    }
    function focusPost() { nextTick(() => postBtn.value && postBtn.value.focus()); }
    function leaveGridUp(el) {
      const first = grid.value && grid.value.querySelector(`[data-row="0"][data-col="${cols.value[0]}"]`);
      move(first || el, -1);
    }
    function onGridKey(e) {
      const t = e.target;
      const row = Number(t.dataset.row), col = t.dataset.col;
      if (Number.isNaN(row) || !col || e.altKey || e.metaKey) return;
      const ci = cols.value.indexOf(col);
      const last = row === lines.value.length - 1;
      const hasLines = calc.value.some((c) => !c.empty);
      if (e.key === "Enter" && !e.ctrlKey) {
        e.preventDefault();
        if (e.shiftKey) {
          if (ci > 0) return focusCell(row, cols.value[ci - 1]);
          if (row > 0) return focusCell(row - 1, cols.value[cols.value.length - 1]);
          return leaveGridUp(t);
        }
        // سطر فارغ في نهاية الجدول + Enter ← الانتقال لزر الترحيل (ثم Enter للترحيل)
        if (last && calc.value[row].empty && hasLines) return focusPost();
        if (ci < cols.value.length - 1) return focusCell(row, cols.value[ci + 1]);
        if (!last) return focusCell(row + 1, cols.value[0]);
        if (linked.value) return focusPost();
        if (!calc.value[row].empty) addLine();
      } else if (e.key === "ArrowDown" && !e.ctrlKey) {
        e.preventDefault();
        if (!last) focusCell(row + 1, col);
        else if (!linked.value && !calc.value[row].empty) { lines.value.push(newLine()); focusCell(row + 1, col); }
        else focusPost();
      } else if (e.key === "ArrowUp" && !e.ctrlKey) {
        e.preventDefault();
        if (row > 0) focusCell(row - 1, col);
        else leaveGridUp(t);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && !e.ctrlKey && !e.shiftKey) {
        const forward = e.key === "ArrowLeft"; // الجدول من اليمين لليسار
        if (!atEdge(t, forward)) return;
        e.preventDefault();
        if (forward) {
          if (ci < cols.value.length - 1) focusCell(row, cols.value[ci + 1]);
          else if (!last) focusCell(row + 1, cols.value[0]);
        } else if (ci > 0) focusCell(row, cols.value[ci - 1]);
        else if (row > 0) focusCell(row - 1, cols.value[cols.value.length - 1]);
      } else if (e.key === "Delete" && e.ctrlKey) {
        e.preventDefault();
        removeLine(row);
      }
    }

    // ------------------------------------------------------------ الترحيل
    function payload() {
      const ls = [];
      lines.value.forEach((l, i) => {
        if (calc.value[i].empty) return;
        ls.push({ id: l.id || undefined, run_no: String(l.run_no).trim(), gold: l.gold, diamond: l.diamond, rate: l.rate,
          original_line_id: l.original_line_id || undefined });
      });
      const p = { doc_type: mode.value, account_id: accountId.value, doc_date: date.value, notes: notes.value, description: description.value, lines: ls };
      if (isReturn.value) {
        if (linked.value) p.original_doc_id = originalId.value;
        else { p.unlinked = true; p.exception_reason = exceptionReason.value; }
      }
      return p;
    }
    function clientValidate() {
      if (!accountId.value) { toast("error", "اختر العميل أولاً"); picker.value && picker.value.focus(); return false; }
      if (!date.value) { toast("error", "حدد تاريخ العملية"); return false; }
      if (isReturn.value && linked.value && !originalId.value) { toast("error", "اختر الفاتورة الأصلية للمرتجع"); return false; }
      if (isReturn.value && !linked.value && exceptionReason.value.trim().length < 5) { toast("error", "اكتب سبب الاستثناء للمرتجع غير المرتبط (5 أحرف على الأقل)"); return false; }
      if (!totals.value.lines) { toast("error", "المستند لا يحتوي على أي سطر صالح"); return false; }
      if (errorCount.value) {
        const i = calc.value.findIndex((c) => !c.empty && c.err);
        toast("error", `يوجد ${errorCount.value} سطر به خطأ`, `السطر ${i + 1}: ${calc.value[i].err}`);
        focusCell(i, cols.value[0]);
        return false;
      }
      return true;
    }
    async function startPost() {
      if (busy.value || checking.value || !canPost.value) return;
      if (!clientValidate()) return;
      checking.value = true;
      try {
        const path = editDoc.value ? `/api/documents/${editDoc.value.id}/preview` : "/api/documents/preview";
        preview.value = await api.post(path, payload());
      } catch (e) {
        handleError(e);
      } finally { checking.value = false; }
    }
    function handleError(e) {
      if (e.details && e.details.line_errors) {
        const map = {};
        let k = 0;
        const idx = lines.value.map((l, i) => i).filter((i) => !calc.value[i].empty);
        for (const [pos, msg] of Object.entries(e.details.line_errors)) { map[idx[Number(pos)]] = msg; k++; }
        serverLineErrors.value = map;
      }
      toastError(e, "لم يتم الترحيل");
    }
    async function confirmPost(reason) {
      if (busy.value) return;
      busy.value = true;
      try {
        let doc;
        if (editDoc.value) {
          doc = await api.put(`/api/documents/${editDoc.value.id}`, { ...payload(), version: editDoc.value.version, reason });
          toast("success", "تم حفظ التعديل", `${doc.doc_no} — أُعيد احتساب الأرصدة وكشف الحساب والتحليل.`);
        } else {
          doc = await postWithRetry("/api/documents", { ...payload(), client_token: token.value });
          if (doc.duplicate_request) toast("info", "المستند مُرحّل مسبقاً", `هذا الطلب رُحّل سابقاً برقم ${doc.doc_no} ولم يُكرَّر.`);
          else toast("success", `تم الترحيل: ${doc.doc_no}`, `${doc.type_label} — ${doc.account.name}`);
        }
        lastPosted.value = doc;
        preview.value = null;
        dataChanged();
        finish();
      } catch (e) {
        preview.value = null;
        handleError(e);
      } finally { busy.value = false; }
    }
    function finish() {
      local.remove("draft:sales");
      const keepMode = mode.value;
      editDoc.value = null;
      if (location.hash.includes("edit=")) history.replaceState(null, "", "#/sales");
      accountId.value = null;
      account.value = null;
      notes.value = ""; description.value = ""; exceptionReason.value = "";
      originalId.value = null; returnable.value = null;
      mode.value = keepMode;
      token.value = newToken();
      resetLines();
      refreshNextNo();
      nextTick(() => picker.value && picker.value.focus());
    }
    function clearAll() {
      if (totals.value.lines && !confirm("سيتم مسح كل الأسطر غير المرحّلة. متابعة؟")) return;
      finish();
    }
    async function previewLast() { await openPreview(docSpec(await api.get(`/api/documents/${lastPosted.value.id}`))); }

    // ------------------------------------------------------------ وضع التعديل
    async function loadForEdit(id) {
      try {
        const d = await api.get(`/api/documents/${id}`);
        if (d.doc_type !== "sale" && d.doc_type !== "return") return go(d.doc_type === "opening" ? "opening" : "vouchers", { edit: id });
        if (d.status !== "posted") { toast("error", "لا يمكن تعديل مستند ملغى"); return; }
        editDoc.value = d;
        mode.value = d.doc_type;
        accountId.value = d.account.id;
        date.value = d.doc_date;
        notes.value = d.notes;
        description.value = d.description;
        if (d.doc_type === "return") {
          linkMode.value = d.is_unlinked_return ? "unlinked" : "linked";
          exceptionReason.value = d.exception_reason;
          originalId.value = d.original_doc ? d.original_doc.id : null;
        }
        await nextTick();
        lines.value = d.lines.map((l) => newLine({ id: l.id, run_no: l.run_no, gold: l.gold, diamond: l.diamond, rate: l.rate, rateTouched: true, original_line_id: l.original_line_id }));
        if (!lines.value.length) resetLines();
      } catch (e) { toastError(e, "تعذر فتح المستند للتعديل"); }
    }
    function cancelEdit() { finish(); }

    // ------------------------------------------------------------ المسودة والرقم التالي
    async function refreshNextNo() {
      try { nextNo.value = (await api.get("/api/documents/next-no", { type: mode.value })).doc_no; } catch { /* */ }
    }
    const saveDraft = debounce(() => {
      if (editDoc.value) return;
      if (!totals.value.lines && !accountId.value) { local.remove("draft:sales"); return; }
      local.set("draft:sales", { mode: mode.value, accountId: accountId.value, date: date.value, notes: notes.value, description: description.value,
        lines: lines.value, linkMode: linkMode.value, originalId: originalId.value, exceptionReason: exceptionReason.value, token: token.value });
    }, 500);
    watch([mode, accountId, date, notes, description, lines, linkMode, originalId, exceptionReason], saveDraft, { deep: true });

    function onKey(e) {
      if (preview.value || store.docViewId || store.print) return;
      if (e.key === "F9" || ((e.ctrlKey || e.metaKey) && e.key === "Enter")) { e.preventDefault(); startPost(); }
      else if (e.altKey && e.code === "KeyN") { e.preventDefault(); if (!linked.value) addLine(); }
      else if (e.key === "F3") { e.preventDefault(); showSearch.value = true; }
    }
    onMounted(async () => {
      document.addEventListener("keydown", onKey);
      const p = parseHashQuery();
      if (p.get("edit")) { await loadForEdit(p.get("edit")); }
      else {
        const draft = local.get("draft:sales");
        if (draft && draft.lines && (draft.accountId || draft.lines.some((l) => l.gold || l.diamond || l.run_no))) {
          mode.value = draft.mode; await nextTick();
          accountId.value = draft.accountId; date.value = draft.date; notes.value = draft.notes; description.value = draft.description;
          linkMode.value = draft.linkMode; exceptionReason.value = draft.exceptionReason; token.value = draft.token;
          await nextTick();
          keepLinesOnce = !!draft.originalId;
          originalId.value = draft.originalId;
          await nextTick();
          lines.value = draft.lines.map((l) => ({ ...l, key: ++keySeq }));
          toast("info", "استُعيدت مسودة غير مرحّلة", "يمكنك متابعتها أو الضغط على «مسح» للبدء من جديد.");
        } else {
          resetLines();
          if (p.get("account")) accountId.value = Number(p.get("account"));
          if (p.get("type") === "return") mode.value = "return";
        }
        refreshNextNo();
        nextTick(() => picker.value && picker.value.focus());
      }
    });
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey));

    const g = group;
    return { store, mode, accountId, account, date, notes, description, lines, nextNo, linkMode, originalId, exceptionReason, invoices, invoiceFilter,
      invoiceOptions, returnable, editDoc, showOriginalSnapshot, preview, busy, checking, lastPosted, showSearch, activeRow, grid, picker, postBtn, u,
      canOverride, canUnlinked, canPost, isReturn, linked, defaultRate, workingKarat, calc, totals, errorCount, cols, origById,
      addLine, removeLine, onGridKey, startPost, confirmPost, clearAll, previewLast, cancelEdit, addOriginal, addAllRemaining, fmt, fmtRate, g, DOC_LABEL };
  },
  template: `<div>
    <div class="page-head">
      <div><h1>المبيعات والمرتجعات</h1><p>إجمالي الأجر = وزن الذهب × الأجر المعتمد لكل جرام. الألماس ورقم التشغيل لا يدخلان في حساب الأجر.</p></div>
      <div class="actions">
        <button class="btn" @click="showSearch = true"><Icon name="search"/> بحث عن مستند <span class="kbd" style="color:var(--text-3)">F3</span></button>
      </div>
    </div>

    <LastPosted :doc="lastPosted" @preview="previewLast" @dismiss="lastPosted = null" />

    <div v-if="editDoc" class="alert warn mb"><Icon name="pencil"/>
      <div style="flex:1"><b>وضع التعديل:</b> {{ editDoc.type_label }} <b class="num">{{ editDoc.doc_no }}</b> — العميل والنوع ثابتان. عند الحفظ يُطلب سبب التعديل وتُحفظ القيم السابقة في سجل المستند.
        <button class="btn btn-sm btn-ghost" @click="showOriginalSnapshot = !showOriginalSnapshot">{{ showOriginalSnapshot ? 'إخفاء' : 'عرض' }} البيانات قبل التعديل</button>
        <table v-if="showOriginalSnapshot" class="tbl mt" style="background:#fff;font-size:.85rem">
          <thead><tr><th>#</th><th>رقم التشغيل</th><th class="num">الذهب</th><th class="num">الألماس</th><th class="num">الأجر</th><th class="num">الإجمالي</th></tr></thead>
          <tbody><tr v-for="l in editDoc.lines" :key="l.id"><td>{{ l.line_no }}</td><td>{{ l.run_no }}</td><td class="num">{{ g(l.gold) }}</td><td class="num">{{ g(l.diamond) }}</td><td class="num">{{ l.rate }}</td><td class="num">{{ g(l.wage) }}</td></tr></tbody>
          <tfoot><tr><td></td><td>الإجمالي</td><td class="num">{{ g(editDoc.totals.gold) }}</td><td class="num">{{ g(editDoc.totals.diamond) }}</td><td></td><td class="num">{{ g(editDoc.totals.wage) }}</td></tr></tfoot>
        </table></div>
      <button class="btn btn-sm" @click="cancelEdit">إلغاء التعديل</button></div>

    <div class="card">
      <div class="card-body" data-focus-scope>
        <div class="row mb" style="gap:16px">
          <div class="seg lg" role="radiogroup" aria-label="نوع العملية">
            <button class="t-sale" :class="{ on: mode === 'sale' }" @click="!editDoc && (mode = 'sale')" :disabled="!!editDoc"><Icon name="receipt"/> مبيعات</button>
            <button class="t-return" :class="{ on: mode === 'return' }" @click="!editDoc && (mode = 'return')" :disabled="!!editDoc"><Icon name="undo-2"/> مرتجع مبيعات</button>
          </div>
          <div class="info-strip" style="margin-inline-start:auto">
            <div><div class="k">رقم المستند</div><div class="v num">{{ editDoc ? editDoc.doc_no : nextNo }}</div></div>
            <div><div class="k">عيار العمل</div><div class="v num" style="color:var(--gold)">{{ workingKarat }}</div></div>
            <div><div class="k">رقم الحساب</div><div class="v num">{{ account ? account.account_no : '—' }}</div></div>
            <div><div class="k">الأجر الافتراضي / جم</div><div class="v num">{{ account ? account.wage_rate : '—' }}</div></div>
          </div>
        </div>
        <div class="grid g4">
          <div class="field span2"><label class="req">العميل</label>
            <AccountPicker ref="picker" v-model="accountId" :disabled="!!editDoc" /></div>
          <div class="field"><label class="req">تاريخ العملية</label><input type="date" class="input" v-model="date" /></div>
          <div class="field"><label>البيان <span class="muted">(اختياري)</span></label><input class="input" v-model="description" maxlength="300" /></div>
          <div class="field span2" v-if="!isReturn || linked"><label>ملاحظات <span class="muted">(اختياري)</span></label><input class="input" v-model="notes" maxlength="1000" /></div>

          <template v-if="isReturn">
            <div class="field"><label>ربط المرتجع</label>
              <div class="seg"><button :class="{ on: linkMode === 'linked' }" @click="!editDoc && (linkMode = 'linked')" :disabled="!!editDoc">مرتبط بفاتورة</button>
                <button :class="{ on: linkMode === 'unlinked' }" @click="!editDoc && canUnlinked && (linkMode = 'unlinked')" :disabled="!!editDoc || !canUnlinked" :title="canUnlinked ? '' : 'يحتاج صلاحية من الإدارة'">غير مرتبط (استثناء)</button></div></div>
            <div class="field" v-if="linked"><label class="req">الفاتورة الأصلية</label>
              <select class="select" v-model="originalId" :disabled="!accountId || !!editDoc">
                <option :value="null">{{ accountId ? (invoiceOptions.length ? 'اختر الفاتورة…' : 'لا فواتير بها كميات قابلة للإرجاع') : 'اختر العميل أولاً' }}</option>
                <option v-for="i in invoiceOptions" :key="i.id" :value="i.id">{{ i.doc_no }} — {{ i.doc_date }} — متبقي ذهب {{ i.remaining_gold }} / ألماس {{ i.remaining_diamond }}</option>
              </select></div>
            <div class="field span2" v-if="!linked"><label class="req">سبب الاستثناء (مرتجع دون فاتورة أصلية)</label>
              <input class="input" v-model="exceptionReason" maxlength="300" placeholder="مثال: قطعة بيعت قبل تشغيل النظام" />
              <span class="hint">يُسجَّل السبب ويظهر المرتجع كاستثناء في التحليل وكشف الحساب.</span></div>
            <div class="field span2" v-if="!linked"><label>ملاحظات</label><input class="input" v-model="notes" maxlength="1000" /></div>
          </template>
        </div>

        <div v-if="linked && returnable" class="section-box mt">
          <div class="sb-head" style="background:var(--surface-2)"><Icon name="list-plus" size="sm"/> أسطر الفاتورة الأصلية <span class="num">{{ returnable.doc_no }}</span>
            <button class="btn btn-sm" style="margin-inline-start:auto" @click="addAllRemaining">إضافة كل المتبقي</button></div>
          <div class="tbl-wrap" style="max-height:240px;border:0">
            <table class="tbl" style="font-size:.88rem">
              <thead><tr><th>#</th><th>رقم التشغيل</th><th class="num">ذهب مباع</th><th class="num">ذهب مرتجع</th><th class="num">ذهب متبقٍ</th><th class="num">ألماس متبقٍ</th><th class="num">الأجر</th><th></th></tr></thead>
              <tbody><tr v-for="ol in returnable.lines" :key="ol.id" :style="ol.fully_returned ? 'opacity:.5' : ''">
                <td class="rownum">{{ ol.line_no }}</td><td class="strong">{{ ol.run_no || '—' }}</td><td class="num">{{ g(ol.sold.gold) }}</td><td class="num">{{ g(ol.returned.gold) }}</td>
                <td class="num strong">{{ g(ol.remaining.gold) }}</td><td class="num">{{ g(ol.remaining.diamond) }}</td><td class="num">{{ ol.rate }}</td>
                <td><button class="btn btn-sm" :disabled="ol.fully_returned" @click="addOriginal(ol)"><Icon name="plus" size="sm"/> إضافة</button></td></tr></tbody>
            </table></div>
        </div>
      </div>

      <div class="card-head" style="border-top:1px solid var(--border)">
        <h3>{{ isReturn ? 'أسطر المرتجع' : 'أسطر الفاتورة' }}</h3>
        <span class="badge" :class="isReturn ? 'debit' : 'posted'">{{ isReturn ? 'يُخفض مستحقات العميل (دائن)' : 'يزيد مستحقات العميل (مدين)' }}</span>
        <div class="tools muted small">
          <span><span class="kbd" style="color:var(--text)">Enter</span> / <span class="kbd" style="color:var(--text)">←</span> الخانة التالية</span>
          <span><span class="kbd" style="color:var(--text)">↑↓</span> السطر السابق/التالي</span>
          <span><span class="kbd" style="color:var(--text)">Enter</span> على سطر فارغ ← زر الترحيل</span>
          <span><span class="kbd" style="color:var(--text)">Alt+N</span> سطر جديد</span>
          <span><span class="kbd" style="color:var(--text)">Ctrl+Del</span> حذف السطر</span>
          <span><span class="kbd" style="color:var(--text)">F9</span> ترحيل</span>
        </div>
      </div>
      <div class="tbl-wrap tall" ref="grid" @keydown="onGridKey">
        <table class="tbl entry-tbl">
          <thead><tr>
            <th class="c" style="width:44px">#</th><th style="width:20%">رقم التشغيل</th><th class="num">الذهب ({{ u.gold }})</th><th class="num">الألماس ({{ u.diamond }})</th>
            <th class="num" style="width:15%">الأجر المعتمد / جم</th><th class="num">{{ isReturn ? 'الأجر المسترد' : 'إجمالي الأجر' }} ({{ u.wage }})</th><th class="c" style="width:90px">الإجراءات</th>
          </tr></thead>
          <tbody>
            <tr v-for="(l, i) in lines" :key="l.key" :class="{ 'row-error': calc[i] && calc[i].err, 'active-row': activeRow === i }" @focusin="activeRow = i">
              <td class="rownum">{{ i + 1 }}</td>
              <td>
                <input v-if="!linked" class="input" v-model="l.run_no" :data-row="i" data-col="run_no" maxlength="60" autocomplete="off" aria-label="رقم التشغيل" />
                <div v-else class="readout" style="height:36px">{{ l.run_no || '—' }} <span class="muted small" v-if="origById[l.original_line_id]">&nbsp;(متبقٍ {{ origById[l.original_line_id].remaining.gold }})</span></div>
                <div v-if="calc[i] && calc[i].err" class="line-err">{{ calc[i].err }}</div>
              </td>
              <td><NumInput v-model="l.gold" :dp="4" :data-row="i" data-col="gold" :enter-next="false" label="وزن الذهب" /></td>
              <td><NumInput v-model="l.diamond" :dp="3" :data-row="i" data-col="diamond" :enter-next="false" label="وزن الألماس" /></td>
              <td>
                <NumInput v-if="canOverride && !linked" v-model="l.rate" :dp="3" :data-row="i" data-col="rate" :enter-next="false" label="الأجر المعتمد" @update:modelValue="l.rateTouched = true"
                  :style="l.rate !== defaultRate && !l.id ? 'border-color:var(--warn);background:var(--warn-bg)' : ''" />
                <div v-else class="readout num" style="height:36px;justify-content:flex-end" :title="linked ? 'أجر الفاتورة الأصلية' : 'تعديل أجر السطر يحتاج صلاحية'">{{ l.rate || '—' }}</div>
              </td>
              <td class="calc">{{ calc[i] && !calc[i].empty && !calc[i].err ? fmt(calc[i].wage, 2) : (calc[i] && calc[i].empty ? '' : '—') }}</td>
              <td class="c"><button class="btn btn-sm btn-ghost" @click="removeLine(i)" title="حذف السطر (Ctrl+Delete)" tabindex="-1"><Icon name="trash-2" size="sm"/></button></td>
            </tr>
          </tbody>
        </table>
        <Empty v-if="!lines.length" :text="linked ? 'اختر الفاتورة الأصلية ثم أضف الأسطر المرتجعة منها' : 'لا أسطر'" icon="list-plus" />
      </div>
      <div class="row" style="padding:10px 18px;border-top:1px solid var(--border)">
        <button class="btn" @click="addLine()" v-if="!linked"><Icon name="plus"/> إضافة سطر</button>
        <span v-if="errorCount" class="badge debit">{{ errorCount }} سطر به خطأ</span>
        <span class="muted small">الأسطر الفارغة تماماً تُتجاهل عند الترحيل.</span>
      </div>
      <div class="totals-bar">
        <div><div class="t-label">عدد الأسطر</div><div class="t-value num">{{ totals.lines }}</div></div>
        <div><div class="t-label">إجمالي وزن الذهب</div><div class="t-value num" style="color:var(--gold)">{{ totals.gold }}<span class="t-unit">{{ u.gold }}</span></div></div>
        <div><div class="t-label">إجمالي وزن الألماس</div><div class="t-value num" style="color:var(--diamond)">{{ totals.diamond }}<span class="t-unit">{{ u.diamond }}</span></div></div>
        <div><div class="t-label">{{ isReturn ? 'إجمالي الأجور المستردة' : 'إجمالي الأجور' }}</div><div class="t-value num" style="color:var(--wage)">{{ totals.wage }}<span class="t-unit">{{ u.wage }}</span></div></div>
        <div><div class="t-label">{{ isReturn ? 'إجمالي المرتجعات' : 'إجمالي المبيعات' }}</div><div class="t-value small" style="font-size:.95rem;line-height:1.5">ذهب <span class="num">{{ totals.gold }}</span><br>أجور <span class="num">{{ totals.wage }}</span></div></div>
      </div>
    </div>

    <div class="row mt">
      <button ref="postBtn" class="btn btn-primary btn-lg" @click="startPost" :disabled="busy || checking || !canPost" data-enter-stop>
        <span v-if="checking" class="spinner"></span><Icon v-else name="check"/> {{ editDoc ? 'حفظ التعديل' : 'ترحيل' }} <span class="kbd">F9</span></button>
      <button class="btn btn-lg" @click="clearAll" :disabled="busy"><Icon name="eraser"/> مسح</button>
      <span v-if="!canPost" class="badge warn">لا تملك صلاحية {{ editDoc ? 'التعديل' : 'الترحيل' }}</span>
      <span class="muted small" style="margin-inline-start:auto">قبل الترحيل يعرض النظام ملخصاً بالأثر على الأرصدة. الترحيل يتم مرة واحدة فقط حتى لو تكرر الضغط.</span>
    </div>

    <PostSummary v-if="preview" :preview="preview" :editing="!!editDoc" :busy="busy" :doc-no="editDoc ? editDoc.doc_no : nextNo" @confirm="confirmPost" @cancel="preview = null" />
    <DocSearch v-if="showSearch" :types="['sale','return']" title="البحث في المبيعات والمرتجعات" @close="showSearch = false" />
  </div>`,
};

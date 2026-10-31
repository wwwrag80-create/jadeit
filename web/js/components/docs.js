// عرض المستند المرحّل (التفاصيل، السجل، الطباعة، التعديل، الإلغاء) + نافذة البحث عن المستندات.
import { api } from "../api.js";
import { store, can, toast, toastError, dataChanged, units } from "../store.js";
import { group } from "../num.js";
import { DOC_LABEL, MATERIAL_LABEL, DIR_LABEL, fmtDateTime, go, today } from "../util.js";
import { confirmDialog } from "./ui.js";
import { openPreview, docSpec } from "./print.js";

const { ref, reactive, computed, watch, onMounted, onBeforeUnmount } = Vue;

export const SCREEN_FOR = { sale: "sales", return: "sales", receipt: "vouchers", payment: "vouchers", opening: "opening" };
const ACTION_LABEL = { post: "ترحيل", edit: "تعديل", cancel: "إلغاء" };
const FIELD_LABEL = { doc_date: "التاريخ", description: "البيان", notes: "ملاحظات", exception_reason: "سبب الاستثناء" };

function parseJson(s) {
  if (!s) return null;
  try { return typeof s === "string" ? JSON.parse(s) : s; } catch { return null; }
}

export const DocView = {
  name: "DocView",
  setup() {
    const doc = ref(null);
    const loading = ref(false);
    const tab = ref("details");
    const u = computed(units);
    async function load() {
      if (!store.docViewId) { doc.value = null; return; }
      loading.value = true;
      try {
        doc.value = await api.get(`/api/documents/${store.docViewId}`);
        tab.value = "details";
      } catch (e) {
        toastError(e, "تعذر فتح المستند");
        store.docViewId = null;
      } finally {
        loading.value = false;
      }
    }
    watch(() => [store.docViewId, store.dataVersion], load, { immediate: true });

    const history = computed(() => (doc.value ? doc.value.history.map((h) => ({
      ...h, label: ACTION_LABEL[h.action] || h.action, beforeObj: parseJson(h.before), afterObj: parseJson(h.after),
    })) : []));

    function headerChanges(h) {
      const b = h.beforeObj, a = h.afterObj;
      if (!b || !a) return [];
      return Object.keys(FIELD_LABEL).filter((k) => (b[k] ?? "") !== (a[k] ?? "")).map((k) => ({ label: FIELD_LABEL[k], old: b[k] || "—", new: a[k] || "—" }));
    }
    function voucherChange(h) {
      const b = h.beforeObj && h.beforeObj.voucher, a = h.afterObj && h.afterObj.voucher;
      if (!b || !a) return null;
      return { b, a };
    }

    function close() { store.docViewId = null; }
    async function preview() { await openPreview(docSpec(doc.value)); }
    function edit() {
      const d = doc.value;
      close();
      go(SCREEN_FOR[d.doc_type], { edit: d.id });
    }
    async function cancel() {
      const d = doc.value;
      let body = `سيُلغى المستند ${d.doc_no} بقيد عكسي بالتاريخ نفسه، فيصبح أثره على الأرصدة صفراً.\nيبقى المستند وقيوده الأصلية ظاهرة في كشف الحساب مع علامة «ملغى»، ولا يُحذف أي أثر.`;
      if (d.linked_returns && d.linked_returns.some((r) => r.status === "posted")) {
        body += "\n\nتنبيه: توجد مرتجعات مرحّلة مرتبطة بهذه الفاتورة، ولن يُسمح بالإلغاء قبل إلغائها.";
      }
      const reason = await confirmDialog({ title: `إلغاء ${d.type_label} ${d.doc_no}`, body, okText: "تأكيد الإلغاء", danger: true, reasonLabel: "سبب الإلغاء" });
      if (!reason) return;
      try {
        doc.value = await api.post(`/api/documents/${d.id}/cancel`, { reason, version: d.version });
        toast("success", "تم إلغاء المستند", `${d.doc_no} — أُضيف قيد عكسي وحُدّثت الأرصدة وكشف الحساب.`);
        dataChanged();
      } catch (e) { toastError(e, "تعذر الإلغاء"); }
    }
    function openStatement() {
      const d = doc.value;
      close();
      const m = d.voucher ? d.voucher.material : "gold";
      go("statement", { account: d.account.id, material: m });
    }
    function openDoc(id) { store.docViewId = id; }
    const canEdit = computed(() => doc.value && doc.value.status === "posted" && can("docs.edit") && (doc.value.doc_type !== "opening" || can("opening.manage")));
    const canCancel = computed(() => doc.value && doc.value.status === "posted" && can("docs.cancel") && (doc.value.doc_type !== "opening" || can("opening.manage")));
    return { store, doc, loading, tab, u, history, headerChanges, voucherChange, close, preview, edit, cancel, openStatement, openDoc,
      canEdit, canCancel, g: group, MATERIAL_LABEL, DIR_LABEL, fmtDateTime };
  },
  template: `<Modal v-if="store.docViewId && doc" size="wide" @close="close">
    <template #head>
      <div class="row" style="gap:12px">
        <h3>{{ doc.type_label }} <span class="num">{{ doc.doc_no }}</span></h3>
        <StatusBadge :status="doc.status" />
        <span v-if="doc.is_unlinked_return" class="badge warn">غير مرتبط — استثناء</span>
      </div>
    </template>
    <div class="info-strip mb">
      <div><div class="k">العميل</div><div class="v">{{ doc.account.name }} <span class="muted num">({{ doc.account.account_no }})</span></div></div>
      <div><div class="k">التاريخ</div><div class="v num">{{ doc.doc_date }}</div></div>
      <div><div class="k">عيار العمل</div><div class="v num">{{ doc.working_karat }}</div></div>
      <div v-if="doc.original_doc"><div class="k">الفاتورة الأصلية</div><div class="v"><button class="link num" style="background:none;border:0;cursor:pointer;color:var(--primary);font-weight:700;text-decoration:underline" @click="openDoc(doc.original_doc.id)">{{ doc.original_doc.doc_no }}</button></div></div>
      <div><div class="k">أدخله</div><div class="v">{{ doc.posted_by }} <span class="muted small num">{{ fmtDateTime(doc.posted_at) }}</span></div></div>
      <div v-if="doc.updated_at"><div class="k">آخر تعديل</div><div class="v">{{ doc.updated_by }} <span class="muted small num">{{ fmtDateTime(doc.updated_at) }}</span></div></div>
    </div>
    <div v-if="doc.status === 'cancelled'" class="alert danger mb"><Icon name="ban"/><div>أُلغي هذا المستند بتاريخ <span class="num">{{ fmtDateTime(doc.cancelled_at) }}</span> بواسطة {{ doc.cancelled_by }}. السبب: {{ doc.cancel_reason }}. أثره على الأرصدة صفر بقيد عكسي.</div></div>
    <div v-if="doc.is_unlinked_return" class="alert warn mb"><Icon name="triangle-alert"/><div>مرتجع غير مرتبط بفاتورة أصلية. سبب الاستثناء: {{ doc.exception_reason }}</div></div>
    <div class="tabs">
      <button :class="{ on: tab === 'details' }" @click="tab = 'details'">التفاصيل</button>
      <button :class="{ on: tab === 'effects' }" @click="tab = 'effects'">الأثر المحاسبي</button>
      <button :class="{ on: tab === 'history' }" @click="tab = 'history'">سجل التعديلات ({{ history.length }})</button>
    </div>

    <div v-if="tab === 'details'">
      <div v-if="doc.doc_type === 'sale' || doc.doc_type === 'return'" class="tbl-wrap auto">
        <table class="tbl">
          <thead><tr><th class="c">#</th><th>رقم التشغيل</th><th class="num">الذهب ({{ u.gold }})</th><th class="num">الألماس ({{ u.diamond }})</th>
            <th class="num">الأجر المعتمد</th><th class="num">{{ doc.doc_type === 'return' ? 'الأجر المسترد' : 'إجمالي الأجر' }}</th>
            <th v-if="doc.doc_type === 'sale'">المرتجع منه</th><th v-if="doc.doc_type === 'return'">من سطر</th></tr></thead>
          <tbody>
            <tr v-for="l in doc.lines" :key="l.id">
              <td class="rownum">{{ l.line_no }}</td><td class="strong">{{ l.run_no || '—' }}</td>
              <td class="num">{{ g(l.gold) }}</td><td class="num">{{ g(l.diamond) }}</td>
              <td class="num">{{ l.rate }} <span v-if="l.rate_overridden" class="badge warn" title="أجر مختلف عن الافتراضي">معدّل</span></td>
              <td class="num">{{ g(l.wage) }}</td>
              <td v-if="doc.doc_type === 'sale'" class="small"><span v-if="l.has_returns">ذهب <span class="num">{{ l.returned.gold }}</span> · ألماس <span class="num">{{ l.returned.diamond }}</span></span><span v-else class="muted">—</span></td>
              <td v-if="doc.doc_type === 'return'" class="small num">{{ l.original ? l.original.doc_no + ' / ' + l.original.line_no : '—' }}</td>
            </tr>
          </tbody>
          <tfoot><tr><td></td><td>الإجمالي ({{ doc.totals.lines }} سطر)</td><td class="num">{{ g(doc.totals.gold) }}</td><td class="num">{{ g(doc.totals.diamond) }}</td><td></td><td class="num">{{ g(doc.totals.wage) }}</td><td></td></tr></tfoot>
        </table>
      </div>
      <div v-else-if="doc.voucher" class="grid g4">
        <div class="field"><span class="label">نوع المادة</span><div class="readout">{{ MATERIAL_LABEL[doc.voucher.material] }}</div></div>
        <div class="field"><span class="label">{{ doc.voucher.material === 'wage' ? 'المبلغ' : 'الوزن الفعلي' }}</span><div class="readout num">{{ g(doc.voucher.actual) }}</div></div>
        <template v-if="doc.voucher.material === 'gold'">
          <div class="field"><span class="label">العيار الفعلي ← عيار العمل</span><div class="readout num">{{ doc.voucher.karat }} ← {{ doc.voucher.working_karat }}</div></div>
          <div class="field"><span class="label">الوزن المكافئ</span><div class="readout big num">{{ g(doc.voucher.equivalent) }}</div></div>
        </template>
      </div>
      <div v-else class="tbl-wrap auto">
        <table class="tbl"><thead><tr><th>#</th><th>نوع الرصيد</th><th>الاتجاه</th><th class="num">الوزن/المبلغ</th><th class="num">العيار</th><th class="num">المعتمد</th><th>البيان</th><th>ملاحظات</th></tr></thead>
          <tbody><tr v-for="l in doc.lines" :key="l.id"><td class="rownum">{{ l.line_no }}</td><td><MaterialBadge :m="l.material"/></td><td><DirBadge :dir="l.direction"/></td>
            <td class="num">{{ g(l.actual) }}</td><td class="num">{{ l.karat ? l.karat + ' ← ' + l.working_karat : '—' }}</td><td class="num">{{ g(l.equivalent) }}</td><td>{{ l.description }}</td><td>{{ l.note }}</td></tr></tbody></table>
      </div>
      <div class="kv mt" v-if="doc.description || doc.notes">
        <template v-if="doc.description"><dt>البيان</dt><dd>{{ doc.description }}</dd></template>
        <template v-if="doc.notes"><dt>ملاحظات</dt><dd style="white-space:pre-line">{{ doc.notes }}</dd></template>
      </div>
      <div v-if="doc.linked_returns && doc.linked_returns.length" class="mt">
        <span class="label">مرتجعات مرتبطة:</span>
        <span v-for="r in doc.linked_returns" :key="r.id" style="margin-inline-start:8px">
          <button class="btn btn-sm" @click="openDoc(r.id)"><span class="num">{{ r.doc_no }}</span> <StatusBadge :status="r.status"/></button>
        </span>
      </div>
    </div>

    <div v-if="tab === 'effects'">
      <p class="muted small" style="margin-top:0">القيود المسجلة في دفتر الحركات لهذا المستند (مدين = يزيد المستحق على العميل، دائن = يخفضه).</p>
      <table class="tbl"><thead><tr><th>النوع</th><th class="num">مدين</th><th class="num">دائن</th><th class="num">صافي الأثر الحالي</th></tr></thead>
        <tbody><tr v-for="m in ['gold','diamond','wage']" :key="m"><td><MaterialBadge :m="m"/></td>
          <td class="num">{{ g(doc.effects[m].debit) }}</td><td class="num">{{ g(doc.effects[m].credit) }}</td>
          <td class="num">{{ g(doc.net_effects[m].net) }} <span class="muted small">{{ u[m] }}</span></td></tr></tbody></table>
    </div>

    <div v-if="tab === 'history'" class="stack">
      <div v-for="(h, i) in history" :key="i" class="section-box">
        <div class="sb-head" style="background:var(--surface-2)"><Icon name="history" size="sm"/> {{ h.label }} — {{ h.user }} <span class="muted small num" style="margin-inline-start:auto">{{ fmtDateTime(h.at) }}</span></div>
        <div style="padding:10px 14px" class="diff">
          <div v-if="h.reason"><b>السبب:</b> {{ h.reason }}</div>
          <div v-for="c in headerChanges(h)" :key="c.label">{{ c.label }}: <span class="old">{{ c.old }}</span> ← <span class="new">{{ c.new }}</span></div>
          <div v-if="voucherChange(h)">القيمة: <span class="old num">{{ voucherChange(h).b.actual }} ({{ voucherChange(h).b.equivalent }})</span> ← <span class="new num">{{ voucherChange(h).a.actual }} ({{ voucherChange(h).a.equivalent }})</span></div>
          <div v-if="h.action === 'edit' && h.beforeObj && h.beforeObj.lines && h.beforeObj.lines.length" class="grid g2 mt" style="gap:10px">
            <div><b>قبل التعديل</b>
              <table class="tbl" style="font-size:.82rem"><tbody><tr v-for="l in h.beforeObj.lines" :key="'b'+l.line_no"><td>{{ l.run_no || l.material || '' }}</td><td class="num">{{ l.gold || l.actual }}</td><td class="num">{{ l.diamond || l.direction }}</td><td class="num">{{ l.wage || l.equivalent }}</td></tr></tbody></table>
              <div class="small">الإجمالي: ذهب <span class="num">{{ h.beforeObj.totals.gold }}</span> · أجور <span class="num">{{ h.beforeObj.totals.wage }}</span></div></div>
            <div><b>بعد التعديل</b>
              <table class="tbl" style="font-size:.82rem"><tbody><tr v-for="l in h.afterObj.lines" :key="'a'+l.line_no"><td>{{ l.run_no || l.material || '' }}</td><td class="num">{{ l.gold || l.actual }}</td><td class="num">{{ l.diamond || l.direction }}</td><td class="num">{{ l.wage || l.equivalent }}</td></tr></tbody></table>
              <div class="small">الإجمالي: ذهب <span class="num">{{ h.afterObj.totals.gold }}</span> · أجور <span class="num">{{ h.afterObj.totals.wage }}</span></div></div>
          </div>
        </div>
      </div>
    </div>

    <template #foot>
      <button class="btn btn-primary" @click="preview"><Icon name="eye"/> معاينة وطباعة</button>
      <button class="btn" @click="openStatement"><Icon name="file-text"/> كشف الحساب</button>
      <div class="end">
        <button v-if="canEdit" class="btn" @click="edit"><Icon name="pencil"/> تعديل</button>
        <button v-if="canCancel" class="btn btn-danger" @click="cancel"><Icon name="ban"/> إلغاء المستند</button>
      </div>
    </template>
  </Modal>`,
};

/** نافذة البحث عن المستندات داخل الشاشة الحالية. */
export const DocSearch = {
  name: "DocSearch",
  props: { types: { type: Array, default: () => [] }, title: { type: String, default: "البحث عن مستند" } },
  emits: ["close"],
  setup(props) {
    const f = reactive({ q: "", type: "", account_id: null, date_from: "", date_to: "", status: "" });
    const rows = ref([]);
    const loading = ref(false);
    const searched = ref(false);
    async function search() {
      loading.value = true;
      try {
        rows.value = await api.get("/api/documents", {
          q: f.q, types: f.type || props.types.join(","), account_id: f.account_id || "",
          date_from: f.date_from, date_to: f.date_to, status: f.status, limit: 300,
        });
        searched.value = true;
      } catch (e) { toastError(e, "تعذر البحث"); } finally { loading.value = false; }
    }
    onMounted(search);
    watch(() => store.dataVersion, search);
    function open(r) { store.docViewId = r.id; }
    return { f, rows, loading, searched, search, open, DOC_LABEL, g: group, today };
  },
  template: `<Modal :title="title" size="xwide" @close="$emit('close')">
    <div class="grid g6" style="align-items:end" @keydown.enter.prevent="search">
      <div class="field span2"><label>رقم المستند / رقم التشغيل / اسم أو رقم العميل</label>
        <input class="input" v-model="f.q" autofocus placeholder="مثال: SA-000012 أو 0045 أو اسم العميل" /></div>
      <div class="field"><label>نوع العملية</label>
        <select class="select" v-model="f.type"><option value="">الكل</option><option v-for="t in types" :key="t" :value="t">{{ DOC_LABEL[t] }}</option></select></div>
      <div class="field"><label>من تاريخ</label><input type="date" class="input" v-model="f.date_from" /></div>
      <div class="field"><label>إلى تاريخ</label><input type="date" class="input" v-model="f.date_to" /></div>
      <div class="field"><label>الحالة</label><select class="select" v-model="f.status"><option value="">الكل</option><option value="posted">مرحّل</option><option value="cancelled">ملغى</option></select></div>
      <div class="field span2"><label>العميل</label><AccountPicker v-model="f.account_id" include-inactive placeholder="كل العملاء" /></div>
      <div class="row"><button class="btn btn-primary" @click="search" :disabled="loading"><Icon name="search"/> بحث</button>
        <button class="btn btn-ghost" @click="Object.assign(f, { q: '', type: '', account_id: null, date_from: '', date_to: '', status: '' }); search()">مسح</button></div>
    </div>
    <div class="tbl-wrap mt" style="max-height:55vh">
      <table class="tbl">
        <thead><tr><th>التاريخ</th><th>رقم المستند</th><th>النوع</th><th>العميل</th><th>أرقام التشغيل</th><th class="num">ذهب</th><th class="num">ألماس</th><th class="num">أجور</th><th>الحالة</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" class="clickable" @click="open(r)" tabindex="0" @keydown.enter="open(r)">
            <td class="num">{{ r.doc_date }}</td><td><span class="link num">{{ r.doc_no }}</span></td><td>{{ r.type_label }}</td>
            <td>{{ r.account.name }} <span class="muted small num">{{ r.account.account_no }}</span></td>
            <td class="small" style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ r.run_numbers || '—' }}</td>
            <td class="num">{{ g(r.gold) }}</td><td class="num">{{ g(r.diamond) }}</td><td class="num">{{ g(r.wage) }}</td>
            <td><StatusBadge :status="r.status"/></td>
          </tr>
        </tbody>
      </table>
      <Empty v-if="searched && !rows.length" text="لا توجد مستندات مطابقة" />
    </div>
    <div class="muted small mt">اضغط على المستند لعرضه ثم طباعته أو تعديله أو إلغائه حسب صلاحياتك.</div>
  </Modal>`,
};

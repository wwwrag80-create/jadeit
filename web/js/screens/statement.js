// الشاشة الخامسة: كشف الحساب — كشف مستقل لكل نوع رصيد مع رصيد افتتاحي للفترة.
import { api } from "../api.js";
import { store, toastError, units } from "../store.js";
import { group } from "../num.js";
import { today, monthStart, yearStart, parseHashQuery, MATERIAL_LABEL } from "../util.js";
import { openPreview, paginate, printPages, statementSpec } from "../components/print.js";

const { ref, reactive, computed, watch, onMounted } = Vue;

export const StatementScreen = {
  name: "StatementScreen",
  setup() {
    const f = reactive({ account_id: null, material: "gold", date_from: monthStart(), date_to: today() });
    const st = ref(null);
    const loading = ref(false);
    const u = computed(units);
    const account = computed(() => store.accounts.find((a) => a.id === f.account_id) || null);
    async function load() {
      if (!f.account_id) { toastError({ message: "اختر العميل أولاً" }, "لا يمكن عرض الكشف"); return; }
      if (f.date_from && f.date_to && f.date_from > f.date_to) { toastError({ message: "تاريخ البداية بعد تاريخ النهاية" }); return; }
      loading.value = true;
      try { st.value = await api.get("/api/statement", f); } catch (e) { toastError(e, "تعذر عرض الكشف"); } finally { loading.value = false; }
    }
    watch(() => store.dataVersion, () => { if (st.value) load(); });
    watch(() => f.material, () => { if (f.account_id && st.value) load(); });
    function period(kind) {
      if (kind === "month") { f.date_from = monthStart(); f.date_to = today(); }
      else if (kind === "year") { f.date_from = yearStart(); f.date_to = today(); }
      else { f.date_from = ""; f.date_to = ""; }
      if (f.account_id) load();
    }
    const spec = () => statementSpec(st.value, MATERIAL_LABEL[st.value.material]);
    async function preview() { if (!st.value) await load(); if (st.value) await openPreview(spec()); }
    async function print() { if (!st.value) await load(); if (st.value) printPages(await paginate(spec())); }
    onMounted(() => {
      const p = parseHashQuery();
      if (p.get("account")) {
        f.account_id = Number(p.get("account"));
        if (p.get("material")) f.material = p.get("material");
        if (p.has("from")) f.date_from = p.get("from");
        else f.date_from = "";
        if (p.has("to")) f.date_to = p.get("to");
        load();
      }
    });
    const openDoc = (r) => { if (r.doc_id) store.docViewId = r.doc_id; };
    return { store, f, st, loading, u, account, load, period, preview, print, openDoc, g: group, MATERIAL_LABEL };
  },
  template: `<div>
    <div class="page-head"><div><h1>كشف الحساب</h1><p>كل كشف مستقل بنوعه. الرصيد الختامي = الرصيد الافتتاحي للفترة + المدين − الدائن. اختيار الفترة لا يغيّر الرصيد الفعلي للحساب.</p></div></div>
    <div class="card mb">
      <div class="card-body" data-focus-scope @keydown.enter.ctrl="load">
        <div class="grid g6" style="align-items:end">
          <div class="field span2"><label class="req">اسم العميل</label><AccountPicker v-model="f.account_id" include-inactive autofocus /></div>
          <div class="field"><label>رقم الحساب</label><div class="readout num">{{ account ? account.account_no : '—' }}</div></div>
          <div class="field"><label>من تاريخ</label><input type="date" class="input" v-model="f.date_from" /></div>
          <div class="field"><label>إلى تاريخ</label><input type="date" class="input" v-model="f.date_to" /></div>
          <div class="field"><label>الفترة</label><div class="row" style="gap:4px">
            <button class="btn btn-sm" @click="period('month')">الشهر</button><button class="btn btn-sm" @click="period('year')">السنة</button><button class="btn btn-sm" @click="period('all')">الكل</button></div></div>
          <div class="field span2"><label>نوع الكشف</label>
            <div class="seg"><button class="m-gold" :class="{ on: f.material === 'gold' }" @click="f.material = 'gold'"><Icon name="coins"/> كشف الذهب</button>
              <button class="m-diamond" :class="{ on: f.material === 'diamond' }" @click="f.material = 'diamond'"><Icon name="gem"/> كشف الألماس</button>
              <button class="m-wage" :class="{ on: f.material === 'wage' }" @click="f.material = 'wage'"><Icon name="wallet"/> كشف الأجور</button></div></div>
          <div class="row span2" style="grid-column: span 4; justify-content:flex-end">
            <button class="btn btn-primary" @click="load" :disabled="loading" data-enter-stop><span v-if="loading" class="spinner"></span><Icon v-else name="file-text"/> عرض الكشف</button>
            <button class="btn" @click="preview" :disabled="!f.account_id"><Icon name="eye"/> معاينة</button>
            <button class="btn" @click="print" :disabled="!f.account_id"><Icon name="printer"/> طباعة</button>
          </div>
        </div>
      </div>
    </div>

    <template v-if="st">
      <div class="stats mb">
        <div class="stat" :class="st.material"><div class="stat-label">الرصيد الافتتاحي للفترة</div><div class="stat-value"><Bal :b="st.opening" :unit="u[st.material]" /></div>
          <div class="stat-sub">{{ st.date_from ? 'قبل ' + st.date_from : 'من بداية الحساب' }}</div></div>
        <div class="stat"><div class="stat-label">إجمالي المدين</div><div class="stat-value num">{{ g(st.totals.debit) }}</div><div class="stat-sub">{{ st.totals.count }} حركة في الفترة</div></div>
        <div class="stat"><div class="stat-label">إجمالي الدائن</div><div class="stat-value num">{{ g(st.totals.credit) }}</div></div>
        <div class="stat" :class="st.material"><div class="stat-label">الرصيد الختامي</div><div class="stat-value"><Bal :b="st.closing" :unit="u[st.material]" /></div>
          <div class="stat-sub">{{ st.date_to ? 'حتى ' + st.date_to : 'حتى الآن' }}</div></div>
        <div class="stat"><div class="stat-label">الرصيد الفعلي للحساب (كل الفترات)</div><div class="stat-value"><Bal :b="st.account_balance_all_time" /></div>
          <div class="stat-sub">مطابق لشاشة الأرصدة</div></div>
      </div>
      <div v-if="st.mixed_karats" class="alert warn mb"><Icon name="triangle-alert"/><div>الكشف يتضمن حركات ذهب مُعبَّر عنها بعيارات عمل مختلفة ({{ st.ref_karats.join('، ') }}) بسبب تغيير عيار العمل؛ لم تُحوَّل تلقائياً حفاظاً على القيم التاريخية. عمود «عيار» يوضح عيار كل حركة.</div></div>
      <div class="card">
        <div class="card-head"><h3>{{ 'كشف ' + MATERIAL_LABEL[st.material] }} — {{ st.account.name }} <span class="muted num">({{ st.account.account_no }})</span></h3>
          <div class="tools muted small">الوحدة: {{ u[st.material] }}{{ st.material === 'gold' ? ' بعيار العمل' : '' }}</div></div>
        <div class="tbl-wrap tall">
          <table class="tbl">
            <thead><tr><th>التاريخ</th><th>رقم المستند</th><th>نوع الحركة</th><th>البيان</th><th>رقم التشغيل</th><th v-if="st.mixed_karats">عيار</th>
              <th class="num">مدين</th><th class="num">دائن</th><th class="num">الرصيد بعد الحركة</th><th>ملاحظات</th></tr></thead>
            <tbody>
              <tr class="is-opening"><td class="num">{{ st.date_from || '' }}</td><td></td><td class="strong">رصيد افتتاحي للفترة</td><td class="muted">{{ st.date_from ? 'مجموع الحركات قبل ' + st.date_from : 'لا حركات سابقة' }}</td><td></td><td v-if="st.mixed_karats"></td><td></td><td></td>
                <td class="num"><Bal :b="st.opening" /></td><td></td></tr>
              <tr v-for="(r, i) in st.rows" :key="i" :class="{ 'is-reversal': r.is_reversal, 'is-cancelled': r.cancelled && !r.is_reversal }">
                <td class="num">{{ r.date }}</td>
                <td><button class="link num" @click="openDoc(r)">{{ r.doc_no }}</button></td>
                <td>{{ r.kind }} <span v-if="r.cancelled && !r.is_reversal" class="badge cancelled">ملغى</span></td>
                <td class="small">{{ r.text }}</td><td class="strong">{{ r.run_no }}</td>
                <td v-if="st.mixed_karats" class="num">{{ r.ref_karat }}</td>
                <td class="num">{{ g(r.debit) }}</td><td class="num">{{ g(r.credit) }}</td>
                <td class="num"><Bal :b="r.balance" /></td><td class="small muted">{{ r.notes }}</td>
              </tr>
            </tbody>
            <tfoot><tr><td colspan="2">الإجماليات</td><td>{{ st.totals.count }} حركة</td><td></td><td></td><td v-if="st.mixed_karats"></td>
              <td class="num">{{ g(st.totals.debit) }}</td><td class="num">{{ g(st.totals.credit) }}</td><td class="num"><Bal :b="st.closing" /></td><td></td></tr></tfoot>
          </table>
          <Empty v-if="!st.rows.length" text="لا توجد حركات في هذه الفترة" icon="file-text" />
        </div>
      </div>
    </template>
    <Empty v-else text="اختر العميل والفترة ونوع الكشف ثم اضغط «عرض الكشف»" icon="file-text" />
  </div>`,
};

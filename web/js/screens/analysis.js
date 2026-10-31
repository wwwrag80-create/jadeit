// الشاشة السادسة: تحليل حركة العميل — المبيعات، المرتجعات، المباع الصافي، السداد.
import { api } from "../api.js";
import { store, toastError, units } from "../store.js";
import { group } from "../num.js";
import { today, monthStart, yearStart, parseHashQuery, MATERIAL_LABEL } from "../util.js";
import { openPreview, analysisSpec } from "../components/print.js";

const { ref, reactive, computed, watch, onMounted } = Vue;

export const AnalysisScreen = {
  name: "AnalysisScreen",
  setup() {
    const f = reactive({ account_id: null, date_from: yearStart(), date_to: today() });
    const an = ref(null);
    const loading = ref(false);
    const panel = ref("sales");
    const u = computed(units);
    const account = computed(() => store.accounts.find((a) => a.id === f.account_id) || null);
    async function load() {
      if (!f.account_id) { toastError({ message: "اختر العميل أولاً" }, "لا يمكن عرض التحليل"); return; }
      loading.value = true;
      try { an.value = await api.get("/api/analysis", f); } catch (e) { toastError(e, "تعذر عرض التحليل"); } finally { loading.value = false; }
    }
    watch(() => store.dataVersion, () => { if (an.value) load(); });
    function period(kind) {
      if (kind === "month") { f.date_from = monthStart(); f.date_to = today(); }
      else if (kind === "year") { f.date_from = yearStart(); f.date_to = today(); }
      else { f.date_from = ""; f.date_to = ""; }
      if (f.account_id) load();
    }
    async function print() { if (an.value) await openPreview(analysisSpec(an.value)); }
    onMounted(() => {
      const p = parseHashQuery();
      if (p.get("account")) { f.account_id = Number(p.get("account")); f.date_from = ""; load(); }
    });
    const openDoc = (id) => { store.docViewId = id; };
    const DIR = { debit: "مدين", credit: "دائن", zero: "صفر" };
    return { store, f, an, loading, panel, u, account, load, period, print, openDoc, g: group, MATERIAL_LABEL, DIR };
  },
  template: `<div>
    <div class="page-head"><div><h1>تحليل حركة العميل</h1><p>الأوزان منفصلة عن الأجور، ولا يُعد قبض الذهب أو الألماس سداداً للأجور. كل الأرقام من المستندات المرحّلة فعلاً.</p></div></div>
    <div class="card mb"><div class="card-body">
      <div class="grid g6" style="align-items:end">
        <div class="field span2"><label class="req">اسم العميل</label><AccountPicker v-model="f.account_id" include-inactive autofocus /></div>
        <div class="field"><label>من تاريخ</label><input type="date" class="input" v-model="f.date_from" /></div>
        <div class="field"><label>إلى تاريخ</label><input type="date" class="input" v-model="f.date_to" /></div>
        <div class="field"><label>الفترة</label><div class="row" style="gap:4px"><button class="btn btn-sm" @click="period('month')">الشهر</button><button class="btn btn-sm" @click="period('year')">السنة</button><button class="btn btn-sm" @click="period('all')">الكل</button></div></div>
        <div class="row"><button class="btn btn-primary" @click="load" :disabled="loading"><span v-if="loading" class="spinner"></span><Icon v-else name="chart-column"/> عرض</button>
          <button class="btn" @click="print" :disabled="!an"><Icon name="printer"/> طباعة التقرير</button></div>
      </div>
    </div></div>

    <template v-if="an">
      <div class="stats mb">
        <div class="stat"><div class="stat-label"><Icon name="receipt" size="sm"/> إجمالي المبيعات</div>
          <div class="stat-lines"><div><span class="small">ذهب</span><span class="num">{{ g(an.sales.totals.gold) }} <span class="stat-unit">{{ u.gold }}</span></span></div>
            <div><span class="small">ألماس</span><span class="num">{{ g(an.sales.totals.diamond) }} <span class="stat-unit">{{ u.diamond }}</span></span></div>
            <div><span class="small">أجور</span><span class="num">{{ g(an.sales.totals.wage) }} <span class="stat-unit">{{ u.wage }}</span></span></div></div></div>
        <div class="stat"><div class="stat-label"><Icon name="undo-2" size="sm"/> إجمالي المرتجعات</div>
          <div class="stat-lines"><div><span class="small">ذهب</span><span class="num">{{ g(an.returns.totals.gold) }} <span class="stat-unit">{{ u.gold }}</span></span></div>
            <div><span class="small">ألماس</span><span class="num">{{ g(an.returns.totals.diamond) }} <span class="stat-unit">{{ u.diamond }}</span></span></div>
            <div><span class="small">أجور مستردة</span><span class="num">{{ g(an.returns.totals.wage) }} <span class="stat-unit">{{ u.wage }}</span></span></div></div></div>
        <div class="stat"><div class="stat-label"><Icon name="equal" size="sm"/> صافي المباع</div>
          <div class="stat-lines"><div><span class="small">ذهب</span><span class="num">{{ g(an.net.totals.gold.signed) }} <span class="stat-unit">{{ u.gold }}</span></span></div>
            <div><span class="small">ألماس</span><span class="num">{{ g(an.net.totals.diamond.signed) }} <span class="stat-unit">{{ u.diamond }}</span></span></div>
            <div><span class="small">أجور</span><span class="num">{{ g(an.net.totals.wage.signed) }} <span class="stat-unit">{{ u.wage }}</span></span></div></div></div>
        <div class="stat"><div class="stat-label"><Icon name="arrow-left-right" size="sm"/> إجمالي السداد (قبض − صرف)</div>
          <div class="stat-lines"><div><span class="small">ذهب</span><span class="num">{{ g(an.payments.totals.gold.net) }} <span class="stat-unit">{{ u.gold }}</span></span></div>
            <div><span class="small">ألماس</span><span class="num">{{ g(an.payments.totals.diamond.net) }} <span class="stat-unit">{{ u.diamond }}</span></span></div>
            <div><span class="small">أجور</span><span class="num">{{ g(an.payments.totals.wage.net) }} <span class="stat-unit">{{ u.wage }}</span></span></div></div></div>
      </div>
      <div class="stats mb">
        <div v-for="m in ['gold','diamond','wage']" :key="m" class="stat" :class="m">
          <div class="stat-label">رصيد {{ MATERIAL_LABEL[m] }} الحالي <span class="muted">({{ u[m] }})</span></div>
          <div class="stat-value"><Bal :b="an.balances[m]" /></div>
          <div class="stat-sub" v-if="an.date_to">في نهاية الفترة: <span class="num strong">{{ g(an.balances_at_end[m].value) }}</span> {{ DIR[an.balances_at_end[m].direction] }}</div>
        </div>
      </div>
      <div v-if="an.cancelled_count" class="alert info mb"><Icon name="info"/><div>يوجد {{ an.cancelled_count }} مستند ملغى في الفترة، وهي مستبعدة من التحليل (أثرها صفر في الأرصدة).</div></div>
      <div v-if="an.returns.unlinked_count" class="alert warn mb"><Icon name="triangle-alert"/><div>يوجد {{ an.returns.unlinked_count }} سطر مرتجع غير مرتبط بفاتورة أصلية (استثناء)، وهو محسوب في صافي المباع ومميَّز في الجداول.</div></div>

      <div class="grid g4 mb">
        <button v-for="p in [{id:'sales',t:'المبيعات',i:'receipt',n:an.sales.count},{id:'returns',t:'المرتجعات',i:'undo-2',n:an.returns.count},{id:'net',t:'المباع الصافي',i:'equal',n:an.net.rows.length},{id:'payments',t:'السداد',i:'arrow-left-right',n:an.payments.count}]"
          :key="p.id" class="stat" style="text-align:right;cursor:pointer;font:inherit" :style="panel === p.id ? 'border-color:var(--brand);box-shadow:0 0 0 2px var(--brand-soft)' : ''" @click="panel = p.id">
          <div class="stat-label"><Icon :name="p.i" size="sm"/> {{ p.t }}</div><div class="stat-value num" style="font-size:1.3rem">{{ p.n }} <span class="stat-unit">{{ p.id === 'net' ? 'فاتورة' : p.id === 'payments' ? 'سند' : 'سطر' }}</span></div></button>
      </div>

      <div class="card">
        <div class="tbl-wrap tall">
          <table class="tbl" v-if="panel === 'sales'">
            <thead><tr><th>التاريخ</th><th>رقم الفاتورة</th><th>رقم التشغيل</th><th class="num">وزن الذهب ({{ u.gold }})</th><th class="num">وزن الألماس ({{ u.diamond }})</th><th class="num">الأجر المعتمد</th><th class="num">إجمالي الأجر ({{ u.wage }})</th></tr></thead>
            <tbody><tr v-for="(r, i) in an.sales.rows" :key="i"><td class="num">{{ r.date }}</td><td><button class="link num" @click="openDoc(r.doc_id)">{{ r.doc_no }}</button></td><td class="strong">{{ r.run_no }}</td>
              <td class="num">{{ g(r.gold) }}</td><td class="num">{{ g(r.diamond) }}</td><td class="num">{{ r.rate }}</td><td class="num">{{ g(r.wage) }}</td></tr></tbody>
            <tfoot><tr><td colspan="3">الإجمالي ({{ an.sales.count }} سطر)</td><td class="num">{{ g(an.sales.totals.gold) }}</td><td class="num">{{ g(an.sales.totals.diamond) }}</td><td></td><td class="num">{{ g(an.sales.totals.wage) }}</td></tr></tfoot>
          </table>
          <table class="tbl" v-if="panel === 'returns'">
            <thead><tr><th>التاريخ</th><th>رقم المرتجع</th><th>الفاتورة الأصلية</th><th>رقم التشغيل</th><th class="num">الذهب المرتجع</th><th class="num">الألماس المرتجع</th><th class="num">الأجر المسترد</th><th>البيان</th></tr></thead>
            <tbody><tr v-for="(r, i) in an.returns.rows" :key="i"><td class="num">{{ r.date }}</td><td><button class="link num" @click="openDoc(r.doc_id)">{{ r.doc_no }}</button></td>
              <td><span v-if="r.original_doc_no" class="num">{{ r.original_doc_no }}</span><span v-else class="badge warn" :title="r.exception_reason">غير مرتبط — استثناء</span></td>
              <td class="strong">{{ r.run_no }}</td><td class="num">{{ g(r.gold) }}</td><td class="num">{{ g(r.diamond) }}</td><td class="num">{{ g(r.wage) }}</td><td class="small">{{ r.text }}</td></tr></tbody>
            <tfoot><tr><td colspan="4">الإجمالي ({{ an.returns.count }} سطر)</td><td class="num">{{ g(an.returns.totals.gold) }}</td><td class="num">{{ g(an.returns.totals.diamond) }}</td><td class="num">{{ g(an.returns.totals.wage) }}</td><td></td></tr></tfoot>
          </table>
          <table class="tbl" v-if="panel === 'net'">
            <thead><tr><th>الفاتورة</th><th>التاريخ</th><th class="num">ذهب مباع</th><th class="num">ذهب مرتجع</th><th class="num">صافي الذهب</th><th class="num">ألماس مباع</th><th class="num">ألماس مرتجع</th><th class="num">صافي الألماس</th><th class="num">أجور</th><th class="num">مستردة</th><th class="num">صافي الأجور</th><th></th></tr></thead>
            <tbody><tr v-for="(r, i) in an.net.rows" :key="i" :style="r.kind === 'unlinked' ? 'background:var(--warn-bg)' : ''">
              <td class="num strong">{{ r.doc_no }}</td><td class="num">{{ r.doc_date }}</td>
              <td class="num">{{ g(r.sold.gold) }}</td><td class="num">{{ g(r.returned.gold) }}</td><td class="num strong">{{ g(r.net.gold.signed) }}</td>
              <td class="num">{{ g(r.sold.diamond) }}</td><td class="num">{{ g(r.returned.diamond) }}</td><td class="num strong">{{ g(r.net.diamond.signed) }}</td>
              <td class="num">{{ g(r.sold.wage) }}</td><td class="num">{{ g(r.returned.wage) }}</td><td class="num strong">{{ g(r.net.wage.signed) }}</td>
              <td><span v-if="r.kind === 'unlinked'" class="badge warn">مرتجع غير مرتبط</span><span v-else-if="r.invoice_outside_period" class="badge info" title="الفاتورة قبل الفترة؛ المرتجع داخلها">فاتورة خارج الفترة</span></td></tr></tbody>
            <tfoot><tr><td colspan="2">الصافي للفترة</td><td class="num">{{ g(an.sales.totals.gold) }}</td><td class="num">{{ g(an.returns.totals.gold) }}</td><td class="num">{{ g(an.net.totals.gold.signed) }}</td>
              <td class="num">{{ g(an.sales.totals.diamond) }}</td><td class="num">{{ g(an.returns.totals.diamond) }}</td><td class="num">{{ g(an.net.totals.diamond.signed) }}</td>
              <td class="num">{{ g(an.sales.totals.wage) }}</td><td class="num">{{ g(an.returns.totals.wage) }}</td><td class="num">{{ g(an.net.totals.wage.signed) }}</td><td></td></tr></tfoot>
          </table>
          <table class="tbl" v-if="panel === 'payments'">
            <thead><tr><th>التاريخ</th><th>رقم السند</th><th>الحركة</th><th>نوع المادة</th><th class="num">الوزن الفعلي / المبلغ</th><th class="num">العيار الفعلي</th><th class="num">عيار العمل</th><th class="num">الوزن المكافئ</th><th>البيان</th></tr></thead>
            <tbody><tr v-for="(r, i) in an.payments.rows" :key="i"><td class="num">{{ r.date }}</td><td><button class="link num" @click="openDoc(r.doc_id)">{{ r.doc_no }}</button></td>
              <td><span class="badge" :class="r.doc_type === 'receipt' ? 'credit' : 'debit'">{{ r.kind }}</span></td><td><MaterialBadge :m="r.material"/></td>
              <td class="num">{{ g(r.actual) }}</td><td class="num">{{ r.karat || '—' }}</td><td class="num">{{ r.working_karat || '—' }}</td><td class="num strong">{{ r.equivalent ? g(r.equivalent) : '—' }}</td><td class="small">{{ r.text }}</td></tr></tbody>
            <tfoot>
              <tr v-for="m in ['gold','diamond','wage']" :key="m"><td colspan="3"><MaterialBadge :m="m"/> قبض <span class="num">{{ g(an.payments.totals[m].in) }}</span> — صرف <span class="num">{{ g(an.payments.totals[m].out) }}</span></td>
                <td colspan="6">صافي السداد: <span class="num">{{ g(an.payments.totals[m].net) }}</span> {{ u[m] }}</td></tr></tfoot>
          </table>
          <Empty v-if="(panel === 'sales' && !an.sales.rows.length) || (panel === 'returns' && !an.returns.rows.length) || (panel === 'net' && !an.net.rows.length) || (panel === 'payments' && !an.payments.rows.length)" text="لا توجد حركات في هذه الفترة" icon="chart-column" />
        </div>
      </div>
    </template>
    <Empty v-else text="اختر العميل والفترة ثم اضغط «عرض»" icon="chart-column" />
  </div>`,
};

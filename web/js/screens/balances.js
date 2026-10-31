// الشاشة الرابعة: الأرصدة — حالة كل الحسابات بأرصدة منفصلة (ذهب / ألماس / أجور).
import { api } from "../api.js";
import { store, units } from "../store.js";
import { group } from "../num.js";
import { STATUS_LABEL, debounce, local } from "../util.js";

const { ref, reactive, computed, watch, onMounted } = Vue;

export const BalancesScreen = {
  name: "BalancesScreen",
  setup() {
    const f = reactive(local.get("balances:filters", { q: "", filter: "all", material: "any", sort: "account_no", dir: "asc", page: 1, size: 100 }));
    f.q = "";
    f.page = 1;
    const data = ref(null);
    const loading = ref(false);
    const u = computed(units);
    async function load() {
      loading.value = true;
      try { data.value = await api.get("/api/balances", f); } catch (e) { /* يُعرض في الشريط */ data.value = null; } finally { loading.value = false; }
      local.set("balances:filters", { ...f, q: "" });
    }
    const loadDebounced = debounce(() => { f.page = 1; load(); }, 250);
    watch(() => f.q, loadDebounced);
    watch(() => [f.filter, f.material, f.size], () => { f.page = 1; load(); });
    watch(() => store.dataVersion, load);
    onMounted(load);
    function sortBy(col) {
      if (f.sort === col) f.dir = f.dir === "asc" ? "desc" : "asc";
      else { f.sort = col; f.dir = col === "name" || col === "account_no" ? "asc" : "desc"; }
      load();
    }
    const arrow = (col) => (f.sort === col ? (f.dir === "asc" ? "▲" : "▼") : "");
    function page(n) { f.page = n; load(); }
    const open = (r) => { store.accountPanelId = r.id; };
    return { store, f, data, loading, u, sortBy, arrow, page, open, g: group, STATUS_LABEL };
  },
  template: `<div>
    <div class="page-head">
      <div><h1>الأرصدة</h1><p>رصيد مستقل لكل نوع لكل حساب، محسوب من الحركات المرحّلة فعلياً. مدين = مستحق على العميل، دائن = مستحق للعميل.</p></div>
    </div>
    <div class="stats mb" v-if="data">
      <div class="stat gold"><div class="stat-label"><Icon name="coins" size="sm"/> أرصدة الذهب ({{ u.gold }})</div>
        <div class="stat-lines"><div><span class="badge debit">▲ مدينة</span><span class="num">{{ g(data.totals.gold.debit) }}</span></div><div><span class="badge credit">▼ دائنة</span><span class="num">{{ g(data.totals.gold.credit) }}</span></div></div></div>
      <div class="stat diamond"><div class="stat-label"><Icon name="gem" size="sm"/> أرصدة الألماس ({{ u.diamond }})</div>
        <div class="stat-lines"><div><span class="badge debit">▲ مدينة</span><span class="num">{{ g(data.totals.diamond.debit) }}</span></div><div><span class="badge credit">▼ دائنة</span><span class="num">{{ g(data.totals.diamond.credit) }}</span></div></div></div>
      <div class="stat wage"><div class="stat-label"><Icon name="wallet" size="sm"/> أرصدة الأجور ({{ u.wage }})</div>
        <div class="stat-lines"><div><span class="badge debit">▲ مدينة</span><span class="num">{{ g(data.totals.wage.debit) }}</span></div><div><span class="badge credit">▼ دائنة</span><span class="num">{{ g(data.totals.wage.credit) }}</span></div></div></div>
      <div class="stat"><div class="stat-label"><Icon name="users" size="sm"/> الحسابات المعروضة</div><div class="stat-value num">{{ data.totals.count }}</div>
        <div class="stat-sub">حسب عوامل التصفية الحالية</div></div>
    </div>
    <div class="card">
      <div class="card-head" style="gap:10px">
        <input class="input" style="max-width:320px" v-model="f.q" placeholder="بحث باسم العميل أو رقم الحساب…" aria-label="بحث" />
        <select class="select" style="max-width:190px" v-model="f.filter" aria-label="تصفية">
          <option value="all">كل الحسابات</option><option value="nonzero">ذات الأرصدة فقط</option>
          <option value="debit">الحسابات المدينة</option><option value="credit">الحسابات الدائنة</option><option value="zero">المسددة (صفر)</option>
        </select>
        <select class="select" style="max-width:170px" v-model="f.material" aria-label="نوع الرصيد للتصفية">
          <option value="any">أي نوع رصيد</option><option value="gold">رصيد الذهب</option><option value="diamond">رصيد الألماس</option><option value="wage">رصيد الأجور</option>
        </select>
        <div class="tools"><span v-if="loading" class="spinner" style="color:var(--text-3)"></span>
          <select class="select" style="width:auto" v-model.number="f.size" aria-label="عدد الصفوف"><option :value="50">50</option><option :value="100">100</option><option :value="250">250</option><option :value="500">500</option></select></div>
      </div>
      <div class="tbl-wrap tall">
        <table class="tbl">
          <thead><tr>
            <th style="cursor:pointer" @click="sortBy('account_no')">رقم الحساب {{ arrow('account_no') }}</th>
            <th style="cursor:pointer" @click="sortBy('name')">اسم العميل {{ arrow('name') }}</th>
            <th class="num" style="cursor:pointer" @click="sortBy('gold')">رصيد الذهب ({{ u.gold }}) {{ arrow('gold') }}</th>
            <th class="num" style="cursor:pointer" @click="sortBy('wage')">رصيد الأجور ({{ u.wage }}) {{ arrow('wage') }}</th>
            <th class="num" style="cursor:pointer" @click="sortBy('diamond')">رصيد الألماس ({{ u.diamond }}) {{ arrow('diamond') }}</th>
            <th>حالة الحساب</th><th></th>
          </tr></thead>
          <tbody v-if="data">
            <tr v-for="r in data.items" :key="r.id">
              <td class="num strong">{{ r.account_no }}</td>
              <td><button class="link" @click="open(r)" style="font-size:.98rem">{{ r.name }}</button> <span v-if="!r.is_active" class="badge warn">موقوف</span></td>
              <td class="num"><Bal :b="r.gold" /><span v-if="r.gold_mixed_karats" class="badge warn" title="يتضمن حركات بعيارات عمل مختلفة" style="margin-inline-start:4px">مختلط العيار</span></td>
              <td class="num"><Bal :b="r.wage" /></td>
              <td class="num"><Bal :b="r.diamond" /></td>
              <td><span class="badge" :class="r.status">{{ STATUS_LABEL[r.status] }}</span></td>
              <td><button class="btn btn-sm" @click="open(r)"><Icon name="external-link" size="sm"/> فتح الحساب</button></td>
            </tr>
          </tbody>
        </table>
        <Empty v-if="data && !data.items.length" text="لا توجد حسابات مطابقة" icon="scale" />
      </div>
      <div class="pagination" v-if="data && data.pages > 1">
        <button class="btn btn-sm" :disabled="f.page <= 1" @click="page(f.page - 1)">السابق</button>
        <span class="small">صفحة <span class="num">{{ data.page }}</span> من <span class="num">{{ data.pages }}</span></span>
        <button class="btn btn-sm" :disabled="f.page >= data.pages" @click="page(f.page + 1)">التالي</button>
      </div>
    </div>
  </div>`,
};

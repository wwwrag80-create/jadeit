// الشاشة الأولى: الحسابات (إنشاء حساب عميل وتعديل بياناته).
import { api } from "../api.js";
import { store, can, toast, toastError, loadAccounts, dataChanged } from "../store.js";
import { parse } from "../num.js";
import { newToken, debounce, parseHashQuery, go } from "../util.js";
import { normalizeAr } from "../components/ui.js";

const { ref, reactive, computed, watch, onMounted, nextTick } = Vue;

export const AccountsScreen = {
  name: "AccountsScreen",
  setup() {
    const blank = () => ({ id: null, name: "", phone: "", notes: "", wage_rate: "", is_active: true, version: 0, reason: "" });
    const f = reactive(blank());
    const original = ref(null);
    const token = ref(newToken());
    const nextNo = ref("");
    const busy = ref(false);
    const errors = reactive({});
    const nameCheck = ref(null);
    const created = ref(null);
    const q = ref("");
    const nameInput = ref(null);

    const editing = computed(() => !!f.id);
    const canManage = computed(() => can("accounts.manage"));
    const canWage = computed(() => !editing.value || can("accounts.wage"));
    const rateErr = computed(() => {
      if (f.wage_rate === "") return "";
      const r = parse(f.wage_rate, 3);
      return r.ok ? "" : r.error;
    });
    const dirty = computed(() => {
      if (!editing.value) return !!(f.name || f.phone || f.notes || f.wage_rate);
      const o = original.value;
      return o && (o.name !== f.name || o.phone !== f.phone || o.notes !== f.notes || o.wage_rate !== f.wage_rate || o.is_active !== f.is_active);
    });

    async function refreshNextNo() {
      try { nextNo.value = (await api.get("/api/accounts/next-no")).account_no; } catch { /* */ }
    }
    const checkName = debounce(async () => {
      if (f.name.trim().length < 2) { nameCheck.value = null; return; }
      try { nameCheck.value = await api.get("/api/accounts/check-name", { name: f.name, exclude: f.id || "" }); } catch { /* */ }
    }, 300);
    watch(() => f.name, checkName);

    function clear() {
      Object.assign(f, blank());
      Object.keys(errors).forEach((k) => delete errors[k]);
      original.value = null;
      nameCheck.value = null;
      token.value = newToken();
      if (location.hash.includes("edit=")) go("accounts");
      nextTick(() => nameInput.value && nameInput.value.focus());
    }

    function validate() {
      Object.keys(errors).forEach((k) => delete errors[k]);
      if (f.name.trim().length < 2) errors.name = "اكتب اسم العميل (حرفان على الأقل)";
      else if (nameCheck.value && !nameCheck.value.available) errors.name = `الاسم مستخدم في الحساب ${nameCheck.value.account_no}`;
      if (f.wage_rate === "") errors.wage_rate = "الأجر المعتمد مطلوب (اكتب 0 إن لم يوجد أجر)";
      else if (rateErr.value) errors.wage_rate = rateErr.value;
      if (f.phone && !/^\+?[0-9٠-٩][0-9٠-٩ \-]{4,24}$/.test(f.phone.trim())) errors.phone = "رقم الجوال غير صالح";
      if (editing.value && original.value && original.value.wage_rate !== f.wage_rate && f.reason.trim().length < 3) errors.reason = "اكتب سبب تعديل الأجر";
      return Object.keys(errors).length === 0;
    }

    async function save() {
      if (busy.value || !canManage.value) return;
      if (!validate()) { toast("error", "راجع الحقول المظللة"); return; }
      busy.value = true;
      try {
        if (editing.value) {
          const a = await api.put(`/api/accounts/${f.id}`, { name: f.name, phone: f.phone, notes: f.notes, wage_rate: f.wage_rate,
            is_active: f.is_active, version: f.version, reason: f.reason });
          toast("success", "تم حفظ التعديلات", `${a.name} — رقم ${a.account_no}` + (original.value.wage_rate !== a.wage_rate ? "\nالأجر الجديد يسري على العمليات الجديدة فقط." : ""));
          load(a);
        } else {
          const a = await api.post("/api/accounts", { name: f.name, phone: f.phone, notes: f.notes, wage_rate: f.wage_rate, client_token: token.value });
          created.value = a;
          toast("success", "تم إنشاء الحساب بنجاح", `${a.name} — رقم الحساب ${a.account_no}`, { actions: [{ label: "فتح الحساب", run: () => (store.accountPanelId = a.id) }] });
          Object.assign(f, blank());
          token.value = newToken();
          nameCheck.value = null;
          refreshNextNo();
          nextTick(() => nameInput.value && nameInput.value.focus());
        }
        await loadAccounts();
        dataChanged();
      } catch (e) {
        if (e.details && e.details.field) errors[e.details.field] = e.message;
        toastError(e, editing.value ? "تعذر حفظ التعديلات" : "تعذر إنشاء الحساب");
      } finally { busy.value = false; }
    }

    function load(a) {
      created.value = null;
      Object.assign(f, { id: a.id, name: a.name, phone: a.phone, notes: a.notes, wage_rate: a.wage_rate, is_active: a.is_active, version: a.version, reason: "" });
      original.value = { ...a };
      Object.keys(errors).forEach((k) => delete errors[k]);
      nameCheck.value = null;
    }
    async function loadById(id) {
      try { load(await api.get(`/api/accounts/${id}`)); } catch (e) { toastError(e); }
    }

    const list = computed(() => {
      const t = normalizeAr(q.value);
      const all = store.accounts;
      if (!t) return all.slice().reverse().slice(0, 300);
      return all.filter((a) => normalizeAr(a.name).includes(t) || a.account_no.startsWith(t) || (a.phone || "").includes(t)).slice(0, 300);
    });

    function onKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
    }
    onMounted(() => {
      refreshNextNo();
      const p = parseHashQuery();
      if (p.get("edit")) loadById(p.get("edit"));
      else nextTick(() => nameInput.value && nameInput.value.focus());
    });
    watch(() => store.dataVersion, refreshNextNo);

    return { store, f, original, errors, busy, editing, canManage, canWage, rateErr, dirty, nextNo, nameCheck, created, q, list, nameInput,
      save, clear, load, onKey, go };
  },
  template: `<div @keydown="onKey">
    <div class="page-head">
      <div><h1>الحسابات</h1><p>إنشاء حسابات العملاء وتحديد الأجر المعتمد لكل حساب. تعديل الأجر لا يغيّر أجور العمليات المرحّلة سابقاً.</p></div>
    </div>
    <div class="split">
      <div>
        <div v-if="created" class="alert ok mb"><Icon name="circle-check"/>
          <div style="flex:1">تم إنشاء الحساب <b>{{ created.name }}</b> برقم <b class="num">{{ created.account_no }}</b> وأجر <b class="num">{{ created.wage_rate }}</b> لكل جرام.
            <div class="row" style="margin-top:8px">
              <button class="btn btn-sm btn-primary" @click="store.accountPanelId = created.id"><Icon name="external-link" size="sm"/> فتح الحساب</button>
              <button class="btn btn-sm" @click="go('sales', { account: created.id })"><Icon name="receipt" size="sm"/> فاتورة مبيعات</button>
              <button class="btn btn-sm" @click="go('opening', { account: created.id })"><Icon name="book-open" size="sm"/> رصيد افتتاحي</button>
            </div></div>
          <button class="btn btn-ghost btn-icon" @click="created = null"><Icon name="x"/></button></div>

        <div class="card">
          <div class="card-head">
            <Icon :name="editing ? 'pencil' : 'user-plus'"/>
            <h2>{{ editing ? 'تعديل بيانات الحساب' : 'إضافة حساب جديد' }}</h2>
            <span v-if="editing && !f.is_active" class="badge warn">موقوف</span>
            <div class="tools"><span class="muted small">حفظ سريع: <span class="kbd" style="color:var(--text)">Ctrl+S</span></span></div>
          </div>
          <div class="card-body" data-focus-scope>
            <div v-if="!canManage" class="alert info mb"><Icon name="lock"/><div>لا تملك صلاحية إنشاء الحسابات أو تعديلها.</div></div>
            <div class="grid g3">
              <div class="field span2"><label class="req" for="acc-name">اسم العميل / الحساب</label>
                <input id="acc-name" ref="nameInput" class="input" :class="{ 'is-invalid': errors.name || (nameCheck && !nameCheck.available) }" v-model="f.name"
                  maxlength="100" autocomplete="off" :readonly="!canManage" @keydown.enter.prevent="$event.target.closest('[data-focus-scope]').querySelector('#acc-phone').focus()" />
                <span v-if="nameCheck && !nameCheck.available" class="field-error"><Icon name="circle-alert" size="sm"/> يوجد حساب بالاسم نفسه: {{ nameCheck.name }} (رقم {{ nameCheck.account_no }})
                  <button class="btn btn-sm btn-ghost" @click="store.accountPanelId = nameCheck.id">فتحه</button></span>
                <span v-else-if="errors.name" class="field-error">{{ errors.name }}</span>
                <span v-else-if="nameCheck && nameCheck.available" class="hint" style="color:var(--credit)">✓ الاسم متاح</span>
              </div>
              <div class="field"><label>رقم الحساب</label>
                <div class="readout num">{{ editing ? (original && original.account_no) : nextNo }}</div>
                <span class="hint">{{ editing ? 'رقم ثابت لا يتغير' : 'تلقائي — يُثبَّت عند الإنشاء' }}</span></div>
              <div class="field"><label for="acc-phone">رقم الجوال <span class="muted">(اختياري)</span></label>
                <input id="acc-phone" class="input ltr" style="text-align:left" :class="{ 'is-invalid': errors.phone }" v-model="f.phone" inputmode="tel" maxlength="30" :readonly="!canManage"
                  @keydown.enter.prevent="$event.target.closest('[data-focus-scope]').querySelector('#acc-rate').focus()" />
                <span v-if="errors.phone" class="field-error">{{ errors.phone }}</span></div>
              <div class="field"><label class="req" for="acc-rate">الأجر المعتمد لكل جرام ذهب</label>
                <NumInput id="acc-rate" v-model="f.wage_rate" :dp="3" :invalid="!!errors.wage_rate" :readonly="!canManage || !canWage" placeholder="مثال: 5.50" label="الأجر المعتمد"
                  @enter="$event.target.closest('[data-focus-scope]').querySelector('#acc-notes').focus(); $event.defaultHandled = true" />
                <span v-if="errors.wage_rate || rateErr" class="field-error">{{ errors.wage_rate || rateErr }}</span>
                <span v-else-if="editing && !canWage" class="hint">تعديل الأجر يحتاج صلاحية خاصة</span>
                <span v-else class="hint">يُجلب تلقائياً في المبيعات ({{ store.settings.wage_unit }} / جم)</span></div>
              <div class="field" v-if="editing"><label>حالة الحساب</label>
                <label class="check" style="height:40px"><input type="checkbox" v-model="f.is_active" :disabled="!canManage"/> الحساب نشط (يقبل حركات جديدة)</label></div>
              <div class="field" :class="editing ? 'span3' : 'span3'"><label for="acc-notes">ملاحظات <span class="muted">(اختياري)</span></label>
                <textarea id="acc-notes" class="textarea" v-model="f.notes" maxlength="1000" :readonly="!canManage"></textarea></div>
              <div class="field span3" v-if="editing && original && original.wage_rate !== f.wage_rate">
                <label class="req" for="acc-reason">سبب تعديل الأجر الافتراضي</label><input id="acc-reason" class="input" :class="{ 'is-invalid': errors.reason }" v-model="f.reason" />
                <span v-if="errors.reason" class="field-error">{{ errors.reason }}</span>
                <span class="hint">من {{ original.wage_rate }} إلى {{ f.wage_rate || '—' }} — يسري على العمليات الجديدة فقط ويُسجَّل في سجل التعديلات.</span></div>
            </div>
          </div>
          <div class="card-foot row">
            <button class="btn btn-primary" @click="save" :disabled="busy || !canManage" data-focusable>
              <span v-if="busy" class="spinner"></span><Icon v-else :name="editing ? 'save' : 'user-plus'"/> {{ editing ? 'حفظ التعديلات' : 'إنشاء حساب' }}</button>
            <button class="btn" @click="clear" :disabled="busy"><Icon name="eraser"/> {{ editing ? 'إلغاء التعديل' : 'مسح الحقول' }}</button>
            <button v-if="editing" class="btn btn-ghost" @click="store.accountPanelId = f.id"><Icon name="external-link"/> فتح الحساب</button>
            <span v-if="dirty" class="muted small" style="margin-inline-start:auto">تغييرات غير محفوظة</span>
          </div>
        </div>
        <div class="alert info mt"><Icon name="info"/><div>
          <b>قواعد منع التكرار:</b> رقم الحساب تلقائي وفريد. يُعد الاسم مكرراً إذا تطابق بعد تجاهل المسافات الزائدة والتشكيل والتطويل،
          وتوحيد الهمزات (أ إ آ ← ا) والتاء المربوطة (ة ← ه) والألف المقصورة (ى ← ي). الضغط على «إنشاء حساب» أكثر من مرة لا ينشئ حساباً ثانياً.</div></div>
      </div>

      <div class="card">
        <div class="card-head"><Icon name="users"/><h3>الحسابات المسجلة</h3><span class="badge neutral">{{ store.accounts.length }}</span></div>
        <div class="card-body" style="padding-bottom:8px"><input class="input" v-model="q" placeholder="بحث بالاسم أو الرقم أو الجوال…" /></div>
        <div class="tbl-wrap" style="max-height:60vh">
          <table class="tbl">
            <thead><tr><th>الرقم</th><th>الاسم</th><th class="num">الأجر</th><th></th></tr></thead>
            <tbody>
              <tr v-for="a in list" :key="a.id" class="clickable" :class="{ 'active-row': a.id === f.id }" @click="load(a)">
                <td class="num">{{ a.account_no }}</td><td><span class="strong">{{ a.name }}</span> <span v-if="!a.is_active" class="badge warn">موقوف</span></td>
                <td class="num">{{ a.wage_rate }}</td>
                <td><button class="btn btn-sm btn-ghost" @click.stop="store.accountPanelId = a.id" title="فتح الحساب"><Icon name="external-link" size="sm"/></button></td>
              </tr>
            </tbody>
          </table>
          <Empty v-if="!list.length" :text="store.accounts.length ? 'لا نتائج مطابقة' : 'لا توجد حسابات بعد — أنشئ أول حساب من النموذج'" icon="users"/>
        </div>
      </div>
    </div>
  </div>`,
};

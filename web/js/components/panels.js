// اللوحة التفصيلية للحساب + نافذة الإعدادات العامة + تغيير عيار العمل + الدخول/الإعداد الأول.
import { api } from "../api.js";
import { store, can, toast, toastError, applyBoot, loadAccounts, dataChanged, units } from "../store.js";
import { group } from "../num.js";
import { MATERIAL_LABEL, STATUS_LABEL, fmtDateTime, go } from "../util.js";
import { openPreview, accountSpec } from "./print.js";

const { ref, reactive, computed, watch, onMounted } = Vue;

// ============================================================================
//  لوحة الحساب التفصيلية (تُفتح من الأرصدة أو بعد إنشاء الحساب)
// ============================================================================
export const AccountPanel = {
  name: "AccountPanel",
  setup() {
    const s = ref(null);
    const u = computed(units);
    async function load() {
      if (!store.accountPanelId) { s.value = null; return; }
      try { s.value = await api.get(`/api/accounts/${store.accountPanelId}/summary`); }
      catch (e) { toastError(e, "تعذر فتح الحساب"); store.accountPanelId = null; }
    }
    watch(() => [store.accountPanelId, store.dataVersion], load, { immediate: true });
    const close = () => { store.accountPanelId = null; };
    const nav = (route, params) => { close(); go(route, params); };
    const print = async () => openPreview(accountSpec(s.value));
    const icons = { gold: "coins", diamond: "gem", wage: "wallet" };
    return { store, s, u, close, nav, print, icons, g: group, MATERIAL_LABEL, STATUS_LABEL, fmtDateTime, can };
  },
  template: `<Drawer v-if="store.accountPanelId && s" @close="close">
    <template #head>
      <div class="muted small">حساب رقم <span class="num strong">{{ s.account.account_no }}</span></div>
      <h3 style="font-size:1.25rem">{{ s.account.name }}</h3>
      <div class="row small" style="margin-top:4px;gap:6px">
        <span class="badge" :class="s.status">{{ STATUS_LABEL[s.status] }}</span>
        <span v-if="!s.account.is_active" class="badge warn">موقوف</span>
        <span class="badge neutral">الأجر الافتراضي: <span class="num">{{ s.account.wage_rate }}</span> / جم</span>
        <span v-if="s.account.phone" class="badge neutral num">{{ s.account.phone }}</span>
      </div>
    </template>
    <div v-for="m in ['gold','diamond','wage']" :key="m" class="section-box" :class="m">
      <div class="sb-head"><Icon :name="icons[m]" size="sm"/> {{ MATERIAL_LABEL[m] }} <span class="small" style="margin-inline-start:auto;font-weight:500">الوحدة: {{ u[m] || '—' }}</span></div>
      <div class="sb-grid">
        <div><div class="k">مدين {{ MATERIAL_LABEL[m].replace('ال','') }}</div><div class="v num">{{ g(s.sections[m].debit) }}</div></div>
        <div><div class="k">دائن {{ MATERIAL_LABEL[m].replace('ال','') }}</div><div class="v num">{{ g(s.sections[m].credit) }}</div></div>
        <div><div class="k">رصيد {{ MATERIAL_LABEL[m] }}</div><div class="v"><Bal :b="s.sections[m].balance" /></div></div>
      </div>
      <div v-if="m === 'gold' && s.sections.gold.mixed_karats" style="padding:8px 14px;border-top:1px solid var(--border)" class="small">
        <div class="alert warn" style="padding:6px 10px"><Icon name="triangle-alert" size="sm"/><div>الرصيد يتضمن حركات بعيارات عمل مختلفة (لم تُحوَّل تلقائياً):
          <span v-for="k in s.sections.gold.by_karat" :key="k.karat" style="margin-inline-start:8px">عيار {{ k.karat }}: <b class="num">{{ g(k.balance.value) }}</b> {{ ({debit:'مدين',credit:'دائن',zero:''})[k.balance.direction] }}</span></div></div>
      </div>
    </div>
    <div class="mt">
      <div class="row" style="justify-content:space-between"><b>آخر المستندات</b><span class="muted small">آخر حركة: <span class="num">{{ s.last_movement || '—' }}</span></span></div>
      <table class="tbl mt" style="font-size:.88rem">
        <tbody>
          <tr v-for="d in s.recent" :key="d.id" class="clickable" @click="store.docViewId = d.id" :class="{ 'is-cancelled': d.status === 'cancelled' }">
            <td class="num">{{ d.doc_date }}</td><td class="num link">{{ d.doc_no }}</td><td>{{ d.type_label }}</td><td class="muted small">{{ d.description }}</td>
          </tr>
        </tbody>
      </table>
      <Empty v-if="!s.recent.length" text="لا توجد حركات على هذا الحساب بعد" icon="layers" />
    </div>
    <div v-if="s.account.notes" class="alert info mt"><Icon name="info"/><div style="white-space:pre-line">{{ s.account.notes }}</div></div>
    <template #foot>
      <button class="btn btn-primary" @click="nav('statement', { account: s.account.id })"><Icon name="file-text"/> كشف الحساب</button>
      <button class="btn" @click="nav('analysis', { account: s.account.id })"><Icon name="chart-column"/> تحليل الحركة</button>
      <button class="btn" @click="print"><Icon name="printer"/> طباعة البيانات</button>
      <button class="btn btn-ghost" v-if="can('accounts.manage')" @click="nav('accounts', { edit: s.account.id })"><Icon name="pencil"/> تعديل</button>
      <button class="btn btn-ghost" v-if="can('opening.manage') && !s.opening" @click="nav('opening', { account: s.account.id })"><Icon name="book-open"/> رصيد افتتاحي</button>
      <button class="btn btn-ghost" v-if="s.opening" @click="store.docViewId = s.opening.id"><Icon name="book-open"/> الرصيد الافتتاحي</button>
    </template>
  </Drawer>`,
};

// ============================================================================
//  تغيير عيار العمل المعتمد
// ============================================================================
export const KaratDialog = {
  name: "KaratDialog",
  setup() {
    const f = reactive({ karat: store.settings.working_karat, reason: "" });
    const busy = ref(false);
    const hist = ref([]);
    onMounted(async () => { try { hist.value = await api.get("/api/settings/karat-history"); } catch { /* */ } });
    async function save() {
      busy.value = true;
      try {
        store.settings = await api.post("/api/settings/karat", { karat: f.karat, reason: f.reason });
        toast("success", "تم تغيير عيار العمل", `العيار المعتمد الآن ${store.settings.working_karat}. المستندات السابقة تحتفظ بعيارها.`);
        store.karatDialog = false;
        dataChanged();
      } catch (e) { toastError(e, "تعذر تغيير العيار"); } finally { busy.value = false; }
    }
    return { store, f, busy, save, hist, fmtDateTime, can };
  },
  template: `<Modal title="عيار العمل المعتمد" @close="store.karatDialog = false">
    <div class="stack">
      <div class="info-strip"><div><div class="k">العيار الحالي</div><div class="v num" style="font-size:1.4rem">{{ store.settings.working_karat }}</div></div>
        <div><div class="k">يُستخدم في</div><div class="v small">الوزن المكافئ للذهب في القبض والصرف والافتتاحي، وأوزان المبيعات</div></div></div>
      <template v-if="can('settings.manage')">
        <div class="field"><label>العيار الجديد</label>
          <div class="seg lg"><button v-for="k in [18,21,22,24]" :key="k" :class="{ on: f.karat === k }" @click="f.karat = k" class="num">{{ k }}</button></div></div>
        <div class="alert warn"><Icon name="triangle-alert"/><div>
          التغيير يسري على العمليات الجديدة فقط. كل مستند مرحّل يحتفظ بعيار العمل الذي رُحّل به ولا يُعاد حسابه.
          إن كانت للعملاء حركات ذهب سابقة فسيظهر رصيدهم «مختلط العيار» مع تفصيل كل عيار، لذا يُنصح بالتغيير عند بدء التشغيل أو بعد تسوية الأرصدة.</div></div>
        <div class="field"><label class="req">سبب التغيير</label><input class="input" v-model="f.reason" placeholder="مثال: اعتماد عيار 21 للمصنع من بداية السنة" /></div>
      </template>
      <div v-else class="alert info"><Icon name="lock"/><div>تغيير عيار العمل يحتاج صلاحية «تغيير عيار العمل والإعدادات العامة».</div></div>
      <div v-if="hist.length"><b class="small">سجل التغييرات</b>
        <table class="tbl" style="font-size:.85rem"><tbody><tr v-for="h in hist" :key="h.id"><td class="num">{{ fmtDateTime(h.changed_at) }}</td>
          <td class="num">{{ h.previous_karat ? h.previous_karat + ' ← ' : '' }}{{ h.karat }}</td><td>{{ h.reason }}</td><td class="muted">{{ h.user_name }}</td></tr></tbody></table></div>
    </div>
    <template #foot v-if="can('settings.manage')">
      <button class="btn btn-primary" @click="save" :disabled="busy || f.karat === store.settings.working_karat || f.reason.trim().length < 3" data-enter-stop>حفظ العيار</button>
      <button class="btn" @click="store.karatDialog = false">إغلاق</button>
    </template>
  </Modal>`,
};

// ============================================================================
//  الإعدادات العامة (نافذة داخل الواجهة الرئيسية — ليست شاشة مستقلة)
// ============================================================================
export const SettingsDialog = {
  name: "SettingsDialog",
  setup() {
    const tabs = computed(() => [
      { id: "general", label: "عام", show: true },
      { id: "users", label: "المستخدمون والصلاحيات", show: can("users.manage") },
      { id: "backup", label: "النسخ الاحتياطي", show: can("system.backup") },
      { id: "integrity", label: "فحص سلامة البيانات", show: can("system.backup") },
      { id: "audit", label: "سجل العمليات", show: can("system.backup") },
      { id: "password", label: "كلمة المرور", show: true },
    ].filter((t) => t.show));
    const tab = ref("general");
    const gen = reactive({ system_name: store.settings.system_name, wage_unit: store.settings.wage_unit, diamond_unit: store.settings.diamond_unit });
    const busy = ref(false);

    async function saveGeneral() {
      busy.value = true;
      try {
        store.settings = await api.post("/api/settings/general", gen);
        document.title = store.settings.system_name;
        toast("success", "تم حفظ الإعدادات");
      } catch (e) { toastError(e); } finally { busy.value = false; }
    }

    // ---- المستخدمون
    const users = ref([]);
    const permLabels = ref({});
    const defaults = ref([]);
    const uf = reactive({ id: null, username: "", full_name: "", password: "", is_admin: false, is_active: true, permissions: [] });
    async function loadUsers() {
      try {
        const r = await api.get("/api/users");
        users.value = r.users; permLabels.value = r.permissions; defaults.value = r.accountant_defaults;
      } catch (e) { toastError(e); }
    }
    function newUser() { Object.assign(uf, { id: null, username: "", full_name: "", password: "", is_admin: false, is_active: true, permissions: [...defaults.value] }); }
    function editUser(u) { Object.assign(uf, { id: u.id, username: u.username, full_name: u.full_name, password: "", is_admin: u.is_admin, is_active: u.is_active, permissions: [...u.permissions] }); }
    async function saveUser() {
      busy.value = true;
      try {
        if (uf.id) await api.put(`/api/users/${uf.id}`, { full_name: uf.full_name, password: uf.password || undefined, is_admin: uf.is_admin, is_active: uf.is_active, permissions: uf.permissions });
        else await api.post("/api/users", { ...uf });
        toast("success", uf.id ? "تم تحديث المستخدم" : "تم إنشاء المستخدم");
        newUser();
        await loadUsers();
      } catch (e) { toastError(e); } finally { busy.value = false; }
    }

    // ---- النسخ الاحتياطي
    const backups = ref({ files: [], directory: "" });
    const restoreFile = ref(null);
    async function loadBackups() { try { backups.value = await api.get("/api/backups"); } catch (e) { toastError(e); } }
    async function download() {
      try {
        const resp = await api.download("/api/backup/download");
        const blob = await resp.blob();
        const name = (resp.headers.get("Content-Disposition") || "").match(/filename="([^"]+)"/);
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = name ? name[1] : "jadeit-backup.db";
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        toast("success", "تم تنزيل النسخة الاحتياطية");
      } catch (e) { toastError(e); }
    }
    async function restore() {
      const file = restoreFile.value && restoreFile.value.files[0];
      if (!file) return toast("warning", "اختر ملف النسخة أولاً");
      if (!confirm("ستُستبدل كل البيانات الحالية بمحتوى النسخة المختارة (مع حفظ نسخة أمان من الوضع الحالي تلقائياً). هل تريد المتابعة؟")) return;
      busy.value = true;
      try {
        const r = await api.upload("/api/backup/restore", file);
        alert("تمت الاستعادة بنجاح. نسخة الأمان: " + (r.safety_backup || "—") + "\nسيُعاد تحميل النظام، سجّل الدخول من جديد.");
        location.reload();
      } catch (e) { toastError(e, "فشلت الاستعادة — لم يتغير شيء"); } finally { busy.value = false; }
    }

    // ---- الفحص والسجل
    const check = ref(null);
    async function runCheck() {
      busy.value = true;
      try { check.value = await api.get("/api/integrity"); } catch (e) { toastError(e); } finally { busy.value = false; }
    }
    const audit = ref({ items: [], page: 1, pages: 1 });
    const auditFilter = reactive({ exclude_login: "1", page: 1 });
    async function loadAudit() { try { audit.value = await api.get("/api/audit", auditFilter); } catch (e) { toastError(e); } }

    // ---- كلمة المرور
    const pw = reactive({ current: "", new: "", confirm: "" });
    async function changePw() {
      if (pw.new !== pw.confirm) return toast("error", "كلمتا المرور غير متطابقتين");
      busy.value = true;
      try { await api.post("/api/me/password", { current: pw.current, new: pw.new }); toast("success", "تم تغيير كلمة المرور"); Object.assign(pw, { current: "", new: "", confirm: "" }); }
      catch (e) { toastError(e); } finally { busy.value = false; }
    }

    watch(tab, (t) => {
      if (t === "users") { loadUsers(); newUser(); }
      if (t === "backup") loadBackups();
      if (t === "audit") loadAudit();
    });
    const openRef = (it) => { if (it.entity === "document" && it.entity_id) store.docViewId = it.entity_id; };
    return { store, tabs, tab, gen, busy, saveGeneral, users, permLabels, uf, newUser, editUser, saveUser, backups, restoreFile, download, restore,
      check, runCheck, audit, auditFilter, loadAudit, pw, changePw, fmtDateTime, openRef, can };
  },
  template: `<Modal title="الإعدادات العامة" size="xwide" @close="store.settingsOpen = false">
    <div class="tabs"><button v-for="t in tabs" :key="t.id" :class="{ on: tab === t.id }" @click="tab = t.id">{{ t.label }}</button></div>

    <div v-if="tab === 'general'" class="stack">
      <div class="grid g3">
        <div class="field"><label>اسم النظام (يظهر في الطباعة)</label><input class="input" v-model="gen.system_name" :readonly="!can('settings.manage')" /></div>
        <div class="field"><label>وحدة الأجور</label><input class="input" v-model="gen.wage_unit" placeholder="مثال: ريال" :readonly="!can('settings.manage')" />
          <span class="hint">تسمية العملة المستخدمة للأجور (منزلتان عشريتان).</span></div>
        <div class="field"><label>وحدة وزن الألماس</label><input class="input" v-model="gen.diamond_unit" :readonly="!can('settings.manage') || store.settings.diamond_unit_locked" />
          <span class="hint" v-if="store.settings.diamond_unit_locked">مقفلة لوجود حركات ألماس مرحّلة.</span><span class="hint" v-else>تُحدد قبل تسجيل أول حركة ألماس.</span></div>
      </div>
      <div class="info-strip"><div><div class="k">عيار العمل المعتمد</div><div class="v num">{{ store.settings.working_karat }}</div></div>
        <div><div class="k">دقة الأوزان</div><div class="v small">ذهب 4 منازل — ألماس 3 منازل — أجور منزلتان — سعر الأجر حتى 3 منازل</div></div>
        <div><button class="btn btn-sm" @click="store.karatDialog = true">إدارة عيار العمل</button></div></div>
      <div v-if="can('settings.manage')"><button class="btn btn-primary" @click="saveGeneral" :disabled="busy" data-enter-stop>حفظ الإعدادات</button></div>
    </div>

    <div v-if="tab === 'users'" class="split" style="grid-template-columns:minmax(0,1fr) 400px">
      <div class="tbl-wrap auto"><table class="tbl"><thead><tr><th>المستخدم</th><th>الاسم</th><th>الدور</th><th>الحالة</th><th></th></tr></thead>
        <tbody><tr v-for="u in users" :key="u.id"><td class="num">{{ u.username }}</td><td>{{ u.full_name }}</td>
          <td><span class="badge" :class="u.is_admin ? 'gold' : 'neutral'">{{ u.is_admin ? 'مدير النظام' : (u.permissions.length + ' صلاحية') }}</span></td>
          <td><span class="badge" :class="u.is_active ? 'posted' : 'warn'">{{ u.is_active ? 'نشط' : 'موقوف' }}</span></td>
          <td><button class="btn btn-sm" @click="editUser(u)"><Icon name="pencil" size="sm"/> تعديل</button></td></tr></tbody></table></div>
      <div class="card"><div class="card-head"><h3>{{ uf.id ? 'تعديل مستخدم' : 'مستخدم جديد' }}</h3><div class="tools"><button v-if="uf.id" class="btn btn-sm btn-ghost" @click="newUser">جديد</button></div></div>
        <div class="card-body stack">
          <div class="field"><label class="req">اسم المستخدم</label><input class="input" v-model="uf.username" :readonly="!!uf.id" autocomplete="off" /></div>
          <div class="field"><label>الاسم الكامل</label><input class="input" v-model="uf.full_name" /></div>
          <div class="field"><label :class="{ req: !uf.id }">{{ uf.id ? 'كلمة مرور جديدة (اختياري)' : 'كلمة المرور' }}</label><input type="password" class="input" v-model="uf.password" autocomplete="new-password" /></div>
          <label class="check"><input type="checkbox" v-model="uf.is_admin"/> مدير النظام (كل الصلاحيات)</label>
          <label class="check"><input type="checkbox" v-model="uf.is_active"/> المستخدم نشط</label>
          <div v-if="!uf.is_admin" class="stack" style="gap:6px"><b class="small">الصلاحيات</b>
            <label v-for="(label, key) in permLabels" :key="key" class="check small"><input type="checkbox" :value="key" v-model="uf.permissions"/> {{ label }}</label></div>
          <button class="btn btn-primary" @click="saveUser" :disabled="busy" data-enter-stop>حفظ المستخدم</button>
        </div></div>
    </div>

    <div v-if="tab === 'backup'" class="stack">
      <div class="alert info"><Icon name="database"/><div>قاعدة البيانات ملف واحد. يأخذ النظام نسخة تلقائية عند كل تشغيل (آخر 30 نسخة) في: <span class="num small">{{ backups.directory }}</span></div></div>
      <div class="row"><button class="btn btn-primary" @click="download"><Icon name="download"/> تنزيل نسخة احتياطية الآن</button></div>
      <div class="card"><div class="card-head"><h3>استعادة من نسخة</h3></div><div class="card-body row">
        <input type="file" ref="restoreFile" accept=".db" class="input" style="max-width:360px;padding-top:6px" />
        <button class="btn btn-danger" @click="restore" :disabled="busy"><Icon name="upload"/> استعادة</button>
        <span class="muted small">يُتحقق من سلامة الملف قبل الاستعادة، وتُحفظ نسخة أمان من الوضع الحالي تلقائياً.</span></div></div>
      <table class="tbl"><thead><tr><th>النسخ التلقائية</th><th>التاريخ</th><th class="num">الحجم</th></tr></thead>
        <tbody><tr v-for="b in backups.files" :key="b.name"><td class="num small">{{ b.name }}</td><td class="num">{{ b.modified }}</td><td class="num">{{ (b.size / 1024).toFixed(0) }} KB</td></tr></tbody></table>
    </div>

    <div v-if="tab === 'integrity'" class="stack">
      <p class="muted" style="margin:0">يعيد الفحص بناء القيود المتوقعة لكل مستند من أسطره ويقارنها بالدفتر، ويتحقق من الأجور والأوزان المكافئة والإلغاءات والمرتجعات وتطابق الأرصدة المحفوظة مع الحركات.</p>
      <div><button class="btn btn-primary" @click="runCheck" :disabled="busy" data-enter-stop><Icon name="shield-check"/> تشغيل الفحص</button></div>
      <div v-if="check" class="alert" :class="check.ok ? 'ok' : 'danger'"><Icon :name="check.ok ? 'circle-check' : 'circle-alert'"/>
        <div><b>{{ check.ok ? 'البيانات سليمة ومتطابقة' : ('تم العثور على ' + check.issue_count + ' اختلاف') }}</b> — فُحص {{ check.documents_checked }} مستند و{{ check.entries_checked }} قيد.
          <ul v-if="!check.ok"><li v-for="(i, k) in check.issues" :key="k"><span class="num">{{ i.ref }}</span>: {{ i.message }}</li></ul></div></div>
    </div>

    <div v-if="tab === 'audit'" class="stack">
      <div class="row"><label class="check"><input type="checkbox" true-value="1" false-value="" v-model="auditFilter.exclude_login" @change="loadAudit"/> إخفاء عمليات الدخول</label></div>
      <div class="tbl-wrap"><table class="tbl" style="font-size:.86rem"><thead><tr><th>الوقت</th><th>المستخدم</th><th>العملية</th><th>المرجع</th><th>السبب</th></tr></thead>
        <tbody><tr v-for="it in audit.items" :key="it.id" :class="{ clickable: it.entity === 'document' }" @click="openRef(it)">
          <td class="num">{{ fmtDateTime(it.at) }}</td><td>{{ it.user || '—' }}</td><td>{{ it.action_label }}</td><td class="num">{{ it.ref }}</td><td>{{ it.reason }}</td></tr></tbody></table></div>
      <div class="row"><button class="btn btn-sm" :disabled="audit.page <= 1" @click="auditFilter.page--; loadAudit()">السابق</button>
        <span class="small">صفحة {{ audit.page }} من {{ audit.pages }}</span>
        <button class="btn btn-sm" :disabled="audit.page >= audit.pages" @click="auditFilter.page++; loadAudit()">التالي</button></div>
    </div>

    <div v-if="tab === 'password'" class="grid g3">
      <div class="field"><label>كلمة المرور الحالية</label><input type="password" class="input" v-model="pw.current" autocomplete="current-password" /></div>
      <div class="field"><label>كلمة المرور الجديدة</label><input type="password" class="input" v-model="pw.new" autocomplete="new-password" /></div>
      <div class="field"><label>تأكيد كلمة المرور</label><input type="password" class="input" v-model="pw.confirm" autocomplete="new-password" /></div>
      <div><button class="btn btn-primary" @click="changePw" :disabled="busy || !pw.new" data-enter-stop>تغيير كلمة المرور</button></div>
    </div>
  </Modal>`,
};

// ============================================================================
//  الدخول والإعداد الأول
// ============================================================================
export const LoginView = {
  name: "LoginView",
  emits: ["done"],
  setup(_, { emit }) {
    const f = reactive({ username: "", password: "", confirm: "", full_name: "", system_name: "جاديت — نظام حسابات العملاء", working_karat: 18, wage_unit: "ريال" });
    const busy = ref(false);
    const error = ref("");
    async function submit() {
      error.value = "";
      if (store.needsSetup && f.password !== f.confirm) { error.value = "كلمتا المرور غير متطابقتين"; return; }
      busy.value = true;
      try {
        const data = store.needsSetup ? await api.post("/api/setup", f) : await api.post("/api/login", { username: f.username, password: f.password });
        applyBoot(data);
        store.needsSetup = false;
        await loadAccounts();
        emit("done");
      } catch (e) { error.value = e.message; } finally { busy.value = false; }
    }
    return { store, f, busy, error, submit };
  },
  template: `<div class="login-wrap"><form class="login-card" @submit.prevent="submit" data-focus-scope>
      <img src="/img/logo.png" class="logo" alt="">
      <h1>{{ store.needsSetup ? 'إعداد النظام لأول مرة' : (store.settings.system_name || 'جاديت') }}</h1>
      <p class="sub">{{ store.needsSetup ? 'أنشئ حساب مدير النظام وحدد عيار العمل المعتمد' : 'سجّل الدخول للمتابعة' }}</p>
      <div class="stack">
        <template v-if="store.needsSetup">
          <div class="field"><label>اسم النظام / المنشأة</label><input class="input" v-model="f.system_name" /></div>
          <div class="field"><label class="req">اسم مدير النظام</label><input class="input" v-model="f.full_name" /></div>
        </template>
        <div class="field"><label class="req">اسم المستخدم</label><input class="input" v-model="f.username" autocomplete="username" autofocus /></div>
        <div class="field"><label class="req">كلمة المرور</label><input type="password" class="input" v-model="f.password" :autocomplete="store.needsSetup ? 'new-password' : 'current-password'" /></div>
        <template v-if="store.needsSetup">
          <div class="field"><label class="req">تأكيد كلمة المرور</label><input type="password" class="input" v-model="f.confirm" autocomplete="new-password" /></div>
          <div class="field"><label class="req">عيار العمل المعتمد</label>
            <div class="seg lg"><button type="button" v-for="k in [18,21,22,24]" :key="k" :class="{ on: f.working_karat === k }" @click="f.working_karat = k" class="num">{{ k }}</button></div>
            <span class="hint">يُحسب على أساسه الوزن المكافئ للذهب، ويمكن تغييره لاحقاً بصلاحية مع حفظ عيار كل عملية سابقة.</span></div>
          <div class="field"><label>وحدة الأجور (العملة)</label><input class="input" v-model="f.wage_unit" /></div>
        </template>
        <div v-if="error" class="alert danger"><Icon name="circle-alert"/><div>{{ error }}</div></div>
        <button class="btn btn-primary btn-lg" type="submit" :disabled="busy" data-enter-stop><span v-if="busy" class="spinner"></span>{{ store.needsSetup ? 'إنشاء وبدء الاستخدام' : 'دخول' }}</button>
      </div>
    </form></div>`,
};

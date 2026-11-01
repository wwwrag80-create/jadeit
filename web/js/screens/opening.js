// الشاشة السابعة: الرصيد الافتتاحي — مستند مستقل (ليس بيعاً ولا قبضاً ولا صرفاً) بأسطر منفصلة لكل نوع.
import { api, postWithRetry } from "../api.js";
import { store, can, toast, toastError, dataChanged, units } from "../store.js";
import { parse, fmt, equivalent, group, KARATS } from "../num.js";
import { today, newToken, parseHashQuery, local, debounce, MATERIAL_LABEL, fmtDateTime } from "../util.js";
import { DocSearch } from "../components/docs.js";
import { PostSummary, LastPosted } from "../components/post.js";
import { openPreview, docSpec } from "../components/print.js";

const { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;
let seq = 0;
const DP = { gold: 4, diamond: 3, wage: 2 };

export const OpeningScreen = {
  name: "OpeningScreen",
  components: { DocSearch, PostSummary, LastPosted },
  setup() {
    const accountId = ref(null);
    const date = ref(today());
    const description = ref("رصيد افتتاحي");
    const notes = ref("");
    const lines = ref([]);
    const token = ref(newToken());
    const nextNo = ref("");
    const existing = ref(null);
    const editDoc = ref(null);
    const preview = ref(null);
    const busy = ref(false);
    const checking = ref(false);
    const lastPosted = ref(null);
    const showSearch = ref(false);
    const recent = ref([]);
    const picker = ref(null);
    const u = computed(units);
    const canManage = computed(() => can("opening.manage") && (!editDoc.value || can("docs.edit")));
    const workingKarat = computed(() => (editDoc.value ? editDoc.value.working_karat : store.settings.working_karat));
    const account = computed(() => store.accounts.find((a) => a.id === accountId.value) || null);

    const newLine = (material = "gold") => ({ key: ++seq, material, direction: "", actual: "", karat: null, description: "", note: "" });
    function addLine(m) { lines.value.push(newLine(m)); nextTick(() => { const el = document.querySelector(`[data-ob-row="${lines.value.length - 1}"]`); el && el.focus(); }); }

    const calc = computed(() => lines.value.map((l) => {
      const r = parse(l.actual, DP[l.material]);
      const out = { err: "", value: 0n, eq: null };
      if (!l.direction) out.err = "حدد الاتجاه (مدين أو دائن)";
      else if (!r.ok) out.err = r.error;
      else if (r.empty || r.value === 0n) out.err = "أدخل الوزن أو المبلغ";
      else if (l.material === "gold" && !l.karat) out.err = "اختر عيار الذهب";
      if (r.ok) out.value = r.value;
      if (r.ok && l.material === "gold" && l.karat) out.eq = equivalent(r.value, l.karat, workingKarat.value);
      else if (r.ok && l.material !== "gold") out.eq = r.value;
      return out;
    }));
    const net = computed(() => {
      const t = { gold: 0n, diamond: 0n, wage: 0n };
      lines.value.forEach((l, i) => { const c = calc.value[i]; if (!c.err && c.eq !== null) t[l.material] += l.direction === "debit" ? c.eq : -c.eq; });
      return Object.fromEntries(Object.entries(t).map(([m, v]) => [m, { value: fmt(v < 0n ? -v : v, DP[m]), dir: v > 0n ? "debit" : v < 0n ? "credit" : "zero" }]));
    });

    async function checkExisting() {
      existing.value = null;
      if (!accountId.value || editDoc.value) return;
      try {
        const s = await api.get(`/api/accounts/${accountId.value}/summary`);
        existing.value = s.opening;
      } catch { /* */ }
    }
    watch(accountId, checkExisting);
    async function refreshNextNo() { try { nextNo.value = (await api.get("/api/documents/next-no", { type: "opening" })).doc_no; } catch { /* */ } }
    async function loadRecent() { try { recent.value = await api.get("/api/documents", { types: "opening", limit: 15 }); } catch { /* */ } }
    watch(() => store.dataVersion, () => { loadRecent(); refreshNextNo(); checkExisting(); });

    function payload() {
      return { doc_type: "opening", account_id: accountId.value, doc_date: date.value, description: description.value, notes: notes.value,
        lines: lines.value.map((l) => ({ material: l.material, direction: l.direction, actual: l.actual, karat: l.material === "gold" ? l.karat : undefined, description: l.description, note: l.note })) };
    }
    async function startPost() {
      if (busy.value || checking.value || !canManage.value) return;
      if (!accountId.value) { toast("error", "اختر الحساب أولاً"); return; }
      if (!lines.value.length) { toast("error", "أضف سطراً واحداً على الأقل"); return; }
      const bad = calc.value.findIndex((c) => c.err);
      if (bad >= 0) { toast("error", `السطر ${bad + 1}: ${calc.value[bad].err}`); return; }
      if (existing.value && !editDoc.value) { toast("error", "يوجد رصيد افتتاحي مرحّل لهذا الحساب", "افتحه وعدّله بدلاً من تسجيل رصيد جديد."); return; }
      checking.value = true;
      try { preview.value = await api.post(editDoc.value ? `/api/documents/${editDoc.value.id}/preview` : "/api/documents/preview", payload()); }
      catch (e) { toastError(e, "لم يتم الترحيل"); } finally { checking.value = false; }
    }
    async function confirmPost(reason) {
      if (busy.value) return;
      busy.value = true;
      try {
        let doc;
        if (editDoc.value) {
          doc = await api.put(`/api/documents/${editDoc.value.id}`, { ...payload(), version: editDoc.value.version, reason });
          toast("success", "تم حفظ تعديل الرصيد الافتتاحي", doc.doc_no);
        } else {
          doc = await postWithRetry("/api/documents", { ...payload(), client_token: token.value });
          if (doc.duplicate_request) toast("info", "الرصيد مُرحّل مسبقاً", doc.doc_no);
          else toast("success", `تم ترحيل الرصيد الافتتاحي ${doc.doc_no}`, doc.account.name);
        }
        lastPosted.value = doc;
        preview.value = null;
        dataChanged();
        reset();
      } catch (e) { preview.value = null; toastError(e, "لم يتم الترحيل"); } finally { busy.value = false; }
    }
    function reset() {
      local.remove("draft:opening");
      editDoc.value = null;
      if (location.hash.includes("edit=")) history.replaceState(null, "", "#/opening");
      accountId.value = null; existing.value = null;
      description.value = "رصيد افتتاحي"; notes.value = ""; lines.value = [];
      token.value = newToken();
      refreshNextNo();
      nextTick(() => picker.value && picker.value.focus());
    }
    async function loadForEdit(id) {
      try {
        const d = await api.get(`/api/documents/${id}`);
        if (d.doc_type !== "opening") return;
        if (d.status !== "posted") { toast("error", "لا يمكن تعديل مستند ملغى"); return; }
        editDoc.value = d;
        accountId.value = d.account.id;
        date.value = d.doc_date; description.value = d.description; notes.value = d.notes;
        lines.value = d.lines.map((l) => ({ key: ++seq, material: l.material, direction: l.direction, actual: l.actual, karat: l.karat, description: l.description, note: l.note }));
      } catch (e) { toastError(e); }
    }
    async function previewLast() { await openPreview(docSpec(await api.get(`/api/documents/${lastPosted.value.id}`))); }

    const saveDraft = debounce(() => {
      if (editDoc.value) return;
      if (!accountId.value && !lines.value.length) { local.remove("draft:opening"); return; }
      local.set("draft:opening", { accountId: accountId.value, date: date.value, description: description.value, notes: notes.value, lines: lines.value, token: token.value });
    }, 400);
    watch([accountId, date, description, notes, lines], saveDraft, { deep: true });

    function onKey(e) {
      if (preview.value || store.docViewId || store.print) return;
      if (e.key === "F9" || ((e.ctrlKey || e.metaKey) && e.key === "Enter")) { e.preventDefault(); startPost(); }
      else if (e.key === "F3") { e.preventDefault(); showSearch.value = true; }
      else if (e.altKey && e.code === "KeyN") { e.preventDefault(); addLine(lines.value.length ? lines.value[lines.value.length - 1].material : "gold"); }
    }
    onMounted(async () => {
      document.addEventListener("keydown", onKey);
      loadRecent();
      const p = parseHashQuery();
      if (p.get("edit")) await loadForEdit(p.get("edit"));
      else {
        const d = local.get("draft:opening");
        if (d && (d.accountId || (d.lines && d.lines.length))) {
          accountId.value = d.accountId; date.value = d.date; description.value = d.description; notes.value = d.notes;
          lines.value = d.lines.map((l) => ({ ...l, key: ++seq })); token.value = d.token;
          toast("info", "استُعيدت مسودة رصيد افتتاحي غير مرحّل");
        } else {
          if (p.get("account")) accountId.value = Number(p.get("account"));
          lines.value = [newLine("gold")];
        }
        refreshNextNo();
      }
    });
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey));

    return { store, accountId, account, date, description, notes, lines, nextNo, existing, editDoc, preview, busy, checking, lastPosted, showSearch, recent,
      picker, u, canManage, workingKarat, calc, net, addLine, startPost, confirmPost, reset, previewLast, fmt, g: group, KARATS, MATERIAL_LABEL, DP, fmtDateTime };
  },
  template: `<div>
    <div class="page-head">
      <div><h1>الرصيد الافتتاحي</h1><p>إدخال أرصدة بداية التشغيل للحسابات. لكل نوع (ذهب / ألماس / أجور) سطر مستقل واتجاه مستقل — مدين أو دائن — ولا يُفترض اتجاه تلقائي.</p></div>
      <div class="actions"><button class="btn" @click="showSearch = true"><Icon name="search"/> بحث <span class="kbd" style="color:var(--text-3)">F3</span></button></div>
    </div>
    <LastPosted :doc="lastPosted" @preview="previewLast" @dismiss="lastPosted = null" />
    <div v-if="!canManage" class="alert info mb"><Icon name="lock"/><div>إدخال الأرصدة الافتتاحية يحتاج صلاحية «إدخال وتعديل الأرصدة الافتتاحية».</div></div>
    <div v-if="editDoc" class="alert warn mb"><Icon name="pencil"/><div style="flex:1"><b>تعديل معتمد</b> للرصيد الافتتاحي <b class="num">{{ editDoc.doc_no }}</b> — يُطلب سبب التعديل ويُحفظ الأصل في السجل.</div><button class="btn btn-sm" @click="reset">إلغاء التعديل</button></div>
    <div v-if="existing && !editDoc" class="alert warn mb"><Icon name="triangle-alert"/><div style="flex:1">لهذا الحساب رصيد افتتاحي مرحّل برقم <b class="num">{{ existing.doc_no }}</b> بتاريخ <span class="num">{{ existing.doc_date }}</span>. لا يُسجل الرصيد الافتتاحي مرتين؛ يمكن تعديله تعديلاً معتمداً.</div>
      <button class="btn btn-sm" @click="store.docViewId = existing.id">عرض / تعديل</button></div>

    <div class="card">
      <div class="card-body" data-focus-scope>
        <div class="grid g6">
          <div class="field span2"><label class="req">اسم الحساب</label><AccountPicker ref="picker" v-model="accountId" :disabled="!!editDoc" autofocus /></div>
          <div class="field"><label>رقم الحساب</label><div class="readout num">{{ account ? account.account_no : '—' }}</div></div>
          <div class="field"><label class="req">تاريخ الرصيد الافتتاحي</label><input type="date" class="input" v-model="date" /></div>
          <div class="field"><label>رقم المستند</label><div class="readout num">{{ editDoc ? editDoc.doc_no : nextNo }}</div></div>
          <div class="field"><label>عيار العمل المعتمد</label><div class="readout num" style="color:var(--gold)">{{ workingKarat }}</div></div>
          <div class="field span3"><label>البيان</label><input class="input" v-model="description" maxlength="300" /></div>
          <div class="field span3"><label>ملاحظات</label><input class="input" v-model="notes" maxlength="1000" /></div>
        </div>
      </div>
      <div class="card-head" style="border-top:1px solid var(--border)"><h3>أسطر الرصيد الافتتاحي</h3>
        <div class="tools"><span class="muted small"><span class="kbd" style="color:var(--text)">Alt+N</span> سطر جديد</span>
          <button class="btn btn-sm" @click="addLine('gold')"><Icon name="plus" size="sm"/> ذهب</button>
          <button class="btn btn-sm" @click="addLine('diamond')"><Icon name="plus" size="sm"/> ألماس</button>
          <button class="btn btn-sm" @click="addLine('wage')"><Icon name="plus" size="sm"/> أجور</button></div></div>
      <div class="tbl-wrap auto">
        <table class="tbl entry-tbl" data-nav-grid>
          <thead><tr><th class="c">#</th><th>نوع الرصيد</th><th>اتجاه الرصيد</th><th class="num">الوزن / المبلغ</th><th>عيار الذهب</th><th class="num">الوزن المكافئ / المعتمد</th><th>البيان</th><th>ملاحظات</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(l, i) in lines" :key="l.key" :class="{ 'row-error': calc[i].err && (l.actual || l.direction) }">
              <td class="rownum">{{ i + 1 }}</td>
              <td><select class="select" v-model="l.material" :data-ob-row="i" style="min-width:110px" @change="l.karat = null"><option value="gold">الذهب</option><option value="diamond">الألماس</option><option value="wage">الأجور</option></select></td>
              <td><select class="select" v-model="l.direction" :class="{ 'is-invalid': !l.direction && l.actual }" style="min-width:140px">
                <option value="" disabled>اختر…</option><option value="debit">مدين (على العميل)</option><option value="credit">دائن (للعميل)</option></select></td>
              <td><NumInput v-model="l.actual" :dp="DP[l.material]" :label="l.material === 'wage' ? 'المبلغ' : 'الوزن'" /><div class="muted small">{{ u[l.material] }}{{ l.material === 'gold' ? ' (وزن فعلي)' : '' }}</div></td>
              <td><select v-if="l.material === 'gold'" class="select" v-model.number="l.karat" style="min-width:90px"><option :value="null" disabled>العيار</option><option v-for="k in KARATS" :key="k" :value="k">{{ k }}</option></select><span v-else class="muted">—</span></td>
              <td class="calc">{{ calc[i].eq !== null ? fmt(calc[i].eq, DP[l.material]) : '—' }}<div class="muted small" v-if="l.material === 'gold' && l.karat" style="font-weight:400">{{ l.karat }} ← {{ workingKarat }}</div></td>
              <td><input class="input" v-model="l.description" maxlength="300" /></td>
              <td><input class="input" v-model="l.note" maxlength="300" /></td>
              <td><button class="btn btn-sm btn-ghost" @click="lines.splice(i, 1)" title="حذف السطر"><Icon name="trash-2" size="sm"/></button></td>
            </tr>
          </tbody>
        </table>
        <Empty v-if="!lines.length" text="أضف سطر ذهب أو ألماس أو أجور" icon="book-open" />
      </div>
      <div class="totals-bar" style="grid-template-columns:repeat(3,1fr)">
        <div v-for="m in ['gold','diamond','wage']" :key="m"><div class="t-label">صافي {{ MATERIAL_LABEL[m] }} الافتتاحي</div>
          <div class="t-value num">{{ net[m].value }}<span class="t-unit">{{ u[m] }}</span> <DirBadge :dir="net[m].dir" /></div></div>
      </div>
    </div>
    <div class="row mt">
      <button class="btn btn-primary btn-lg" @click="startPost" :disabled="busy || checking || !canManage" data-enter-stop><span v-if="checking" class="spinner"></span><Icon v-else name="check"/> {{ editDoc ? 'حفظ التعديل' : 'ترحيل الرصيد الافتتاحي' }} <span class="kbd">F9</span></button>
      <button class="btn btn-lg" @click="reset"><Icon name="eraser"/> مسح</button>
    </div>

    <div class="card mt">
      <div class="card-head"><Icon name="history"/><h3>آخر الأرصدة الافتتاحية</h3></div>
      <div class="tbl-wrap" style="max-height:320px">
        <table class="tbl"><thead><tr><th>التاريخ</th><th>رقم المستند</th><th>الحساب</th><th class="num">ذهب</th><th class="num">ألماس</th><th class="num">أجور</th><th>الحالة</th></tr></thead>
          <tbody><tr v-for="r in recent" :key="r.id" class="clickable" @click="store.docViewId = r.id">
            <td class="num">{{ r.doc_date }}</td><td class="num link">{{ r.doc_no }}</td><td>{{ r.account.name }}</td><td class="num">{{ g(r.gold) }}</td><td class="num">{{ g(r.diamond) }}</td><td class="num">{{ g(r.wage) }}</td><td><StatusBadge :status="r.status"/></td></tr></tbody></table>
        <Empty v-if="!recent.length" text="لا توجد أرصدة افتتاحية بعد" icon="book-open" />
      </div>
    </div>
    <PostSummary v-if="preview" :preview="preview" :editing="!!editDoc" :busy="busy" :doc-no="editDoc ? editDoc.doc_no : nextNo" @confirm="confirmPost" @cancel="preview = null" />
    <DocSearch v-if="showSearch" :types="['opening']" title="البحث في الأرصدة الافتتاحية" @close="showSearch = false" />
  </div>`,
};

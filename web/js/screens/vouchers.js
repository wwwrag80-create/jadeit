// الشاشة الثالثة: القبض والصرف (ذهب / ألماس) + سداد الأجور كحركة أجور صريحة ومستقلة.
import { api, postWithRetry } from "../api.js";
import { store, can, toast, toastError, dataChanged, units } from "../store.js";
import { parse, fmt, equivalent, group, KARATS } from "../num.js";
import { today, newToken, parseHashQuery, go, local, debounce, MATERIAL_LABEL } from "../util.js";
import { DocSearch } from "../components/docs.js";
import { PostSummary, LastPosted } from "../components/post.js";
import { openPreview, docSpec } from "../components/print.js";

const { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } = Vue;

export const VouchersScreen = {
  name: "VouchersScreen",
  components: { DocSearch, PostSummary, LastPosted },
  setup() {
    const kind = ref("receipt");
    const material = ref("gold");
    const accountId = ref(null);
    const date = ref(today());
    const actual = ref("");
    const karat = ref(null);
    const description = ref("");
    const notes = ref("");
    const token = ref(newToken());
    const nextNo = ref("");
    const summary = ref(null);
    const editDoc = ref(null);
    const preview = ref(null);
    const busy = ref(false);
    const checking = ref(false);
    const lastPosted = ref(null);
    const showSearch = ref(false);
    const recent = ref([]);
    const picker = ref(null);
    const amountInput = ref(null);
    const u = computed(units);

    const workingKarat = computed(() => (editDoc.value && editDoc.value.voucher.working_karat) || (editDoc.value ? editDoc.value.working_karat : store.settings.working_karat));
    const dp = computed(() => ({ gold: 4, diamond: 3, wage: 2 }[material.value]));
    const parsed = computed(() => parse(actual.value, dp.value));
    const eq = computed(() => {
      if (material.value !== "gold" || !parsed.value.ok || parsed.value.empty || !karat.value) return null;
      return equivalent(parsed.value.value, karat.value, workingKarat.value);
    });
    const canPost = computed(() => (editDoc.value ? can("docs.edit") : can("docs.post")));
    const account = computed(() => store.accounts.find((a) => a.id === accountId.value) || null);
    const effectText = computed(() => {
      const m = MATERIAL_LABEL[material.value];
      if (material.value === "wage") {
        return kind.value === "receipt" ? "سداد أجور: يُسجَّل دائناً في حساب الأجور ويخفض الأجور المستحقة على العميل. لا يمس رصيد الذهب أو الألماس."
          : "صرف أجور (رد مبلغ للعميل): يُسجَّل مديناً في حساب الأجور ويزيد المستحق على العميل.";
      }
      return kind.value === "receipt" ? `قبض ${m.replace("ال", "")}: يُسجَّل دائناً ويخفض ${m} المستحق على العميل. لا تُنشأ أي حركة أجور تلقائياً.`
        : `صرف ${m.replace("ال", "")}: يُسجَّل مديناً ويزيد ${m} المستحق على العميل.`;
    });

    async function loadSummary() {
      if (!accountId.value) { summary.value = null; return; }
      try { summary.value = await api.get(`/api/accounts/${accountId.value}/summary`); } catch { summary.value = null; }
    }
    watch(accountId, loadSummary);
    watch(() => store.dataVersion, () => { loadSummary(); loadRecent(); refreshNextNo(); });
    watch(kind, () => { if (!editDoc.value) refreshNextNo(); });
    watch(material, () => { if (!editDoc.value) { actual.value = ""; karat.value = null; } });

    async function refreshNextNo() {
      try { nextNo.value = (await api.get("/api/documents/next-no", { type: kind.value })).doc_no; } catch { /* */ }
    }
    async function loadRecent() {
      try { recent.value = await api.get("/api/documents", { types: "receipt,payment", limit: 12 }); } catch { /* */ }
    }

    function payload() {
      const p = { doc_type: kind.value, account_id: accountId.value, doc_date: date.value, material: material.value, actual: actual.value,
        description: description.value, notes: notes.value };
      if (material.value === "gold") p.karat = karat.value;
      return p;
    }
    function validate() {
      if (!accountId.value) { toast("error", "اختر العميل أولاً"); picker.value && picker.value.focus(); return false; }
      if (!parsed.value.ok) { toast("error", parsed.value.error); return false; }
      if (parsed.value.empty || parsed.value.value === 0n) { toast("error", material.value === "wage" ? "أدخل مبلغ الأجور" : "أدخل الوزن"); amountInput.value && amountInput.value.$el && amountInput.value.$el.focus(); return false; }
      if (material.value === "gold" && !karat.value) { toast("error", "اختر عيار الذهب"); return false; }
      return true;
    }
    async function startPost() {
      if (busy.value || checking.value || !canPost.value || !validate()) return;
      checking.value = true;
      try {
        preview.value = await api.post(editDoc.value ? `/api/documents/${editDoc.value.id}/preview` : "/api/documents/preview", payload());
      } catch (e) { toastError(e, "لم يتم الترحيل"); } finally { checking.value = false; }
    }
    async function confirmPost(reason) {
      if (busy.value) return;
      busy.value = true;
      try {
        let doc;
        if (editDoc.value) {
          doc = await api.put(`/api/documents/${editDoc.value.id}`, { ...payload(), version: editDoc.value.version, reason });
          toast("success", "تم حفظ التعديل", `${doc.doc_no} — حُدّثت الأرصدة وكشف الحساب.`);
        } else {
          doc = await postWithRetry("/api/documents", { ...payload(), client_token: token.value });
          if (doc.duplicate_request) toast("info", "السند مُرحّل مسبقاً", `رُحّل سابقاً برقم ${doc.doc_no} ولم يُكرَّر.`);
          else toast("success", `تم ترحيل ${doc.type_label}: ${doc.doc_no}`, `${doc.account.name} — ${doc.description}`);
        }
        lastPosted.value = doc;
        preview.value = null;
        dataChanged();
        reset(true);
      } catch (e) { preview.value = null; toastError(e, "لم يتم الترحيل"); } finally { busy.value = false; }
    }
    function reset(keepKind = true) {
      local.remove("draft:vouchers");
      editDoc.value = null;
      if (location.hash.includes("edit=")) history.replaceState(null, "", "#/vouchers");
      accountId.value = null;
      actual.value = ""; karat.value = null; description.value = ""; notes.value = "";
      if (!keepKind) { kind.value = "receipt"; material.value = "gold"; }
      token.value = newToken();
      refreshNextNo();
      nextTick(() => picker.value && picker.value.focus());
    }
    async function loadForEdit(id) {
      try {
        const d = await api.get(`/api/documents/${id}`);
        if (!d.voucher) return go(d.doc_type === "opening" ? "opening" : "sales", { edit: id });
        if (d.status !== "posted") { toast("error", "لا يمكن تعديل مستند ملغى"); return; }
        editDoc.value = d;
        kind.value = d.doc_type;
        material.value = d.voucher.material;
        await nextTick();
        accountId.value = d.account.id;
        date.value = d.doc_date;
        actual.value = d.voucher.actual;
        karat.value = d.voucher.karat;
        description.value = d.description;
        notes.value = d.notes;
      } catch (e) { toastError(e); }
    }
    async function previewLast() { await openPreview(docSpec(await api.get(`/api/documents/${lastPosted.value.id}`))); }

    const saveDraft = debounce(() => {
      if (editDoc.value) return;
      if (!accountId.value && !actual.value) { local.remove("draft:vouchers"); return; }
      local.set("draft:vouchers", { kind: kind.value, material: material.value, accountId: accountId.value, date: date.value, actual: actual.value,
        karat: karat.value, description: description.value, notes: notes.value, token: token.value });
    }, 400);
    watch([kind, material, accountId, date, actual, karat, description, notes], saveDraft);

    function onKey(e) {
      if (preview.value || store.docViewId || store.print) return;
      if (e.key === "F9" || ((e.ctrlKey || e.metaKey) && e.key === "Enter")) { e.preventDefault(); startPost(); }
      else if (e.key === "F3") { e.preventDefault(); showSearch.value = true; }
    }
    onMounted(async () => {
      document.addEventListener("keydown", onKey);
      loadRecent();
      const p = parseHashQuery();
      if (p.get("edit")) await loadForEdit(p.get("edit"));
      else {
        const d = local.get("draft:vouchers");
        if (d && (d.accountId || d.actual)) {
          kind.value = d.kind; material.value = d.material; await nextTick();
          accountId.value = d.accountId; date.value = d.date; actual.value = d.actual; karat.value = d.karat;
          description.value = d.description; notes.value = d.notes; token.value = d.token;
          toast("info", "استُعيدت مسودة سند غير مرحّل");
        } else if (p.get("account")) accountId.value = Number(p.get("account"));
        refreshNextNo();
        nextTick(() => picker.value && picker.value.focus());
      }
    });
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey));

    return { store, kind, material, accountId, account, date, actual, karat, description, notes, nextNo, summary, editDoc, preview, busy, checking,
      lastPosted, showSearch, recent, picker, amountInput, u, workingKarat, dp, parsed, eq, canPost, effectText, KARATS, fmt, g: group,
      startPost, confirmPost, reset, previewLast, MATERIAL_LABEL };
  },
  template: `<div>
    <div class="page-head">
      <div><h1>القبض والصرف</h1><p>سندات استلام وتسليم الذهب والألماس، مع حفظ الوزن الفعلي والعيار والوزن المكافئ. تسوية الأجور تتم بسند أجور صريح ومستقل.</p></div>
      <div class="actions"><button class="btn" @click="showSearch = true"><Icon name="search"/> بحث عن سند <span class="kbd" style="color:var(--text-3)">F3</span></button></div>
    </div>
    <LastPosted :doc="lastPosted" @preview="previewLast" @dismiss="lastPosted = null" />
    <div v-if="editDoc" class="alert warn mb"><Icon name="pencil"/><div style="flex:1"><b>وضع التعديل:</b> {{ editDoc.type_label }} <b class="num">{{ editDoc.doc_no }}</b> —
      القيمة قبل التعديل: <b class="num">{{ g(editDoc.voucher.actual) }}</b><span v-if="editDoc.voucher.karat"> عيار {{ editDoc.voucher.karat }} = مكافئ <b class="num">{{ g(editDoc.voucher.equivalent) }}</b></span>.
      يحتفظ السند بعيار العمل الذي رُحّل به ({{ workingKarat }}).</div><button class="btn btn-sm" @click="reset()">إلغاء التعديل</button></div>

    <div class="split">
      <div class="card">
        <div class="card-body" data-focus-scope>
          <div class="row mb" style="gap:16px">
            <div class="seg lg" aria-label="نوع الحركة">
              <button class="t-sale" :class="{ on: kind === 'receipt' }" @click="!editDoc && (kind = 'receipt')" :disabled="!!editDoc"><Icon name="arrow-down-left"/> قبض</button>
              <button class="t-return" :class="{ on: kind === 'payment' }" @click="!editDoc && (kind = 'payment')" :disabled="!!editDoc"><Icon name="arrow-up-right"/> صرف</button>
            </div>
            <div class="seg lg" aria-label="نوع المادة">
              <button class="m-gold" :class="{ on: material === 'gold' }" @click="material = 'gold'"><Icon name="coins"/> ذهب</button>
              <button class="m-diamond" :class="{ on: material === 'diamond' }" @click="material = 'diamond'"><Icon name="gem"/> ألماس</button>
              <button class="m-wage" :class="{ on: material === 'wage' }" @click="material = 'wage'"><Icon name="wallet"/> أجور</button>
            </div>
          </div>
          <div class="grid g4">
            <div class="field span2"><label class="req">اسم العميل</label><AccountPicker ref="picker" v-model="accountId" :disabled="!!editDoc" /></div>
            <div class="field"><label>رقم الحساب</label><div class="readout num">{{ account ? account.account_no : '—' }}</div></div>
            <div class="field"><label>رقم السند</label><div class="readout num">{{ editDoc ? editDoc.doc_no : nextNo }}</div></div>
            <div class="field"><label class="req">التاريخ</label><input type="date" class="input" v-model="date" /></div>

            <template v-if="material === 'gold'">
              <div class="field"><label class="req">الوزن الفعلي (جم)</label><NumInput ref="amountInput" v-model="actual" :dp="4" placeholder="0.0000" label="الوزن الفعلي" /></div>
              <div class="field span2"><label class="req">عيار الذهب {{ kind === 'receipt' ? 'المستلم' : 'المصروف' }}</label>
                <div class="seg"><button v-for="k in KARATS" :key="k" class="num" :class="{ on: karat === k }" @click="karat = k" style="min-width:58px">{{ k }}</button></div></div>
              <div class="field"><label>عيار العمل المعتمد</label><div class="readout num" style="color:var(--gold)">{{ workingKarat }}</div></div>
              <div class="field span3"><label>الوزن المكافئ (يُعتمد في رصيد الذهب)</label>
                <div class="readout big" style="justify-content:space-between;background:var(--gold-bg);border-color:var(--gold-border)">
                  <span class="num" style="font-size:1.35rem">{{ eq !== null ? fmt(eq, 4) : '—' }} <span class="muted small">جم</span></span>
                  <span class="num muted small" v-if="eq !== null">{{ actual }} × {{ karat }} ÷ {{ workingKarat }}</span>
                  <span class="muted small" v-else>الوزن الفعلي × العيار الفعلي ÷ عيار العمل</span>
                </div></div>
            </template>
            <div class="field" v-if="material === 'diamond'"><label class="req">وزن الألماس ({{ u.diamond }})</label><NumInput ref="amountInput" v-model="actual" :dp="3" placeholder="0.000" label="وزن الألماس" /></div>
            <div class="field" v-if="material === 'wage'"><label class="req">مبلغ الأجور ({{ u.wage }})</label><NumInput ref="amountInput" v-model="actual" :dp="2" placeholder="0.00" label="مبلغ الأجور" /></div>
            <div class="field" :class="material === 'gold' ? 'span2' : 'span2'"><label>البيان <span class="muted">(اختياري — يُولَّد تلقائياً)</span></label><input class="input" v-model="description" maxlength="300" /></div>
            <div class="field span2"><label>ملاحظات <span class="muted">(اختياري)</span></label><input class="input" v-model="notes" maxlength="1000" /></div>
          </div>
          <div class="alert info mt"><Icon name="info"/><div>{{ effectText }}</div></div>
          <div v-if="parsed.error" class="field-error mt">{{ parsed.error }}</div>
        </div>
        <div class="card-foot row">
          <button class="btn btn-primary btn-lg" @click="startPost" :disabled="busy || checking || !canPost"><span v-if="checking" class="spinner"></span><Icon v-else name="check"/> {{ editDoc ? 'حفظ التعديل' : 'ترحيل' }} <span class="kbd">F9</span></button>
          <button class="btn btn-lg" @click="reset()"><Icon name="eraser"/> مسح</button>
          <span v-if="!canPost" class="badge warn">لا تملك صلاحية الترحيل</span>
        </div>
      </div>

      <div class="stack">
        <div class="card" v-if="summary">
          <div class="card-head"><Icon name="scale"/><h3>أرصدة العميل الحالية</h3><div class="tools"><button class="btn btn-sm btn-ghost" @click="store.accountPanelId = summary.account.id">فتح الحساب</button></div></div>
          <div class="card-body stack" style="gap:8px">
            <div v-for="m in ['gold','diamond','wage']" :key="m" class="row" style="justify-content:space-between" :style="m === material ? 'font-weight:700' : 'opacity:.75'">
              <MaterialBadge :m="m"/><Bal :b="summary.sections[m].balance" :unit="u[m]" /></div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><Icon name="history"/><h3>آخر السندات</h3></div>
          <div class="tbl-wrap" style="max-height:420px">
            <table class="tbl" style="font-size:.86rem"><tbody>
              <tr v-for="r in recent" :key="r.id" class="clickable" @click="store.docViewId = r.id" :class="{ 'is-cancelled': r.status === 'cancelled' }">
                <td class="num">{{ r.doc_date }}</td><td class="num link">{{ r.doc_no }}</td><td>{{ r.account.name }}</td>
                <td class="num">{{ r.gold !== '0.0000' ? g(r.gold) + ' جم' : r.diamond !== '0.000' ? g(r.diamond) + ' ' + u.diamond : g(r.wage) + ' ' + u.wage }}</td></tr>
            </tbody></table>
            <Empty v-if="!recent.length" text="لا سندات بعد" icon="arrow-left-right"/>
          </div>
        </div>
      </div>
    </div>
    <PostSummary v-if="preview" :preview="preview" :editing="!!editDoc" :busy="busy" :doc-no="editDoc ? editDoc.doc_no : nextNo" @confirm="confirmPost" @cancel="preview = null" />
    <DocSearch v-if="showSearch" :types="['receipt','payment']" title="البحث في سندات القبض والصرف" @close="showSearch = false" />
  </div>`,
};

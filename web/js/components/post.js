// ملخص ما قبل الترحيل/التعديل: يعرض النتيجة المحسوبة من الخادم وأثرها على أرصدة العميل قبل وبعد.
import { store, units } from "../store.js";
import { group } from "../num.js";
import { DOC_LABEL, MATERIAL_LABEL } from "../util.js";

const { ref, computed } = Vue;

const DIR = { debit: "مدين", credit: "دائن", zero: "صفر" };
function dirOf(e4) { return e4 > 0 ? "debit" : e4 < 0 ? "credit" : "zero"; }
function absStr(s) { return String(s).startsWith("-") ? String(s).slice(1) : String(s); }

export const PostSummary = {
  name: "PostSummary",
  props: { preview: Object, editing: Boolean, busy: Boolean, docNo: String },
  emits: ["confirm", "cancel"],
  setup(props, { emit }) {
    const reason = ref("");
    const u = computed(units);
    const p = computed(() => props.preview);
    const rows = computed(() => ["gold", "diamond", "wage"].map((m) => {
      const b = p.value.balances[m];
      return { m, before: absStr(b.before), beforeDir: dirOf(b.before_e4), change: b.change, after: absStr(b.after), afterDir: dirOf(b.after_e4),
        changed: b.change.replace(/[0.\-]/g, "") !== "" };
    }));
    function confirm() {
      if (props.busy) return;
      if (props.editing && reason.value.trim().length < 3) return;
      emit("confirm", reason.value.trim());
    }
    return { reason, u, p, rows, confirm, g: group, DOC_LABEL, MATERIAL_LABEL, DIR, store };
  },
  template: `<Modal :title="(editing ? 'مراجعة التعديل: ' : 'مراجعة قبل الترحيل: ') + DOC_LABEL[p.doc_type] + (docNo ? ' ' + docNo : '')" size="wide" @close="$emit('cancel')" :closable="!busy">
    <div class="stack">
      <div class="info-strip">
        <div><div class="k">العميل</div><div class="v">{{ p.account.name }} <span class="muted num">({{ p.account.account_no }})</span></div></div>
        <div><div class="k">التاريخ</div><div class="v num">{{ p.doc_date }}</div></div>
        <div><div class="k">عيار العمل</div><div class="v num">{{ p.working_karat }}</div></div>
        <div v-if="p.totals.gold !== undefined"><div class="k">عدد الأسطر</div><div class="v num">{{ p.totals.lines }}</div></div>
        <div v-if="p.totals.gold !== undefined"><div class="k">إجمالي الذهب</div><div class="v num">{{ g(p.totals.gold) }} <span class="muted small">{{ u.gold }}</span></div></div>
        <div v-if="p.totals.diamond !== undefined"><div class="k">إجمالي الألماس</div><div class="v num">{{ g(p.totals.diamond) }} <span class="muted small">{{ u.diamond }}</span></div></div>
        <div v-if="p.totals.wage !== undefined"><div class="k">إجمالي الأجور</div><div class="v num">{{ g(p.totals.wage) }} <span class="muted small">{{ u.wage }}</span></div></div>
        <div v-if="p.voucher"><div class="k">{{ p.voucher.material === 'gold' ? 'الوزن المكافئ' : 'القيمة' }}</div><div class="v num">{{ g(p.voucher.equivalent) }}</div></div>
      </div>
      <div v-if="p.warnings.length" class="alert warn"><Icon name="triangle-alert"/><div><b>تنبيهات (لا تمنع الترحيل):</b><ul><li v-for="w in p.warnings" :key="w">{{ w }}</li></ul></div></div>
      <div>
        <b>الأثر على أرصدة العميل</b>
        <table class="tbl mt">
          <thead><tr><th>الرصيد</th><th class="num">قبل</th><th class="num">التغيير</th><th class="num">بعد</th></tr></thead>
          <tbody>
            <tr v-for="r in rows" :key="r.m" :style="r.changed ? '' : 'opacity:.6'">
              <td><MaterialBadge :m="r.m"/> <span class="muted small">{{ u[r.m] }}</span></td>
              <td class="num">{{ g(r.before) }} <span class="badge" :class="r.beforeDir">{{ DIR[r.beforeDir] }}</span></td>
              <td class="num" :style="{ color: r.changed ? (r.change.startsWith('-') ? 'var(--credit)' : 'var(--debit)') : '' }">{{ r.changed ? (r.change.startsWith('-') ? '' : '+') + g(r.change) : '—' }}</td>
              <td class="num strong">{{ g(r.after) }} <span class="badge" :class="r.afterDir">{{ DIR[r.afterDir] }}</span></td>
            </tr>
          </tbody>
        </table>
        <div class="muted small mt">الأرصدة منفصلة: لا مقاصة بين الذهب والألماس والأجور. (+) يزيد المستحق على العميل، (−) يخفضه.</div>
      </div>
      <div class="field" v-if="editing"><label class="req">سبب التعديل</label>
        <input class="input" v-model="reason" autofocus placeholder="مثال: تصحيح وزن السطر 3" @keydown.enter.prevent="confirm" />
        <span class="hint">يُحفظ مع القيم قبل التعديل وبعده واسمك والتاريخ في سجل المستند.</span></div>
    </div>
    <template #foot>
      <button class="btn btn-primary btn-lg" @click="confirm" :disabled="busy || (editing && reason.trim().length < 3)" :autofocus="!editing">
        <span v-if="busy" class="spinner"></span><Icon v-else name="check"/> {{ editing ? 'تأكيد حفظ التعديل' : 'تأكيد الترحيل' }} <span class="kbd">Enter</span></button>
      <button class="btn btn-lg" @click="$emit('cancel')" :disabled="busy">رجوع للتعديل</button>
    </template>
  </Modal>`,
};

/** شريط «آخر مستند مُرحّل» مع أزرار المعاينة والعرض. */
export const LastPosted = {
  name: "LastPosted",
  props: { doc: Object },
  emits: ["preview", "dismiss"],
  setup() { return { store, g: group }; },
  template: `<div v-if="doc" class="alert ok mb"><Icon name="circle-check"/>
      <div style="flex:1">تم ترحيل <b>{{ doc.type_label }}</b> رقم <b class="num">{{ doc.doc_no }}</b> للعميل <b>{{ doc.account.name }}</b> وتحديث الأرصدة وكشف الحساب.
        <div class="row" style="margin-top:6px">
          <button class="btn btn-sm btn-primary" @click="$emit('preview')"><Icon name="printer" size="sm"/> معاينة وطباعة</button>
          <button class="btn btn-sm" @click="store.docViewId = doc.id"><Icon name="eye" size="sm"/> عرض المستند</button>
          <button class="btn btn-sm" @click="store.accountPanelId = doc.account.id"><Icon name="external-link" size="sm"/> حساب العميل</button>
        </div></div>
      <button class="btn btn-ghost btn-icon" @click="$emit('dismiss')"><Icon name="x"/></button></div>`,
};

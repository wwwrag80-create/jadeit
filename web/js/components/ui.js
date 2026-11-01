// مكوّنات واجهة مشتركة: الأيقونات، النوافذ، الأرصدة، حقول الأرقام، منتقي العميل، الإشعارات.
import { ICONS } from "../icons.js";
import { sanitizeTyping, parse, group } from "../num.js";
import { store, dismissToast } from "../store.js";
import { DIR_LABEL, focusNext } from "../util.js";

const { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, reactive } = Vue;

// توحيد النص العربي للبحث (نفس قواعد الخادم)
export function normalizeAr(text) {
  return String(text || "")
    .normalize("NFKC")
    .replace(/[ؐ-ًؚ-ٰٟۖ-ۭـ]/g, "")
    .replace(/[أإآٱ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي").replace(/ؤ/g, "و").replace(/ئ/g, "ي")
    .replace(/\s+/g, " ").trim().toLowerCase();
}

export const Icon = {
  name: "Icon",
  props: { name: String, size: { type: String, default: "" } },
  computed: { paths() { return ICONS[this.name] || ""; } },
  template: `<svg class="icon" :class="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="paths"></svg>`,
};

export const DirBadge = {
  name: "DirBadge",
  props: { dir: String },
  computed: {
    label() { return DIR_LABEL[this.dir] || ""; },
    sym() { return this.dir === "debit" ? "▲" : this.dir === "credit" ? "▼" : "●"; },
    title() {
      return this.dir === "debit" ? "مدين: مستحق على العميل" : this.dir === "credit" ? "دائن: مستحق للعميل" : "الرصيد صفر";
    },
  },
  template: `<span class="badge" :class="dir" :title="title"><span aria-hidden="true">{{ sym }}</span>{{ label }}</span>`,
};

/** عرض رصيد: القيمة المطلقة + كلمة مدين/دائن/صفر (لا اعتماد على اللون وحده). */
export const Bal = {
  name: "Bal",
  components: { DirBadge },
  props: { b: Object, unit: String, plain: Boolean },
  template: `<span class="bal" :class="b && b.direction">
      <span class="num">{{ b ? g(b.value) : "—" }}</span><span v-if="unit" class="muted small">{{ unit }}</span>
      <DirBadge v-if="b && !plain" :dir="b.direction" />
    </span>`,
  methods: { g: group },
};

export const Modal = {
  name: "Modal",
  components: { Icon },
  props: { title: String, size: { type: String, default: "" }, closable: { type: Boolean, default: true } },
  emits: ["close"],
  setup(props, { emit }) {
    const root = ref(null);
    const onKey = (e) => {
      if (e.key === "Escape" && props.closable) {
        e.stopPropagation();
        emit("close");
      }
    };
    onMounted(() => {
      document.addEventListener("keydown", onKey, true);
      nextTick(() => {
        const el = root.value && root.value.querySelector("[autofocus], .modal-body input:not([readonly]), .modal-body select, .modal-body textarea, .modal-foot .btn-primary");
        if (el) el.focus();
      });
    });
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey, true));
    return { root };
  },
  template: `<div class="overlay" @mousedown.self="closable && $emit('close')">
      <div class="modal" :class="size" ref="root" role="dialog" aria-modal="true" :aria-label="title">
        <div class="modal-head"><slot name="head"><h3>{{ title }}</h3></slot>
          <button v-if="closable" class="btn btn-ghost btn-icon close" @click="$emit('close')" title="إغلاق (Esc)"><Icon name="x"/></button>
        </div>
        <slot name="top"></slot>
        <div class="modal-body"><slot></slot></div>
        <div class="modal-foot" v-if="$slots.foot"><slot name="foot"></slot></div>
      </div>
    </div>`,
};

export const Drawer = {
  name: "Drawer",
  components: { Icon },
  props: { title: String },
  emits: ["close"],
  setup(props, { emit }) {
    const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); emit("close"); } };
    onMounted(() => document.addEventListener("keydown", onKey, true));
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey, true));
  },
  template: `<div>
      <div class="drawer-overlay" @click="$emit('close')"></div>
      <aside class="drawer" role="dialog" aria-modal="true" :aria-label="title">
        <div class="drawer-head"><div style="flex:1;min-width:0"><slot name="head"><h3>{{ title }}</h3></slot></div>
          <button class="btn btn-ghost btn-icon" @click="$emit('close')" title="إغلاق (Esc)"><Icon name="x"/></button></div>
        <div class="drawer-body"><slot></slot></div>
        <div class="drawer-foot" v-if="$slots.foot"><slot name="foot"></slot></div>
      </aside>
    </div>`,
};

/** حقل رقم عشري: يقبل الأرقام العربية، يمنع الحروف، يتحقق من عدد المنازل، Enter ينقل للحقل التالي. */
export const NumInput = {
  name: "NumInput",
  props: { modelValue: [String, Number], dp: { type: Number, default: 4 }, placeholder: String, invalid: Boolean,
    readonly: Boolean, enterNext: { type: Boolean, default: true }, label: String },
  emits: ["update:modelValue", "enter", "blur"],
  setup(props, { emit }) {
    const err = computed(() => {
      const r = parse(props.modelValue ?? "", props.dp);
      return r.ok ? "" : r.error;
    });
    function onInput(e) {
      const clean = sanitizeTyping(e.target.value);
      if (clean !== e.target.value) e.target.value = clean;
      emit("update:modelValue", clean);
    }
    function onKey(e) {
      // التنقل بـ Enter والأسهم يتولاه المحرك العام (keynav.js)؛ هنا نبلّغ فقط من يستمع
      if (e.key === "Enter" && !e.ctrlKey && !e.altKey) emit("enter", e);
    }
    return { err, onInput, onKey };
  },
  template: `<input class="input num-input" :class="{ 'is-invalid': invalid || err }" :value="modelValue" @input="onInput"
      @keydown="onKey" @blur="$emit('blur')" inputmode="decimal" autocomplete="off" :placeholder="placeholder ?? '0'"
      :readonly="readonly" :title="err || label || ''" :aria-label="label" :aria-invalid="!!(invalid || err)" />`,
};

/** منتقي العميل: بحث سريع بالاسم أو الرقم أو الجوال، تنقل بالأسهم، Enter للاختيار. */
export const AccountPicker = {
  name: "AccountPicker",
  components: { Icon },
  props: { modelValue: [Number, String, null], placeholder: { type: String, default: "ابحث باسم العميل أو رقم الحساب…" },
    includeInactive: Boolean, invalid: Boolean, disabled: Boolean, autofocus: Boolean },
  emits: ["update:modelValue", "select"],
  setup(props, { emit }) {
    const text = ref("");
    const open = ref(false);
    const hl = ref(0);
    const input = ref(null);
    const selected = computed(() => store.accounts.find((a) => a.id === Number(props.modelValue)) || null);
    const label = (a) => (a ? `${a.name} — ${a.account_no}` : "");
    watch(selected, (a) => { if (!open.value) text.value = label(a); }, { immediate: true });
    watch(() => store.accountsVersion, () => { if (!open.value) text.value = label(selected.value); });

    const matches = computed(() => {
      const q = normalizeAr(text.value);
      const list = store.accounts.filter((a) => props.includeInactive || a.is_active);
      if (!q || (selected.value && text.value === label(selected.value))) return list.slice(0, 60);
      const digits = q.replace(/[^\d]/g, "");
      const out = [];
      for (const a of list) {
        const n = normalizeAr(a.name);
        let score = -1;
        if (a.account_no === q) score = 0;
        else if (digits && a.account_no.startsWith(digits)) score = 1;
        else if (n.startsWith(q)) score = 2;
        else if (n.includes(q)) score = 3;
        else if (digits && a.phone && a.phone.replace(/\D/g, "").includes(digits)) score = 4;
        if (score >= 0) out.push([score, a]);
      }
      out.sort((x, y) => x[0] - y[0] || x[1].name.localeCompare(y[1].name, "ar"));
      return out.slice(0, 60).map((x) => x[1]);
    });

    function choose(a) {
      emit("update:modelValue", a.id);
      emit("select", a);
      text.value = label(a);
      open.value = false;
      nextTick(() => input.value && focusNext(input.value));
    }
    // التركيز لا يفتح القائمة (حتى لا تغطي الشاشة عند الفتح التلقائي)؛ تفتح بالكتابة أو السهم أو النقر
    function onFocus(e) { hl.value = 0; e.target.select(); }
    function onMouseDown() { open.value = true; }
    function onBlur() { setTimeout(() => { open.value = false; text.value = label(selected.value); }, 150); }
    // القائمة مفتوحة: ↑↓ لاختيار العميل و Enter لاعتماده. القائمة مغلقة والعميل محدد: Enter والأسهم تنتقل بين الخانات.
    function onKey(e) {
      if (e.ctrlKey || e.altKey || e.metaKey) return;
      if (e.key === "ArrowDown") {
        if (open.value) { e.preventDefault(); hl.value = Math.min(hl.value + 1, matches.value.length - 1); scroll(); }
        else if (!selected.value || text.value !== label(selected.value)) { e.preventDefault(); open.value = true; hl.value = 0; scroll(); }
      } else if (e.key === "ArrowUp") {
        if (open.value) { e.preventDefault(); hl.value = Math.max(hl.value - 1, 0); scroll(); }
      } else if (e.key === "Enter") {
        if (open.value && matches.value[hl.value]) { e.preventDefault(); choose(matches.value[hl.value]); }
        else if (!selected.value || text.value !== label(selected.value)) { e.preventDefault(); open.value = true; hl.value = 0; }
        // وإلا: العميل محدد والقائمة مغلقة ← المحرك العام ينقل للخانة التالية
      } else if (e.key === "Escape") { if (open.value) { e.stopPropagation(); open.value = false; } }
    }
    function scroll() {
      nextTick(() => {
        const el = document.querySelector(".picker-item.hl");
        if (el) el.scrollIntoView({ block: "nearest" });
      });
    }
    function onInput() { open.value = true; hl.value = 0; }
    onMounted(() => { if (props.autofocus) nextTick(() => input.value && input.value.focus()); });
    return { text, open, hl, matches, choose, onFocus, onMouseDown, onBlur, onKey, onInput, input, selected, focus: () => input.value && input.value.focus() };
  },
  template: `<div class="picker">
      <input ref="input" class="input" :class="{ 'is-invalid': invalid }" v-model="text" :placeholder="placeholder" :disabled="disabled"
        @focus="onFocus" @mousedown="onMouseDown" @blur="onBlur" @keydown="onKey" @input="onInput" autocomplete="off" role="combobox"
        :aria-expanded="open" aria-label="العميل" data-picker />
      <div class="picker-list" v-if="open && !disabled">
        <div v-for="(a, i) in matches" :key="a.id" class="picker-item" :class="{ hl: i === hl }" @mousedown.prevent="choose(a)" @mouseenter="hl = i">
          <span class="no">{{ a.account_no }}</span><span class="nm">{{ a.name }}</span>
          <span v-if="!a.is_active" class="badge warn">موقوف</span>
          <span class="meta">أجر {{ a.wage_rate }}</span>
        </div>
        <div v-if="!matches.length" class="picker-empty">لا يوجد عميل مطابق</div>
      </div>
    </div>`,
};

export const Toasts = {
  name: "Toasts",
  components: { Icon },
  setup() {
    const icon = { success: "circle-check", error: "circle-x", warning: "triangle-alert", info: "info" };
    return { store, icon, dismissToast };
  },
  template: `<div class="toasts" role="status" aria-live="polite">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">
        <Icon :name="icon[t.kind]" />
        <div style="flex:1;min-width:0">
          <div class="t-title">{{ t.title }}</div>
          <div class="t-body" v-if="t.body" style="white-space:pre-line">{{ t.body }}</div>
          <div class="t-actions" v-if="t.actions.length">
            <button v-for="a in t.actions" class="btn btn-sm" @click="a.run(); dismissToast(t.id)">{{ a.label }}</button>
          </div>
        </div>
        <button class="close" @click="dismissToast(t.id)" aria-label="إغلاق"><Icon name="x" size="sm"/></button>
      </div>
    </div>`,
};

// ---------------------------------------------------------------- نافذة التأكيد العامة
export const confirmState = reactive({ open: false, opts: {}, reason: "", resolve: null, busy: false });

/** confirmDialog({title, body, okText, danger, reasonLabel}) → يعيد السبب/true أو null عند الإلغاء. */
export function confirmDialog(opts) {
  return new Promise((resolve) => {
    Object.assign(confirmState, { open: true, opts, reason: "", resolve });
  });
}

export const ConfirmHost = {
  name: "ConfirmHost",
  components: { Modal, Icon },
  setup() {
    const s = confirmState;
    function done(ok) {
      if (ok && s.opts.reasonLabel && s.reason.trim().length < (s.opts.minReason ?? 3)) return;
      const r = s.resolve;
      s.open = false;
      r && r(ok ? (s.opts.reasonLabel ? s.reason.trim() : true) : null);
    }
    return { s, done };
  },
  template: `<Modal v-if="s.open" :title="s.opts.title" @close="done(false)">
      <div class="stack">
        <div v-if="s.opts.body" style="white-space:pre-line">{{ s.opts.body }}</div>
        <div class="field" v-if="s.opts.reasonLabel">
          <label class="req">{{ s.opts.reasonLabel }}</label>
          <textarea class="textarea" v-model="s.reason" autofocus @keydown.enter.ctrl="done(true)"></textarea>
          <span class="hint">{{ s.opts.reasonHint || 'يُحفظ السبب في سجل التعديلات مع اسمك والتاريخ.' }}</span>
        </div>
      </div>
      <template #foot>
        <button class="btn" :class="s.opts.danger ? 'btn-danger-solid' : 'btn-primary'" @click="done(true)" data-enter-stop
          :disabled="s.opts.reasonLabel && s.reason.trim().length < (s.opts.minReason ?? 3)">{{ s.opts.okText || 'تأكيد' }}</button>
        <button class="btn" @click="done(false)">تراجع</button>
      </template>
    </Modal>`,
};

export const Empty = {
  name: "Empty",
  components: { Icon },
  props: { icon: { type: String, default: "file-search" }, text: String },
  template: `<div class="empty"><Icon :name="icon" /><div>{{ text }}</div><slot></slot></div>`,
};

export const MaterialBadge = {
  name: "MaterialBadge",
  props: { m: String },
  computed: { label() { return { gold: "ذهب", diamond: "ألماس", wage: "أجور" }[this.m]; } },
  template: `<span class="badge" :class="m">{{ label }}</span>`,
};

export const StatusBadge = {
  name: "StatusBadge",
  props: { status: String },
  template: `<span class="badge" :class="status === 'cancelled' ? 'cancelled' : 'posted'">{{ status === 'cancelled' ? 'ملغى' : 'مرحّل' }}</span>`,
};

export const KaratBadge = {
  name: "KaratBadge",
  props: { k: [Number, String], label: { type: String, default: "عيار" } },
  template: `<span class="badge gold">{{ label }} {{ k }}</span>`,
};

export function registerUi(app) {
  for (const c of [Icon, DirBadge, Bal, Modal, Drawer, NumInput, AccountPicker, Toasts, ConfirmHost, Empty,
    MaterialBadge, StatusBadge, KaratBadge]) {
    app.component(c.name, c);
  }
}

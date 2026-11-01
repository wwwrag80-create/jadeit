// نقطة البداية: الهيكل الرئيسي (الشريط العلوي + القائمة الجانبية) والتنقل بين الشاشات السبع.
import { api, setUnauthorizedHandler } from "./api.js";
import { store, can, applyBoot, loadAccounts, toast } from "./store.js";
import { registerUi } from "./components/ui.js";
import { DocView } from "./components/docs.js";
import { PrintPreview } from "./components/print.js";
import { AccountPanel, SettingsDialog, KaratDialog, LoginView } from "./components/panels.js";
import { AccountsScreen } from "./screens/accounts.js";
import { SalesScreen } from "./screens/sales.js";
import { VouchersScreen } from "./screens/vouchers.js";
import { BalancesScreen } from "./screens/balances.js";
import { StatementScreen } from "./screens/statement.js";
import { AnalysisScreen } from "./screens/analysis.js";
import { OpeningScreen } from "./screens/opening.js";
import { today } from "./util.js";
import { installKeyNav } from "./keynav.js";

const { createApp, ref, computed, onMounted, onBeforeUnmount, watch, shallowRef } = Vue;

// الشاشات السبع فقط — لا شاشات مستقلة أخرى.
const ROUTES = [
  { id: "accounts", label: "الحسابات", icon: "users", comp: AccountsScreen },
  { id: "sales", label: "المبيعات والمرتجعات", icon: "receipt", comp: SalesScreen },
  { id: "vouchers", label: "القبض والصرف", icon: "arrow-left-right", comp: VouchersScreen },
  { id: "balances", label: "الأرصدة", icon: "scale", comp: BalancesScreen },
  { id: "statement", label: "كشف الحساب", icon: "file-text", comp: StatementScreen },
  { id: "analysis", label: "تحليل حركة العميل", icon: "chart-column", comp: AnalysisScreen },
  { id: "opening", label: "الرصيد الافتتاحي", icon: "book-open", comp: OpeningScreen },
];

function currentRoute() {
  const h = (location.hash || "").replace(/^#\/?/, "");
  const id = h.split("?")[0];
  return ROUTES.find((r) => r.id === id) || ROUTES[1];
}

const App = {
  components: { DocView, PrintPreview, AccountPanel, SettingsDialog, KaratDialog, LoginView },
  setup() {
    const route = shallowRef(currentRoute());
    const routeKey = ref(location.hash);
    const menuOpen = ref(false);
    const loggedIn = computed(() => !!store.me);
    const initials = computed(() => (store.me ? store.me.full_name.trim().slice(0, 1) : ""));
    const dateLabel = computed(() => new Intl.DateTimeFormat("ar", { weekday: "long", year: "numeric", month: "long", day: "numeric" }).format(new Date()));

    function onHash() {
      // التنقل لشاشة أخرى يغلق النوافذ العامة المفتوحة
      store.print = null;
      store.docViewId = null;
      store.accountPanelId = null;
      route.value = currentRoute();
      if (store.me) refreshAccounts();
      routeKey.value = location.hash.split("?")[0] + (location.hash.includes("edit=") || location.hash.includes("account=") ? location.hash : "");
      menuOpen.value = false;
      document.title = `${route.value.label} — ${store.settings.system_name || "جاديت"}`;
      window.scrollTo(0, 0);
    }
    function onKey(e) {
      if (!store.me) return;
      if (e.altKey && !e.ctrlKey && /^Digit[1-7]$/.test(e.code)) {
        e.preventDefault();
        location.hash = "#/" + ROUTES[Number(e.code.slice(5)) - 1].id;
      }
    }
    async function boot() {
      try {
        const st = await api.get("/api/status");
        store.needsSetup = st.needs_setup;
        store.settings.system_name = st.system_name;
        if (st.logged_in) {
          applyBoot(await api.get("/api/bootstrap"));
          await loadAccounts();
        }
      } catch (e) {
        toast("error", "تعذر الاتصال بالخادم", e.message, { sticky: true });
      } finally {
        store.ready = true;
        onHash();
      }
    }
    // تحديث ذاكرة الحسابات (قد يضيف مستخدم آخر حساباً) عند التنقل أو العودة للنافذة
    let lastRefresh = 0;
    function refreshAccounts() {
      if (Date.now() - lastRefresh < 3000) return;
      lastRefresh = Date.now();
      loadAccounts().catch(() => {});
    }
    async function logout() {
      try { await api.post("/api/logout"); } catch { /* */ }
      store.me = null;
      store.accounts = [];
    }
    setUnauthorizedHandler(() => {
      if (store.me) {
        store.me = null;
        toast("warning", "انتهت الجلسة", "سجّل الدخول مجدداً. لم يُفقد أي مستند مرحّل، والمسودات محفوظة في هذا المتصفح.");
      }
    });
    onMounted(() => {
      window.addEventListener("hashchange", onHash);
      window.addEventListener("focus", () => store.me && refreshAccounts());
      document.addEventListener("keydown", onKey);
      boot();
    });
    onBeforeUnmount(() => {
      window.removeEventListener("hashchange", onHash);
      document.removeEventListener("keydown", onKey);
    });
    return { store, ROUTES, route, routeKey, menuOpen, loggedIn, initials, dateLabel, logout, can, onHash };
  },
  template: `
  <template v-if="store.ready">
    <LoginView v-if="!loggedIn" @done="onHash" />
    <div v-else class="app">
      <header class="topbar">
        <button class="btn btn-ghost btn-icon menu-toggle" @click="menuOpen = !menuOpen" aria-label="القائمة"><Icon name="layers"/></button>
        <div class="brand"><img src="/img/logo.png" alt="">
          <div style="min-width:0"><div class="brand-name">{{ store.settings.system_name }}</div><div class="brand-sub">حسابات العملاء — ذهب · ألماس · أجور</div></div></div>
        <div class="karat-chip" title="عيار العمل المعتمد في النظام">
          <Icon name="coins"/><span class="lbl">عيار العمل المعتمد</span><span class="karat-value num">{{ store.settings.working_karat }}</span>
          <button class="btn btn-sm" style="height:28px;border-radius:999px" @click="store.karatDialog = true">{{ can('settings.manage') ? 'تغيير' : 'تفاصيل' }}</button>
        </div>
        <div class="topbar-spacer"></div>
        <span class="topbar-date">{{ dateLabel }}</span>
        <button class="btn btn-ghost" @click="store.settingsOpen = true" title="الإعدادات العامة"><Icon name="settings"/> <span class="lbl">الإعدادات</span></button>
        <div class="user-chip"><span class="avatar">{{ initials }}</span><span class="small strong">{{ store.me.full_name }}</span>
          <button class="btn btn-ghost btn-icon" @click="logout" title="تسجيل الخروج"><Icon name="log-out" size="sm"/></button></div>
      </header>
      <nav class="sidebar" :class="{ open: menuOpen }" aria-label="التنقل الرئيسي">
        <div class="nav-title">الشاشات</div>
        <a v-for="(r, i) in ROUTES" :key="r.id" :href="'#/' + r.id" class="nav-item" :class="{ active: route.id === r.id }" :title="r.label">
          <Icon :name="r.icon"/><span class="lbl">{{ r.label }}</span><span class="kbd-hint">Alt+{{ i + 1 }}</span></a>
        <div class="sidebar-foot">الأرصدة تُحسب من الحركات المرحّلة فقط.<br>الذهب · الألماس · الأجور أرصدة منفصلة.</div>
      </nav>
      <main class="main"><component :is="route.comp" :key="routeKey" /></main>
    </div>
    <DocView />
    <AccountPanel />
    <SettingsDialog v-if="store.settingsOpen && loggedIn" />
    <KaratDialog v-if="store.karatDialog && loggedIn" />
    <PrintPreview />
  </template>
  <div v-else class="login-wrap"><div class="spinner" style="width:28px;height:28px;color:var(--text-3)"></div></div>
  <Toasts /><ConfirmHost />`,
};

installKeyNav();
const app = createApp(App);
registerUi(app);
app.config.errorHandler = (err) => {
  console.error(err);
  toast("error", "خطأ في الواجهة", String(err && err.message ? err.message : err));
};
app.mount("#app");

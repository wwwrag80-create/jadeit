// اختبار واجهة ثانٍ: الإعدادات، المستخدمون والصلاحيات، تغيير عيار العمل، تعديل الأجر، المرتجع غير المرتبط، تعديل مرتجع.
//   node tests/e2e/ui_admin.js
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "jadeit-e2e2-"));
const OUT = process.env.E2E_OUT || path.join(TMP, "out");
fs.mkdirSync(OUT, { recursive: true });
const PORT = 8900 + Math.floor(Math.random() * 90);
const BASE = process.env.E2E_BASE || `http://127.0.0.1:${PORT}`; // E2E_BASE: اختبار خادم يعمل مسبقاً (مثل نسخة ويندوز)
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok, info }); console.log(`${ok ? "✔" : "✘"} ${name}${info ? " — " + info : ""}`); };

async function api(page, method, p, body) {
  return page.evaluate(async ({ method, p, body }) => {
    const r = await fetch(p, { method, headers: { "Content-Type": "application/json", "X-Requested-With": "jadeit" }, body: body ? JSON.stringify(body) : undefined });
    return { status: r.status, body: await r.json() };
  }, { method, p, body });
}

(async () => {
  const server = process.env.E2E_BASE ? { kill() {} } : spawn("python3", [path.join(ROOT, "run.py"), "--port", String(PORT), "--db", path.join(TMP, "e2e.db"), "--no-backup"],
    { env: { ...process.env, JADEIT_QUIET: "1" }, stdio: "ignore" });
  let browser;
  try {
    for (let i = 0; i < 60; i++) { try { if ((await fetch(BASE + "/api/status")).ok) break; } catch { /* */ } await new Promise((r) => setTimeout(r, 250)); }
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1366, height: 860 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("401") && !m.text().includes("403")) errors.push(m.text()); });
    await page.goto(BASE + "/");
    await page.waitForSelector(".login-card");
    await page.evaluate(async () => {
      await fetch("/api/setup", { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "jadeit" },
        body: JSON.stringify({ username: "admin", password: "secret123", full_name: "المدير", working_karat: 18 }) });
    });
    await page.reload();
    await page.waitForSelector(".topbar");

    // بيانات أساسية عبر الواجهة البرمجية
    const a = (await api(page, "POST", "/api/accounts", { name: "عميل الصلاحيات", wage_rate: "4", client_token: "acc000000001" })).body;
    const sale = (await api(page, "POST", "/api/documents", { doc_type: "sale", client_token: "doc000000001", account_id: a.id, doc_date: "2026-10-01",
      lines: [{ run_no: "R1", gold: "10", diamond: "1" }, { run_no: "R2", gold: "5" }] })).body;
    const ret = (await api(page, "POST", "/api/documents", { doc_type: "return", client_token: "doc000000002", account_id: a.id, doc_date: "2026-10-02",
      original_doc_id: sale.id, lines: [{ original_line_id: sale.lines[0].id, gold: "3" }] })).body;
    check("تجهيز بيانات", sale.doc_no === "SA-000001" && ret.doc_no === "SR-000001");

    // ---- تعديل مرتجع مرحّل عبر الواجهة
    await page.goto(BASE + "/#/sales?edit=" + ret.id);
    await page.waitForSelector("text=وضع التعديل");
    await page.waitForSelector('[data-row="0"][data-col="gold"]');
    await page.locator('[data-row="0"][data-col="gold"]').fill("10");
    await page.waitForTimeout(150);
    check("تعديل المرتجع: المتبقي يشمل كمية المستند نفسه", await page.locator(".line-err").count() === 0);
    await page.locator('[data-row="0"][data-col="gold"]').fill("10.0001");
    await page.waitForTimeout(150);
    check("تعديل المرتجع: منع تجاوز المباع", await page.locator(".line-err").count() === 1);
    await page.locator('[data-row="0"][data-col="gold"]').fill("4");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة التعديل");
    await page.getByPlaceholder("مثال: تصحيح وزن السطر 3").fill("تصحيح كمية المرتجع");
    await page.getByRole("button", { name: /تأكيد حفظ التعديل/ }).click();
    await page.waitForSelector("text=تم حفظ التعديل");
    const b1 = (await api(page, "GET", "/api/balances?q=" + a.account_no)).body.items[0];
    check("رصيد الذهب بعد تعديل المرتجع", b1.gold.signed === "11.0000" && b1.wage.signed === "44.00", `${b1.gold.signed} / ${b1.wage.signed}`);

    // ---- تعديل أجر الحساب مع السبب
    await page.goto(BASE + "/#/accounts?edit=" + a.id);
    await page.waitForSelector("text=تعديل بيانات الحساب");
    await page.fill("#acc-rate", "6");
    await page.waitForSelector("#acc-reason");
    await page.fill("#acc-reason", "زيادة الأجر من بداية الشهر");
    await page.screenshot({ path: path.join(OUT, "19-account-edit.png"), fullPage: true });
    await page.getByRole("button", { name: "حفظ التعديلات" }).click();
    await page.waitForSelector("text=تم حفظ التعديلات");
    const doc = (await api(page, "GET", "/api/documents/" + sale.id)).body;
    check("تعديل الأجر الافتراضي لا يغير الفاتورة القديمة", doc.lines[0].rate === "4.00" && doc.totals.wage === "60.00");

    // ---- الإعدادات: كل التبويبات + فحص السلامة + المستخدمون
    await page.getByRole("button", { name: /الإعدادات/ }).click();
    await page.waitForSelector("text=الإعدادات العامة");
    for (const t of ["المستخدمون والصلاحيات", "النسخ الاحتياطي", "فحص سلامة البيانات", "سجل العمليات", "كلمة المرور", "عام"]) {
      await page.locator(".tabs button", { hasText: t }).click();
      await page.waitForTimeout(250);
    }
    await page.locator(".tabs button", { hasText: "فحص سلامة البيانات" }).click();
    await page.getByRole("button", { name: /تشغيل الفحص/ }).click();
    await page.waitForSelector("text=البيانات سليمة ومتطابقة");
    check("فحص السلامة من الواجهة", true);
    await page.locator(".tabs button", { hasText: "المستخدمون والصلاحيات" }).click();
    await page.waitForSelector("text=مستخدم جديد");
    const form = page.locator(".card", { hasText: "مستخدم جديد" });
    await form.locator("input.input").nth(0).fill("clerk");
    await form.locator("input.input").nth(1).fill("محاسب مبتدئ");
    await form.locator("input.input").nth(2).fill("clerk123");
    await page.getByRole("button", { name: "حفظ المستخدم" }).click();
    await page.waitForSelector("text=تم إنشاء المستخدم");
    await page.screenshot({ path: path.join(OUT, "20-settings-users.png") });
    await page.keyboard.press("Escape");

    // ---- تغيير عيار العمل
    await page.locator(".karat-chip button").click();
    await page.waitForSelector("text=التغيير يسري على العمليات الجديدة فقط");
    await page.locator(".modal .seg button", { hasText: "21" }).click();
    await page.locator(".modal input.input").fill("اعتماد عيار 21");
    await page.getByRole("button", { name: "حفظ العيار" }).click();
    await page.waitForSelector("text=تم تغيير عيار العمل");
    check("تغيير عيار العمل من أعلى الواجهة", (await page.locator(".karat-value").innerText()).trim() === "21");
    const d2 = (await api(page, "GET", "/api/documents/" + sale.id)).body;
    check("المستند القديم يحتفظ بعيار 18", d2.working_karat === 18);

    // ---- مستخدم محدود الصلاحيات
    await page.getByTitle("تسجيل الخروج").click();
    await page.waitForSelector(".login-card");
    const li = page.locator(".login-card input");
    await li.nth(0).fill("clerk");
    await li.nth(1).fill("clerk123");
    await page.getByRole("button", { name: "دخول" }).click();
    await page.waitForSelector(".topbar");
    await page.goto(BASE + "/#/sales");
    await page.waitForSelector("[data-picker]");
    await page.locator("[data-picker]").fill(a.account_no);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    check("المحاسب لا يعدّل أجر السطر", await page.locator('[data-col="rate"]').count() === 0);
    await page.getByRole("button", { name: /مرتجع مبيعات/ }).click();
    check("المرتجع غير المرتبط معطّل دون صلاحية", await page.getByRole("button", { name: /غير مرتبط/ }).isDisabled());
    const forbidden = await api(page, "POST", "/api/documents/" + sale.id + "/cancel", { reason: "محاولة" });
    check("المحاسب لا يلغي مستنداً", forbidden.status === 403, forbidden.body.error.message);
    await page.goto(BASE + "/#/balances");
    await page.getByRole("button", { name: "عميل الصلاحيات" }).click();
    await page.waitForSelector(".drawer");
    await page.locator(".drawer .tbl tr.clickable").first().click();
    await page.waitForSelector(".modal");
    check("زر التعديل والإلغاء مخفيان دون صلاحية", await page.getByRole("button", { name: /إلغاء المستند/ }).count() === 0 && await page.locator(".modal-foot").getByRole("button", { name: "تعديل", exact: true }).count() === 0);
    await page.screenshot({ path: path.join(OUT, "21-doc-view-limited.png") });

    check("لا أخطاء في وحدة التحكم", errors.length === 0, errors.slice(0, 5).join(" || "));
  } catch (e) {
    console.error(e);
    check("اكتمل السيناريو دون استثناء", false, e.message);
  } finally {
    if (browser) await browser.close();
    server.kill();
    const failed = results.filter((r) => !r.ok);
    console.log(`\nالنتيجة: ${results.length - failed.length}/${results.length} ناجح`);
    process.exit(failed.length ? 1 : 0);
  }
})();

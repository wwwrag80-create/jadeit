// اختبار التنقل بلوحة المفاتيح فقط: Enter والأسهم بين كل الخانات، والترحيل بـ Enter، في كل شاشات الإدخال.
//   node tests/e2e/ui_keyboard.js
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "jadeit-kb-"));
const PORT = 8700 + Math.floor(Math.random() * 90);
const BASE = process.env.E2E_BASE || `http://127.0.0.1:${PORT}`; // E2E_BASE: اختبار خادم يعمل مسبقاً (مثل نسخة ويندوز)
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok, info }); console.log(`${ok ? "✔" : "✘"} ${name}${info ? " — " + info : ""}`); };

async function api(page, p) { return page.evaluate(async (u) => (await fetch(u)).json(), p); }
const active = (page) => page.evaluate(() => {
  const el = document.activeElement;
  return { tag: el.tagName, id: el.id, col: el.dataset.col || "", row: el.dataset.row || "", text: (el.innerText || "").trim().slice(0, 30),
    type: el.type || "", picker: el.hasAttribute("data-picker"), label: el.getAttribute("aria-label") || "", stop: el.hasAttribute("data-enter-stop") };
});

(async () => {
  const server = process.env.E2E_BASE ? { kill() {} } : spawn("python3", [path.join(ROOT, "run.py"), "--port", String(PORT), "--db", path.join(TMP, "kb.db"), "--no-backup"],
    { env: { ...process.env, JADEIT_QUIET: "1" }, stdio: "ignore" });
  let browser;
  try {
    for (let i = 0; i < 60; i++) { try { if ((await fetch(BASE + "/api/status")).ok) break; } catch { /* */ } await new Promise((r) => setTimeout(r, 250)); }
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1366, height: 900 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const k = (key) => page.keyboard.press(key);
    const type = (t) => page.keyboard.type(t);

    // ---- الدخول بلوحة المفاتيح فقط
    await page.goto(BASE + "/");
    await page.evaluate(async () => {
      await fetch("/api/setup", { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "jadeit" },
        body: JSON.stringify({ username: "admin", password: "secret123", full_name: "المدير", working_karat: 18 }) });
      await fetch("/api/logout", { method: "POST", headers: { "X-Requested-With": "jadeit" } });
    });
    await page.reload();
    await page.waitForSelector(".login-card");
    await type("admin"); await k("Enter");
    await type("secret123"); await k("Enter");
    const a0 = await active(page);
    check("الدخول: Enter ينقل لزر الدخول", a0.tag === "BUTTON" && a0.stop, JSON.stringify(a0));
    await k("Enter");
    await page.waitForSelector(".topbar");

    // ---- الحسابات
    await page.goto(BASE + "/#/accounts");
    await page.waitForSelector("#acc-name");
    await page.focus("#acc-name");
    await type("مؤسسة الكيبورد"); await k("Enter");
    check("الحسابات: Enter من الاسم إلى الجوال", (await active(page)).id === "acc-phone");
    await type("0500000000"); await k("Enter");
    check("الحسابات: Enter إلى الأجر", (await active(page)).id === "acc-rate");
    await type("5.5"); await k("ArrowDown");
    check("الحسابات: السهم ↓ إلى الملاحظات", (await active(page)).id === "acc-notes");
    await k("ArrowUp");
    check("الحسابات: السهم ↑ يرجع للأجر", (await active(page)).id === "acc-rate");
    await k("Shift+Enter");
    check("الحسابات: Shift+Enter للخانة السابقة", (await active(page)).id === "acc-phone");
    await k("Enter"); await k("Enter"); await type("ملاحظة"); await k("Enter");
    const a1 = await active(page);
    check("الحسابات: آخر خانة + Enter ← زر إنشاء حساب", a1.tag === "BUTTON" && a1.text.includes("إنشاء حساب"), a1.text);
    await k("Enter");
    await page.waitForSelector("text=تم إنشاء الحساب");
    const accs = await api(page, "/api/accounts");
    check("الحسابات: الإنشاء بـ Enter", accs.length === 1 && accs[0].wage_rate === "5.50");

    // ---- المبيعات: إدخال كامل وترحيل بلوحة المفاتيح
    await page.goto(BASE + "/#/sales");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.waitForTimeout(300);
    const a2 = await active(page);
    check("المبيعات: التركيز يبدأ على العميل", a2.picker, JSON.stringify(a2));
    await type("1001"); await k("Enter");
    const a3 = await active(page);
    check("المبيعات: Enter يختار العميل وينتقل للتاريخ", a3.type === "date", JSON.stringify(a3));
    await k("Enter"); await k("Enter"); await k("Enter");
    const a4 = await active(page);
    check("المبيعات: Enter ينقل حتى أول خانة في الجدول", a4.col === "run_no" && a4.row === "0", JSON.stringify(a4));
    await type("K1"); await k("Enter"); await type("10"); await k("Enter"); await type("0.5"); await k("Enter"); await k("Enter");
    const a5 = await active(page);
    check("المبيعات: Enter في آخر خانة يضيف سطراً جديداً", a5.col === "run_no" && a5.row === "1", JSON.stringify(a5));
    await type("K2"); await k("ArrowLeft");
    const a6 = await active(page);
    check("المبيعات: السهم ← ينتقل للعمود التالي", a6.col === "gold" && a6.row === "1", JSON.stringify(a6));
    await type("5"); await k("ArrowUp");
    const a7 = await active(page);
    check("المبيعات: السهم ↑ لنفس العمود في السطر السابق", a7.col === "gold" && a7.row === "0", JSON.stringify(a7));
    await k("ArrowDown"); await k("Enter"); await k("Enter"); await k("Enter");
    const a8 = await active(page);
    check("المبيعات: سطر جديد فارغ", a8.col === "run_no" && a8.row === "2", JSON.stringify(a8));
    await k("Enter");
    const a9 = await active(page);
    check("المبيعات: Enter على سطر فارغ ← زر الترحيل", a9.tag === "BUTTON" && a9.text.includes("ترحيل"), a9.text);
    await k("Enter");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.waitForTimeout(200);
    await k("Enter");
    await page.waitForSelector("text=تم ترحيل");
    const sales = await api(page, "/api/documents?types=sale");
    check("المبيعات: الترحيل بـ Enter (سطران)", sales.length === 1 && sales[0].lines === 2 && sales[0].gold === "15.0000", sales[0] && `${sales[0].lines} / ${sales[0].gold}`);

    // ---- القبض: اختيار العيار بالأسهم
    await page.goto(BASE + "/#/vouchers");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.waitForTimeout(300);
    await type("1001"); await k("Enter"); await k("Enter");
    check("القبض: Enter إلى الوزن الفعلي", (await active(page)).label === "الوزن الفعلي");
    await type("100"); await k("Enter");
    const b1 = await active(page);
    check("القبض: Enter إلى مجموعة العيار", b1.tag === "BUTTON" && b1.text === "18", JSON.stringify(b1));
    await k("ArrowLeft");
    const b2 = await active(page);
    check("القبض: السهم يغيّر العيار إلى 21", b2.text === "21" && (await page.locator(".readout.big .num").first().innerText()).includes("116.6667"));
    await k("Enter"); await k("Enter"); await k("Enter");
    const b3 = await active(page);
    check("القبض: الوصول لزر الترحيل", b3.tag === "BUTTON" && b3.text.includes("ترحيل"), b3.text);
    await k("Enter");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.waitForTimeout(200);
    await k("Enter");
    await page.waitForSelector("text=تم ترحيل");
    const rv = await api(page, "/api/documents?types=receipt");
    check("القبض: الترحيل بـ Enter وبالعيار المختار", rv.length === 1 && rv[0].gold === "116.6667", rv[0] && rv[0].gold);

    // ---- الرصيد الافتتاحي
    await page.goto(BASE + "/#/opening");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.waitForTimeout(300);
    await type("1001"); await k("Enter"); await k("Enter"); await k("Enter"); await k("Enter");
    const c1 = await active(page);
    check("الافتتاحي: Enter حتى نوع الرصيد في الجدول", c1.tag === "SELECT", JSON.stringify(c1));
    await k("Enter");
    await page.evaluate(() => { const s = document.activeElement; s.value = "debit"; s.dispatchEvent(new Event("change")); });
    await k("Enter"); await type("50"); await k("Enter");
    await page.evaluate(() => { const s = document.activeElement; s.value = "21"; s.dispatchEvent(new Event("change")); });
    await k("Enter"); await type("رصيد سابق"); await k("Enter"); await k("Enter");
    const c2 = await active(page);
    check("الافتتاحي: الوصول لزر الترحيل", c2.tag === "BUTTON" && c2.text.includes("ترحيل"), c2.text);
    await k("Enter");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.waitForTimeout(200);
    await k("Enter");
    await page.waitForSelector("text=تم ترحيل الرصيد الافتتاحي");
    const bal = (await api(page, "/api/balances")).items[0];
    check("الافتتاحي: الترحيل بـ Enter (15 − 116.6667 + 58.3333)", bal.gold.signed === "-43.3334", bal.gold.signed);

    // ---- كشف الحساب: اختيار النوع بالأسهم والعرض بـ Enter
    await page.goto(BASE + "/#/statement");
    await page.waitForSelector("[data-picker]");
    await page.waitForTimeout(300);
    await type("1001"); await k("Enter"); await k("Enter"); await k("Enter");
    const d1 = await active(page);
    check("الكشف: Enter إلى نوع الكشف", d1.tag === "BUTTON" && d1.text.includes("الذهب"), d1.text);
    await k("Enter");
    const d2 = await active(page);
    check("الكشف: Enter إلى زر عرض الكشف", d2.text.includes("عرض الكشف"), d2.text);
    await k("Enter");
    await page.waitForSelector(".stats");
    check("الكشف: العرض بـ Enter", await page.locator(".tbl tbody tr").count() >= 3);

    check("لا أخطاء في الواجهة", errors.length === 0, errors.join(" | "));
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

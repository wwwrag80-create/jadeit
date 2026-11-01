// اختبار واجهة شامل في متصفح حقيقي (Playwright + Chromium).
// يشغّل الخادم على قاعدة بيانات مؤقتة منفصلة، ثم ينفذ سيناريو المحاسب كاملاً عبر الواجهة.
//   node tests/e2e/ui_flow.js            (يتطلب: npm i playwright  أو Playwright مثبت مسبقاً)
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.resolve(__dirname, "..", "..");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "jadeit-e2e-"));
const OUT = process.env.E2E_OUT || path.join(TMP, "out");
fs.mkdirSync(OUT, { recursive: true });
const PORT = 8800 + Math.floor(Math.random() * 100);
const BASE = process.env.E2E_BASE || `http://127.0.0.1:${PORT}`; // E2E_BASE: اختبار خادم يعمل مسبقاً (مثل نسخة ويندوز)

const results = [];
function check(name, ok, info = "") {
  results.push({ name, ok, info });
  console.log(`${ok ? "✔" : "✘"} ${name}${info ? " — " + info : ""}`);
}

async function waitServer() {
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(BASE + "/api/status"); if (r.ok) return; } catch { /* */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("server did not start");
}

async function apiGet(page, p) {
  return page.evaluate(async (u) => (await fetch(u)).json(), p);
}

(async () => {
  const server = process.env.E2E_BASE ? { kill() {} } : spawn("python3", [path.join(ROOT, "run.py"), "--port", String(PORT), "--db", path.join(TMP, "e2e.db"), "--no-backup"],
    { env: { ...process.env, JADEIT_QUIET: "1" }, stdio: "inherit" });
  let browser;
  try {
    await waitServer();
    browser = await chromium.launch();
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    const shot = (n) => page.screenshot({ path: path.join(OUT, n + ".png"), fullPage: true });

    // ---------------------------------------------------------- الإعداد الأول
    await page.goto(BASE + "/");
    await page.getByLabel("اسم مدير النظام").fill("مدير النظام").catch(() => {});
    const inputs = page.locator(".login-card input");
    await inputs.nth(1).fill("مدير النظام");
    await inputs.nth(2).fill("admin");
    await inputs.nth(3).fill("secret123");
    await inputs.nth(4).fill("secret123");
    await page.getByRole("button", { name: "18" }).click();
    await page.getByRole("button", { name: "إنشاء وبدء الاستخدام" }).click();
    await page.waitForSelector(".topbar");
    check("الإعداد الأول وتسجيل الدخول", true);
    check("عيار العمل ظاهر أعلى الواجهة", (await page.locator(".karat-value").innerText()).trim() === "18");

    // ---------------------------------------------------------- 1) إنشاء حساب
    await page.goto(BASE + "/#/accounts");
    await page.fill("#acc-name", "مؤسسة النور للمجوهرات");
    await page.fill("#acc-phone", "0551234567");
    await page.fill("#acc-rate", "5.5");
    const createBtn = page.getByRole("button", { name: "إنشاء حساب" });
    await Promise.all([createBtn.click(), createBtn.click({ force: true }).catch(() => {})]); // ضغط مزدوج
    await page.waitForSelector(".alert.ok");
    await page.waitForTimeout(400);
    let accs = await apiGet(page, "/api/accounts");
    check("إنشاء حساب بأجر 5.50 (ضغط مزدوج لا يكرر)", accs.length === 1 && accs[0].wage_rate === "5.50" && accs[0].account_no === "1001", JSON.stringify(accs.map((a) => a.account_no)));
    await page.fill("#acc-name", "مؤسسة النور للمجوهرات ");
    await page.waitForTimeout(600);
    check("تنبيه الاسم المكرر", await page.locator("text=يوجد حساب بالاسم نفسه").count() > 0);
    await page.getByRole("button", { name: "مسح الحقول" }).click();
    await page.fill("#acc-name", "ورشة الفجر");
    await page.fill("#acc-rate", "3");
    await page.getByRole("button", { name: "إنشاء حساب" }).click();
    await page.waitForTimeout(500);
    await shot("01-accounts");

    // ---------------------------------------------------------- 2) فاتورة مبيعات متعددة الأسطر بلوحة المفاتيح
    await page.goto(BASE + "/#/sales");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.locator("[data-picker]").fill("النور");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    await page.locator('[data-row="0"][data-col="run_no"]').click();
    const typeRow = async (run, gold, dia) => {
      await page.keyboard.type(run); await page.keyboard.press("Enter");
      await page.keyboard.type(gold); await page.keyboard.press("Enter");
      await page.keyboard.type(dia); await page.keyboard.press("Enter");
      await page.keyboard.press("Enter"); // عمود الأجر المعتمد (المدير يملك صلاحية تعديله) — نبقي الأجر الافتراضي
    };
    await typeRow("0012", "10.25", "0.5");
    await typeRow("0013", "5", "");
    await typeRow("0014", "", "1.25");
    await page.waitForTimeout(200);
    const totals = await page.locator(".totals-bar .t-value").allInnerTexts();
    check("إجماليات المستند قبل الترحيل", totals[0].includes("3") && totals[1].includes("15.2500") && totals[2].includes("1.750") && totals[3].includes("83.88"), totals.join(" | "));
    await shot("02-sales-entry");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await shot("03-sales-summary");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل");
    const sale = (await apiGet(page, "/api/documents?types=sale"))[0];
    check("ترحيل فاتورة المبيعات SA-000001", sale && sale.doc_no === "SA-000001" && sale.gold === "15.2500" && sale.wage === "83.88", sale && `${sale.gold} / ${sale.wage}`);

    // ---------------------------------------------------------- 4) مرتجع مرتبط بالفاتورة
    await page.getByRole("button", { name: /مرتجع مبيعات/ }).click();
    await page.locator("[data-picker]").fill("النور");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(400);
    await page.locator("select.select").first().selectOption({ index: 1 });
    await page.waitForSelector("text=أسطر الفاتورة الأصلية");
    await page.locator(".section-box button", { hasText: "إضافة" }).nth(1).click(); // السطر الأول (بعد زر إضافة كل المتبقي)
    const goldInput = page.locator('[data-row="0"][data-col="gold"]');
    await goldInput.fill("2.25");
    await page.locator('[data-row="0"][data-col="diamond"]').fill("0.1");
    await page.waitForTimeout(200);
    const rt = await page.locator(".totals-bar .t-value").allInnerTexts();
    check("حساب الأجر المسترد بأجر الفاتورة الأصلية", rt[3].includes("12.38"), rt.join(" | "));
    await page.locator('[data-row="0"][data-col="gold"]').fill("11");
    await page.waitForTimeout(150);
    check("منع مرتجع أكبر من المباع (في الواجهة)", await page.locator(".line-err", { hasText: "أكبر من المتبقي" }).count() === 1);
    await page.locator('[data-row="0"][data-col="gold"]').fill("2.25");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل");
    await shot("04-return-posted");

    // ---------------------------------------------------------- 5/6) قبض ذهب عيار 21
    await page.goto(BASE + "/#/vouchers");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.locator("[data-picker]").fill("1001");
    await page.keyboard.press("Enter");
    await page.getByLabel("الوزن الفعلي").fill("100");
    await page.getByRole("button", { name: "21", exact: true }).click();
    const eqText = await page.locator(".readout.big .num").first().innerText();
    check("الوزن المكافئ 100 × 21 ÷ 18 = 116.6667", eqText.includes("116.6667"), eqText);
    await shot("05-voucher-gold");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل");

    // 7) صرف ذهب ثم 8) قبض ألماس
    await page.getByRole("button", { name: /صرف/ }).first().click();
    await page.locator("[data-picker]").fill("1001");
    await page.keyboard.press("Enter");
    await page.getByLabel("الوزن الفعلي").fill("20");
    await page.getByRole("button", { name: "18", exact: true }).click();
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل");
    await page.getByRole("button", { name: /قبض/ }).first().click();
    await page.getByRole("button", { name: /ألماس/ }).first().click();
    await page.locator("[data-picker]").fill("1001");
    await page.keyboard.press("Enter");
    await page.getByLabel("وزن الألماس").fill("0.4");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل");

    // ---------------------------------------------------------- 9/10) رصيد افتتاحي مدين ودائن
    await page.goto(BASE + "/#/opening");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForSelector("[data-picker]");
    await page.locator("[data-picker]").fill("الفجر");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    const row0 = page.locator("tbody tr").first();
    await row0.locator("select").nth(1).selectOption("debit");
    await row0.locator("input.num-input").fill("50");
    await row0.locator("select").nth(2).selectOption("21");
    await page.getByRole("button", { name: "أجور", exact: true }).click();
    const row1 = page.locator("tbody tr").nth(1);
    await row1.locator("select").nth(1).selectOption("credit");
    await row1.locator("input.num-input").fill("120.5");
    await shot("06-opening");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة قبل الترحيل");
    await page.getByRole("button", { name: /تأكيد الترحيل/ }).click();
    await page.waitForSelector("text=تم ترحيل الرصيد الافتتاحي");

    // ---------------------------------------------------------- الأرصدة
    await page.goto(BASE + "/#/balances");
    await page.waitForSelector(".tbl tbody tr");
    await page.waitForTimeout(300);
    await shot("07-balances");
    const bal = await apiGet(page, "/api/balances");
    const nour = bal.items.find((x) => x.account_no === "1001");
    const fajr = bal.items.find((x) => x.account_no === "1002");
    // ذهب: 15.25 − 2.25 − 116.6667 + 20 = −83.6667 ؛ ألماس: 1.75 − 0.1 − 0.4 = 1.25 ؛ أجور: 83.88 − 12.38 = 71.50
    check("أرصدة العميل الأول", nour.gold.signed === "-83.6667" && nour.diamond.signed === "1.250" && nour.wage.signed === "71.50",
      `${nour.gold.signed} / ${nour.diamond.signed} / ${nour.wage.signed}`);
    check("رصيد افتتاحي مدين ذهب ودائن أجور", fajr.gold.signed === "58.3333" && fajr.wage.signed === "-120.50", `${fajr.gold.signed} / ${fajr.wage.signed}`);
    await page.getByRole("button", { name: "مؤسسة النور للمجوهرات" }).click();
    await page.waitForSelector(".drawer");
    await shot("08-account-panel");
    await page.keyboard.press("Escape");

    // ---------------------------------------------------------- كشف الحساب لفترة + مطابقته للأرصدة
    await page.goto(BASE + "/#/statement?account=" + nour.id + "&material=gold");
    await page.waitForSelector(".stats");
    await page.waitForTimeout(300);
    await shot("09-statement");
    const st = await apiGet(page, `/api/statement?account_id=${nour.id}&material=gold`);
    check("الكشف الكامل مطابق لشاشة الأرصدة", st.closing.signed === nour.gold.signed, st.closing.signed);

    // ---------------------------------------------------------- 15) تعديل مستند مرحّل
    await page.goto(BASE + "/#/sales?edit=" + sale.id);
    await page.waitForSelector("text=وضع التعديل");
    await page.locator('[data-row="1"][data-col="gold"]').fill("6");
    await page.keyboard.press("F9");
    await page.waitForSelector("text=مراجعة التعديل");
    await page.getByPlaceholder("مثال: تصحيح وزن السطر 3").fill("تصحيح وزن القطعة 0013");
    await page.getByRole("button", { name: /تأكيد حفظ التعديل/ }).click();
    await page.waitForSelector("text=تم حفظ التعديل");
    const bal2 = (await apiGet(page, "/api/balances?q=1001")).items[0];
    check("التعديل حدّث الذهب والأجور", bal2.gold.signed === "-82.6667" && bal2.wage.signed === "77.00", `${bal2.gold.signed} / ${bal2.wage.signed}`);

    // ---------------------------------------------------------- 16) إلغاء مستند مع حفظ الأثر + معاينة الطباعة
    const vouchers = await apiGet(page, "/api/documents?types=payment");
    await page.evaluate((id) => { window.location.hash = "#/balances"; }, null);
    await page.goto(BASE + "/#/vouchers");
    await page.waitForSelector("text=آخر السندات");
    await page.locator("td.link", { hasText: vouchers[0].doc_no }).click();
    await page.waitForSelector(".modal");
    await page.getByRole("button", { name: /إلغاء المستند/ }).click();
    await page.locator(".modal textarea").fill("سند مكرر بالخطأ");
    await page.getByRole("button", { name: "تأكيد الإلغاء" }).click();
    await page.waitForSelector("text=تم إلغاء المستند");
    const bal3 = (await apiGet(page, "/api/balances?q=1001")).items[0];
    check("الإلغاء بقيد عكسي أعاد الرصيد", bal3.gold.signed === "-102.6667", bal3.gold.signed);
    await shot("10-cancelled-doc");
    await page.keyboard.press("Escape");

    // ---------------------------------------------------------- تحليل الحركة
    await page.goto(BASE + "/#/analysis?account=" + nour.id);
    await page.waitForSelector(".stats");
    await page.waitForTimeout(300);
    await shot("11-analysis");
    const an = await apiGet(page, `/api/analysis?account_id=${nour.id}`);
    check("صافي المباع بعد المرتجعات", an.net.totals.gold.signed === "14.0000" && an.net.totals.wage.signed === "77.00", `${an.net.totals.gold.signed} / ${an.net.totals.wage.signed}`);

    // ---------------------------------------------------------- 19) طباعة عربية + معاينة صفحات
    await page.goto(BASE + "/#/statement?account=" + nour.id + "&material=gold");
    await page.waitForSelector(".stats");
    await page.getByRole("button", { name: "معاينة" }).click();
    await page.waitForSelector(".print-preview .sheet");
    await shot("12-print-preview");
    const pagesInfo = await page.locator(".preview-tools .badge").innerText();
    check("معاينة كشف الحساب (A4)", /صفحة|صفحات/.test(pagesInfo), pagesInfo);
    const sheetText = await page.locator(".print-preview .sheet").first().innerText();
    check("الطباعة تعرض التواريخ وأرقام الحسابات دون فواصل آلاف", sheetText.includes("1001") && !sheetText.includes("1,001") && !sheetText.includes("2,02") && sheetText.includes("116.6667"));
    // اطبع إلى PDF بنفس محتوى المعاينة
    await page.evaluate(() => {
      const root = document.getElementById("print-root");
      root.innerHTML = Array.from(document.querySelectorAll(".print-preview .sheet")).map((s) => s.outerHTML).join("");
      document.body.classList.add("printing");
    });
    await page.pdf({ path: path.join(OUT, "statement.pdf"), preferCSSPageSize: true, printBackground: true });
    check("حفظ كشف الحساب PDF", fs.statSync(path.join(OUT, "statement.pdf")).size > 10000);
    await page.evaluate(() => document.body.classList.remove("printing"));

    // كشف طويل متعدد الصفحات: 80 سطر بيع
    const lines = Array.from({ length: 80 }, (_, i) => ({ run_no: String(1000 + i), gold: "1.1", diamond: "0" }));
    await page.evaluate(async ({ id, lines }) => {
      await fetch("/api/documents", { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "jadeit" },
        body: JSON.stringify({ doc_type: "sale", client_token: "bulk" + Date.now(), account_id: id, doc_date: new Date().toISOString().slice(0, 10), lines }) });
    }, { id: nour.id, lines });
    const big = (await apiGet(page, "/api/documents?types=sale"))[0];
    await page.goto(BASE + "/#/balances");
    await page.evaluate((id) => { window.__open = id; }, big.id);
    await page.waitForSelector(".tbl tbody tr");
    await page.evaluate(() => { document.querySelector("#app").__vue_app__.config.globalProperties; });
    await page.goto(BASE + "/#/sales");
    await page.getByRole("button", { name: /بحث عن مستند/ }).click();
    await page.locator(".modal input.input").first().fill(big.doc_no);
    await page.keyboard.press("Enter");
    await page.locator("tr.clickable").first().click();
    await page.getByRole("button", { name: /معاينة وطباعة/ }).click();
    await page.waitForSelector(".print-preview .sheet");
    const nPages = await page.locator(".print-preview .sheet").count();
    const lastFoot = await page.locator(".print-preview .sheet .p-pageno").last().innerText();
    const headersRepeated = await page.locator(".print-preview .sheet thead").count();
    check("فاتورة 80 سطراً على عدة صفحات مع تكرار العناوين", nPages >= 2 && headersRepeated === nPages && lastFoot.includes(`من ${nPages}`), `${nPages} صفحات — ${lastFoot}`);
    await shot("13-invoice-multipage-preview");
    await page.evaluate(() => {
      const root = document.getElementById("print-root");
      root.innerHTML = Array.from(document.querySelectorAll(".print-preview .sheet")).map((s) => s.outerHTML).join("");
      document.body.classList.add("printing");
    });
    await page.pdf({ path: path.join(OUT, "invoice-80-lines.pdf"), preferCSSPageSize: true, printBackground: true });
    await page.evaluate(() => document.body.classList.remove("printing"));

    // ---------------------------------------------------------- 20) فحص السلامة
    const integ = await apiGet(page, "/api/integrity");
    check("فحص السلامة: لا أرصدة وهمية ولا حركات مكررة", integ.ok, `${integ.documents_checked} مستند / ${integ.entries_checked} قيد`);

    // ---------------------------------------------------------- التجاوب مع شاشة صغيرة
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(BASE + "/#/balances");
    await page.waitForTimeout(500);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    await shot("14-mobile-balances");
    check("لا تمرير أفقي للصفحة على الجوال", overflow <= 1, `فرق ${overflow}px`);

    check("لا أخطاء في وحدة التحكم", errors.length === 0, errors.slice(0, 5).join(" || "));
  } catch (e) {
    console.error(e);
    check("اكتمل السيناريو دون استثناء", false, e.message);
  } finally {
    if (browser) await browser.close();
    server.kill();
    const failed = results.filter((r) => !r.ok);
    fs.writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2));
    console.log(`\nالنتيجة: ${results.length - failed.length}/${results.length} ناجح — المخرجات في ${OUT}`);
    process.exit(failed.length ? 1 : 0);
  }
})();

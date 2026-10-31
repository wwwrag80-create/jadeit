// محرّك المعاينة والطباعة: يقسّم المستند إلى صفحات A4 حقيقية بقياس فعلي للمحتوى،
// مع تكرار عناوين الجداول في كل صفحة وترقيم «صفحة س من ص». المعاينة = ما يُطبع تماماً.
import { store } from "../store.js";
import { group } from "../num.js";
import { fmtDateTime, DOC_LABEL, MATERIAL_LABEL } from "../util.js";

const { computed, onMounted, onBeforeUnmount } = Vue;

export function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const n = (v) => `<span class="num">${esc(group(v))}</span>`;          // مبلغ أو وزن (بفواصل الآلاف)
const t = (v) => `<span class="num">${esc(v ?? "")}</span>`;            // معرّف: رقم حساب، تاريخ، رقم مستند
const DIR_AR = { debit: "مدين", credit: "دائن", zero: "صفر" };
const balTxt = (b) => (b ? `${n(b.value)} ${DIR_AR[b.direction]}` : "");

function nowStr() {
  return fmtDateTime(new Date().toISOString());
}

function sheetHtml(spec, first) {
  const meta = first
    ? `<div class="p-meta">${spec.meta.map(([k, v]) => `<div><b>${esc(k)}:</b> ${v}</div>`).join("")}</div>`
    : `<div class="p-meta" style="grid-template-columns:repeat(3,1fr)">${spec.meta.slice(0, 3).map(([k, v]) => `<div><b>${esc(k)}:</b> ${v}</div>`).join("")}</div>`;
  return `<div class="sheet">
    <div class="p-head"><img src="/img/logo.png" alt="">
      <div><div class="p-sys">${esc(store.settings.system_name)}</div><div style="font-size:8.5pt">${esc(spec.subtitle || "")}</div></div>
      <div class="p-title"><div class="t">${esc(spec.title)}</div>${spec.docNo ? `<div class="n">${esc(spec.docNo)}</div>` : ""}</div>
    </div>
    ${meta}
    <div class="p-body"></div>
    ${spec.stamp ? `<div class="p-stamp">${esc(spec.stamp)}</div>` : ""}
    <div class="p-foot"><span>تاريخ الطباعة: <span class="num">${esc(nowStr())}</span> — طبع بواسطة: ${esc(store.me ? store.me.full_name : "")}</span><span class="p-pageno"></span></div>
  </div>`;
}

function tableHtml(block, continued) {
  const cols = block.columns.map((c) => `<th class="${c.num ? "num" : ""}" style="${c.width ? `width:${c.width}` : ""}">${esc(c.label)}</th>`).join("");
  const title = block.title ? `<div class="p-sec">${esc(block.title)}${continued ? " (تابع)" : ""}</div>` : "";
  return `<div>${title}<table class="p-tbl"><thead><tr>${cols}</tr></thead><tbody></tbody></table></div>`;
}

function rowHtml(block, row) {
  const cls = block.rowClass ? block.rowClass(row) : "";
  return `<tr class="${cls}">${block.columns.map((c) => {
    const raw = typeof c.value === "function" ? c.value(row) : row[c.key];
    const html = c.html ? raw : c.num ? (raw === "" || raw === null || raw === undefined ? "" : n(raw)) : c.ltr ? t(raw) : esc(raw);
    return `<td class="${c.num ? "num" : ""}">${html ?? ""}</td>`;
  }).join("")}</tr>`;
}

function blockHtml(block) {
  if (block.type === "summary") {
    return `<div class="p-sum" style="grid-template-columns:repeat(${Math.min(block.items.length, 4)},1fr)">${block.items.map(([k, v]) => `<div><div class="k">${esc(k)}</div><div class="v">${v}</div></div>`).join("")}</div>`;
  }
  if (block.type === "box") return `<div class="p-box">${block.html}</div>`;
  if (block.type === "sign") return `<div class="p-sign">${block.labels.map((l) => `<div>${esc(l)}</div>`).join("")}</div>`;
  if (block.type === "title") return `<div class="p-sec">${esc(block.text)}</div>`;
  return "";
}

function toEl(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

function rowEl(html) {
  const t = document.createElement("template");
  t.innerHTML = `<table><tbody>${html}</tbody></table>`;
  return t.content.querySelector("tr");
}

/** يبني صفحات HTML من مواصفة المستند بقياس فعلي داخل المتصفح. */
export async function paginate(spec) {
  if (document.fonts && document.fonts.ready) await document.fonts.ready;
  const host = document.createElement("div");
  host.style.cssText = "position:absolute;left:-100000px;top:0;visibility:hidden";
  document.body.appendChild(host);
  const pages = [];
  let body;
  const newPage = () => {
    const sheet = toEl(sheetHtml(spec, pages.length === 0));
    host.appendChild(sheet);
    body = sheet.querySelector(".p-body");
    pages.push(sheet);
  };
  const fits = () => body.scrollHeight <= body.clientHeight + 1;
  newPage();
  for (const block of spec.blocks) {
    if (block.type !== "table") {
      const node = toEl(blockHtml(block));
      body.appendChild(node);
      if (!fits() && body.children.length > 1) {
        body.removeChild(node);
        newPage();
        body.appendChild(node);
      }
      continue;
    }
    let wrap = toEl(tableHtml(block, false));
    body.appendChild(wrap);
    let tbody = wrap.querySelector("tbody");
    const restart = () => {
      newPage();
      wrap = toEl(tableHtml(block, true));
      body.appendChild(wrap);
      tbody = wrap.querySelector("tbody");
    };
    if (!fits() && body.children.length > 1) {
      body.removeChild(wrap);
      restart();
    }
    const rows = block.rows.length ? block.rows.map((r) => rowHtml(block, r))
      : [`<tr><td colspan="${block.columns.length}" style="text-align:center">${esc(block.emptyText || "لا توجد بيانات")}</td></tr>`];
    if (block.totalsRow) rows.push(`<tr class="tot">${block.totalsRow.map((v) => `<td class="${v && v.num ? "num" : ""}">${v ? (v.num ? n(v.text) : esc(v.text)) : ""}</td>`).join("")}</tr>`);
    for (const html of rows) {
      const tr = rowEl(html);
      tbody.appendChild(tr);
      if (!fits()) {
        tbody.removeChild(tr);
        restart();
        tbody.appendChild(tr);
      }
    }
  }
  pages.forEach((p, i) => { p.querySelector(".p-pageno").textContent = `صفحة ${i + 1} من ${pages.length}`; });
  const html = pages.map((p) => p.outerHTML);
  host.remove();
  return html;
}

/** فتح نافذة المعاينة لمواصفة مستند. */
export async function openPreview(spec) {
  const pages = await paginate(spec);
  store.print = { title: spec.title + (spec.docNo ? " " + spec.docNo : ""), pages };
}

export function printPages(pages) {
  const root = document.getElementById("print-root");
  root.innerHTML = pages.join("");
  document.body.classList.add("printing");
  const done = () => {
    document.body.classList.remove("printing");
    root.innerHTML = "";
    window.removeEventListener("afterprint", done);
  };
  window.addEventListener("afterprint", done);
  setTimeout(() => window.print(), 50);
}

export const PrintPreview = {
  name: "PrintPreview",
  setup() {
    const p = computed(() => store.print);
    const onKey = (e) => {
      if (store.print && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault();
        printPages(store.print.pages);
      }
    };
    onMounted(() => document.addEventListener("keydown", onKey));
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey));
    return { p, store, printPages };
  },
  template: `<Modal v-if="p" :title="'معاينة: ' + p.title" size="xwide" @close="store.print = null">
      <template #top>
        <div class="preview-tools">
          <button class="btn btn-primary" @click="printPages(p.pages)" autofocus><Icon name="printer"/> طباعة <span class="kbd">Ctrl+P</span></button>
          <span class="badge neutral">{{ p.pages.length }} {{ p.pages.length === 1 ? 'صفحة' : 'صفحات' }} — A4</span>
          <span class="muted small">لحفظ المستند PDF: اضغط طباعة ثم اختر «حفظ كملف PDF» في نافذة الطباعة.</span>
        </div>
      </template>
      <div class="print-preview" style="margin:-18px -20px">
        <div v-for="(html, i) in p.pages" :key="i" v-html="html"></div>
      </div>
    </Modal>`,
};

// ============================================================================
//  قوالب المستندات (كلها تُبنى من البيانات المحفوظة الفعلية القادمة من الخادم)
// ============================================================================
function unit(m) {
  return m === "gold" ? "جم" : m === "diamond" ? (store.settings.diamond_unit || "قيراط") : (store.settings.wage_unit || "");
}

function docMeta(doc) {
  const meta = [
    ["العميل", esc(doc.account.name)],
    ["رقم الحساب", t(doc.account.account_no)],
    ["التاريخ", t(doc.doc_date)],
    ["عيار العمل", t(doc.working_karat)],
    ["الحالة", doc.status === "cancelled" ? "ملغى" : "مرحّل"],
    ["أدخله", esc(doc.posted_by)],
  ];
  if (doc.doc_type === "return") {
    meta.push(doc.original_doc ? ["الفاتورة الأصلية", t(doc.original_doc.doc_no)] : ["الربط", "غير مرتبط (استثناء)"]);
  }
  if (doc.description) meta.push(["البيان", esc(doc.description)]);
  return meta;
}

export function docSpec(doc) {
  const spec = { title: DOC_LABEL[doc.doc_type], docNo: doc.doc_no, meta: docMeta(doc), blocks: [],
    stamp: doc.status === "cancelled" ? "ملغى" : null, subtitle: "نظام حسابات العملاء — ذهب / ألماس / أجور" };
  const u = { gold: unit("gold"), diamond: unit("diamond"), wage: unit("wage") };
  if (doc.doc_type === "sale" || doc.doc_type === "return") {
    const isRet = doc.doc_type === "return";
    spec.blocks.push({
      type: "table",
      columns: [
        { label: "#", key: "line_no", width: "7mm", ltr: true },
        { label: "رقم التشغيل", key: "run_no", ltr: true },
        { label: `الذهب (${u.gold})`, key: "gold", num: true },
        { label: `الألماس (${u.diamond})`, key: "diamond", num: true },
        { label: "الأجر المعتمد / جم", key: "rate", num: true },
        { label: isRet ? `الأجر المسترد (${u.wage})` : `إجمالي الأجر (${u.wage})`, key: "wage", num: true },
      ],
      rows: doc.lines,
      totalsRow: [{ text: "" }, { text: `الإجمالي (${doc.totals.lines} سطر)` }, { text: doc.totals.gold, num: true },
        { text: doc.totals.diamond, num: true }, { text: "" }, { text: doc.totals.wage, num: true }],
    });
    spec.blocks.push({ type: "summary", items: [
      ["إجمالي وزن الذهب", `${n(doc.totals.gold)} ${esc(u.gold)}`],
      ["إجمالي وزن الألماس", `${n(doc.totals.diamond)} ${esc(u.diamond)}`],
      [isRet ? "إجمالي الأجور المستردة" : "إجمالي الأجور", `${n(doc.totals.wage)} ${esc(u.wage)}`],
      ["عدد الأسطر", t(doc.totals.lines)],
    ] });
    spec.blocks.push({ type: "box", html: `أثر المستند على حساب العميل: ${isRet ? "دائن (تخفيض المستحقات)" : "مدين (زيادة المستحقات)"} — الذهب بعيار العمل ${esc(doc.working_karat)}. إجمالي الأجر = وزن الذهب × الأجر المعتمد لكل جرام.` + (doc.is_unlinked_return ? `<br><b>سبب الاستثناء:</b> ${esc(doc.exception_reason)}` : "") });
  } else if (doc.doc_type === "receipt" || doc.doc_type === "payment") {
    const v = doc.voucher;
    const cols = v.material === "gold"
      ? [{ label: "نوع المادة", key: "m" }, { label: "الوزن الفعلي (جم)", key: "actual", num: true }, { label: "العيار الفعلي", key: "karat", ltr: true },
        { label: "عيار العمل", key: "working_karat", ltr: true }, { label: "الوزن المكافئ (جم)", key: "equivalent", num: true }]
      : [{ label: "نوع المادة", key: "m" }, { label: v.material === "diamond" ? `الوزن (${u.diamond})` : `المبلغ (${u.wage})`, key: "actual", num: true }];
    spec.blocks.push({ type: "table", columns: cols, rows: [{ ...v, m: MATERIAL_LABEL[v.material], karat: String(v.karat ?? ""), working_karat: String(v.working_karat ?? "") }] });
    const eff = doc.effects[v.material];
    const side = doc.doc_type === "receipt" ? "دائن — يخفض المستحق على العميل" : "مدين — يزيد المستحق على العميل";
    spec.blocks.push({ type: "box", html: `أثر السند على حساب ${esc(MATERIAL_LABEL[v.material])}: ${n(doc.doc_type === "receipt" ? eff.credit : eff.debit)} ${esc(u[v.material])} (${side}).` +
      (v.material === "gold" ? `<br>الوزن المكافئ = الوزن الفعلي × العيار الفعلي ÷ عيار العمل = ${n(v.actual)} × ${t(v.karat)} ÷ ${t(v.working_karat)} = ${n(v.equivalent)}` : "") });
    spec.blocks.push({ type: "sign", labels: [doc.doc_type === "receipt" ? "المستلم (المحاسب)" : "المسلِّم (المحاسب)", "العميل", "الاعتماد"] });
  } else if (doc.doc_type === "opening") {
    spec.blocks.push({
      type: "table",
      columns: [
        { label: "#", key: "line_no", width: "7mm", ltr: true },
        { label: "نوع الرصيد", value: (r) => MATERIAL_LABEL[r.material] },
        { label: "الاتجاه", value: (r) => DIR_AR[r.direction] },
        { label: "الوزن / المبلغ", key: "actual", num: true },
        { label: "العيار", value: (r) => r.karat ?? "—" },
        { label: "عيار العمل", value: (r) => r.working_karat ?? "—" },
        { label: "المعتمد في الرصيد", key: "equivalent", num: true },
        { label: "البيان", key: "description" },
        { label: "ملاحظات", key: "note" },
      ],
      rows: doc.lines,
    });
    spec.blocks.push({ type: "box", html: "الرصيد الافتتاحي مستند مستقل لا يُعد بيعاً ولا قبضاً ولا صرفاً. الذهب يُعتمد بوزنه المكافئ بعيار العمل." });
  }
  if (doc.notes) spec.blocks.push({ type: "box", html: `<b>ملاحظات:</b> ${esc(doc.notes)}` });
  if (doc.status === "cancelled") spec.blocks.push({ type: "box", html: `<b>أُلغي بتاريخ</b> ${t(fmtDateTime(doc.cancelled_at))} بواسطة ${esc(doc.cancelled_by)} — السبب: ${esc(doc.cancel_reason)}` });
  if (doc.doc_type === "sale" || doc.doc_type === "return") spec.blocks.push({ type: "sign", labels: ["المحاسب", "العميل / المستلم", "الاعتماد"] });
  return spec;
}

export function statementSpec(st, materialLabel) {
  const m = st.material;
  const u = unit(m);
  const rows = [{ date: st.date_from || "", doc_no: "", kind: "رصيد افتتاحي للفترة", text: st.date_from ? `الرصيد قبل ${st.date_from}` : "لا رصيد سابق", run_no: "", debit: "", credit: "", balance: st.opening, notes: "", _open: true }, ...st.rows];
  return {
    title: `كشف حساب ${materialLabel}`, docNo: "", subtitle: `الوحدة: ${u}${m === "gold" ? " — بعيار العمل المعتمد" : ""}`,
    meta: [
      ["العميل", esc(st.account.name)], ["رقم الحساب", t(st.account.account_no)],
      ["الفترة", `${st.date_from ? t(st.date_from) : "من البداية"} — ${st.date_to ? t(st.date_to) : "حتى الآن"}`],
      ["نوع الكشف", esc(materialLabel)], ["الرصيد الافتتاحي", balTxt(st.opening)], ["الرصيد الختامي", balTxt(st.closing)],
    ],
    blocks: [
      {
        type: "table",
        columns: [
          { label: "التاريخ", key: "date", ltr: true, width: "19mm" },
          { label: "رقم المستند", key: "doc_no", ltr: true },
          { label: "نوع الحركة", key: "kind" },
          { label: "البيان", key: "text" },
          { label: "رقم التشغيل", key: "run_no", ltr: true },
          { label: "مدين", key: "debit", num: true },
          { label: "دائن", key: "credit", num: true },
          { label: "الرصيد", value: (r) => balTxt(r.balance), html: true },
          { label: "ملاحظات", key: "notes" },
        ],
        rows,
        rowClass: (r) => (r.cancelled && !r.is_reversal ? "cx" : ""),
        totalsRow: [{ text: "" }, { text: "" }, { text: "الإجمالي" }, { text: `${st.totals.count} حركة` }, { text: "" },
          { text: st.totals.debit, num: true }, { text: st.totals.credit, num: true }, { text: `${group(st.closing.value)} ${DIR_AR[st.closing.direction]}` }, { text: "" }],
      },
      { type: "summary", items: [["الرصيد الافتتاحي", balTxt(st.opening)], ["إجمالي المدين", n(st.totals.debit)], ["إجمالي الدائن", n(st.totals.credit)], ["الرصيد الختامي", balTxt(st.closing)]] },
      { type: "box", html: "الرصيد الختامي = الرصيد الافتتاحي للفترة + إجمالي المدين − إجمالي الدائن. مدين: مستحق على العميل — دائن: مستحق للعميل." + (st.mixed_karats ? `<br><b>تنبيه:</b> الكشف يتضمن حركات بعيارات عمل مختلفة (${st.ref_karats.join("، ")}).` : "") },
    ],
  };
}

export function analysisSpec(an) {
  const u = { gold: unit("gold"), diamond: unit("diamond"), wage: unit("wage") };
  const period = `${an.date_from ? t(an.date_from) : "من البداية"} — ${an.date_to ? t(an.date_to) : "حتى الآن"}`;
  return {
    title: "تقرير تحليل حركة العميل", docNo: "", subtitle: "المبيعات — المرتجعات — المباع الصافي — السداد",
    meta: [["العميل", esc(an.account.name)], ["رقم الحساب", t(an.account.account_no)], ["الفترة", period],
      ["رصيد الذهب الحالي", balTxt(an.balances.gold)], ["رصيد الألماس الحالي", balTxt(an.balances.diamond)], ["رصيد الأجور الحالي", balTxt(an.balances.wage)]],
    blocks: [
      { type: "table", title: "المبيعات", columns: [
        { label: "التاريخ", key: "date", ltr: true }, { label: "رقم الفاتورة", key: "doc_no", ltr: true }, { label: "رقم التشغيل", key: "run_no", ltr: true },
        { label: `الذهب (${u.gold})`, key: "gold", num: true }, { label: `الألماس (${u.diamond})`, key: "diamond", num: true },
        { label: "الأجر المعتمد", key: "rate", num: true }, { label: `إجمالي الأجر (${u.wage})`, key: "wage", num: true }],
        rows: an.sales.rows, emptyText: "لا مبيعات في الفترة",
        totalsRow: [{ text: "الإجمالي" }, { text: `${an.sales.count} سطر` }, { text: "" }, { text: an.sales.totals.gold, num: true }, { text: an.sales.totals.diamond, num: true }, { text: "" }, { text: an.sales.totals.wage, num: true }] },
      { type: "table", title: "المرتجعات", columns: [
        { label: "التاريخ", key: "date", ltr: true }, { label: "رقم المرتجع", key: "doc_no", ltr: true }, { label: "الفاتورة الأصلية", value: (r) => r.original_doc_no || "غير مرتبط" },
        { label: "رقم التشغيل", key: "run_no", ltr: true }, { label: "الذهب المرتجع", key: "gold", num: true }, { label: "الألماس المرتجع", key: "diamond", num: true },
        { label: "الأجر المسترد", key: "wage", num: true }, { label: "البيان", key: "text" }],
        rows: an.returns.rows, emptyText: "لا مرتجعات في الفترة",
        totalsRow: [{ text: "الإجمالي" }, { text: `${an.returns.count} سطر` }, { text: "" }, { text: "" }, { text: an.returns.totals.gold, num: true }, { text: an.returns.totals.diamond, num: true }, { text: an.returns.totals.wage, num: true }, { text: "" }] },
      { type: "table", title: "المباع الصافي", columns: [
        { label: "الفاتورة", key: "doc_no", ltr: true }, { label: "التاريخ", key: "doc_date", ltr: true },
        { label: "ذهب مباع", value: (r) => r.sold.gold, num: true }, { label: "ذهب مرتجع", value: (r) => r.returned.gold, num: true }, { label: "صافي الذهب", value: (r) => r.net.gold.signed, num: true },
        { label: "صافي الألماس", value: (r) => r.net.diamond.signed, num: true }, { label: "صافي الأجور", value: (r) => r.net.wage.signed, num: true },
        { label: "ملاحظة", value: (r) => (r.kind === "unlinked" ? "مرتجع غير مرتبط (استثناء)" : r.invoice_outside_period ? "فاتورة خارج الفترة" : "") }],
        rows: an.net.rows, emptyText: "لا حركة",
        totalsRow: [{ text: "الصافي" }, { text: "" }, { text: an.sales.totals.gold, num: true }, { text: an.returns.totals.gold, num: true }, { text: an.net.totals.gold.signed, num: true }, { text: an.net.totals.diamond.signed, num: true }, { text: an.net.totals.wage.signed, num: true }, { text: "" }] },
      { type: "table", title: "السداد (قبض وصرف)", columns: [
        { label: "التاريخ", key: "date", ltr: true }, { label: "رقم السند", key: "doc_no", ltr: true }, { label: "الحركة", key: "kind" },
        { label: "المادة", value: (r) => MATERIAL_LABEL[r.material] }, { label: "الوزن الفعلي / المبلغ", key: "actual", num: true },
        { label: "العيار", value: (r) => r.karat ?? "—" }, { label: "عيار العمل", value: (r) => r.working_karat ?? "—" },
        { label: "المكافئ", key: "equivalent", num: true }, { label: "البيان", key: "text" }],
        rows: an.payments.rows, emptyText: "لا سندات في الفترة" },
      { type: "summary", items: [
        [`ذهب: قبض / صرف / صافي (${u.gold})`, `${n(an.payments.totals.gold.in)} / ${n(an.payments.totals.gold.out)} / ${n(an.payments.totals.gold.net)}`],
        [`ألماس (${u.diamond})`, `${n(an.payments.totals.diamond.in)} / ${n(an.payments.totals.diamond.out)} / ${n(an.payments.totals.diamond.net)}`],
        [`أجور (${u.wage})`, `${n(an.payments.totals.wage.in)} / ${n(an.payments.totals.wage.out)} / ${n(an.payments.totals.wage.net)}`]] },
      { type: "box", html: "الأوزان والأجور منفصلة ولا تُجمع معاً. صافي المباع = المبيعات − المرتجعات خلال الفترة. قبض الذهب أو الألماس لا يُعد سداداً للأجور." + (an.cancelled_count ? `<br>مستندات ملغاة في الفترة (مستبعدة): ${an.cancelled_count}` : "") },
    ],
  };
}

export function accountSpec(sum) {
  const a = sum.account;
  return {
    title: "بطاقة حساب عميل", docNo: a.account_no, subtitle: "بيانات الحساب وأرصدته",
    meta: [["اسم العميل", esc(a.name)], ["رقم الحساب", t(a.account_no)], ["الجوال", t(a.phone || "—")],
      ["الأجر الافتراضي / جم", n(a.wage_rate)], ["الحالة", a.is_active ? "نشط" : "موقوف"], ["آخر حركة", t(sum.last_movement || "—")]],
    blocks: [
      { type: "table", title: "الأرصدة", columns: [{ label: "النوع", key: "k" }, { label: "مدين", key: "d", num: true }, { label: "دائن", key: "c", num: true }, { label: "الرصيد", key: "b", html: true }, { label: "الوحدة", key: "u" }],
        rows: ["gold", "diamond", "wage"].map((m) => ({ k: MATERIAL_LABEL[m], d: sum.sections[m].debit, c: sum.sections[m].credit, b: balTxt(sum.sections[m].balance), u: unit(m) })) },
      { type: "table", title: "آخر المستندات", columns: [{ label: "التاريخ", key: "doc_date", ltr: true }, { label: "رقم المستند", key: "doc_no", ltr: true }, { label: "النوع", key: "type_label" }, { label: "البيان", key: "description" }, { label: "الحالة", value: (r) => (r.status === "cancelled" ? "ملغى" : "مرحّل") }],
        rows: sum.recent, emptyText: "لا مستندات" },
      ...(a.notes ? [{ type: "box", html: `<b>ملاحظات:</b> ${esc(a.notes)}` }] : []),
    ],
  };
}

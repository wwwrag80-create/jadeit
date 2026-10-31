"""المستندات: الترحيل، المعاينة قبل الترحيل، التعديل، الإلغاء، البحث.

مصدر واحد للمنطق المحاسبي: الدالة build_entries() تحوّل المستند إلى قيود
في دفتر الحركات، ويستخدمها الترحيل والتعديل وفحص السلامة معاً، فيستحيل أن
تختلف المعالجة بين شاشة وأخرى.

اتجاه القيود (من منظور حساب العميل):
    فاتورة مبيعات   → مدين  (تزيد مستحقات الذهب/الألماس/الأجور على العميل)
    مرتجع مبيعات   → دائن  (تخفض المستحقات المقابلة)
    سند قبض        → دائن  (استلام ذهب/ألماس/أجور من العميل يخفض المستحق)
    سند صرف        → مدين  (تسليم ذهب/ألماس للعميل يزيد المستحق)
    رصيد افتتاحي   → حسب الاتجاه المحدد لكل سطر
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .. import fixed as F
from ..db import next_seq, peek_seq, utcnow
from ..errors import Conflict, NotFound, ValidationError
from .common import (DOC_PREFIX, DOC_TYPES, MATERIALS, Actor, audit, clean_line, clean_text,
                     client_token, name_key, parse_date, working_karat)

TRADE_TYPES = ("sale", "return")
VOUCHER_TYPES = ("receipt", "payment")
SIGN = {"sale": 1, "return": -1, "receipt": -1, "payment": 1}  # +1 مدين، −1 دائن
MAX_LINES = 2000


# ============================================================================
#  أدوات
# ============================================================================
def doc_no_for(doc_type: str, seq: int) -> str:
    return f"{DOC_PREFIX[doc_type]}-{seq:06d}"


def next_doc_no(db, doc_type: str) -> str:
    if doc_type not in DOC_TYPES:
        raise ValidationError("نوع مستند غير معروف")
    with db.read() as c:
        return doc_no_for(doc_type, peek_seq(c, f"doc:{doc_type}"))


def _perm_for(doc_type: str) -> str:
    return "opening.manage" if doc_type == "opening" else "docs.post"


def _num(value, dp, label, allow_zero=True):
    try:
        return F.parse(value, dp, label, allow_zero=allow_zero)
    except F.FixedError as e:
        raise ValidationError(str(e))


def _karat(value, label="العيار"):
    try:
        k = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError(f"{label}: اختر العيار (18، 21، 22، 24)")
    if k not in F.KARATS:
        raise ValidationError(f"{label}: العيار يجب أن يكون 18 أو 21 أو 22 أو 24")
    return k


@dataclass
class Prepared:
    doc_type: str
    account: dict
    doc_date: str
    working_karat: int
    description: str = ""
    notes: str = ""
    original_doc_id: int | None = None
    is_unlinked_return: bool = False
    exception_reason: str = ""
    lines: list = field(default_factory=list)       # أسطر المبيعات/المرتجعات أو الافتتاحي
    voucher: dict | None = None
    warnings: list = field(default_factory=list)


# ============================================================================
#  توليد القيود — مصدر الحقيقة الوحيد لاتجاه الحركة
# ============================================================================
def build_entries(doc_type: str, working_karat_: int, lines=None, voucher=None):
    """يعيد قائمة القيود المتوقعة (بدون معرفات) لمستند معيّن."""
    entries = []

    def add(material, signed, line_no=0, run_no="", source=None, ref=None):
        if signed == 0:
            return
        entries.append({
            "material": material,
            "debit_e4": signed if signed > 0 else 0,
            "credit_e4": -signed if signed < 0 else 0,
            "ref_karat": ref if material == "gold" else None,
            "line_no": line_no,
            "run_no": run_no,
            "source_line_id": source,
        })

    if doc_type in TRADE_TYPES:
        s = SIGN[doc_type]
        for ln in lines:
            add("gold", s * ln["gold_e4"], ln["line_no"], ln["run_no"], ln.get("id"), working_karat_)
            add("diamond", s * ln["diamond_e4"], ln["line_no"], ln["run_no"], ln.get("id"))
            add("wage", s * ln["wage_e4"], ln["line_no"], ln["run_no"], ln.get("id"))
    elif doc_type in VOUCHER_TYPES:
        s = SIGN[doc_type]
        add(voucher["material"], s * voucher["equivalent_e4"], 1, "", None, voucher.get("working_karat"))
    elif doc_type == "opening":
        for ln in lines:
            s = 1 if ln["direction"] == "debit" else -1
            add(ln["material"], s * ln["equivalent_e4"], ln["line_no"], "", ln.get("id"), ln.get("working_karat"))
    return entries


def _effects(entries) -> dict:
    out = {m: {"debit_e4": 0, "credit_e4": 0} for m in MATERIALS}
    for e in entries:
        out[e["material"]]["debit_e4"] += e["debit_e4"]
        out[e["material"]]["credit_e4"] += e["credit_e4"]
    return out


def _fmt_effects(eff: dict) -> dict:
    res = {}
    for m, v in eff.items():
        dp = F.MATERIAL_DP[m]
        net = v["debit_e4"] - v["credit_e4"]
        res[m] = {"debit": F.fmt(v["debit_e4"], dp), "credit": F.fmt(v["credit_e4"], dp),
                  "net": F.fmt(net, dp), "net_e4": net}
    return res


# ============================================================================
#  الكميات المرتجعة لكل سطر بيع
# ============================================================================
def returned_by_line(c, line_ids, exclude_doc_id=None) -> dict:
    """مجموع ما أُرجع فعلاً (مرتجعات مرحّلة غير ملغاة) لكل سطر بيع."""
    if not line_ids:
        return {}
    marks = ",".join("?" * len(line_ids))
    args = list(line_ids)
    sql = f"""SELECT tl.original_line_id AS lid, SUM(tl.gold_e4) g, SUM(tl.diamond_e4) d, SUM(tl.wage_e4) w
              FROM trade_lines tl JOIN documents d ON d.id = tl.doc_id
              WHERE tl.original_line_id IN ({marks}) AND d.status = 'posted' AND d.doc_type = 'return'"""
    if exclude_doc_id:
        sql += " AND d.id <> ?"
        args.append(exclude_doc_id)
    sql += " GROUP BY tl.original_line_id"
    return {r["lid"]: {"gold_e4": r["g"] or 0, "diamond_e4": r["d"] or 0, "wage_e4": r["w"] or 0}
            for r in c.execute(sql, args)}


# ============================================================================
#  التحضير والتحقق (مشترك بين المعاينة والترحيل والتعديل)
# ============================================================================
def _load_account(c, account_id, require_active=True):
    try:
        account_id = int(account_id)
    except (TypeError, ValueError):
        raise ValidationError("اختر العميل أولاً", {"field": "account_id"})
    row = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if row is None:
        raise ValidationError("العميل المحدد غير موجود", {"field": "account_id"})
    if require_active and not row["is_active"]:
        raise ValidationError(f"الحساب «{row['name']}» موقوف، لا يمكن ترحيل حركات جديدة عليه",
                              {"field": "account_id"})
    return dict(row)


def _prepare(c, actor: Actor, data: dict, existing: dict | None = None) -> Prepared:
    doc_type = existing["doc_type"] if existing else str(data.get("doc_type") or "")
    if doc_type not in DOC_TYPES:
        raise ValidationError("اختر نوع العملية")
    if existing:
        if data.get("account_id") not in (None, "") and int(data["account_id"]) != existing["account_id"]:
            raise ValidationError("لا يمكن تغيير العميل في مستند مرحّل. ألغِ المستند وأنشئ مستنداً جديداً")
        account = _load_account(c, existing["account_id"], require_active=False)
        wk = existing["working_karat"]
    else:
        account = _load_account(c, data.get("account_id"))
        wk = working_karat(c)
    doc_date = parse_date(data.get("doc_date"), "تاريخ العملية")
    p = Prepared(
        doc_type=doc_type,
        account=account,
        doc_date=doc_date,
        working_karat=wk,
        description=clean_line(data.get("description"), 300),
        notes=clean_text(data.get("notes"), 1000),
    )
    if doc_date > date.today().isoformat():
        p.warnings.append("تاريخ العملية في المستقبل")

    if doc_type in TRADE_TYPES:
        _prepare_trade(c, actor, data, p, existing)
    elif doc_type in VOUCHER_TYPES:
        _prepare_voucher(data, p, existing)
    else:
        _prepare_opening(c, data, p, existing)

    if doc_type != "opening":
        ob = c.execute("""SELECT doc_date FROM documents WHERE account_id = ? AND doc_type = 'opening'
                          AND status = 'posted'""", (account["id"],)).fetchone()
        if ob and doc_date < ob["doc_date"]:
            p.warnings.append(f"تاريخ العملية يسبق تاريخ الرصيد الافتتاحي للحساب ({ob['doc_date']})")
    return p


def _prepare_trade(c, actor, data, p: Prepared, existing):
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError("المستند لا يحتوي على أي سطر. أضف سطراً واحداً على الأقل")
    if len(raw_lines) > MAX_LINES:
        raise ValidationError(f"الحد الأقصى {MAX_LINES} سطر في المستند الواحد")

    default_rate = p.account["wage_rate_e4"]
    can_override = actor.can("docs.rate_override")
    errors = {}
    existing_lines = {}
    if existing:
        for r in c.execute("SELECT * FROM trade_lines WHERE doc_id = ?", (existing["id"],)):
            existing_lines[r["id"]] = dict(r)

    # ---------------- المرتجع: مرتبط بفاتورة أم استثناء
    original_lines = {}
    if p.doc_type == "return":
        unlinked = bool(existing["is_unlinked_return"]) if existing else bool(data.get("unlinked"))
        if unlinked:
            actor.require("docs.unlinked_return", "المرتجع غير المرتبط بفاتورة يحتاج صلاحية خاصة من الإدارة")
            reason = clean_line(data.get("exception_reason"), 300)
            if len(reason) < 5:
                raise ValidationError("اكتب سبب الاستثناء للمرتجع غير المرتبط بفاتورة (5 أحرف على الأقل)",
                                      {"field": "exception_reason"})
            p.is_unlinked_return = True
            p.exception_reason = reason
            p.warnings.append("مرتجع غير مرتبط بفاتورة أصلية (استثناء)")
        else:
            orig_id = existing["original_doc_id"] if existing else data.get("original_doc_id")
            if orig_id in (None, ""):
                raise ValidationError("اختر الفاتورة الأصلية للمرتجع", {"field": "original_doc_id"})
            if existing and data.get("original_doc_id") not in (None, "") \
                    and int(data["original_doc_id"]) != existing["original_doc_id"]:
                raise ValidationError("لا يمكن تغيير الفاتورة الأصلية لمرتجع مرحّل. ألغِه وأنشئ مرتجعاً جديداً")
            orig = c.execute("SELECT * FROM documents WHERE id = ?", (int(orig_id),)).fetchone()
            if orig is None or orig["doc_type"] != "sale":
                raise ValidationError("الفاتورة الأصلية غير موجودة", {"field": "original_doc_id"})
            if orig["account_id"] != p.account["id"]:
                raise ValidationError("الفاتورة الأصلية تخص عميلاً آخر", {"field": "original_doc_id"})
            if orig["status"] != "posted":
                raise ValidationError("الفاتورة الأصلية ملغاة، لا يمكن الإرجاع عليها", {"field": "original_doc_id"})
            if p.doc_date < orig["doc_date"]:
                raise ValidationError(f"تاريخ المرتجع يسبق تاريخ الفاتورة الأصلية ({orig['doc_date']})",
                                      {"field": "doc_date"})
            p.original_doc_id = orig["id"]
            for r in c.execute("SELECT * FROM trade_lines WHERE doc_id = ?", (orig["id"],)):
                original_lines[r["id"]] = dict(r)

    returned = {}
    if p.doc_type == "return" and original_lines:
        returned = returned_by_line(c, list(original_lines), exclude_doc_id=existing["id"] if existing else None)
    # للمبيعات المرحّلة: ما أُرجع من كل سطر (لمنع تعديل يجعل المرتجع أكبر من المباع)
    sale_returned = {}
    if p.doc_type == "sale" and existing_lines:
        sale_returned = returned_by_line(c, list(existing_lines))

    seen_runs = {}
    seen_orig = set()
    kept_ids = set()
    for idx, raw in enumerate(raw_lines):
        n = idx + 1
        try:
            if not isinstance(raw, dict):
                raise ValidationError("بيانات السطر غير صالحة")
            line_id = raw.get("id")
            old = None
            if line_id not in (None, ""):
                line_id = int(line_id)
                old = existing_lines.get(line_id)
                if old is None:
                    raise ValidationError("السطر لا ينتمي لهذا المستند")
                kept_ids.add(line_id)
            gold = _num(raw.get("gold"), F.DP_GOLD, "وزن الذهب")
            diamond = _num(raw.get("diamond"), F.DP_DIAMOND, "وزن الألماس")
            if gold == 0 and diamond == 0:
                raise ValidationError("أدخل وزن الذهب أو وزن الألماس")
            orig_line = None
            if p.doc_type == "return" and not p.is_unlinked_return:
                olid = raw.get("original_line_id")
                if olid in (None, ""):
                    raise ValidationError("اختر سطر الفاتورة الأصلية المرتجع منه")
                orig_line = original_lines.get(int(olid))
                if orig_line is None:
                    raise ValidationError("سطر الفاتورة الأصلية غير موجود في هذه الفاتورة")
                if orig_line["id"] in seen_orig:
                    raise ValidationError("سطر الفاتورة الأصلية مكرر في هذا المرتجع")
                seen_orig.add(orig_line["id"])
                run_no = orig_line["run_no"]
                rate = orig_line["rate_e4"]
                done = returned.get(orig_line["id"], {"gold_e4": 0, "diamond_e4": 0, "wage_e4": 0})
                rem_gold = orig_line["gold_e4"] - done["gold_e4"]
                rem_dia = orig_line["diamond_e4"] - done["diamond_e4"]
                rem_wage = orig_line["wage_e4"] - done["wage_e4"]
                if gold > rem_gold:
                    raise ValidationError(
                        f"الذهب المرتجع ({F.fmt(gold, 4)}) أكبر من المتبقي القابل للإرجاع ({F.fmt(rem_gold, 4)})")
                if diamond > rem_dia:
                    raise ValidationError(
                        f"الألماس المرتجع ({F.fmt(diamond, 3)}) أكبر من المتبقي القابل للإرجاع ({F.fmt(rem_dia, 3)})")
                # الأجر المسترد بأجر الفاتورة الأصلية؛ وإن اكتمل إرجاع ذهب السطر يُسترد باقي أجره بالضبط
                wage = rem_wage if (gold > 0 and gold == rem_gold) else min(F.wage_total(gold, rate), rem_wage)
                overridden = False
            else:
                run_no = clean_line(raw.get("run_no"), 60)
                if run_no:
                    key = run_no.casefold()
                    if key in seen_runs:
                        raise ValidationError(f"رقم التشغيل «{run_no}» مكرر في السطر {seen_runs[key]}")
                    seen_runs[key] = n
                base_rate = old["rate_e4"] if old else default_rate
                if raw.get("rate") in (None, ""):
                    rate = base_rate
                else:
                    rate = _num(raw.get("rate"), F.DP_RATE, "الأجر المعتمد")
                if rate != base_rate and not can_override:
                    raise ValidationError("لا تملك صلاحية تعديل الأجر المعتمد للسطر")
                wage = F.wage_total(gold, rate)
                overridden = rate != default_rate if not old else (old["rate_overridden"] or rate != old["rate_e4"])
                if old and p.doc_type == "sale":
                    done = sale_returned.get(old["id"])
                    if done:
                        if rate != old["rate_e4"]:
                            raise ValidationError("لا يمكن تغيير أجر سطر عليه مرتجعات مرحّلة")
                        if gold < done["gold_e4"] or diamond < done["diamond_e4"] or wage < done["wage_e4"]:
                            raise ValidationError(
                                "لا يمكن إنقاص السطر إلى أقل مما أُرجع منه فعلاً "
                                f"(ذهب مرتجع {F.fmt(done['gold_e4'], 4)}، ألماس مرتجع {F.fmt(done['diamond_e4'], 3)})")
            p.lines.append({
                "id": line_id if old else None,
                "line_no": n,
                "run_no": run_no,
                "gold_e4": gold,
                "diamond_e4": diamond,
                "rate_e4": rate,
                "wage_e4": wage,
                "rate_overridden": bool(overridden),
                "original_line_id": orig_line["id"] if orig_line else None,
            })
        except ValidationError as e:
            errors[idx] = e.message
    if errors:
        first = min(errors)
        raise ValidationError(f"السطر {first + 1}: {errors[first]}",
                              {"line_errors": {str(k): v for k, v in errors.items()}})

    # أسطر محذوفة من فاتورة مرحّلة: لا يجوز حذف سطر عليه مرتجعات
    if existing and p.doc_type == "sale":
        for lid in existing_lines:
            if lid not in kept_ids and lid in sale_returned:
                raise ValidationError(
                    f"لا يمكن حذف السطر ذي رقم التشغيل «{existing_lines[lid]['run_no']}» لأن عليه مرتجعات مرحّلة")

    # تحذير: رقم تشغيل سبق بيعه في فاتورة أخرى
    if p.doc_type == "sale":
        runs = [ln["run_no"] for ln in p.lines if ln["run_no"]]
        if runs:
            marks = ",".join("?" * len(runs))
            args = runs + [existing["id"] if existing else -1]
            dup = c.execute(
                f"""SELECT tl.run_no, d.doc_no FROM trade_lines tl JOIN documents d ON d.id = tl.doc_id
                    WHERE tl.run_no IN ({marks}) AND d.doc_type = 'sale' AND d.status = 'posted' AND d.id <> ?
                    LIMIT 5""", args).fetchall()
            for r in dup:
                p.warnings.append(f"رقم التشغيل «{r['run_no']}» مسجّل سابقاً في الفاتورة {r['doc_no']}")
        if any(ln["rate_overridden"] for ln in p.lines):
            p.warnings.append("بعض الأسطر بأجر مختلف عن الأجر الافتراضي للعميل")


def _prepare_voucher(data, p: Prepared, existing):
    material = str(data.get("material") or "")
    if material not in MATERIALS:
        raise ValidationError("اختر نوع المادة (ذهب / ألماس / أجور)", {"field": "material"})
    if material == "gold":
        actual = _num(data.get("actual"), F.DP_GOLD, "الوزن الفعلي", allow_zero=False)
        karat = _karat(data.get("karat"), "عيار الذهب")
        wk = p.working_karat
        eq = F.equivalent(actual, karat, wk)
        if eq <= 0:
            raise ValidationError("الوزن المكافئ يساوي صفراً بعد التقريب، الوزن صغير جداً")
        p.voucher = {"material": "gold", "actual_e4": actual, "actual_karat": karat,
                     "working_karat": wk, "equivalent_e4": eq}
    elif material == "diamond":
        w = _num(data.get("actual"), F.DP_DIAMOND, "وزن الألماس", allow_zero=False)
        p.voucher = {"material": "diamond", "actual_e4": w, "actual_karat": None,
                     "working_karat": None, "equivalent_e4": w}
    else:
        amount = _num(data.get("actual"), F.DP_WAGE, "مبلغ الأجور", allow_zero=False)
        p.voucher = {"material": "wage", "actual_e4": amount, "actual_karat": None,
                     "working_karat": None, "equivalent_e4": amount}
    if not p.description:
        p.description = _auto_voucher_description(p.doc_type, p.voucher)


def _auto_voucher_description(doc_type, v):
    verb = "قبض" if doc_type == "receipt" else "صرف"
    if v["material"] == "gold":
        return f"{verb} ذهب عيار {v['actual_karat']}"
    if v["material"] == "diamond":
        return f"{verb} ألماس"
    return "سداد أجور" if doc_type == "receipt" else "صرف أجور (رد مبلغ)"


def _prepare_opening(c, data, p: Prepared, existing):
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValidationError("أضف سطراً واحداً على الأقل في الرصيد الافتتاحي")
    if len(raw_lines) > 50:
        raise ValidationError("عدد أسطر الرصيد الافتتاحي كبير جداً")
    dup = c.execute(
        """SELECT doc_no FROM documents WHERE account_id = ? AND doc_type = 'opening' AND status = 'posted'
           AND id <> ?""", (p.account["id"], existing["id"] if existing else -1)).fetchone()
    if dup:
        raise Conflict(
            f"يوجد رصيد افتتاحي مرحّل لهذا الحساب ({dup['doc_no']}). عدّله بدلاً من تسجيل رصيد جديد",
            code="duplicate_opening")
    errors = {}
    for idx, raw in enumerate(raw_lines):
        try:
            if not isinstance(raw, dict):
                raise ValidationError("بيانات السطر غير صالحة")
            material = str(raw.get("material") or "")
            if material not in MATERIALS:
                raise ValidationError("اختر نوع الرصيد")
            direction = str(raw.get("direction") or "")
            if direction not in ("debit", "credit"):
                raise ValidationError("حدد اتجاه الرصيد (مدين أو دائن)")
            if material == "gold":
                actual = _num(raw.get("actual"), F.DP_GOLD, "الوزن الفعلي", allow_zero=False)
                karat = _karat(raw.get("karat"), "عيار الذهب")
                wk = p.working_karat
                eq = F.equivalent(actual, karat, wk)
            else:
                dp = F.DP_DIAMOND if material == "diamond" else F.DP_WAGE
                label = "وزن الألماس" if material == "diamond" else "مبلغ الأجور"
                actual = _num(raw.get("actual"), dp, label, allow_zero=False)
                karat = wk = None
                eq = actual
            p.lines.append({
                "id": None,
                "line_no": idx + 1,
                "material": material,
                "direction": direction,
                "actual_e4": actual,
                "actual_karat": karat,
                "working_karat": wk,
                "equivalent_e4": eq,
                "description": clean_line(raw.get("description"), 300),
                "note": clean_line(raw.get("note"), 300),
            })
        except ValidationError as e:
            errors[idx] = e.message
    if errors:
        first = min(errors)
        raise ValidationError(f"السطر {first + 1}: {errors[first]}",
                              {"line_errors": {str(k): v for k, v in errors.items()}})
    if not p.description:
        p.description = "رصيد افتتاحي"


# ============================================================================
#  الحفظ
# ============================================================================
def _insert_lines_and_entries(c, doc_id: int, p: Prepared, now: str):
    if p.doc_type in TRADE_TYPES:
        for ln in p.lines:
            if ln.get("id"):
                continue
            cur = c.execute(
                """INSERT INTO trade_lines(doc_id, line_no, run_no, gold_e4, diamond_e4, rate_e4, wage_e4,
                                           rate_overridden, original_line_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, ln["line_no"], ln["run_no"], ln["gold_e4"], ln["diamond_e4"], ln["rate_e4"],
                 ln["wage_e4"], int(ln["rate_overridden"]), ln["original_line_id"]),
            )
            ln["id"] = cur.lastrowid
    elif p.doc_type in VOUCHER_TYPES:
        v = p.voucher
        c.execute(
            """INSERT INTO voucher_details(doc_id, material, actual_e4, actual_karat, working_karat, equivalent_e4)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (doc_id, v["material"], v["actual_e4"], v["actual_karat"], v["working_karat"], v["equivalent_e4"]),
        )
    else:
        for ln in p.lines:
            cur = c.execute(
                """INSERT INTO opening_lines(doc_id, line_no, material, direction, actual_e4, actual_karat,
                                             working_karat, equivalent_e4, description, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (doc_id, ln["line_no"], ln["material"], ln["direction"], ln["actual_e4"], ln["actual_karat"],
                 ln["working_karat"], ln["equivalent_e4"], ln["description"], ln["note"]),
            )
            ln["id"] = cur.lastrowid

    for e in build_entries(p.doc_type, p.working_karat, p.lines, p.voucher):
        c.execute(
            """INSERT INTO ledger_entries(doc_id, account_id, entry_date, material, debit_e4, credit_e4,
                                          ref_karat, line_no, source_line_id, run_no, is_reversal, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (doc_id, p.account["id"], p.doc_date, e["material"], e["debit_e4"], e["credit_e4"], e["ref_karat"],
             e["line_no"], e["source_line_id"], e["run_no"], now),
        )


def preview_document(db, actor: Actor, data: dict, doc_id: int | None = None) -> dict:
    """تحقق كامل وحساب نهائي دون حفظ: يعرض الأسطر المحسوبة والأثر على الأرصدة قبل/بعد."""
    with db.read() as c:
        existing = None
        if doc_id:
            existing = _load_doc_row(c, doc_id)
            actor.require("docs.edit")
        else:
            actor.require(_perm_for(str(data.get("doc_type") or "")))
        p = _prepare(c, actor, data, existing)
        entries = build_entries(p.doc_type, p.working_karat, p.lines, p.voucher)
        eff = _effects(entries)
        if existing:
            old_eff = _effects([dict(r) for r in c.execute(
                "SELECT material, debit_e4, credit_e4 FROM ledger_entries WHERE doc_id = ?", (existing["id"],))])
            for m in eff:
                eff[m]["debit_e4"] -= old_eff[m]["debit_e4"]
                eff[m]["credit_e4"] -= old_eff[m]["credit_e4"]
        before = _account_balances(c, p.account["id"])
    out = {
        "doc_type": p.doc_type,
        "account": {"id": p.account["id"], "account_no": p.account["account_no"], "name": p.account["name"]},
        "doc_date": p.doc_date,
        "working_karat": p.working_karat,
        "lines": [_fmt_prepared_line(p.doc_type, ln) for ln in p.lines],
        "voucher": _fmt_voucher(p.voucher) if p.voucher else None,
        "description": p.description,
        "totals": _totals(p),
        "warnings": p.warnings,
        "balances": {},
    }
    for m, dp in F.MATERIAL_DP.items():
        net_change = eff[m]["debit_e4"] - eff[m]["credit_e4"]
        out["balances"][m] = {
            "before": F.fmt(before[m], dp),
            "change": F.fmt(net_change, dp),
            "after": F.fmt(before[m] + net_change, dp),
            "before_e4": before[m],
            "after_e4": before[m] + net_change,
        }
    return out


def post_document(db, actor: Actor, data: dict) -> dict:
    doc_type = str(data.get("doc_type") or "")
    if doc_type not in DOC_TYPES:
        raise ValidationError("اختر نوع العملية")
    actor.require(_perm_for(doc_type))
    token = client_token(data.get("client_token"))
    with db.write() as c:
        dup = c.execute("SELECT id, doc_type, account_id FROM documents WHERE client_token = ?", (token,)).fetchone()
        if dup:
            # إعادة إرسال الطلب نفسه: نعيد المستند الذي رُحّل سابقاً ولا نسجّل شيئاً جديداً
            result = _doc_dict(c, dup["id"])
            result["duplicate_request"] = True
            return result
        p = _prepare(c, actor, data)
        seq = next_seq(c, f"doc:{doc_type}")
        order = next_seq(c, "posting_order")
        now = utcnow()
        cur = c.execute(
            """INSERT INTO documents(doc_type, seq, doc_no, posting_order, account_id, doc_date, working_karat,
                                     original_doc_id, is_unlinked_return, exception_reason, description, notes,
                                     status, client_token, version, posted_at, posted_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?, 1, ?, ?)""",
            (doc_type, seq, doc_no_for(doc_type, seq), order, p.account["id"], p.doc_date, p.working_karat,
             p.original_doc_id, int(p.is_unlinked_return), p.exception_reason, p.description, p.notes,
             token, now, actor.id),
        )
        doc_id = cur.lastrowid
        _insert_lines_and_entries(c, doc_id, p, now)
        result = _doc_dict(c, doc_id, with_history=False)
        audit(c, actor, "post", "document", doc_id, result["doc_no"], after=_snapshot(result))
        result = _doc_dict(c, doc_id)
    result["warnings"] = p.warnings
    return result


def edit_document(db, actor: Actor, doc_id: int, data: dict) -> dict:
    actor.require("docs.edit")
    reason = clean_line(data.get("reason"), 300)
    if len(reason) < 3:
        raise ValidationError("اكتب سبب التعديل", {"field": "reason"})
    with db.write() as c:
        existing = _load_doc_row(c, doc_id)
        if existing["doc_type"] == "opening":
            actor.require("opening.manage")
        if existing["status"] != "posted":
            raise ValidationError("لا يمكن تعديل مستند ملغى")
        if int(data.get("version", 0)) != existing["version"]:
            raise Conflict("تم تعديل هذا المستند من مستخدم آخر بعد فتحه. أعد فتحه ثم عدّل", code="stale")
        before = _doc_dict(c, doc_id, with_history=False)
        p = _prepare(c, actor, data, existing)
        now = utcnow()
        c.execute(
            """UPDATE documents SET doc_date = ?, description = ?, notes = ?, exception_reason = ?,
                      version = version + 1, updated_at = ?, updated_by = ? WHERE id = ?""",
            (p.doc_date, p.description, p.notes, p.exception_reason, now, actor.id, doc_id),
        )
        c.execute("DELETE FROM ledger_entries WHERE doc_id = ?", (doc_id,))
        if p.doc_type in TRADE_TYPES:
            keep = [ln["id"] for ln in p.lines if ln.get("id")]
            # الأسطر المحذوفة (تحققنا مسبقاً أنه لا مرتجعات عليها)
            if keep:
                marks = ",".join("?" * len(keep))
                c.execute(f"DELETE FROM trade_lines WHERE doc_id = ? AND id NOT IN ({marks})", [doc_id] + keep)
            else:
                c.execute("DELETE FROM trade_lines WHERE doc_id = ?", (doc_id,))
            # ترقيم مؤقت سالب لتفادي تعارض (doc_id, line_no) أثناء إعادة الترقيم
            c.execute("UPDATE trade_lines SET line_no = -id WHERE doc_id = ?", (doc_id,))
            for ln in p.lines:
                if ln.get("id"):
                    c.execute(
                        """UPDATE trade_lines SET line_no = ?, run_no = ?, gold_e4 = ?, diamond_e4 = ?, rate_e4 = ?,
                                  wage_e4 = ?, rate_overridden = ? WHERE id = ?""",
                        (ln["line_no"], ln["run_no"], ln["gold_e4"], ln["diamond_e4"], ln["rate_e4"],
                         ln["wage_e4"], int(ln["rate_overridden"]), ln["id"]),
                    )
        elif p.doc_type in VOUCHER_TYPES:
            c.execute("DELETE FROM voucher_details WHERE doc_id = ?", (doc_id,))
        else:
            c.execute("DELETE FROM opening_lines WHERE doc_id = ?", (doc_id,))
        _insert_lines_and_entries(c, doc_id, p, now)
        after = _doc_dict(c, doc_id, with_history=False)
        audit(c, actor, "edit", "document", doc_id, after["doc_no"], reason,
              before=_snapshot(before), after=_snapshot(after))
        after = _doc_dict(c, doc_id)
    after["warnings"] = p.warnings
    return after


def cancel_document(db, actor: Actor, doc_id: int, data: dict) -> dict:
    """إلغاء معتمد: يبقى المستند وقيوده الأصلية، وتُضاف قيود عكسية بنفس التاريخ فيصبح الأثر صفراً."""
    actor.require("docs.cancel")
    reason = clean_line(data.get("reason"), 300)
    if len(reason) < 3:
        raise ValidationError("اكتب سبب الإلغاء", {"field": "reason"})
    with db.write() as c:
        doc = _load_doc_row(c, doc_id)
        if doc["doc_type"] == "opening":
            actor.require("opening.manage")
        if doc["status"] != "posted":
            raise ValidationError("المستند ملغى مسبقاً")
        if data.get("version") not in (None, "") and int(data["version"]) != doc["version"]:
            raise Conflict("تم تعديل هذا المستند من مستخدم آخر بعد فتحه. أعد فتحه", code="stale")
        if doc["doc_type"] == "sale":
            linked = c.execute(
                """SELECT doc_no FROM documents WHERE original_doc_id = ? AND status = 'posted' ORDER BY id""",
                (doc_id,)).fetchall()
            if linked:
                raise Conflict(
                    "لا يمكن إلغاء الفاتورة لوجود مرتجعات مرحّلة مرتبطة بها: "
                    + "، ".join(r["doc_no"] for r in linked)
                    + ". ألغِ المرتجعات أولاً.",
                    {"linked": [r["doc_no"] for r in linked]}, code="has_links")
        before = _doc_dict(c, doc_id, with_history=False)
        now = utcnow()
        for e in c.execute("SELECT * FROM ledger_entries WHERE doc_id = ? AND is_reversal = 0",
                           (doc_id,)).fetchall():
            c.execute(
                """INSERT INTO ledger_entries(doc_id, account_id, entry_date, material, debit_e4, credit_e4,
                                              ref_karat, line_no, source_line_id, run_no, is_reversal, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (doc_id, e["account_id"], e["entry_date"], e["material"], e["credit_e4"], e["debit_e4"],
                 e["ref_karat"], e["line_no"], e["source_line_id"], e["run_no"], now),
            )
        c.execute(
            """UPDATE documents SET status = 'cancelled', cancelled_at = ?, cancelled_by = ?, cancel_reason = ?,
                      version = version + 1 WHERE id = ?""",
            (now, actor.id, reason, doc_id),
        )
        audit(c, actor, "cancel", "document", doc_id, before["doc_no"], reason,
              before=_snapshot(before), after={"status": "cancelled"})
        after = _doc_dict(c, doc_id)
    return after


# ============================================================================
#  القراءة والعرض
# ============================================================================
def _load_doc_row(c, doc_id) -> dict:
    row = c.execute("SELECT * FROM documents WHERE id = ?", (int(doc_id),)).fetchone()
    if row is None:
        raise NotFound("المستند غير موجود")
    return dict(row)


def _account_balances(c, account_id) -> dict:
    out = {m: 0 for m in MATERIALS}
    for r in c.execute("""SELECT material, SUM(debit_e4) - SUM(credit_e4) AS b FROM ledger_entries
                          WHERE account_id = ? GROUP BY material""", (account_id,)):
        out[r["material"]] = r["b"] or 0
    return out


def _fmt_prepared_line(doc_type, ln) -> dict:
    if doc_type in TRADE_TYPES:
        return {
            "id": ln.get("id"),
            "line_no": ln["line_no"],
            "run_no": ln["run_no"],
            "gold": F.fmt(ln["gold_e4"], F.DP_GOLD),
            "diamond": F.fmt(ln["diamond_e4"], F.DP_DIAMOND),
            "rate": F.fmt_rate(ln["rate_e4"]),
            "wage": F.fmt(ln["wage_e4"], F.DP_WAGE),
            "rate_overridden": bool(ln["rate_overridden"]),
            "original_line_id": ln.get("original_line_id"),
        }
    return _fmt_opening_line(ln)


def _fmt_opening_line(ln) -> dict:
    dp = F.MATERIAL_DP[ln["material"]]
    return {
        "id": ln.get("id"),
        "line_no": ln["line_no"],
        "material": ln["material"],
        "direction": ln["direction"],
        "actual": F.fmt(ln["actual_e4"], dp),
        "karat": ln["actual_karat"],
        "working_karat": ln["working_karat"],
        "equivalent": F.fmt(ln["equivalent_e4"], dp),
        "description": ln["description"],
        "note": ln["note"],
    }


def _fmt_voucher(v) -> dict:
    dp = F.MATERIAL_DP[v["material"]]
    return {
        "material": v["material"],
        "actual": F.fmt(v["actual_e4"], dp),
        "karat": v["actual_karat"],
        "working_karat": v["working_karat"],
        "equivalent": F.fmt(v["equivalent_e4"], dp),
    }


def _totals(p: Prepared) -> dict:
    if p.doc_type in TRADE_TYPES:
        return {
            "lines": len(p.lines),
            "gold": F.fmt(sum(ln["gold_e4"] for ln in p.lines), F.DP_GOLD),
            "diamond": F.fmt(sum(ln["diamond_e4"] for ln in p.lines), F.DP_DIAMOND),
            "wage": F.fmt(sum(ln["wage_e4"] for ln in p.lines), F.DP_WAGE),
        }
    return {"lines": len(p.lines) if p.lines else 1}


def _users_map(c) -> dict:
    return {r["id"]: r["full_name"] for r in c.execute("SELECT id, full_name FROM users")}


def _doc_dict(c, doc_id: int, with_history: bool = True) -> dict:
    d = _load_doc_row(c, doc_id)
    users = _users_map(c)
    acc = c.execute("SELECT id, account_no, name, wage_rate_e4, is_active FROM accounts WHERE id = ?",
                    (d["account_id"],)).fetchone()
    out = {
        "id": d["id"],
        "doc_type": d["doc_type"],
        "type_label": DOC_TYPES[d["doc_type"]],
        "doc_no": d["doc_no"],
        "doc_date": d["doc_date"],
        "status": d["status"],
        "account": {"id": acc["id"], "account_no": acc["account_no"], "name": acc["name"],
                    "wage_rate": F.fmt_rate(acc["wage_rate_e4"]), "is_active": bool(acc["is_active"])},
        "working_karat": d["working_karat"],
        "description": d["description"],
        "notes": d["notes"],
        "is_unlinked_return": bool(d["is_unlinked_return"]),
        "exception_reason": d["exception_reason"],
        "original_doc": None,
        "version": d["version"],
        "posted_at": d["posted_at"],
        "posted_by": users.get(d["posted_by"], ""),
        "updated_at": d["updated_at"],
        "updated_by": users.get(d["updated_by"], "") if d["updated_by"] else "",
        "cancelled_at": d["cancelled_at"],
        "cancelled_by": users.get(d["cancelled_by"], "") if d["cancelled_by"] else "",
        "cancel_reason": d["cancel_reason"],
        "lines": [],
        "voucher": None,
        "linked_returns": [],
    }
    if d["original_doc_id"]:
        o = c.execute("SELECT id, doc_no, doc_date, status FROM documents WHERE id = ?",
                      (d["original_doc_id"],)).fetchone()
        out["original_doc"] = dict(o)

    if d["doc_type"] in TRADE_TYPES:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM trade_lines WHERE doc_id = ? ORDER BY line_no", (doc_id,))]
        returned = returned_by_line(c, [r["id"] for r in rows]) if d["doc_type"] == "sale" else {}
        orig_info = {}
        if d["doc_type"] == "return":
            ids = [r["original_line_id"] for r in rows if r["original_line_id"]]
            if ids:
                marks = ",".join("?" * len(ids))
                for r in c.execute(
                        f"""SELECT tl.id, tl.line_no, tl.gold_e4, tl.diamond_e4, d.doc_no FROM trade_lines tl
                            JOIN documents d ON d.id = tl.doc_id WHERE tl.id IN ({marks})""", ids):
                    orig_info[r["id"]] = {"doc_no": r["doc_no"], "line_no": r["line_no"],
                                          "gold": F.fmt(r["gold_e4"], 4), "diamond": F.fmt(r["diamond_e4"], 3)}
        for r in rows:
            line = _fmt_prepared_line(d["doc_type"], r)
            if d["doc_type"] == "sale":
                done = returned.get(r["id"], {"gold_e4": 0, "diamond_e4": 0, "wage_e4": 0})
                line["returned"] = {"gold": F.fmt(done["gold_e4"], 4), "diamond": F.fmt(done["diamond_e4"], 3),
                                    "wage": F.fmt(done["wage_e4"], 2)}
                line["has_returns"] = done["gold_e4"] > 0 or done["diamond_e4"] > 0 or done["wage_e4"] > 0
            if r["original_line_id"]:
                line["original"] = orig_info.get(r["original_line_id"])
            out["lines"].append(line)
        out["totals"] = {
            "lines": len(rows),
            "gold": F.fmt(sum(r["gold_e4"] for r in rows), 4),
            "diamond": F.fmt(sum(r["diamond_e4"] for r in rows), 3),
            "wage": F.fmt(sum(r["wage_e4"] for r in rows), 2),
        }
        if d["doc_type"] == "sale":
            out["linked_returns"] = [dict(r) for r in c.execute(
                "SELECT id, doc_no, doc_date, status FROM documents WHERE original_doc_id = ? ORDER BY id",
                (doc_id,))]
    elif d["doc_type"] in VOUCHER_TYPES:
        v = c.execute("SELECT * FROM voucher_details WHERE doc_id = ?", (doc_id,)).fetchone()
        out["voucher"] = _fmt_voucher(dict(v))
        out["totals"] = {"lines": 1}
    else:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM opening_lines WHERE doc_id = ? ORDER BY line_no", (doc_id,))]
        out["lines"] = [_fmt_opening_line(r) for r in rows]
        out["totals"] = {"lines": len(rows)}

    entries = [dict(r) for r in c.execute(
        "SELECT material, debit_e4, credit_e4, is_reversal FROM ledger_entries WHERE doc_id = ?", (doc_id,))]
    out["effects"] = _fmt_effects(_effects([e for e in entries if not e["is_reversal"]]))
    out["net_effects"] = _fmt_effects(_effects(entries))
    if with_history:
        out["history"] = [
            {"at": h["at"], "user": users.get(h["user_id"], ""), "action": h["action"], "reason": h["reason"],
             "before": h["before_json"], "after": h["after_json"]}
            for h in c.execute(
                "SELECT * FROM audit_log WHERE entity = 'document' AND entity_id = ? ORDER BY id", (doc_id,))
        ]
    return out


def _snapshot(doc: dict) -> dict:
    keys = ("doc_no", "doc_type", "doc_date", "status", "description", "notes", "working_karat",
            "exception_reason", "lines", "voucher", "totals")
    snap = {k: doc.get(k) for k in keys}
    snap["account"] = {"id": doc["account"]["id"], "account_no": doc["account"]["account_no"],
                       "name": doc["account"]["name"]}
    if doc.get("original_doc"):
        snap["original_doc"] = doc["original_doc"]["doc_no"]
    snap["lines"] = [{k: v for k, v in ln.items() if k not in ("returned", "has_returns", "original")}
                     for ln in (doc.get("lines") or [])]
    return snap


def get_document(db, doc_id: int) -> dict:
    with db.read() as c:
        return _doc_dict(c, doc_id)


def get_document_by_no(db, doc_no: str) -> dict:
    with db.read() as c:
        row = c.execute("SELECT id FROM documents WHERE doc_no = ?", (clean_line(doc_no, 30).upper(),)).fetchone()
        if row is None:
            raise NotFound("لا يوجد مستند بهذا الرقم")
        return _doc_dict(c, row["id"])


def returnable_lines(db, sale_doc_id: int, exclude_doc_id: int | None = None) -> dict:
    """أسطر فاتورة البيع مع الكميات المرتجعة والمتبقية (لاختيار أسطر المرتجع)."""
    with db.read() as c:
        doc = _load_doc_row(c, sale_doc_id)
        if doc["doc_type"] != "sale":
            raise ValidationError("المستند المحدد ليس فاتورة مبيعات")
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM trade_lines WHERE doc_id = ? ORDER BY line_no", (sale_doc_id,))]
        done = returned_by_line(c, [r["id"] for r in rows], exclude_doc_id)
    lines = []
    for r in rows:
        dn = done.get(r["id"], {"gold_e4": 0, "diamond_e4": 0, "wage_e4": 0})
        lines.append({
            "id": r["id"],
            "line_no": r["line_no"],
            "run_no": r["run_no"],
            "rate": F.fmt_rate(r["rate_e4"]),
            "sold": {"gold": F.fmt(r["gold_e4"], 4), "diamond": F.fmt(r["diamond_e4"], 3),
                     "wage": F.fmt(r["wage_e4"], 2)},
            "returned": {"gold": F.fmt(dn["gold_e4"], 4), "diamond": F.fmt(dn["diamond_e4"], 3),
                         "wage": F.fmt(dn["wage_e4"], 2)},
            "remaining": {"gold": F.fmt(r["gold_e4"] - dn["gold_e4"], 4),
                          "diamond": F.fmt(r["diamond_e4"] - dn["diamond_e4"], 3),
                          "wage": F.fmt(r["wage_e4"] - dn["wage_e4"], 2)},
            "fully_returned": r["gold_e4"] == dn["gold_e4"] and r["diamond_e4"] == dn["diamond_e4"],
        })
    return {"doc_id": doc["id"], "doc_no": doc["doc_no"], "doc_date": doc["doc_date"], "status": doc["status"],
            "account_id": doc["account_id"], "lines": lines}


def sale_invoices_for_account(db, account_id: int, q: str = "") -> list:
    """فواتير المبيعات المرحّلة للعميل مع المتبقي القابل للإرجاع (لاختيار الفاتورة الأصلية)."""
    q = clean_line(q, 60)
    with db.read() as c:
        rows = c.execute(
            """SELECT d.id, d.doc_no, d.doc_date,
                      SUM(tl.gold_e4) g, SUM(tl.diamond_e4) dm, SUM(tl.wage_e4) w, COUNT(tl.id) n,
                      GROUP_CONCAT(tl.run_no, ' ') runs
               FROM documents d JOIN trade_lines tl ON tl.doc_id = d.id
               WHERE d.account_id = ? AND d.doc_type = 'sale' AND d.status = 'posted'
               GROUP BY d.id ORDER BY d.doc_date DESC, d.posting_order DESC LIMIT 500""",
            (int(account_id),)).fetchall()
        ret = {r["oid"]: r for r in c.execute(
            """SELECT r.original_doc_id oid, SUM(tl.gold_e4) g, SUM(tl.diamond_e4) dm
               FROM documents r JOIN trade_lines tl ON tl.doc_id = r.id
               WHERE r.account_id = ? AND r.doc_type = 'return' AND r.status = 'posted'
                     AND r.original_doc_id IS NOT NULL GROUP BY r.original_doc_id""", (int(account_id),))}
    out = []
    for r in rows:
        if q and q.upper() not in r["doc_no"] and q.casefold() not in (r["runs"] or "").casefold():
            continue
        rg = ret.get(r["id"])
        rem_g = r["g"] - (rg["g"] if rg else 0)
        rem_d = r["dm"] - (rg["dm"] if rg else 0)
        out.append({
            "id": r["id"], "doc_no": r["doc_no"], "doc_date": r["doc_date"], "lines": r["n"],
            "gold": F.fmt(r["g"], 4), "diamond": F.fmt(r["dm"], 3), "wage": F.fmt(r["w"], 2),
            "remaining_gold": F.fmt(rem_g, 4), "remaining_diamond": F.fmt(rem_d, 3),
            "has_remaining": rem_g > 0 or rem_d > 0,
        })
    return out


def search_documents(db, params: dict) -> list:
    """البحث عن المستندات برقم المستند أو رقم التشغيل أو اسم/رقم العميل أو التاريخ أو النوع."""
    q = clean_line(params.get("q"), 80)
    types = [t for t in str(params.get("types") or "").split(",") if t in DOC_TYPES]
    where, args = [], []
    if types:
        where.append(f"d.doc_type IN ({','.join('?' * len(types))})")
        args += types
    if params.get("account_id"):
        where.append("d.account_id = ?")
        args.append(int(params["account_id"]))
    if params.get("date_from"):
        where.append("d.doc_date >= ?")
        args.append(parse_date(params["date_from"], "من تاريخ"))
    if params.get("date_to"):
        where.append("d.doc_date <= ?")
        args.append(parse_date(params["date_to"], "إلى تاريخ"))
    if params.get("status") in ("posted", "cancelled"):
        where.append("d.status = ?")
        args.append(params["status"])
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        key_like = "%" + name_key(q).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(
            """(d.doc_no LIKE ? ESCAPE '\\' OR a.account_no = ? OR a.name_key LIKE ? ESCAPE '\\'
                OR d.description LIKE ? ESCAPE '\\'
                OR EXISTS (SELECT 1 FROM trade_lines t WHERE t.doc_id = d.id AND t.run_no LIKE ? ESCAPE '\\'))""")
        args += [like.upper(), q, key_like, like, like]
    sql = """SELECT d.*, a.name AS account_name, a.account_no FROM documents d
             JOIN accounts a ON a.id = d.account_id"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY d.doc_date DESC, d.posting_order DESC LIMIT ?"
    args.append(min(int(params.get("limit") or 200), 500))
    with db.read() as c:
        rows = c.execute(sql, args).fetchall()
        ids = [r["id"] for r in rows]
        eff = {}
        runs = {}
        if ids:
            marks = ",".join("?" * len(ids))
            for e in c.execute(
                    f"""SELECT doc_id, material, SUM(debit_e4) dr, SUM(credit_e4) cr FROM ledger_entries
                        WHERE doc_id IN ({marks}) AND is_reversal = 0 GROUP BY doc_id, material""", ids):
                eff.setdefault(e["doc_id"], {})[e["material"]] = (e["dr"] or 0) + (e["cr"] or 0)
            for t in c.execute(
                    f"""SELECT doc_id, GROUP_CONCAT(run_no, '، ') rn, COUNT(*) n FROM trade_lines
                        WHERE doc_id IN ({marks}) GROUP BY doc_id""", ids):
                runs[t["doc_id"]] = (t["rn"] or "", t["n"])
    out = []
    for r in rows:
        e = eff.get(r["id"], {})
        rn = runs.get(r["id"], ("", 0))
        out.append({
            "id": r["id"], "doc_no": r["doc_no"], "doc_type": r["doc_type"], "type_label": DOC_TYPES[r["doc_type"]],
            "doc_date": r["doc_date"], "status": r["status"],
            "account": {"id": r["account_id"], "name": r["account_name"], "account_no": r["account_no"]},
            "description": r["description"],
            "gold": F.fmt(e.get("gold", 0), 4), "diamond": F.fmt(e.get("diamond", 0), 3),
            "wage": F.fmt(e.get("wage", 0), 2),
            "run_numbers": rn[0][:200], "lines": rn[1],
        })
    return out

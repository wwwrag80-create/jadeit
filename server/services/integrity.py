"""فحص سلامة البيانات: يكتشف مصدر أي اختلاف بدلاً من إخفائه.

يعيد بناء القيود المتوقعة لكل مستند من أسطره (بنفس الدالة المستخدمة في الترحيل)
ثم يقارنها بالقيود الفعلية في الدفتر، ويتحقق من:
  1. تطابق قيود كل مستند مع أسطره (العدد، المادة، المدين، الدائن، العيار).
  2. صحة الأجر المحسوب لكل سطر (الذهب × الأجر) وصحة الوزن المكافئ لكل سند.
  3. أن المستند الملغى صافي أثره صفر (قيد أصلي + قيد عكسي مطابق).
  4. ألا تتجاوز المرتجعات الكميات المباعة لكل سطر.
  5. تطابق جدول الأرصدة المحفوظة مع مجموع الدفتر لكل حساب.
  6. عدم وجود قيود يتيمة أو مستندات مرحّلة بلا قيود.
"""
from __future__ import annotations

from collections import Counter

from .. import fixed as F
from .common import Actor
from .documents import TRADE_TYPES, VOUCHER_TYPES, build_entries


def _key(e):
    return (e["material"], e["debit_e4"], e["credit_e4"], e["ref_karat"], e["line_no"])


def run_check(db, actor: Actor) -> dict:
    actor.require("system.backup")
    issues = []

    def issue(kind, ref, message):
        issues.append({"kind": kind, "ref": ref, "message": message})

    with db.read() as c:
        docs = c.execute("SELECT * FROM documents ORDER BY id").fetchall()
        lines_by_doc = {}
        for r in c.execute("SELECT * FROM trade_lines ORDER BY doc_id, line_no"):
            lines_by_doc.setdefault(r["doc_id"], []).append(dict(r))
        opening_by_doc = {}
        for r in c.execute("SELECT * FROM opening_lines ORDER BY doc_id, line_no"):
            opening_by_doc.setdefault(r["doc_id"], []).append(dict(r))
        vouchers = {r["doc_id"]: dict(r) for r in c.execute("SELECT * FROM voucher_details")}
        entries_by_doc = {}
        for r in c.execute("SELECT * FROM ledger_entries"):
            entries_by_doc.setdefault(r["doc_id"], []).append(dict(r))
        doc_ids = {d["id"] for d in docs}
        orphan = [d for d in entries_by_doc if d not in doc_ids]
        cache = c.execute(
            "SELECT account_id, material, ref_karat, debit_e4, credit_e4, entries FROM account_balances").fetchall()
        ledger_sum = c.execute(
            """SELECT account_id, material, COALESCE(ref_karat, 0) rk, SUM(debit_e4) dr, SUM(credit_e4) cr,
                      COUNT(*) n FROM ledger_entries GROUP BY account_id, material, COALESCE(ref_karat, 0)""").fetchall()

    for d in orphan:
        issue("orphan", str(d), "قيود في الدفتر لمستند غير موجود")

    for d in docs:
        ref = d["doc_no"]
        actual = entries_by_doc.get(d["id"], [])
        for e in actual:
            if e["account_id"] != d["account_id"] or e["entry_date"] != d["doc_date"]:
                issue("mismatch", ref, "قيد لا يطابق حساب المستند أو تاريخه")
        if d["doc_type"] in TRADE_TYPES:
            lines = lines_by_doc.get(d["id"], [])
            if not lines:
                issue("empty", ref, "مستند بلا أسطر")
            for ln in lines:
                if d["doc_type"] == "sale" or d["is_unlinked_return"]:
                    if ln["wage_e4"] != F.wage_total(ln["gold_e4"], ln["rate_e4"]):
                        issue("wage", ref, f"أجر السطر {ln['line_no']} لا يساوي الذهب × الأجر")
                elif ln["gold_e4"] == 0 and ln["wage_e4"] != 0:
                    issue("wage", ref, f"أجر مسترد دون ذهب مرتجع في السطر {ln['line_no']}")
            expected = build_entries(d["doc_type"], d["working_karat"], lines)
        elif d["doc_type"] in VOUCHER_TYPES:
            v = vouchers.get(d["id"])
            if v is None:
                issue("empty", ref, "سند بلا تفاصيل")
                continue
            if v["material"] == "gold" and v["equivalent_e4"] != F.equivalent(
                    v["actual_e4"], v["actual_karat"], v["working_karat"]):
                issue("equivalent", ref, "الوزن المكافئ لا يطابق المعادلة")
            expected = build_entries(d["doc_type"], d["working_karat"], voucher=v)
        else:
            lines = opening_by_doc.get(d["id"], [])
            if not lines:
                issue("empty", ref, "رصيد افتتاحي بلا أسطر")
            for ln in lines:
                if ln["material"] == "gold" and ln["equivalent_e4"] != F.equivalent(
                        ln["actual_e4"], ln["actual_karat"], ln["working_karat"]):
                    issue("equivalent", ref, f"الوزن المكافئ في السطر {ln['line_no']} لا يطابق المعادلة")
            expected = build_entries("opening", d["working_karat"], lines)

        originals = [e for e in actual if not e["is_reversal"]]
        reversals = [e for e in actual if e["is_reversal"]]
        if Counter(map(_key, expected)) != Counter(map(_key, originals)):
            issue("entries", ref, "قيود المستند في الدفتر لا تطابق أسطره")
        if d["status"] == "cancelled":
            flipped = [{**e, "debit_e4": e["credit_e4"], "credit_e4": e["debit_e4"]} for e in originals]
            if Counter(map(_key, flipped)) != Counter(map(_key, reversals)):
                issue("cancel", ref, "المستند ملغى لكن قيوده العكسية غير مكتملة")
        elif reversals:
            issue("cancel", ref, "قيود عكسية لمستند غير ملغى")

    # المرتجعات لا تتجاوز المباع
    sold = {}
    for d in docs:
        if d["doc_type"] == "sale":
            for ln in lines_by_doc.get(d["id"], []):
                sold[ln["id"]] = (d["doc_no"], ln)
    returned = {}
    for d in docs:
        if d["doc_type"] == "return" and d["status"] == "posted":
            for ln in lines_by_doc.get(d["id"], []):
                if ln["original_line_id"]:
                    t = returned.setdefault(ln["original_line_id"], [0, 0, 0])
                    t[0] += ln["gold_e4"]
                    t[1] += ln["diamond_e4"]
                    t[2] += ln["wage_e4"]
    for lid, (g, dm, w) in returned.items():
        if lid not in sold:
            issue("return", str(lid), "مرتجع مرتبط بسطر بيع غير موجود")
            continue
        doc_no, ln = sold[lid]
        if g > ln["gold_e4"] or dm > ln["diamond_e4"] or w > ln["wage_e4"]:
            issue("return", doc_no, f"المرتجع تجاوز المباع في السطر {ln['line_no']}")

    # الأرصدة المحفوظة = مجموع الدفتر
    cache_map = {(r["account_id"], r["material"], r["ref_karat"]): (r["debit_e4"], r["credit_e4"], r["entries"])
                 for r in cache}
    ledger_map = {(r["account_id"], r["material"], r["rk"]): (r["dr"], r["cr"], r["n"]) for r in ledger_sum}
    for k in set(cache_map) | set(ledger_map):
        cv = cache_map.get(k, (0, 0, 0))
        lv = ledger_map.get(k, (0, 0, 0))
        if cv != lv:
            issue("balance_cache", f"حساب {k[0]}", f"الرصيد المحفوظ لا يطابق الدفتر ({k[1]})")

    return {
        "ok": not issues,
        "issues": issues[:500],
        "issue_count": len(issues),
        "documents_checked": len(docs),
        "entries_checked": sum(len(v) for v in entries_by_doc.values()),
    }

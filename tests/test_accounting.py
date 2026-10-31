"""اختبارات السيناريوهات المحاسبية العشرين المطلوبة (على طبقة الخدمات مباشرة)."""
from __future__ import annotations

import sqlite3
import threading
import unittest

from helpers import BaseCase, token

from server import fixed as F
from server.errors import Conflict, Forbidden, ValidationError
from server.services import accounts, integrity, reports, settings
from server.services import documents as docs


class S01_CreateAccount(BaseCase):
    def test_create_account_with_wage(self):
        a = self.account("ورشة النور", rate="7.25", phone="0551234567", notes="عميل جملة")
        self.assertEqual(a["account_no"], "1001")
        self.assertEqual(a["wage_rate"], "7.25")
        b = self.account("ورشة الفجر", rate="3.125")
        self.assertEqual(b["account_no"], "1002")
        self.assertEqual(b["wage_rate"], "3.125")

    def test_duplicate_name_rules(self):
        self.account("مؤسسة أحمد للذهب")
        # نفس الاسم مع اختلاف الهمزة والمسافات والتشكيل → مكرر
        for variant in ("مؤسسة احمد للذهب", "  مؤسسة   أحمد للذهب ", "مؤسسةُ أحمدَ للذهب", "مؤسسـة إحمد للذهب"):
            with self.assertRaises(Conflict, msg=variant):
                self.account(variant)
        self.account("مؤسسة أحمد للذهب فرع 2")  # اسم مختلف فعلاً

    def test_double_click_creates_one_account(self):
        t = token()
        a1 = accounts.create_account(self.db, self.admin, {"name": "عميل", "wage_rate": "1", "client_token": t})
        a2 = accounts.create_account(self.db, self.admin, {"name": "عميل", "wage_rate": "1", "client_token": t})
        self.assertEqual(a1["id"], a2["id"])
        self.assertTrue(a2.get("duplicate_request"))
        self.assertEqual(len(accounts.list_accounts(self.db)), 1)

    def test_wage_required_and_validated(self):
        with self.assertRaises(ValidationError):
            accounts.create_account(self.db, self.admin, {"name": "س", "wage_rate": "1", "client_token": token()})
        with self.assertRaises(ValidationError):
            accounts.create_account(self.db, self.admin, {"name": "عميل", "wage_rate": "", "client_token": token()})
        with self.assertRaises(ValidationError):
            accounts.create_account(self.db, self.admin, {"name": "عميل", "wage_rate": "-2", "client_token": token()})

    def test_wage_change_does_not_touch_posted_lines(self):
        a = self.account(rate="5")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10"}])
        accounts.update_account(self.db, self.admin, a["id"], {"wage_rate": "9", "version": a["version"]})
        doc = docs.get_document(self.db, s["id"])
        self.assertEqual(doc["lines"][0]["rate"], "5.00")
        self.assertEqual(doc["lines"][0]["wage"], "50.00")
        self.assertEqual(self.balance(a["id"], "wage"), "50.00")
        s2 = self.sale(a["id"], [{"run_no": "2", "gold": "10"}])
        self.assertEqual(s2["lines"][0]["rate"], "9.00")

    def test_wage_edit_requires_permission(self):
        a = self.account(rate="5")
        clerk = self.make_user("clerk", ["accounts.manage"])
        with self.assertRaises(Forbidden):
            accounts.update_account(self.db, clerk, a["id"], {"wage_rate": "6", "version": a["version"]})
        accounts.update_account(self.db, clerk, a["id"], {"phone": "0500000000", "version": a["version"]})


class S02_S03_Sales(BaseCase):
    def test_multi_line_sale(self):
        a = self.account(rate="5.5")
        s = self.sale(a["id"], [
            {"run_no": "0012", "gold": "10.25", "diamond": "0.5"},
            {"run_no": "0013", "gold": "5", "diamond": "0"},
            {"run_no": "0014", "gold": "0", "diamond": "1.25"},
        ])
        self.assertEqual(s["doc_no"], "SA-000001")
        self.assertEqual(s["totals"], {"lines": 3, "gold": "15.2500", "diamond": "1.750", "wage": "83.88"})
        self.assertEqual([ln["run_no"] for ln in s["lines"]], ["0012", "0013", "0014"])  # كما أدخلها المستخدم
        self.assertEqual(self.balance(a["id"], "gold"), "15.2500")
        self.assertEqual(self.balance(a["id"], "diamond"), "1.750")
        self.assertEqual(self.balance(a["id"], "wage"), "83.88")

    def test_wage_depends_on_gold_only(self):
        a = self.account(rate="10")
        s = self.sale(a["id"], [
            {"run_no": "999", "gold": "2", "diamond": "5"},     # الألماس ورقم التشغيل لا يدخلان في الأجر
            {"run_no": "1000", "gold": "0", "diamond": "3"},    # ذهب صفر → أجر صفر
        ])
        self.assertEqual(s["lines"][0]["wage"], "20.00")
        self.assertEqual(s["lines"][1]["wage"], "0.00")
        self.assertEqual(s["totals"]["wage"], "20.00")

    def test_line_rate_override_needs_permission(self):
        a = self.account(rate="5")
        clerk = self.make_user("clerk", ["docs.post"])
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": "1", "rate": "6"}], actor=clerk)
        senior = self.make_user("senior", ["docs.post", "docs.rate_override"])
        s = self.sale(a["id"], [{"run_no": "1", "gold": "1", "rate": "6"}], actor=senior)
        self.assertEqual(s["lines"][0]["wage"], "6.00")
        self.assertTrue(s["lines"][0]["rate_overridden"])

    def test_validation(self):
        a = self.account()
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [])
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": "0", "diamond": "0"}])
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": "1"}, {"run_no": "1", "gold": "2"}])  # رقم تشغيل مكرر
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": "1.00001"}])  # منازل زائدة
        with self.assertRaises(ValidationError):
            self.sale(9999, [{"run_no": "1", "gold": "1"}])  # عميل غير موجود
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": 1.5}])  # float مرفوض
        # لم يُرحَّل أي شيء
        self.assertEqual(self.balance(a["id"], "gold"), "0.0000")

    def test_inactive_account_blocked(self):
        a = self.account()
        accounts.update_account(self.db, self.admin, a["id"], {"is_active": False, "version": a["version"]})
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "1", "gold": "1"}])


class S04_Returns(BaseCase):
    def test_linked_return_reduces_balances(self):
        a = self.account(rate="5.5")
        s = self.sale(a["id"], [{"run_no": "A1", "gold": "10.25", "diamond": "0.5"},
                                {"run_no": "A2", "gold": "5"}])
        r = self.ret(a["id"], s["id"], [{"original_line_id": s["lines"][0]["id"], "gold": "2.25", "diamond": "0.1"}])
        self.assertEqual(r["doc_no"], "SR-000001")
        self.assertEqual(r["lines"][0]["run_no"], "A1")
        self.assertEqual(r["lines"][0]["rate"], "5.50")        # بأجر الفاتورة الأصلية
        self.assertEqual(r["lines"][0]["wage"], "12.38")       # 2.25 × 5.5 = 12.375 → 12.38
        self.assertEqual(self.balance(a["id"], "gold"), "13.0000")
        self.assertEqual(self.balance(a["id"], "diamond"), "0.400")
        self.assertEqual(self.balance(a["id"], "wage"), F.fmt(F.parse("83.88", 2) - F.parse("12.38", 2), 2))

    def test_return_cannot_exceed_sold(self):
        a = self.account()
        s = self.sale(a["id"], [{"run_no": "A1", "gold": "10", "diamond": "1"}])
        lid = s["lines"][0]["id"]
        with self.assertRaises(ValidationError):
            self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "10.0001"}])
        self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "6"}])
        with self.assertRaises(ValidationError):
            self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "4.0001"}])
        with self.assertRaises(ValidationError):
            self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "0", "diamond": "1.001"}])
        self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "4", "diamond": "1"}])
        self.assertEqual(self.balance(a["id"], "gold"), "0.0000")
        self.assertEqual(self.balance(a["id"], "wage"), "0.00")

    def test_partial_returns_never_over_refund_wage(self):
        a = self.account(rate="0.335")
        s = self.sale(a["id"], [{"run_no": "X", "gold": "3"}])  # 1.005 → 1.01
        self.assertEqual(s["lines"][0]["wage"], "1.01")
        lid = s["lines"][0]["id"]
        for _ in range(3):
            self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "1"}])
        self.assertEqual(self.balance(a["id"], "gold"), "0.0000")
        self.assertEqual(self.balance(a["id"], "wage"), "0.00")

    def test_return_must_belong_to_same_customer(self):
        a = self.account("عميل أ")
        b = self.account("عميل ب")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "1"}])
        with self.assertRaises(ValidationError):
            self.ret(b["id"], s["id"], [{"original_line_id": s["lines"][0]["id"], "gold": "1"}])

    def test_unlinked_return_needs_permission_and_reason(self):
        a = self.account(rate="4")
        clerk = self.make_user("clerk", ["docs.post"])
        data = {"doc_type": "return", "client_token": token(), "account_id": a["id"], "doc_date": "2026-10-01",
                "unlinked": True, "exception_reason": "قطعة قديمة قبل تشغيل النظام",
                "lines": [{"run_no": "OLD-1", "gold": "2"}]}
        with self.assertRaises(Forbidden):
            docs.post_document(self.db, clerk, data)
        with self.assertRaises(ValidationError):
            docs.post_document(self.db, self.admin, {**data, "client_token": token(), "exception_reason": ""})
        r = docs.post_document(self.db, self.admin, {**data, "client_token": token()})
        self.assertTrue(r["is_unlinked_return"])
        self.assertEqual(self.balance(a["id"], "gold"), "-2.0000")
        self.assertEqual(self.balance(a["id"], "wage"), "-8.00")


class S05_S06_S07_GoldVouchers(BaseCase):
    def test_gold_receipt_different_karat(self):
        a = self.account()
        v = self.voucher(a["id"], "receipt", "gold", "100", karat=21)
        self.assertEqual(v["voucher"], {"material": "gold", "actual": "100.0000", "karat": 21,
                                        "working_karat": 18, "equivalent": "116.6667"})
        self.assertEqual(v["doc_no"], "RV-000001")
        self.assertEqual(self.balance(a["id"], "gold"), "-116.6667")  # قبض = دائن
        self.assertEqual(self.balance(a["id"], "wage"), "0.00")        # لا حركة أجور تلقائية

    def test_equivalent_formula(self):
        cases = [("100", 21, 18, "116.6667"), ("100", 18, 18, "100.0000"), ("100", 24, 18, "133.3333"),
                 ("100", 22, 18, "122.2222"), ("50", 18, 21, "42.8571"), ("12.3456", 21, 18, "14.4032"),
                 ("0.0001", 18, 24, "0.0001")]
        for actual, karat, work, expected in cases:
            got = F.fmt(F.equivalent(F.parse(actual, 4), karat, work), 4)
            self.assertEqual(got, expected, (actual, karat, work))

    def test_gold_payment_is_debit(self):
        a = self.account()
        self.voucher(a["id"], "receipt", "gold", "100", karat=21)
        p = self.voucher(a["id"], "payment", "gold", "50", karat=18)
        self.assertEqual(p["doc_no"], "PV-000001")
        self.assertEqual(p["effects"]["gold"]["debit"], "50.0000")
        self.assertEqual(self.balance(a["id"], "gold"), "-66.6667")

    def test_working_karat_change_keeps_history(self):
        a = self.account()
        v1 = self.voucher(a["id"], "receipt", "gold", "100", karat=21)
        settings.change_working_karat(self.db, self.admin, 21, "تغيير سياسة المصنع")
        v2 = self.voucher(a["id"], "receipt", "gold", "100", karat=21)
        self.assertEqual(docs.get_document(self.db, v1["id"])["voucher"]["equivalent"], "116.6667")
        self.assertEqual(v2["voucher"]["equivalent"], "100.0000")
        self.assertEqual(v2["working_karat"], 21)
        summ = reports.account_summary(self.db, a["id"])
        self.assertTrue(summ["sections"]["gold"]["mixed_karats"])
        self.assertEqual([k["karat"] for k in summ["sections"]["gold"]["by_karat"]], [18, 21])
        with self.assertRaises(ValidationError):
            settings.change_working_karat(self.db, self.admin, 21, "نفس العيار")
        hist = settings.karat_history(self.db)
        self.assertEqual(hist[0]["karat"], 21)
        self.assertEqual(hist[0]["previous_karat"], 18)


class S08_Diamond(BaseCase):
    def test_diamond_receipt_and_payment(self):
        a = self.account()
        self.sale(a["id"], [{"run_no": "1", "gold": "1", "diamond": "2.5"}])
        self.voucher(a["id"], "receipt", "diamond", "1.25")
        self.assertEqual(self.balance(a["id"], "diamond"), "1.250")
        self.voucher(a["id"], "payment", "diamond", "0.5")
        self.assertEqual(self.balance(a["id"], "diamond"), "1.750")
        self.assertEqual(self.balance(a["id"], "gold"), "1.0000")     # الألماس لا يمس الذهب
        with self.assertRaises(ValidationError):
            self.voucher(a["id"], "receipt", "diamond", "0")

    def test_wage_settlement_is_explicit(self):
        a = self.account(rate="10")
        self.sale(a["id"], [{"run_no": "1", "gold": "5"}])
        self.voucher(a["id"], "receipt", "gold", "5", karat=18)
        self.assertEqual(self.balance(a["id"], "wage"), "50.00")      # قبض الذهب لا يسدد الأجور
        self.voucher(a["id"], "receipt", "wage", "30")
        self.assertEqual(self.balance(a["id"], "wage"), "20.00")


class S09_S10_Opening(BaseCase):
    def test_opening_debit_and_credit(self):
        a = self.account("عميل أ")
        b = self.account("عميل ب")
        o = self.opening(a["id"], [
            {"material": "gold", "direction": "debit", "actual": "50", "karat": 21, "description": "ذهب سابق"},
            {"material": "diamond", "direction": "credit", "actual": "3"},
            {"material": "wage", "direction": "debit", "actual": "150.50"},
        ])
        self.assertEqual(o["doc_no"], "OB-000001")
        self.assertEqual(o["lines"][0]["equivalent"], "58.3333")
        self.assertEqual(self.balance(a["id"], "gold"), "58.3333")
        self.assertEqual(self.balance(a["id"], "diamond"), "-3.000")
        self.assertEqual(self.balance(a["id"], "wage"), "150.50")
        self.opening(b["id"], [{"material": "gold", "direction": "credit", "actual": "20", "karat": 18}])
        self.assertEqual(self.balance(b["id"], "gold"), "-20.0000")
        st = self.statement(a["id"], "gold")
        self.assertEqual(st["rows"][0]["kind"], "رصيد افتتاحي")

    def test_opening_once_per_account(self):
        a = self.account()
        self.opening(a["id"], [{"material": "wage", "direction": "debit", "actual": "10"}])
        with self.assertRaises(Conflict):
            self.opening(a["id"], [{"material": "wage", "direction": "debit", "actual": "10"}])

    def test_opening_requires_permission(self):
        a = self.account()
        clerk = self.make_user("clerk", ["docs.post"])
        with self.assertRaises(Forbidden):
            self.opening(a["id"], [{"material": "wage", "direction": "debit", "actual": "10"}], actor=clerk)

    def test_opening_records_user_and_date(self):
        a = self.account()
        o = self.opening(a["id"], [{"material": "wage", "direction": "credit", "actual": "10"}], date="2025-12-31")
        self.assertEqual(o["doc_date"], "2025-12-31")
        self.assertEqual(o["posted_by"], "المدير")


class S11_S12_S13_Statement(BaseCase):
    def setUp(self):
        super().setUp()
        self.a = self.account(rate="2")
        self.opening(self.a["id"], [{"material": "gold", "direction": "debit", "actual": "10", "karat": 18}],
                     date="2026-01-01")
        self.sale(self.a["id"], [{"run_no": "1", "gold": "20"}], date="2026-02-10")
        self.voucher(self.a["id"], "receipt", "gold", "18", karat=21, date="2026-03-05")   # 21.0000
        self.sale(self.a["id"], [{"run_no": "2", "gold": "7.5"}], date="2026-04-01")
        self.voucher(self.a["id"], "payment", "gold", "2", karat=18, date="2026-05-01")

    def test_period_statement_and_opening(self):
        st = self.statement(self.a["id"], "gold", date_from="2026-03-01", date_to="2026-04-30")
        self.assertEqual(st["opening"]["signed"], "30.0000")            # 10 + 20 قبل الفترة
        self.assertEqual([r["doc_no"] for r in st["rows"]], ["RV-000001", "SA-000002"])
        self.assertEqual(st["totals"]["debit"], "7.5000")
        self.assertEqual(st["totals"]["credit"], "21.0000")
        self.assertEqual(st["closing"]["signed"], "16.5000")           # 30 − 21 + 7.5
        self.assertEqual(st["rows"][-1]["balance"]["signed"], st["closing"]["signed"])
        # الفترة لا تغيّر الرصيد الفعلي للحساب
        self.assertEqual(st["account_balance_all_time"]["signed"], "18.5000")
        self.assertEqual(self.balance(self.a["id"], "gold"), "18.5000")

    def test_full_statement_matches_balances_screen(self):
        full = self.statement(self.a["id"], "gold")
        row = reports.balances(self.db, {"q": self.a["account_no"]})["items"][0]
        self.assertEqual(full["closing"]["signed"], row["gold"]["signed"])
        for m in ("diamond", "wage"):
            self.assertEqual(self.statement(self.a["id"], m)["closing"]["signed"], row[m]["signed"])
        # الرصيد الختامي = الافتتاحي + المدين − الدائن
        o = F.parse(full["opening"]["value"], 4)
        dr = F.parse(full["totals"]["debit"], 4)
        cr = F.parse(full["totals"]["credit"], 4)
        self.assertEqual(F.fmt(o + dr - cr, 4), full["closing"]["signed"])

    def test_statements_are_independent(self):
        wage = self.statement(self.a["id"], "wage")
        self.assertEqual(wage["closing"]["signed"], "55.00")           # (20 + 7.5) × 2
        self.assertTrue(all(r["doc_type"] == "sale" for r in wage["rows"]))
        dia = self.statement(self.a["id"], "diamond")
        self.assertEqual(dia["rows"], [])


class S14_NetSold(BaseCase):
    def test_net_sold_after_returns(self):
        a = self.account(rate="3")
        s1 = self.sale(a["id"], [{"run_no": "1", "gold": "10", "diamond": "1"},
                                 {"run_no": "2", "gold": "6"}], date="2026-06-01")
        s2 = self.sale(a["id"], [{"run_no": "3", "gold": "4", "diamond": "0.5"}], date="2026-06-10")
        self.ret(a["id"], s1["id"], [{"original_line_id": s1["lines"][0]["id"], "gold": "2.5", "diamond": "0.25"}],
                 date="2026-06-15")
        self.ret(a["id"], s2["id"], [{"original_line_id": s2["lines"][0]["id"], "gold": "4", "diamond": "0.5"}],
                 date="2026-06-20")
        an = reports.analysis(self.db, {"account_id": a["id"], "date_from": "2026-06-01", "date_to": "2026-06-30"})
        self.assertEqual(an["sales"]["totals"], {"gold": "20.0000", "diamond": "1.500", "wage": "60.00"})
        self.assertEqual(an["returns"]["totals"], {"gold": "6.5000", "diamond": "0.750", "wage": "19.50"})
        self.assertEqual(an["net"]["totals"]["gold"]["signed"], "13.5000")
        self.assertEqual(an["net"]["totals"]["diamond"]["signed"], "0.750")
        self.assertEqual(an["net"]["totals"]["wage"]["signed"], "40.50")
        # الأرقام متطابقة مع شاشة الأرصدة
        self.assertEqual(an["balances"]["gold"]["signed"], self.balance(a["id"], "gold"))
        rows = {r["doc_no"]: r for r in an["net"]["rows"]}
        self.assertEqual(rows["SA-000002"]["net"]["gold"]["signed"], "0.0000")

    def test_unlinked_return_shown_as_exception(self):
        a = self.account(rate="1")
        self.sale(a["id"], [{"run_no": "1", "gold": "5"}])
        docs.post_document(self.db, self.admin, {
            "doc_type": "return", "client_token": token(), "account_id": a["id"], "doc_date": "2026-10-02",
            "unlinked": True, "exception_reason": "مرتجع قديم", "lines": [{"run_no": "Z", "gold": "1"}]})
        an = reports.analysis(self.db, {"account_id": a["id"]})
        self.assertEqual(an["returns"]["unlinked_count"], 1)
        kinds = [r["kind"] for r in an["net"]["rows"]]
        self.assertIn("unlinked", kinds)
        self.assertEqual(an["net"]["totals"]["gold"]["signed"], "4.0000")


class S15_Edit(BaseCase):
    def test_edit_posted_sale_updates_everything(self):
        a = self.account(rate="5")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10"}, {"run_no": "2", "gold": "4", "diamond": "1"}])
        self.assertEqual(self.balance(a["id"], "wage"), "70.00")
        lines = [{"id": s["lines"][0]["id"], "run_no": "1", "gold": "12"},
                 {"run_no": "3", "gold": "1.5", "diamond": "0.2"}]          # حذف السطر 2 وإضافة سطر جديد
        with self.assertRaises(ValidationError):
            docs.edit_document(self.db, self.admin, s["id"], {"lines": lines, "doc_date": "2026-10-01",
                                                              "version": s["version"], "reason": ""})
        e = docs.edit_document(self.db, self.admin, s["id"], {"lines": lines, "doc_date": "2026-10-03",
                                                              "version": s["version"], "reason": "تصحيح وزن"})
        self.assertEqual(e["doc_no"], s["doc_no"])
        self.assertEqual(e["version"], 2)
        self.assertEqual(self.balance(a["id"], "gold"), "13.5000")
        self.assertEqual(self.balance(a["id"], "diamond"), "0.200")
        self.assertEqual(self.balance(a["id"], "wage"), "67.50")
        st = self.statement(a["id"], "gold")
        self.assertEqual([r["run_no"] for r in st["rows"]], ["1", "3"])
        self.assertEqual(st["rows"][0]["date"], "2026-10-03")
        an = reports.analysis(self.db, {"account_id": a["id"]})
        self.assertEqual(an["sales"]["totals"]["gold"], "13.5000")
        hist = [h for h in e["history"] if h["action"] == "edit"][0]
        self.assertEqual(hist["reason"], "تصحيح وزن")
        self.assertIn("10.0000", hist["before"])
        self.assertIn("12.0000", hist["after"])
        # نسخة قديمة → رفض (حماية من التعديل المتزامن)
        with self.assertRaises(Conflict):
            docs.edit_document(self.db, self.admin, s["id"], {"lines": lines, "doc_date": "2026-10-03",
                                                              "version": 1, "reason": "x x x"})
        self.assertTrue(integrity.run_check(self.db, self.admin)["ok"])

    def test_edit_cannot_break_returns(self):
        a = self.account(rate="5")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10"}])
        lid = s["lines"][0]["id"]
        self.ret(a["id"], s["id"], [{"original_line_id": lid, "gold": "6"}])
        s = docs.get_document(self.db, s["id"])
        base = {"doc_date": "2026-10-01", "version": s["version"], "reason": "اختبار"}
        with self.assertRaises(ValidationError):   # إنقاص تحت المرتجع
            docs.edit_document(self.db, self.admin, s["id"], {**base, "lines": [{"id": lid, "run_no": "1", "gold": "5"}]})
        with self.assertRaises(ValidationError):   # حذف سطر عليه مرتجع
            docs.edit_document(self.db, self.admin, s["id"], {**base, "lines": [{"run_no": "9", "gold": "5"}]})
        with self.assertRaises(ValidationError):   # تغيير أجر سطر عليه مرتجع
            docs.edit_document(self.db, self.admin, s["id"],
                               {**base, "lines": [{"id": lid, "run_no": "1", "gold": "10", "rate": "6"}]})
        docs.edit_document(self.db, self.admin, s["id"], {**base, "lines": [{"id": lid, "run_no": "1", "gold": "8"}]})
        self.assertEqual(self.balance(a["id"], "gold"), "2.0000")

    def test_edit_voucher_keeps_its_karat_snapshot(self):
        a = self.account()
        v = self.voucher(a["id"], "receipt", "gold", "100", karat=21)
        settings.change_working_karat(self.db, self.admin, 24, "اختبار")
        e = docs.edit_document(self.db, self.admin, v["id"], {
            "material": "gold", "actual": "90", "karat": 21, "doc_date": "2026-10-06",
            "version": v["version"], "reason": "تصحيح الوزن"})
        self.assertEqual(e["voucher"]["working_karat"], 18)
        self.assertEqual(e["voucher"]["equivalent"], "105.0000")
        self.assertEqual(self.balance(a["id"], "gold"), "-105.0000")

    def test_edit_requires_permission(self):
        a = self.account()
        s = self.sale(a["id"], [{"run_no": "1", "gold": "1"}])
        clerk = self.make_user("clerk", ["docs.post"])
        with self.assertRaises(Forbidden):
            docs.edit_document(self.db, clerk, s["id"], {"lines": [], "version": 1, "reason": "abc"})


class S16_Cancel(BaseCase):
    def test_cancel_keeps_history(self):
        a = self.account(rate="2")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10", "diamond": "1"}])
        c = docs.cancel_document(self.db, self.admin, s["id"], {"reason": "فاتورة مكررة"})
        self.assertEqual(c["status"], "cancelled")
        self.assertEqual(c["cancel_reason"], "فاتورة مكررة")
        for m in ("gold", "diamond", "wage"):
            self.assertEqual(F.parse(self.balance(a["id"], m).lstrip("-"), 4), 0)
        st = self.statement(a["id"], "gold")
        self.assertEqual(len(st["rows"]), 2)                      # الأصل + القيد العكسي
        self.assertTrue(st["rows"][1]["is_reversal"])
        self.assertEqual(st["rows"][1]["credit"], "10.0000")
        self.assertEqual(st["closing"]["signed"], "0.0000")
        self.assertEqual(docs.get_document(self.db, s["id"])["doc_no"], s["doc_no"])   # لا حذف
        an = reports.analysis(self.db, {"account_id": a["id"]})
        self.assertEqual(an["sales"]["count"], 0)
        self.assertEqual(an["cancelled_count"], 1)
        with self.assertRaises(ValidationError):
            docs.cancel_document(self.db, self.admin, s["id"], {"reason": "مرة ثانية"})
        with self.assertRaises(ValidationError):
            docs.edit_document(self.db, self.admin, s["id"], {"lines": [], "version": c["version"], "reason": "abc"})
        self.assertTrue(integrity.run_check(self.db, self.admin)["ok"])

    def test_cannot_cancel_sale_with_returns(self):
        a = self.account()
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10"}])
        r = self.ret(a["id"], s["id"], [{"original_line_id": s["lines"][0]["id"], "gold": "1"}])
        with self.assertRaises(Conflict):
            docs.cancel_document(self.db, self.admin, s["id"], {"reason": "اختبار"})
        docs.cancel_document(self.db, self.admin, r["id"], {"reason": "اختبار"})
        docs.cancel_document(self.db, self.admin, s["id"], {"reason": "اختبار"})
        self.assertEqual(self.balance(a["id"], "gold"), "0.0000")

    def test_cancelled_opening_allows_new_one(self):
        a = self.account()
        o = self.opening(a["id"], [{"material": "wage", "direction": "debit", "actual": "10"}])
        docs.cancel_document(self.db, self.admin, o["id"], {"reason": "خطأ"})
        self.opening(a["id"], [{"material": "wage", "direction": "debit", "actual": "12"}])
        self.assertEqual(self.balance(a["id"], "wage"), "12.00")


class S17_DoublePosting(BaseCase):
    def test_same_request_twice(self):
        a = self.account()
        data = {"doc_type": "sale", "client_token": token(), "account_id": a["id"], "doc_date": "2026-10-01",
                "lines": [{"run_no": "1", "gold": "10"}]}
        d1 = docs.post_document(self.db, self.admin, data)
        d2 = docs.post_document(self.db, self.admin, data)
        self.assertEqual(d1["id"], d2["id"])
        self.assertTrue(d2["duplicate_request"])
        self.assertEqual(self.balance(a["id"], "gold"), "10.0000")

    def test_concurrent_double_click(self):
        a = self.account()
        data = {"doc_type": "receipt", "client_token": token(), "account_id": a["id"], "doc_date": "2026-10-01",
                "material": "gold", "actual": "5", "karat": 21}
        results, errors = [], []

        def worker():
            try:
                results.append(docs.post_document(self.db, self.admin, dict(data))["id"])
            except Exception as e:  # pragma: no cover
                errors.append(e)
            finally:
                self.db.close_all()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)
        self.assertEqual(self.balance(a["id"], "gold"), "-5.8333")

    def test_unique_numbers(self):
        a = self.account()
        nos = {self.sale(a["id"], [{"run_no": str(i), "gold": "1"}])["doc_no"] for i in range(25)}
        self.assertEqual(len(nos), 25)


class S18_Decimals(BaseCase):
    def test_small_weights_and_exact_sums(self):
        a = self.account(rate="0.01")
        lines = [{"run_no": str(i), "gold": "0.1"} for i in range(3)] + [{"run_no": "x", "gold": "0.0001"}]
        s = self.sale(a["id"], lines)
        self.assertEqual(s["totals"]["gold"], "0.3001")          # لا 0.30000000000000004
        self.assertEqual(s["lines"][3]["wage"], "0.00")           # 0.000001 → 0.00
        self.voucher(a["id"], "receipt", "diamond", "0.001")
        self.assertEqual(self.balance(a["id"], "diamond"), "-0.001")
        self.assertEqual(self.balance(a["id"], "gold"), "0.3001")

    def test_rounding_half_up(self):
        self.assertEqual(F.fmt(F.wage_total(F.parse("2.25", 4), F.parse("5.5", 3)), 2), "12.38")
        self.assertEqual(F.fmt(F.wage_total(F.parse("1", 4), F.parse("0.005", 3)), 2), "0.01")
        self.assertEqual(F.fmt(F.wage_total(F.parse("1", 4), F.parse("0.004", 3)), 2), "0.00")
        self.assertEqual(F.round_div(-5, 2), -3)
        self.assertEqual(F.parse("١٢٫٥", 4), 125000)            # أرقام عربية

    def test_large_values(self):
        a = self.account(rate="999.999")
        s = self.sale(a["id"], [{"run_no": "1", "gold": "99999.9999"}])
        self.assertEqual(s["lines"][0]["wage"], "99999899.90")  # 99999.9999 × 999.999 = 99,999,899.9000001
        with self.assertRaises(ValidationError):
            self.sale(a["id"], [{"run_no": "2", "gold": "10000000000"}])


class S20_NoPhantoms(BaseCase):
    def test_integrity_after_full_scenario_and_tamper_detection(self):
        a = self.account(rate="5")
        b = self.account("عميل ثان", rate="3")
        self.opening(a["id"], [{"material": "gold", "direction": "credit", "actual": "100", "karat": 21}])
        s = self.sale(a["id"], [{"run_no": "1", "gold": "10", "diamond": "1"}, {"run_no": "2", "gold": "3"}])
        self.ret(a["id"], s["id"], [{"original_line_id": s["lines"][0]["id"], "gold": "2"}])
        self.voucher(a["id"], "receipt", "gold", "5", karat=22)
        self.voucher(b["id"], "payment", "diamond", "0.5")
        v = self.voucher(b["id"], "receipt", "wage", "10")
        docs.cancel_document(self.db, self.admin, v["id"], {"reason": "اختبار"})
        res = integrity.run_check(self.db, self.admin)
        self.assertTrue(res["ok"], res["issues"])
        with self.db.read() as c:
            n = c.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
        # افتتاحي 1 + بيع (3 + 2) + مرتجع 2 + قبض 1 + صرف 1 + قبض أجور 1 + عكسي 1 = 12
        self.assertEqual(n, 12)
        # كل الأرصدة صفر لحساب بلا حركات
        c3 = self.account("بلا حركة")
        for m in ("gold", "diamond", "wage"):
            self.assertEqual(F.parse(self.balance(c3["id"], m).lstrip("-"), 4), 0)

        # عبث يدوي بالقاعدة يُكتشف ولا يُخفى
        with self.db.write() as c:
            c.execute("""INSERT INTO ledger_entries(doc_id, account_id, entry_date, material, debit_e4, credit_e4,
                         ref_karat, created_at) VALUES (?, ?, '2026-10-01', 'gold', 10000, 0, 18, 'x')""",
                      (s["id"], a["id"]))
        res = integrity.run_check(self.db, self.admin)
        self.assertFalse(res["ok"])
        self.assertTrue(any(i["ref"] == s["doc_no"] for i in res["issues"]))

    def test_ledger_is_immutable(self):
        a = self.account()
        self.sale(a["id"], [{"run_no": "1", "gold": "1"}])
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.write() as c:
                c.execute("UPDATE ledger_entries SET debit_e4 = 1")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.write() as c:
                c.execute("DELETE FROM audit_log")


class Preview(BaseCase):
    def test_preview_shows_before_after_without_saving(self):
        a = self.account(rate="5")
        self.sale(a["id"], [{"run_no": "1", "gold": "10"}])
        p = docs.preview_document(self.db, self.admin, {
            "doc_type": "sale", "account_id": a["id"], "doc_date": "2026-10-02",
            "lines": [{"run_no": "1", "gold": "2.5"}]})
        self.assertEqual(p["balances"]["gold"]["before"], "10.0000")
        self.assertEqual(p["balances"]["gold"]["after"], "12.5000")
        self.assertEqual(p["balances"]["wage"]["after"], "62.50")
        self.assertTrue(any("مسجّل سابقاً" in w for w in p["warnings"]))  # رقم تشغيل مكرر عبر الفواتير
        self.assertEqual(self.balance(a["id"], "gold"), "10.0000")     # لم يُحفظ شيء


if __name__ == "__main__":
    unittest.main()

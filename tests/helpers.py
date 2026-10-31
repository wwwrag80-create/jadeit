"""أدوات مشتركة للاختبارات — كل اختبار يعمل على قاعدة بيانات مؤقتة منفصلة تماماً عن البيانات الحقيقية."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.db import Database  # noqa: E402
from server.services import accounts, auth  # noqa: E402
from server.services import documents as docs  # noqa: E402
from server.services import reports  # noqa: E402


def token() -> str:
    return uuid.uuid4().hex


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jadeit-test-")
        self.db = Database(os.path.join(self.tmp, "test.db"))
        self.admin = auth.setup_first_admin(
            self.db, {"username": "admin", "password": "secret123", "working_karat": 18, "full_name": "المدير"})

    def tearDown(self):
        self.db.close_all()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- مساعدات
    def make_user(self, username, permissions):
        u = auth.create_user(self.db, self.admin, {"username": username, "password": "secret123",
                                                   "full_name": username, "permissions": permissions})
        from server.services.common import Actor
        return Actor(u["id"], u["username"], u["full_name"], False, set(permissions))

    def account(self, name="عميل الاختبار", rate="5.5", **kw):
        return accounts.create_account(self.db, self.admin, {"name": name, "wage_rate": rate,
                                                             "client_token": token(), **kw})

    def sale(self, account_id, lines, date="2026-10-01", actor=None, **kw):
        return docs.post_document(self.db, actor or self.admin, {
            "doc_type": "sale", "client_token": token(), "account_id": account_id, "doc_date": date,
            "lines": lines, **kw})

    def ret(self, account_id, original, lines, date="2026-10-05", actor=None, **kw):
        return docs.post_document(self.db, actor or self.admin, {
            "doc_type": "return", "client_token": token(), "account_id": account_id, "doc_date": date,
            "original_doc_id": original, "lines": lines, **kw})

    def voucher(self, account_id, doc_type, material, actual, karat=None, date="2026-10-06", actor=None, **kw):
        data = {"doc_type": doc_type, "client_token": token(), "account_id": account_id, "doc_date": date,
                "material": material, "actual": actual, **kw}
        if karat is not None:
            data["karat"] = karat
        return docs.post_document(self.db, actor or self.admin, data)

    def opening(self, account_id, lines, date="2026-01-01", actor=None):
        return docs.post_document(self.db, actor or self.admin, {
            "doc_type": "opening", "client_token": token(), "account_id": account_id, "doc_date": date,
            "lines": lines})

    def balance(self, account_id, material) -> str:
        """الرصيد الموقّع (موجب = مدين، سالب = دائن) من ملخص الحساب."""
        return reports.account_summary(self.db, account_id)["sections"][material]["balance"]["signed"]

    def statement(self, account_id, material, **kw):
        return reports.statement(self.db, {"account_id": account_id, "material": material, **kw})

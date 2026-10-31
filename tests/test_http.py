"""اختبارات طبقة HTTP: الإعداد، الدخول، الحماية، الترحيل عبر الشبكة، النسخ الاحتياطي."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
import uuid
from http.cookiejar import CookieJar
from urllib import error, request

import helpers  # noqa: F401  (يضبط مسار الاستيراد)

from server.app import create_server
from server.db import Database

os.environ["JADEIT_QUIET"] = "1"


class Client:
    def __init__(self, base):
        self.base = base
        self.jar = CookieJar()
        self.opener = request.build_opener(request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, body=None, csrf=True, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = request.Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if csrf:
            req.add_header("X-Requested-With", "jadeit")
        try:
            with self.opener.open(req) as resp:
                content = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                return resp.status, (json.loads(content) if "json" in ctype else content)
        except error.HTTPError as e:
            content = e.read()
            return e.code, json.loads(content) if content else None


class HttpCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="jadeit-http-")
        cls.db = Database(os.path.join(cls.tmp, "http.db"))
        cls.server = create_server(cls.db, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.admin = Client(cls.base)
        st, body = cls.admin.call("POST", "/api/setup", {"username": "admin", "password": "secret123",
                                                         "working_karat": 18, "system_name": "اختبار"})
        assert st == 200, body

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_01_setup_only_once_and_status(self):
        st, body = Client(self.base).call("GET", "/api/status")
        self.assertEqual(st, 200)
        self.assertFalse(body["needs_setup"])
        st, body = Client(self.base).call("POST", "/api/setup", {"username": "x", "password": "secret123",
                                                                  "working_karat": 18})
        self.assertEqual(st, 409)

    def test_02_auth_required_and_csrf(self):
        anon = Client(self.base)
        st, body = anon.call("GET", "/api/balances")
        self.assertEqual(st, 401)
        self.assertIn("سجّل الدخول", body["error"]["message"])
        st, _ = self.admin.call("POST", "/api/accounts", {"name": "x"}, csrf=False)
        self.assertEqual(st, 403)
        st, body = anon.call("POST", "/api/login", {"username": "admin", "password": "wrong"})
        self.assertEqual(st, 401)

    def test_03_password_not_stored_plain(self):
        with self.db.read() as c:
            h = c.execute("SELECT password_hash FROM users WHERE username = 'admin'").fetchone()[0]
        self.assertNotIn("secret123", h)
        self.assertTrue(h.startswith("scrypt$"))

    def test_04_full_flow_and_double_post(self):
        st, acc = self.admin.call("POST", "/api/accounts", {"name": "عميل الشبكة", "wage_rate": "4",
                                                            "client_token": uuid.uuid4().hex})
        self.assertEqual(st, 200, acc)
        payload = {"doc_type": "sale", "client_token": uuid.uuid4().hex, "account_id": acc["id"],
                   "doc_date": "2026-10-01", "lines": [{"run_no": "77", "gold": "2.5", "diamond": "0.3"}]}
        results = []

        def post():
            results.append(self.admin.call("POST", "/api/documents", payload))

        threads = [threading.Thread(target=post) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = {body["id"] for st, body in results if st == 200}
        self.assertEqual(len(ids), 1, results)
        st, bal = self.admin.call("GET", f"/api/balances?q={acc['account_no']}")
        self.assertEqual(bal["items"][0]["gold"]["value"], "2.5000")
        self.assertEqual(bal["items"][0]["wage"]["value"], "10.00")
        st, doc = self.admin.call("GET", f"/api/documents/{ids.pop()}")
        self.assertEqual(doc["lines"][0]["run_no"], "77")
        st, found = self.admin.call("GET", "/api/documents?q=77")
        self.assertTrue(any(d["doc_no"] == doc["doc_no"] for d in found))
        st, stt = self.admin.call("GET", f"/api/statement?account_id={acc['id']}&material=gold")
        self.assertEqual(stt["closing"]["value"], "2.5000")

    def test_05_validation_error_shape(self):
        st, body = self.admin.call("POST", "/api/documents", {"doc_type": "sale", "client_token": uuid.uuid4().hex,
                                                              "account_id": 99999, "doc_date": "2026-10-01",
                                                              "lines": [{"gold": "1"}]})
        self.assertEqual(st, 422)
        self.assertEqual(body["error"]["code"], "validation")

    def test_06_permissions_through_http(self):
        st, u = self.admin.call("POST", "/api/users", {"username": "viewer", "password": "secret123",
                                                       "full_name": "مطّلع", "permissions": []})
        self.assertEqual(st, 200, u)
        viewer = Client(self.base)
        st, _ = viewer.call("POST", "/api/login", {"username": "viewer", "password": "secret123"})
        self.assertEqual(st, 200)
        st, body = viewer.call("POST", "/api/accounts", {"name": "ممنوع", "wage_rate": "1",
                                                         "client_token": uuid.uuid4().hex})
        self.assertEqual(st, 403)
        st, _ = viewer.call("GET", "/api/balances")
        self.assertEqual(st, 200)
        st, _ = viewer.call("POST", "/api/settings/karat", {"karat": 21, "reason": "محاولة"})
        self.assertEqual(st, 403)

    def test_07_backup_and_restore(self):
        st, acc = self.admin.call("POST", "/api/accounts", {"name": "قبل النسخة", "wage_rate": "1",
                                                            "client_token": uuid.uuid4().hex})
        st, data = self.admin.call("GET", "/api/backup/download")
        self.assertEqual(st, 200)
        self.assertGreater(len(data), 1024)
        st, acc2 = self.admin.call("POST", "/api/accounts", {"name": "بعد النسخة", "wage_rate": "1",
                                                             "client_token": uuid.uuid4().hex})
        self.assertEqual(st, 200)
        st, res = self.admin.call("POST", "/api/backup/restore", raw=data)
        self.assertEqual(st, 200, res)
        self.assertTrue(res["restored"])
        c = Client(self.base)
        c.call("POST", "/api/login", {"username": "admin", "password": "secret123"})
        st, lst = c.call("GET", "/api/accounts")
        names = [a["name"] for a in lst]
        self.assertIn("قبل النسخة", names)
        self.assertNotIn("بعد النسخة", names)
        st, bad = c.call("POST", "/api/backup/restore", raw=b"x" * 4096)
        self.assertEqual(st, 422)
        type(self).admin = c

    def test_08_static_files(self):
        req = request.Request(self.base + "/")
        with request.urlopen(req) as r:
            html = r.read().decode()
            self.assertIn('dir="rtl"', html)
            self.assertIn("default-src 'self'", r.headers["Content-Security-Policy"])
        with self.assertRaises(error.HTTPError):
            request.urlopen(self.base + "/../server/db.py")


if __name__ == "__main__":
    unittest.main()

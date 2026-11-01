"""خادم HTTP مبني على مكتبة بايثون القياسية فقط (بدون أي اعتماديات خارجية).

• واجهة JSON تحت /api/ ، وملفات الواجهة الثابتة من مجلد web/.
• الجلسة في كوكي HttpOnly + SameSite=Strict، وكل طلب كتابة يجب أن يحمل
  الترويسة X-Requested-With: jadeit (حماية إضافية من CSRF).
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import sys
import traceback
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .errors import AppError, Conflict, Unauthorized
from .services import accounts as acc_svc
from .services import auth as auth_svc
from .services import backup as backup_svc
from .services import documents as doc_svc
from .services import integrity as integ_svc
from .services import reports as rep_svc
from .services import settings as set_svc
from .services.common import DOC_TYPES, MATERIALS, PERMISSIONS

def _resource_root():
    """جذر ملفات البرنامج: مجلد المشروع، أو مجلد الاستخراج المؤقت في الملف التنفيذي المستقل (PyInstaller)."""
    base = getattr(sys, "_MEIPASS", None)
    return base if base else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


WEB_DIR = os.path.join(_resource_root(), "web")
MAX_JSON = 5 * 1024 * 1024
MAX_UPLOAD = 500 * 1024 * 1024
COOKIE = "jadeit_sid"

# أنواع المحتوى ثابتة هنا ولا تُقرأ من سجل ويندوز: على بعض أجهزة ويندوز 7/10 يربط السجل
# امتداد .js بالنوع text/plain فيرفض المتصفح تحميل وحدات الواجهة.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".svg": "image/svg+xml",
}


class Request:
    def __init__(self, method, path, query, headers, body, client):
        self.method = method
        self.path = path
        self.query = query
        self.headers = headers
        self.body = body
        self.client = client
        self.params = {}
        self.actor = None
        self.token = None
        self._json = None

    def json(self) -> dict:
        if self._json is None:
            if not self.body:
                self._json = {}
            else:
                try:
                    self._json = json.loads(self.body.decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    raise AppError("صيغة البيانات المرسلة غير صحيحة", code="bad_json")
                if not isinstance(self._json, dict):
                    raise AppError("صيغة البيانات المرسلة غير صحيحة", code="bad_json")
        return self._json


class Response:
    def __init__(self, status=200, body=None, headers=None, raw: bytes | None = None,
                 content_type="application/json; charset=utf-8"):
        self.status = status
        self.body = body
        self.headers = headers or {}
        self.raw = raw
        self.content_type = content_type


class App:
    def __init__(self, db):
        self.db = db
        self.routes = []
        self._register()

    def route(self, method, pattern, public=False):
        def param(m):
            name = m.group(1)
            return f"(?P<{name}>\\d+)" if name == "id" else f"(?P<{name}>[^/]+)"
        regex = re.compile("^" + re.sub(r"\{(\w+)\}", param, pattern) + "$")

        def deco(fn):
            self.routes.append((method, regex, fn, public))
            return fn
        return deco

    # ------------------------------------------------------------------ المسارات
    def _register(self):
        db = self.db
        r = self.route

        def session_cookie(token, max_age):
            # يُبنى يدوياً لأن سمة SameSite غير مدعومة في http.cookies قبل بايثون 3.8 (ويندوز 7)
            return {"Set-Cookie": f"{COOKIE}={token}; Path=/; Max-Age={int(max_age)}; HttpOnly; SameSite=Strict"}

        def boot(actor):
            return {
                "me": actor.to_dict(),
                "settings": set_svc.get_settings(db),
                "permissions": PERMISSIONS,
                "doc_types": DOC_TYPES,
                "materials": MATERIALS,
            }

        @r("GET", "/api/status", public=True)
        def status(req):
            s = set_svc.get_settings(db)
            return {"needs_setup": auth_svc.needs_setup(db), "system_name": s["system_name"],
                    "logged_in": req.actor is not None}

        @r("POST", "/api/setup", public=True)
        def setup(req):
            actor = auth_svc.setup_first_admin(db, req.json())
            token, actor = auth_svc.login(db, req.json().get("username"), req.json().get("password"), req.client)
            return Response(200, boot(actor), headers=session_cookie(token, auth_svc.SESSION_HOURS * 3600))

        @r("POST", "/api/login", public=True)
        def login(req):
            data = req.json()
            token, actor = auth_svc.login(db, data.get("username"), data.get("password"), req.client)
            return Response(200, boot(actor), headers=session_cookie(token, auth_svc.SESSION_HOURS * 3600))

        @r("POST", "/api/logout", public=True)
        def logout(req):
            auth_svc.logout(db, req.token)
            return Response(200, {"ok": True}, headers=session_cookie("", 0))

        @r("GET", "/api/bootstrap")
        def bootstrap(req):
            return boot(req.actor)

        # ---------------- الإعدادات والمستخدمون
        @r("GET", "/api/settings")
        def settings_get(req):
            return set_svc.get_settings(db)

        @r("GET", "/api/settings/karat-history")
        def karat_hist(req):
            return set_svc.karat_history(db)

        @r("POST", "/api/settings/karat")
        def karat_change(req):
            d = req.json()
            return set_svc.change_working_karat(db, req.actor, d.get("karat"), d.get("reason"))

        @r("POST", "/api/settings/general")
        def settings_general(req):
            return set_svc.update_general(db, req.actor, req.json())

        @r("GET", "/api/users")
        def users_list(req):
            return auth_svc.list_users(db, req.actor)

        @r("POST", "/api/users")
        def users_create(req):
            return auth_svc.create_user(db, req.actor, req.json())

        @r("PUT", "/api/users/{id}")
        def users_update(req):
            return auth_svc.update_user(db, req.actor, int(req.params["id"]), req.json())

        @r("POST", "/api/me/password")
        def me_password(req):
            d = req.json()
            auth_svc.change_own_password(db, req.actor, d.get("current"), d.get("new"))
            return {"ok": True}

        # ---------------- الحسابات
        @r("GET", "/api/accounts")
        def accounts_list(req):
            return acc_svc.list_accounts(db, req.query.get("q", ""), req.query.get("active") != "1")

        @r("GET", "/api/accounts/next-no")
        def accounts_next(req):
            return {"account_no": acc_svc.next_account_no(db)}

        @r("GET", "/api/accounts/check-name")
        def accounts_check(req):
            ex = req.query.get("exclude")
            return acc_svc.check_name(db, req.query.get("name", ""), int(ex) if ex else None)

        @r("POST", "/api/accounts")
        def accounts_create(req):
            return acc_svc.create_account(db, req.actor, req.json())

        @r("GET", "/api/accounts/{id}")
        def accounts_get(req):
            return acc_svc.get_account(db, int(req.params["id"]))

        @r("PUT", "/api/accounts/{id}")
        def accounts_update(req):
            return acc_svc.update_account(db, req.actor, int(req.params["id"]), req.json())

        @r("GET", "/api/accounts/{id}/summary")
        def accounts_summary(req):
            return rep_svc.account_summary(db, int(req.params["id"]))

        @r("GET", "/api/accounts/{id}/sale-invoices")
        def accounts_invoices(req):
            return doc_svc.sale_invoices_for_account(db, int(req.params["id"]), req.query.get("q", ""))

        # ---------------- المستندات
        @r("GET", "/api/documents")
        def docs_search(req):
            return doc_svc.search_documents(db, req.query)

        @r("GET", "/api/documents/next-no")
        def docs_next(req):
            return {"doc_no": doc_svc.next_doc_no(db, req.query.get("type", ""))}

        @r("GET", "/api/documents/by-no/{no}")
        def docs_by_no(req):
            return doc_svc.get_document_by_no(db, unquote(req.params["no"]))

        @r("POST", "/api/documents/preview")
        def docs_preview(req):
            return doc_svc.preview_document(db, req.actor, req.json())

        @r("POST", "/api/documents")
        def docs_post(req):
            return doc_svc.post_document(db, req.actor, req.json())

        @r("GET", "/api/documents/{id}")
        def docs_get(req):
            return doc_svc.get_document(db, int(req.params["id"]))

        @r("PUT", "/api/documents/{id}")
        def docs_edit(req):
            return doc_svc.edit_document(db, req.actor, int(req.params["id"]), req.json())

        @r("POST", "/api/documents/{id}/preview")
        def docs_edit_preview(req):
            return doc_svc.preview_document(db, req.actor, req.json(), int(req.params["id"]))

        @r("POST", "/api/documents/{id}/cancel")
        def docs_cancel(req):
            return doc_svc.cancel_document(db, req.actor, int(req.params["id"]), req.json())

        @r("GET", "/api/documents/{id}/returnable")
        def docs_returnable(req):
            ex = req.query.get("exclude")
            return doc_svc.returnable_lines(db, int(req.params["id"]), int(ex) if ex else None)

        # ---------------- التقارير
        @r("GET", "/api/balances")
        def balances(req):
            return rep_svc.balances(db, req.query)

        @r("GET", "/api/statement")
        def statement(req):
            return rep_svc.statement(db, req.query)

        @r("GET", "/api/analysis")
        def analysis(req):
            return rep_svc.analysis(db, req.query)

        # ---------------- النظام
        @r("GET", "/api/integrity")
        def integrity(req):
            return integ_svc.run_check(db, req.actor)

        @r("GET", "/api/audit")
        def audit_list(req):
            return backup_svc.list_audit(db, req.actor, req.query)

        @r("GET", "/api/backups")
        def backups(req):
            return backup_svc.list_backups(db, req.actor)

        @r("GET", "/api/backup/download")
        def backup_download(req):
            name, data = backup_svc.make_download(db, req.actor)
            return Response(200, raw=data, content_type="application/octet-stream",
                            headers={"Content-Disposition": f'attachment; filename="{name}"'})

        @r("POST", "/api/backup/restore")
        def backup_restore(req):
            result = backup_svc.restore(db, req.actor, req.body)
            return Response(200, result, headers=session_cookie("", 0))

    # ------------------------------------------------------------------ التوجيه
    def dispatch(self, req: Request) -> Response:
        cookie_header = req.headers.get("Cookie")
        if cookie_header:
            jar = cookies.SimpleCookie()
            try:
                jar.load(cookie_header)
                if COOKIE in jar:
                    req.token = jar[COOKIE].value or None
            except cookies.CookieError:
                pass
        try:
            for method, regex, fn, public in self.routes:
                m = regex.match(req.path)
                if not m:
                    continue
                if method != req.method:
                    continue
                req.params = m.groupdict()
                if req.method != "GET" and req.headers.get("X-Requested-With") != "jadeit":
                    raise AppError("طلب غير مسموح", code="csrf", status=403)
                req.actor = auth_svc.actor_from_token(self.db, req.token)
                if not public and req.actor is None:
                    raise Unauthorized("انتهت الجلسة أو لم تسجّل الدخول. سجّل الدخول مجدداً")
                result = fn(req)
                return result if isinstance(result, Response) else Response(200, result)
            if any(regex.match(req.path) for _, regex, _, _ in self.routes):
                return Response(405, {"error": {"code": "method", "message": "طريقة الطلب غير مسموحة"}})
            return Response(404, {"error": {"code": "not_found", "message": "المسار غير موجود"}})
        except AppError as e:
            return Response(e.status, {"error": e.to_dict()})
        except sqlite3.IntegrityError as e:
            traceback.print_exc()
            err = Conflict("تعارض مع بيانات موجودة، لم يُحفظ شيء. أعد المحاولة", {"db": str(e)})
            return Response(err.status, {"error": err.to_dict()})
        except Exception:
            traceback.print_exc()
            return Response(500, {"error": {"code": "server",
                                            "message": "حدث خطأ غير متوقع في الخادم، لم يُحفظ أي تغيير"}})


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    # 'unsafe-eval' مطلوب لمترجم قوالب Vue داخل المتصفح؛ لا يُسمح بأي مصدر خارجي.
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; "
                               "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'self'",
}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Jadeit"
        sys_version = ""
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            # في التطبيق المكتبي (pythonw) لا توجد نافذة أوامر: sys.stderr قد يكون None
            if os.environ.get("JADEIT_QUIET") or sys.stderr is None:
                return
            try:
                super().log_message(fmt, *args)
            except Exception:
                pass

        def _send(self, status, body: bytes, content_type, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _api(self, method):
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            limit = MAX_UPLOAD if parsed.path == "/api/backup/restore" else MAX_JSON
            if length > limit:
                self._send(413, json.dumps({"error": {"code": "too_large", "message": "حجم الطلب كبير جداً"}},
                                           ensure_ascii=False).encode(), "application/json; charset=utf-8")
                return
            body = self.rfile.read(length) if length else b""
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            req = Request(method, parsed.path, query, self.headers, body, self.client_address[0])
            resp = app.dispatch(req)
            headers = {"Cache-Control": "no-store", **resp.headers}
            if resp.raw is not None:
                self._send(resp.status, resp.raw, resp.content_type, headers)
            else:
                payload = json.dumps(resp.body, ensure_ascii=False).encode("utf-8")
                self._send(resp.status, payload, resp.content_type, headers)

        def _static(self):
            parsed = urlparse(self.path)
            rel = unquote(parsed.path).lstrip("/") or "index.html"
            full = os.path.realpath(os.path.join(WEB_DIR, rel))
            if not full.startswith(os.path.realpath(WEB_DIR) + os.sep) or not os.path.isfile(full):
                # تطبيق صفحة واحدة: أي مسار غير موجود يعيد الصفحة الرئيسية
                if "." in os.path.basename(rel):
                    self._send(404, "غير موجود".encode(), "text/plain; charset=utf-8")
                    return
                full = os.path.join(WEB_DIR, "index.html")
            st = os.stat(full)
            etag = f'"{int(st.st_mtime)}-{st.st_size}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            ext = os.path.splitext(full)[1].lower()
            ctype = CONTENT_TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
            with open(full, "rb") as f:
                data = f.read()
            self._send(200, data, ctype, {"ETag": etag, "Cache-Control": "no-cache"})

        def do_GET(self):
            if self.path.startswith("/api/"):
                self._api("GET")
            else:
                self._static()

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            self._api("POST")

        def do_PUT(self):
            self._api("PUT")

        def do_DELETE(self):
            self._api("DELETE")

    return Handler


def create_server(db, host="127.0.0.1", port=8080) -> ThreadingHTTPServer:
    app = App(db)
    server = ThreadingHTTPServer((host, port), make_handler(app))
    server.daemon_threads = True
    return server

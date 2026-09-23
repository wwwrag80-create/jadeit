# -*- coding: utf-8 -*-
"""
جاديت — عميل Supabase لبرنامج سطح المكتب (مصادقة + استدعاء دوال)
================================================================

يستخدم urllib من المكتبة القياسية فقط: صفر حزم خارجية، فلا يكبر ملف exe
ولا تتعطل المصادقة بسبب تعارض إصدارات httpx/supabase.

⚠️ لا يُخزَّن أي شيء على القرص هنا إطلاقاً.
   رمز الدخول (JWT) يبقى في ذاكرة البرنامج فقط ويختفي بإغلاقه.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_ANON_KEY = "PUT-YOUR-ANON-KEY-HERE"

HTTP_TIMEOUT = 25


class AuthError(Exception):
    """خطأ مصادقة برسالة عربية جاهزة للعرض للمستخدم"""


class NetworkError(Exception):
    """تعذّر الوصول للخادم (انقطاع إنترنت أو الخادم متوقف)"""


class SupabaseAPI:
    """اتصال واحد بـ Supabase: تسجيل الدخول، تجديد الرمز، واستدعاء الدوال."""

    def __init__(self, url=None, anon_key=None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.anon_key = anon_key or SUPABASE_ANON_KEY

        self.access_token = None
        self.refresh_token = None
        self.expires_at = 0
        self.user_id = None
        self.email = None

        self.tenant_id = None
        self.business_name = None
        self.role = None
        self.can_edit = True
        self.sync_enabled = True

        self._lock = threading.Lock()

    # ------------------------------------------------------------ المصادقة
    def sign_in(self, email, password):
        """تسجيل الدخول ببريد وكلمة مرور. يرجع بيانات الجلسة أو يرمي خطأً واضحاً."""
        email = (email or "").strip()
        if not email or not password:
            raise AuthError("الرجاء إدخال البريد الإلكتروني وكلمة المرور.")

        data = self._request(
            "POST",
            f"{self.url}/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
            auth=False,
        )

        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")
        self.expires_at = time.time() + int(data.get("expires_in") or 3600)
        self.user_id = (data.get("user") or {}).get("id")
        self.email = email

        if not self.access_token:
            raise AuthError("تعذّر إنشاء الجلسة. حاول مرة أخرى.")

        return self.load_session()

    def load_session(self):
        """يجلب بيانات المصنع المرتبط بالحساب بعد نجاح الدخول."""
        rows = self.rpc("my_session", {})
        if not rows:
            raise AuthError(
                "الحساب موجود لكنه غير مربوط بأي مصنع.\n"
                "تواصل مع الإدارة لربط حسابك."
            )

        row = rows[0] if isinstance(rows, list) else rows
        self.tenant_id = row.get("tenant_id")
        self.business_name = row.get("business_name") or ""
        self.role = row.get("user_role") or "owner"
        self.can_edit = bool(row.get("can_edit", True))
        self.sync_enabled = bool(row.get("sync_enabled", True))

        if not row.get("is_active", True):
            raise AuthError("هذا الحساب موقوف حالياً. تواصل مع الإدارة.")

        if not self.tenant_id:
            raise AuthError(
                "هذا حساب إدارة عامة وليس حساب مصنع.\n"
                "استخدم لوحة التحكم على الويب بدل برنامج سطح المكتب."
            )

        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "business_name": self.business_name,
            "role": self.role,
            "can_edit": self.can_edit,
            "sync_enabled": self.sync_enabled,
        }

    def ensure_fresh(self):
        """يجدّد الرمز قبل انتهائه بدقيقتين حتى لا تنقطع المزامنة أثناء العمل."""
        with self._lock:
            if not self.refresh_token or time.time() < self.expires_at - 120:
                return
            try:
                data = self._request(
                    "POST",
                    f"{self.url}/auth/v1/token?grant_type=refresh_token",
                    {"refresh_token": self.refresh_token},
                    auth=False,
                )
                if data.get("access_token"):
                    self.access_token = data["access_token"]
                    self.refresh_token = data.get("refresh_token") or self.refresh_token
                    self.expires_at = time.time() + int(data.get("expires_in") or 3600)
            except Exception:
                # فشل التجديد لا يوقف البرنامج — المزامنة تعيد المحاولة لاحقاً
                pass

    def sign_out(self):
        self.access_token = None
        self.refresh_token = None
        self.tenant_id = None
        self.expires_at = 0

    @property
    def is_signed_in(self):
        return bool(self.access_token and self.tenant_id)

    # ---------------------------------------------------------- استدعاء RPC
    def rpc(self, function_name, payload=None):
        self.ensure_fresh()
        return self._request(
            "POST",
            f"{self.url}/rest/v1/rpc/{function_name}",
            payload if payload is not None else {},
        )

    # ------------------------------------------------------------------ HTTP
    def _request(self, method, url, payload=None, auth=True):
        headers = {
            "apikey": self.anon_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        token = self.access_token if (auth and self.access_token) else self.anon_key
        headers["Authorization"] = f"Bearer {token}"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method, headers=headers)

        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8").strip()
                return json.loads(raw) if raw else None

        except urllib.error.HTTPError as e:
            raise self._http_error(e) from e

        except urllib.error.URLError as e:
            raise NetworkError(
                "تعذّر الاتصال بالخادم.\nتأكد من اتصال الإنترنت ثم حاول مرة أخرى."
            ) from e

        except TimeoutError as e:
            raise NetworkError("انتهت مهلة الاتصال بالخادم. تحقق من سرعة الإنترنت.") from e

    @staticmethod
    def _http_error(e):
        """يحوّل خطأ HTTP إلى رسالة عربية تقول للمستخدم ماذا يفعل."""
        detail = ""
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            pass

        try:
            parsed = json.loads(detail)
            code = parsed.get("error_code") or parsed.get("code") or ""
            msg = parsed.get("msg") or parsed.get("message") or parsed.get("error_description") or ""
        except Exception:
            code, msg = "", detail[:200]

        text = f"{code} {msg}".strip()

        if "invalid_credentials" in text or "Invalid login" in text:
            return AuthError("البريد الإلكتروني أو كلمة المرور غير صحيحة.")
        if "email_not_confirmed" in text or "Email not confirmed" in text:
            return AuthError("البريد الإلكتروني غير مُفعّل. تواصل مع الإدارة لتفعيله.")
        if "over_request_rate_limit" in text or e.code == 429:
            return AuthError("محاولات كثيرة متتالية. انتظر دقيقة ثم حاول مرة أخرى.")
        if "غير مصرّح" in text or e.code == 403:
            return AuthError("هذا الحساب غير مصرّح له بالوصول لهذه البيانات.")
        if e.code >= 500:
            return NetworkError("الخادم غير متاح مؤقتاً. حاول بعد قليل.")
        if e.code == 401:
            return AuthError("انتهت صلاحية الجلسة. سجّل الدخول من جديد.")

        return AuthError(msg or f"خطأ من الخادم (رمز {e.code}).")

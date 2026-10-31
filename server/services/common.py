"""أدوات مشتركة: المستخدم المنفّذ والصلاحيات، توحيد النصوص، التواريخ، سجل التدقيق."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from ..db import utcnow
from ..errors import Forbidden, ValidationError

PERMISSIONS = {
    "accounts.manage": "إنشاء الحسابات وتعديل بياناتها",
    "accounts.wage": "تعديل الأجر الافتراضي للحساب",
    "docs.post": "ترحيل المبيعات والمرتجعات وسندات القبض والصرف",
    "docs.rate_override": "تعديل الأجر المعتمد لسطر معيّن",
    "docs.unlinked_return": "مرتجع غير مرتبط بفاتورة أصلية (استثناء)",
    "docs.edit": "تعديل المستندات المرحّلة",
    "docs.cancel": "إلغاء المستندات المرحّلة",
    "opening.manage": "إدخال وتعديل الأرصدة الافتتاحية",
    "settings.manage": "تغيير عيار العمل والإعدادات العامة",
    "users.manage": "إدارة المستخدمين والصلاحيات",
    "system.backup": "النسخ الاحتياطي والاستعادة وفحص سلامة البيانات",
}

# صلاحيات مقترحة للمحاسب عند إنشاء مستخدم جديد
ACCOUNTANT_DEFAULTS = ["accounts.manage", "docs.post", "opening.manage"]

DOC_TYPES = {
    "sale": "فاتورة مبيعات",
    "return": "مرتجع مبيعات",
    "receipt": "سند قبض",
    "payment": "سند صرف",
    "opening": "رصيد افتتاحي",
}
DOC_PREFIX = {"sale": "SA", "return": "SR", "receipt": "RV", "payment": "PV", "opening": "OB"}
MATERIALS = {"gold": "الذهب", "diamond": "الألماس", "wage": "الأجور"}


@dataclass
class Actor:
    id: int
    username: str
    full_name: str
    is_admin: bool = False
    permissions: set = field(default_factory=set)

    def can(self, perm: str) -> bool:
        return self.is_admin or perm in self.permissions

    def require(self, perm: str, message: str | None = None):
        if not self.can(perm):
            raise Forbidden(message or f"لا تملك صلاحية: {PERMISSIONS.get(perm, perm)}")

    def to_dict(self):
        perms = sorted(PERMISSIONS) if self.is_admin else sorted(self.permissions)
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "is_admin": self.is_admin,
            "permissions": perms,
        }


# ------------------------------------------------------------------ النصوص
_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_SPACES = re.compile(r"\s+")


def clean_text(value, max_len: int = 500) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r\n", "\n").strip()
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    return text[:max_len]


def clean_line(value, max_len: int = 200) -> str:
    """نص سطر واحد: يزيل المسافات المكررة وأسطر الانتقال."""
    return _SPACES.sub(" ", clean_text(value, max_len * 2)).strip()[:max_len]


def name_key(name: str) -> str:
    """مفتاح مقارنة الأسماء لمنع التكرار.

    القواعد: تجاهل المسافات الزائدة، التشكيل، التطويل؛ توحيد (أ إ آ ٱ ← ا)،
    (ة ← ه)، (ى ← ي)، (ؤ ← و)، (ئ ← ي)؛ وعدم التمييز بين الأحرف اللاتينية الكبيرة والصغيرة.
    """
    text = unicodedata.normalize("NFKC", clean_line(name))
    text = _DIACRITICS.sub("", text)
    text = (
        text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
        .replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    )
    return _SPACES.sub(" ", text).strip().casefold()


def parse_date(value, label: str = "التاريخ") -> str:
    text = clean_line(value, 20)
    try:
        d = date.fromisoformat(text)
    except ValueError:
        raise ValidationError(f"{label}: صيغة التاريخ غير صحيحة (المطلوب سنة-شهر-يوم)")
    if d.year < 1900 or d.year > 2200:
        raise ValidationError(f"{label}: سنة غير منطقية")
    return d.isoformat()


def optional_date(value, label: str):
    if value in (None, ""):
        return None
    return parse_date(value, label)


def client_token(value) -> str:
    token = clean_line(value, 80)
    if not re.fullmatch(r"[A-Za-z0-9_\-]{8,80}", token or ""):
        raise ValidationError("مفتاح العملية غير صالح، أعد تحميل الصفحة")
    return token


# ------------------------------------------------------------------ التدقيق
def audit(c, actor: Actor | None, action: str, entity: str, entity_id=None, ref: str = "",
          reason: str = "", before=None, after=None):
    c.execute(
        """INSERT INTO audit_log(at, user_id, action, entity, entity_id, ref, reason, before_json, after_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            utcnow(),
            actor.id if actor else None,
            action,
            entity,
            entity_id,
            ref,
            reason,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
        ),
    )


def get_setting(c, key: str) -> str:
    row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else ""


def working_karat(c) -> int:
    return int(get_setting(c, "working_karat") or 18)

import os
import io
import sys
import shutil
import base64
import datetime
import calendar
import contextlib
import sqlite3
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
import customtkinter as ctk
from PIL import Image

# ================= مكتبات توليد فواتير PDF وعرضها بالعربية (اختيارية، لا توقف البرنامج إن غابت) =================
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SHAPING_AVAILABLE = True
except ImportError:
    ARABIC_SHAPING_AVAILABLE = False

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ================= الربط بالسحابة (Supabase) — اختياري بالكامل، لا يوقف البرنامج إن غاب الإنترنت أو المكتبة =================
import re
import hashlib
import threading
import json

SUPABASE_URL = "https://ttpqksvtnhoulghgovob.supabase.co"
SUPABASE_PUBLISHABLE_KEY = "sb_publishable_ymRG7rKUf-704V3j1bNwgg_b1IvlMlX"


def _load_admin_secret_key():
    """يقرأ المفتاح السري لنسخة المدير من خارج الكود — لا يُكتب في الملف أبداً.

    ⚠️ هذا المفتاح يمنح صلاحيات كاملة على بيانات كل العملاء (يتخطى كل الحمايات).
    كتابته داخل الكود تعني تسريبه مع أي نسخة أو رفع للمستودع، لذلك يُقرأ من:
      ١) متغيّر البيئة JADEITE_SUPABASE_SECRET_KEY، أو
      ٢) ملف admin_secret.key بجانب البرنامج (مستبعد من git في .gitignore).
    بدونهما تعمل نسخة المدير بلا صلاحيات إدارية وتظهر رسالة واضحة عند الحاجة.
    """
    key = os.environ.get("JADEITE_SUPABASE_SECRET_KEY", "").strip()
    if key:
        return key
    folders = [os.path.dirname(os.path.abspath(sys.argv[0] or "."))]
    try:
        folders.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    for folder in folders:
        try:
            with open(os.path.join(folder, "admin_secret.key"), encoding="utf-8") as f:
                key = f.read().strip()
            if key:
                return key
        except OSError:
            continue
    return ""


SUPABASE_SECRET_KEY = ""   # مُزال عمداً من نسخة العميل (يتخطى كل الحمايات)

# ================= وحدات المزامنة السحابية =================
try:
    from gold_price import GoldPriceWatcher
    GOLD_PRICE_AVAILABLE = True
except Exception:
    GoldPriceWatcher = None
    GOLD_PRICE_AVAILABLE = False

try:
    from cloud_sync import CloudSync, install_sync_schema
    from sync_down import sync_down
    SYNC_AVAILABLE = True
except Exception as _sync_err:      # noqa: F841
    # غياب وحدات المزامنة لا يمنع البرنامج من العمل محلياً
    CloudSync = None
    install_sync_schema = None
    sync_down = None
    SYNC_AVAILABLE = False


class _RpcBridge:
    """يمرّر استدعاءات المزامنة لعميل Supabase الموجود أصلاً في البرنامج،
    ويحقن رمز المزامنة المحفوظ في الذاكرة (بدون أي ملف على القرص)."""

    def __init__(self, sb_client, sync_token=None):
        self._sb = sb_client
        self.sync_token = sync_token

    def rpc(self, name, payload=None):
        params = dict(payload or {})
        if "p_token" in params and params["p_token"] is None:
            params["p_token"] = self.sync_token
        res = self._sb.rpc(name, params).execute()
        return res.data


ADMIN_USERNAME = "admin"
# كلمة مرور لوحة المدير المحلية: غيّرها بمتغيّر البيئة JADEITE_ADMIN_PASSWORD
# (القيمة الافتراضية admin معروفة لكل من يقرأ هذا الكود)
ADMIN_PASSWORD = os.environ.get("JADEITE_ADMIN_PASSWORD", "").strip() or "admin"
APP_VERSION = "1.43.0"

# ══════════════════════════════════════════════════════════════════════════
#  نوع النسخة — يضبطه make_client_build.py تلقائياً
#
#  True  = نسخة المدير: سحابية بحتة. لا تعتمد على قاعدة الجهاز المحلية إطلاقاً،
#          بل تمسح النسخة المؤقتة وتسحب أحدث نسخة سحابية للعميل في كل دخول،
#          سواء بانتحال الشخصية أو بتسجيل الدخول بحساب العميل مباشرة.
#  False = نسخة العميل: تستعيد بياناتها المحلية أولاً ثم ترفعها للسحابة.
# ══════════════════════════════════════════════════════════════════════════
IS_ADMIN_BUILD = False   # نسخة العميل: تستعيد بياناتها المحلية ثم ترفعها

# نسب المسموح — معرّفة هنا في مكان واحد لتبقى شاشة صناديق الخياس
# وكشف حركة المصنعين/المركبين متطابقتين دائماً
# علامة الاتجاه من اليسار لليمين: تُجبر النص المختلط على عرض الأرقام
# بالصيغة الإنجليزية (5) بدل العربية الهندية (٥) داخل الجمل العربية
LTR_MARK = "\u200e"


def en(value, decimals=2, thousands=True):
    """يُنسّق رقماً بالصيغة الإنجليزية ويثبّت اتجاهه داخل النص العربي"""
    try:
        num = float(value or 0)
    except (TypeError, ValueError):
        return LTR_MARK + "0.00"
    fmt = "{:,.%df}" % decimals if thousands else "{:.%df}" % decimals
    return LTR_MARK + fmt.format(num)


ALLOWANCE_8 = 0.008    # ٨ بالألف
ALLOWANCE_4 = 0.004    # ٤ بالألف

# الحالات التي تُحتسب في الأرصدة (نفس الفلتر في كل الشاشات وفي السحابة):
# SETTLED = حركات قسم أُقفلت فترته بالأرشفة القديمة، MEMO = سطر معلوماتي
COUNTED_STATUSES = ("ACTIVE", "SETTLED_INOUT")
# علامات تمييز حركات خياس الطقوم داخل حقل trees_count (المستخدم كعلامة داخلية
# في هذا النظام أصلاً): تفصل خياس التلميع النهائي عن خياس البوليش عن الصافي
# دون إضافة عمود جديد لقاعدة البيانات — فتبقى نسخ العملاء القديمة متوافقة.
KHAYAS_MARK_FINAL = 0.0    # خياس التلميع النهائي (القيمة التاريخية الافتراضية)
KHAYAS_MARK_POLISH = 7.0   # خياس البوليش
KHAYAS_MARK_NET = 9.0      # صافي الطقم (سطر معلوماتي لا يؤثر على الخزينة)
# عدد الصفوف التي تُقاس لتحديد عرض الأعمدة (لا تُقاس كل الصفوف: القياس
# الكامل يستدعي measure() آلاف المرات فيبطئ فتح الشاشات بشكل ملحوظ)
FIT_SAMPLE_ROWS = 60

KHAYAS_MARK_ASSEMBLER = 5.0  # خياس المركب (مأخوذ من مراحل التصنيع، معلوماتي هنا)

# ══════════════════════════════════════════════════════════════════════════
#  حالة السطور المعلوماتية (Memo)
#
#  كل فلاتر النظام المحاسبية مكتوبة هكذا:
#      if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
#  لذلك أي حالة خارج هاتين تُستبعد تلقائياً من: رصيد الخزينة، كشف حسابها،
#  أرصدة المواد، صناديق الخياس، الفواقد، والتقارير — بلا تعديل أي منها.
#
#  تُستخدم لسطور تُحفظ مع الفاتورة للعرض وإعادة البناء فقط:
#  خياس البوليش، وخياس المركب (محمّل أصلاً على صندوق المركبين)، وصافي الطقم.
# ══════════════════════════════════════════════════════════════════════════
MEMO_STATUS = "MEMO"

# الحالات التي تُقرأ عند إعادة بناء فاتورة مبيعات أو حذفها
SALE_READ_STATUSES = ("ACTIVE", "SETTLED_INOUT", MEMO_STATUS)

RAJI_PURITY = 750.0    # عيار المرجع لتحويل السلك الراجع (الراجع/عيار = سلك_راجع × عيار ÷ 750)


def sale_net_weight(row):
    """صافي الطقم = (الفصوص + الأحجار بعد الخصم)
                     − خياس التلميع النهائي − خياس البوليش − خياس المركب.

    الفصوص والأحجار بعد الخصم قيمة تُجمع، والخياسات الثلاثة فاقد يُخصم منها.
    الذهب والأحجار الخام والماس خارج المعادلة عمداً حسب التعريف المعتمد.

    مصدر واحد للحساب يستخدمه: جدول السطور المعلّقة، قالب الطباعة، وصندوق
    خياس الطقوم — فلا يختلف الرقم بين شاشة وأخرى مهما تغيّرت المعادلة لاحقاً.
    """
    def val(key):
        try:
            return float(row.get(key, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return round(val("فصوص") + val("أحجار بعد الخصم")
                 - val("خياس") - val("خياس البوليش") - val("خياس المركب"), 2)


def raji_ayar(wire_back, karat):
    """يحوّل وزن السلك الراجع لمعادله بعيار ٧٥٠ حسب العيار المُقاس فعلياً"""
    try:
        return round((float(wire_back or 0) * float(karat or 0)) / RAJI_PURITY, 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

# ================= مجلد بيانات النظام الموحّد على القرص المحلي =================
# كل ما ينتجه البرنامج (قاعدة البيانات، النسخ الاحتياطية، ملفات PDF، السجلات، جلسة الجهاز)
# يُحفظ داخل مجلد واحد منظّم في بيانات التطبيقات المحلية للمستخدم، فلا يتناثر بجوار البرنامج
# ولا يضيع عند حذف/تحديث ملف البرنامج نفسه.
APP_FOLDER_NAME = "JadeiteERP"


def _make_dir(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def get_app_base_dir():
    """مسار مجلد البرنامج نفسه (يعمل مع نسخة exe المجمّعة ومع تشغيل ملف بايثون عادي)"""
    try:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return os.getcwd()


def get_app_data_dir():
    """المجلد الرئيسي لكل ملفات النظام على القرص المحلي"""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        home = os.path.expanduser("~")
        base = home if os.name == "nt" else os.path.join(home, ".local", "share")
    path = _make_dir(os.path.join(base, APP_FOLDER_NAME))
    if not os.path.isdir(path):
        # حل احتياطي لو تعذّر الإنشاء (صلاحيات مقيّدة): مجلد بجوار البرنامج
        path = _make_dir(os.path.join(get_app_base_dir(), APP_FOLDER_NAME))
    return path


APP_DATA_DIR = get_app_data_dir()
DATA_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Data"))
BACKUPS_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Backups"))
INVOICES_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Invoices"))
LOGS_DIR = _make_dir(os.path.join(APP_DATA_DIR, "Logs"))

# (أُلغي ملف الجلسة نهائياً — لا يُخزَّن أي سر على القرص)


def is_sqlite_db_healthy(path):
    """يتأكد أن ملف قاعدة البيانات سليم وقابل للقراءة (يمنع تشغيل النظام على ملف تالف)"""
    try:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            return False
        con = sqlite3.connect(path)
        try:
            res = con.execute("PRAGMA quick_check").fetchone()
            return bool(res) and str(res[0]).lower() == "ok"
        finally:
            con.close()
    except Exception:
        return False


def sync_error_message(raw_error):
    """يحوّل خطأ المزامنة إلى رسالة تقول للمستخدم ماذا يفعل بالضبط"""
    text = str(raw_error)

    if "28000" in text or "غير مصرّح بالمزامنة" in text or "غير مصرح بالمزامنة" in text:
        return ("تعذّر تجهيز البيانات من السحابة: هذا الحساب غير مربوط بالمزامنة بعد.\n\n"
                "الحل (مرة واحدة): افتح Supabase ← SQL Editor وشغّل الملفين:\n"
                "   11_fix_sync_permissions.sql\n"
                "   12_fix_pull_token.sql\n\n"
                "سيفتح النظام الآن ببياناتك المحفوظة على هذا الجهاز، ولن تفقد شيئاً.")

    if any(k in text for k in ("اتصال", "الإنترنت", "urlopen", "timed out", "Connection")):
        return ("تعذّر الاتصال بالسحابة — تحقق من الإنترنت.\n\n"
                "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
                "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")

    return (f"تعذّر تجهيز البيانات من السحابة:\n{text}\n\n"
            "سيفتح النظام ببياناتك المحفوظة على هذا الجهاز، "
            "وستُرفع أي حركات جديدة تلقائياً عند عودة الاتصال.")


def resource_path(filename):
    """مسار ملف مرفق مع البرنامج، يعمل في التشغيل العادي وداخل ملف exe معاً"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def apply_app_icon(window):
    """يضبط أيقونة البرنامج على النافذة (شعار جاديت).

    يُستدعى لكل نافذة رئيسية: ويندوز يأخذ أيقونة شريط المهام من النافذة
    الأولى، وأيقونة الملف التنفيذي تُضبط عند البناء بـ --icon.
    """
    try:
        ico = resource_path("jadeite.ico")
        if os.path.exists(ico):
            window.iconbitmap(ico)
    except Exception:
        pass   # غياب الأيقونة لا يمنع تشغيل البرنامج


def reset_local_cache(db_path):
    """يمسح النسخة المحلية المؤقتة قبل السحب من السحابة (نسخة المدير فقط).

    الخطر الذي يمنعه: السحب دمج لا استبدال، فلو بقيت نسخة قديمة على جهاز
    المدير لظهرت له حركة حذفها العميل فعلياً، وقد يبني عليها قراراً محاسبياً.
    الحذف آمن هنا: هذه القاعدة ذاكرة عرض مؤقتة، ومصدر الحقيقة السحابة وجهاز
    العميل — لا تُحذف بيانات أحد.
    """
    for suffix in ("", "-journal", "-wal", "-shm"):
        path = db_path + suffix
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            log_cloud_error("تعذّر تنظيف النسخة المؤقتة", e)


def migrate_legacy_file(filename, target_path):
    """ينقل أي ملف قديم كان يُنشأ بجوار البرنامج إلى المجلد المنظّم الجديد (نسخ آمن، بدون فقدان بيانات)"""
    if os.path.exists(target_path):
        return True
    for folder in {os.getcwd(), get_app_base_dir()}:
        try:
            old = os.path.join(folder, filename)
            if os.path.exists(old) and os.path.abspath(old) != os.path.abspath(target_path):
                shutil.copy2(old, target_path)
                return True
        except Exception:
            pass
    return False


def cleanup_old_files(folder, keep=100, suffix=""):
    """يبقي أحدث عدد من الملفات في مجلد ويحذف الأقدم، حتى لا تتراكم الملفات بلا حدود"""
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.lower().endswith(suffix) and os.path.isfile(os.path.join(folder, f))]
        files.sort(key=lambda p: os.path.getmtime(p))
        while len(files) > keep:
            try:
                os.remove(files.pop(0))
            except Exception:
                pass
    except Exception:
        pass

try:
    from supabase import create_client as _sb_create_client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

CLOUD_LOG_FILE = os.path.join(LOGS_DIR, "cloud_errors.log")


def log_cloud_error(context: str, error) -> None:
    """يسجّل أي خطأ متعلق بالسحابة في ملف محلي (عشان ميضيعش صامت في نسخة exe بدون شاشة كونسول)"""
    try:
        with open(CLOUD_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {context}: {error}\n")
    except Exception:
        pass
    print(f"{context}: {error}")


def hash_password(raw_password: str) -> str:
    """تشفير بسيط لكلمة المرور — لا تُخزَّن كلمة المرور الحقيقية أبداً بالسحابة"""
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def get_supabase_public_client():
    """عميل سحابي بصلاحيات محدودة — يُستخدم لدخول العملاء ورفع/تنزيل نسخهم فقط (آمن للتوزيع)"""
    if not SUPABASE_AVAILABLE:
        return None
    try:
        return _sb_create_client(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY)
    except Exception:
        return None


def get_supabase_admin_client():
    """عميل سحابي بصلاحيات كاملة (المدير فقط) — يتخطى كل الحمايات"""
    if not SUPABASE_AVAILABLE:
        return None
    if not SUPABASE_SECRET_KEY:
        log_cloud_error("مفتاح المدير غير مضبوط",
                        "ضع المفتاح في متغيّر البيئة JADEITE_SUPABASE_SECRET_KEY "
                        "أو في ملف admin_secret.key بجانب البرنامج")
        return None
    try:
        return _sb_create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
    except Exception:
        return None


CURRENT_SYNC_TOKEN = None   # رمز مزامنة الجلسة الحالية (ذاكرة فقط)


def cloud_verify_client_login(username, password):
    """يتحقق من بيانات دخول عميل عبر السحابة. يرجع (client_id, business_name, can_edit) أو (None, None, False)"""
    sb = get_supabase_public_client()
    if sb is None:
        return None, None, False
    try:
        # نجرّب أولاً الدالة الموسّعة التي ترجع رمز المزامنة معها،
        # ونرجع للقديمة تلقائياً لو لم تكن مثبّتة في السحابة بعد
        try:
            res = sb.rpc("client_login_full", {"p_username": username, "p_password_hash": hash_password(password)}).execute()
        except Exception:
            res = sb.rpc("verify_client_login", {"p_username": username, "p_password_hash": hash_password(password)}).execute()

        if res.data:
            row = res.data[0]
            client_id = row.get("out_client_id")
            # رمز المزامنة يبقى في الذاكرة فقط طوال تشغيل البرنامج
            global CURRENT_SYNC_TOKEN
            CURRENT_SYNC_TOKEN = row.get("out_sync_token")
            # تسجيل وقت الدخول ليظهر للمدير في لوحته
            try:
                cloud_touch_client_activity(client_id, is_login=True)
            except Exception:
                pass
            return client_id, row.get("out_business_name"), bool(row.get("out_can_edit"))
    except Exception as e:
        log_cloud_error("تعذر التحقق من بيانات الدخول عبر السحابة", e)
    return None, None, False


# يتحوّل إلى False لو تبيّن أن أعمدة تتبّع النشاط غير موجودة، فلا نكرر المحاولة ولا نملأ ملف السجل
_ACTIVITY_TRACKING_SUPPORTED = True


def cloud_touch_client_activity(client_id, is_login=False):
    """يحدّث (آخر ظهور) للعميل — و(آخر دخول) عند تسجيل الدخول — ليراهما المدير في لوحته.
    عملية خفيفة جداً (سطر واحد)، وتتوقف بهدوء لو لم تكن أعمدة التتبّع مضافة في السحابة."""
    global _ACTIVITY_TRACKING_SUPPORTED
    if not client_id or not _ACTIVITY_TRACKING_SUPPORTED:
        return False

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {"last_seen": now_iso}
    if is_login:
        payload["last_login"] = now_iso

    last_err = None
    for getter in (get_supabase_admin_client, get_supabase_public_client):
        sb = getter()
        if sb is None:
            continue
        try:
            sb.table("clients").update(payload).eq("client_id", client_id).execute()
            return True
        except Exception as e:
            last_err = e

    _ACTIVITY_TRACKING_SUPPORTED = False
    log_cloud_error("تعذّر تسجيل نشاط العميل (تأكد من إضافة عمودي last_login و last_seen بجدول clients)", last_err)
    return False


def cloud_check_can_edit(client_id):
    """فحص خفيف لصلاحية التعديل الحالية (للتحديث الدوري أثناء تشغيل البرنامج)"""
    sb = get_supabase_public_client()
    if sb is None or not client_id:
        return None
    try:
        res = sb.rpc("check_client_can_edit", {"p_client_id": client_id}).execute()
        if res.data is not None:
            return bool(res.data)
    except Exception as e:
        log_cloud_error("تعذر فحص صلاحية التعديل", e)
    return None


def cloud_set_client_can_edit(client_id, value):
    """(المدير فقط) يفتح/يقفل صلاحية التعديل لعميل معيّن"""
    sb = get_supabase_admin_client()
    if sb is None:
        return False
    try:
        sb.table("clients").update({"can_edit": value}).eq("client_id", client_id).execute()
        return True
    except Exception as e:
        log_cloud_error("فشل تغيير صلاحية التعديل", e)
        return False


def cloud_upload_backup(client_id, db_path):
    """يرفع نسخة كاملة من قاعدة البيانات المحلية للسحابة — تعمل في الخلفية ولا تعطّل البرنامج عند فشلها"""
    sb = get_supabase_public_client()
    if sb is None or not client_id or not os.path.exists(db_path):
        return False
    try:
        with open(db_path, "rb") as f:
            raw = f.read()
        encoded = base64.b64encode(raw).decode("ascii")
        sb.rpc("upload_backup", {"p_client_id": client_id, "p_backup_data": encoded}).execute()
        return True
    except Exception as e:
        log_cloud_error("فشل رفع النسخة الاحتياطية للسحابة (سيُعاد المحاولة تلقائياً)", e)
        return False


def cloud_download_backup(client_id, target_db_path):
    """ينزّل آخر نسخة احتياطية للعميل من السحابة ويكتبها محلياً. يرجع True لو نجح"""
    sb = get_supabase_public_client()
    if sb is None or not client_id:
        return False
    try:
        res = sb.rpc("download_backup", {"p_client_id": client_id}).execute()
        if res.data and res.data[0].get("out_backup_data"):
            raw = base64.b64decode(res.data[0]["out_backup_data"])
            with open(target_db_path, "wb") as f:
                f.write(raw)
            return True
    except Exception as e:
        log_cloud_error("تعذر تنزيل النسخة الاحتياطية من السحابة", e)
    return False


def cloud_create_client_account(business_name, username, password):
    """(المدير فقط) ينشئ حساب عميل جديد بالسحابة. يرجع (True, client_id) أو (False, رسالة الخطأ)"""
    sb = get_supabase_admin_client()
    if sb is None:
        return False, "تعذر الاتصال بالسحابة (تأكد من الإنترنت)."
    try:
        result = sb.table("clients").insert({
            "business_name": business_name, "username": username, "password_hash": hash_password(password),
        }).execute()
        return True, result.data[0]["client_id"]
    except Exception as e:
        return False, str(e)


def cloud_list_clients():
    """(المدير فقط) يرجع قائمة كل العملاء المسجلين بالسحابة، مع وقت آخر نسخة احتياطية وصلت لكل واحد منهم"""
    sb = get_supabase_admin_client()
    if sb is None:
        return []
    try:
        # نحاول أولاً جلب أعمدة تتبّع النشاط، وإن لم تكن مضافة في السحابة نرجع للأعمدة الأساسية بدون تعطّل
        base_cols = "client_id, business_name, username, is_active, can_edit, created_at"
        try:
            result = sb.table("clients").select(base_cols + ", last_login, last_seen").order("created_at", desc=True).execute()
        except Exception:
            result = sb.table("clients").select(base_cols).order("created_at", desc=True).execute()
        clients = result.data or []
        try:
            backups = sb.table("db_backups").select("client_id, updated_at").execute()
            backup_map = {b["client_id"]: b["updated_at"] for b in (backups.data or [])}
        except Exception as e:
            log_cloud_error("تعذر جلب أوقات النسخ الاحتياطية", e)
            backup_map = {}
        for c in clients:
            c["last_backup"] = backup_map.get(c["client_id"])
        return clients
    except Exception as e:
        log_cloud_error("تعذر جلب قائمة العملاء", e)
        return []


def cloud_verify_sub_admin_login(username, password):
    """يتحقق هل هذا مستخدم 'مدير مساعد' (صلاحيات محدودة: انتحال شخصية فقط)"""
    sb = get_supabase_public_client()
    if sb is None:
        return False
    try:
        res = sb.rpc("verify_sub_admin_login", {"p_username": username, "p_password_hash": hash_password(password)}).execute()
        return bool(res.data)
    except Exception as e:
        log_cloud_error("تعذر التحقق من دخول المدير المساعد", e)
        return False


def cloud_create_sub_admin(username, password):
    """(المدير الرئيسي فقط) ينشئ حساب مدير مساعد جديد (يقدر فقط على انتحال شخصية العملاء)"""
    sb = get_supabase_admin_client()
    if sb is None:
        return False, "تعذر الاتصال بالسحابة."
    try:
        sb.table("sub_admins").insert({"username": username, "password_hash": hash_password(password)}).execute()
        return True, None
    except Exception as e:
        return False, str(e)


def cloud_delete_client(client_id):
    """(المدير الرئيسي فقط) يحذف حساب عميل نهائياً من السحابة، وكل بياناته المرتبطة (نسخ احتياطية وأي جداول مرتبطة به).
    السجلات التابعة تُحذف أولاً، لأن قيود المفاتيح الأجنبية تمنع حذف العميل قبل حذف ما يشير إليه."""
    sb = get_supabase_admin_client()
    if sb is None:
        return False, "تعذر الاتصال بالسحابة."

    # الجداول التابعة المعروفة تُحذف مباشرة
    for child_table in ("db_backups",):
        try:
            sb.table(child_table).delete().eq("client_id", client_id).execute()
        except Exception as e:
            log_cloud_error(f"تعذر حذف سجلات ({child_table}) المرتبطة بالعميل", e)

    # أي جدول تابع آخر يُكتشف تلقائياً من رسالة قيد المفتاح الأجنبي ثم يُحذف، ثم يُعاد المحاولة
    last_err = None
    cleared = set()
    for _ in range(8):
        try:
            sb.table("clients").delete().eq("client_id", client_id).execute()
            return True, None
        except Exception as e:
            last_err = e
            # اسم الجدول المرتبط يُستخرج من رسالة قاعدة البيانات مهما كان شكل الاقتباس فيها
            match = re.search(r'referenced from table\s+\\?["\']([^"\'\\]+)', str(e))
            if not match:
                break
            ref_table = match.group(1)
            if ref_table in cleared:
                break
            cleared.add(ref_table)
            try:
                sb.table(ref_table).delete().eq("client_id", client_id).execute()
            except Exception as e2:
                log_cloud_error(f"تعذر حذف سجلات ({ref_table}) المرتبطة بالعميل", e2)
                break

    return False, str(last_err) if last_err else "تعذر حذف الحساب لسبب غير معروف."


def cloud_list_sub_admins():
    """(المدير الرئيسي فقط) يرجع قائمة كل المدراء المساعدين"""
    sb = get_supabase_admin_client()
    if sb is None:
        return []
    try:
        result = sb.table("sub_admins").select("id, username, created_at").order("created_at", desc=True).execute()
        return result.data or []
    except Exception as e:
        log_cloud_error("تعذر جلب قائمة المدراء المساعدين", e)
        return []


def cloud_delete_sub_admin(sub_admin_id):
    """(المدير الرئيسي فقط) يحذف حساب مدير مساعد"""
    sb = get_supabase_admin_client()
    if sb is None:
        return False, "تعذر الاتصال بالسحابة."
    try:
        sb.table("sub_admins").delete().eq("id", sub_admin_id).execute()
        return True, None
    except Exception as e:
        return False, str(e)


# ملاحظة معمارية: أُلغيت دوال حفظ/قراءة جلسة الجهاز.
# البرنامج الآن يطلب تسجيل الدخول في كل تشغيل، ويحتفظ ببيانات الجلسة
# (معرّف المصنع ورمز المزامنة) في الذاكرة فقط، فتختفي بإغلاق البرنامج.


# ================= نهاية وحدة الربط بالسحابة =================

_ARABIC_FONT_NAME = "Helvetica"
_ARABIC_FONT_BOLD_NAME = "Helvetica-Bold"


_ARABIC_FONT_PATH_USED = None


def _register_arabic_font():
    """يحاول تسجيل خط يدعم العربية (من خطوط ويندوز الشائعة) لاستخدامه داخل ملفات PDF"""
    global _ARABIC_FONT_NAME, _ARABIC_FONT_BOLD_NAME, _ARABIC_FONT_PATH_USED
    if not REPORTLAB_AVAILABLE:
        return
    candidates_regular = [
        r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\times.ttf", r"C:\Windows\Fonts\micross.ttf",
        r"C:\Windows\Fonts\simpo.ttf", r"C:\Windows\Fonts\trado.ttf",
        r"C:\Windows\Fonts\arialuni.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/kacst/KacstOne.ttf",
    ]
    candidates_bold = [
        r"C:\Windows\Fonts\tahomabd.ttf", r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\calibrib.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates_regular:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ArFont", path))
                _ARABIC_FONT_NAME = "ArFont"
                _ARABIC_FONT_PATH_USED = path
                break
            except Exception:
                continue
    for path in candidates_bold:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("ArFont-Bold", path))
                _ARABIC_FONT_BOLD_NAME = "ArFont-Bold"
                break
            except Exception:
                continue
    if _ARABIC_FONT_BOLD_NAME == "Helvetica-Bold" and _ARABIC_FONT_NAME != "Helvetica":
        _ARABIC_FONT_BOLD_NAME = _ARABIC_FONT_NAME


def ar(text):
    """يهيئ نصاً عربياً للعرض الصحيح داخل PDF (تشكيل الحروف المتصلة واتجاه الكتابة من اليمين لليسار)"""
    text = "" if text is None else str(text)
    if not text:
        return ""
    if ARABIC_SHAPING_AVAILABLE:
        try:
            reshaped = arabic_reshaper.reshape(text)
            return get_display(reshaped)
        except Exception:
            return text
    return text


def fit_font_size(raw_text, max_width, base_size, font_name=None, bold_font_name=None, bold=False, min_size=6.0):
    """يحسب أكبر حجم خط (بدءاً من base_size وحتى min_size) يجعل النص يدخل ضمن max_width دون تجاوزها،
    لمنع تصادم/تداخل الكلمات مع حدود أعمدة الجدول"""
    if not REPORTLAB_AVAILABLE or not raw_text:
        return base_size
    fname = (bold_font_name or _ARABIC_FONT_BOLD_NAME) if bold else (font_name or _ARABIC_FONT_NAME)
    size = base_size
    shaped = ar(raw_text)
    while size > min_size:
        try:
            w = pdfmetrics.stringWidth(shaped, fname, size)
        except Exception:
            break
        if w <= max_width:
            break
        size -= 0.5
    return round(size, 1)


def vcenter_baseline(cell_top, cell_h, font_size):
    """يحسب موضع خط أساس النص (baseline) بحيث يتوسّط عمودياً داخل خلية ارتفاعها cell_h وأعلاها cell_top،
    مع مراعاة الحجم الفعلي للخط (بدل إزاحة ثابتة قد ترفع النص فتلامس حد الخلية العلوي)"""
    cell_bottom = cell_top - cell_h
    return cell_bottom + (cell_h - font_size) / 2 + font_size * 0.16


if REPORTLAB_AVAILABLE:
    _register_arabic_font()

# تفعيل الوضع الداكن الفخم افتراضياً
ctk.set_appearance_mode("Light")   # الوضع الفاتح هو الافتراضي عند فتح النظام
ctk.set_default_color_theme("blue")

# ================= شعار النظام (مُضمَّن كـ base64 حتى لا يعتمد على ملف خارجي) =================
APP_LOGO_B64 = (
    "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"
    "8X8LkfcsM19esWGefu/MKUbJ2j2Gl5m9bNzH7H274pfv65/5y3nyrkumySkn5MhTrnnM/GlHbbnOPP1PXvMqZm7fWPKpfuq4sXzx"
    "Xc/p25sCXN3c9nZje+OAwxyfGf7tYG5NPJKR9neueeAYI9B4peGr2umuWy+bypeZ8z59iS+47AbjyfcWGFsqG75n5sFcxrYjycgj"
    "fJ7OzHE+X0t3Zl93r9fbjZkzfMy9jzYvn8/X8wjjqYebe+fPDv089O+Dim5H7u2Vq+b+03fZqeONL+YUc02zp56Zc5g5vra2ct6G"
    "tUvljVddHrjypnsDO2s7ZGtH8BGfz9edmTOZeSAzx4Qjt+xH3N9WTmD2XmB661bX7lol169YYN54w43648++aNQ0NeQLEgduEzNn"
    "GJ6Kum0lb/IFU0bIUdNvCC4ta+WaNs+i+qa20/goe6YmxnTZzFz3znGTTj7/6v0O/9De6RUAvwKIrKwu8Sfnnjd2gJaQtMI0JZgL"
    "lY4O5QpNJL077dyZo3mHqEu2iZ+s9owrDKh/u+fpWVcnvvfhsuZWYyDI5kjv098ycNiA1t69+lt7jRprCGBuo6/5obTYlP1/f+v9"
    "O2bNevPb8or6oGqLsRx/xukp48aP6Z/y0rs7e/ZN2xlrdRZ6PbJnt5En5c79bsnkhd9937Zlx85dZXsrdouYeGPGhRfPmDDx+J/b"
    "2tqMH+Li3Lk9enz2yudFF3z66dxGmdY/uUeX5CqOd1ZOOPecrvYeg1gLBle5rNYF5eXbNyUkoGXY4B43JySel+i0xxRKn61730nn"
    "Z381f9TIFavWo6Kyoa6qum4LHCN2X3b9xSdTu9/Va9k23TSDeVCsE7oPmXDV7ddfq8UN71ehang23hm/t3M/vnCojAAQaG+uOq/7"
    "2FOefOfT0ZOWLi7Ghm27lPLKNgRMCxJP6qX2Gz4KA4f0x5Bs/EurD/zVkpLay0joO+/qG29KaLdnLXUo9qs87U3Dk/uc8MRTr88a"
    "um1HJZpaOdA1XtuhQFlgkna6tGVN7Zrd3/TLBnHK8ROVnikuEr6m1QCQkxP1nkcRRRT/83Go59ZisWDp0qXG0qVLUVDwx3t704E+"
    "q5xFRJVhoUzHGHrNubm5KSbz3cGgv6/H7QZABNCBwHMGQQIQJEAgttg0UhWl0m61tgN4i4h2CyFQUFAQmb8oLi4WOTk5fJgerpGi"
    "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"
    "aKmplk1tJjkHpJJTYyhBvZWZCUZlo5IcjwQn5A53qzB0M+C0JF0Hw2efPP28HlNssNtk05nOzOxLbJpqqooGkwCGKTTFGM6BNjS3"
    "CzMhuavqaXevESJUI8nrrdkC4URSaiLMpl8g3W4SqgspXbrh7mumoiHvA+Wlh2/DokHdL1A8Ddjxyw4kTJwurr/rBiRYdY9Ftmne"
    "plpLe3U7yhYt592/WGWM0YiWhnryq8l0/OkXW664YPpsZu5LRNUUm/oOe+p7Dz2F7vfW7jFjYu2KzW4HQQlLOhYtLS1rNQrW9hw1"
    "sctfr2vh517/id5+fJd1+ZfpQ4MN+1C6ZS/ST5yBCy45X4iA3q5Dm5/k0F5u3b6ky1vvfm32Ou026jPuVNS3lyLWboMpGUIhGH6v"
    "1JuaRF2rAXtWMpKcAl5d15iZpF5dpyTGDkyMAeutHTAM/XDGzEhR06q0fr3+ecYNF18oVEseEVUzs8jPz48Q6wOdtxoatrsSE9Lf"
    "qdm7Kfe+O+/nteXt8MX8ZN571+2n3nz2KRlEtCtC6gGgMLdQmVk00/zgjbeuio2NzTV1c7FiJZMsMQKK2ru4uHjrggULFGZ2BTx1"
    "f1mxauOp835YOaj3kGFeN/PPLStXXpRN5CsrK7P1IGqqq9ibn5oVt3H9lx/Jn/ZImXP1NQO8zMcT0U+dDA4KEZnrVq/O3b5t24MA"
    "RoTnH45iU1c3NTdujomzjOjw1s3TvdXvb924mTftqh9asmpHVlOQt8dqeDVihCkuLlanTJkSMbAre/fuOs00sapPnz4t69evp1F9"
    "+sTWGMaYrT9vPk9AtCVlJM1WAVOYwSB5DWbNboXdBpBuWohIFofd8wWhMAQB7NKIqKywsNDSs2cujx59hDwDaQCSEfD6UDh7Nmk2"
    "DTZV6cLMXdrcXnh8BuKz+vOY8y/AzX+9trlbWnx+2JrgBnAhM+cA8BLRmt+Y03+1QtQCmANgzhZmS6qXLrGriqowmDQiIgTiYrVz"
    "AaEEvWwqZFHtdoUBOImopaysLMgkqm0OVwIRsbutBVZgX1hQ/wLgTm97xTsWpxyokl8SmYDonDAngwGPRMCwsM2hChUERcjVRMRG"
    "R50JqwV2hwbd1wbTNKAY7bCaHRCKgLejA9u27pdBWKitxUW2+BTYXLGwsQ6FmHTDhGH40W/EMJp4Zg5NHDFAdPHvx9ZV3+OzeUvx"
    "+nNPyKTsHvFTh6TfU8X8VxfRBwf+Unwt1yY7YyYHfX7EJ7gyAYybfvvti3H77fC37h6uuushjQCbBqNmfyNX11rg91rJKzJgd2Uo"
    "QY+UVlfNZTZbS1xRweNy9T6LeuUTdyMpzQ5LU6g3rkUIsCmhkyGBoNrRAdZMO5w2BgArEcnCwi1NZ5/LrQ6HI0EVgMfdBimlS1UN"
    "27G2w4kiiiiiOEDQPV5EvLkhWSDIhCG79eiWIiD2hhWAwY8++vBbO3fsFAqpdOHMXOqSllIaFvadreO/YZT5+fmUn59Puu5/8/bb"
    "bn1q2Y/LXI1NzawoChmmCcU0sHfvHuvVV102qvCrOe8wc/M333zzEIAOAywMiUgvcjAYRlAX5eX7Katnjwnbtm3eLCWTx+PjPXv3"
    "0rPPPtd/SckSZdWKn+D3+aQ0WeiGwQB42qmniEfz8sSoUSMWb9y4+ZqxY8c3RVqDhY3Vkm+/Pa5Oof4+v98LEjFEByILaH9FBZYt"
    "X5bl9/tv/ujDD8bV1tZtBGSKpml9X3/jtXQ2ZVKzux0Lvp2HzRs3wecPGmecfqaa2TV7iabRt2G232Bz2DfExcYM8weCpmEYCikq"
    "qmvrtDnz5nUZN2HCR5V1desyU1PvIKLyw5DcyP627t+7f5HT4Zjq9fukECSEQlAUwWD5Rwy0FqtFI00VsFqsAJsgIhhMeOrZp6jw"
    "y0KHw2YbR0LA1A3ohoFg0I8Ojwd7du9BRcV+AEISS+rbb5B58ikntwMg5qihOIoo/qsReQ9TcnI7gEXhj+dsWfbTuRYFTkUQNCHY"
    "VGADyObzBaTHUGCxaYh1EXSvrlqtVjaDdc3CosFhM6UtqMEf1BeR3b47PN5mAOBA/TCH1QoVgplIBIOAoshEZiNTb3NDBi3ksjsR"
    "9Pq3P/poKCe6rq5yjcMRgMVhU/y6B7puwiALVMOHYGslVHjgb67C7i1+2ahbqbkjhrqqcfBChxUeaBJC+hQkJKWg3wkTacqkQUrP"
    "GD/8ldvx9YKlKPnkPSPJbnP27nrBJACfrVu3TiNn6gOB9qpxjqS4HBUBKUJ1QiFNwwtYLYmJiW2+tn0rbTGx56hol0awUtH9Fajf"
    "22Y2+Bh1iFHibWkcH58kOtzeDel2zwAnPFMfy3vS8KUer04+70JY1TbEO6ywKQYMXYcEoCgQHQEdHlOBLUZDrBOAVwfFW9gI1Oqw"
    "aoixAcIwQId5ZXeSqe0AbmHmLwBsxeUhq3FBQYGsqakZtGPHjjYA1SHy23oaOupzH3v4aUPJnqJeftZx5PEH0FDR5AnzwM7vZZpZ"
    "NJOZ2T73vfdvWfTBByOtsfEnxqamYfe+cpjE10+ZMuULAIa3fsd3P3z+Qc6/Zi9EhRtI7T8m6dxLr+56+tTxW1o97U/FO2PfLORC"
    "paHCW5EatFZOHJ2cVfTdPP2XnTNcJwztcR+AGSG5wLR+/XrBzHLhwu+fsKi2bwCgpKRECbdmE0TU/NZLLwbb3TXwtO1Xaiu2XPve"
    "P2dj3Y5W+NQkjJs2M/PCS88/yc38r/b162/JHD3ay8wWADoRGZ9/8uEcTdWe6tu37wMAsHNH2ex9+/ad2lDbCCYNeyor6lRASLvT"
    "AZtCaAv6EdAZkKEJlhx8EySAAADMnDnzqLFpCgBBJoQicPq55yC7exYbrfWyeu8uXrp8vQgEHeKUGefJa++6TjFaGopj7fRGMbM6"
    "hcgIezFKfu8PPGKFKCkBegApoRmGCtBAylB3G3A2AFKFlR0WB/buq/gZQE1hYaHovm+fYXYfVqcQDwrofphswquH+sLvX7HC3nX8"
    "eD3QUcWAAaIAwBwa+1eCToAAs4CASZ4gfJkWYxMAKJoioSqQEhCmF1bywWxpw5sfr8JmTwqmXXIFzjp1kgj4GrBq5Y/49MN5eO/1"
    "NzF2SL4rPckhrTFZfPqVl9O5fae1jRg6qNWmYpmDB+4YNqzPI1ZN2gremC++KvqUJw+754aY1tanmHl/9fr11oxRo4LoaI2DNGC1"
    "WOH3+esQ6lmLprba8VaH7+HCT+fLeVul0mfqubj8whmUZJXYXroJhR9+jcK3X0dWz1Qx4dy0uJ3zvpRvf7RCjJ35KEYOT4dV1EGz"
    "ApAdoIAP0gSZqnmcXwIkHBBSgHUTEVfOwIGAoihVQlAP3QiCWTJIfmEYlsAR8jyiiCKKKI4Id3s7SChgPhDFTACQEBcnIv+9bdsv"
    "CStXrorXdd0cNnioGDVy1H7d9C+yqhbG7xQkC+cpKxaL/c3W1qZT3nn7rfMuuvgS0+8PKqqmgk1TeH0+3rpz++A7bvvL4KuvvaF5"
    "5HEji70B7xSAgzarlaU0oRuAIAFFVSn/b/no8mZqjM1mHewPBODz+tDa1o6GhvpQkTQmqZsm2SwaTzx+PF16+WV05hkz9iQmJsy2"
    "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"
    "nPdcbm7+W6lJiS5ATwa0yvA1vJ3OPew7vaCgQBYUFGD//v33xMV1vdeNdqg+n0pEdZH1/l43j8j3hmEQEb0K4NXId+vWzdKamrpb"
    "4rt2tY0dOLDpWO/xzJkzo+Q8iij+TTBw4EAGILxe7x6SmBQw2BQC3CplW6KJNy0ZWff07ZEhVq3bzbXVTcqoUUm9R40aVQIEu+zb"
    "uQf7G0F9xveAarEo+1p2HUzuBNiQCsACkAxpAqqixpkB+8sg74nDB6ZPfHveGiNGsZ3u9SKmrm7LQxaLeldz2RrevrNMSeo/Dmnd"
    "+5psLiHNromgrsDw6mTTbKbH854GY4oAWdFS3wHoRB6dWbbW9nr/b89SoM/U9OtvuXxuU13TtPrm+p29e6Q9EKzb0uvnbXtNThiu"
    "KJpVQVsbdXrXqQBYlyaZEmD561JMKXYKkmxXVDJ8BlQm0gitXftSoLm5WgMBbQ0dkGSHsDjRr1c2/ePZl1T2tEP3+8F6ADJQy3v3"
    "ltKcBavh6tMTx59zFWLTs3clJIleg/t0FWtX7OXKvfvphKzuA+bOnbsPMJ0Ve/ZjXyMoY1hXGR/vtLe1BwYDqAvLFrMzOQ/LQuTn"
    "w2n6657k9sqJ+6oa5ZiczIfgdr9WUoLWlpbKcofF8d748aPyfT8uNampTt2wfZNe6pE0rFvfyczsJCLvwbKhRDCDYbZdo+tBNLeZ"
    "nJndTU474wwx78sipXLbNrnTMAKqZhUsFEWFIaQ0IPUAzKAOQYrpUk3Wa3ZgcdF2f0ycEy6nXbW7XKo9NsWalZ4IwWiIyJvy8nIl"
    "KUnXy0s3s97OKYEgPmXmMUTUGF5rHIA39+3/sc+G7eWGqXmEVd1jCKEommKQDPpgBvwIBkzTrlrYJt2oWbdE/3z9EumyaiIxIUbr"
    "MXgUugSk0lG1XdvbuAfxMQ5cft11SmV1G1ISusPhinGrROTRvVXzT8u98qYv5qwNrlj0nuW++4R56UXn3dAnyzWt1d1Q52spH7F0"
    "3tv8zxfmao1x4zn3grNEcoxFa2/dc1OMK/GsJcuWZ35XsqFj0pjhtxDR+vqdm6EIBUKoUKxW1kLV/BQAsrW18pX4boPPufWq6ebe"
    "J4osJV9/Kr8bPyr54pMGrK+vrJxssfF53y5cOrDbwBF1Y4YOnG0l2ni4HLxDYZLKQmgAB8FgYkBpra5u75Yy7A5HTOKMCf0TnR+u"
    "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"
    "SSxkbWtPAAAAAElFTkSuQmCC"
)


class ScreenRouter(ctk.CTkFrame):
    """بديل خفيف عن CTkTabview: نفس واجهة add()/tab() المستخدمة في كل شاشات النظام،
    لكن بدل شريط تبويبات جانبي، يعرض شاشة واحدة فقط في كل مرة مع زر عودة للقائمة الرئيسية،
    وتبقى بقية الشاشات مغلقة حتى يتم اختيارها من القائمة الرئيسية."""

    def __init__(self, master, go_home_callback=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._contents = {}   # name -> إطار المحتوى (نفس ما كانت ترجعه tabview.tab())
        self._wrappers = {}   # name -> الإطار الكامل (شريط علوي + محتوى)
        self._screen_info_labels = {}   # name -> عناوين الفترة والأرصدة في شريط الشاشة
        self.go_home_callback = go_home_callback
        self.current_screen = None

    def update_screen_info(self, period_text, treasury_text, total_text):
        """يحدّث الفترة والأرصدة في شريط كل شاشة (تُستدعى من recalculate_all)"""
        for labels in self._screen_info_labels.values():
            try:
                labels["period"].configure(text=period_text)
                labels["treasury"].configure(text=treasury_text)
                labels["total"].configure(text=total_text)
            except Exception:
                pass

    def add(self, name):
        wrapper = ctk.CTkFrame(self, fg_color="transparent")

        top_bar = ctk.CTkFrame(wrapper, fg_color=("gray85", "gray17"), height=52, corner_radius=10)
        top_bar.pack(fill="x", padx=5, pady=(5, 6))

        # يسار الشريط: العودة للقائمة الرئيسية
        btn_back = ctk.CTkButton(top_bar, text="🏠 القائمة الرئيسية", font=("Cairo", 15, "bold"),
                                  fg_color="#555555", hover_color="#333333", width=170, height=38,
                                  command=self._go_home)
        btn_back.pack(side="left", padx=10, pady=7)

        # يمين الشريط: اسم الشاشة
        ctk.CTkLabel(top_bar, text=name, font=ctk.CTkFont(family="Cairo", size=17, weight="bold"),
                     text_color="#d4af37").pack(side="right", padx=15, pady=7)

        # وسط الشريط: الفترة والأرصدة مصغّرة — كل ما كان يشغل الشريط العام
        # بارتفاع ٩٥ بكسل صار هنا في سطر واحد، فتُفرَّغ المساحة كلها للجدول
        info_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        info_box.pack(side="right", padx=8, pady=6)

        lbl_period = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                   text_color="#1f77b4")
        lbl_period.pack(side="right", padx=8)

        lbl_treasury = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                     text_color="#d4af37")
        lbl_treasury.pack(side="right", padx=8)

        lbl_total = ctk.CTkLabel(info_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                  text_color="#2ecc71")
        lbl_total.pack(side="right", padx=8)

        self._screen_info_labels[name] = {
            "period": lbl_period, "treasury": lbl_treasury, "total": lbl_total}

        content = ctk.CTkFrame(wrapper, fg_color="transparent")
        content.pack(fill="both", expand=True)

        self._contents[name] = content
        self._wrappers[name] = wrapper
        return content

    def tab(self, name):
        return self._contents[name]

    def show(self, name):
        self.current_screen = name
        self.pack(fill="both", expand=True)
        for w in self._wrappers.values():
            w.pack_forget()
        if name in self._wrappers:
            self._wrappers[name].pack(fill="both", expand=True)

    def _go_home(self):
        self.pack_forget()
        if self.go_home_callback:
            self.go_home_callback()


class GoldSystemApp(ctk.CTk):
    def __init__(self, client_id=None, client_name=None, supabase_client=None, is_admin_session=False, initial_can_edit=False):
        super().__init__()

        self.client_id = client_id
        self.client_name = client_name
        self.supabase = supabase_client
        self.is_admin_session = is_admin_session
        # صلاحية التعديل: المدير/الجلسة المحلية بدون عميل = مسموح دائماً، العميل العادي حسب ما فتحه المدير له
        self.can_edit = True if (is_admin_session or not client_id) else bool(initial_can_edit)

        # تم تغيير مسمى النظام + ضبط حجم الشاشة تلقائياً حسب دقة جهاز المستخدم (بدل الحجم الثابت)
        title_suffix = f" - {client_name}" if client_name else ""
        self.title(f"نظام قسم التصنيع - الإصدار المحاسبي المتكامل{title_suffix}")
        apply_app_icon(self)
        self.update_idletasks()
        try:
            # يعمل على ويندوز: يكبّر النافذة لتملأ مساحة الشاشة المتاحة فعلياً على أي جهاز
            self.state('zoomed')
        except Exception:
            try:
                # بديل لأنظمة لينكس
                self.attributes('-zoomed', True)
            except Exception:
                # حل احتياطي: حساب مساحة مناسبة يدوياً حسب أبعاد شاشة الجهاز وتوسيطها
                sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
                w, h = min(1600, int(sw * 0.94)), min(950, int(sh * 0.88))
                x, y = (sw - w) // 2, (sh - h) // 2
                self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(1000, 650)
        self.current_theme = "Light"

        # قاعدة البيانات والنسخ الاحتياطية داخل المجلد المنظّم على القرص المحلي
        old_generic_path = os.path.join(DATA_DIR, "gold_workshop.db")
        self.db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db") if client_id else old_generic_path
        self.backup_dir = _make_dir(os.path.join(BACKUPS_DIR, str(client_id) if client_id else "local"))

        # ترحيل أي قاعدة بيانات قديمة كانت بجوار البرنامج إلى المجلد الجديد (مرة واحدة، بدون فقدان بيانات)
        if client_id:
            migrate_legacy_file(f"client_data_{client_id}.db", self.db_path)
        migrate_legacy_file("gold_workshop.db", old_generic_path)

        # تنظيف تراكم ملفات PDF والنسخ القديمة حتى يبقى المجلد مرتباً
        cleanup_old_files(INVOICES_DIR, keep=120, suffix=".pdf")
        self.archive_data_map = {}
        self.current_display_month = datetime.datetime.now().strftime("%Y-%m")
        
        self.setup_treeview_styles()

        # ترحيل آمن: لو فيه قاعدة بيانات قديمة بالاسم العام القديم (من نسخة سابقة) ومفيش قاعدة جديدة بعد لهذا العميل تحديدًا،
        # ننقلها بدل ما نفقدها أو نستبدلها بنسخة أقدم من السحابة
        if client_id and not os.path.exists(self.db_path) and os.path.exists(old_generic_path):
            try:
                import shutil
                shutil.copy2(old_generic_path, self.db_path)
            except Exception as e:
                log_cloud_error("فشل ترحيل قاعدة البيانات القديمة للاسم الجديد الخاص بالعميل", e)

        # لو مفيش نسخة محلية للعميل ده (تنصيب جديد/تم حذف البرنامج وإرجاعه) حاول استرجاعها من السحابة تلقائياً
        if self.client_id and not os.path.exists(self.db_path):
            restored = cloud_download_backup(self.client_id, self.db_path)
            if not restored:
                # تحذير صريح بدل البدء الصامت بقاعدة بيانات فارغة وكأن مفيش مشكلة
                self.after(500, lambda: messagebox.showwarning(
                    "تنبيه استرجاع البيانات",
                    "لم يتم العثور على نسخة سابقة محفوظة على السحابة لهذا الحساب، أو تعذّر الاتصال بالإنترنت الآن.\n"
                    "البرنامج سيبدأ بقاعدة بيانات جديدة فارغة.\n\n"
                    "لو كنت تتوقع استرجاع بيانات سابقة، تأكد من الاتصال بالإنترنت وأعد فتح البرنامج، أو تواصل مع المدير."
                ))
        
        # فحص سلامة قاعدة البيانات، ومحاولة إصلاحها تلقائياً من أحدث نسخة احتياطية سليمة أو من السحابة
        if os.path.exists(self.db_path) and not is_sqlite_db_healthy(self.db_path):
            self.recover_corrupt_database()

        # تهيئة قاعدة البيانات والنسخ الاحتياطي
        self.init_database()
        self.perform_backup()       # أخذ نسخة احتياطية عند تشغيل البرنامج
        self.schedule_backup()      # جدولة النسخ الاحتياطي التلقائي كل 15 دقيقة
        if self.client_id:
            self.schedule_cloud_backup()   # دورة المزامنة السحابية كل ١٠ ثواني
            self.protocol("WM_DELETE_WINDOW", self.on_app_closing)
            if not self.is_admin_session:
                self.schedule_permission_refresh()   # تحديث دوري لصلاحية التعديل (كل دقيقة)
        
        self.load_data_from_db()

        self.apply_design_system()
        try:
            # حدّ أدنى يمنع تشوّه الجداول لو صغّر المستخدم النافذة
            self.minsize(1100, 620)
            # تُخفى النافذة حتى تكتمل الواجهة: بدون ذلك يرى المستخدم الشريط
            # الجانبي والشعار والأزرار تُرسم واحدةً تلو الأخرى عند الدخول
            self.withdraw()
        except Exception:
            pass

        self.create_layout()
        self.update_period_selector()

        # النافذة تُكبَّر وتُرسم **أولاً** ثم تُحسب الأرقام.
        # كان الحساب الأول يسبق أول رسم، فتظهر نافذة مصغّرة فارغة ثوانٍ قبل
        # أن يبدأ النظام — والحساب يمسح كل الحركات فيأخذ وقته.
        # تُبنى الواجهة كاملة وهي مخفية، ثم تظهر مرة واحدة جاهزة
        self.update_idletasks()
        try:
            self.deiconify()
        except Exception:
            pass
        self.force_maximize()
        self.update_idletasks()
        self.after(30, self._startup_first_calc)
        # إعادة التكبير بعد ظهور النافذة فعلياً: النداء قبل الظهور يُتجاهل
        # أحياناً على ويندوز فتبقى النافذة بحجمها الصغير
        self.after(220, self.force_maximize)
        self.after(700, self.force_maximize)

    def force_maximize(self):
        """يكبّر النافذة لملء الشاشة، مع بديل يدوي لو تعذّر التكبير الأصلي"""
        try:
            if self.state() == "zoomed":
                return
        except Exception:
            pass
        try:
            self.state("zoomed")
            return
        except Exception:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except Exception:
            pass
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{sw}x{sh - 48}+0+0")
        except Exception:
            pass

    def _startup_first_calc(self):
        """أول حساب شامل بعد ظهور النافذة، مع مؤشّر انتظار واضح"""
        try:
            self.configure(cursor="watch")
            self.update_idletasks()
        except Exception:
            pass
        try:
            self.recalculate_all()
        finally:
            try:
                self.configure(cursor="")
            except Exception:
                pass

        # الشاشات الثلاث الأكثر استخداماً تُبنى في الخلفية بعد ظهور النظام،
        # فتفتح **فوراً** بلا «تكوّن» أمام المستخدم. البناء متدرّج (شاشة كل
        # ١٢٠ ملّي ثانية) حتى لا تتجمّد الواجهة أثناء التجهيز.
        self.after(120, lambda: self._prebuild_screens(
            ["المبيعات", "مراحل التصنيع", "صناديق الخياس"]))

    def _prebuild_screens(self, names):
        """يبني الشاشات المطلوبة تباعاً في الخلفية بلا إظهارها"""
        if not names:
            return
        name, rest = names[0], names[1:]
        try:
            self.ensure_screen_built(name)
            self.refresh_pending_screen(name)
        except Exception as e:
            log_cloud_error(f"تعذّر تجهيز شاشة ({name}) مسبقاً", e)
        if rest:
            self.after(120, lambda: self._prebuild_screens(rest))

    def schedule_permission_refresh(self):
        self.after(30000, self.refresh_edit_permission)   # كل ٣٠ ثانية — ليصل فتح المدير للعميل بسرعة

    def refresh_edit_permission(self):
        def _check():
            result = cloud_check_can_edit(self.client_id)
            if result is not None:
                def _apply():
                    changed = (self.can_edit != result)
                    self.can_edit = result
                    self.update_edit_status_ui()
                    if changed and result:
                        try:
                            messagebox.showinfo("تم فتح التعديل ✅", "قام المدير بفتح صلاحية التعديل على حسابك الآن.")
                        except Exception:
                            pass
                self.after(0, _apply)
        threading.Thread(target=_check, daemon=True).start()
        self.schedule_permission_refresh()

    def is_edit_locked(self):
        """هل التعديل مقفول حالياً؟ (يخص العملاء فقط — المدير والجلسة المحلية مفتوحة دائماً)"""
        if self.is_admin_session or not self.client_id:
            return False
        return not self.can_edit

    def check_edit_permission(self, silent=False):
        """يُستدعى قبل أي *تعديل* على حركة مسجّلة — يمنعه لو أقفل المدير التعديل على هذا الحساب.
        ملاحظة: الحذف وتسجيل الحركات الجديدة يظلّان مسموحين دائماً."""
        if not self.is_edit_locked():
            return True
        if not silent:
            try:
                messagebox.showwarning(
                    "التعديل مقفول 🔒",
                    "التعديل مقفول حالياً على حسابك من قِبل المدير.\n\n"
                    "ما زال بإمكانك تسجيل حركات جديدة وحذف الحركات الخاطئة.\n"
                    "لتعديل حركة مسجّلة، تواصل مع المدير ليفتح لك التعديل من جهازه — "
                    "وسيُفعَّل عندك تلقائياً خلال أقل من دقيقة عبر الإنترنت.")
            except Exception:
                pass
        return False

    def check_delete_permission(self):
        """الحذف مسموح دائماً — قفل المدير يخص التعديل فقط"""
        return True

    def update_edit_status_ui(self):
        """يحدّث مؤشر حالة التعديل أعلى الشاشة ليعرف المستخدم فوراً إن كان التعديل مفتوحاً أو مقفولاً"""
        if not hasattr(self, 'lbl_edit_status'):
            return
        if not self.client_id or self.is_admin_session:
            self.lbl_edit_status.configure(text="🔓 التعديل: مفتوح (جلسة مدير)", text_color="#2ecc71")
        elif self.can_edit:
            self.lbl_edit_status.configure(text="🔓 التعديل: مفتوح", text_color="#2ecc71")
        else:
            self.lbl_edit_status.configure(text="🔒 التعديل: مقفول (الحذف متاح)", text_color="#e67e22")

    def refresh_edit_permission_now(self):
        """تحديث فوري يدوي لصلاحية التعديل من السحابة (بعد ما يفتحها المدير)"""
        if not self.client_id:
            messagebox.showinfo("صلاحية التعديل", "هذه جلسة محلية/مدير — التعديل مفتوح دائماً.")
            return

        def _check():
            result = cloud_check_can_edit(self.client_id)
            def _apply():
                if result is None:
                    messagebox.showwarning("تعذّر التحديث", "تعذّر الاتصال بالإنترنت للتحقق من صلاحية التعديل.\nتأكد من الاتصال وحاول مرة أخرى.")
                    return
                self.can_edit = result
                self.update_edit_status_ui()
                messagebox.showinfo("صلاحية التعديل",
                                    "✅ تم فتح التعديل على حسابك." if result else "التعديل ما زال مقفولاً من المدير.")
            self.after(0, _apply)

        threading.Thread(target=_check, daemon=True).start()

    def apply_edit_lock_to_button(self, btn, parent_window=None):
        """يعطّل زر الحفظ/التعديل لو كان التعديل مقفولاً، مع بيان واضح للسبب (وتبقى أزرار الحذف شغّالة)"""
        if not self.is_edit_locked():
            return
        try:
            btn.configure(state="disabled", text="التعديل مقفول 🔒", fg_color="#555555", hover_color="#555555")
            if parent_window is not None:
                ctk.CTkLabel(parent_window, text="التعديل مقفول من المدير — الحذف ما زال متاحاً",
                             font=("Cairo", 12, "bold"), text_color="#e67e22").pack(pady=(0, 6))
        except Exception:
            pass

    def mark_backup_dirty(self):
        """تُستدعى بعد أي تعديل فعلي ناجح بقاعدة البيانات — تعلّم إن فيه بيانات جديدة محتاجة رفع للسحابة"""
        self._backup_dirty = True

    def schedule_cloud_backup(self):
        self.after(10000, self.auto_cloud_backup_trigger)   # دورة المزامنة كل ١٠ ثواني

    def auto_cloud_backup_trigger(self):
        """كل ١٠ ثواني: يرفع نسخة محدّثة للسحابة لو فيه أي تغيير، ويسجّل (آخر ظهور) للعميل دائماً.
        ويرفع نسخة احتياطية دورية كل ١٠ دقائق حتى لو ما فيه تغيير، كضمان إضافي لسلامة النسخة السحابية."""
        if not self.client_id:
            return

        now = datetime.datetime.now()
        last_forced = getattr(self, '_last_forced_cloud_upload', None)
        force_due = (last_forced is None) or ((now - last_forced).total_seconds() >= 600)
        need_upload = getattr(self, '_backup_dirty', False) or force_due

        if need_upload:
            self._backup_dirty = False
            if force_due:
                self._last_forced_cloud_upload = now
            self.run_cloud_sync_cycle(upload=True)
        else:
            self.run_cloud_sync_cycle(upload=False)

        self.schedule_cloud_backup()

    def run_cloud_sync_cycle(self, upload=True):
        """دورة مزامنة واحدة في الخلفية: رفع النسخة (عند الحاجة) + تسجيل آخر ظهور، ثم تحديث المؤشر"""
        def _work():
            ok = True
            if upload:
                ok = cloud_upload_backup(self.client_id, self.db_path)
            cloud_touch_client_activity(self.client_id)
            self.after(0, lambda: self.update_cloud_sync_ui(ok, upload))

        threading.Thread(target=_work, daemon=True).start()

    def update_cloud_sync_ui(self, ok, uploaded):
        """مؤشر صغير أعلى الشاشة يوضح آخر رفع ناجح للسحابة"""
        if not hasattr(self, 'lbl_cloud_sync'):
            return
        if ok:
            if uploaded:
                self._last_cloud_sync_ok = datetime.datetime.now().strftime("%H:%M:%S")
            stamp = getattr(self, '_last_cloud_sync_ok', None)
            self.lbl_cloud_sync.configure(text=f"☁️ آخر رفع: {stamp}" if stamp else "☁️ المزامنة: جاهزة",
                                          text_color="#2ecc71")
        else:
            self.lbl_cloud_sync.configure(text="☁️ تعذّر الرفع — تحقق من الإنترنت", text_color="#e74c3c")

    def on_app_closing(self):
        try:
            if getattr(self, 'cloud_sync', None):
                self.cloud_sync.stop()
        except Exception:
            pass
        try:
            if getattr(self, 'gold_watcher', None):
                self.gold_watcher.stop()
        except Exception:
            pass
        """يحاول رفع نسخة أخيرة للسحابة قبل إغلاق البرنامج (بدون تعطيل الإغلاق لو فشل الاتصال)"""
        try:
            threading.Thread(target=cloud_upload_backup, args=(self.client_id, self.db_path), daemon=True).start()
        except Exception:
            pass
        self.destroy()

    def list_local_backups(self):
        """يرجع مسارات النسخ الاحتياطية المحلية لهذا الحساب، من الأحدث للأقدم"""
        try:
            files = [os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir)
                     if f.lower().endswith(".db")]
            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            return files
        except Exception:
            return []

    def describe_backup(self, path):
        """وصف مقروء لنسخة احتياطية: وقتها، حجمها، وعدد حركاتها"""
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            size_kb = max(1, os.path.getsize(path) // 1024)
        except Exception:
            return None

        rows = periods = "?"
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            rows = con.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
            cols = [c[1] for c in con.execute("PRAGMA table_info(invoices)")]
            if "period" in cols:
                periods = con.execute(
                    "SELECT COUNT(DISTINCT COALESCE(NULLIF(period,''), substr(date_time,1,7))) "
                    "FROM invoices").fetchone()[0]
            else:
                periods = con.execute(
                    "SELECT COUNT(DISTINCT substr(date_time,1,7)) FROM invoices").fetchone()[0]
            con.close()
        except Exception:
            pass

        delta = datetime.datetime.now() - mtime
        if delta.days >= 1:
            ago = f"قبل {delta.days} يوم"
        elif delta.seconds >= 3600:
            ago = f"قبل {delta.seconds // 3600} ساعة"
        else:
            ago = f"قبل {max(1, delta.seconds // 60)} دقيقة"

        return {"path": path, "when": mtime.strftime("%Y-%m-%d  %H:%M"), "ago": ago,
                "rows": rows, "periods": periods, "size": f"{size_kb} كيلوبايت"}

    def open_backup_restore_window(self):
        """شاشة استعادة نسخة احتياطية سابقة.

        تعرض كل النسخ المحفوظة بوقتها وعدد حركاتها وفتراتها، فيختار المستخدم
        النسخة الصحيحة بنفسه — لا تخمين ولا استعادة عمياء.
        """
        backups = self.list_local_backups()
        if not backups:
            messagebox.showinfo(
                "لا توجد نسخ",
                f"لم يُعثر على نسخ احتياطية في:\n{self.backup_dir}")
            return

        win = ctk.CTkToplevel(self)
        win.title("استعادة نسخة احتياطية")
        win.geometry("820x560")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="🗄️ استعادة نسخة احتياطية سابقة",
                     font=("Cairo", 20, "bold"), text_color="#d4af37").pack(pady=(16, 2))
        ctk.CTkLabel(win,
                     text="اختر النسخة التي تريد الرجوع إليها — الأحدث أولاً.\n"
                          "قبل الاستعادة تُحفظ نسخة من وضعك الحالي تلقائياً، فلا تفقد شيئاً.",
                     font=("Cairo", 12), text_color="#8b8f95", justify="center").pack(pady=(0, 10))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=18, pady=6)

        cols = ("وقت النسخة", "منذ", "عدد الحركات", "عدد الفترات", "الحجم")
        tree = self.create_standard_treeview(frame, cols, height=14)
        for c, w in zip(cols, (200, 130, 130, 120, 130)):
            tree.column(c, width=w, anchor="center")

        info_by_iid = {}
        for path in backups:
            info = self.describe_backup(path)
            if not info:
                continue
            iid = tree.insert("", "end", values=(
                info["when"], info["ago"], info["rows"], info["periods"], info["size"]))
            info_by_iid[iid] = info

        if not info_by_iid:
            messagebox.showwarning("تعذّر", "لم يمكن قراءة أي نسخة احتياطية.", parent=win)
            win.destroy()
            return

        def do_restore():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "اختر النسخة المراد استعادتها.", parent=win)
                return
            info = info_by_iid[sel[0]]

            if not messagebox.askyesno(
                    "تأكيد الاستعادة",
                    f"استعادة نسخة {info['when']} ({info['ago']})\n"
                    f"عدد حركاتها: {info['rows']}  |  فتراتها: {info['periods']}\n\n"
                    "سيُستبدل وضعك الحالي ببيانات هذه النسخة.\n"
                    "وستُحفظ نسخة من وضعك الحالي قبل ذلك تلقائياً.\n\n"
                    "هل تريد المتابعة؟", parent=win):
                return

            ok, msg = self.restore_from_backup(info["path"])
            win.destroy()
            if ok:
                messagebox.showinfo(
                    "تمت الاستعادة",
                    f"تمت استعادة نسخة {info['when']} بنجاح.\n\n"
                    "سيُغلق البرنامج الآن — افتحه من جديد لتظهر بياناتك المستعادة.")
                self.destroy()
            else:
                messagebox.showerror("تعذّرت الاستعادة", msg)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=12)
        ctk.CTkButton(btns, text="↩️ استعادة النسخة المحددة", font=("Cairo", 15, "bold"),
                      fg_color="#1e8449", hover_color="#145a32", width=250, height=44,
                      command=do_restore).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="📂 فتح مجلد النسخ", font=("Cairo", 13),
                      fg_color="#555555", hover_color="#333333", width=160, height=44,
                      command=lambda: self.open_folder(self.backup_dir)).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="إغلاق", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=44,
                      command=win.destroy).pack(side="left", padx=6)

    def restore_from_backup(self, backup_path):
        """يستعيد قاعدة البيانات من نسخة احتياطية.

        الترتيب مقصود: نحفظ الوضع الحالي أولاً، ثم نتحقق من سلامة النسخة
        المختارة، ثم نستبدل — فلا يُفقد شيء حتى لو كانت النسخة تالفة.
        يرجع: (نجح؟، رسالة)
        """
        try:
            # (١) حفظ الوضع الحالي قبل أي تغيير
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safety = os.path.join(self.backup_dir, f"before_restore_{stamp}.db")
            with sqlite3.connect(self.db_path) as srccon, sqlite3.connect(safety) as dst:
                srccon.backup(dst)

            # (٢) التحقق من سلامة النسخة المختارة قبل الاعتماد عليها
            probe = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
            try:
                integrity = probe.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    return False, f"النسخة تالفة (فحص السلامة: {integrity}).\nلم يتغيّر شيء."
                probe.execute("SELECT COUNT(*) FROM invoices").fetchone()
            finally:
                probe.close()

            # (٣) الاستبدال
            with sqlite3.connect(backup_path) as srccon, sqlite3.connect(self.db_path) as dst:
                srccon.backup(dst)

            log_cloud_error("تمت استعادة نسخة احتياطية",
                            Exception(f"{backup_path} (نسخة الأمان: {safety})"))
            return True, "تمت الاستعادة"
        except Exception as e:
            return False, f"تعذّرت الاستعادة:\n{e}\n\nلم يتغيّر شيء في بياناتك الحالية."

    def open_folder(self, path):
        """يفتح مجلداً في مستكشف الملفات"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showinfo("المسار", f"{path}\n\n({e})")

    def recover_corrupt_database(self):
        """يُستدعى تلقائياً لو كان ملف قاعدة البيانات تالفاً:
        يعزل الملف التالف، ثم يسترجع من أحدث نسخة احتياطية محلية سليمة، وإلا من السحابة."""
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        broken_path = f"{self.db_path}.corrupt_{stamp}"
        try:
            shutil.move(self.db_path, broken_path)
        except Exception:
            try:
                os.remove(self.db_path)
            except Exception:
                pass

        restored_from = None
        for backup in self.list_local_backups():
            if is_sqlite_db_healthy(backup):
                try:
                    shutil.copy2(backup, self.db_path)
                    restored_from = f"نسخة احتياطية محلية ({os.path.basename(backup)})"
                    break
                except Exception:
                    continue

        if not restored_from and self.client_id:
            if cloud_download_backup(self.client_id, self.db_path) and is_sqlite_db_healthy(self.db_path):
                restored_from = "النسخة المحفوظة على السحابة"
            elif os.path.exists(self.db_path):
                try:
                    os.remove(self.db_path)
                except Exception:
                    pass

        msg = (f"تم اكتشاف تلف في ملف قاعدة البيانات، وتم عزله في:\n{broken_path}\n\n"
               + (f"✅ وتم استرجاع بياناتك من: {restored_from}"
                  if restored_from else
                  "⚠️ لم يتم العثور على نسخة سليمة (محلية أو سحابية)، وسيبدأ البرنامج بقاعدة بيانات جديدة.\n"
                  "لا تُدخل بيانات جديدة قبل التواصل مع المدير لمحاولة الاسترجاع."))
        log_cloud_error("استرجاع قاعدة بيانات تالفة", msg.replace("\n", " | "))
        try:
            self.after(600, lambda: messagebox.showwarning("استرجاع قاعدة البيانات", msg))
        except Exception:
            pass

    def open_backup_manager(self):
        """نافذة إدارة النسخ الاحتياطية والسحابة: رفع فوري، استرجاع، وعرض مسارات الملفات"""
        win = ctk.CTkToplevel(self)
        win.title("النسخ الاحتياطي والسحابة")
        win.geometry("640x520")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="☁️ النسخ الاحتياطي واسترجاع البيانات", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(14, 6))

        info = ctk.CTkFrame(win)
        info.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(info, text=f"مجلد ملفات النظام:\n{APP_DATA_DIR}", font=("Cairo", 12), justify="right", anchor="e").pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(info, text=f"قاعدة البيانات:\n{self.db_path}", font=("Cairo", 12), justify="right", anchor="e").pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(info, text=f"النسخ الاحتياطية المحلية:\n{self.backup_dir}", font=("Cairo", 12), justify="right", anchor="e").pack(fill="x", padx=10, pady=(2, 8))

        lbl_status = ctk.CTkLabel(win, text="", font=("Cairo", 13, "bold"), text_color="#2ecc71")
        lbl_status.pack(pady=4)

        backups = self.list_local_backups()
        ctk.CTkLabel(win, text=f"عدد النسخ الاحتياطية المحلية المتاحة: {len(backups)}", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(pady=(2, 8))

        def do_backup_now():
            self.perform_backup()
            lbl_status.configure(text="✅ تم أخذ نسخة احتياطية محلية جديدة", text_color="#2ecc71")

        def do_upload_now():
            if not self.client_id:
                lbl_status.configure(text="هذه جلسة محلية بدون حساب سحابي.", text_color="#e67e22")
                return
            lbl_status.configure(text="⏳ جاري الرفع للسحابة...", text_color="#1f77b4")

            def _work():
                ok = cloud_upload_backup(self.client_id, self.db_path)
                self.after(0, lambda: lbl_status.configure(
                    text="✅ تم رفع نسخة محدّثة للسحابة" if ok else "⚠️ تعذّر الرفع — تأكد من الاتصال بالإنترنت",
                    text_color="#2ecc71" if ok else "#e74c3c"))

            threading.Thread(target=_work, daemon=True).start()

        def do_cloud_restore():
            if not self.client_id:
                lbl_status.configure(text="هذه جلسة محلية بدون حساب سحابي.", text_color="#e67e22")
                return
            if not messagebox.askyesno(
                    "استرجاع من السحابة",
                    "سيتم استبدال البيانات الحالية على هذا الجهاز بآخر نسخة محفوظة على السحابة لحسابك.\n\n"
                    "سيتم أولاً حفظ نسخة احتياطية من البيانات الحالية تلقائياً.\n"
                    "هل تريد المتابعة؟", parent=win):
                return

            self.perform_backup()   # نسخة أمان من الوضع الحالي قبل أي استبدال
            tmp_path = f"{self.db_path}.cloud_tmp"
            lbl_status.configure(text="⏳ جاري التنزيل من السحابة...", text_color="#1f77b4")

            def _work():
                ok = cloud_download_backup(self.client_id, tmp_path) and is_sqlite_db_healthy(tmp_path)

                def _apply():
                    if not ok:
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
                        lbl_status.configure(text="⚠️ تعذّر الاسترجاع — لا توجد نسخة سليمة أو لا يوجد اتصال", text_color="#e74c3c")
                        return
                    try:
                        shutil.move(tmp_path, self.db_path)
                    except Exception as e:
                        lbl_status.configure(text=f"⚠️ تعذّر استبدال الملف: {e}", text_color="#e74c3c")
                        return
                    self.load_data_from_db()
                    self.update_period_selector()
                    self.recalculate_all()
                    lbl_status.configure(text="✅ تم استرجاع البيانات من السحابة وتحديث كل الشاشات", text_color="#2ecc71")

                self.after(0, _apply)

            threading.Thread(target=_work, daemon=True).start()

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=10)
        ctk.CTkButton(btns, text="💾 نسخة احتياطية الآن", font=("Cairo", 14, "bold"), width=185, height=42,
                      fg_color="#1e8449", hover_color="#145a32", command=do_backup_now).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="⬆️ رفع للسحابة الآن", font=("Cairo", 14, "bold"), width=185, height=42,
                      fg_color="#1f77b4", hover_color="#144d75", command=do_upload_now).pack(side="right", padx=6)

        # الاستعادة المحلية أولاً وأبرز: النسخ على جهازك هي الأوثق، والسحابة
        # قد تحمل حالة لا تريدها
        ctk.CTkButton(win, text="🗄️ استعادة نسخة احتياطية من جهازي", font=("Cairo", 15, "bold"),
                      width=340, height=48, fg_color="#1e8449", hover_color="#145a32",
                      command=lambda: (win.destroy(), self.open_backup_restore_window())).pack(pady=(10, 6))

        ctk.CTkButton(win, text="⬇️ استرجاع آخر نسخة من السحابة", font=("Cairo", 14, "bold"), width=300, height=44,
                      fg_color="#b8860b", hover_color="#daa520", command=do_cloud_restore).pack(pady=8)

        ctk.CTkButton(win, text="📂 فتح مجلد ملفات النظام", font=("Cairo", 13, "bold"), width=240, height=38,
                      fg_color="#555555", hover_color="#333333", command=self.open_app_data_folder).pack(pady=(4, 14))

    def perform_backup(self):
        """نظام النسخ الاحتياطي الآمن لقاعدة البيانات"""
        try:
            if not os.path.exists(self.backup_dir):
                os.makedirs(self.backup_dir)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self.backup_dir, f"gold_backup_{timestamp}.db")
            
            # النسخ الآمن باستخدام مكتبة sqlite3 لمنع التلف أثناء النسخ
            with sqlite3.connect(self.db_path) as src:
                with sqlite3.connect(backup_path) as dst:
                    src.backup(dst)
            
            # الاحتفاظ بأحدث 20 نسخة فقط لتوفير المساحة
            backups = sorted(os.listdir(self.backup_dir))
            while len(backups) > 20:
                oldest = backups.pop(0)
                os.remove(os.path.join(self.backup_dir, oldest))
        except Exception as e:
            print("فشل النسخ الاحتياطي التلقائي:", e)

    def schedule_backup(self):
        """جدولة النسخ الاحتياطي كل 15 دقيقة (900000 ملي ثانية)"""
        self.after(900000, self.auto_backup_trigger)

    def auto_backup_trigger(self):
        self.perform_backup()
        self.schedule_backup()

    def setup_treeview_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        bg_color = "#242424" if self.current_theme == "Dark" else "#f2f2f2"
        fg_color = "#ffffff" if self.current_theme == "Dark" else "#000000"
        field_bg = "#242424" if self.current_theme == "Dark" else "#ffffff"
        
        # --- تم تصغير الخط إلى 11 وارتفاع الصفوف ليتناسب مع النوافذ والأرشيف ---
        style.configure("Treeview",
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=field_bg,
                        rowheight=35,
                        font=("Cairo", 13, "bold"))
        
        style.configure("Treeview.Heading",
                        background="#1f77b4",
                        foreground="#ffffff",
                        font=("Cairo", 13, "bold"),
                        padding=(5, 4),
                        relief="flat")
        
        style.map("Treeview.Heading", background=[('active', '#144d75')])

    def toggle_theme(self):
        # التنسيق الموحّد يُعاد تطبيقه بعد التبديل ليتبع المظهر الجديد
        self.after(60, self.apply_design_system)
        if self.current_theme == "Dark":
            self.current_theme = "Light"
            ctk.set_appearance_mode("Light")
            self.btn_theme.configure(text="🎨 المظهر: فاتح ☀️")
        else:
            self.current_theme = "Dark"
            ctk.set_appearance_mode("Dark")
            self.btn_theme.configure(text="🎨 المظهر: داكن 🌙")
            
        self.setup_treeview_styles()
        self.recalculate_all()


    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # تفعيل نظام (WAL) للحماية القصوى ضد انقطاع الكهرباء
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS names (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    category TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # تثبيت المسميات المطلوبة في قسم الآلة/المكائن تلقائياً
            cursor.execute("INSERT OR IGNORE INTO names (name, category) VALUES ('الكاستينج', 'الآلة/المكائن')")
            cursor.execute("INSERT OR IGNORE INTO names (name, category) VALUES ('التلميع النهائي', 'الآلة/المكائن')")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    invoice_id INTEGER PRIMARY KEY,
                    date_time TEXT,
                    name TEXT,
                    op_type TEXT,
                    weight REAL,
                    before_w REAL,
                    after_w REAL,
                    note TEXT,
                    settled_status TEXT DEFAULT 'ACTIVE',
                    trees_count REAL DEFAULT 0,
                    set_number TEXT DEFAULT '',
                    period TEXT DEFAULT ''
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monthly_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_date TEXT,
                    name TEXT,
                    category TEXT,
                    sarf REAL DEFAULT 0,
                    qabd REAL DEFAULT 0,
                    leez REAL DEFAULT 0,
                    polish REAL DEFAULT 0,
                    mufanish_8 REAL DEFAULT 0,
                    mufanish_4 REAL DEFAULT 0,
                    salk_rajia REAL DEFAULT 0,
                    ayar_fahs REAL DEFAULT 0,
                    before_w REAL DEFAULT 0,
                    after_w REAL DEFAULT 0,
                    khayas REAL DEFAULT 0,
                    production REAL DEFAULT 0,
                    note TEXT,
                    linked_inv_id INTEGER DEFAULT 0,
                    trees_count REAL DEFAULT 0
                )
            """)
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_date ON invoices(date_time)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_name ON invoices(name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_inv_status ON invoices(settled_status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_arch_date ON monthly_archive(archive_date)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_arch_cat ON monthly_archive(category)")

            cursor.execute("PRAGMA table_info(invoices)")
            columns = [col[1] for col in cursor.fetchall()]
            if "settled_status" not in columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN settled_status TEXT DEFAULT 'ACTIVE'")
            if "trees_count" not in columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN trees_count REAL DEFAULT 0")
            if "set_number" not in columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN set_number TEXT DEFAULT ''")
            if "row_number" not in columns:
                cursor.execute("ALTER TABLE invoices ADD COLUMN row_number TEXT DEFAULT ''")
            if "manual_no" not in columns:
                # رقم الفاتورة اليدوي (يُدخله المستخدم في شاشة المبيعات ويُعتمد كرقم للفاتورة)
                cursor.execute("ALTER TABLE invoices ADD COLUMN manual_no TEXT DEFAULT ''")
            if "period" not in columns:
                # الفترة المحاسبية صراحةً، منفصلة عن تاريخ العملية الحقيقي
                cursor.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")
            # ═══════════════════════════════════════════════════════════
            #  ترحيل السطور المعلوماتية المسجّلة قبل هذا التحديث
            #
            #  خياس البوليش وخياس المركب وصافي الطقم كانت تُسجَّل بحالة
            #  SETTLED_INOUT التي **تُحتسب** في الخزينة. فتظهر في كشف حساب
            #  الخزينة وتُنقص رصيدها رغم أنها معلوماتية بحتة.
            #
            #  تُحوَّل هنا إلى MEMO — الحالة التي ترفضها كل الفلاتر المحاسبية —
            #  فتختفي من الكشف ويعود الرصيد صحيحاً بأثر رجعي.
            #  (خياس التلميع النهائي بعلامة 0.0 يبقى ACTIVE كما هو)
            # ═══════════════════════════════════════════════════════════
            cursor.execute("""
                UPDATE invoices
                   SET settled_status = ?
                 WHERE op_type = 'خياس طقوم'
                   AND settled_status IN ('ACTIVE', 'SETTLED_INOUT')
                   AND trees_count IN (?, ?, ?)
            """, (MEMO_STATUS, KHAYAS_MARK_POLISH, KHAYAS_MARK_ASSEMBLER, KHAYAS_MARK_NET))
            _memo_fixed = cursor.rowcount or 0
            if _memo_fixed:
                log_cloud_error("ترحيل السطور المعلوماتية",
                                Exception(f"حُوّل {_memo_fixed} سطراً إلى MEMO"))

            # الحركات القديمة: الفترة = شهر تاريخها (نفس السلوك السابق حرفياً).
            # يُكتم صندوق الصادر أثناء الترحيل: هذا UPDATE على كل الحركات،
            # ولولا الكتم لأطلق المحفّزات فأعاد رفع القاعدة كاملة للسحابة.
            try:
                cursor.execute("INSERT INTO sync_state(key, value) VALUES('suppress_outbox','1') "
                               "ON CONFLICT(key) DO UPDATE SET value='1'")
            except Exception:
                pass
            cursor.execute("UPDATE invoices SET period = substr(date_time, 1, 7) "
                           "WHERE period IS NULL OR period = ''")
            try:
                cursor.execute("UPDATE sync_state SET value='0' WHERE key='suppress_outbox'")
            except Exception:
                pass
                    
            cursor.execute("PRAGMA table_info(monthly_archive)")
            arch_cols = [col[1] for col in cursor.fetchall()]
            needed_cols = {
                "archive_date": "TEXT", "sarf": "REAL DEFAULT 0", "qabd": "REAL DEFAULT 0", "leez": "REAL DEFAULT 0",
                "polish": "REAL DEFAULT 0", "mufanish_8": "REAL DEFAULT 0", "mufanish_4": "REAL DEFAULT 0", 
                "salk_rajia": "REAL DEFAULT 0", "ayar_fahs": "REAL DEFAULT 0", "before_w": "REAL DEFAULT 0", 
                "after_w": "REAL DEFAULT 0", "khayas": "REAL DEFAULT 0", "production": "REAL DEFAULT 0", 
                "linked_inv_id": "INTEGER DEFAULT 0", "trees_count": "REAL DEFAULT 0"
            }
            for col_name, col_type in needed_cols.items():
                if col_name not in arch_cols:
                    cursor.execute(f"ALTER TABLE monthly_archive ADD COLUMN {col_name} {col_type}")
            conn.commit()

    def load_data_from_db(self):
        self.categories = {"المصنعين": [], "المركبين": [], "الآلة/المكائن": [], "الكاستنج": [], "التلميع": [], "التلميع/البف": [], "الموردين": [], "حسابات إضافية": [], "أقسام_خياس_إضافية": [], "نسب_خصم_احجار": []}
        self.invoices = {}
        self.opening_balance = 0.0

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, category FROM names")
            for row in cursor.fetchall():
                if row[1] in self.categories:
                    self.categories[row[1]].append(row[0])

            cursor.execute("SELECT invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status, trees_count, set_number, row_number, manual_no, period FROM invoices")
            for row in cursor.fetchall():
                inv_id = row[0]
                self.invoices[inv_id] = {
                    "رقم الفاتورة": inv_id, "التاريخ": row[1], "الاسم": row[2],
                    "النوع": row[3], "الوزن": row[4], "قبل": row[5], "بعد": row[6], "البيان": row[7],
                    "settled_status": row[8], "trees_count": row[9] if len(row)>9 and row[9] else 0.0,
                    "رقم الفاتورة اليدوي": row[12] if len(row) > 12 and row[12] else "",
                    "set_number": row[10] if len(row)>10 and row[10] else "",
                    "row_number": row[11] if len(row)>11 and row[11] else "",
                    # الفترة المحاسبية صراحةً؛ وتُشتق من التاريخ لو كانت فارغة
                    "period": (row[13] if len(row) > 13 and row[13] else str(row[1] or "")[:7])
                }
                if row[3] == "رصيد افتتاحي":
                    self.opening_balance = row[4]
                    
            cursor.execute("SELECT MAX(invoice_id) FROM invoices")
            max_id = cursor.fetchone()[0]

        self.invoice_counter = max_id if max_id else 1000

        # الفترة المعروضة = الشهر الحالي فعلياً حسب تاريخ الجهاز، دائماً.
        #
        # سابقاً كانت تُضبط على (أحدث شهر فيه حركات)، فكان البرنامج يفتح على
        # الشهر السابق في بداية كل شهر جديد قبل تسجيل أول حركة فيه — وتُعبّأ
        # خانات التاريخ بأول يوم من الشهر الماضي، فتُسجَّل حركات الشهر الجديد
        # في الشهر الخطأ. الاختيار اليدوي من قائمة الفترات يبقى متاحاً كما هو.
        self.current_display_month = datetime.datetime.now().strftime("%Y-%m")

    def save_invoice_to_db(self, inv_id, inv_data):
        """يرجع True لو تم الحفظ فعلياً، أو False لو تم المنع (تعديل على فاتورة موجودة ومقفول عليها التعديل)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""SELECT invoice_id, date_time, name, op_type, weight, before_w, after_w, note,
                               settled_status, trees_count, set_number, row_number, manual_no, period FROM invoices WHERE invoice_id = ?""", (inv_id,))
            existing_row = cursor.fetchone()
            existing_manual = (existing_row[12] if existing_row and len(existing_row) > 12 and existing_row[12] else "")
            existing_period = (existing_row[13] if existing_row and len(existing_row) > 13 and existing_row[13] else "")

            # ختم الفترة المحاسبية مركزياً لكل الحركات:
            #   • حركة جديدة  → الفترة المعروضة وقت التسجيل
            #   • حركة قائمة  → تبقى فترتها الأصلية ما لم تُمرَّر صراحةً
            # المركزية مقصودة: مسارات إنشاء الحركات كثيرة (٢٧ موضعاً)، وختمها
            # هنا يضمن ألا يفلت أي مسار بلا فترة فتسقط حركته من كل الشاشات.
            if not inv_data.get("period"):
                inv_data["period"] = existing_period or self.current_display_month

            # فاتورة موجودة بالفعل بقاعدة البيانات (تعديل على عملية سابقة) ومقفول عليه التعديل؟
            if existing_row and not self.check_edit_permission():
                # نرجّع الذاكرة لنفس القيمة المخزّنة فعلياً بقاعدة البيانات (بدون أي تغيير وهمي)
                self.invoices[inv_id] = {
                    "رقم الفاتورة": existing_row[0], "التاريخ": existing_row[1], "الاسم": existing_row[2],
                    "النوع": existing_row[3], "الوزن": existing_row[4], "قبل": existing_row[5], "بعد": existing_row[6],
                    "البيان": existing_row[7], "settled_status": existing_row[8],
                    "trees_count": existing_row[9] if existing_row[9] else 0.0,
                    "set_number": existing_row[10] if existing_row[10] else "",
                    "row_number": existing_row[11] if existing_row[11] else "",
                    "رقم الفاتورة اليدوي": existing_manual,
                    "period": existing_period or str(existing_row[1] or "")[:7]
                }
                return False

            cursor.execute("""
                INSERT OR REPLACE INTO invoices (invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status, trees_count, set_number, row_number, manual_no, period)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (inv_id, inv_data["التاريخ"], inv_data["الاسم"], inv_data["النوع"], 
                  inv_data["الوزن"], inv_data.get("قبل", 0.0), inv_data.get("بعد", 0.0), 
                  inv_data["البيان"], inv_data.get("settled_status", "ACTIVE"), inv_data.get("trees_count", 0.0), inv_data.get("set_number", ""), inv_data.get("row_number", ""),
                  inv_data.get("رقم الفاتورة اليدوي", existing_manual),
                  inv_data.get("period") or existing_period or self.inv_period(inv_data)))
            conn.commit()
        self.mark_backup_dirty()
        return True

    def delete_invoice_from_db(self, inv_id):
        """يرجع True لو تم الحذف فعلياً، أو False لو تم المنع.
        الحذف مسموح دائماً حتى لو أقفل المدير التعديل (القفل يخص تعديل الحركات فقط)."""
        if not self.check_delete_permission():
            return False
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM invoices WHERE invoice_id = ?", (inv_id,))
            conn.commit()
        if inv_id in self.invoices:
            del self.invoices[inv_id]
        self.mark_backup_dirty()
        return True

    def delete_worker_from_db(self, worker_name, category, keep_transactions=True):
        """يحذف اسم العامل من شجرة الحسابات.

        keep_transactions=True (الافتراضي): **حركاته المحاسبية تبقى كما هي**.
        حذف حركات عامل يغيّر رصيد الخزينة وإجمالي الفواقد بأثر رجعي ويُفسد
        فترات مقفلة — والاسم مجرد تسمية، أما الحركات فقيود محاسبية.
        تمرير False يحذفها معه (يُستخدم عند حذف صندوق خياس بكامله بعد تأكيد
        المستخدم على عدد حركاته).
        """
        if not self.check_delete_permission():
            return False

        # لقطة للتراجع قبل أي تغيير
        self.push_undo(f"حذف الاسم ({worker_name})")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM names WHERE name = ? AND category = ?", (worker_name, category))
            if not keep_transactions:
                cursor.execute("DELETE FROM invoices WHERE name = ? AND settled_status = 'ACTIVE'",
                               (worker_name,))
            conn.commit()

        if worker_name in self.categories.get(category, []):
            self.categories[category].remove(worker_name)
        if not keep_transactions:
            self.invoices = {k: v for k, v in self.invoices.items() if v["الاسم"] != worker_name}
        self.mark_backup_dirty()
        return True

    # =====================================================================
    # --- التراجع عن آخر خطوة (مثل Ctrl+Z) ---
    # =====================================================================
    UNDO_LIMIT = 20

    def push_undo(self, label):
        """يحفظ لقطة من الحالة قبل عملية قابلة للتراجع.

        اللقطة نسخة من الحركات وشجرة الأسماء — وهما مصدر كل الأرقام في النظام،
        فاستعادتهما تُرجع الوضع كما كان تماماً.
        """
        try:
            import copy
            if not hasattr(self, "_undo_stack"):
                self._undo_stack = []
            self._undo_stack.append({
                "label": label,
                "invoices": copy.deepcopy(self.invoices),
                "categories": copy.deepcopy(self.categories),
                "counter": self.invoice_counter,
            })
            if len(self._undo_stack) > self.UNDO_LIMIT:
                self._undo_stack.pop(0)
            self.update_undo_buttons()
        except Exception as e:
            log_cloud_error("تعذّر حفظ لقطة التراجع", e)

    def can_undo(self):
        return bool(getattr(self, "_undo_stack", []))

    def update_undo_buttons(self):
        """يفعّل أو يعطّل أزرار التراجع حسب توفّر خطوة سابقة"""
        label = "↩️ تراجع"
        if self.can_undo():
            label = f"↩️ تراجع: {self._undo_stack[-1]['label']}"
        for btn in getattr(self, "_undo_buttons", []):
            try:
                btn.configure(text=label if len(label) < 34 else "↩️ تراجع",
                              state="normal" if self.can_undo() else "disabled")
            except Exception:
                continue

    def register_undo_button(self, btn):
        if not hasattr(self, "_undo_buttons"):
            self._undo_buttons = []
        self._undo_buttons.append(btn)
        self.update_undo_buttons()

    def undo_last_action(self):
        """يُرجع الحالة إلى ما قبل آخر خطوة قابلة للتراجع"""
        if not self.can_undo():
            messagebox.showinfo("لا يوجد", "لا توجد خطوة يمكن التراجع عنها.")
            return
        if not self.check_edit_permission():
            return

        snap = self._undo_stack[-1]
        if not messagebox.askyesno(
                "تأكيد التراجع",
                f"سيتم التراجع عن: {snap['label']}\n\n"
                "وتعود البيانات كما كانت قبل هذه الخطوة. هل تريد المتابعة؟"):
            return

        snap = self._undo_stack.pop()
        try:
            self.invoices = snap["invoices"]
            self.categories = snap["categories"]
            self.invoice_counter = snap["counter"]
            self.rewrite_database_from_memory()
            self.recalculate_all()
            self.update_undo_buttons()
            messagebox.showinfo("تم التراجع", f"تم التراجع عن: {snap['label']}")
        except Exception as e:
            log_cloud_error("تعذّر التراجع", e)
            messagebox.showerror("خطأ", f"تعذّر إتمام التراجع:\n{e}")

    def rewrite_database_from_memory(self):
        """يُعيد كتابة جدولَي الحركات والأسماء من الذاكرة (تنفيذ التراجع).

        تُكتب في معاملة واحدة: إما أن ينجح كل شيء أو لا يتغيّر شيء —
        فلا تبقى القاعدة في حالة نصفية لو انقطع التنفيذ.
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute("DELETE FROM invoices")
                cur.execute("DELETE FROM names")
                for inv in self.invoices.values():
                    cur.execute("""INSERT INTO invoices
                        (invoice_id, date_time, name, op_type, weight, before_w, after_w,
                         note, settled_status, trees_count, set_number, row_number, manual_no, period)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (inv.get("رقم الفاتورة"), inv.get("التاريخ"), inv.get("الاسم"),
                         inv.get("النوع"), inv.get("الوزن", 0.0), inv.get("قبل", 0.0),
                         inv.get("بعد", 0.0), inv.get("البيان", ""),
                         inv.get("settled_status", "ACTIVE"), inv.get("trees_count", 0.0),
                         inv.get("set_number", ""), inv.get("row_number", ""),
                         inv.get("رقم الفاتورة اليدوي", ""),
                         inv.get("period") or self.inv_period(inv)))
                for cat, names in self.categories.items():
                    for n in names:
                        cur.execute("INSERT OR IGNORE INTO names (name, category) VALUES (?, ?)",
                                    (n, cat))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        self.mark_backup_dirty()

    def save_name_to_db(self, name, category):
        # إضافة اسم/عامل/مورد جديد = عملية طبيعية يومية، مسموحة دائماً بدون الحاجة لإذن المدير
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("INSERT INTO names (name, category) VALUES (?, ?)", (name, category))
                conn.commit()
            except sqlite3.IntegrityError:
                pass
        self.mark_backup_dirty()

    def get_setting(self, key, default=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key, value):
        # إعدادات عامة للنظام (مش "فاتورة أو رقم مُثبت") — مسموحة دائماً
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()
        self.mark_backup_dirty()

    # =====================================================================
    # --- تلوين الأرقام السالبة: إعداد مستقل لكل قسم، محفوظ ويبقى بعد الإغلاق ---
    # =====================================================================
    def negative_color_enabled(self, section):
        """هل تلوين السالب مفعّل في هذا القسم؟ (الافتراضي: غير مفعّل)"""
        return self.get_setting(f"neg_color_{section}", "0") == "1"

    def toggle_negative_color(self, section, refresh_callback=None):
        """يبدّل حالة التلوين لهذا القسم ويعيد رسم جدوله فوراً"""
        new_value = "0" if self.negative_color_enabled(section) else "1"
        self.set_setting(f"neg_color_{section}", new_value)
        self.update_negative_color_button(section)
        if refresh_callback:
            try:
                refresh_callback()
            except Exception:
                pass

    def build_negative_color_button(self, parent, section, refresh_callback=None):
        """زر صغير يظهر في أعلى جدول كل قسم (بما فيها الأقسام المضافة لاحقاً)"""
        if not hasattr(self, "neg_color_buttons"):
            self.neg_color_buttons = {}

        btn = ctk.CTkButton(
            parent, text="", font=("Cairo", 12, "bold"), width=105, height=28,
            command=lambda s=section, cb=refresh_callback: self.toggle_negative_color(s, cb))
        btn.pack(side="left", padx=5)

        self.neg_color_buttons[section] = btn
        self.update_negative_color_button(section)
        return btn

    def update_negative_color_button(self, section):
        """يحدّث شكل الزر ليعكس حالته الحالية بوضوح"""
        btn = getattr(self, "neg_color_buttons", {}).get(section)
        if btn is None:
            return
        if self.negative_color_enabled(section):
            btn.configure(text="🔴 تلوين السالب", fg_color="#8b0000", hover_color="#a52a2a")
        else:
            btn.configure(text="⚪ لون واحد", fg_color="#555555", hover_color="#333333")

    def get_discount_percentages(self):
        """كل نسب الخصم المتاحة لخانة الأحجار بعد الخصم (كنص، بدون علامة %) - القيمة الافتراضية 30 دائماً متاحة"""
        pcts = [n.replace("نسبة%", "") for n in self.categories.get("نسب_خصم_احجار", [])]
        if not pcts:
            pcts = ["30"]
        return pcts

    def add_discount_percentage(self, pct_str):
        label = f"نسبة%{pct_str}"
        if label not in self.categories.get("نسب_خصم_احجار", []):
            self.categories.setdefault("نسب_خصم_احجار", []).append(label)
            self.save_name_to_db(label, "نسب_خصم_احجار")

    def get_last_discount_percentage(self):
        return self.get_setting("last_discount_pct", self.get_discount_percentages()[0])

    def set_last_discount_percentage(self, pct_str):
        self.set_setting("last_discount_pct", pct_str)

    def register_operation_period(self, date_val):
        """تُستدعى بعد أي ترحيل: تحدّث قائمة الفترات فقط.

        الحركة تُختم بالفترة المعروضة وقت تسجيلها (save_invoice_to_db) أياً كان
        تاريخها — فتظهر في جدول الفترة الحالية دائماً. كانت هنا رسالة تقول إن
        الحركة رُحّلت لفترة شهر تاريخها ولن تظهر في الفترة الحالية، وهذا عكس
        ما يحدث فعلاً، فأُزيلت.
        """
        self.update_period_selector()

    @staticmethod
    def inv_period(inv):
        """الفترة المحاسبية لحركة: العمود الصريح إن وُجد، وإلا تُشتق من تاريخها.

        الاشتقاق ضروري لتوافق بيانات العملاء المسجّلة قبل هذا التحديث، حيث
        كانت الفترة = شهر التاريخ دائماً.
        """
        period = (inv.get("period") or "").strip()
        if period:
            return period
        # الاشتقاق من التاريخ مباشرةً هنا فقط — لا عبر self.inv_period وإلا
        # استدعت الدالة نفسها بلا نهاية
        return str(inv.get("التاريخ", ""))[:7]

    @classmethod
    def inv_in_period(cls, inv, month):
        """هل تنتمي الحركة للفترة المطلوبة؟ (فترة فارغة = بلا تقييد)"""
        if not month:
            return True
        return cls.inv_period(inv) == month

    def get_treasury_type_sets(self):
        """أنواع صرف/قبض كل صناديق الخياس (الثابتة والمضافة) وأسماء مسترجعاتها."""
        sarf_types, qabd_types, mustarja_names = set(), set(), set()
        for cat in self.get_all_stage_categories():
            madin, qabd, mustarja = self.get_stage_config(cat)
            if madin:
                sarf_types.add(madin)
            if qabd:
                qabd_types.add(qabd)
            if mustarja:
                mustarja_names.add(mustarja)
        return sarf_types, qabd_types, mustarja_names

    def treasury_bucket(self, inv, type_sets=None):
        """يصنّف حركة واحدة في بند من بنود الخزينة ويرجع (البند، الأثر بإشارته).

        ══ المصدر الوحيد لتعريف ما يمسّ الخزينة ══
        يستخدمه شريط الخزينة، ورصيد أول المدة، والتقرير الشهري، وكشف حساب
        الخزينة — فيستحيل أن يختلف رقم شاشة عن رقم التقرير.

        البنود:
          opening  رصيد افتتاحي / قيد افتتاحي من شاشة الرصيد الافتتاحي   (+)
          inbound  وارد ذهب                                               (+)
          sales    مبيعات ذهب / صادر ذهب                                  (−)
          boxes    صرف صناديق الخياس (−) وقبضها والذهب المسترجع منها (+)
          closed   صرف خياس مقفل (إقفال الأرشفة القديم)                   (−)
          journal  قيد يومي على «حساب الخزينة» (مدين + / دائن −)

        (خياس المصنعين والمركبين لا يأتي من حركة واحدة بل من معادلة القسم،
         فيُضاف في treasury_period_components.)
        """
        if inv.get("settled_status") not in COUNTED_STATUSES:
            return None, 0.0
        sarf_types, qabd_types, mustarja_names = type_sets or self.get_treasury_type_sets()
        t = inv.get("النوع")
        w = inv.get("الوزن", 0.0) or 0.0

        if t == "رصيد افتتاحي":
            return "opening", w
        if t == "وارد ذهب (عيار 18)":
            if inv.get("trees_count") == 1.0 and inv.get("البيان") == "قيد افتتاحي":
                return "opening", w
            if inv.get("الاسم") in mustarja_names:
                return "boxes", w          # ذهب عاد من صندوق خياس: يخفّض خياسه
            return "inbound", w
        if t in ("مبيعات ذهب", "مبيعات ذهب مع الماس", "صادر ذهب"):
            return "sales", -w
        if t == "صرف خياس مقفل":
            return "closed", -w
        if t in sarf_types:
            return "boxes", -w
        if t in qabd_types:
            return "boxes", w
        if inv.get("الاسم") == "حساب الخزينة":
            if t == "قيد يومي مدين":
                return "journal", w
            if t == "قيد يومي دائن":
                return "journal", -w
        return None, 0.0

    def treasury_effect(self, inv):
        """أثر حركة واحدة على رصيد الخزينة (+ وارد، − صادر، 0 لا أثر)."""
        return self.treasury_bucket(inv)[1]

    def get_workers_khayas(self, month, invoices=None):
        """الخياس الفعلي للمصنعين والمركبين في فترة — يُخصم من الخزينة سواء أُقفل أم لا.

        الإقفال قيد مزدوج بين «حساب الخسائر» وحساب الصندوق فقط، ولا يمسّ الخزينة:
        هو إعادة تصنيف للفاقد لا ذهبٌ عاد. لذلك يبقى الخياس مخصوماً بعد الإقفال —
        في فترته، وفي رصيد أول المدة لكل ما بعدها.

        (كان رصيد أول المدة يخصم «غير المُقفل» فقط، فإقفال خياس فترة ٨ كان يرفع
        رصيد افتتاح فترة ٩ بقيمة المُقفل — فتختلف أرقام فترة ٩ عن نهاية فترة ٨.
        والإقفال القديم بالأرشفة يحوّل السطور إلى SETTLED ويسجّل «صرف خياس مقفل»،
        فيصير الخياس الحي صفراً ويُخصم عبر بند closed — لا يُخصم مرتين.)
        """
        return round(
            self.get_actual_section_khayas("المصنعين", target_month=month, invoices=invoices)
            + self.get_actual_section_khayas("المركبين", target_month=month, invoices=invoices), 2)

    def treasury_period_components(self, month, invoices=None, type_sets=None):
        """بنود حركة الخزينة داخل فترة واحدة (بإشاراتها) وصافيها.

        invoices: حركات الفترة إن كانت مجمّعة مسبقاً (تسريع)، وإلا تُقرأ هنا.
        """
        type_sets = type_sets or self.get_treasury_type_sets()
        if invoices is None:
            invoices = [inv for inv in self.invoices.values() if self.inv_in_period(inv, month)]
        comp = {"opening": 0.0, "inbound": 0.0, "sales": 0.0,
                "boxes": 0.0, "closed": 0.0, "journal": 0.0}
        for inv in invoices:
            if not inv.get("التاريخ"):
                continue
            bucket, amount = self.treasury_bucket(inv, type_sets)
            if bucket:
                comp[bucket] += amount
        comp["workers"] = -self.get_workers_khayas(month, invoices=invoices)
        comp = {k: round(v, 2) for k, v in comp.items()}
        comp["net"] = round(sum(comp.values()), 2)
        return comp

    def get_treasury_ledger(self, before=None):
        """دفتر الخزينة لكل الفترات بالترتيب.

        لكل فترة: carry (رصيد أولها = نهاية سابقتها بالضبط)، وبنودها، و closing.
        كل حركة تنتمي لفترتها (عمود period) لا لشهر تاريخها، والفترة لا تتأثر
        بالفترة المعروضة حالياً — فالتقرير يعطي الأرقام نفسها من أي فترة فُتح.

        before: يقصر الحساب على الفترات السابقة لها (يكفي لرصيد أول المدة).
        """
        by_period = {}
        for inv in self.invoices.values():
            period = self.inv_period(inv)
            if period:
                by_period.setdefault(period, []).append(inv)
        periods = {p for p, invs in by_period.items()
                   if any(i.get("settled_status") in COUNTED_STATUSES for i in invs)}
        if getattr(self, "current_display_month", None):
            periods.add(self.current_display_month)

        type_sets = self.get_treasury_type_sets()
        ledger, carry = [], 0.0
        for period in sorted(periods):
            if before and period >= before:
                break
            comp = self.treasury_period_components(period, invoices=by_period.get(period, []),
                                                   type_sets=type_sets)
            row = dict(comp)
            row["period"] = period
            row["carry"] = round(carry, 2)
            row["closing"] = round(carry + comp["net"], 2)
            ledger.append(row)
            carry = row["closing"]
        return ledger

    def period_closing_datetime(self, month):
        """آخر لحظة في الفترة: تاريخ مناسب لقيود إقفالها.

        استخدام تاريخ اليوم كان يضع قيد إقفال شهر ٩ في أول شهر ١٠، فيبدو
        كأنه حركة الشهر الجديد.
        """
        try:
            year, mon = (int(x) for x in str(month).split("-")[:2])
            last_day = calendar.monthrange(year, mon)[1]
            return f"{year:04d}-{mon:02d}-{last_day:02d} 23:59:00"
        except (ValueError, IndexError):
            return f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"

    def get_opening_treasury_balance(self, month):
        """رصيد أول المدة = رصيد نهاية الفترة السابقة بالضبط.

        يُقرأ من دفتر الخزينة الموحّد (get_treasury_ledger)، الذي يبني شريط
        الخزينة والتقرير الشهري أيضاً — فرصيد افتتاح فترة ٩ = آخر رصيد في
        فترة ٨ دائماً، سواء أُقفل خياس فترة ٨ أم لا.
        """
        if not month:
            return 0.0
        ledger = self.get_treasury_ledger(before=month)
        return round(ledger[-1]["closing"], 2) if ledger else 0.0

    def get_smart_default_date(self):
        """تاريخ العملية الافتراضي: **تاريخ اليوم الحقيقي** دائماً.

        العملية تُعرض وتُسجَّل بتاريخها الحيّ (مثلاً ٢٠٢٦-٠٩-٠١)، بينما تُثبَّت
        محاسبياً في الفترة المعروضة (مثلاً ٢٠٢٦-٠٨) عبر عمود (period) المستقل.
        فلا يُزوَّر التاريخ ليدخل الفترة، ولا تُحسب العملية في فترة غير فترتها.
        """
        # التاريخ هو تاريخ اليوم الحقيقي دائماً، مهما كانت الفترة المعروضة.
        # أما انتماء العملية للفترة فيحدّده عمود (period) لا التاريخ.
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def get_operation_datetime(self):
        """تاريخ ووقت العملية الحقيقيان (الفترة تُحدَّد بعمود period لا بالتاريخ)"""
        return f"{self.get_smart_default_date()} {datetime.datetime.now().strftime('%H:%M:%S')}"

    def stamp_period(self, inv_data, date_value=None):
        """يختم الحركة بالفترة المحاسبية التي تنتمي إليها.

        الأساس: الفترة المعروضة وقت التسجيل. ولو كان تاريخ الحركة يقع داخل
        فترة معروضة أخرى (كتعديل حركة قديمة) تُترك فترتها كما هي.
        """
        if not inv_data.get("period"):
            inv_data["period"] = self.current_display_month
        return inv_data

    def refresh_live_date_fields(self):
        """يحدّث خانات التاريخ المعروضة عند تغيّر تاريخ الجهاز والبرنامج مفتوح.

        بدون هذا كانت الخانات تحتفظ بتاريخ لحظة فتح الشاشة، فيبقى النظام
        على تاريخ الأمس حتى يُعاد تشغيله.
        """
        try:
            expected = self.get_smart_default_date()
            last = getattr(self, "_last_live_date", None)
            if last != expected:
                for attr in ("date_entry", "sale_date", "in_date", "op_date",
                             "cast_date", "polish_date", "pbuff_date"):
                    widget = getattr(self, attr, None)
                    if widget is None:
                        continue
                    try:
                        current = widget.get().strip()
                        # لا نلمس تاريخاً عدّله المستخدم بنفسه
                        if current in ("", last):
                            widget.delete(0, "end")
                            widget.insert(0, expected)
                    except Exception:
                        continue

                for stage in getattr(self, "dynamic_stage_widgets", {}).values():
                    widget = stage.get("date")
                    if widget is None:
                        continue
                    try:
                        current = widget.get().strip()
                        if current in ("", last):
                            widget.delete(0, "end")
                            widget.insert(0, expected)
                    except Exception:
                        continue

                self._last_live_date = expected
        except Exception as e:
            log_cloud_error("تعذّر تحديث التاريخ الحيّ", e)
        finally:
            self.after(30000, self.refresh_live_date_fields)   # كل ٣٠ ثانية

    def update_period_warning(self):
        """مؤشر واضح بجوار مختار الفترة عندما تكون الفترة المعروضة ليست الشهر الحالي.

        الهدف: ألا يُسجّل المستخدم حركات في شهر خطأ وهو لا ينتبه.
        """
        if not hasattr(self, 'lbl_period_warning'):
            return
        curr = datetime.datetime.now().strftime("%Y-%m")
        if self.current_display_month == curr:
            self.lbl_period_warning.configure(text="")
        else:
            self.lbl_period_warning.configure(
                text=f"⚠️ أنت تعمل في فترة سابقة ({self.current_display_month}) — الشهر الحالي {curr}")

    def watch_system_month(self):
        """يراقب تغيّر شهر النظام والبرنامج مفتوح (يعمل ليلاً عند نهاية الشهر).

        بدون هذا يبقى البرنامج مفتوحاً من ٣١ يوليو إلى ١ أغسطس وهو ما زال
        يسجّل في يوليو، لأن الفترة تُحسب مرة واحدة عند التشغيل فقط.
        """
        try:
            curr = datetime.datetime.now().strftime("%Y-%m")
            last = getattr(self, "_last_seen_system_month", None)
            if last is None:
                self._last_seen_system_month = curr
            elif curr != last:
                self._last_seen_system_month = curr
                if messagebox.askyesno(
                        "بداية شهر جديد",
                        f"بدأ شهر جديد ({curr}).\n\n"
                        f"هل تريد الانتقال للفترة الجديدة الآن؟\n"
                        f"(إن اخترت لا، ستبقى في فترة {self.current_display_month} "
                        f"وستُسجَّل حركاتك فيها)"):
                    self.current_display_month = curr
                    self.update_period_selector()
                    self.on_period_changed(curr)
        except Exception:
            pass
        finally:
            self.after(300000, self.watch_system_month)   # كل ٥ دقائق

    def create_sticky_total_tree(self, parent, columns, height=18, col_widths=None):
        """جدول بصف إجمالي ثابت أسفله لا يتحرّك مع التمرير.

        Treeview لا يدعم "تجميد صف" أصلياً، فالحل القياسي هو استخدام شجرتين:
        الأولى قابلة للتمرير لصفوف البيانات، والثانية أسفلها مباشرة (خارج
        منطقة التمرير) لصف الإجمالي فقط، بنفس الأعمدة والعرض بالضبط حتى
        تصطف الأرقام رأسياً مع الجدول العلوي.

        يرجع: (شجرة البيانات القابلة للتمرير، شجرة الإجمالي الثابتة)
        """
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True)

        # ترتيب الرصف مقصود: صف الإجمالي يُرصف **أولاً** من الأسفل، ثم يأخذ
        # جدول البيانات ما تبقّى. لو عُكس الترتيب لالتهم الجدول المساحة كلها
        # ودُفع صف الإجمالي خارج الشاشة فلا يظهر إطلاقاً.
        # ارتفاع ثابت ومنع الانتشار: يضمن ظهور الشريط دائماً، فقد كان ينكمش
        # إلى صفر عندما يطلب جدول البيانات ارتفاعاً أكبر من المتاح
        total_holder = ttk.Frame(wrapper, height=40)
        total_holder.pack(side="bottom", fill="x")
        total_holder.pack_propagate(False)
        ttk.Separator(wrapper, orient="horizontal").pack(side="bottom", fill="x", pady=(2, 0))

        body_frame = ttk.Frame(wrapper)
        body_frame.pack(side="top", fill="both", expand=True)

        data_tree = ttk.Treeview(body_frame, columns=columns, show="headings", height=height)
        for col in columns:
            data_tree.heading(col, text=col)
            data_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center", stretch=False)

        vsb = ttk.Scrollbar(body_frame, orient="vertical", command=data_tree.yview)
        data_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        data_tree.pack(side="left", fill="both", expand=True)

        # هامش يعادل عرض شريط التمرير الرأسي، حتى تصطف أعمدة الشجرتين رأسياً
        # رغم غياب الشريط في شجرة الإجمالي
        ttk.Frame(total_holder, width=17).pack(side="right", fill="y")

        # show="" يُخفي شريط العناوين الفارغ فوق صف الإجمالي، فيظهر الصف
        # ملاصقاً للجدول تماماً بلا فراغ يفصله عنه
        total_tree = ttk.Treeview(total_holder, columns=columns, show="", height=1,
                                  style="Totals.Treeview")
        for col in columns:
            total_tree.column(col, width=(col_widths or {}).get(col, 110), anchor="center", stretch=False)
        # شريط رصاصي غامق بأرقام بيضاء ليتميّز بوضوح عن صفوف الجدول
        self.ensure_totals_bar_style()
        total_tree.tag_configure("total_tag", foreground="#000000", font=("Cairo", 14, "bold"))
        total_tree.pack(side="left", fill="x", expand=True)

        # ربط الشجرتين ليُعاد ضبط عرض أعمدة الإجمالي كلما تغيّر عرض الجدول
        data_tree._total_tree = total_tree
        data_tree.bind("<Configure>",
                       lambda e, d=data_tree, t=total_tree: self.sync_total_tree_columns(d, t),
                       add="+")
        return data_tree, total_tree

    def ensure_totals_bar_style(self):
        """نمط شريط الإجمالي: خلفية رصاصية غامقة ثابتة في الوضعين الفاتح والداكن"""
        if getattr(self, "_totals_style_ready", False):
            return
        try:
            style = ttk.Style()
            # رصاصي فاتح بنص أسود عريض — أوضح للقراءة من الغامق
            style.configure("Totals.Treeview",
                            background="#c4c9ce", fieldbackground="#c4c9ce",
                            foreground="#000000", rowheight=34, borderwidth=0)
            # الصف يبقى بلونه حتى عند التحديد، فلا يتغيّر شكل الشريط بالنقر
            style.map("Totals.Treeview",
                      background=[("selected", "#c4c9ce")],
                      foreground=[("selected", "#000000")])
            self._totals_style_ready = True
        except Exception:
            pass

    def sync_total_tree_columns(self, data_tree, total_tree):
        """يطابق عرض أعمدة صف الإجمالي مع أعمدة جدول البيانات.

        ضروري لأن عرض أعمدة الجدول يُضبط لاحقاً حسب المحتوى، فلولا هذه
        المطابقة لظهر صف الإجمالي بأرقام مزاحة عن أعمدتها.
        """
        if data_tree is None or total_tree is None:
            return
        try:
            for col in data_tree["columns"]:
                total_tree.column(col, width=data_tree.column(col, "width"), stretch=False)
        except Exception:
            pass

    def view_treeview_fullscreen(self, tree, title, name_tree=None):
        """يقرأ محتوى Treeview ظاهر حالياً في الشاشة (بيانات + إجمالي إن وُجد)
        ويعرضه بملء الشاشة بنفس الآلية العامة، بدل إعادة حساب البيانات من
        الصفر — فما تراه بالضبط هو ما يُعرض بملء الشاشة، بلا احتمال تعارض."""
        if tree is None:
            messagebox.showinfo("تنبيه", "لا يوجد جدول لعرضه حالياً.")
            return

        columns = list(tree["columns"])
        children = tree.get_children()
        if not children:
            messagebox.showinfo("تنبيه", "الجدول فارغ حالياً — لا يوجد ما يُعرض.")
            return

        # صف الإجمالي هو آخر صف موسوم total_tag إن وُجد، وباقي الصفوف بيانات
        rows, tags, totals_values = [], [], None
        for iid in children:
            vals = tree.item(iid, "values")
            item_tags = tree.item(iid, "tags") or ()
            if "total_tag" in item_tags:
                totals_values = tuple(vals)
            else:
                rows.append(tuple(vals))
                tags.append("red_tag" if "red_tag" in item_tags else None)

        # الجداول ذات الإجمالي الثابت تحفظه على الجدول نفسه
        if totals_values is None:
            totals_values = getattr(tree, "_totals_values", None)

        # عمود الاسم (إن وُجد كجدول منفصل) يُدمَج كعمود أول في العرض الكامل
        if name_tree is not None:
            name_children = name_tree.get_children()
            merged_rows = []
            for i, r in enumerate(rows):
                nm = name_tree.item(name_children[i], "values")[0] if i < len(name_children) else ""
                merged_rows.append((nm,) + r)
            rows = merged_rows
            columns = ["الاسم"] + columns
            if totals_values is not None:
                totals_values = ("الإجمالي",) + totals_values[1:]

        self.open_fullscreen_table_view(title, tuple(columns), rows,
                                        totals_values=totals_values, row_tags=tags)

    def open_fullscreen_table_view(self, title, columns, rows, totals_values=None,
                                   col_widths=None, row_tags=None):
        """يفتح نافذة ملء الشاشة لعرض جدول كامل.

        صف الإجمالي يُدرَج **داخل الجدول نفسه** كآخر صف بعد البيانات، بترتيبه
        المحاسبي الطبيعي. استُبدل بذلك الشريط المنفصل أسفل الجدول لأنه كان
        ينكمش ويختفي حسب مساحة النافذة — والصف داخل الجدول لا يمكن أن يختفي
        ولا أن تنزاح أعمدته. وعند الفتح يُمرَّر الجدول إليه تلقائياً ليظهر فوراً.

        rows: قائمة صفوف، كل صف Tuple بنفس عدد الأعمدة
        totals_values: صف الإجمالي (Tuple)، أو None ليُحسب تلقائياً
        row_tags: قائمة موازية لـ rows فيها وسم اللون لكل صف (أو None)
        """
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.transient(self)
        win.grab_set()
        win.focus_force()

        # حجم يناسب الشاشة مع هامش، ثم تكبير على ويندوز إن أمكن
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        win.geometry(f"{max(900, sw - 80)}x{max(600, sh - 120)}+40+30")
        try:
            win.state("zoomed")
        except Exception:
            pass

        ctk.CTkLabel(win, text=title, font=("Cairo", 20, "bold"),
                     text_color="#d4af37").pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"عدد الصفوف: {len(rows)}   •   صف الإجمالي في آخر الجدول",
                     font=("Cairo", 12), text_color="#8b8f95").pack(pady=(0, 8))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)

        data_tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        for col in columns:
            data_tree.heading(col, text=self.wrap_header(col))
            data_tree.column(col, width=(col_widths or {}).get(col, 110),
                             anchor="center", stretch=False)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=data_tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=data_tree.xview)
        data_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right", fill="y")
        data_tree.pack(side="left", fill="both", expand=True)

        # صف الإجمالي بارز: خلفية رصاصية غامقة وخط أبيض عريض، ليتميّز عن البيانات
        data_tree.tag_configure("total_tag", foreground="#000000", background="#c4c9ce",
                                font=("Cairo", 14, "bold"))
        data_tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))

        if totals_values is None:
            totals_values = self.compute_totals_row(columns, rows)

        for i, row in enumerate(rows):
            tag = (row_tags[i],) if row_tags and row_tags[i] else ()
            data_tree.insert("", "end", values=row, tags=tag)

        # صف الإجمالي في **آخر** الجدول، بترتيبه المحاسبي الطبيعي بعد البيانات
        if totals_values is not None:
            data_tree.insert("", "end", values=totals_values, tags=("total_tag",))

        def fit_and_reveal():
            self.fit_columns_to_content(data_tree, None, min_width=54, max_width=220)
            # ارتفاع الجدول يُضبط على عدد صفوفه ما دام يسع الشاشة، فيظهر صف
            # الإجمالي مباشرةً بلا تمرير؛ ولو زادت الصفوف عن سعة الشاشة نُمرّر
            # إليه تلقائياً ليكون أول ما تراه عند الفتح
            try:
                children = data_tree.get_children()
                if children:
                    data_tree.see(children[-1])
            except Exception:
                pass

        win.after(120, fit_and_reveal)
        win.after(420, fit_and_reveal)   # إعادة بعد اكتمال التكبير

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=40,
                      command=win.destroy).pack(pady=12)

    @staticmethod
    def compute_totals_row(columns, rows):
        """يحسب صف إجمالي من الصفوف المعروضة عندما لا يوفّره الجدول المصدر.

        يجمع كل عمود قابل للتحويل لرقم، ويضع (-) في الأعمدة النصية،
        والكلمة (الإجمالي) في أول عمود.
        """
        if not rows:
            return None

        totals = []
        for idx, _col in enumerate(columns):
            if idx == 0:
                totals.append("الإجمالي")
                continue
            acc, numeric = 0.0, False
            for row in rows:
                try:
                    raw = str(row[idx]).replace(",", "").replace("\u200e", "").strip()
                except (IndexError, TypeError):
                    continue
                if raw in ("", "-"):
                    continue
                try:
                    acc += float(raw)
                    numeric = True
                except ValueError:
                    continue      # عمود نصي: لا يُجمع
            totals.append(f"{round(acc, 2):.2f}" if numeric else "-")
        return tuple(totals)

    def create_two_pane_ledger_tree(self, parent, main_cols, height=11,
                                    name_col_width=110, main_col_widths=None):
        """جدولان متلاصقان: عمود (الاسم) برتقالي بالكامل + الجدول الرئيسي بجانبه،
        يتحرّكان معاً عند التمرير أو عجلة الفأرة.

        السبب التقني: Treeview يُلوَّن على مستوى الصف كاملاً لا الخلية المفردة،
        فلا توجد طريقة لجعل عمود واحد برتقالياً بينما بقية أعمدة نفس الصف
        سوداء/حمراء حسب حالتها — حاولت ذلك بوسوم الصف فتعارضت الألوان.
        الحل: عمود الاسم في جدول منفصل ملاصق، بلا تعارض تلوين إطلاقاً.

        يرجع: (الجدول الرئيسي, جدول الاسم)
        """
        row = ttk.Frame(parent)
        row.pack(fill="both", expand=True)

        name_frame = ttk.Frame(row)
        name_frame.pack(side="right", fill="y")
        name_tree = ttk.Treeview(name_frame, columns=("الاسم",), show="headings", height=height)
        name_tree.heading("الاسم", text="الاسم")
        name_tree.column("الاسم", width=name_col_width, anchor="center", stretch=False)
        name_tree.tag_configure("orange_name", foreground="#e67e22", font=("Cairo", 13, "bold"))
        name_tree.pack(fill="y")

        main_frame = ttk.Frame(row)
        main_frame.pack(side="right", fill="both", expand=True)
        main_tree = self.create_standard_treeview(main_frame, main_cols, height=height)
        if main_col_widths:
            for col, w in main_col_widths.items():
                main_tree.column(col, width=w, anchor="center", stretch=False)

        # تزامن التمرير في الاتجاهين: تحريك أي من الجدولين يحرّك الآخر بنفس القدر
        orig_cmd = main_tree.cget("yscrollcommand")

        def on_main_scroll(first, last):
            if orig_cmd:
                self.tk.call(orig_cmd, first, last)
            name_tree.yview_moveto(first)

        main_tree.configure(yscrollcommand=on_main_scroll)
        name_tree.bind("<MouseWheel>",
                       lambda e: (main_tree.yview_scroll(int(-1 * (e.delta / 120)), "units"), "break"))
        name_tree.bind("<Button-4>", lambda e: (main_tree.yview_scroll(-1, "units"), "break"))
        name_tree.bind("<Button-5>", lambda e: (main_tree.yview_scroll(1, "units"), "break"))

        return main_tree, name_tree

    # أسماء الأعمدة المعدّلة من المستخدم — تُحفظ لكل جدول على حدة
    COLUMN_LABEL_KEY = "col_labels"

    def get_column_label(self, table_key, column_id):
        """الاسم المعروض للعمود: المعدَّل من المستخدم إن وُجد، وإلا الاسم الأصلي"""
        try:
            import json as _json
            saved = _json.loads(self.get_setting(f"{self.COLUMN_LABEL_KEY}_{table_key}", "") or "{}")
            return saved.get(column_id, column_id)
        except Exception:
            return column_id

    def set_column_label(self, table_key, column_id, new_label):
        try:
            import json as _json
            key = f"{self.COLUMN_LABEL_KEY}_{table_key}"
            saved = _json.loads(self.get_setting(key, "") or "{}")
            if new_label and new_label != column_id:
                saved[column_id] = new_label
            else:
                saved.pop(column_id, None)   # إرجاع الاسم الأصلي
            self.set_setting(key, _json.dumps(saved, ensure_ascii=False))
        except Exception as e:
            log_cloud_error("تعذّر حفظ اسم العمود", e)

    @staticmethod
    def wrap_header(text, max_len=9):
        """عنوان العمود كما هو — بلا توزيع على سطرين.

        السبب: رؤوس أعمدة ttk.Treeview تعرض **السطر الأول فقط** من النص،
        فتوزيع العنوان على سطرين كان يقصّه فيظهر «خياس» بدل «خياس المركب».
        العرض يتكفّل به fit_columns_to_content الذي يقيس العنوان كاملاً.
        """
        return str(text or "")

    @staticmethod
    def _wrap_header_unused(text, max_len=9):
        text = str(text or "")
        if len(text) <= max_len:
            return text
        words = text.split()
        if len(words) == 1:
            return text
        # نقسم الكلمات على سطرين متوازنين قدر الإمكان
        best, best_diff = 1, None
        for i in range(1, len(words)):
            a = len(" ".join(words[:i]))
            b = len(" ".join(words[i:]))
            diff = abs(a - b)
            if best_diff is None or diff < best_diff:
                best, best_diff = i, diff
        return " ".join(words[:best]) + "\n" + " ".join(words[best:])

    def enable_column_rename(self, tree, table_key, on_renamed=None):
        """يسمح بتعديل اسم أي عمود بالضغط على رأسه، ويحفظ الاسم الجديد"""
        def on_header_click(event):
            if tree.identify_region(event.x, event.y) != "heading":
                return
            try:
                cols = list(tree["columns"])
                idx = int(tree.identify_column(event.x).replace("#", "")) - 1
                if not (0 <= idx < len(cols)):
                    return
                col_id = cols[idx]
            except (ValueError, IndexError):
                return

            current = self.get_column_label(table_key, col_id)
            dialog = ctk.CTkInputDialog(
                title="تعديل اسم العمود",
                text=f"الاسم الجديد للعمود «{current}»\n(اتركه فارغاً لإرجاع الاسم الأصلي: {col_id})")
            new_name = dialog.get_input()
            if new_name is None:
                return

            self.set_column_label(table_key, col_id, new_name.strip())
            label = self.get_column_label(table_key, col_id)
            try:
                tree.heading(col_id, text=self.wrap_header(label))
            except Exception:
                pass
            if on_renamed:
                try:
                    on_renamed()
                except Exception:
                    pass

        # علم على الأداة نفسها لا على النافذة: كل جدول جديد يُربط مرة واحدة،
        # فلا تتراكم الروابط على الجدول نفسه ولا يُحرم الجدول الجديد من الربط
        if not getattr(tree, "_rename_bound", False):
            tree.bind("<Button-1>", on_header_click, add="+")
            tree._rename_bound = True

    def apply_column_labels(self, tree, table_key):
        """يطبّق الأسماء المعدّلة والعناوين ذات السطرين على كل أعمدة الجدول"""
        try:
            for col_id in list(tree["columns"]):
                tree.heading(col_id, text=self.wrap_header(self.get_column_label(table_key, col_id)))
        except Exception:
            pass

    def expected_table_width(self):
        """العرض المتوقّع للجدول قبل ظهوره على الشاشة.

        يُقدَّر من عرض النافذة بعد خصم الشريط الجانبي والهوامش، فتُضبط
        الأعمدة صحيحةً من أول مرة بلا انتظار الظهور.
        """
        try:
            w = self.winfo_width()
            if w <= 1:
                w = self.winfo_screenwidth()
        except Exception:
            w = 1366
        try:
            w -= self.sidebar_width()
        except Exception:
            w -= 300
        return max(600, w - 60)

    def fit_columns_to_content(self, tree, table_key=None, min_width=46, max_width=200, padding=16):
        """يضبط عرض كل عمود على أعرض محتوى فيه فعلياً — لا عرض ثابت ولا تمدّد.

        المشكلة التي يحلّها: التوزيع بالنِسَب كان يمنح كل عمود حصة متساوية
        تقريباً، فتتمدّد أعمدة الأرقام القصيرة (كرقم الصف) وتُزاح بقية الأعمدة
        خارج الشاشة فتحتاج سحباً أفقياً. القياس الفعلي للنص يجعل كل عمود
        بعرض محتواه بالضبط، فتظهر كل الأعمدة معاً.
        """
        if tree is None:
            return
        try:
            import tkinter.font as tkfont
            cols = list(tree["columns"])
            if not cols:
                return

            body_font = tkfont.Font(family="Cairo", size=11)
            head_font = tkfont.Font(family="Cairo", size=11, weight="bold")

            # قياس **عيّنة** من الصفوف لا كلها:
            # القياس السابق كان يستدعي measure() لكل خلية — مع ٥٠٠ صف و١٦
            # عموداً = ٨٠٠٠ استدعاء في كل تحديث، وهو السبب الأكبر لبطء فتح
            # الشاشات. العيّنة تعطي نفس العرض عملياً لأن الأرقام متقاربة الطول.
            all_children = tree.get_children()
            if len(all_children) > FIT_SAMPLE_ROWS:
                step = max(1, len(all_children) // FIT_SAMPLE_ROWS)
                children = all_children[::step][:FIT_SAMPLE_ROWS]
                # آخر الصفوف مهم: صف الإجمالي عادةً أطول الأرقام
                children = list(children) + list(all_children[-3:])
            else:
                children = all_children
            widths = []
            for i, col_id in enumerate(cols):
                label = self.get_column_label(table_key, col_id) if table_key else col_id
                # العنوان يُقاس كاملاً: هو سطر واحد في رأس العمود
                header_w = head_font.measure(str(label)) + 10

                content_w = 0
                for iid in children:
                    try:
                        text = str(tree.item(iid, "values")[i])
                    except (IndexError, TypeError):
                        continue
                    if text:
                        content_w = max(content_w, body_font.measure(text))

                # العنوان لا يُقصّ أبداً: الحد الأقصى يقيّد المحتوى لا الرأس،
                # وإلا ظهرت كلمة واحدة من اسم العمود
                width = max(min_width, header_w, min(max_width, content_w + padding))
                widths.append(width)

            # توزيع المساحة الفائضة على الأعمدة بالتناسب مع عرضها المطلوب،
            # فيمتلئ الجدول كاملاً بلا فراغ على اليسار وبلا انكماش الأعمدة.
            # لو ضاق الجدول عن المجموع، نُبقي العرض المحسوب ويظهر شريط أفقي
            # بدل قصّ الأعمدة — فلا يختفي عمود أبداً.
            # العرض المتاح: من الجدول إن كان ظاهراً، وإلا **يُقدَّر** من عرض
            # النافذة. هذا هو جوهر إصلاح «اهتزاز» الشاشة عند الفتح:
            # كان الجدول يُبنى وهو مخفي (عرضه ١)، فيُؤجَّل الضبط إلى ما بعد
            # الظهور — فيرى المستخدم الأعمدة تقفز أمامه. التقدير المسبق يجعل
            # الأعمدة صحيحة **قبل** أول رسم، فتظهر الشاشة جاهزة دفعةً واحدة.
            avail = tree.winfo_width()
            if avail <= 1:
                avail = self.expected_table_width()

            total = sum(widths)
            extra = avail - total - 4          # هامش يمنع شريطاً أفقياً زائداً
            if extra > 0 and total > 0:
                for i in range(len(widths)):
                    widths[i] += int(extra * (widths[i] / total))

            for col_id, width in zip(cols, widths):
                tree.column(col_id, width=width, minwidth=min_width, stretch=False)

            # صف الإجمالي الثابت (إن وُجد) يتبع نفس الأعرض فتصطف الأرقام معه
            self.sync_total_tree_columns(tree, getattr(tree, "_total_tree", None))

            # الصفوف المتناوبة: تُطبَّق هنا لأن الجدول يكون قد امتلأ فعلاً
            self.style_tree_rows(tree)

            # يُعاد الضبط عند تغيير حجم النافذة، لكن **بتأجيل**: حدث Configure
            # يتكرّر عشرات المرات أثناء السحب، وإعادة الضبط مع كل حدث كانت
            # تُجمّد الواجهة. التأجيل ينفّذها مرة واحدة بعد استقرار الحجم.
            if not getattr(tree, "_fit_bound", False):
                def on_resize(_e, t=tree, k=table_key):
                    # تجاهل التغيّر الطفيف: أول ظهور للجدول يُطلق Configure
                    # بعرضه الحقيقي، وإعادة الضبط حينها هي ما يُرى كاهتزاز.
                    new_w = t.winfo_width()
                    last = getattr(t, "_last_fit_w", 0)
                    if abs(new_w - last) < 40:
                        return
                    t._last_fit_w = new_w

                    job = getattr(t, "_fit_job", None)
                    if job:
                        try:
                            t.after_cancel(job)
                        except Exception:
                            pass
                    t._fit_job = t.after(200, lambda: self.fit_columns_to_content(
                        t, k, min_width, max_width, padding))

                tree.bind("<Configure>", on_resize, add="+")
                tree._fit_bound = True
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول

    def autofit_tree_columns(self, tree, min_width=70, priority_wide=None):
        """يوزّع عرض الأعمدة على كامل عرض الجدول تلقائياً.

        المشكلة التي يحلّها: الأعمدة كانت بعرض ثابت، فتتكدّس في نصف الجدول
        ويبقى النصف الآخر فارغاً على الشاشات العريضة. الآن تُوزَّع المساحة
        كاملة بلا تدخّل، مع إعطاء أعمدة النصوص (كالبيان والاسم) وزناً أكبر
        لأنها تحتاج مساحة أكثر من الأعمدة الرقمية.
        """
        if tree is None:
            return
        try:
            cols = list(tree["columns"])
            if not cols:
                return

            wide = set(priority_wide or ("البيان", "الاسم", "التاريخ", "رقم التشغيل"))
            weights = {c: (1.7 if c in wide else 1.0) for c in cols}
            total_weight = sum(weights.values())

            avail = tree.winfo_width()
            if avail <= 1:
                # الجدول لم يُرسم بعد: نعيد المحاولة بعد اكتمال التخطيط
                tree.after(120, lambda: self.autofit_tree_columns(tree, min_width, priority_wide))
                return

            avail -= 4   # هامش بسيط يمنع ظهور شريط تمرير أفقي بلا داعٍ
            for c in cols:
                w = int(avail * (weights[c] / total_weight))
                tree.column(c, width=max(min_width, w), minwidth=min_width, stretch=True)
        except Exception:
            pass   # التنسيق تحسين بصري: فشله يجب ألا يمنع عرض الجدول

    # ══════════════════════════════════════════════════════════════════
    #  نظام التصميم المركزي
    #
    #  كل الجداول في النظام تُنشأ من create_standard_treeview، وكل الخطوط
    #  تُقاس من هنا — فتغيير هذه القيم يغيّر مظهر الشاشات الأربع عشرة معاً
    #  بلا لمس أي منطق محاسبي.
    # ══════════════════════════════════════════════════════════════════
    DESIGN = {
        "light": {
            "bg":          "#ffffff",
            "row_alt":     "#f4f7fb",
            "text":        "#1b2a3a",
            "head_bg":     "#1f4e79",
            "head_text":   "#ffffff",
            "sel_bg":      "#cfe4fb",
            "sel_text":    "#0d2a45",
            "grid":        "#d8e0ea",
        },
        "dark": {
            "bg":          "#1b2027",
            "row_alt":     "#222933",
            "text":        "#e8eef5",
            "head_bg":     "#16344f",
            "head_text":   "#ffffff",
            "sel_bg":      "#2c4a68",
            "sel_text":    "#ffffff",
            "grid":        "#2c343f",
        },
    }

    def design_metrics(self):
        """مقاييس تتناسب مع دقة شاشة المستخدم.

        الجداول والخطوط تكبر على الشاشات الكبيرة وتصغر على الصغيرة، فيبقى
        النظام مقروءاً ومتناسقاً على كل المقاسات بلا تدخّل من المستخدم.
        """
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        except Exception:
            sw, sh = 1366, 768

        if sw >= 2400:
            base, row_h, head = 15, 40, 15
        elif sw >= 1900:
            base, row_h, head = 14, 36, 14
        elif sw >= 1600:
            base, row_h, head = 13, 33, 13
        elif sw >= 1400:
            base, row_h, head = 12, 31, 12
        else:
            base, row_h, head = 11, 28, 11

        # الشاشات القصيرة تحتاج صفوفاً أقصر وإلا ظهر عدد قليل منها
        if sh <= 800:
            row_h = max(24, row_h - 4)

        return {"font": base, "row_h": row_h, "head": head,
                "pad_x": max(6, base - 4), "pad_y": max(3, base // 3)}

    def apply_design_system(self):
        """يطبّق التنسيق الموحّد على كل جداول النظام دفعةً واحدة"""
        try:
            m = self.design_metrics()
            mode = "dark" if ctk.get_appearance_mode() == "Dark" else "light"
            c = self.DESIGN[mode]
            self._design = dict(c, **m)

            style = ttk.Style()
            try:
                style.theme_use("clam")   # أكثر سمة تقبل التخصيص الكامل
            except Exception:
                pass

            style.configure(
                "Treeview",
                background=c["bg"], fieldbackground=c["bg"], foreground=c["text"],
                rowheight=m["row_h"], borderwidth=0, relief="flat",
                font=("Cairo", m["font"]))

            style.configure(
                "Treeview.Heading",
                background=c["head_bg"], foreground=c["head_text"],
                relief="flat", borderwidth=0, padding=(4, m["pad_y"] + 2),
                font=("Cairo", m["head"], "bold"))

            style.map("Treeview.Heading",
                      background=[("active", c["head_bg"])],
                      foreground=[("active", c["head_text"])])

            style.map("Treeview",
                      background=[("selected", c["sel_bg"])],
                      foreground=[("selected", c["sel_text"])])

            # شريط التمرير بنفس لغة الألوان
            style.configure("Vertical.TScrollbar", background=c["grid"],
                            troughcolor=c["bg"], borderwidth=0, arrowsize=14)
            style.configure("Horizontal.TScrollbar", background=c["grid"],
                            troughcolor=c["bg"], borderwidth=0, arrowsize=14)

            # شريط الإجمالي يتبع النظام أيضاً
            self._totals_style_ready = False
            self.ensure_totals_bar_style()
        except Exception as e:
            log_cloud_error("تعذّر تطبيق نظام التصميم", e)

    def style_tree_rows(self, tree):
        """صفوف متناوبة اللون: تسهّل تتبّع السطر الواحد عبر جدول عريض"""
        try:
            c = getattr(self, "_design", self.DESIGN["light"])
            tree.tag_configure("odd_row", background=c["bg"])
            tree.tag_configure("even_row", background=c["row_alt"])
            for i, iid in enumerate(tree.get_children()):
                tags = list(tree.item(iid, "tags") or ())
                # لا نلمس الصفوف ذات الوسوم الخاصة (الإجمالي، السالب…)
                if any(t in tags for t in ("total_tag", "red_tag", "orange_name")):
                    continue
                tags = [t for t in tags if t not in ("odd_row", "even_row")]
                tags.append("even_row" if i % 2 else "odd_row")
                tree.item(iid, tags=tuple(tags))
        except Exception:
            pass

    def reuse_or_create_tree(self, parent, columns, height=15, sticky_total=False):
        """يُعيد استخدام جدول الإطار إن كانت أعمدته نفسها، وإلا يبنيه من جديد.

        السبب: كانت كل عملية تحديث تُدمّر أدوات الجدول كلها وتُعيد بناءها —
        إنشاء Treeview وشريط تمرير وعشرات الإعدادات في كل مرة. هذا ما يظهر
        للمستخدم كأن الشاشة «تتكوّن» أمامه. إعادة الاستخدام تُبقي الأدوات
        وتكتفي بمسح الصفوف وإعادة ملئها — وهو أسرع بمراتب.

        يرجع: (الجدول، شجرة الإجمالي أو None، هل أُعيد استخدامه؟)
        """
        cached = getattr(parent, "_cached_tree", None)
        cached_cols = getattr(parent, "_cached_cols", None)

        if cached is not None and cached_cols == tuple(columns):
            try:
                if cached.winfo_exists():
                    cached.delete(*cached.get_children())
                    total = getattr(parent, "_cached_total_tree", None)
                    if total is not None and total.winfo_exists():
                        total.delete(*total.get_children())
                    else:
                        total = None
                    return cached, total, True
            except Exception:
                pass   # الجدول تالف لأي سبب: نبنيه من جديد

        for widget in parent.winfo_children():
            widget.destroy()

        if sticky_total:
            tree, total = self.create_sticky_total_tree(parent, columns, height=height)
        else:
            tree, total = self.create_standard_treeview(parent, columns, height=height), None

        parent._cached_tree = tree
        parent._cached_cols = tuple(columns)
        parent._cached_total_tree = total
        return tree, total, False

    def create_standard_treeview(self, parent, columns, height=15):
        # كل جداول النظام تمرّ من هنا، فالتنسيق الموحّد يصلها جميعاً
        if not getattr(self, "_design", None):
            self.apply_design_system()

        tree = ttk.Treeview(parent, columns=columns, show="headings", height=height)
        for col in columns:
            tree.heading(col, text=self.wrap_header(col))
            tree.column(col, anchor="center")

        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        return tree

    @staticmethod
    def row_sort_key(row_num):
        """مفتاح ترتيب تدريجي لأرقام الصفوف: رقمياً أولاً، ثم نصياً، والصفوف بدون ترقيم في النهاية"""
        s = str(row_num or "").strip()
        if not s:
            return (2, 0.0, "")
        try:
            return (0, float(s), "")
        except ValueError:
            return (1, 0.0, s)

    def collect_stage_ops_rows(self, madin_type, qabd_type):
        """يجمع حركات أي شاشة عمليات للشهر المعروض في صفوف (رقم الصف + الاسم)، مرتبة تصاعدياً برقم الصف.
        الخياس لكل صف = مدين - دائن (الصرف ناقص القبض)."""
        recs = [inv for inv in self.invoices.values()
                if inv.get("النوع") in (madin_type, qabd_type)
                and inv.get("settled_status") == "ACTIVE"
                and self.inv_in_period(inv, self.current_display_month)]
        recs.sort(key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)))

        grouped = {}
        for inv in recs:
            key = ((inv.get("row_number", "") or ""), inv["الاسم"])
            if key not in grouped:
                grouped[key] = {"ids": [], "مدين": 0.0, "دائن": 0.0, "dt": inv["التاريخ"], "البيان": "", "أشجار": 0.0}
            g = grouped[key]
            g["ids"].append(inv["رقم الفاتورة"])
            # الجمع (وليس الاستبدال) حتى لا تُهمل أي حركة مسجّلة فعلياً بنفس رقم الصف
            if inv["النوع"] == madin_type:
                g["مدين"] = round(g["مدين"] + inv["الوزن"], 2)
            else:
                g["دائن"] = round(g["دائن"] + inv["الوزن"], 2)
            note = (inv.get("البيان") or "").strip()
            if note and note not in g["البيان"]:
                g["البيان"] = note if not g["البيان"] else g["البيان"] + " | " + note
            trees = inv.get("trees_count", 0.0) or 0.0
            if trees > g["أشجار"]:
                g["أشجار"] = trees

        order = sorted(grouped.keys(), key=lambda k: (self.row_sort_key(k[0]), grouped[k]["dt"], k[1]))
        return [(k[0], k[1], grouped[k]) for k in order]

    def render_stage_ops_table(self, table_frame, madin_type, qabd_type, height=11,
                               with_trees=False, on_edit=None, totals_label=None,
                               section=None, show_name=False, on_detail=None, on_refresh=None):
        """محرك موحّد لجداول شاشات العمليات:
        (الصف / الاسم / مدين / دائن / الخياس [+ عدد الأشجار + خياس كل شجرة] / البيان)
        مع سطر إجماليات أسفل الجدول وشريط إجماليات ثابت تحته."""


        # عمود الاسم يظهر فقط حيث يكون له معنى (المصنعين/المركبين).
        # في باقي الأقسام الاسم هو اسم القسم نفسه فلا فائدة من تكراره في كل صف.
        name_col = ("الاسم",) if show_name else ()
        # هذه الأقسام عمليات صرف وقبض فعلية، فالتسمية المحاسبية الأوضح للمستخدم
        # هي (صرف/قبض) لا (مدين/دائن) — والمصنعون والمركبون لهم جدولهم المستقل
        if with_trees:
            cols = ("الصف",) + name_col + ("صرف", "قبض", "الخياس", "عدد الأشجار", "خياس كل شجرة", "البيان")
        else:
            cols = ("الصف",) + name_col + ("صرف", "قبض", "الخياس", "البيان")

        tree, total_tree, _reused = self.reuse_or_create_tree(
            table_frame, cols, height=height, sticky_total=True)
        tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 230 if c == "البيان" else 165 if c == "الاسم" else 120 if c == "الصف" else 110
            tree.column(c, width=w, anchor="center")

        color_negative = self.negative_color_enabled(section) if section else False

        # الإجمالي في شجرة ثابتة أسفل الجدول: يبقى أمام المستخدم أثناء التمرير
        # بدل الاضطرار للنزول لآخر الصفوف لرؤيته
        rows_map = {}
        tot_madin = tot_daen = tot_trees = 0.0
        for row_num, name, g in self.collect_stage_ops_rows(madin_type, qabd_type):
            khayas = round(g["مدين"] - g["دائن"], 2)
            tot_madin = round(tot_madin + g["مدين"], 2)
            tot_daen = round(tot_daen + g["دائن"], 2)
            tot_trees += g["أشجار"]
            row_label = row_num if row_num else "بدون ترقيم"
            # التلوين حسب إعداد القسم نفسه: الأحمر فقط لو كان الخياس سالباً
            # (أي أن القبض أكبر من الصرف) والزر مفعّل في هذا القسم.
            tags = ("red_tag",) if (color_negative and khayas < 0) else ()
            vals = [row_label] + ([name] if show_name else []) + [
                    f"{g['مدين']:.2f}" if g["مدين"] else "-",
                    f"{g['دائن']:.2f}" if g["دائن"] else "-",
                    f"{khayas:.2f}"]
            if with_trees:
                trees = g["أشجار"]
                vals += [f"{trees:g}" if trees else "-",
                         f"{round(khayas / trees, 2):.2f}" if trees > 0 else "-"]
            vals.append(g["البيان"])
            item_id = tree.insert("", "end", values=tuple(vals), tags=tags)
            rows_map[item_id] = g["ids"]

        tot_khayas = round(tot_madin - tot_daen, 2)
        if rows_map:
            tvals = ["إجمالي الشهر"] + (["-"] if show_name else []) + [
                     f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{tot_khayas:.2f}"]
            if with_trees:
                tvals += [f"{tot_trees:g}" if tot_trees else "-",
                          f"{round(tot_khayas / tot_trees, 2):.2f}" if tot_trees > 0 else "-"]
            tvals.append("-")
            # الإجمالي في الشريط الثابت **وداخل الجدول** معاً: الشريط يبقى أمام
            # المستخدم بلا تمرير، والصف داخل الجدول ضمانة لا يمكن أن تختفي
            total_tree.insert("", "end", values=tuple(tvals), tags=("total_tag",))
            tree.insert("", "end", values=tuple(tvals), tags=("total_tag",))
            tree._totals_values = tuple(tvals)
            tree._total_tree = total_tree

        if totals_label is not None:
            txt = f"الإجماليات — صرف: {tot_madin:.2f}  |  قبض: {tot_daen:.2f}  |  الخياس: {tot_khayas:.2f} جم"
            if with_trees:
                per_tree = round(tot_khayas / tot_trees, 2) if tot_trees > 0 else 0.0
                txt += f"  |  عدد الأشجار: {tot_trees:g}  |  خياس كل شجرة: {per_tree:.2f}"
            totals_label.configure(text=txt)

        # الضغط المزدوج يعرض تفاصيل العملية. التعديل يبقى متاحاً من زره المخصّص،
        # حتى لا يفتح المستخدم نافذة تعديل بالخطأ وهو يريد الاطّلاع فقط.
        if on_detail:
            tree.bind("<Double-1>", lambda e: on_detail())
        elif on_edit:
            tree.bind("<Double-1>", lambda e: on_edit())

        # عناوين بسطرين + عرض محكوم بالمحتوى، فتظهر كل الأعمدة بلا سحب أفقي
        # الانتقال لآخر صف: نريد أن نرى أين وصلنا، لا أول الصفوف
        try:
            rows_now = tree.get_children()
            if rows_now:
                tree.see(rows_now[-1])
        except Exception:
            pass

        table_key = f"stage_{section or madin_type}"
        self.apply_column_labels(tree, table_key)
        self.fit_columns_to_content(tree, table_key, min_width=44, max_width=170)
        # تعديل اسم أي عمود بالضغط على رأسه (يُحفظ ويُطبَّق في كل مرة)
        self.enable_column_rename(tree, table_key, on_renamed=on_refresh)
        return tree, rows_map

    def show_selected_stage_details(self, tree, rows_map, title):
        """يفتح تفاصيل الصف المحدد في أي جدول من جداول الأقسام"""
        if not tree:
            return
        sel = tree.selection()
        if not sel:
            return
        ids = (rows_map or {}).get(sel[0])
        if ids:
            self.show_stage_row_details(ids, title)

    def show_stage_row_details(self, ids, title):
        """نافذة عرض تفاصيل حركات الصف: التاريخ والوقت والنوع والوزن والبيان.

        للاطّلاع فقط — لا تعديل هنا، فالتعديل له زره المخصّص أعلى الجدول.
        """
        invs = [self.invoices[i] for i in ids if i in self.invoices]
        if not invs:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.")
            return
        invs.sort(key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)))

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("760x480")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ref = invs[0]
        ctk.CTkLabel(win, text=f"📋 تفاصيل الصف ({ref.get('row_number') or 'بدون ترقيم'})",
                     font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"{ref.get('الاسم', '')}   |   عدد الحركات: {len(invs)}",
                     font=("Cairo", 12), text_color="#8b8f95").pack(pady=(0, 10))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=16, pady=6)

        cols = ("رقم الحركة", "التاريخ", "الوقت", "النوع", "الوزن", "عدد الأشجار", "البيان")
        tree = self.create_standard_treeview(frame, cols, height=11)
        tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        for c in cols:
            tree.column(c, width=180 if c == "البيان" else 130 if c == "النوع" else 100, anchor="center")

        total_w = 0.0
        for inv in invs:
            dt = str(inv.get("التاريخ", ""))
            total_w = round(total_w + inv.get("الوزن", 0.0), 2)
            tree.insert("", "end", values=(
                inv.get("رقم الفاتورة", "-"),
                dt[:10] or "-",
                dt[11:19] or "-",
                inv.get("النوع", "-"),
                f"{inv.get('الوزن', 0.0):.2f}",
                f"{inv.get('trees_count', 0) or 0:g}" if inv.get("trees_count") else "-",
                inv.get("البيان", "") or "-",
            ))

        tree.insert("", "end", values=("الإجمالي", "-", "-", "-", f"{total_w:.2f}", "-", "-"),
                    tags=("total_tag",))

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=38,
                      command=win.destroy).pack(pady=12)

    def open_stage_op_edit_dialog(self, ids, madin_type, qabd_type, title, with_trees=False, status_text=""):
        """نافذة تعديل موحّدة لأي حركة في شاشات العمليات (صرف/قبض/عدد الأشجار/البيان)"""
        if not self.check_edit_permission():
            return
        invs = [self.invoices[i] for i in ids if i in self.invoices]
        if not invs:
            messagebox.showwarning("تنبيه", "الحركة المحددة لم تعد موجودة. حدّث الشاشة وحاول مجدداً.")
            return
        ref_dt = invs[0]["التاريخ"]
        ref_name = invs[0]["الاسم"]
        ref_row = invs[0].get("row_number", "") or ""
        sarf_inv = next((i for i in invs if i["النوع"] == madin_type), None)
        qabd_inv = next((i for i in invs if i["النوع"] == qabd_type), None)
        base_inv = sarf_inv or qabd_inv
        common_note = (base_inv.get("البيان") or "") if base_inv else ""
        cur_trees = max([(i.get("trees_count", 0.0) or 0.0) for i in invs] or [0.0])

        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("540x610" if with_trees else "540x545")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"تعديل حركة الصف ({ref_row or 'بدون ترقيم'}) — {ref_name}",
                     font=("Cairo", 17, "bold"), text_color="#d4af37").pack(pady=10)

        frm = ctk.CTkFrame(win)
        frm.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(frm, text="الصرف (مدين):", font=("Cairo", 15, "bold")).grid(row=0, column=1, padx=10, pady=8)
        ent_sarf = ctk.CTkEntry(frm, justify="center", width=130)
        ent_sarf.insert(0, f"{sarf_inv['الوزن']:g}" if sarf_inv else "0")
        ent_sarf.grid(row=0, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="القبض (دائن):", font=("Cairo", 15, "bold")).grid(row=1, column=1, padx=10, pady=8)
        ent_qabd = ctk.CTkEntry(frm, justify="center", width=130)
        ent_qabd.insert(0, f"{qabd_inv['الوزن']:g}" if qabd_inv else "0")
        ent_qabd.grid(row=1, column=0, padx=10, pady=8)

        ent_trees = None
        if with_trees:
            ctk.CTkLabel(frm, text="عدد الأشجار:", font=("Cairo", 15, "bold")).grid(row=2, column=1, padx=10, pady=8)
            ent_trees = ctk.CTkEntry(frm, justify="center", width=130)
            ent_trees.insert(0, f"{cur_trees:g}" if cur_trees else "")
            ent_trees.grid(row=2, column=0, padx=10, pady=8)

        # حقول تعريف الحركة: قابلة للتعديل لتصحيح أي خطأ في الترقيم أو التاريخ
        ref_set = (base_inv.get("set_number", "") or "") if base_inv else ""

        ctk.CTkLabel(frm, text="رقم الصف:", font=("Cairo", 15, "bold")).grid(row=3, column=1, padx=10, pady=8)
        ent_row_no = ctk.CTkEntry(frm, justify="center", width=130)
        ent_row_no.insert(0, ref_row)
        ent_row_no.grid(row=3, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="رقم التشغيل:", font=("Cairo", 15, "bold")).grid(row=4, column=1, padx=10, pady=8)
        ent_set_no = ctk.CTkEntry(frm, justify="center", width=130)
        ent_set_no.insert(0, ref_set)
        ent_set_no.grid(row=4, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="التاريخ:", font=("Cairo", 15, "bold")).grid(row=5, column=1, padx=10, pady=8)
        ent_date = ctk.CTkEntry(frm, justify="center", width=130)
        ent_date.insert(0, str(ref_dt)[:10])
        ent_date.grid(row=5, column=0, padx=10, pady=8)

        ctk.CTkLabel(win, text="البيان:", font=("Cairo", 15, "bold")).pack(pady=(8, 0))
        ent_note = ctk.CTkEntry(win, justify="right", width=380)
        ent_note.insert(0, common_note)
        ent_note.pack(pady=5)

        def save_edit():
            try:
                new_sarf = round(float(ent_sarf.get().strip() or 0), 2)
                new_qabd = round(float(ent_qabd.get().strip() or 0), 2)
                new_trees = round(float(ent_trees.get().strip() or 0), 2) if ent_trees is not None else cur_trees
            except ValueError:
                messagebox.showerror("خطأ", "الرجاء إدخال أرقام صحيحة.", parent=win)
                return
            if new_sarf < 0 or new_qabd < 0 or new_trees < 0:
                messagebox.showerror("خطأ", "لا يمكن إدخال قيم بالسالب.", parent=win)
                return
            if new_sarf <= 0 and new_qabd <= 0:
                if not messagebox.askyesno("تأكيد", "الصرف والقبض كلاهما صفر — سيتم حذف هذه الحركة بالكامل.\nهل تريد المتابعة؟", parent=win):
                    return
            new_note = ent_note.get().strip()
            new_row_no = ent_row_no.get().strip()
            new_set_no = ent_set_no.get().strip()

            new_date = ent_date.get().strip()
            if len(new_date) < 10 or new_date[4] != "-":
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة YYYY-MM-DD.", parent=win)
                return
            # نُبقي وقت الحركة كما هو ما دام اليوم لم يتغيّر، فلا يتبدّل ترتيبها
            # المحاسبي بلا داعٍ داخل اليوم نفسه
            old_time = str(ref_dt)[11:] or datetime.datetime.now().strftime("%H:%M:%S")
            new_dt = f"{new_date} {old_time}"

            any_blocked = False

            def upsert(existing, value, op_type):
                nonlocal any_blocked
                if value > 0:
                    if existing:
                        existing["الوزن"] = value
                        existing["البيان"] = new_note
                        existing["trees_count"] = new_trees
                        existing["row_number"] = new_row_no
                        existing["set_number"] = new_set_no
                        existing["التاريخ"] = new_dt
                        if not self.save_invoice_to_db(existing["رقم الفاتورة"], existing):
                            any_blocked = True
                    else:
                        self.invoice_counter += 1
                        inv_data = {"رقم الفاتورة": self.invoice_counter, "التاريخ": new_dt, "الاسم": ref_name,
                                    "النوع": op_type, "الوزن": value, "البيان": new_note, "settled_status": "ACTIVE",
                                    "trees_count": new_trees, "قبل": 0.0, "بعد": 0.0,
                                    "set_number": new_set_no, "row_number": new_row_no}
                        self.invoices[self.invoice_counter] = inv_data
                        if not self.save_invoice_to_db(self.invoice_counter, inv_data):
                            any_blocked = True
                elif existing:
                    if not self.delete_invoice_from_db(existing["رقم الفاتورة"]):
                        any_blocked = True

            upsert(sarf_inv, new_sarf, madin_type)
            upsert(qabd_inv, new_qabd, qabd_type)

            # أي حركة أخرى في نفس الصف (غير الصرف والقبض) تتبع الترقيم الجديد
            # أيضاً، وإلا انفصلت عن صفها وظهرت كصف مستقل بعد التعديل
            for extra in invs:
                if extra is sarf_inv or extra is qabd_inv:
                    continue
                extra["row_number"] = new_row_no
                extra["set_number"] = new_set_no
                extra["التاريخ"] = new_dt
                if not self.save_invoice_to_db(extra["رقم الفاتورة"], extra):
                    any_blocked = True

            if any_blocked:
                return  # تم منع بعض التعديلات (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            win.destroy()
            if status_text and hasattr(self, 'lbl_op_status'):
                self.lbl_op_status.configure(text=status_text)
                self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            messagebox.showinfo("تم", "تم تحديث الحركة بنجاح.")

        # التنقّل بين الخانات: Enter و↑ ↓، وEnter في آخر خانة يحفظ مباشرة
        _nav = [e for e in (ent_sarf, ent_qabd,
                            ent_trees if with_trees else None,
                            ent_row_no, ent_set_no, ent_date, ent_note) if e is not None]
        self.bind_vertical_navigation(_nav, on_last=lambda: save_edit(), window=win)
        try:
            _nav[0].focus_set()
        except Exception:
            pass

        ctk.CTkButton(win, text="حفظ التعديلات 💾", font=("Cairo", 16, "bold"), fg_color="#2ecc71",
                      hover_color="#27ae60", height=42, command=save_edit).pack(pady=15)

    # ترتيب الشاشات في الشريط الجانبي كما طلبه المستخدم
    SIDEBAR_PRIMARY = [
        ("المبيعات",        "🧾", "المبيعات / الصادر"),
        ("مراحل التصنيع",   "⚙️", "مراحل التصنيع"),
        ("صناديق الخياس",   "⚖️", "صناديق الخياس"),
        ("الوارد",          "📥", "الوارد / قبض"),
        ("شاشة الخسائر",    "📉", "شاشة الخسائر"),
        ("صناديق المصنع",   "🏭", "صناديق المصنع"),
    ]
    SIDEBAR_SECONDARY = [
        ("ربح/خسارة الطقم", "📈", "ربح / خسارة الطقم"),
        ("كشف حساب",        "📑", "كشف حساب"),
        ("التقرير الشهري",  "📊", "التقرير الشهري"),
        ("أرشيف الفواتير",  "🗂️", "أرشيف الفواتير"),
        ("القيود اليومية",  "📝", "القيود اليومية"),
        ("الحسابات",        "🌳", "شجرة الحسابات"),
        ("الموردين",        "🚚", "الموردين"),
        ("الرصيد الافتتاحي", "🔢", "الرصيد الافتتاحي"),
    ]

    def sidebar_width(self):
        """عرض الشريط حسب حجم الشاشة: لا يبتلع المساحة على الشاشات الصغيرة"""
        try:
            sw = self.winfo_screenwidth()
        except Exception:
            sw = 1366
        # عريض بما يكفي ليظهر اسم كل شاشة كاملاً بخط واضح
        if sw >= 1920:
            return 330
        if sw >= 1440:
            return 300
        return 268

    def ui_scale(self):
        """معامل تكبير موحّد يجعل النظام مريحاً على كل مقاسات الشاشات"""
        try:
            sw = self.winfo_screenwidth()
        except Exception:
            sw = 1366
        if sw >= 1920:
            return 1.0
        if sw >= 1440:
            return 0.94
        return 0.86

    def get_screen_label(self, name, default_label):
        """اسم الشاشة المعروض في الشريط: المعدَّل من المستخدم إن وُجد"""
        try:
            saved = json.loads(self.get_setting("sidebar_labels", "") or "{}")
            return saved.get(name) or default_label
        except Exception:
            return default_label

    def rename_screen_dialog(self, name, default_label):
        """تعديل اسم شاشة في الشريط الجانبي (بالزر الأيمن)"""
        current = self.get_screen_label(name, default_label)
        new_label = ctk.CTkInputDialog(
            title="تعديل اسم الشاشة",
            text=f"الاسم الجديد للشاشة «{current}»\n(اتركه فارغاً لإرجاع الاسم الأصلي)"
        ).get_input()
        if new_label is None:
            return
        try:
            saved = json.loads(self.get_setting("sidebar_labels", "") or "{}")
            new_label = new_label.strip()
            if new_label and new_label != default_label:
                saved[name] = new_label
            else:
                saved.pop(name, None)
            self.set_setting("sidebar_labels", json.dumps(saved, ensure_ascii=False))
        except Exception as e:
            log_cloud_error("تعذّر حفظ اسم الشاشة", e)
        self.build_sidebar()

    def promote_screen_to_main(self, name):
        """ينقل شاشة من (أخرى) إلى القائمة الرئيسية في الشريط"""
        order = self.sidebar_order()
        if name not in order:
            order.append(name)
            self.save_sidebar_order(order)
        self.build_sidebar()

    def demote_screen_to_more(self, name):
        """يُرجع شاشة من القائمة الرئيسية إلى (أخرى)"""
        order = [n for n in self.sidebar_order() if n != name]
        self.save_sidebar_order(order)
        self.build_sidebar()

    def show_screen_context_menu(self, event, name, default_label, in_main):
        """قائمة الزر الأيمن: تعديل الاسم، ونقل الشاشة بين القائمتين"""
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="✏️ تعديل الاسم",
                         command=lambda: self.rename_screen_dialog(name, default_label))
        menu.add_separator()
        if in_main:
            menu.add_command(label="⤵️ نقل إلى (أخرى)",
                             command=lambda: self.demote_screen_to_more(name))
        else:
            menu.add_command(label="⤴️ نقل إلى القائمة الرئيسية",
                             command=lambda: self.promote_screen_to_main(name))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def sidebar_order(self):
        """ترتيب الشاشات في الشريط: المحفوظ إن وُجد، وإلا الافتراضي.

        يُصلَح تلقائياً لو أُضيفت أو حُذفت شاشة في نسخة أحدث.
        """
        default = [n for n, _i, _l in self.SIDEBAR_PRIMARY]
        try:
            saved = json.loads(self.get_setting("sidebar_order", "") or "[]")
        except Exception:
            saved = []
        known = {n for n, _i, _l in self.SIDEBAR_PRIMARY + self.SIDEBAR_SECONDARY}
        order = [n for n in saved if n in known]
        order += [n for n in default if n not in order]
        return order

    def save_sidebar_order(self, order):
        try:
            self.set_setting("sidebar_order", json.dumps(order, ensure_ascii=False))
        except Exception as e:
            log_cloud_error("تعذّر حفظ ترتيب الشريط الجانبي", e)

    def move_sidebar_item(self, name, direction):
        """يحرّك شاشة لأعلى أو لأسفل في الشريط الجانبي"""
        order = self.sidebar_order()
        if name not in order:
            order.insert(0, name)
        i = order.index(name)
        j = i + direction
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            self.save_sidebar_order(order)
            self.build_sidebar()

    def toggle_sidebar_arrange(self):
        """تشغيل/إيقاف وضع ترتيب الشريط: تظهر أسهم التحريك بجانب كل شاشة"""
        self._sidebar_arrange = not getattr(self, "_sidebar_arrange", False)
        self.build_sidebar()

    def build_sidebar(self):
        """يبني أزرار التنقّل: بطاقات بيضاء زجاجية بحواف زرقاء لامعة"""
        for w in self.sidebar.winfo_children():
            w.destroy()

        scale = self.ui_scale()
        btn_h = int(58 * scale)
        font_size = max(17, int(20 * scale))         # خط بارز يُقرأ من بعيد

        # رأس الشريط: شعار مصغّر واسم النظام
        head = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(14, 8))
        try:
            logo_img = Image.open(io.BytesIO(base64.b64decode(APP_LOGO_B64)))
            w0, h0 = logo_img.size
            dw = int(200 * scale)
            mini = ctk.CTkImage(light_image=logo_img, dark_image=logo_img,
                                size=(dw, max(1, round(dw * h0 / w0))))
            ctk.CTkLabel(head, image=mini, text="").pack()
        except Exception:
            ctk.CTkLabel(head, text="جاديت", font=("Cairo", 20, "bold"),
                         text_color="#d4af37").pack()

        ttk.Separator(self.sidebar, orient="horizontal").pack(fill="x", padx=12, pady=(4, 8))

        nav = ctk.CTkScrollableFrame(self.sidebar, fg_color=("#ffffff", "#ffffff"))
        nav.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        def make_button(parent, name, icon, label, primary=True, in_main=True):
            label = self.get_screen_label(name, label)
            """بطاقة زجاجية: خلفية بيضاء وحافة زرقاء تلمع عند المرور"""
            card = ctk.CTkFrame(
                parent, corner_radius=12, border_width=2,
                border_color="#2e86de" if primary else "#7f8c8d",
                fg_color=("#ffffff", "#ffffff"), height=btn_h)
            card.pack(fill="x", pady=4, padx=2)
            card.pack_propagate(False)

            btn = ctk.CTkButton(
                card, text=f"{icon}  {label}", anchor="e",
                font=ctk.CTkFont(family="Cairo", size=font_size, weight="bold"),
                fg_color="transparent", hover_color=("#dceeff", "#dceeff"),
                text_color=("#1b2a3a", "#1b2a3a"),
                corner_radius=10, height=btn_h - 6,
                command=lambda n=name: self.navigate_to_screen(n))
            btn.pack(fill="both", expand=True, padx=3, pady=3)

            # لمعان الحافة عند المرور بالفأرة
            def glow(_e=None):
                card.configure(border_color="#5dade2", fg_color=("#eaf5ff", "#22303f"))

            def unglow(_e=None):
                card.configure(border_color="#2e86de" if primary else "#7f8c8d",
                               fg_color=("#ffffff", "#ffffff"))

            for widget in (card, btn):
                widget.bind("<Enter>", glow, add="+")
                widget.bind("<Leave>", unglow, add="+")
                # الزر الأيمن: تعديل الاسم أو نقل الشاشة بين القائمتين
                widget.bind("<Button-3>",
                            lambda e, n=name, l=label, m=in_main:
                            self.show_screen_context_menu(e, n, l, m), add="+")
            return card

        registered = set(getattr(self.tabview, "_contents", {}).keys())
        meta = {n: (i, l) for n, i, l in self.SIDEBAR_PRIMARY + self.SIDEBAR_SECONDARY}
        arranging = getattr(self, "_sidebar_arrange", False)

        for name in self.sidebar_order():
            if name not in registered:
                continue
            icon, label = meta.get(name, ("📄", name))
            card = make_button(nav, name, icon, label, primary=True, in_main=True)
            if arranging:
                # أسهم التحريك تظهر في وضع الترتيب فقط، فلا تزحم الواجهة عادةً
                arrows = ctk.CTkFrame(card, fg_color="transparent")
                arrows.place(relx=0.02, rely=0.5, anchor="w")
                for txt_a, delta in (("▲", -1), ("▼", 1)):
                    ctk.CTkButton(arrows, text=txt_a, width=24, height=22,
                                  font=("Cairo", 11, "bold"), fg_color="#2e86de",
                                  hover_color="#1b5e91", corner_radius=6,
                                  command=lambda n=name, d=delta: self.move_sidebar_item(n, d)
                                  ).pack(side="left", padx=1)

        # زر (أخرى) يفتح باقي الشاشات أسفله
        self._sidebar_more_open = False
        more_holder = ctk.CTkFrame(nav, fg_color="transparent")

        def toggle_more():
            self._sidebar_more_open = not self._sidebar_more_open
            if self._sidebar_more_open:
                more_holder.pack(fill="x", pady=(2, 0))
                btn_more.configure(text="▴  أخرى")
            else:
                more_holder.pack_forget()
                btn_more.configure(text="▾  أخرى")

        more_card = ctk.CTkFrame(nav, corner_radius=12, border_width=2,
                                 border_color="#b8860b",
                                 fg_color=("#fffaf0", "#fffaf0"), height=btn_h)
        more_card.pack(fill="x", pady=(10, 4), padx=2)
        more_card.pack_propagate(False)
        btn_more = ctk.CTkButton(
            more_card, text="▾  أخرى", anchor="e",
            font=ctk.CTkFont(family="Cairo", size=font_size, weight="bold"),
            fg_color="transparent", hover_color=("#fdf0d5", "#fdf0d5"),
            text_color=("#6b4e00", "#6b4e00"), corner_radius=10, height=btn_h - 6,
            command=toggle_more)
        btn_more.pack(fill="both", expand=True, padx=3, pady=3)

        more_holder.pack_forget()
        primary_names = set(self.sidebar_order())
        for name, icon, label in self.SIDEBAR_SECONDARY:
            if name in registered and name not in primary_names:
                make_button(more_holder, name, icon, label, primary=False, in_main=False)

        # زر ترتيب الشريط أسفله
        ctk.CTkButton(
            self.sidebar,
            text="✅ إنهاء الترتيب" if arranging else "↔️ ترتيب الشاشات",
            font=ctk.CTkFont(family="Cairo", size=max(12, int(13 * scale)), weight="bold"),
            fg_color="#1e8449" if arranging else "#555555",
            hover_color="#145a32" if arranging else "#333333",
            height=int(38 * scale), corner_radius=10,
            command=self.toggle_sidebar_arrange).pack(fill="x", padx=10, pady=(0, 4))

        ctk.CTkLabel(self.sidebar, text="زر الفأرة الأيمن: تعديل الاسم أو النقل",
                     font=("Cairo", 10), text_color="#8b8f95").pack(pady=(0, 10))

    def create_layout(self):
        # الشريط الجانبي أولاً وبكامل ارتفاع النافذة (من أعلاها لأسفلها)،
        # ثم منطقة المحتوى يساره تضمّ الشريط العلوي والشاشات معاً.
        self.sidebar = ctk.CTkFrame(
            self, width=self.sidebar_width(), corner_radius=0,
            border_width=0, fg_color=("#ffffff", "#ffffff"))
        self.sidebar.pack(side="right", fill="y")
        self.sidebar.pack_propagate(False)

        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.pack(side="right", fill="both", expand=True)

        top_frame = ctk.CTkFrame(self.content_area, height=62, corner_radius=10)
        top_frame.pack(fill="x", padx=10, pady=(8, 6))
        self.top_frame = top_frame

        treasury_display_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        treasury_display_frame.pack(side="right", padx=14, pady=4)

        # ====== شريط رصيد الخزينة ======
        treasury_bar = ctk.CTkFrame(treasury_display_frame, corner_radius=10,
                                     fg_color=("#f3e6c0", "#2a2318"), border_width=2, border_color="#d4af37")
        treasury_bar.pack(fill="x", pady=(0, 4))

        self.lbl_live_treasury = ctk.CTkLabel(treasury_bar, text="رصيد الخزينة الحالي: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=19, weight="bold"), text_color="#d4af37")
        self.lbl_live_treasury.pack(padx=14, pady=3)

        # ====== شريط الرصيد الحالي (الخزينة + كل صناديق الخياس) ======
        total_bar = ctk.CTkFrame(treasury_display_frame, corner_radius=10,
                                  fg_color=("#d9ecd9", "#16261a"), border_width=2, border_color="#2ecc71")
        total_bar.pack(fill="x", pady=(0, 6))

        self.lbl_total_gold = ctk.CTkLabel(total_bar, text="الرصيد الحالي: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=19, weight="bold"), text_color="#2ecc71")
        self.lbl_total_gold.pack(padx=14, pady=3)
        self.lbl_total_gold.bind("<Button-1>", lambda e: self.show_gold_balance_breakdown())

        # أرصدة الفصوص والألماس تبقى محسوبة لكنها لا تُرصف: الشريط العلوي
        # يعرض الرصيدين الأساسيين فقط ليبقى منخفضاً ومريحاً للعين.
        # تفصيلها متاح بالضغط على (الرصيد الحالي).
        self.lbl_gems_stones_balance = ctk.CTkLabel(treasury_display_frame, text="", font=("Cairo", 11))
        self.lbl_diamond_balance = ctk.CTkLabel(treasury_display_frame, text="", font=("Cairo", 11))

        self.btn_theme = ctk.CTkButton(top_frame, text="🎨 المظهر", width=108, height=34, corner_radius=8, font=ctk.CTkFont(family="Cairo", size=12, weight="bold"), fg_color="#444444", hover_color="#666666", command=self.toggle_theme)
        self.btn_theme.pack(side="right", padx=8, pady=6)

        # صف أدوات واحد: كل الأزرار جنباً إلى جنب أفقياً بلا تبعثر رأسي
        period_column = ctk.CTkFrame(top_frame, fg_color="transparent")
        period_column.pack(side="right", padx=8, pady=4)
        self.period_column = period_column

        period_frame = ctk.CTkFrame(period_column, fg_color="transparent")
        period_frame.pack(side="right")
        
        ctk.CTkLabel(period_frame, text="الفترة:", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.combo_active_period = ctk.CTkComboBox(period_frame, width=125, font=("Cairo", 16), command=self.on_period_changed)
        self.combo_active_period.pack(side="right", padx=5)
        
        btn_add_period = ctk.CTkButton(period_frame, text="➕ شهر جديد", width=110, height=40, font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), fg_color="#1f77b4", hover_color="#144d75", command=self.add_new_period_ui)
        btn_add_period.pack(side="right", padx=5)

        # قسم البحث المزدوج الجديد (بحث فاتورة + بحث رقم التشغيل)
        # أزرار البحث لا تُرصف: الشريط العلوي يعرض الرصيدين والفترة والمظهر
        # وتصفير البيانات فقط. البحث متاح من داخل الشاشات نفسها.
        search_container = ctk.CTkFrame(top_frame, fg_color="transparent")

        # صف 1: البحث وتعديل الفاتورة
        row1 = ctk.CTkFrame(search_container, fg_color="transparent")
        row1.pack(fill="x", pady=3)
        btn_search = ctk.CTkButton(row1, text="بحث عن فاتورة", font=ctk.CTkFont(family="Cairo", size=12, weight="bold"), width=112, height=30, corner_radius=8, command=self.search_invoice_window)
        btn_search.pack(side="left", padx=5)
        self.entry_search_inv = ctk.CTkEntry(row1, placeholder_text="رقم الفاتورة...", font=("Cairo", 14), justify="center", width=125, height=35)
        self.entry_search_inv.pack(side="left", padx=5)
        self.entry_search_inv.bind("<Return>", lambda e: self.search_invoice_window())
        # تحديد الشاشة التي تمت فيها الفاتورة (الأرقام قد تتكرر بين الشاشات)
        self.combo_search_source = ctk.CTkComboBox(row1, values=self.SEARCH_SOURCES, font=("Cairo", 13),
                                                    justify="right", width=145, height=35, state="readonly")
        self.combo_search_source.set("المبيعات/الصادر")
        self.combo_search_source.pack(side="left", padx=5)

        # صف 2: البحث برقم التشغيل الجديد
        row2 = ctk.CTkFrame(search_container, fg_color="transparent")
        row2.pack(fill="x", pady=3)
        btn_search_op = ctk.CTkButton(row2, text="بحث برقم التشغيل", font=ctk.CTkFont(family="Cairo", size=12, weight="bold"), width=124, height=30, corner_radius=8, fg_color="#b8860b", hover_color="#daa520", command=self.search_op_number_window)
        btn_search_op.pack(side="left", padx=5)
        self.entry_search_op = ctk.CTkEntry(row2, placeholder_text="رقم التشغيل...", font=("Cairo", 14), justify="center", width=140, height=35)
        self.entry_search_op.pack(side="left", padx=5)

        # زر التصفير يُنشأ داخل عمود الفترة مباشرة فيظهر فوق شريط الشهر
        btn_clear_system = ctk.CTkButton(self.period_column, text="⚠️ تصفير البيانات", font=ctk.CTkFont(family="Cairo", size=12, weight="bold"), width=132, height=32, corner_radius=8, fg_color="#b03a2e", hover_color="#7b241c", command=self.reset_system_data_action)
        btn_clear_system.pack(side="right", padx=(6, 0))

        # ====== خانة حالة التعديل والمزامنة: في طرف الشريط العلوي داخل إطار مستقل واضح ======
        status_box = ctk.CTkFrame(top_frame, corner_radius=10, border_width=1, border_color="#555555")
        status_box.pack(side="left", padx=12, pady=8)

        self.lbl_edit_status = ctk.CTkLabel(status_box, text="", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), text_color="#2ecc71")
        self.lbl_edit_status.pack(padx=10, pady=(7, 0))

        self.lbl_cloud_sync = ctk.CTkLabel(status_box, text="☁️ المزامنة: —", font=ctk.CTkFont(family="Cairo", size=11), text_color="#aaaaaa")
        self.lbl_cloud_sync.pack(padx=10)

        # تنبيه واضح لو كانت الفترة المعروضة ليست الشهر الحالي
        self.lbl_period_warning = ctk.CTkLabel(status_box, text="", font=ctk.CTkFont(family="Cairo", size=11, weight="bold"), text_color="#e67e22")
        self.lbl_period_warning.pack(padx=10)

        status_btns = ctk.CTkFrame(status_box, fg_color="transparent")
        status_btns.pack(padx=8, pady=(3, 7))
        ctk.CTkButton(status_btns, text="🔄 تحديث الصلاحية", font=("Cairo", 12, "bold"), width=125, height=28,
                      fg_color="#1f77b4", hover_color="#144d75", command=self.refresh_edit_permission_now).pack(side="left", padx=3)
        ctk.CTkButton(status_btns, text="☁️ النسخ الاحتياطي", font=("Cairo", 12, "bold"), width=125, height=28,
                      fg_color="#555555", hover_color="#333333", command=self.open_backup_manager).pack(side="left", padx=3)

        self.main_shell = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.main_shell.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.tabview = ScreenRouter(self.main_shell, go_home_callback=self.show_home_screen)

        self.tabview.add("الحسابات")
        self.tabview.add("الرصيد الافتتاحي")
        self.tabview.add("الوارد")
        self.tabview.add("المبيعات")
        self.tabview.add("الموردين")
        self.tabview.add("مراحل التصنيع")
        self.tabview.add("صناديق الخياس")
        self.tabview.add("صناديق المصنع")
        self.tabview.add("كشف حساب")
        self.tabview.add("التقرير الشهري")
        self.tabview.add("أرشيف الفواتير")
        self.tabview.add("القيود اليومية")
        self.tabview.add("شاشة الخسائر")
        self.tabview.add("ربح/خسارة الطقم")

        # ═══════════════════════════════════════════════════════════════
        #  بناء كسول للشاشات
        #
        #  كانت الشاشات الأربع عشرة تُبنى كلها عند التشغيل: آلاف الأدوات
        #  تُنشأ وتُرسم قبل ظهور النظام، فيبطؤ الفتح وتظهر الشاشات وهي
        #  «تتكوّن» أمام المستخدم.
        #
        #  الآن تُبنى كل شاشة **عند أول فتح لها فقط**، ثم تبقى جاهزة.
        #  فالتشغيل فوري، وفتح الشاشة أول مرة يستغرق جزءاً من الثانية.
        # ═══════════════════════════════════════════════════════════════
        self._screen_builders = {
            "الرصيد الافتتاحي": self.build_opening_tab,
            "الوارد":           self.build_inout_tab,
            "المبيعات":         self.build_sales_tab,
            "الموردين":         self.build_suppliers_tab,
            "مراحل التصنيع":    self.build_operations_tab,
            "صناديق الخياس":    self.build_inquiries_tab,
            "صناديق المصنع":    self.build_factory_boxes_tab,
            "كشف حساب":         self.build_account_statement_tab,
            "التقرير الشهري":   self.build_monthly_report_tab,
            "أرشيف الفواتير":   self.build_invoice_archive_tab,
            "القيود اليومية":   self.build_journal_entries_tab,
            "شاشة الخسائر":     self.build_losses_tab,
            "الحسابات":         self.build_chart_of_accounts_tab,
            "ربح/خسارة الطقم":  self.build_sets_profit_tab,
        }
        self._built_screens = set()

        self.ensure_default_khayas_boxes()
        self.remove_legacy_casting_box()
        self.build_gold_price_bar()
        self.build_home_screen()
        self.show_home_screen()
        self.update_edit_status_ui()
        self.update_period_warning()
        self.watch_system_month()
        self.refresh_live_date_fields()
        self.start_cloud_sync_engine()

    def build_gold_price_bar(self):
        """شريط سعر الذهب العالمي أسفل الشاشة — يتحدّث تلقائياً كل ١٠ ثوانٍ"""
        self.gold_watcher = None

        # خلفية رصاصية غامقة موحّدة في الوضعين الفاتح والداكن،
        # والأرقام سوداء بارزة عليها لأقصى وضوح
        self.gold_bar = ctk.CTkFrame(self, height=44, corner_radius=0,
                                      fg_color=("#9aa0a6", "#8a9096"),
                                      border_width=2, border_color="#6d7378")
        # يُرصف قبل الشريط الجانبي ليمتدّ بعرض النافذة كاملاً أسفل الكل،
        # وإلا اقتصر على المنطقة اليسرى فقط
        if hasattr(self, "sidebar"):
            self.gold_bar.pack(side="bottom", fill="x", before=self.sidebar)
        else:
            self.gold_bar.pack(side="bottom", fill="x")

        self.lbl_gold_price = ctk.CTkLabel(
            self.gold_bar, text="🥇 جارٍ جلب سعر الذهب العالمي…",
            font=ctk.CTkFont(family="Cairo", size=16, weight="bold"),
            text_color="#000000")
        self.lbl_gold_price.pack(side="right", padx=16, pady=7)

        ctk.CTkButton(self.gold_bar, text="🔄 تحديث", width=80, height=28,
                      font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                      fg_color="#5f6368", hover_color="#42464a", text_color="#ffffff",
                      command=lambda: self.gold_watcher and self.gold_watcher.refresh_now()
                      ).pack(side="left", padx=10)

        if not GOLD_PRICE_AVAILABLE:
            self.lbl_gold_price.configure(text="🥇 سعر الذهب غير متاح (وحدة الأسعار غير موجودة)",
                                          text_color="#5a2d0c")
            return

        try:
            self.gold_watcher = GoldPriceWatcher(on_update=self._on_gold_price)
            self.gold_watcher.start()
        except Exception as e:
            log_cloud_error("تعذّر تشغيل مراقب سعر الذهب", e)

    def _on_gold_price(self, snapshot):
        """يُستدعى من الخيط الخلفي — يمرّ عبر after حتى لا يُسقط Tkinter"""
        def apply():
            try:
                # أسود عند توفر السعر، وبنّي غامق عند تعذّر التحديث
                # (كلاهما واضح على الخلفية الرصاصية)
                self.lbl_gold_price.configure(
                    text=self.gold_watcher.display_text(),
                    text_color="#000000" if snapshot.get("ounce") else "#5a2d0c")
            except Exception:
                pass
        try:
            self.after(0, apply)
        except Exception:
            pass

    def start_cloud_sync_engine(self):
        # نسخة المدير مرآة للقراءة: لا تُشغّل محرك الرفع إطلاقاً، فلا يمكن
        # لبياناتها المؤقتة أن تصعد للسحابة وتطمس بيانات العميل
        if IS_ADMIN_BUILD:
            return
        """يشغّل محرك الرفع الخلفي. فشله لا يؤثر على عمل البرنامج محلياً إطلاقاً."""
        self.cloud_sync = None
        if not (SYNC_AVAILABLE and self.client_id and CURRENT_SYNC_TOKEN):
            return
        try:
            api = _RpcBridge(self.supabase or get_supabase_public_client(), CURRENT_SYNC_TOKEN)
            self.cloud_sync = CloudSync(
                db_path=self.db_path,
                api=api,
                tenant_id=self.client_id,
                app_version=APP_VERSION,
                on_status=self._on_sync_status,
                on_remote_change=self._on_remote_change,
            )
            self.cloud_sync.start()
        except Exception as e:
            log_cloud_error("تعذّر تشغيل محرك المزامنة", e)

    def _on_sync_status(self, text):
        """تُستدعى من الخيط الخلفي — نمرّرها لخيط الواجهة عبر after"""
        try:
            self.after(0, lambda: self.lbl_cloud_sync.configure(text=text))
        except Exception:
            pass

    def _on_remote_change(self, count):
        # نسخة العميل لا تستقبل أي تغيير من السحابة: بياناتها مصدر الحقيقة
        if not IS_ADMIN_BUILD:
            return
        """وصلت تعديلات من لوحة الإدارة على الويب: نعيد تحميل البيانات ونحدّث الشاشات.

        تُستدعى من الخيط الخلفي، فكل العمل يمر عبر after حتى لا يُسقط Tkinter.
        """
        def apply():
            try:
                self.load_data_from_db()
                self.update_period_selector()
                self.recalculate_all()
                if hasattr(self, 'lbl_cloud_sync'):
                    self.lbl_cloud_sync.configure(
                        text=f"🔄 وصل {count} تحديث من الإدارة")
                    self.after(6000, lambda: self.lbl_cloud_sync.configure(
                        text=self.cloud_sync.status_text() if self.cloud_sync else ""))
            except Exception as e:
                log_cloud_error("تعذّر تطبيق تحديثات الإدارة", e)

        try:
            self.after(0, apply)
        except Exception:
            pass

    def open_app_data_folder(self):
        """يفتح مجلد ملفات النظام (قاعدة البيانات + النسخ الاحتياطية + الفواتير + السجلات)"""
        try:
            self._open_file(APP_DATA_DIR)
        except Exception as e:
            messagebox.showinfo("مجلد ملفات النظام", f"مسار ملفات النظام:\n{APP_DATA_DIR}\n\n(تعذّر فتحه تلقائياً: {e})")

    def get_home_screens_default(self):
        return ["الحسابات", "الرصيد الافتتاحي", "الوارد", "المبيعات", "الموردين", "مراحل التصنيع",
                "صناديق الخياس", "صناديق المصنع", "كشف حساب", "التقرير الشهري", "أرشيف الفواتير",
                "القيود اليومية", "شاشة الخسائر", "ربح/خسارة الطقم"]

    def load_home_order(self):
        """يقرأ ترتيب الشاشات المحفوظ، ويصلحه تلقائياً لو أُضيفت أو حُذفت شاشة في نسخة أحدث"""
        default = self.get_home_screens_default()
        try:
            saved = json.loads(self.get_setting("home_screen_order", "") or "[]")
        except Exception:
            saved = []
        order = [n for n in saved if n in default]
        order += [n for n in default if n not in order]   # أي شاشة جديدة تُضاف في آخر الترتيب
        return order

    def save_home_order(self):
        try:
            self.set_setting("home_screen_order", json.dumps(self.home_order, ensure_ascii=False))
        except Exception:
            pass

    def build_home_screen(self):
        # الشريط الجانبي يُبنى بعد تسجيل كل الشاشات، فيعرف أيّها متاح فعلاً
        try:
            self.build_sidebar()
        except Exception as e:
            log_cloud_error("تعذّر بناء الشريط الجانبي", e)

        self.home_frame = ctk.CTkFrame(self.main_shell, fg_color="transparent")

        # ====== الشعار: بطاقة بلون النظام نفسه (لا إطار أبيض) بارزة في أعلى الواجهة ======
        # المساحة اليسرى بيضاء بالكامل بلا هوامش، والشعار في منتصفها تماماً
        logo_card = ctk.CTkFrame(self.home_frame, corner_radius=0, border_width=0,
                                 fg_color=("#ffffff", "#12161c"))
        logo_card.pack(fill="both", expand=True, padx=0, pady=0)

        try:
            # الشعار النقي المرفق أولاً؛ صورة الترويسة (الاسم والعنوان) بديل
            # فقط لو غاب الملف — المطلوب شعار كبير وحده بلا نصوص جانبية
            pure = resource_path("jadeite_logo.png")
            if os.path.exists(pure):
                # RGBA يحفظ الشفافية؛ بدونه تظهر خلفية سوداء خلف الشعار
                logo_img = Image.open(pure).convert("RGBA")
                # تخفيف السطوع: الشعار خلفية للشاشة لا عنصر يُقرأ، فالألوان
                # الكاملة تُجهد العين. نُخفّف شفافيته فيبدو هادئاً مريحاً.
                try:
                    alpha = logo_img.getchannel("A").point(lambda v: int(v * 0.38))
                    logo_img.putalpha(alpha)
                except Exception:
                    pass
            else:
                logo_img = Image.open(io.BytesIO(base64.b64decode(APP_LOGO_B64)))
            w, h = logo_img.size
            # الشعار يملأ المساحة البيضاء: نصف عرضها المتاح تقريباً، بحدّ
            # أدنى وأقصى يمنعان صِغره على الشاشات الكبيرة أو قصّه على الصغيرة
            try:
                avail = self.winfo_screenwidth() - self.sidebar_width() - 60
            except Exception:
                avail = 1000
            # حجم معتدل: كبير بما يكفي ليبرز، وصغير بما يكفي ألا يطغى
            disp_w = max(240, min(420, int(avail * 0.26)))
            disp_h = round(disp_w * h / w)
            ctk_logo = ctk.CTkImage(light_image=logo_img, dark_image=logo_img, size=(disp_w, disp_h))
            ctk.CTkLabel(logo_card, image=ctk_logo, text="",
                         fg_color=("#ffffff", "#12161c")).place(
                relx=0.5, rely=0.5, anchor="center")
        except Exception:
            ctk.CTkLabel(logo_card, text="💎 مصنع جاديت للتصنيع", font=("Cairo", 26, "bold"), text_color="#d4af37").pack(pady=16)

        header_row = ctk.CTkFrame(self.home_frame, fg_color="transparent")
        header_row.pack(fill="x", padx=30, pady=(10, 6))

        self.lbl_home_hint = ctk.CTkLabel(header_row, text="اختر الشاشة التي تريد الدخول إليها",
                                          font=("Cairo", 15, "bold"), text_color="#aaaaaa")
        self.lbl_home_hint.pack(side="right", expand=True)
        try:
            self.lbl_home_hint.configure(text="اختر الشاشة من الشريط الجانبي على اليمين")
        except Exception:
            pass

        self.home_arrange_mode = False
        self.home_swap_pick = None
        self.btn_home_arrange = ctk.CTkButton(header_row, text="↔️ ترتيب الشاشات", font=("Cairo", 13, "bold"),
                                              width=145, height=34, fg_color="#555555", hover_color="#333333",
                                              command=self.toggle_home_arrange_mode)
        # الترتيب صار من الشريط الجانبي نفسه، فلا داعي لتكراره هنا
        # self.btn_home_arrange.pack(side="left", padx=4)

        self.btn_home_reset = ctk.CTkButton(header_row, text="↺ الترتيب الافتراضي", font=("Cairo", 13, "bold"),
                                            width=155, height=34, fg_color="#8b0000", hover_color="#a52a2a",
                                            command=self.reset_home_order)
        # self.btn_home_reset.pack(side="left", padx=4)

        # ====== أزرار التنقل: 3 شاشات في كل عمود (توزيع رأسي مضغوط يناسب الشاشات الصغيرة) ======
        # شبكة الأزرار القديمة تبقى موجودة (لترتيب الشاشات) لكنها لا تُرصف:
        # التنقّل صار من الشريط الجانبي، والمساحة للشعار
        self.home_btns_frame = ctk.CTkFrame(self.home_frame, fg_color="transparent")

        self.home_order = self.load_home_order()
        self.render_home_buttons()

    def render_home_buttons(self):
        """يعيد رسم أزرار الشاشات حسب الترتيب المحفوظ (٣ شاشات في كل عمود، من اليمين لليسار)"""
        for widget in self.home_btns_frame.winfo_children():
            widget.destroy()

        screen_display = {"الوارد": "الوارد/قبض", "المبيعات": "المبيعات/الصادر"}
        rows_per_col = 3
        n_cols = (len(self.home_order) + rows_per_col - 1) // rows_per_col

        for i, name in enumerate(self.home_order):
            if self.home_arrange_mode:
                fg = "#d4af37" if self.home_swap_pick == name else "#7d6608"
                cmd = (lambda n=name: self.home_pick_for_swap(n))
            else:
                fg = "#1f77b4"
                cmd = (lambda n=name: self.navigate_to_screen(n))

            b = ctk.CTkButton(self.home_btns_frame, text=screen_display.get(name, name),
                              font=("Cairo", 15, "bold"), width=200, height=50,
                              fg_color=fg, hover_color="#144d75", command=cmd)
            b.grid(row=i % rows_per_col, column=(n_cols - 1) - (i // rows_per_col), padx=10, pady=9)

    def toggle_home_arrange_mode(self):
        """تشغيل/إيقاف وضع الترتيب: في وضع الترتيب تُبدَّل أماكن الشاشات بدل الدخول إليها"""
        # شبكة الترتيب تظهر عند تفعيل الوضع فقط، ثم تُخفى ليعود الشعار للمساحة
        try:
            if self.home_arrange_mode:
                self.home_btns_frame.pack_forget()
            else:
                self.home_btns_frame.pack(pady=4)
        except Exception:
            pass

        self.home_arrange_mode = not self.home_arrange_mode
        self.home_swap_pick = None
        if self.home_arrange_mode:
            self.btn_home_arrange.configure(text="✅ إنهاء الترتيب", fg_color="#1e8449", hover_color="#145a32")
            self.lbl_home_hint.configure(text="اضغط على شاشة ثم على شاشة أخرى لتبديل مكانيهما", text_color="#d4af37")
        else:
            self.btn_home_arrange.configure(text="↔️ ترتيب الشاشات", fg_color="#555555", hover_color="#333333")
            self.lbl_home_hint.configure(text="اختر الشاشة من الشريط الجانبي على اليمين", text_color="#aaaaaa")
            self.save_home_order()
        self.render_home_buttons()

    def home_pick_for_swap(self, name):
        """أول ضغطة تختار الشاشة، والثانية تبدّل مكانها بمكان الشاشة الأخرى"""
        if self.home_swap_pick is None:
            self.home_swap_pick = name
        elif self.home_swap_pick == name:
            self.home_swap_pick = None
        else:
            i, j = self.home_order.index(self.home_swap_pick), self.home_order.index(name)
            self.home_order[i], self.home_order[j] = self.home_order[j], self.home_order[i]
            self.home_swap_pick = None
            self.save_home_order()
        self.render_home_buttons()

    def reset_home_order(self):
        if not messagebox.askyesno("الترتيب الافتراضي", "هل تريد إرجاع ترتيب الشاشات للوضع الافتراضي؟"):
            return
        self.home_order = self.get_home_screens_default()
        self.home_swap_pick = None
        self.save_home_order()
        self.render_home_buttons()

    @contextlib.contextmanager
    def frozen_redraw(self):
        """يوقف رسم النافذة أثناء بناء الأدوات ثم يُظهرها دفعةً واحدة.

        بدونه يرسم Tk كل أداة فور إضافتها، فيرى المستخدم الشاشة «تتكوّن»
        قطعةً قطعة. التجميد يجعلها تظهر جاهزة مرة واحدة.
        """
        frozen = False
        try:
            # لا نُجمّد نافذة غير ظاهرة أصلاً (لا فائدة، وقد يُسبب وميضاً)
            if self.winfo_viewable():
                self.tk.call("update", "idletasks")
                frozen = True
            yield
        finally:
            if frozen:
                try:
                    self.update_idletasks()
                except Exception:
                    pass

    def navigate_to_screen(self, name):
        if getattr(self, 'home_arrange_mode', False):
            self.toggle_home_arrange_mode()
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack_forget()

        # الشريط العام يختفي داخل الشاشات: مساحته كاملة تذهب للجدول،
        # وبياناته (الفترة والأرصدة) تظهر مصغّرة في شريط الشاشة نفسها
        if hasattr(self, 'top_frame'):
            self.top_frame.pack_forget()

        # الشريط الجانبي يختفي أيضاً: الشاشة تفتح بعرض النافذة كاملاً،
        # والعودة إليه بزر (🏠 القائمة الرئيسية) أعلى الشاشة
        if hasattr(self, 'sidebar'):
            self.sidebar.pack_forget()

        # البناء والتحديث داخل تجميد واحد، ثم تُعرض الشاشة جاهزة دفعةً واحدة
        with self.frozen_redraw():
            self.ensure_screen_built(name)
            self.refresh_pending_screen(name)
            self.tabview.show(name)
        self.refresh_screen_info_bar()

    def show_home_screen(self):
        # العودة للقائمة الرئيسية تُرجع الشريط العام والشريط الجانبي معاً
        if hasattr(self, 'sidebar'):
            self.sidebar.pack(side="right", fill="y", before=self.content_area)
        if hasattr(self, 'top_frame'):
            self.top_frame.pack(fill="x", padx=10, pady=(8, 6), before=self.main_shell)
        if hasattr(self, 'home_frame') and self.home_frame:
            self.home_frame.pack(fill="both", expand=True)

    # خريطة: اسم الشاشة ← الدوال التي تُعيد بناء جداولها
    # الأسماء هنا يجب أن تطابق أسماء الشاشات المسجّلة في tabview.add تماماً،
    # وإلا لم تُحدَّث الشاشة عند فتحها. يتحقق من ذلك test_lazy_refresh.py
    SCREEN_REFRESHERS = {
        "مراحل التصنيع": ("refresh_op_ledger_table", "refresh_casting_table",
                          "refresh_polish_table", "refresh_polish_buff_table",
                          "_refresh_dynamic_stages"),
        "صناديق الخياس": ("refresh_inquiry_table",),
        "الوارد": ("refresh_inout_tables",),
        "المبيعات": ("refresh_sales_table", "refresh_sales_ops_table"),
        "التقرير الشهري": ("calculate_and_refresh_monthly_report",),
        "أرشيف الفواتير": ("refresh_invoice_archive_table",),
        "القيود اليومية": ("refresh_journal_entries_table",),
        "شاشة الخسائر": ("refresh_losses_tab",),
        "الحسابات": ("refresh_chart_of_accounts",),
        "الموردين": ("refresh_suppliers_table",),
        "كشف حساب": ("refresh_account_statement",),
        "الرصيد الافتتاحي": ("refresh_opening_table",),
        "صناديق المصنع": ("refresh_factory_boxes_table",),
        "ربح/خسارة الطقم": ("refresh_sets_profit_tab",),
    }

    def _refresh_dynamic_stages(self):
        """يُعيد بناء جداول الأقسام المضافة ديناميكياً"""
        for stage_name in list(getattr(self, "dynamic_stage_widgets", {}).keys()):
            self.refresh_generic_stage_table(stage_name)

    def mark_all_screens_dirty(self):
        """يُعلّم كل الشاشات بأنها تحتاج إعادة رسم عند فتحها"""
        self._dirty_screens = set(self.SCREEN_REFRESHERS.keys())

    def refresh_screen(self, name):
        """يُعيد بناء جداول شاشة واحدة ويزيل علامة الحاجة للتحديث عنها"""
        # شاشة لم تُبنَ بعد لا تُحدَّث: ستُبنى بأحدث البيانات عند أول فتح
        if name in getattr(self, "_screen_builders", {}) and \
                name not in getattr(self, "_built_screens", set()):
            return
        for fn_name in self.SCREEN_REFRESHERS.get(name, ()):
            fn = getattr(self, fn_name, None)
            if fn is None:
                continue
            try:
                fn()
            except Exception as e:
                log_cloud_error(f"تعذّر تحديث ({name}) عبر {fn_name}", e)
        if hasattr(self, "_dirty_screens"):
            self._dirty_screens.discard(name)

    def refresh_visible_screen(self):
        """يُحدّث الشاشة المفتوحة حالياً فقط — هذا ما يراه المستخدم فعلاً"""
        current = getattr(getattr(self, "tabview", None), "current_screen", None)
        if current:
            self.refresh_screen(current)

    def ensure_screen_built(self, name):
        """يبني أدوات الشاشة عند أول فتح لها فقط.

        يرجع True لو بُنيت الآن. الفشل لا يُسكت: تظهر رسالة واضحة بدل
        شاشة فارغة بلا تفسير.
        """
        if name in getattr(self, "_built_screens", set()):
            return False
        builder = getattr(self, "_screen_builders", {}).get(name)
        if builder is None:
            return False

        try:
            self.configure(cursor="watch")
            self.update_idletasks()
        except Exception:
            pass
        try:
            builder()
            self._built_screens.add(name)
            return True
        except Exception as e:
            log_cloud_error(f"تعذّر بناء شاشة ({name})", e)
            messagebox.showerror("خطأ", f"تعذّر فتح شاشة ({name}):\n{e}")
            return False
        finally:
            try:
                self.configure(cursor="")
            except Exception:
                pass

    def refresh_pending_screen(self, name):
        """يُحدّث شاشة عند فتحها إن كانت بحاجة لذلك (تحديث كسول)"""
        if name in getattr(self, "_dirty_screens", set()):
            self.refresh_screen(name)

    def refresh_screen_info_bar(self):
        """يحدّث الفترة والأرصدة المصغّرة في شريط كل شاشة"""
        if not hasattr(self, 'tabview'):
            return
        try:
            self.tabview.update_screen_info(
                f"الفترة: {self.current_display_month}",
                f"الخزينة: {en(getattr(self, 'current_treasury_balance', 0.0))} جم",
                f"الرصيد الحالي: {en(getattr(self, 'current_total_gold', 0.0))} جم")
        except Exception:
            pass

    def reset_system_data_action(self):
        if not self.check_edit_permission():
            return
        first_confirm = messagebox.askyesno("تنبيه أمني حساس", "تنبيه خطير جداً!\n\nهل أنت متأكد من رغبتك في مسح وتصفير كافة بيانات النظام بالكامل؟\n(سيتم حذف جميع الحسابات، العمال، الفواتير، الأرشيف والخزائن بشكل نهائي!)")
        if not first_confirm: return
            
        second_confirm = messagebox.askyesno("تأكيد قطعي للتدمير", "هل أنت متأكد بنسبة 100% من حذف قاعدة البيانات الحالية؟\nلا يمكن التراجع عن هذه العملية بعد إتمامها!")
        if not second_confirm: return
            
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM invoices")
                cursor.execute("DELETE FROM names")
                cursor.execute("DELETE FROM monthly_archive")
                conn.commit()
            
            self.categories = {"المصنعين": [], "المركبين": [], "الآلة/المكائن": [], "الكاستنج": [], "التلميع": [], "التلميع/البف": [], "الموردين": [], "حسابات إضافية": [], "أقسام_خياس_إضافية": [], "نسب_خصم_احجار": []}
            self.invoices = {}
            self.opening_balance = 0.0
            self.invoice_counter = 1000
            self.current_display_month = datetime.datetime.now().strftime("%Y-%m")
            
            self.update_period_selector()
            self.recalculate_all()
            if hasattr(self, 'entry_opening') and self.entry_opening:
                self.entry_opening.delete(0, 'end')
                
            messagebox.showinfo("تصفير ناجح", "تم تصفير النظام بنجاح وحذف كافة المدخلات السابقة، وأصبحت قاعدة البيانات جاهزة للتأسيس من جديد.")
        except Exception as e:
            messagebox.showerror("خطأ في النظام", f"فشل إجراء مسح البيانات بسبب خطأ التقني: {e}")

    def update_period_selector(self):
        months = set()
        for inv in self.invoices.values():
            if inv.get("التاريخ") and len(inv["التاريخ"]) >= 7:
                months.add(self.inv_period(inv))
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT archive_date FROM monthly_archive")
            for row in cursor.fetchall():
                if row[0]: months.add(row[0][:7])

        months.add(datetime.datetime.now().strftime("%Y-%m"))
        sorted_months = sorted(list(months), reverse=True)
        
        self.combo_active_period.configure(values=sorted_months)
        self.combo_active_period.set(self.current_display_month)
        self.update_period_warning()

    def on_period_changed(self, selected_period):
        self.current_display_month = selected_period
        self.recalculate_all()
        self.update_period_warning()
        # تنبيه بعد اكتمال إعادة الحساب: قد تكون هناك فترة منتهية لم يُقفل
        # خياسها، فتبقى معلّقة بلا أثر محاسبي إن لم يُنتبَه لها
        self.after(400, self.check_unclosed_previous_periods)
        if hasattr(self, 'in_date') and self.in_date:
            self.in_date.delete(0, 'end')
            self.in_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'cast_date') and self.cast_date:
            self.cast_date.delete(0, 'end')
            self.cast_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'polish_date') and self.polish_date:
            self.polish_date.delete(0, 'end')
            self.polish_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'pbuff_date') and self.pbuff_date:
            self.pbuff_date.delete(0, 'end')
            self.pbuff_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'op_date') and self.op_date:
            self.op_date.delete(0, 'end')
            self.op_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'sale_date') and self.sale_date:
            self.sale_date.delete(0, 'end')
            self.sale_date.insert(0, self.get_smart_default_date())
        if hasattr(self, 'dynamic_stage_widgets'):
            for _w in self.dynamic_stage_widgets.values():
                if _w.get("date"):
                    _w["date"].delete(0, 'end')
                    _w["date"].insert(0, self.get_smart_default_date())

    def add_new_period_ui(self):
        dialog = ctk.CTkInputDialog(text="أدخل رمز الشهر الجديد (مثال: 2026-08):", title="إضافة فترة محاسبية جديدة")
        new_p = dialog.get_input()
        if new_p:
            new_p = new_p.strip()
            if len(new_p) == 7 and new_p[4] == '-':
                self.current_display_month = new_p
                self.update_period_selector()
                self.combo_active_period.set(new_p)
                self.on_period_changed(new_p)
            else:
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة الصحيحة YYYY-MM")

    def build_opening_tab(self):
        tab = self.tabview.tab("الرصيد الافتتاحي")
        frame = ctk.CTkFrame(tab, corner_radius=12)
        frame.pack(pady=30, padx=40, fill="both", expand=True)
        lbl = ctk.CTkLabel(frame, text="⚖️ قيد افتتاحي", font=ctk.CTkFont(family="Cairo", size=22, weight="bold"), text_color="#d4af37")
        lbl.pack(pady=20)

        self.lbl_opening_status = ctk.CTkLabel(frame, text="", font=("Cairo", 15, "bold"), text_color="#2ecc71")
        self.lbl_opening_status.pack()

        name_row = ctk.CTkFrame(frame, fg_color="transparent")
        name_row.pack(pady=10)
        ctk.CTkLabel(name_row, text="الاسم:", font=("Cairo", 16, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.opening_name = ctk.CTkComboBox(name_row, values=self.get_supplier_name_values_no_mustarja(), font=("Cairo", 16), justify="right", width=250, height=42)
        self.opening_name.set("المصنع")
        self.opening_name.pack(side="right", padx=8)
        self.bind_name_autocomplete(self.opening_name, self.get_supplier_name_values_no_mustarja)

        type_row = ctk.CTkFrame(frame, fg_color="transparent")
        type_row.pack(pady=10)
        self.opening_type = ctk.CTkOptionMenu(type_row, values=["ذهب", "الماس", "فصوص وأحجار"], font=("Cairo", 15, "bold"), width=140, height=40, command=self.toggle_opening_carat_field)
        self.opening_type.set("ذهب")
        self.opening_type.pack(side="right", padx=8)
        ctk.CTkLabel(type_row, text="النوع:", font=("Cairo", 16, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        weight_row = ctk.CTkFrame(frame, fg_color="transparent")
        weight_row.pack(pady=10)
        self.lbl_opening_carat = ctk.CTkLabel(weight_row, text="العيار:", font=("Cairo", 15, "bold"))
        self.opening_carat = ctk.CTkEntry(weight_row, placeholder_text="العيار", font=("Cairo", 16), justify="center", width=100, height=40)
        self.lbl_opening_carat.pack(side="right", padx=5)
        self.opening_carat.pack(side="right", padx=8)

        self.entry_opening = ctk.CTkEntry(weight_row, placeholder_text="الوزن...", font=("Cairo", 16), justify="center", width=150, height=40)
        self.entry_opening.pack(side="right", padx=8)
        ctk.CTkLabel(weight_row, text="الوزن:", font=("Cairo", 16, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        btn = ctk.CTkButton(frame, text="تثبيت القيد الافتتاحي ⚖️", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), height=48, command=self.set_opening_balance)
        btn.pack(pady=20)

        table_top_open = ctk.CTkFrame(frame, fg_color="transparent")
        table_top_open.pack(fill="x", padx=15, pady=(10, 2))
        ctk.CTkLabel(table_top_open, text="القيود الافتتاحية المسجّلة", font=("Cairo", 16, "bold"), text_color="#d4af37").pack(side="right")

        btn_del_open = ctk.CTkButton(table_top_open, text="حذف القيد المحدد 🗑️", font=("Cairo", 14, "bold"),
                                     fg_color="#8b0000", hover_color="#a52a2a", width=165, height=32,
                                     command=self.delete_selected_opening_row)
        btn_del_open.pack(side="left", padx=5)

        btn_edit_open = ctk.CTkButton(table_top_open, text="تعديل القيد المحدد ✏️", font=("Cairo", 14, "bold"),
                                      fg_color="#b8860b", hover_color="#daa520", width=165, height=32,
                                      command=self.edit_selected_opening_row)
        btn_edit_open.pack(side="left", padx=5)

        self.opening_table_frame = ttk.Frame(frame)
        self.opening_table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))
        self.opening_tree = None

        btn_print_opening = ctk.CTkButton(frame, text="🖨️ طباعة القيود الافتتاحية", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=40, command=self.print_opening_screen)
        btn_print_opening.pack(pady=(0, 15))

        self.refresh_opening_table()

    def print_opening_screen(self):
        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18")
        col_ratios = [0.9, 1.2, 1.3, 1.2, 0.9, 0.8, 0.9]
        recs = [inv for inv in self.invoices.values()
                if inv.get("trees_count") == 1.0 and inv.get("البيان") == "قيد افتتاحي" and inv.get("settled_status") == "ACTIVE"]
        recs = sorted(recs, key=lambda x: x.get("التاريخ", ""))
        rows = []
        for inv in recs:
            carat_disp = f"{inv.get('بعد', 0):.1f}" if inv.get("بعد", 0) else "-"
            rows.append((inv["رقم الفاتورة"], inv["التاريخ"][:16], inv["الاسم"], inv["النوع"].replace("وارد ", ""),
                         f"{inv.get('قبل', inv['الوزن']):.2f}", carat_disp, f"{inv['الوزن']:.2f}"))
        self.print_generic_table_screen("🏁 القيود الافتتاحية", cols, col_ratios, rows, "opening_screen")

    def print_single_opening_operation(self, inv_id):
        """يطبع قيد افتتاحي واحد بعينه فقط (وليس كل القيود المسجّلة)"""
        inv = self.invoices.get(inv_id)
        if not inv:
            return
        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18")
        col_ratios = [0.9, 1.2, 1.3, 1.2, 0.9, 0.8, 0.9]
        carat_disp = f"{inv.get('بعد', 0):.1f}" if inv.get("بعد", 0) else "-"
        rows = [(inv["رقم الفاتورة"], inv["التاريخ"][:16], inv["الاسم"], inv["النوع"].replace("وارد ", ""),
                 f"{inv.get('قبل', inv['الوزن']):.2f}", carat_disp, f"{inv['الوزن']:.2f}")]
        self.print_generic_table_screen("🏁 قيد افتتاحي", cols, col_ratios, rows, "opening_operation")

    def toggle_opening_carat_field(self, choice):
        if choice == "ذهب":
            self.lbl_opening_carat.pack(side="right", padx=5)
            self.opening_carat.pack(side="right", padx=8)
        else:
            self.lbl_opening_carat.pack_forget()
            self.opening_carat.pack_forget()
            self.opening_carat.delete(0, 'end')

    def set_opening_balance(self):
        name = self.opening_name.get().strip()
        if not name:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم الشخص/المورد.")
            return
        op_type = self.opening_type.get()
        try:
            raw_w = round(float(self.entry_opening.get()), 2)
            if raw_w <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("خطأ", "الرجاء إدخال وزن صحيح")
            return

        if op_type == "ذهب":
            try:
                carat = round(float(self.opening_carat.get()), 2)
                if carat <= 0: raise ValueError
            except ValueError:
                messagebox.showerror("خطأ", "الرجاء إدخال عيار صحيح للذهب")
                return
            final_w = round((raw_w * carat) / 18.0, 2)
            op_invoice_type = "وارد ذهب (عيار 18)"
        else:
            carat = 0.0
            final_w = raw_w
            op_invoice_type = {"فصوص وأحجار": "وارد فصوص وأحجار", "الماس": "وارد الماس"}[op_type]

        if not messagebox.askyesno("تأكيد الترحيل", "هل أنت متأكد من ترحيل هذا القيد الافتتاحي؟"):
            return

        if name != "المصنع" and not self.check_name_exists(name):
            self.categories["الموردين"].append(name)
            self.save_name_to_db(name, "الموردين")

        self.invoice_counter += 1
        main_inv_id = self.invoice_counter
        inv_data = {
            "رقم الفاتورة": self.invoice_counter, "التاريخ": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "الاسم": name, "النوع": op_invoice_type, "الوزن": final_w, "قبل": raw_w, "بعد": carat,
            "البيان": "قيد افتتاحي", "settled_status": "ACTIVE", "trees_count": 1.0, "set_number": ""
        }
        self.invoices[self.invoice_counter] = inv_data
        self.save_invoice_to_db(self.invoice_counter, inv_data)

        self.entry_opening.delete(0, 'end')
        self.opening_carat.delete(0, 'end')
        self.opening_name.configure(values=self.get_supplier_name_values_no_mustarja())

        self.update_period_selector()
        self.recalculate_all()
        self.lbl_opening_status.configure(text=f"✅ تم ترحيل القيد الافتتاحي ({op_type}) لـ ({name})")
        self.after(2500, lambda: self.lbl_opening_status.configure(text=""))
        if messagebox.askyesno("طباعة", "هل تريد طباعة العملية؟"):
            self.print_single_opening_operation(main_inv_id)
        self.refresh_opening_table()

    def refresh_opening_table(self):
        if not hasattr(self, 'opening_table_frame') or not self.opening_table_frame:
            return
        for widget in self.opening_table_frame.winfo_children():
            widget.destroy()

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18")
        self.opening_tree = self.create_standard_treeview(self.opening_table_frame, cols, height=8)
        self.opening_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 170 if c == "الاسم" else 140 if c == "التاريخ" else 100
            self.opening_tree.column(c, width=w, anchor="center")

        recs = [inv for inv in self.invoices.values()
                if inv.get("trees_count") == 1.0 and inv.get("البيان") == "قيد افتتاحي" and inv.get("settled_status") == "ACTIVE"]
        recs = sorted(recs, key=lambda x: x.get("التاريخ", ""))
        tot_18 = 0.0
        for inv in recs:
            carat_disp = f"{inv.get('بعد', 0):.1f}" if inv.get("بعد", 0) else "-"
            if inv.get("النوع") == "وارد ذهب (عيار 18)":
                tot_18 += inv["الوزن"]
            self.opening_tree.insert("", "end", iid=str(inv["رقم الفاتورة"]), values=(
                inv["رقم الفاتورة"], inv["التاريخ"], inv["الاسم"], inv["النوع"].replace("وارد ", ""),
                f"{inv.get('قبل', inv['الوزن']):.2f}", carat_disp, f"{inv['الوزن']:.2f}"
            ))

        if recs:
            self.opening_tree.insert("", "end", iid="total_opening",
                                     values=("-", "-", "-", "إجمالي الذهب (عيار 18)", "-", "-", f"{tot_18:.2f}"),
                                     tags=("total_tag",))

        self.opening_tree.bind("<Double-1>", lambda e: self.edit_selected_opening_row())

    def get_selected_opening_invoice(self, action="تعديل"):
        """يرجع الحركة المحددة في جدول القيود الافتتاحية، أو None مع رسالة مناسبة"""
        if not (hasattr(self, 'opening_tree') and self.opening_tree):
            return None
        sel = self.opening_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", f"الرجاء تحديد القيد الافتتاحي المراد {action}ه أولاً.")
            return None
        raw = sel[0]
        if raw == "total_opening" or not str(raw).isdigit():
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للتعديل أو الحذف (قيمة إجمالية وليست قيداً مستقلاً).")
            return None
        inv = self.invoices.get(int(raw))
        if not inv:
            messagebox.showwarning("تنبيه", "القيد المحدد لم يعد موجوداً. حدّث الشاشة وحاول مجدداً.")
            return None
        return inv

    def delete_selected_opening_row(self):
        """حذف قيد افتتاحي محدد مع إعادة حساب الخزينة وكل الأرصدة المرتبطة فوراً"""
        inv = self.get_selected_opening_invoice("حذف")
        if not inv:
            return
        inv_id = inv["رقم الفاتورة"]
        if not messagebox.askyesno(
                "تأكيد الحذف",
                f"هل أنت متأكد من حذف القيد الافتتاحي رقم ({inv_id})؟\n"
                f"الاسم: {inv['الاسم']} — الوزن (عيار 18): {inv['الوزن']:.2f} جم\n\n"
                "سيتم إعادة حساب رصيد الخزينة وكل الأرصدة المرتبطة تلقائياً."):
            return
        if not self.delete_invoice_from_db(inv_id):
            return  # تم المنع (رسالة ظهرت بالفعل)
        self.update_period_selector()
        self.recalculate_all()
        self.refresh_opening_table()
        self.lbl_opening_status.configure(text="🗑️ تم حذف القيد الافتتاحي وتحديث كل الأرصدة")
        self.after(3000, lambda: self.lbl_opening_status.configure(text=""))

    def edit_selected_opening_row(self):
        """تعديل قيد افتتاحي محدد (الاسم/النوع/الوزن/العيار) مع إعادة احتساب وزن العيار ١٨ وكل أرصدة النظام"""
        if not self.check_edit_permission():
            return
        inv = self.get_selected_opening_invoice("تعديل")
        if not inv:
            return
        inv_id = inv["رقم الفاتورة"]
        type_map = {"وارد ذهب (عيار 18)": "ذهب", "وارد فصوص وأحجار": "فصوص وأحجار", "وارد الماس": "الماس"}
        inv_type_map = {v: k for k, v in type_map.items()}
        cur_type = type_map.get(inv.get("النوع"), "ذهب")

        win = ctk.CTkToplevel(self)
        win.title("تعديل القيد الافتتاحي")
        win.geometry("520x470")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"✏️ تعديل القيد الافتتاحي رقم ({inv_id})", font=("Cairo", 17, "bold"), text_color="#d4af37").pack(pady=12)

        frm = ctk.CTkFrame(win)
        frm.pack(fill="x", padx=20, pady=8)

        ctk.CTkLabel(frm, text="التاريخ:", font=("Cairo", 14, "bold")).grid(row=0, column=1, padx=10, pady=8, sticky="e")
        ent_date = ctk.CTkEntry(frm, justify="center", width=190)
        ent_date.insert(0, inv.get("التاريخ", ""))
        ent_date.grid(row=0, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="الاسم:", font=("Cairo", 14, "bold")).grid(row=1, column=1, padx=10, pady=8, sticky="e")
        cmb_name = ctk.CTkComboBox(frm, values=self.get_supplier_name_values_no_mustarja(), justify="right", width=190)
        cmb_name.set(inv.get("الاسم", "المصنع"))
        cmb_name.grid(row=1, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="النوع:", font=("Cairo", 14, "bold")).grid(row=2, column=1, padx=10, pady=8, sticky="e")
        opt_type = ctk.CTkOptionMenu(frm, values=["ذهب", "الماس", "فصوص وأحجار"], width=190)
        opt_type.set(cur_type)
        opt_type.grid(row=2, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="الوزن:", font=("Cairo", 14, "bold")).grid(row=3, column=1, padx=10, pady=8, sticky="e")
        ent_w = ctk.CTkEntry(frm, justify="center", width=190)
        ent_w.insert(0, f"{inv.get('قبل', inv['الوزن']) or inv['الوزن']:g}")
        ent_w.grid(row=3, column=0, padx=10, pady=8)

        ctk.CTkLabel(frm, text="العيار (للذهب فقط):", font=("Cairo", 14, "bold")).grid(row=4, column=1, padx=10, pady=8, sticky="e")
        ent_carat = ctk.CTkEntry(frm, justify="center", width=190)
        ent_carat.insert(0, f"{inv.get('بعد', 0):g}" if inv.get("بعد", 0) else "")
        ent_carat.grid(row=4, column=0, padx=10, pady=8)

        lbl_preview = ctk.CTkLabel(win, text="", font=("Cairo", 14, "bold"), text_color="#1f77b4")
        lbl_preview.pack(pady=(4, 0))

        def preview(event=None):
            try:
                w = float(ent_w.get().strip() or 0)
                if opt_type.get() == "ذهب":
                    c = float(ent_carat.get().strip() or 0)
                    lbl_preview.configure(text=f"الوزن المعادل عيار ١٨ = {round(w * c / 18.0, 2):.2f} جم")
                else:
                    lbl_preview.configure(text=f"الوزن المعتمد = {round(w, 2):.2f}")
            except ValueError:
                lbl_preview.configure(text="")

        ent_w.bind("<KeyRelease>", preview)
        ent_carat.bind("<KeyRelease>", preview)
        preview()

        def save_opening_edit():
            new_date = ent_date.get().strip()
            if len(new_date) < 10 or new_date[4] != '-':
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة الصحيحة YYYY-MM-DD.", parent=win)
                return
            new_name = cmb_name.get().strip()
            if not new_name:
                messagebox.showerror("خطأ", "الرجاء إدخال الاسم.", parent=win)
                return
            new_type = opt_type.get()
            try:
                raw_w = round(float(ent_w.get().strip()), 2)
                if raw_w <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("خطأ", "الرجاء إدخال وزن صحيح أكبر من صفر.", parent=win)
                return

            if new_type == "ذهب":
                try:
                    carat = round(float(ent_carat.get().strip()), 2)
                    if carat <= 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("خطأ", "الرجاء إدخال عيار صحيح للذهب.", parent=win)
                    return
                final_w = round((raw_w * carat) / 18.0, 2)
            else:
                carat = 0.0
                final_w = raw_w

            if new_name != "المصنع" and not self.check_name_exists(new_name):
                self.categories["الموردين"].append(new_name)
                self.save_name_to_db(new_name, "الموردين")

            updated = dict(inv)
            updated["التاريخ"] = new_date if len(new_date) > 10 else f"{new_date} {inv.get('التاريخ', '')[11:] or '00:00:00'}"
            updated["الاسم"] = new_name
            updated["النوع"] = inv_type_map[new_type]
            updated["قبل"] = raw_w
            updated["بعد"] = carat
            updated["الوزن"] = final_w
            updated["البيان"] = "قيد افتتاحي"
            updated["trees_count"] = 1.0

            if not self.save_invoice_to_db(inv_id, updated):
                return  # تم المنع (رسالة ظهرت بالفعل)
            self.invoices[inv_id] = updated

            # إعادة حساب شاملة لكل النظام بعد التعديل (الخزينة، الأرصدة، الكشوف، التقارير)
            self.update_period_selector()
            self.recalculate_all()
            self.refresh_opening_table()
            win.destroy()
            self.lbl_opening_status.configure(text="✅ تم تعديل القيد الافتتاحي وتحديث كل أرصدة النظام")
            self.after(3000, lambda: self.lbl_opening_status.configure(text=""))
            messagebox.showinfo("تم", "تم تعديل القيد الافتتاحي وإعادة حساب الخزينة وكل الأرصدة المرتبطة.")

        btn_save_open = ctk.CTkButton(win, text="حفظ التعديلات 💾", font=("Cairo", 16, "bold"), fg_color="#2ecc71",
                                      hover_color="#27ae60", height=42, command=save_opening_edit)
        btn_save_open.pack(pady=16)
        self.apply_edit_lock_to_button(btn_save_open, win)

    # =========================================================================
    # --- مراحل التصنيع: الكاستنج / المصنعين / المركبين / التلميع ---
    # =========================================================================
    def build_operations_tab(self):
        tab = self.tabview.tab("مراحل التصنيع")
        self.operations_tab_ref = tab
        self.dynamic_stage_containers = {}

        lbl_info = ctk.CTkLabel(tab, text=f"مراحل التصنيع: {self.get_display_label('الكاستنج')} - {self.get_display_label('المصنعين')} - {self.get_display_label('المركبين')} - {self.get_display_label('التلميع')} - {self.get_display_label('التلميع/البف')}", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"))
        lbl_info.pack(pady=(8, 2))

        self.lbl_op_status = ctk.CTkLabel(tab, text="", font=("Cairo", 16, "bold"), text_color="#2ecc71")
        self.lbl_op_status.pack()

        # ====== شريط التنقل بين المراحل الأربعة ======
        self.stage_bar = ctk.CTkFrame(tab, fg_color="transparent")
        self.stage_bar.pack(fill="x", padx=25, pady=(6, 6))

        ctk.CTkLabel(self.stage_bar, text="اختر المرحلة:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=8)

        self.current_op_cat = "المصنعين"
        self.stage_buttons = {}
        self.refresh_stage_buttons()

        # ====== حاوية شاشتي المصنعين والمركبين (تستخدم نفس الآلية الموحدة الحالية) ======
        self.mfg_inst_container = ctk.CTkFrame(tab, fg_color="transparent")

        sel_frame = ctk.CTkFrame(self.mfg_inst_container, fg_color="transparent")
        sel_frame.pack(pady=(6, 4))

        self.op_date = ctk.CTkEntry(sel_frame, font=("Cairo", 15), justify="center", width=130, height=38)
        self.op_date.insert(0, self.get_smart_default_date())
        self.op_date.pack(side="right", padx=8)

        ctk.CTkLabel(sel_frame, text="اختر الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=8)

        self.combo_op_name = ctk.CTkComboBox(sel_frame, values=["لا يوجد أسماء"], font=("Cairo", 15), width=200, height=38, justify="right", command=self.render_unified_fields)
        self.combo_op_name.pack(side="right", padx=8)

        # صف مضغوط واحد يحوي كل حقول العملية المختارة جنباً إلى جنب
        self.unified_inputs_frame = ctk.CTkFrame(self.mfg_inst_container)
        self.unified_inputs_frame.pack(pady=(4, 4), fill="x", padx=25)

        bottom_entry_frame = ctk.CTkFrame(self.mfg_inst_container, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=25, pady=(0, 8))

        self.op_note = ctk.CTkEntry(bottom_entry_frame, placeholder_text="البيان / الملاحظات...", font=("Cairo", 15), justify="right", width=420, height=38)
        self.op_note.pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(bottom_entry_frame, text="ترحيل الحركة 💾", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=190, command=self.submit_unified_op)
        btn_submit.pack(side="right", padx=8)

        # ------------------ كشف حركة العامل/المكينة المحددة أعلاه (مباشر ومتزامن) ------------------
        ledger_header = ctk.CTkFrame(self.mfg_inst_container, fg_color="transparent")
        ledger_header.pack(fill="x", padx=25, pady=(8, 2))

        self.lbl_op_ledger_title = ctk.CTkLabel(ledger_header, text="كشف حركة العامل المحدد", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37")
        self.lbl_op_ledger_title.pack(side="right")

        btn_del_row = ctk.CTkButton(ledger_header, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.op_ledger_delete_selected)
        btn_del_row.pack(side="left", padx=5)

        # زر التلوين لقسمي المصنعين والمركبين: يتبع القسم المعروض حالياً،
        # وإعداده محفوظ لكل قسم على حدة
        self.btn_ledger_neg_color = ctk.CTkButton(
            ledger_header, text="⚪ لون واحد", font=("Cairo", 12, "bold"), width=105, height=28,
            fg_color="#555555", hover_color="#333333",
            command=lambda: self.toggle_negative_color(self.current_op_cat, self.refresh_op_ledger_table))
        self.btn_ledger_neg_color.pack(side="left", padx=5)

        if not hasattr(self, "neg_color_buttons"):
            self.neg_color_buttons = {}
        for _c in ("المصنعين", "المركبين", "الآلة/المكائن"):
            self.neg_color_buttons[_c] = self.btn_ledger_neg_color

        ctk.CTkButton(ledger_header, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.op_ledger_tree, f"عرض كامل — {self.clean_name(self.combo_op_name.get())}",
                          name_tree=self.op_ledger_name_tree)
                      ).pack(side="left", padx=5)

        btn_edit_row = ctk.CTkButton(ledger_header, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.op_ledger_edit_selected)
        btn_edit_row.pack(side="left", padx=5)

        self.op_ledger_table_frame = ttk.Frame(self.mfg_inst_container)
        self.op_ledger_table_frame.pack(fill="both", expand=True, padx=25, pady=(0, 4))
        self.op_ledger_tree = None
        self.op_ledger_group_map = {}

        self.lbl_op_ledger_totals = ctk.CTkLabel(self.mfg_inst_container, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        self.lbl_op_ledger_totals.pack(fill="x", padx=25, pady=(0, 10))

        # ====== حاوية شاشة الكاستنج الجديدة (تاريخ / اسم / صرف / قبض / بيان + جدول حركة) ======
        self.casting_container = ctk.CTkFrame(tab, fg_color="transparent")
        self.build_casting_ui(self.casting_container)

        # ====== حاوية شاشة التلميع الجديدة (تاريخ / اسم / صرف / بيان + جدول حركة) ======
        self.polish_container = ctk.CTkFrame(tab, fg_color="transparent")
        self.build_polish_ui(self.polish_container)

        # ====== حاوية شاشة التلميع/البف الجديدة (تاريخ / الخياس + جدول مدين-دائن-رصيد) ======
        self.polish_buff_container = ctk.CTkFrame(tab, fg_color="transparent")
        self.build_polish_buff_ui(self.polish_buff_container)

        # المرحلة الافتراضية عند فتح الشاشة
        self.switch_op_stage("الكاستنج")

    def refresh_stage_buttons(self):
        """يعيد بناء أزرار المراحل بأعلى شاشة مراحل التصنيع، متضمّناً أي قسم أُضيف ديناميكياً من شجرة الحسابات"""
        for btn in self.stage_buttons.values():
            btn.destroy()
        self.stage_buttons = {}

        stage_defs = [
            ("الكاستنج", f"🏗️ {self.get_display_label('الكاستنج')}"),
            ("المصنعين", f"🏭 {self.get_display_label('المصنعين')}"),
            ("المركبين", f"🔧 {self.get_display_label('المركبين')}"),
            ("التلميع", f"✨ {self.get_display_label('التلميع')}"),
            ("التلميع/البف", f"🪄 {self.get_display_label('التلميع/البف')}"),
        ]
        for stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            stage_defs.append((stage_name, f"➕ {stage_name}"))

        # ترتيب الأقسام كما رتّبه المستخدم (محفوظ ويبقى بعد الإغلاق)
        labels = dict(stage_defs)
        stage_defs = [(k, labels[k]) for k in self.stage_order(list(labels.keys()))]

        for key, label in stage_defs:
            b = ctk.CTkButton(self.stage_bar, text=label, font=("Cairo", 15, "bold"), height=38, width=140,
                               command=lambda k=key: self.switch_op_stage(k))
            b.pack(side="right", padx=5)
            # الزر الأيمن: تحريك القسم يميناً أو يساراً في الشريط
            b.bind("<Button-3>", lambda e, k=key: self.show_stage_context_menu(e, k), add="+")
            self.stage_buttons[key] = b

    def stage_order(self, available):
        """ترتيب أقسام مراحل التصنيع: المحفوظ إن وُجد، مع إصلاحه تلقائياً"""
        try:
            saved = json.loads(self.get_setting("stage_order", "") or "[]")
        except Exception:
            saved = []
        order = [k for k in saved if k in available]
        order += [k for k in available if k not in order]
        return order

    def move_stage(self, key, direction):
        """يحرّك قسماً في شريط المراحل (‎-1 لليمين، ‎+1 لليسار)"""
        keys = list(self.stage_buttons.keys())
        order = self.stage_order(keys)
        if key not in order:
            return
        i = order.index(key)
        j = i + direction
        if not (0 <= j < len(order)):
            return
        order[i], order[j] = order[j], order[i]
        try:
            self.set_setting("stage_order", json.dumps(order, ensure_ascii=False))
        except Exception as e:
            log_cloud_error("تعذّر حفظ ترتيب الأقسام", e)
        self.refresh_stage_buttons()

    def show_stage_context_menu(self, event, key):
        """قائمة الزر الأيمن على قسم في شريط مراحل التصنيع"""
        menu = tk.Menu(self, tearoff=0)
        # الشريط مرصوف من اليمين لليسار: ‎-1 يقرّب القسم من اليمين
        menu.add_command(label="⏩ تحريك لليمين", command=lambda: self.move_stage(key, -1))
        menu.add_command(label="⏪ تحريك لليسار", command=lambda: self.move_stage(key, 1))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def switch_op_stage(self, stage):
        """التبديل بين مراحل التصنيع وإظهار الشاشة الخاصة بكل مرحلة (تشمل أي قسم أُضيف ديناميكياً)"""
        self.current_op_stage = stage
        for key, btn in self.stage_buttons.items():
            btn.configure(fg_color="#144d75" if key == stage else "#1f77b4")

        self.mfg_inst_container.pack_forget()
        self.casting_container.pack_forget()
        self.polish_container.pack_forget()
        self.polish_buff_container.pack_forget()
        if hasattr(self, 'dynamic_stage_containers'):
            for cont in self.dynamic_stage_containers.values():
                cont.pack_forget()

        if stage == "الكاستنج":
            self.casting_container.pack(fill="both", expand=True)
            self.refresh_casting_table()
        elif stage == "التلميع":
            self.polish_container.pack(fill="both", expand=True)
            self.refresh_polish_table()
        elif stage == "التلميع/البف":
            self.polish_buff_container.pack(fill="both", expand=True)
            self.refresh_polish_buff_table()
        elif stage == "المصنعين" or stage == "المركبين":
            self.current_op_cat = stage
            self.mfg_inst_container.pack(fill="both", expand=True)
            self.update_op_names(stage)
        elif stage in self.categories.get("أقسام_خياس_إضافية", []):
            if not hasattr(self, 'dynamic_stage_containers'):
                self.dynamic_stage_containers = {}
            if stage not in self.dynamic_stage_containers:
                cont = ctk.CTkFrame(self.operations_tab_ref, fg_color="transparent")
                self.build_generic_stage_ui(cont, stage)
                self.dynamic_stage_containers[stage] = cont
            self.dynamic_stage_containers[stage].pack(fill="both", expand=True)
            self.refresh_generic_stage_table(stage)

    @staticmethod
    def clean_name(text):
        """يزيل علامات الاتجاه من الاسم قبل استخدامه في الحفظ أو المطابقة.

        ضروري: القوائم تعرض الأسماء بعلامة RLM لتثبيت اتجاهها، ولو حُفظت
        العلامة مع الاسم لاختلف عن الاسم المسجّل في شجرة الحسابات فانفصلت
        حركاته عنه.
        """
        return str(text or "").replace("\u200f", "").replace("\u200e", "").strip()

    @staticmethod
    def rtl(text):
        """يثبّت اتجاه الاسم العربي من اليمين لليسار داخل القوائم.

        بدون هذا كان الاسم المركّب يُعرض بترتيب معكوس («محمد علي» ← «علي محمد»)،
        لأن مُحرّك النص يخمّن اتجاه السطر من أول حرف قابل للاتجاه. علامة RLM
        في البداية تحسم الاتجاه فتبقى الكلمات بترتيبها الصحيح.
        """
        text = str(text or "")
        return ("\u200f" + text) if text else text

    def get_stage_name_values(self, default_name, own_category=None):
        """قائمة أسماء الكاستنج/التلميع: الاسم التلقائي + جميع أسماء المصنعين والمركبين + أسماء القسم نفسه"""
        values = [default_name]
        values += self.categories.get("المصنعين", [])
        values += self.categories.get("المركبين", [])
        if own_category:
            values += [n for n in self.categories.get(own_category, []) if n not in values]
        # نعرضها باتجاه مثبّت، والقيمة المقروءة تُنظَّف عند الاستخدام
        return [self.rtl(v) for v in values]

    # ---------------------------------------------------------------
    # ------------------------- شاشة الكاستنج -------------------------
    # ---------------------------------------------------------------
    # =========================================================================
    # --- نظام صرف/قبض عام لأي "صندوق خياس" يُضاف ديناميكياً من شجرة الحسابات (مطابق لنمط الكاستنج) ---
    # =========================================================================
    def build_generic_stage_ui(self, parent, stage_name):
        """يبني واجهة صرف/قبض كاملة لأي قسم مضاف ديناميكياً، مطابقة لبنية شاشة الكاستنج"""
        if not hasattr(self, 'dynamic_stage_widgets'):
            self.dynamic_stage_widgets = {}
        w = {}

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(pady=(6, 4), padx=25)

        w["date"] = ctk.CTkEntry(top, font=("Cairo", 15), justify="center", width=130, height=38)
        w["date"].insert(0, self.get_smart_default_date())
        w["date"].pack(side="right", padx=8)
        ctk.CTkLabel(top, text="التاريخ:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top, text="الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        # لا خانة اسم في هذه الأقسام: الاسم هو اسم القسم نفسه دائماً،
        # ويُملأ تلقائياً عند الترحيل بلا تدخّل من المستخدم
        w["name"] = None

        fields_row = ctk.CTkFrame(parent)
        fields_row.pack(pady=(4, 4), fill="x", padx=25)

        col_row_num = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_row_num.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_row_num, text="رقم الصف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        w["row_num"] = ctk.CTkEntry(col_row_num, justify="center", font=("Cairo", 15), width=100, height=34)
        w["row_num"].pack()

        col_sarf = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_sarf.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_sarf, text="الصرف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        w["sarf"] = ctk.CTkEntry(col_sarf, justify="center", font=("Cairo", 15), width=100, height=34)
        w["sarf"].pack()

        col_qabd = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_qabd.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_qabd, text="القبض", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        w["qabd"] = ctk.CTkEntry(col_qabd, justify="center", font=("Cairo", 15), width=100, height=34)
        w["qabd"].pack()

        bottom_entry_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=25, pady=(0, 8))

        w["note"] = ctk.CTkEntry(bottom_entry_frame, placeholder_text="البيان / الملاحظات...", font=("Cairo", 15), justify="right", width=420, height=38)
        w["note"].pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(bottom_entry_frame, text=f"ترحيل حركة {stage_name} 💾", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=210, command=lambda: self.submit_generic_stage_op(stage_name))
        btn_submit.pack(side="right", padx=8)

        nav_fields = [w["row_num"], w["sarf"], w["qabd"], w["note"]]
        self.bind_arrow_navigation(nav_fields)
        for i, f in enumerate(nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_fields[i + 1]: nxt.focus_set() or "break")
        # Enter في آخر خانة يرحّل العملية مباشرة (مع إشعار التأكيد كالمعتاد)
        nav_fields[-1].bind("<Return>", lambda e, s=stage_name: (self.submit_generic_stage_op(s), "break")[1])

        table_top = ctk.CTkFrame(parent, fg_color="transparent")
        table_top.pack(fill="x", padx=25, pady=(8, 2))

        ctk.CTkLabel(table_top, text=f"كشف حركة {stage_name}", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37").pack(side="right")

        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=lambda: self.delete_selected_generic_stage_row(stage_name))
        btn_del.pack(side="left", padx=5)

        self.build_negative_color_button(
            table_top, stage_name, lambda s=stage_name: self.refresh_generic_stage_table(s))

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda s=stage_name: self.view_treeview_fullscreen(
                          self.dynamic_stage_widgets.get(s, {}).get("tree"), f"عرض كامل — {s}")
                      ).pack(side="left", padx=5)

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=lambda: self.edit_selected_generic_stage_row(stage_name))
        btn_edit.pack(side="left", padx=5)

        w["table_frame"] = ttk.Frame(parent)
        w["table_frame"].pack(fill="both", expand=True, padx=25, pady=(0, 4))
        w["tree"] = None
        w["table_rows_map"] = {}

        w["totals_lbl"] = ctk.CTkLabel(parent, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        w["totals_lbl"].pack(fill="x", padx=25, pady=(0, 10))

        self.dynamic_stage_widgets[stage_name] = w

    def submit_generic_stage_op(self, stage_name):
        w = self.dynamic_stage_widgets[stage_name]
        madin_type, qabd_type, mustarja_name = self.get_stage_config(stage_name)
        date_val = w["date"].get().strip()
        name = stage_name
        note = w["note"].get().strip()
        row_num = w["row_num"].get().strip()
        if not date_val:
            messagebox.showwarning("تنبيه", "الرجاء إدخال التاريخ.")
            return
        if not row_num:
            messagebox.showwarning("رقم الصف مطلوب", "لازم تسجل رقم الصف أولاً قبل ترحيل أي عملية.")
            return

        try:
            sarf_v = round(float(w["sarf"].get().strip()), 2) if w["sarf"].get().strip() else 0.0
        except ValueError:
            sarf_v = 0.0
        try:
            qabd_v = round(float(w["qabd"].get().strip()), 2) if w["qabd"].get().strip() else 0.0
        except ValueError:
            qabd_v = 0.0

        if sarf_v <= 0 and qabd_v <= 0:
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة الصرف أو القبض أولاً.")
            return

        skipped = []
        if sarf_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == madin_type for inv in self.invoices.values()):
            skipped.append("الصرف")
            sarf_v = 0.0
        if qabd_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == qabd_type for inv in self.invoices.values()):
            skipped.append("القبض")
            qabd_v = 0.0
        if skipped and not messagebox.askyesno("عملية مكررة", "تم تجاهل: " + "، ".join(skipped) + f" لأنها مسجلة بالفعل بنفس رقم الصف ({row_num}).\nهل تريد المتابعة بباقي القيم المُدخلة (إن وُجدت)؟"):
            return
        if sarf_v <= 0 and qabd_v <= 0:
            return

        if not messagebox.askyesno("تأكيد الترحيل", f"هل أنت متأكد من ترحيل حركة {stage_name}؟"):
            return

        if name != stage_name and not self.check_name_exists(name):
            self.categories.setdefault(stage_name, []).append(name)
            self.save_name_to_db(name, stage_name)

        full_date_time = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        saved_any = False

        if sarf_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": madin_type, "الوزن": sarf_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if qabd_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": qabd_type, "الوزن": qabd_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if saved_any:
            self.register_operation_period(date_val)
            self.recalculate_all()

            w["sarf"].delete(0, 'end')
            w["qabd"].delete(0, 'end')
            w["note"].delete(0, 'end')
            w["row_num"].delete(0, 'end')


            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة {stage_name} لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.refresh_generic_stage_table(stage_name)
            # التركيز يعود لرقم الصف لبدء العملية التالية مباشرة.
            # يُؤجَّل بعد إعادة رسم الجدول لأن الرسم يسحب التركيز.
            self.after(60, lambda w=w: w["row_num"].focus_set())

    def refresh_generic_stage_table(self, stage_name):
        if not hasattr(self, 'dynamic_stage_widgets') or stage_name not in self.dynamic_stage_widgets:
            return
        w = self.dynamic_stage_widgets[stage_name]
        if not w.get("table_frame"):
            return
        madin_type, qabd_type, mustarja_name = self.get_stage_config(stage_name)

        tree, rows_map = self.render_stage_ops_table(
            w["table_frame"], madin_type, qabd_type, height=10, section=stage_name, show_name=False,
            on_refresh=lambda s=stage_name: self.refresh_generic_stage_table(s),
            on_detail=lambda s=stage_name: self.show_selected_stage_details(
                self.dynamic_stage_widgets[s]["tree"],
                self.dynamic_stage_widgets[s]["table_rows_map"], f"تفاصيل حركة {s}"),
            on_edit=lambda s=stage_name: self.edit_selected_generic_stage_row(s),
            totals_label=w.get("totals_lbl"))
        w["tree"] = tree
        w["table_rows_map"] = rows_map

    def delete_selected_generic_stage_row(self, stage_name):
        w = self.dynamic_stage_widgets.get(stage_name)
        if not w or not w.get("tree"):
            return
        sel = w["tree"].selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها أولاً.")
            return
        if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف حركة {stage_name} المحددة؟"):
            return
        inv_ids = w["table_rows_map"].get(sel[0], [])
        any_blocked = False
        for inv_id in list(inv_ids):
            if inv_id in self.invoices:
                if not self.delete_invoice_from_db(inv_id):
                    any_blocked = True
                    break
        if any_blocked:
            return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
        self.recalculate_all()
        self.lbl_op_status.configure(text=f"🗑️ تم حذف حركة {stage_name} وتحديث الأرصدة")
        self.after(2500, lambda: self.lbl_op_status.configure(text=""))

    def edit_selected_generic_stage_row(self, stage_name):
        """تعديل حركة محددة في أي قسم أُضيف ديناميكياً (نفس نافذة التعديل الموحّدة)"""
        w = self.dynamic_stage_widgets.get(stage_name) if hasattr(self, 'dynamic_stage_widgets') else None
        if not w or not w.get("tree"):
            return
        sel = w["tree"].selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها من الجدول أولاً.")
            return
        ids = w["table_rows_map"].get(sel[0])
        if not ids:
            return
        madin_type, qabd_type, _ = self.get_stage_config(stage_name)
        self.open_stage_op_edit_dialog(ids, madin_type, qabd_type, f"تعديل حركة {stage_name}",
                                       status_text=f"✏️ تم تعديل حركة {stage_name}")

    def build_casting_ui(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(pady=(6, 4), padx=25)

        self.cast_date = ctk.CTkEntry(top, font=("Cairo", 15), justify="center", width=130, height=38)
        self.cast_date.insert(0, self.get_smart_default_date())
        self.cast_date.pack(side="right", padx=8)
        ctk.CTkLabel(top, text="التاريخ:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top, text="الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.cast_name = ctk.CTkComboBox(top, values=self.get_stage_name_values("كاستنج", "الكاستنج"), font=("Cairo", 15), width=200, height=38, justify="right")
        self.cast_name.pack(side="right", padx=8)
        self.cast_name.set("")
        self.bind_name_autocomplete(self.cast_name, lambda: self.get_stage_name_values("كاستنج", "الكاستنج"))

        fields_row = ctk.CTkFrame(parent)
        fields_row.pack(pady=(4, 4), fill="x", padx=25)

        col_row_num = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_row_num.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_row_num, text="رقم الصف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.cast_row_num = ctk.CTkEntry(col_row_num, justify="center", font=("Cairo", 15), width=100, height=34)
        self.cast_row_num.pack()

        col_sarf = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_sarf.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_sarf, text="الصرف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.cast_sarf = ctk.CTkEntry(col_sarf, justify="center", font=("Cairo", 15), width=100, height=34)
        self.cast_sarf.pack()

        col_qabd = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_qabd.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_qabd, text="القبض", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.cast_qabd = ctk.CTkEntry(col_qabd, justify="center", font=("Cairo", 15), width=100, height=34)
        self.cast_qabd.pack()

        col_trees = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_trees.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_trees, text="عدد الأشجار", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.cast_trees = ctk.CTkEntry(col_trees, justify="center", font=("Cairo", 15), width=100, height=34)
        self.cast_trees.pack()

        bottom_entry_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=25, pady=(0, 8))

        self.cast_note = ctk.CTkEntry(bottom_entry_frame, placeholder_text="البيان / الملاحظات...", font=("Cairo", 15), justify="right", width=420, height=38)
        self.cast_note.pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(bottom_entry_frame, text="ترحيل حركة الكاستنج 💾", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=210, command=self.submit_casting_op)
        btn_submit.pack(side="right", padx=8)

        cast_nav_fields = [self.cast_name, self.cast_row_num, self.cast_sarf, self.cast_qabd, self.cast_trees, self.cast_note]
        self.bind_arrow_navigation(cast_nav_fields)
        for i, f in enumerate(cast_nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=cast_nav_fields[i + 1]: nxt.focus_set() or "break")
        cast_nav_fields[-1].bind("<Return>", lambda e: (self.submit_casting_op(), "break")[1])

        table_top = ctk.CTkFrame(parent, fg_color="transparent")
        table_top.pack(fill="x", padx=25, pady=(8, 2))

        ctk.CTkLabel(table_top, text="كشف حركة الكاستنج", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37").pack(side="right")

        btn_del_cast = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_casting_row)
        btn_del_cast.pack(side="left", padx=5)

        self.build_negative_color_button(table_top, "الكاستنج", self.refresh_casting_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.cast_tree, f"عرض كامل — {self.get_display_label('الكاستنج')}")
                      ).pack(side="left", padx=5)

        btn_edit_cast = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_casting_row)
        btn_edit_cast.pack(side="left", padx=5)

        self.cast_table_frame = ttk.Frame(parent)
        self.cast_table_frame.pack(fill="both", expand=True, padx=25, pady=(0, 4))
        self.cast_tree = None
        self.cast_table_rows_map = {}

        self.cast_totals_lbl = ctk.CTkLabel(parent, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        self.cast_totals_lbl.pack(fill="x", padx=25, pady=(0, 10))

    def submit_casting_op(self):
        date_val = self.cast_date.get().strip()
        name = self.clean_name(self.cast_name.get()) or "كاستنج"
        note = self.cast_note.get().strip()
        row_num = self.cast_row_num.get().strip()
        if not date_val:
            messagebox.showwarning("تنبيه", "الرجاء إدخال التاريخ.")
            return
        if not row_num:
            messagebox.showwarning("رقم الصف مطلوب", "لازم تسجل رقم الصف أولاً قبل ترحيل أي عملية.")
            return

        try:
            sarf_v = round(float(self.cast_sarf.get().strip()), 2) if self.cast_sarf.get().strip() else 0.0
        except ValueError:
            sarf_v = 0.0
        try:
            qabd_v = round(float(self.cast_qabd.get().strip()), 2) if self.cast_qabd.get().strip() else 0.0
        except ValueError:
            qabd_v = 0.0
        try:
            trees_v = round(float(self.cast_trees.get().strip()), 2) if self.cast_trees.get().strip() else 0.0
        except ValueError:
            trees_v = 0.0
        if trees_v < 0:
            messagebox.showwarning("تنبيه", "عدد الأشجار لا يمكن أن يكون بالسالب.")
            return

        if sarf_v <= 0 and qabd_v <= 0:
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة الصرف أو القبض أولاً.")
            return

        skipped = []
        if sarf_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "صرف كاستنج" for inv in self.invoices.values()):
            skipped.append("الصرف")
            sarf_v = 0.0
        if qabd_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "قبض كاستنج" for inv in self.invoices.values()):
            skipped.append("القبض")
            qabd_v = 0.0
        if skipped and not messagebox.askyesno("عملية مكررة", "تم تجاهل: " + "، ".join(skipped) + f" لأنها مسجلة بالفعل بنفس رقم الصف ({row_num}).\nهل تريد المتابعة بباقي القيم المُدخلة (إن وُجدت)؟"):
            return

        if sarf_v <= 0 and qabd_v <= 0:
            return

        if not messagebox.askyesno("تأكيد الترحيل", "هل أنت متأكد من ترحيل حركة الكاستنج؟"):
            return

        if name != "كاستنج" and not self.check_name_exists(name):
            self.categories["الكاستنج"].append(name)
            self.save_name_to_db(name, "الكاستنج")

        full_date_time = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        saved_any = False

        if sarf_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": "صرف كاستنج", "الوزن": sarf_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": trees_v, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if qabd_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": "قبض كاستنج", "الوزن": qabd_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": trees_v, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if saved_any:
            self.register_operation_period(date_val)
            self.recalculate_all()

            self.cast_sarf.delete(0, 'end')
            self.cast_qabd.delete(0, 'end')
            self.cast_trees.delete(0, 'end')
            self.cast_note.delete(0, 'end')
            self.cast_row_num.delete(0, 'end')
            # التركيز يعود لرقم الصف مباشرة ليبدأ تسجيل العملية التالية بلا نقر
            self.cast_row_num.focus_set()
            self.cast_name.configure(values=self.get_stage_name_values("كاستنج", "الكاستنج"))
            self.cast_name.set("")

            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة الكاستنج لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.refresh_casting_table()
            # التركيز يعود لرقم الصف لتسجيل العملية التالية مباشرة بلا نقر.
            # يُؤجَّل بعد إعادة رسم الجدول لأن إعادة الرسم تسحب التركيز.
            self.after(60, lambda: self.cast_row_num.focus_set())

    def refresh_casting_table(self):
        if not hasattr(self, 'cast_table_frame') or not self.cast_table_frame:
            return
        self.cast_tree, self.cast_table_rows_map = self.render_stage_ops_table(
            self.cast_table_frame, "صرف كاستنج", "قبض كاستنج", height=11, with_trees=True,
            section="الكاستنج", show_name=False, on_refresh=self.refresh_casting_table,
            on_detail=lambda: self.show_selected_stage_details(
                self.cast_tree, self.cast_table_rows_map, "تفاصيل حركة الكاستنج"),
            on_edit=self.edit_selected_casting_row,
            totals_label=getattr(self, 'cast_totals_lbl', None))

    def delete_selected_casting_row(self):
        if not (hasattr(self, 'cast_tree') and self.cast_tree):
            return
        sel = self.cast_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها من الجدول أولاً.")
            return
        ids = self.cast_table_rows_map.get(sel[0])
        if not ids:
            return
        if messagebox.askyesno("تأكيد الحذف", "هل أنت متأكد من حذف حركة الكاستنج المحددة؟"):
            any_blocked = False
            for inv_id in ids:
                if not self.delete_invoice_from_db(inv_id):
                    any_blocked = True
            if any_blocked:
                return  # تم منع حذف بعض الحركات (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            self.lbl_op_status.configure(text="🗑️ تم حذف حركة الكاستنج وتحديث الأرصدة")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))

    def edit_selected_casting_row(self):
        if not (hasattr(self, 'cast_tree') and self.cast_tree):
            return
        sel = self.cast_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها من الجدول أولاً.")
            return
        ids = self.cast_table_rows_map.get(sel[0])
        if not ids:
            return
        self.open_stage_op_edit_dialog(ids, "صرف كاستنج", "قبض كاستنج", "تعديل حركة الكاستنج",
                                       with_trees=True, status_text="✏️ تم تعديل حركة الكاستنج")

    # ---------------------------------------------------------------
    # ------------------------- شاشة التلميع -------------------------
    # ---------------------------------------------------------------
    def build_polish_ui(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(pady=(6, 4), padx=25)

        self.polish_date = ctk.CTkEntry(top, font=("Cairo", 15), justify="center", width=130, height=38)
        self.polish_date.insert(0, self.get_smart_default_date())
        self.polish_date.pack(side="right", padx=8)
        ctk.CTkLabel(top, text="التاريخ:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top, text="الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.polish_name = ctk.CTkComboBox(top, values=self.get_stage_name_values("التلميع/البف", "التلميع"), font=("Cairo", 15), width=200, height=38, justify="right")
        self.polish_name.set("")
        self.polish_name.pack(side="right", padx=8)
        self.bind_name_autocomplete(self.polish_name, lambda: self.get_stage_name_values("التلميع/البف", "التلميع"))

        fields_row = ctk.CTkFrame(parent)
        fields_row.pack(pady=(4, 4), fill="x", padx=25)

        col_row_num = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_row_num.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_row_num, text="رقم الصف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.polish_row_num = ctk.CTkEntry(col_row_num, justify="center", font=("Cairo", 15), width=100, height=34)
        self.polish_row_num.pack()

        col_sarf = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_sarf.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_sarf, text="الصرف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.polish_sarf = ctk.CTkEntry(col_sarf, justify="center", font=("Cairo", 15), width=100, height=34)
        self.polish_sarf.pack()

        col_qabd = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_qabd.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_qabd, text="القبض", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.polish_qabd = ctk.CTkEntry(col_qabd, justify="center", font=("Cairo", 15), width=100, height=34)
        self.polish_qabd.pack()

        bottom_entry_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=25, pady=(0, 8))

        self.polish_note = ctk.CTkEntry(bottom_entry_frame, placeholder_text="البيان / الملاحظات...", font=("Cairo", 15), justify="right", width=420, height=38)
        self.polish_note.pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(bottom_entry_frame, text=f"ترحيل حركة {self.get_display_label('التلميع')} 💾", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=210, command=self.submit_polish_op)
        btn_submit.pack(side="right", padx=8)

        polish_nav_fields = [self.polish_name, self.polish_row_num, self.polish_sarf, self.polish_qabd, self.polish_note]
        self.bind_arrow_navigation(polish_nav_fields)
        for i, f in enumerate(polish_nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=polish_nav_fields[i + 1]: nxt.focus_set() or "break")
        polish_nav_fields[-1].bind("<Return>", lambda e: (self.submit_polish_op(), "break")[1])

        table_top = ctk.CTkFrame(parent, fg_color="transparent")
        table_top.pack(fill="x", padx=25, pady=(8, 2))

        ctk.CTkLabel(table_top, text=f"كشف حركة {self.get_display_label('التلميع')}", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37").pack(side="right")

        btn_del_pol = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_row)
        btn_del_pol.pack(side="left", padx=5)

        self.build_negative_color_button(table_top, "التلميع", self.refresh_polish_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.polish_tree, f"عرض كامل — {self.get_display_label('التلميع')}")
                      ).pack(side="left", padx=5)

        btn_edit_pol = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_row)
        btn_edit_pol.pack(side="left", padx=5)

        self.polish_table_frame = ttk.Frame(parent)
        self.polish_table_frame.pack(fill="both", expand=True, padx=25, pady=(0, 4))
        self.polish_tree = None
        self.polish_table_rows_map = {}

        self.polish_totals_lbl = ctk.CTkLabel(parent, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        self.polish_totals_lbl.pack(fill="x", padx=25, pady=(0, 10))

    def submit_polish_op(self):
        date_val = self.polish_date.get().strip()
        name = self.clean_name(self.polish_name.get()) or "التلميع"
        note = self.polish_note.get().strip()
        row_num = self.polish_row_num.get().strip()
        if not date_val:
            messagebox.showwarning("تنبيه", "الرجاء إدخال التاريخ.")
            return
        if not row_num:
            messagebox.showwarning("رقم الصف مطلوب", "لازم تسجل رقم الصف أولاً قبل ترحيل أي عملية.")
            return

        try:
            sarf_v = round(float(self.polish_sarf.get().strip()), 2) if self.polish_sarf.get().strip() else 0.0
        except ValueError:
            sarf_v = 0.0
        try:
            qabd_v = round(float(self.polish_qabd.get().strip()), 2) if self.polish_qabd.get().strip() else 0.0
        except ValueError:
            qabd_v = 0.0

        if sarf_v <= 0 and qabd_v <= 0:
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة الصرف أو القبض أولاً.")
            return

        skipped = []
        if sarf_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "صرف تلميع" for inv in self.invoices.values()):
            skipped.append("الصرف")
            sarf_v = 0.0
        if qabd_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "قبض تلميع" for inv in self.invoices.values()):
            skipped.append("القبض")
            qabd_v = 0.0
        if skipped and not messagebox.askyesno("عملية مكررة", "تم تجاهل: " + "، ".join(skipped) + f" لأنها مسجلة بالفعل بنفس رقم الصف ({row_num}).\nهل تريد المتابعة بباقي القيم المُدخلة (إن وُجدت)؟"):
            return
        if sarf_v <= 0 and qabd_v <= 0:
            return

        if not messagebox.askyesno("تأكيد الترحيل", f"هل أنت متأكد من ترحيل حركة {self.get_display_label('التلميع')}؟"):
            return

        if name != "التلميع" and not self.check_name_exists(name):
            self.categories["التلميع"].append(name)
            self.save_name_to_db(name, "التلميع")

        full_date_time = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        saved_any = False

        if sarf_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": "صرف تلميع", "الوزن": sarf_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if qabd_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time, "الاسم": name,
                "النوع": "قبض تلميع", "الوزن": qabd_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if saved_any:
            self.register_operation_period(date_val)
            self.recalculate_all()

            self.polish_sarf.delete(0, 'end')
            self.polish_qabd.delete(0, 'end')
            self.polish_note.delete(0, 'end')
            self.polish_row_num.delete(0, 'end')
            self.polish_name.configure(values=self.get_stage_name_values("التلميع/البف", "التلميع"))
            self.polish_name.set("")

            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة {self.get_display_label('التلميع')} لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.after(60, lambda: self.polish_row_num.focus_set())
            self.refresh_polish_table()

    def refresh_polish_table(self):
        if not hasattr(self, 'polish_table_frame') or not self.polish_table_frame:
            return
        self.polish_tree, self.polish_table_rows_map = self.render_stage_ops_table(
            self.polish_table_frame, "صرف تلميع", "قبض تلميع", height=11, section="التلميع",
            show_name=False, on_refresh=self.refresh_polish_table,
            on_detail=lambda: self.show_selected_stage_details(
                self.polish_tree, self.polish_table_rows_map, "تفاصيل حركة التلميع"),
            on_edit=self.edit_selected_polish_row,
            totals_label=getattr(self, 'polish_totals_lbl', None))

    def delete_selected_polish_row(self):
        if not (hasattr(self, 'polish_tree') and self.polish_tree):
            return
        sel = self.polish_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها من الجدول أولاً.")
            return
        ids = self.polish_table_rows_map.get(sel[0])
        if not ids:
            return
        if messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف حركة {self.get_display_label('التلميع')} المحددة؟"):
            any_blocked = False
            for inv_id in ids:
                if not self.delete_invoice_from_db(inv_id):
                    any_blocked = True
            if any_blocked:
                return
            self.recalculate_all()
            self.lbl_op_status.configure(text=f"🗑️ تم حذف حركة {self.get_display_label('التلميع')} وتحديث الأرصدة")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))

    def edit_selected_polish_row(self):
        if not (hasattr(self, 'polish_tree') and self.polish_tree):
            return
        sel = self.polish_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها من الجدول أولاً.")
            return
        ids = self.polish_table_rows_map.get(sel[0])
        if not ids:
            return
        self.open_stage_op_edit_dialog(ids, "صرف تلميع", "قبض تلميع",
                                       f"تعديل حركة {self.get_display_label('التلميع')}",
                                       status_text=f"✏️ تم تعديل حركة {self.get_display_label('التلميع')}")

    # ---------------------------------------------------------------
    # ---------------------- شاشة التلميع/البف ----------------------
    # ---------------------------------------------------------------
    def build_polish_buff_ui(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(pady=(6, 4), padx=25)

        self.pbuff_date = ctk.CTkEntry(top, font=("Cairo", 15), justify="center", width=130, height=38)
        self.pbuff_date.insert(0, self.get_smart_default_date())
        self.pbuff_date.pack(side="right", padx=8)
        ctk.CTkLabel(top, text="التاريخ:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top, text="الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.pbuff_name = ctk.CTkComboBox(top, values=self.get_stage_name_values("البوليش", "التلميع/البف"), font=("Cairo", 15), width=200, height=38, justify="right")
        self.pbuff_name.set("")
        self.pbuff_name.pack(side="right", padx=8)
        self.bind_name_autocomplete(self.pbuff_name, lambda: self.get_stage_name_values("البوليش", "التلميع/البف"))

        fields_row = ctk.CTkFrame(parent)
        fields_row.pack(pady=(4, 4), fill="x", padx=25)

        col_row_num = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_row_num.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_row_num, text="رقم الصف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.pbuff_row_num = ctk.CTkEntry(col_row_num, justify="center", font=("Cairo", 15), width=100, height=34)
        self.pbuff_row_num.pack()

        col_sarf = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_sarf.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_sarf, text="الصرف", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.pbuff_sarf = ctk.CTkEntry(col_sarf, justify="center", font=("Cairo", 15), width=110, height=34)
        self.pbuff_sarf.pack()

        col_qabd = ctk.CTkFrame(fields_row, fg_color="transparent")
        col_qabd.pack(side="right", padx=15, pady=8)
        ctk.CTkLabel(col_qabd, text="القبض", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        self.pbuff_qabd = ctk.CTkEntry(col_qabd, justify="center", font=("Cairo", 15), width=110, height=34)
        self.pbuff_qabd.pack()

        bottom_entry_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=25, pady=(0, 8))

        self.pbuff_note = ctk.CTkEntry(bottom_entry_frame, placeholder_text="البيان / الملاحظات...", font=("Cairo", 15), justify="right", width=420, height=38)
        self.pbuff_note.pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(bottom_entry_frame, text=f"ترحيل حركة {self.get_display_label('التلميع/البف')} 💾", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=230, command=self.submit_polish_buff_op)
        btn_submit.pack(side="right", padx=8)

        pbuff_nav_fields = [self.pbuff_name, self.pbuff_row_num, self.pbuff_sarf, self.pbuff_qabd, self.pbuff_note]
        self.bind_arrow_navigation(pbuff_nav_fields)
        for i, f in enumerate(pbuff_nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=pbuff_nav_fields[i + 1]: nxt.focus_set() or "break")
        pbuff_nav_fields[-1].bind("<Return>", lambda e: (self.submit_polish_buff_op(), "break")[1])

        table_top = ctk.CTkFrame(parent, fg_color="transparent")
        table_top.pack(fill="x", padx=25, pady=(8, 2))

        ctk.CTkLabel(table_top, text=f"كشف حركة {self.get_display_label('التلميع/البف')}", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37").pack(side="right")

        btn_del = ctk.CTkButton(table_top, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=160, height=32, command=self.delete_selected_polish_buff_row)
        btn_del.pack(side="left", padx=5)

        self.build_negative_color_button(table_top, "التلميع/البف", self.refresh_polish_buff_table)

        ctk.CTkButton(table_top, text="👁️ عرض", font=("Cairo", 14, "bold"), fg_color="#1f77b4",
                      hover_color="#144d75", width=90, height=32,
                      command=lambda: self.view_treeview_fullscreen(
                          self.pbuff_tree, f"عرض كامل — {self.get_display_label('التلميع/البف')}")
                      ).pack(side="left", padx=5)

        btn_edit = ctk.CTkButton(table_top, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=160, height=32, command=self.edit_selected_polish_buff_row)
        btn_edit.pack(side="left", padx=5)

        self.pbuff_table_frame = ttk.Frame(parent)
        self.pbuff_table_frame.pack(fill="both", expand=True, padx=25, pady=(0, 4))
        self.pbuff_tree = None
        self.pbuff_table_rows_map = {}

        self.pbuff_totals_lbl = ctk.CTkLabel(parent, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        self.pbuff_totals_lbl.pack(fill="x", padx=25, pady=(0, 10))

    def submit_polish_buff_op(self):
        date_val = self.pbuff_date.get().strip()
        name = self.clean_name(self.pbuff_name.get()) or "التلميع/البف"
        note = self.pbuff_note.get().strip()
        row_num = self.pbuff_row_num.get().strip()
        if not date_val:
            messagebox.showwarning("تنبيه", "الرجاء إدخال التاريخ.")
            return
        if not row_num:
            messagebox.showwarning("رقم الصف مطلوب", "لازم تسجل رقم الصف أولاً قبل ترحيل أي عملية.")
            return

        try:
            sarf_v = round(float(self.pbuff_sarf.get().strip()), 2) if self.pbuff_sarf.get().strip() else 0.0
        except ValueError:
            sarf_v = 0.0
        try:
            qabd_v = round(float(self.pbuff_qabd.get().strip()), 2) if self.pbuff_qabd.get().strip() else 0.0
        except ValueError:
            qabd_v = 0.0

        if sarf_v <= 0 and qabd_v <= 0:
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة الصرف أو القبض أولاً.")
            return

        skipped = []
        if sarf_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "صرف تلميع بف" for inv in self.invoices.values()):
            skipped.append("الصرف")
            sarf_v = 0.0
        if qabd_v > 0 and any(inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month) and (inv.get("row_number", "") or "") == row_num and inv.get("النوع") == "قبض تلميع بف" for inv in self.invoices.values()):
            skipped.append("القبض")
            qabd_v = 0.0
        if skipped and not messagebox.askyesno("عملية مكررة", "تم تجاهل: " + "، ".join(skipped) + f" لأنها مسجلة بالفعل بنفس رقم الصف ({row_num}).\nهل تريد المتابعة بباقي القيم المُدخلة (إن وُجدت)؟"):
            return
        if sarf_v <= 0 and qabd_v <= 0:
            return

        if not messagebox.askyesno("تأكيد الترحيل", f"هل أنت متأكد من ترحيل حركة {self.get_display_label('التلميع/البف')}؟"):
            return

        if name != "التلميع/البف" and not self.check_name_exists(name):
            self.categories["التلميع/البف"].append(name)
            self.save_name_to_db(name, "التلميع/البف")

        full_dt = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        saved_any = False

        if sarf_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                "النوع": "صرف تلميع بف", "الوزن": sarf_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if qabd_v > 0:
            self.invoice_counter += 1
            inv_data = {
                "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                "النوع": "قبض تلميع بف", "الوزن": qabd_v, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": "", "row_number": row_num
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)
            saved_any = True

        if saved_any:
            self.register_operation_period(date_val)
            self.recalculate_all()

            self.pbuff_sarf.delete(0, 'end')
            self.pbuff_qabd.delete(0, 'end')
            self.pbuff_note.delete(0, 'end')
            self.pbuff_row_num.delete(0, 'end')
            self.pbuff_name.configure(values=self.get_stage_name_values("البوليش", "التلميع/البف"))
            self.pbuff_name.set("")

            self.lbl_op_status.configure(text=f"✅ تم ترحيل حركة {self.get_display_label('التلميع/البف')} لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            self.after(60, lambda: self.pbuff_row_num.focus_set())
            self.refresh_polish_buff_table()

    def refresh_polish_buff_table(self):
        if not hasattr(self, 'pbuff_table_frame') or not self.pbuff_table_frame:
            return
        self.pbuff_tree, self.pbuff_table_rows_map = self.render_stage_ops_table(
            self.pbuff_table_frame, "صرف تلميع بف", "قبض تلميع بف", height=11, section="التلميع/البف",
            show_name=False, on_refresh=self.refresh_polish_buff_table,
            on_detail=lambda: self.show_selected_stage_details(
                self.pbuff_tree, self.pbuff_table_rows_map, "تفاصيل حركة التلميع/البف"),
            on_edit=self.edit_selected_polish_buff_row,
            totals_label=getattr(self, 'pbuff_totals_lbl', None))

    def delete_selected_polish_buff_row(self):
        if not (hasattr(self, 'pbuff_tree') and self.pbuff_tree):
            return
        sel = self.pbuff_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها من الجدول أولاً.")
            return
        ids = self.pbuff_table_rows_map.get(sel[0])
        if not ids:
            return
        if messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف حركة {self.get_display_label('التلميع/البف')} المحددة؟"):
            any_blocked = False
            for inv_id in ids:
                if not self.delete_invoice_from_db(inv_id):
                    any_blocked = True
            if any_blocked:
                return
            self.recalculate_all()
            self.lbl_op_status.configure(text=f"🗑️ تم حذف حركة {self.get_display_label('التلميع/البف')} وتحديث الأرصدة")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))

    def edit_selected_polish_buff_row(self):
        if not (hasattr(self, 'pbuff_tree') and self.pbuff_tree):
            return
        sel = self.pbuff_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها من الجدول أولاً.")
            return
        ids = self.pbuff_table_rows_map.get(sel[0])
        if not ids:
            return
        self.open_stage_op_edit_dialog(ids, "صرف تلميع بف", "قبض تلميع بف",
                                       f"تعديل حركة {self.get_display_label('التلميع/البف')}",
                                       status_text=f"✏️ تم تعديل حركة {self.get_display_label('التلميع/البف')}")

    def update_op_names(self, cat):
        names = self.categories.get(cat, [])
        if names:
            # تُعرض باتجاه مثبّت (RLM) فيبقى الاسم المركّب بترتيبه الصحيح،
            # وتُنظَّف من العلامة عند كل قراءة عبر clean_name
            self.combo_op_name.configure(values=[self.rtl(n) for n in names])
            self.combo_op_name.set(self.rtl(names[0]))
            self.render_unified_fields(names[0])
        else:
            self.combo_op_name.configure(values=["لا يوجد أسماء"])
            self.combo_op_name.set("لا يوجد أسماء")
            self.render_unified_fields("لا يوجد أسماء")

    def choose_qabd_type(self, btn):
        menu = tk.Menu(self, tearoff=0, font=("Cairo", 13))
        for t in ["ايطالي", "زركون", "احجار", "الماس", "عام"]:
            menu.add_command(label=t, command=lambda v=t, b=btn: self.set_qabd_type(b, v))
        menu.post(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())

    def set_qabd_type(self, btn, val):
        btn.configure(text=val)
        self.selected_qabd_type = val

    def render_unified_fields(self, name):
        # الاسم قد يأتي من القائمة حاملاً علامة الاتجاه، فيُنظَّف قبل أي استخدام
        name = self.clean_name(name)
        for widget in self.unified_inputs_frame.winfo_children():
            widget.destroy()
        
        self.current_win_entries = {}
        # تم إزالة تفريغ النوع من هنا ليحتفظ بآخر قيمة في حال تم تعيينها سابقاً
        if not hasattr(self, 'selected_qabd_type'):
            self.selected_qabd_type = "عام"
            
        cat = self.current_op_cat
        fields = []

        if cat == "الآلة/المكائن":
            if name == "الكاستينج":
                fields = [("before", "قبل الصب"), ("after", "بعد الصب"), ("trees", "عدد الشجر")]
            elif name == "التلميع النهائي":
                fields = [("khayas", "الخياس الفعلي")]
            else:
                fields = [("before", "قبل "), ("after", "بعد ")]
        elif cat == "المركبين":
            # تغيير مسمى الطقم إلى رقم التشغيل + إضافة رقم الصف كأول خانة (يحدد الصف بالجدول)
            fields = [("رقم الصف", "رقم الصف"), ("صرف ذهب", "صرف"), ("قبض ذهب", "قبض"), ("رقم التشغيل", "رقم التشغيل"), ("الليز", "الليز"), 
                      ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")]
        else: # المصنعين
            fields = [("رقم الصف", "رقم الصف"), ("صرف ذهب", "صرف"), ("قبض ذهب", "قبض/كسر"), ("المفنش ٨ بالالف", "قبض/٨"), ("المفنش ٤ بالالف", "قبض/٤"), ("البوليش", "بوليش"),
                      ("رقم التشغيل", "رقم التشغيل"), ("الليز", "الليز"),
                      ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "عيار بعد الفحص")]

        # عرض كل حقول العملية في صف أفقي واحد مضغوط (تسمية أعلى وخانة أصغر أسفلها)
        n_fields = len(fields) if fields else 1

        entries_list = []
        for i, (key, lbl_text) in enumerate(fields):
            col = n_fields - 1 - i
            
            lbl = ctk.CTkLabel(self.unified_inputs_frame, text=lbl_text, font=("Cairo", 14, "bold"))
            lbl.grid(row=0, column=col, padx=6, pady=(8, 2))
            
            if key == "قبض ذهب":
                qabd_frame = ctk.CTkFrame(self.unified_inputs_frame, fg_color="transparent")
                qabd_frame.grid(row=1, column=col, padx=6, pady=(0, 8))
                
                ent = ctk.CTkEntry(qabd_frame, justify="center", font=("Cairo", 15), width=68, height=34)
                ent.pack(side="right", padx=(0, 3))
                
                btn_type = ctk.CTkButton(qabd_frame, text=self.selected_qabd_type if self.selected_qabd_type != "عام" else "نوع", width=36, height=34, font=("Cairo", 12, "bold"), fg_color="#1f77b4")
                btn_type.configure(command=lambda b=btn_type: self.choose_qabd_type(b))
                btn_type.pack(side="right")
                
                self.current_win_entries[key] = (ent, btn_type)
                entries_list.append(ent)
            else:
                ent = ctk.CTkEntry(self.unified_inputs_frame, justify="center", font=("Cairo", 15), width=88, height=34)
                ent.grid(row=1, column=col, padx=6, pady=(0, 8))
                
                self.current_win_entries[key] = ent
                entries_list.append(ent)

        if entries_list:
            entries_list[0].focus_set()

        nav_chain = entries_list + [self.op_note]
        for i, f in enumerate(nav_chain[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_chain[i + 1]: nxt.focus_set() or "break")
        nav_chain[-1].bind("<Return>", lambda e: (self.submit_unified_op(), "break")[1])
        self.bind_arrow_navigation(nav_chain)

        # تحديث كشف حركة العامل/المكينة المعروض أسفل الشاشة فور تغيير الاختيار
        self.refresh_op_ledger_table()

    def find_row_by_set_number(self, cat, set_num, month=None):
        """يبحث عن الصف الذي يحمل رقم تشغيل معيّن داخل قسم.

        رقم التشغيل يخصّ صفاً واحداً وعاملاً واحداً، فهو يُعرّف الصف تعريفاً
        كاملاً. يرجع: (اسم العامل، رقم الصف) أو (None, None).
        """
        set_num = (set_num or "").strip()
        if not set_num:
            return None, None
        month = month or self.current_display_month
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE":
                continue
            if inv.get("الاسم") not in self.categories.get(cat, []):
                continue
            if not self.inv_in_period(inv, month):
                continue
            if (inv.get("set_number", "") or "").strip() == set_num:
                return inv.get("الاسم"), (inv.get("row_number", "") or "").strip()
        return None, None

    def submit_unified_op(self):
        cat = self.current_op_cat
        name = self.clean_name(self.combo_op_name.get())
        date_val = self.op_date.get().strip()
        note = self.op_note.get().strip()

        if name == "لا يوجد أسماء" or not name or not self.check_name_exists(name):
            return

        # التاريخ إلزامي لأنه هو ما يحدد الفترة المحاسبية التي تُسجَّل فيها الحركة
        if len(date_val) < 7 or date_val[4] != '-':
            messagebox.showwarning("التاريخ مطلوب", "الرجاء إدخال التاريخ بالصيغة الصحيحة YYYY-MM-DD قبل الترحيل.")
            return

        # ══════════════════════════════════════════════════════════════
        #  المصنعون والمركبون: رقم التشغيل يُعرّف الصف
        #
        #  • رقم تشغيل جديد  → يلزم رقم صف، ويُنشأ صف جديد.
        #  • رقم تشغيل موجود → تُضاف العملية إلى **نفس صفه** تلقائياً،
        #    فلا حاجة لكتابة رقم الصف (مثلاً: سجّلنا الصرف، ثم نكمل القبض).
        #  • ولا يجوز تكرار رقم التشغيل في صف آخر أو لعامل آخر.
        # ══════════════════════════════════════════════════════════════
        if cat in ("المصنعين", "المركبين"):
            set_entry = self.current_win_entries.get("رقم التشغيل")
            row_entry = self.current_win_entries.get("رقم الصف")
            set_typed = set_entry.get().strip() if set_entry is not None else ""
            row_typed = row_entry.get().strip() if row_entry is not None else ""

            owner, owner_row = self.find_row_by_set_number(cat, set_typed)

            if owner:
                # رقم التشغيل مسجّل مسبقاً: نُكمل على صفه
                if owner != name:
                    messagebox.showwarning(
                        "رقم تشغيل مستخدم",
                        f"رقم التشغيل ({set_typed}) مسجّل للعامل ({owner}) في الصف ({owner_row}).\n\n"
                        "لا يمكن تسجيل نفس رقم التشغيل لعامل آخر.")
                    return
                if row_typed and row_typed != owner_row:
                    messagebox.showwarning(
                        "رقم تشغيل مستخدم",
                        f"رقم التشغيل ({set_typed}) مسجّل في الصف ({owner_row}) وليس ({row_typed}).\n\n"
                        "اترك خانة رقم الصف فارغة لتُضاف العملية إلى صفه تلقائياً.")
                    return
                # نملأ رقم الصف نيابةً عن المستخدم
                if row_entry is not None and not row_typed:
                    row_entry.delete(0, 'end')
                    row_entry.insert(0, owner_row)

            else:
                # رقم تشغيل جديد: رقم الصف إلزامي
                if not row_typed:
                    messagebox.showwarning(
                        "رقم الصف مطلوب",
                        "رقم التشغيل غير مسجّل من قبل، فلازم تكتب رقم الصف لإنشاء صف جديد.")
                    return
                # ولا يجوز أن يحمل الصف الجديد رقم تشغيل صفٍّ آخر
                if set_typed:
                    dup_owner, dup_row = self.find_row_by_set_number(cat, set_typed)
                    if dup_owner and dup_row != row_typed:
                        messagebox.showwarning(
                            "رقم تشغيل مكرر",
                            f"رقم التشغيل ({set_typed}) مستخدم في الصف ({dup_row}).")
                        return

        if not messagebox.askyesno("تأكيد الترحيل", "هل أنت متأكد من ترحيل هذه العملية؟"):
            return

        # تم التعديل ليشمل الثواني لكي تتوحد البصمة الزمنية للعمليات المترابطة بالكامل
        full_date_time = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        saved_any = False

        if cat == "الآلة/المكائن":
            try:
                inv_data = {
                    "رقم الفاتورة": self.invoice_counter + 1, "التاريخ": full_date_time,
                    "الاسم": name, "النوع": "خياس الاله/المكائن", "البيان": note or "حركة مجمعة", "settled_status": "ACTIVE",
                    "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "الوزن": 0.0, "set_number": ""
                }
                
                if name == "الكاستينج":
                    w_b = float(self.current_win_entries['before'].get() or 0)
                    w_a = float(self.current_win_entries['after'].get() or 0)
                    t_count = float(self.current_win_entries['trees'].get() or 0)
                    if w_b == 0 and w_a == 0: return
                    inv_data["قبل"] = w_b
                    inv_data["بعد"] = w_a
                    inv_data["trees_count"] = t_count
                    inv_data["الوزن"] = round(w_b - w_a, 2)
                elif name == "التلميع النهائي":
                    val = float(self.current_win_entries['khayas'].get() or 0)
                    if val == 0: return
                    inv_data["الوزن"] = val
                else:
                    w_b = float(self.current_win_entries['before'].get() or 0)
                    w_a = float(self.current_win_entries['after'].get() or 0)
                    if w_b == 0 and w_a == 0: return
                    inv_data["قبل"] = w_b
                    inv_data["بعد"] = w_a
                    inv_data["الوزن"] = round(w_b - w_a, 2)

                self.invoice_counter += 1
                inv_data["رقم الفاتورة"] = self.invoice_counter
                self.invoices[self.invoice_counter] = inv_data
                self.save_invoice_to_db(self.invoice_counter, inv_data)
                saved_any = True
            except ValueError: pass
        else:
            qabd_t = getattr(self, 'selected_qabd_type', 'عام')
            
            # جلب قيمة رقم التشغيل ورقم الصف
            set_num = ""
            if "رقم التشغيل" in self.current_win_entries:
                set_num = self.current_win_entries["رقم التشغيل"].get().strip()

            row_num = ""
            if "رقم الصف" in self.current_win_entries:
                row_num = self.current_win_entries["رقم الصف"].get().strip()
                
            skipped_types = []
            for op_type, ent in self.current_win_entries.items():
                if op_type in ("رقم التشغيل", "رقم الصف"): continue
                
                if isinstance(ent, tuple):
                    ent_widget = ent[0]
                else:
                    ent_widget = ent
                val_str = ent_widget.get().strip()
                if not val_str: continue
                try:
                    val = round(float(val_str), 2)
                    if val <= 0 and op_type != "العيار بعد الفحص": continue

                    # منع تكرار نفس العملية أكثر من مرة بنفس رقم الصف (لو كان مسجل بالفعل)
                    is_dup = any(
                        inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE"
                        and self.inv_in_period(inv, self.current_display_month)
                        and (inv.get("row_number", "") or "") == row_num
                        and inv.get("النوع") == op_type
                        for inv in self.invoices.values()
                    )
                    if is_dup:
                        skipped_types.append(op_type)
                        continue
                    
                    self.invoice_counter += 1
                    if op_type == "قبض ذهب" and qabd_t != 'عام':
                        current_note = qabd_t
                    else:
                        current_note = ""

                    inv_data = {
                        "رقم الفاتورة": self.invoice_counter, "التاريخ": full_date_time,
                        "الاسم": name, "النوع": op_type, "الوزن": val,
                        "البيان": current_note, "settled_status": "ACTIVE",
                        "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": set_num,
                        "row_number": row_num
                    }
                    self.invoices[self.invoice_counter] = inv_data
                    self.save_invoice_to_db(self.invoice_counter, inv_data)
                    saved_any = True
                except ValueError: pass

            if skipped_types:
                messagebox.showwarning("عملية مكررة", "تم تجاهل الحقول التالية لأنها مسجلة بالفعل بنفس رقم الصف:\n" + "، ".join(skipped_types) + "\n\nلو تقصد تعديل القيمة، عدّلها من كشف الحركة أسفل الشاشة.")


        if saved_any:
            self.register_operation_period(date_val)
            self.recalculate_all()
            
            # تفريغ المدخلات مع الاحتفاظ بذاكرة نوع القبض الأخير
            for k, ent in self.current_win_entries.items():
                if isinstance(ent, tuple):
                    ent[0].delete(0, 'end')
                else:
                    ent.delete(0, 'end')
            self.op_note.delete(0, 'end')
            
            # رسالة نجاح سريعة تتلاشى دون إزعاج المستخدم
            self.lbl_op_status.configure(text=f"✅ تم الترحيل بنجاح لـ ({name})")
            self.after(2500, lambda: self.lbl_op_status.configure(text=""))
            
            # التركيز يعود لخانة (رقم الصف) صراحةً لبدء العملية التالية مباشرة،
            # بدل الاعتماد على ترتيب القاموس الذي قد يتغيّر مع تغيّر الحقول
            target = self.current_win_entries.get("رقم الصف")
            if target is None and self.current_win_entries:
                target = list(self.current_win_entries.values())[0]
            if isinstance(target, tuple):
                target = target[0]
            if target is not None:
                self.after(60, lambda t=target: t.focus_set())

    # =========================================================================
    # --- كشف حركة العامل/المكينة المدمج داخل شاشة العمليات مباشرة ---
    # =========================================================================
    def build_op_ledger_columns(self, worker_name, cat):
        if worker_name == "الكاستينج":
            cols = ("التاريخ", "قبل", "بعد", "عدد الشجر", "الخياس الكلي", "خياس الشجرة", "البيان")
        elif worker_name == "التلميع النهائي":
            cols = ("التاريخ", "الخياس الكلي", "البيان")
        elif cat == "الآلة/المكائن":
            cols = ("التاريخ", "قبل", "بعد", "الخياس الكلي", "البيان")
        elif cat == "المركبين":
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الراجع/عيار",
                    "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")
        else: # المصنعين
            cols = ("الصف", "رقم التشغيل", "صرف", "قبض", "مفنش 8", "مفنش 4", "بوليش", "ليز", "سلك راجع", "عيار",
                    "الراجع/عيار", "الفاقد اللحظي", "مسموح/٨", "مسموح/٤", "ذهب/صافي", "البيان")
        return cols

    def refresh_op_ledger_table(self):
        if not hasattr(self, 'op_ledger_table_frame') or self.op_ledger_table_frame is None:
            return


        self.op_ledger_tree = None
        self.op_ledger_group_map = {}

        if not hasattr(self, 'combo_op_name'):
            return

        worker_name = self.clean_name(self.combo_op_name.get())
        cat = self.current_op_cat

        if not worker_name or worker_name == "لا يوجد أسماء" or not self.check_name_exists(worker_name):
            if hasattr(self, 'lbl_op_ledger_title'):
                self.lbl_op_ledger_title.configure(text="كشف حركة العامل المحدد")
            if hasattr(self, 'lbl_op_ledger_totals'):
                self.lbl_op_ledger_totals.configure(text="")
            return

        if hasattr(self, 'lbl_op_ledger_title'):
            self.lbl_op_ledger_title.configure(text=f"كشف حركة: {worker_name} — الفترة ({self.current_display_month})")

        cols = self.build_op_ledger_columns(worker_name, cat)
        # عمود الاسم صار جزءاً من الجدول نفسه (أول عمود) بدل جدول منفصل بجانبه،
        # فيبقى الجدول كتلة واحدة مرتبة ويتمرّر معها الاسم تلقائياً
        show_name_col = cat in ("المصنعين", "المركبين") and worker_name not in ("الكاستينج", "التلميع النهائي")
        self.op_ledger_name_tree = None
        if show_name_col:
            cols = ("الاسم",) + tuple(cols)

        self.op_ledger_tree, self.op_ledger_total_tree, _reused = self.reuse_or_create_tree(
            self.op_ledger_table_frame, cols, height=11, sticky_total=True)

        self.op_ledger_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.tag_configure("red_tag", foreground="#e74c3c", font=("Cairo", 13, "bold"))
        self.op_ledger_tree.bind("<Double-1>", self._on_op_ledger_double_click)

        if cat == "المصنعين" and worker_name not in ("الكاستينج", "التلميع النهائي"):
            self.op_ledger_tree.heading("قبض", text="قبض/كسر")
            self.op_ledger_tree.heading("مفنش 8", text="قبض/٨")
            self.op_ledger_tree.heading("مفنش 4", text="قبض/٤")

        for c in cols:
            # البيان مُقلَّص عمداً: الأرقام هي الأهم في هذا الكشف،
            # والنص الطويل كان يدفع الأعمدة الرقمية خارج الشاشة
            # عرض مبدئي فقط؛ fit_columns_to_content يضبطه لاحقاً حسب المحتوى
            w = 40 if c == "الصف" else 70
            self.op_ledger_tree.column(c, width=w, anchor="center", stretch=False)

        # بادئة الاسم: تُدرج كأول قيمة في كل صف عندما يكون عمود الاسم ظاهراً،
        # فيبقى عدد القيم مطابقاً لعدد الأعمدة دائماً
        name_prefix = (worker_name,) if show_name_col else ()
        total_prefix = ("الإجمالي",) if show_name_col else ()

        # تلوين السالب حسب إعداد القسم المعروض حالياً
        color_negative = self.negative_color_enabled(cat)
        self.update_negative_color_button(cat)

        # التجميع في كشف الحركة: برقم الصف لقسمي المصنعين والمركبين، وبالتاريخ لباقي الأقسام (الآلة/المكائن) كما كان
        group_by_row = cat in ("المصنعين", "المركبين")

        worker_invs = [inv for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month)]
        worker_invs = sorted(worker_invs, key=lambda x: x.get("التاريخ", ""))

        grouped_data = {}
        for inv in worker_invs:
            gkey = (inv.get("row_number", "") or "") if group_by_row else inv["التاريخ"]
            if gkey not in grouped_data:
                grouped_data[gkey] = {
                    "inv_id": inv["رقم الفاتورة"], "dt": inv["التاريخ"], "note": inv["البيان"] or "",
                    "set_number": inv.get("set_number", ""),
                    "صرف": 0.0, "قبض": 0.0, "ليز": 0.0, "بوليش": 0.0,
                    "مفنش 8": 0.0, "مفنش 4": 0.0, "سلك راجع": 0.0, "عيار": 0.0,
                    "قبل": 0.0, "بعد": 0.0, "الخياس": 0.0, "trees": 0.0
                }

            data = grouped_data[gkey]
            if inv["البيان"] and inv["البيان"] not in data["note"]:
                if data["note"] in ["", "حركة مجمعة"]:
                    data["note"] = inv["البيان"]
                else:
                    data["note"] += " | " + inv["البيان"]

            if not data["set_number"] and inv.get("set_number"):
                data["set_number"] = inv["set_number"]

            t = inv["النوع"]
            w = inv["الوزن"]
            if t == "صرف ذهب": data["صرف"] = w
            elif t == "قبض ذهب": data["قبض"] = w
            elif t == "الليز": data["ليز"] = w
            elif t == "البوليش": data["بوليش"] = w
            elif t == "المفنش ٨ بالالف": data["مفنش 8"] = w
            elif t == "المفنش ٤ بالالف": data["مفنش 4"] = w
            elif t == "السلك الراجع": data["سلك راجع"] = w
            elif t == "العيار بعد الفحص": data["عيار"] = w
            elif t == "خياس الاله/المكائن":
                data["قبل"] = inv.get("قبل", 0.0)
                data["بعد"] = inv.get("بعد", 0.0)
                data["الخياس"] = w
                data["trees"] = inv.get("trees_count", 0.0)

        # الترتيب: تدريجي برقم الصف في المصنعين والمركبين، وبالتاريخ لباقي الأقسام
        if group_by_row:
            ordered = sorted(grouped_data.items(), key=lambda kv: (self.row_sort_key(kv[0]), kv[1]["dt"]))
        else:
            ordered = sorted(grouped_data.items(), key=lambda kv: (kv[1]["dt"], str(kv[0])))

        tot = {k: 0.0 for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع",
                                "قبل", "بعد", "الخياس", "trees", "فاقد", "مسموح 8", "مسموح 4",
                                "ذهب صافي", "راجع عيار")}

        for gkey, data in ordered:
            note = data["note"]
            row_id = None
            row_label = gkey if gkey else "بدون ترقيم"

            for k in ("صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع", "قبل", "بعد", "trees"):
                tot[k] = round(tot[k] + data[k], 2)

            if worker_name == "الكاستينج":
                k_per_tree = round(data["الخياس"] / data["trees"], 2) if data["trees"] > 0 else 0.0
                tot["الخياس"] = round(tot["الخياس"] + data["الخياس"], 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(gkey, f"{data['قبل']:.2f}", f"{data['بعد']:.2f}", f"{data['trees']:.1f}", f"{data['الخياس']:.2f}", f"{k_per_tree:.2f}", note))
            elif worker_name == "التلميع النهائي":
                tot["الخياس"] = round(tot["الخياس"] + data["الخياس"], 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(gkey, f"{data['الخياس']:.2f}", note))
            elif cat == "الآلة/المكائن":
                tot["الخياس"] = round(tot["الخياس"] + data["الخياس"], 2)
                row_id = self.op_ledger_tree.insert("", "end", values=(gkey, f"{data['قبل']:.2f}", f"{data['بعد']:.2f}", f"{data['الخياس']:.2f}", note))
            elif cat == "المركبين":
                raji_v = raji_ayar(data['سلك راجع'], data['عيار'])
                # ذهب/باقي (الفاقد اللحظي) يخصم الآن (الراجع/عيار) أيضاً
                faqid = round(data['صرف'] - data['قبض'] + data['ليز'] - raji_v, 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                tot["راجع عيار"] = round(tot.get("راجع عيار", 0.0) + raji_v, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المركبين يُحتسب على القبض (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['قبض'] * ALLOWANCE_8, 2)
                # ذهب/صافي = الفاقد اللحظي (بعد خصم الراجع/عيار) بعد خصم المسموح
                net_gold = round(faqid - allow8, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=name_prefix + (row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{raji_v:.3f}", f"{faqid:.2f}", f"{allow8:.3f}", "-", f"{net_gold:.2f}", note), tags=row_tags)
            else:
                raji_v = raji_ayar(data['سلك راجع'], data['عيار'])
                # ذهب/باقي (الفاقد اللحظي) يخصم الآن (الراجع/عيار) أيضاً
                faqid = round(data['صرف'] - data['قبض'] - data['بوليش'] + data['ليز'] - data['مفنش 8'] - data['مفنش 4'] - raji_v, 2)
                tot["فاقد"] = round(tot["فاقد"] + faqid, 2)
                tot["راجع عيار"] = round(tot.get("راجع عيار", 0.0) + raji_v, 2)
                row_tags = ("red_tag",) if (color_negative and faqid < 0) else ()
                # المسموح في المصنعين يُحتسب على المفنش ٨ و٤ (نفس معادلة شاشة صناديق الخياس)
                allow8 = round(data['مفنش 8'] * ALLOWANCE_8, 2)
                allow4 = round(data['مفنش 4'] * ALLOWANCE_4, 2)
                # ذهب/صافي = الفاقد اللحظي (بعد خصم الراجع/عيار) بعد خصم المسموح ٨ و٤
                net_gold = round(faqid - allow8 - allow4, 2)
                tot["مسموح 8"] = round(tot["مسموح 8"] + allow8, 2)
                tot["مسموح 4"] = round(tot["مسموح 4"] + allow4, 2)
                tot["ذهب صافي"] = round(tot["ذهب صافي"] + net_gold, 2)
                row_id = self.op_ledger_tree.insert("", "end", values=name_prefix + (row_label, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['بوليش']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{raji_v:.3f}", f"{faqid:.2f}", f"{allow8:.3f}", f"{allow4:.3f}", f"{net_gold:.2f}", note), tags=row_tags)

            if row_id is not None:
                self.op_ledger_group_map[row_id] = gkey

        # سطر الإجماليات أسفل الجدول + شريط إجماليات ثابت تحته
        totals_txt = ""
        if ordered:
            if worker_name == "الكاستينج":
                per_tree = round(tot["الخياس"] / tot["trees"], 2) if tot["trees"] > 0 else 0.0
                _tot_vals = total_prefix + ("الإجمالي", f"{tot['قبل']:.2f}", f"{tot['بعد']:.2f}", f"{tot['trees']:.1f}", f"{tot['الخياس']:.2f}", f"{per_tree:.2f}", "-")
                self.op_ledger_total_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                self.op_ledger_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                totals_txt = f"الإجماليات — قبل: {tot['قبل']:.2f}  |  بعد: {tot['بعد']:.2f}  |  الخياس: {tot['الخياس']:.2f} جم"
            elif worker_name == "التلميع النهائي":
                _tot_vals = total_prefix + ("الإجمالي", f"{tot['الخياس']:.2f}", "-")
                self.op_ledger_total_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                self.op_ledger_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                totals_txt = f"الإجماليات — الخياس: {tot['الخياس']:.2f} جم"
            elif cat == "الآلة/المكائن":
                _tot_vals = total_prefix + ("الإجمالي", f"{tot['قبل']:.2f}", f"{tot['بعد']:.2f}", f"{tot['الخياس']:.2f}", "-")
                self.op_ledger_total_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                self.op_ledger_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                totals_txt = f"الإجماليات — قبل: {tot['قبل']:.2f}  |  بعد: {tot['بعد']:.2f}  |  الخياس: {tot['الخياس']:.2f} جم"
            elif cat == "المركبين":
                _tot_vals = total_prefix + ("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot.get('راجع عيار', 0.0):.3f}", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", "-", f"{tot['ذهب صافي']:.2f}", "-")
                self.op_ledger_total_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                self.op_ledger_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                totals_txt = (f"خياس ٨/٤: {en(round(tot['مسموح 8'] + tot['مسموح 4'], 2))}"
                              f"   |   رصيد العامل: {en(tot['ذهب صافي'])} جم")
            else:
                _tot_vals = total_prefix + ("الإجمالي", "-", f"{tot['صرف']:.2f}", f"{tot['قبض']:.2f}", f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['بوليش']:.2f}", f"{tot['ليز']:.2f}", f"{tot['سلك راجع']:.2f}", "-", f"{tot.get('راجع عيار', 0.0):.3f}", f"{tot['فاقد']:.2f}", f"{tot['مسموح 8']:.3f}", f"{tot['مسموح 4']:.3f}", f"{tot['ذهب صافي']:.2f}", "-")
                self.op_ledger_total_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                self.op_ledger_tree.insert("", "end", values=_tot_vals, tags=("total_tag",))
                totals_txt = (f"خياس ٨/٤: {en(round(tot['مسموح 8'] + tot['مسموح 4'], 2))}"
                              f"   |   رصيد العامل: {en(tot['ذهب صافي'])} جم")

        if hasattr(self, 'lbl_op_ledger_totals'):
            self.lbl_op_ledger_totals.configure(text=totals_txt)

        # الانتقال لآخر صف: العامل يهمّه آخر ما سُجّل له، لا أول الصفوف
        try:
            rows = self.op_ledger_tree.get_children()
            if rows:
                self.op_ledger_tree.see(rows[-1])
                self.op_ledger_tree.selection_set(rows[-1])
        except Exception:
            pass

        # الإجمالي محفوظ على الجدول ليستخدمه العرض الكامل
        try:
            children = self.op_ledger_total_tree.get_children()
            if children:
                self.op_ledger_tree._totals_values = self.op_ledger_total_tree.item(
                    children[0], "values")
        except Exception:
            pass

        # كشف المصنعين/المركبين هو أعرض جداول النظام: نضغط أعمدته حسب محتواها
        # الفعلي (رقم الصف أضيق عمود) مع عناوين بسطرين، فتظهر كل الأعمدة معاً
        ledger_key = f"ledger_{cat}"
        self.apply_column_labels(self.op_ledger_tree, ledger_key)
        self.fit_columns_to_content(self.op_ledger_tree, ledger_key, min_width=40, max_width=150)
        # يُربط في كل مرة: الجدول يُعاد إنشاؤه مع كل تحديث، والعلم القديم كان
        # يمنع الربط على الجدول الجديد فيتعطّل تعديل الأسماء بعد أول تحديث
        self.enable_column_rename(self.op_ledger_tree, ledger_key,
                                  on_renamed=self.refresh_op_ledger_table)

    def _on_op_ledger_double_click(self, event):
        """يميّز نقرة عمود (رقم التشغيل) لفتح تعديل سريع لها، وأي عمود آخر يفتح
        نافذة تعديل الحركة الكاملة كما كان."""
        col = self.op_ledger_tree.identify_column(event.x)
        try:
            cols = self.op_ledger_tree["columns"]
            idx = int(col.replace("#", "")) - 1
            col_name = cols[idx] if 0 <= idx < len(cols) else ""
        except (ValueError, IndexError):
            col_name = ""

        if col_name == "رقم التشغيل":
            self.rename_op_ledger_set_number()
        elif self.current_op_cat in ("المصنعين", "المركبين"):
            # النقر المزدوج للعرض، والتعديل من زره المخصّص
            sel = self.op_ledger_tree.selection()
            if sel:
                key = self.op_ledger_group_map.get(sel[0])
                if key is not None:
                    self.open_row_operations_detail(self.clean_name(self.combo_op_name.get()), key)
        else:
            self.op_ledger_edit_selected()

    def rename_op_ledger_set_number(self):
        """تعديل سريع لقيمة (رقم التشغيل) لصف محدد، بلا فتح نافذة التعديل الكاملة"""
        sel = self.op_ledger_tree.selection() if self.op_ledger_tree else []
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الصف المراد تعديل رقم تشغيله أولاً.")
            return
        gkey = self.op_ledger_group_map.get(sel[0])
        if gkey is None:
            return
        if not self.check_edit_permission():
            return

        worker_name = self.clean_name(self.combo_op_name.get())
        current_vals = self.op_ledger_tree.item(sel[0], "values")
        current_set = current_vals[1] if len(current_vals) > 1 else ""

        new_val = ctk.CTkInputDialog(
            title="تعديل رقم التشغيل",
            text=f"رقم التشغيل الجديد لهذا الصف (الحالي: {current_set or '-'})"
        ).get_input()
        if new_val is None:
            return
        new_val = new_val.strip()

        target_ids = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                     if inv.get("الاسم") == worker_name
                     and inv.get("settled_status") == "ACTIVE"
                     and (inv.get("row_number", "") or "") == gkey
                     and self.inv_in_period(inv, self.current_display_month)]
        if not target_ids:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.")
            return

        blocked = False
        for inv_id in target_ids:
            updated = dict(self.invoices[inv_id])
            updated["set_number"] = new_val
            if not self.save_invoice_to_db(inv_id, updated):
                blocked = True
        if blocked:
            return
        self.recalculate_all()
        messagebox.showinfo("تم", f"تم تحديث رقم التشغيل إلى ({new_val or '-'}) لكل حركات هذا الصف.")

    def reassign_op_ledger_row(self, current_worker, cat):
        """يعيد تخصيص كل حركات الصف المحدد لعامل آخر من نفس القسم — عبر
        النقر المزدوج على عمود الاسم المنفصل."""
        sel = self.op_ledger_name_tree.selection() if self.op_ledger_name_tree else []
        if not sel:
            return
        # صفا الأسماء والجدول الرئيسي متطابقا الترتيب دائماً (يُدرَجان معاً سطراً بسطر)
        idx = self.op_ledger_name_tree.index(sel[0])
        main_children = self.op_ledger_tree.get_children()
        if idx >= len(main_children):
            return
        main_iid = main_children[idx]
        gkey = self.op_ledger_group_map.get(main_iid)
        if gkey is None:
            messagebox.showinfo("تنبيه", "هذا السطر إجمالي، لا يمكن إعادة تخصيصه.")
            return
        if not self.check_edit_permission():
            return

        others = [n for n in self.categories.get(cat, []) if n != current_worker]
        if not others:
            messagebox.showinfo("تنبيه", f"لا يوجد عامل آخر مسجَّل في قسم ({cat}) لإعادة التخصيص إليه.")
            return

        win = ctk.CTkToplevel(self)
        win.title("إعادة تخصيص الحركة")
        win.geometry("380x220")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"نقل حركات هذا الصف من ({current_worker}) إلى:",
                     font=("Cairo", 14, "bold"), wraplength=340, justify="center").pack(pady=(20, 10))
        combo = ctk.CTkComboBox(win, values=others, font=("Cairo", 14), justify="right",
                                width=240, height=38, state="readonly")
        combo.set(others[0])
        combo.pack(pady=6)

        def do_reassign():
            new_worker = combo.get()
            target_ids = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                         if inv.get("الاسم") == current_worker
                         and inv.get("settled_status") == "ACTIVE"
                         and (inv.get("row_number", "") or "") == gkey
                         and self.inv_in_period(inv, self.current_display_month)]
            if not target_ids:
                messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة.", parent=win)
                win.destroy()
                return
            blocked = False
            for inv_id in target_ids:
                updated = dict(self.invoices[inv_id])
                updated["الاسم"] = new_worker
                if not self.save_invoice_to_db(inv_id, updated):
                    blocked = True
            win.destroy()
            if blocked:
                return
            self.recalculate_all()
            messagebox.showinfo("تم", f"تم نقل {len(target_ids)} حركة إلى ({new_worker}).")

        ctk.CTkButton(win, text="نقل الحركات", font=("Cairo", 14, "bold"), fg_color="#1e8449",
                      hover_color="#145a32", width=180, height=40, command=do_reassign).pack(pady=16)

    def op_ledger_delete_selected(self):
        if not self.op_ledger_tree:
            messagebox.showwarning("تنبيه", "لا يوجد كشف حركة معروض حالياً.")
            return
        sel = self.op_ledger_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها من الجدول أولاً.")
            return
        ref_key = self.op_ledger_group_map.get(sel[0])
        if ref_key is None:
            return
        worker_name = self.clean_name(self.combo_op_name.get())
        group_by_row = self.current_op_cat in ("المصنعين", "المركبين")

        if group_by_row:
            confirm_label = ref_key if ref_key else "بدون ترقيم"
            prompt = f"هل أنت متأكد من حذف كل عمليات الصف رقم ({confirm_label})؟"
        else:
            prompt = f"هل أنت متأكد من حذف العمليات المنفذة في تاريخ ({ref_key})؟"

        if messagebox.askyesno("تأكيد الحذف", prompt):
            if group_by_row:
                to_delete = [inv["رقم الفاتورة"] for inv in self.invoices.values() if inv.get("الاسم") == worker_name and (inv.get("row_number", "") or "") == ref_key]
            else:
                to_delete = [inv["رقم الفاتورة"] for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("التاريخ") == ref_key]
            any_blocked = False
            for inv_ref in to_delete:
                if not self.delete_invoice_from_db(inv_ref):
                    any_blocked = True
            if any_blocked:
                return  # تم منع حذف بعض/كل الحركات (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            messagebox.showinfo("تم الحذف", "تم حذف العمليات بنجاح وتحديث الأرصدة المرتبطة.")

    ROW_EDIT_FIELDS = {
        "المصنعين": [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض/كسر"),
                     ("المفنش ٨ بالالف", "قبض/٨"), ("المفنش ٤ بالالف", "قبض/٤"),
                     ("البوليش", "بوليش"), ("الليز", "الليز"),
                     ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")],
        "المركبين": [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض"), ("الليز", "الليز"),
                     ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")],
    }

    def open_row_full_edit_dialog(self, worker_name, cat, row_key):
        """تعديل كل خانات صف واحد في كشف المصنعين/المركبين.

        كل عملية في الصف لها حركة مستقلة في الدفاتر. النافذة تعرض قيمة كل
        عملية، والحفظ: يُحدّث الموجود، ويُنشئ ما أُدخل جديداً، ويحذف ما صُفِّر —
        فيبقى الصف مطابقاً لما يظهر في الجدول تماماً.
        """
        if not self.check_edit_permission():
            return

        fields = self.ROW_EDIT_FIELDS.get(cat)
        if not fields:
            return

        row_key = (row_key or "").strip()
        month = self.current_display_month
        row_invs = [inv for inv in self.invoices.values()
                    if inv.get("الاسم") == worker_name
                    and inv.get("settled_status") == "ACTIVE"
                    and (inv.get("row_number", "") or "").strip() == row_key
                    and self.inv_in_period(inv, month)]

        if not row_invs:
            messagebox.showwarning("تنبيه", "لم يعد لهذا الصف حركات مسجّلة. حدّث الشاشة وحاول مجدداً.")
            return

        row_invs.sort(key=lambda x: x.get("رقم الفاتورة", 0))
        base = row_invs[0]
        ref_dt = base.get("التاريخ", "")
        cur_set = next((i.get("set_number", "") for i in row_invs if i.get("set_number")), "")
        cur_note = next((i.get("البيان", "") for i in row_invs if i.get("البيان")), "")

        by_type = {}
        for inv in row_invs:
            by_type.setdefault(inv.get("النوع"), inv)

        win = ctk.CTkToplevel(self)
        win.title(f"تعديل الصف ({row_key or 'بدون ترقيم'}) — {worker_name}")
        win.geometry("560x680")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"✏️ تعديل كل خانات الصف ({row_key or 'بدون ترقيم'})",
                     font=("Cairo", 17, "bold"), text_color="#d4af37").pack(pady=(14, 2))
        ctk.CTkLabel(win, text=f"{worker_name} — {cat}", font=("Cairo", 12),
                     text_color="#8b8f95").pack(pady=(0, 8))

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=4)

        def add_row(label_text, value=""):
            holder = ctk.CTkFrame(body, fg_color="transparent")
            holder.pack(fill="x", pady=4)
            ctk.CTkLabel(holder, text=label_text, font=("Cairo", 14, "bold"),
                         width=160, anchor="e").pack(side="right", padx=8)
            ent = ctk.CTkEntry(holder, justify="center", font=("Cairo", 14), width=150, height=34)
            ent.insert(0, value)
            ent.pack(side="right")
            return ent

        ent_row_no = add_row("رقم الصف", row_key)
        ent_set_no = add_row("رقم التشغيل", cur_set)
        ent_date = add_row("التاريخ", str(ref_dt)[:10])

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)

        entries = {}
        for op_type, label in fields:
            existing = by_type.get(op_type)
            val = f"{existing['الوزن']:g}" if existing else ""
            entries[op_type] = add_row(label, val)

        ttk.Separator(body, orient="horizontal").pack(fill="x", pady=8)
        ent_note = add_row("البيان", cur_note)

        # التنقّل رأسي في نافذة التعديل: Enter و↑ ↓، وEnter في آخر خانة يحفظ
        nav_all = ([ent_row_no, ent_set_no, ent_date]
                   + [entries[t] for t, _ in fields] + [ent_note])
        self.bind_vertical_navigation(nav_all, on_last=lambda: save_row(), window=win)
        self.bind_arrow_navigation(nav_all)

        # التركيز يبدأ في أول خانة، فالتنقّل يعمل فور فتح النافذة
        try:
            nav_all[0].focus_set()
        except Exception:
            pass

        def save_row():
            new_row_no = ent_row_no.get().strip()
            new_set_no = ent_set_no.get().strip()
            new_note = ent_note.get().strip()

            new_date = ent_date.get().strip()
            if len(new_date) < 10 or new_date[4] != "-":
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة YYYY-MM-DD.", parent=win)
                return

            values = {}
            for op_type, label in fields:
                raw = entries[op_type].get().strip()
                if raw == "":
                    values[op_type] = 0.0
                    continue
                try:
                    v = round(float(raw), 2)
                except ValueError:
                    messagebox.showerror("خطأ", f"القيمة في خانة ({label}) ليست رقماً صحيحاً.", parent=win)
                    return
                if v < 0:
                    messagebox.showerror("خطأ", f"لا يمكن إدخال قيمة سالبة في ({label}).", parent=win)
                    return
                values[op_type] = v

            if all(v <= 0 for v in values.values()):
                if not messagebox.askyesno(
                        "تأكيد", "كل الخانات صفر — سيتم حذف حركات هذا الصف بالكامل.\n"
                        "هل تريد المتابعة؟", parent=win):
                    return

            # الوقت يبقى كما هو ما دام اليوم لم يتغيّر، فلا يتبدّل ترتيب الحركة
            old_time = str(ref_dt)[11:] or datetime.datetime.now().strftime("%H:%M:%S")
            new_dt = f"{new_date} {old_time}"

            blocked = False
            for op_type, _label in fields:
                value = values[op_type]
                existing = by_type.get(op_type)

                # العيار قد يكون صفراً بشكل مشروع، فلا يُحذف بسبب ذلك
                keep_zero = (op_type == "العيار بعد الفحص")

                if value > 0 or (keep_zero and existing and entries[op_type].get().strip() != ""):
                    if existing:
                        existing["الوزن"] = value
                        existing["البيان"] = new_note
                        existing["row_number"] = new_row_no
                        existing["set_number"] = new_set_no
                        existing["التاريخ"] = new_dt
                        if not self.save_invoice_to_db(existing["رقم الفاتورة"], existing):
                            blocked = True
                    else:
                        self.invoice_counter += 1
                        inv_data = {
                            "رقم الفاتورة": self.invoice_counter, "التاريخ": new_dt,
                            "الاسم": worker_name, "النوع": op_type, "الوزن": value,
                            "البيان": new_note, "settled_status": "ACTIVE", "trees_count": 0.0,
                            "قبل": 0.0, "بعد": 0.0, "set_number": new_set_no,
                            "row_number": new_row_no,
                        }
                        self.invoices[self.invoice_counter] = inv_data
                        if not self.save_invoice_to_db(self.invoice_counter, inv_data):
                            blocked = True
                elif existing:
                    if not self.delete_invoice_from_db(existing["رقم الفاتورة"]):
                        blocked = True

            # أي حركة أخرى في الصف (نوع غير معروض) تتبع الترقيم الجديد
            # وإلا انفصلت عن صفها وظهرت كصف مستقل
            handled = {t for t, _ in fields}
            for inv in row_invs:
                if inv.get("النوع") in handled or inv.get("رقم الفاتورة") not in self.invoices:
                    continue
                inv["row_number"] = new_row_no
                inv["set_number"] = new_set_no
                inv["التاريخ"] = new_dt
                if not self.save_invoice_to_db(inv["رقم الفاتورة"], inv):
                    blocked = True

            if blocked:
                return
            self.recalculate_all()
            win.destroy()
            messagebox.showinfo("تم", "تم تحديث كل خانات الصف بنجاح.")

        ctk.CTkButton(win, text="💾 حفظ التعديلات", font=("Cairo", 16, "bold"), fg_color="#2ecc71",
                      hover_color="#27ae60", height=44, width=220, command=save_row).pack(pady=12)

    def op_ledger_edit_selected(self):
        if not self.check_edit_permission():
            return
        if not self.op_ledger_tree:
            messagebox.showwarning("تنبيه", "لا يوجد كشف حركة معروض حالياً.")
            return
        sel = self.op_ledger_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها من الجدول أولاً.")
            return
        ref_key = self.op_ledger_group_map.get(sel[0])
        if ref_key is None:
            return

        worker_name = self.clean_name(self.combo_op_name.get())
        worker_category = self.current_op_cat

        # المصنعين والمركبين: نافذة تعديل بكل خانات الصف (النقر المزدوج يعرض الكشف)
        if worker_category in ("المصنعين", "المركبين"):
            self.open_row_full_edit_dialog(worker_name, worker_category, ref_key)
            return

        ref_dt = ref_key
        invs_to_edit = [inv for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("التاريخ") == ref_dt]
        if not invs_to_edit:
            return

        edit_win = ctk.CTkToplevel(self)
        edit_win.title(f"تعديل سجلات الحركة المجمعة - {ref_dt}")
        edit_win.geometry("900x450")
        edit_win.transient(self)
        edit_win.grab_set()
        edit_win.focus_force()

        ctk.CTkLabel(edit_win, text="قم بتعديل الأرقام في أي عمود وسيتحدث النظام بالكامل", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=10)

        fields_frame = ctk.CTkFrame(edit_win)
        fields_frame.pack(fill="both", expand=True, padx=20, pady=10)

        current_vals = {}
        inv_ids = {}
        common_note = ""
        common_set = ""
        for inv in invs_to_edit:
            current_vals[inv["النوع"]] = inv["الوزن"]
            inv_ids[inv["النوع"]] = inv["رقم الفاتورة"]
            if inv["البيان"] and inv["البيان"] not in common_note:
                common_note += (" | " if common_note else "") + inv["البيان"]
            if inv.get("set_number") and not common_set:
                common_set = inv["set_number"]

        fields = [("قبل", "قبل "), ("بعد", "بعد "), ("خياس الاله/المكائن", "الخياس")]

        entries = {}
        for i, (f_key, f_name) in enumerate(fields):
            row = i // 4 * 2
            col = i % 4
            lbl = ctk.CTkLabel(fields_frame, text=f_name, font=("Cairo", 16, "bold"))
            lbl.grid(row=row, column=col, padx=15, pady=(10, 0))
            ent = ctk.CTkEntry(fields_frame, justify="center", font=("Cairo", 16), width=120)

            if worker_category == "الآلة/المكائن" and f_key in ["قبل", "بعد"]:
                val_to_show = 0.0
                for inv in invs_to_edit:
                    val_to_show = inv.get(f_key, 0.0)
                    if val_to_show > 0: break
                ent.insert(0, str(val_to_show))
            else:
                ent.insert(0, str(current_vals.get(f_key, 0.0)))

            ent.grid(row=row+1, column=col, padx=15, pady=(0, 15))
            entries[f_key] = ent

        bottom_frame = ctk.CTkFrame(edit_win, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(bottom_frame, text="رقم التشغيل:", font=("Cairo", 16, "bold")).pack(side="right", padx=5)
        ent_set = ctk.CTkEntry(bottom_frame, justify="center", font=("Cairo", 16), width=120)
        ent_set.insert(0, common_set)
        ent_set.pack(side="right", padx=10)

        ctk.CTkLabel(bottom_frame, text="البيان:", font=("Cairo", 16, "bold")).pack(side="right", padx=5)
        ent_note = ctk.CTkEntry(bottom_frame, justify="right", font=("Cairo", 16), width=350)
        ent_note.insert(0, common_note)
        ent_note.pack(side="right", padx=10)

        def save_advanced_changes():
            new_set = ent_set.get().strip()
            new_note = ent_note.get().strip()

            saved_ok = True
            try:
                w_b = float(entries.get("قبل").get() if "قبل" in entries else 0)
                w_a = float(entries.get("بعد").get() if "بعد" in entries else 0)
                w_k = float(entries.get("خياس الاله/المكائن").get() if "خياس الاله/المكائن" in entries else 0)

                if "خياس الاله/المكائن" in inv_ids:
                    idx = inv_ids["خياس الاله/المكائن"]
                    self.invoices[idx]["قبل"] = w_b
                    self.invoices[idx]["بعد"] = w_a
                    self.invoices[idx]["الوزن"] = w_k
                    self.invoices[idx]["البيان"] = new_note
                    saved_ok = self.save_invoice_to_db(idx, self.invoices[idx])
            except: pass

            if not saved_ok:
                return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            edit_win.destroy()
            messagebox.showinfo("تم", "تم تحديث الأرقام الجديدة لجميع الأعمدة بنجاح!")

        btn_save = ctk.CTkButton(edit_win, text="حفظ التعديلات الشاملة 💾", font=("Cairo", 17, "bold"), fg_color="#2ecc71", hover_color="#27ae60", height=45, command=save_advanced_changes)
        self.apply_edit_lock_to_button(btn_save, edit_win)
        btn_save.pack(pady=15)

    def open_row_operations_detail(self, worker_name, row_num):
        """يعرض تفصيل كل العمليات المسجلة تحت رقم صف معيّن، كل عملية بتاريخها الخاص (المصنعين/المركبين) —
        الضغط المزدوج على أي عملية يفتح شاشة تعديل/حذف تلك العملية تحديداً"""
        invs = [inv for inv in self.invoices.values()
                if inv.get("الاسم") == worker_name and inv.get("settled_status") == "ACTIVE"
                and self.inv_in_period(inv, self.current_display_month)
                and (inv.get("row_number", "") or "") == row_num]
        invs = sorted(invs, key=lambda x: x.get("التاريخ", ""))
        if not invs:
            return

        row_title = row_num if row_num else "بدون ترقيم"

        win = ctk.CTkToplevel(self)
        win.title(f"تفاصيل حركة الصف: {row_title} — {worker_name}")
        win.geometry("780x430")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"عمليات الصف رقم ({row_title})", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(12, 2))
        ctk.CTkLabel(win, text="اضغط ضغطاً مزدوجاً على أي عملية لتعديلها أو حذفها", font=("Cairo", 13), text_color="#aaaaaa").pack(pady=(0, 10))

        cols = ("رقم الفاتورة", "التاريخ", "النوع", "الوزن", "رقم التشغيل", "البيان")
        tree = self.create_standard_treeview(win, cols, height=12)
        for c in cols:
            w = 230 if c == "البيان" else 150 if c == "التاريخ" else 130 if c == "النوع" else 90
            tree.column(c, width=w, anchor="center")

        id_map = {}
        for inv in invs:
            rid = tree.insert("", "end", values=(inv["رقم الفاتورة"], inv["التاريخ"], inv["النوع"], f"{inv['الوزن']:.2f}", inv.get("set_number", ""), inv.get("البيان", "")))
            id_map[rid] = inv["رقم الفاتورة"]

        def on_dclick(event=None):
            sel = tree.selection()
            if not sel: return
            inv_id = id_map.get(sel[0])
            if inv_id is None: return
            win.destroy()
            self.open_edit_invoice_ui(inv_id)

        tree.bind("<Double-1>", on_dclick)

    # =========================================================================

    def build_inquiries_tab(self):
        tab = self.tabview.tab("صناديق الخياس")

        self.dash_frame = ctk.CTkFrame(tab, height=80, corner_radius=10)
        self.dash_frame.pack(fill="x", padx=10, pady=10)
        
        f_prod = ctk.CTkFrame(self.dash_frame, fg_color="transparent")
        f_prod.pack(side="right", padx=15, pady=10)
        self.lbl_dash_production = ctk.CTkLabel(f_prod, text="إنتاج المكينة (مفنش 4): 0.00 جم", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), text_color="#2ecc71")
        self.lbl_dash_production.pack(side="right", padx=8)
        
        f_loss = ctk.CTkFrame(self.dash_frame, fg_color="transparent")
        f_loss.pack(side="right", padx=15, pady=10)
        self.lbl_dash_loss = ctk.CTkLabel(f_loss, text="إجمالي خياس الورشة: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), text_color="#ff7f0e")
        self.lbl_dash_loss.pack(side="right", padx=8)
        btn_loss_details = ctk.CTkButton(f_loss, text="👁️ تفاصيل", width=80, height=30, font=ctk.CTkFont(family="Cairo", size=12, weight="bold"), fg_color="#ff7f0e", hover_color="#b85c0a", command=self.show_losses_details)
        btn_loss_details.pack(side="right", padx=2)

        self.lbl_dash_alert = ctk.CTkLabel(self.dash_frame, text="الخياس الفعلي (المصنعين): 0.00 جم", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37")
        self.lbl_dash_alert.pack(side="left", padx=25, pady=15)

        header_bar = ctk.CTkFrame(tab, fg_color="transparent")
        header_bar.pack(fill="x", padx=10, pady=(5, 0))

        self.current_view_cat = "المصنعين"
        
        btn_add_name = ctk.CTkButton(header_bar, text="➕ إضافة اسم", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), width=110, height=36, command=self.add_new_name_dialog)
        btn_add_name.pack(side="left", padx=5, pady=6)

        btn_undo = ctk.CTkButton(header_bar, text="↩️ تراجع", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                                 fg_color="#7d6608", hover_color="#5a4a06", width=110, height=36,
                                 command=self.undo_last_action)
        btn_undo.pack(side="left", padx=5)
        self.register_undo_button(btn_undo)

        btn_del_name = ctk.CTkButton(header_bar, text="حذف العامل 🗑️", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), fg_color="#8b0000", hover_color="#a52a2a", width=110, height=36, command=self.delete_selected_worker_ui)
        btn_del_name.pack(side="left", padx=5, pady=6)

        # زر عرض الجدول كاملاً — يظهر في كل أقسام صناديق الخياس بما فيها
        # المصنعين والمركبين (كان مضافاً بالخطأ إلى شاشة شجرة الحسابات)
        ctk.CTkButton(header_bar, text="👁️ عرض", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                      fg_color="#1f77b4", hover_color="#144d75", width=90, height=36,
                      command=lambda: self.view_treeview_fullscreen(
                          getattr(self, "tree", None),
                          f"عرض كامل — {self.get_display_label(self.current_view_cat)}")).pack(side="left", padx=5)

        ctk.CTkButton(header_bar, text="↩️ تراجع عن الإقفال",
                      font=ctk.CTkFont(family="Cairo", size=13, weight="bold"),
                      fg_color="#e67e22", hover_color="#b35f10", width=150, height=36,
                      command=self.reopen_khayas_box_dialog).pack(side="left", padx=5)

        btn_close_khayas = ctk.CTkButton(header_bar, text="🔒 إقفال الخياس", font=ctk.CTkFont(family="Cairo", size=13, weight="bold"), fg_color="#8b0000", hover_color="#a52a2a", width=130, height=36, command=lambda: self.close_khayas_box(self.current_view_cat))
        btn_close_khayas.pack(side="left", padx=5, pady=6)

        # صف مستقل كامل العرض لتبويبات/أزرار الصناديق، حتى يتسع لأي عدد صناديق تُضاف مستقبلاً دون ازدحام
        top_bar = ctk.CTkFrame(tab, fg_color="transparent")
        top_bar.pack(fill="x", padx=10, pady=5)

        self.lbl_table_title = ctk.CTkLabel(top_bar, text="عرض أرصدة: المصنعين", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"))
        self.lbl_table_title.pack(side="right", padx=20, pady=10)

        self.khayas_category_bar = ctk.CTkFrame(top_bar, fg_color="transparent")
        self.khayas_category_bar.pack(side="right", fill="x", expand=True)
        self.khayas_category_buttons = {}
        self.refresh_khayas_category_buttons()

        self.summary_bar = ctk.CTkFrame(tab, height=70, corner_radius=10, border_width=2, border_color="#d4af37", fg_color="#2c3e50")
        self.summary_bar.pack(side="bottom", fill="x", padx=10, pady=10)
        
        self.lbl_section_summary = ctk.CTkLabel(self.summary_bar, text="إجمالي الخياس الفعلي للقسم: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=20, weight="bold"), text_color="#f1c40f")
        self.lbl_section_summary.pack(pady=15)

        self.table_frame = ttk.Frame(tab)
        self.table_frame.pack(side="top", fill="both", expand=True, padx=10, pady=5)
        self.tree = None

    def show_losses_details(self):
        win = ctk.CTkToplevel(self)
        win.title("تفصيل فواقد وخياس الورشة")
        win.geometry("900x480")
        win.transient(self)
        win.grab_set()
        win.focus_force()
        
        ctk.CTkLabel(win, text=f"📉 إجمالي الفواقد والخياس مقسمة حسب الأقسام الخمسة للفترة ({self.current_display_month})", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#ff7f0e").pack(pady=15)
        
        cols = ("القسم / الإجمالي", "التصنيف", "إجمالي الخياس الفعلي")
        tree = self.create_standard_treeview(win, cols, height=10)
        
        tree.tag_configure("section_tag", foreground="#f39c12", font=("Cairo", 16, "bold"))
        tree.tag_configure("total_tag", foreground="#e74c3c", font=("Cairo", 17, "bold"))
        
        for c in cols:
            tree.column(c, width=250, anchor="center")
        
        total_workshop = 0.0
        for cat in ["المصنعين", "المركبين"]:
            section_val = self.get_actual_section_khayas(cat)
            tree.insert("", "end", values=(f"إجمالي الفاقد الفعلي لـ ({cat})", cat, f"{section_val:.2f} جم"), tags=("section_tag",))
            total_workshop += section_val

        for cat in self.get_all_stage_categories():
            madin, daen = self.get_stage_totals_for_month(cat, self.current_display_month)
            section_val = round(madin - daen, 2)
            tree.insert("", "end", values=(f"صافي خياس صندوق ({cat}) لهذا الشهر", cat, f"{section_val:.2f} جم"), tags=("section_tag",))
            total_workshop += section_val
            
        tree.insert("", "end", values=("الإجمالي الكلي لخياس وفواقد الورشة (الأقسام الخمسة)", "-", f"{total_workshop:.2f} جم"), tags=("total_tag",))

    def refresh_khayas_category_buttons(self):
        """يعيد بناء أزرار الأقسام بشاشة صناديق الخياس، متضمّناً أي قسم أُضيف ديناميكياً من شجرة الحسابات"""
        for btn in self.khayas_category_buttons.values():
            btn.destroy()
        self.khayas_category_buttons = {}

        cat_defs = [
            ("الكاستنج", f"🏗️ {self.get_display_label('الكاستنج')}"),
            ("المصنعين", self.get_display_label("المصنعين")),
            ("المركبين", self.get_display_label("المركبين")),
            ("التلميع", f"✨ {self.get_display_label('التلميع')}"),
            ("التلميع/البف", f"🪄 {self.get_display_label('التلميع/البف')}"),
            ("خياس الطقوم", "💍 خياس التلميع النهائي"),
        ]
        for stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            cat_defs.append((stage_name, f"➕ {stage_name}"))

        for key, label in cat_defs:
            b = ctk.CTkButton(self.khayas_category_bar, text=label, font=("Cairo", 16, "bold"), width=120, height=45, command=lambda k=key: self.switch_category_view(k))
            b.pack(side="right", padx=5, pady=10)
            self.khayas_category_buttons[key] = b

    def switch_category_view(self, cat):
        self.current_view_cat = cat
        self.lbl_table_title.configure(text=f"عرض أرصدة: {self.get_display_label(cat)}")
        self.refresh_inquiry_table()

    def check_name_exists(self, name):
        for names in self.categories.values():
            if name in names: return True
        return False

    def calculate_single_ledger(self, name, category=None, target_month=None, include_settled=False,
                                invoices=None):
        ledger = {
            "الصرف": 0.0, "القبض": 0.0, "الليز": 0.0, "البوليش": 0.0, "المفنش ٨ بالالف": 0.0, 
            "المفنش ٤ بالالف": 0.0, "السلك الراجع": 0.0, "العيار بعد الفحص": 0.0,
            "قبل": 0.0, "بعد": 0.0, "خياس_مكائن": 0.0, "حجم الإنتاج": 0.0, "المرجع 750": 0.0, "ذهب/باقي": 0.0, "ذهب/صافي": 0.0, "الخياس": 0.0,
            "مسموح 8": 0.0, "مسموح 4": 0.0
        }
        
        if not category:
            for cat, names in self.categories.items():
                if name in names:
                    category = cat
                    break

        m_check = target_month if target_month else self.current_display_month

        # invoices: حركات الفترة مجمّعة مسبقاً (يمررها دفتر الخزينة لتسريع الحساب)
        source = invoices if invoices is not None else self.invoices.values()
        for inv in source:
            if inv.get("التاريخ") and inv["الاسم"] == name and self.inv_in_period(inv, m_check):
                if not include_settled and inv["settled_status"] != "ACTIVE":
                    continue
                
                t = inv["النوع"]
                if t == "صرف ذهب": ledger["الصرف"] += inv["الوزن"]
                elif t == "قبض ذهب": ledger["القبض"] += inv["الوزن"]
                elif t == "الليز": ledger["الليز"] += inv["الوزن"]
                elif t == "البوليش": ledger["البوليش"] += inv["الوزن"]
                elif t == "المفنش ٨ بالالف": ledger["المفنش ٨ بالالف"] += inv["الوزن"]
                elif t == "المفنش ٤ بالالف": ledger["المفنش ٤ بالالف"] += inv["الوزن"]
                elif t == "السلك الراجع": ledger["السلك الراجع"] += inv["الوزن"]
                elif t == "العيار بعد الفحص": ledger["العيار بعد الفحص"] = inv["الوزن"]
                elif t == "خياس الاله/المكائن":
                    ledger["قبل"] += inv.get("قبل", 0.0)
                    ledger["بعد"] += inv.get("بعد", 0.0)
                    ledger["خياس_مكائن"] += inv["الوزن"]

        if ledger["السلك الراجع"] > 0 and ledger["العيار بعد الفحص"] > 0:
            ledger["المرجع 750"] = round((ledger["السلك الراجع"] * ledger["العيار بعد الفحص"]) / 750.0, 2)

        if category == "المركبين":
            ledger["ذهب/باقي"] = round(ledger["الصرف"] - ledger["القبض"] + ledger["الليز"], 2)
            ledger["مسموح 8"] = round(ledger["القبض"] * ALLOWANCE_8, 2)
            ledger["ذهب/صافي"] = round(ledger["ذهب/باقي"] - ledger["مسموح 8"], 2)
            ledger["حجم الإنتاج"] = round(ledger["القبض"], 2)
            ledger["الخياس"] = round(ledger["المرجع 750"] - ledger["ذهب/صافي"], 2)

        elif category == "الآلة/المكائن":
            ledger["الخياس"] = round(ledger["خياس_مكائن"], 2)

        else:
            ledger["ذهب/باقي"] = round(ledger["الصرف"] - ledger["القبض"] - ledger["البوليش"] + ledger["الليز"] - ledger["المفنش ٨ بالالف"] - ledger["المفنش ٤ بالالف"], 2)
            ledger["مسموح 8"] = round(ledger["المفنش ٨ بالالف"] * ALLOWANCE_8, 2)
            ledger["مسموح 4"] = round(ledger["المفنش ٤ بالالف"] * ALLOWANCE_4, 2)
            ledger["ذهب/صافي"] = round(ledger["ذهب/باقي"] - ledger["مسموح 8"] - ledger["مسموح 4"], 2)
            ledger["حجم الإنتاج"] = round(ledger["المفنش ٤ بالالف"] + ledger["المفنش ٨ بالالف"], 2)
            ledger["الخياس"] = round(ledger["المرجع 750"] - ledger["ذهب/صافي"], 2)

        return ledger

    def get_section_khayas_split(self, cat_name, target_month=None, include_settled=False):
        """يفصل خياس قسم المصنعين/المركبين إلى مكوّنيه المحاسبيين:

          • خياس فاقد (٨/٤): إجمالي (مسموح ٨) + (مسموح ٤) — وهو الفاقد المسموح
            به نظامياً على المفنش، لا يُحمَّل على العامل.
          • خياس العمال: مجموع الأرصدة السالبة فقط في عمود الخياس — أي ما زاد
            عن المسموح فعلاً عند العمال. الأرصدة الموجبة لا تُقاصّ السالبة،
            لأن فائض عامل لا يُلغي عجز عامل آخر محاسبياً.

          • راجع العمال: مجموع الأرصدة الموجبة في عمود الخياس — ذهب زائد عاد
            من العمال، فيُخصم من الخياس لأنه ليس فاقداً.

        المعادلة المعتمدة:
            الخياس الفعلي = خياس العمال + فاقد (٨/٤) − راجع العمال

        يرجع: (فاقد_٨_٤، خياس_العمال، راجع_العمال، الخياس_الفعلي)
        """
        allowance = workers = returned = 0.0
        for n in self.categories.get(cat_name, []):
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month,
                                                include_settled=include_settled)
            allowance += res.get("مسموح 8", 0.0) + res.get("مسموح 4", 0.0)
            khayas_val = res.get("الخياس", 0.0)
            if khayas_val < 0:
                workers += abs(khayas_val)
            elif khayas_val > 0:
                returned += khayas_val

        allowance = round(allowance, 2)
        workers = round(workers, 2)
        returned = round(returned, 2)
        return allowance, workers, returned, round(workers + allowance - returned, 2)

    def get_section_khayas_parts(self, cat_name, target_month=None, include_settled=False):
        """مكوّنات معادلة الخياس الفعلي، لعرضها مفصّلة.

        يرجع: (ذهب_باقي، المرجع_٧٥٠، الخياس_الموجب، الخياس_الفعلي)
        وهي نفس المكوّنات التي تحسبها get_actual_section_khayas — مصدر واحد
        فلا ينحرف الشريط البارز عن الرقم المعتمد.
        """
        faqid = marja = pos = 0.0
        for n in self.categories.get(cat_name, []):
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month,
                                                include_settled=include_settled)
            faqid += res.get("ذهب/باقي", 0.0)
            marja += res.get("المرجع 750", 0.0)
            if res.get("الخياس", 0.0) > 0:
                pos += res["الخياس"]
        faqid, marja, pos = round(faqid, 2), round(marja, 2), round(pos, 2)
        return faqid, marja, pos, round(faqid - marja - pos, 2)

    def get_actual_section_khayas(self, cat_name, target_month=None, include_settled=False,
                                  invoices=None):
        # ══════════════════════════════════════════════════════════════
        #  المعادلة المعتمدة للخياس الفعلي (لكل الأقسام بما فيها
        #  المصنعين والمركبين):
        #
        #      إجمالي (ذهب/باقي)
        #    − إجمالي (المرجع ٧٥٠)
        #    − إجمالي (الخياس الموجب فقط)
        #
        #  الخياس الموجب = ذهب عاد زائداً من العامل، فيُخصم لأنه ليس فاقداً.
        #  والأرصدة السالبة لا تُخصم هنا: هي أصلاً داخلة في (ذهب/باقي).
        # ══════════════════════════════════════════════════════════════
        names_list = self.categories.get(cat_name, [])
        sum_faqid = sum_marja = sum_pos_khayas = sum_mach_khayas = 0.0
        
        for n in names_list:
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month,
                                               include_settled=include_settled, invoices=invoices)
            if cat_name == "الآلة/المكائن":
                sum_mach_khayas += res["الخياس"]
            else:
                sum_faqid += res["ذهب/باقي"]
                sum_marja += res["المرجع 750"]
                if res["الخياس"] > 0: sum_pos_khayas += res["الخياس"]
                
        if cat_name == "الآلة/المكائن":
            return round(sum_mach_khayas, 2)
        else:
            return round(sum_faqid - sum_marja - sum_pos_khayas, 2)

    def recalculate_all(self):
        if hasattr(self, 'treasury_tree') and self.treasury_tree:
            for item in self.treasury_tree.get_children():
                self.treasury_tree.delete(item)

        # رصيد أول المدة: صافي كل حركات الخزينة في الفترات **السابقة**.
        # بدونه يبدأ رصيد كل فترة من الصفر فلا يعكس الذهب الفعلي لديك.
        running_balance = self.get_opening_treasury_balance(self.current_display_month)
        self.current_opening_balance = running_balance
        sorted_invoices = sorted(self.invoices.values(), key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)))
        
        total_mufanish_4 = 0.0

        # تصنيف الحركات من المصدر الموحّد نفسه الذي يبني رصيد أول المدة والتقرير
        # الشهري وكشف حساب الخزينة (treasury_bucket) — فلا يختلف الشريط عنها أبداً
        type_sets = self.get_treasury_type_sets()

        for inv in sorted_invoices:
            if not inv.get("التاريخ"): continue
            # فلتر الحالة كان مفقوداً هنا تماماً، فكان رصيد الخزينة يحتسب
            # السطور المعلوماتية (MEMO) والحركات الملغاة — بينما كشف حسابها
            # يفلترها. لذلك اختلف الشريط العلوي عن الكشف. الآن كلاهما بنفس الفلتر.
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            # كل فترة مستقلة بأرصدتها: الشريط يعرض رصيد الفترة المعروضة وحدها
            if not self.inv_in_period(inv, self.current_display_month): continue
            bucket, amount = self.treasury_bucket(inv, type_sets)
            if not bucket:
                continue
            # «رصيد افتتاحي» يُضاف كأي حركة — كان يستبدل الرصيد الجاري كله
            # (running = الوزن) فيمحو رصيد أول المدة وما سبقه من حركات الفترة
            running_balance += amount

            if hasattr(self, 'treasury_tree') and self.treasury_tree:
                w_in = amount if bucket in ("opening", "inbound") else 0.0
                w_qabd = amount if bucket in ("boxes", "journal") and amount > 0 else 0.0
                w_sarf = -amount if bucket in ("boxes", "closed", "journal") and amount < 0 else 0.0
                w_out = -amount if bucket == "sales" else 0.0
                self.treasury_tree.insert("", "end", values=(
                    inv["رقم الفاتورة"], inv["التاريخ"], inv["الاسم"],
                    f"{w_qabd:.2f}" if w_qabd > 0 else "-",
                    f"{w_sarf:.2f}" if w_sarf > 0 else "-",
                    f"{w_in:.2f}" if w_in > 0 else "-",
                    f"{w_out:.2f}" if w_out > 0 else "-",
                    f"{running_balance:.2f} جم"
                ))

        # الخياس الفعلي للمصنعين والمركبين يُخصم من رصيد الخزينة الحي مباشرة،
        # ويتحدّث مع كل عملية (لا ينتظر الإقفال، ولا يعود بعد الإقفال).
        # قيود «حساب الخزينة» اليومية صارت ضمن الحلقة أعلاه — **لفترتها فقط**:
        # كانت تُجمع من كل الفترات وتُضاف لكل فترة معروضة.
        running_balance -= self.get_workers_khayas(self.current_display_month)

        self.current_treasury_balance = round(running_balance, 2)
        if hasattr(self, 'lbl_live_treasury'):
            self.lbl_live_treasury.configure(text=f"رصيد الخزينة الحالي: {en(self.current_treasury_balance)} جم")
        # الرصيد الحالي: يُحسب بعد الخزينة مباشرة لأنه يعتمد عليها
        self.current_total_gold = self.get_total_gold_balance()
        if hasattr(self, 'lbl_total_gold'):
            self.lbl_total_gold.configure(text=f"الرصيد الحالي: {en(self.current_total_gold)} جم")
        self.refresh_screen_info_bar()

        if hasattr(self, 'lbl_gems_stones_balance'):
            self.lbl_gems_stones_balance.configure(text=f"رصيد فصوص وأحجار الحالي: {self.get_material_balance('فصوص وأحجار'):.2f}")
        if hasattr(self, 'lbl_diamond_balance'):
            self.lbl_diamond_balance.configure(text=f"رصيد الألماس الحالي: {self.get_material_balance('الماس'):.2f}")

        for cat_name, names_list in self.categories.items():
            for n in names_list:
                res = self.calculate_single_ledger(n, cat_name)
                
                if cat_name == "المصنعين":
                    total_mufanish_4 += res.get("المفنش ٤ بالالف", 0.0)

        # الخياس الحي (غير المُقفل بعد) يبقى معروضاً بلوحة "إجمالي فواقد الورشة" لأنه معلومة لحظية مفيدة، بصرف النظر عن الإقفال
        total_losses = self.get_actual_section_khayas("المصنعين") + self.get_actual_section_khayas("المركبين")
        for cat in self.get_all_stage_categories():
            madin, daen = self.get_stage_totals_for_month(cat, self.current_display_month)
            total_losses += round(madin - daen, 2)

        if hasattr(self, 'lbl_dash_production'):
            self.lbl_dash_production.configure(text=f"إنتاج المكينة (مفنش 4 للمصنعين): {total_mufanish_4:.2f} جم")
            self.lbl_dash_loss.configure(text=f"إجمالي فواقد الورشة: {total_losses:.2f} جم")

        # تحديث الشاشة المعروضة فقط، وتأجيل البقية إلى لحظة فتحها.
        # الأرصدة أعلاه حُسبت كاملة، فالأرقام صحيحة دائماً — المؤجَّل هو
        # إعادة رسم الجداول غير الظاهرة فقط.
        self.mark_all_screens_dirty()
        self.refresh_visible_screen()

        if getattr(self, 'cloud_sync', None):
            self.cloud_sync.sync_now()

    def sync_all_archives(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT archive_date, category FROM monthly_archive")
            archived_periods = cursor.fetchall()
            
            for arch_date, cat in archived_periods:
                if cat not in self.categories: continue
                
                for worker_name in self.categories[cat]:
                    res = self.calculate_single_ledger(worker_name, cat, target_month=arch_date, include_settled=True)
                    cursor.execute("SELECT id FROM monthly_archive WHERE archive_date = ? AND name = ? AND category = ?", (arch_date, worker_name, cat))
                    row = cursor.fetchone()
                    if row:
                        cursor.execute("""
                            UPDATE monthly_archive 
                            SET sarf=?, qabd=?, leez=?, polish=?, mufanish_8=?, mufanish_4=?, salk_rajia=?, ayar_fahs=?, before_w=?, after_w=?, khayas=?, production=?
                            WHERE id = ?
                        """, (res["الصرف"], res["القبض"], res["الليز"], res["البوليش"], res["المفنش ٨ بالالف"], res["المفنش ٤ بالالف"],
                              res["السلك الراجع"], res["العيار بعد الفحص"], res["قبل"], res["بعد"], res["الخياس"], res["حجم الإنتاج"], row[0]))
                
                actual_khayas = self.get_actual_section_khayas(cat, target_month=arch_date, include_settled=True)
                
                cursor.execute("""
                    UPDATE invoices SET weight = ? WHERE name = ? AND op_type = 'صرف خياس مقفل' AND date_time LIKE ?
                """, (abs(actual_khayas), f"الخياس الفعلي لقسم ({cat})", f"{arch_date}%"))
                
                for inv_id, inv in self.invoices.items():
                    if inv.get("التاريخ") and inv.get("الاسم") == f"الخياس الفعلي لقسم ({cat})" and inv.get("النوع") == "صرف خياس مقفل" and inv.get("التاريخ").startswith(arch_date):
                        self.invoices[inv_id]["الوزن"] = abs(actual_khayas)
            conn.commit()

    def get_stage_config(self, cat):
        """يرجع: نوع حركة المدين، نوع حركة القبض المباشر (أو None)، اسم المسترجع المرتبط بهذا الصندوق"""
        if cat == "خياس الطقوم":
            # صندوق يُغذّى من خانة (الخياس) بشاشة المبيعات/الصادر، ويُعامل محاسبياً كباقي صناديق الخياس
            return "خياس طقوم", "قبض خياس طقوم", "مسترجع خياس الطقوم"
        if cat == "الكاستنج":
            return "صرف كاستنج", "قبض كاستنج", "مسترجع كاستنج"
        elif cat == "التلميع":
            return "صرف تلميع", "قبض تلميع", f"مسترجع {self.get_display_label('التلميع')}"
        elif cat == "التلميع/البف":
            return "صرف تلميع بف", "قبض تلميع بف", f"مسترجع {self.get_display_label('التلميع/البف')}"
        elif cat in self.categories.get("أقسام_خياس_إضافية", []):
            return f"صرف {cat}", f"قبض {cat}", f"مسترجع {cat}"
        return None, None, None

    BOX_DISPLAY_OVERRIDES = {"خياس الطقوم": "خياس التلميع النهائي"}

    def get_display_label(self, cat):
        """الاسم المعروض للمستخدم لأي قسم (بعض الأقسام أعيدت تسميتها لاحقاً، وهذا يوحّد ظهورها بكل الشاشات)"""
        labels = {"التلميع": "التلميع/البف", "التلميع/البف": "البوليش"}
        labels.update(self.BOX_DISPLAY_OVERRIDES)
        return labels.get(cat, cat)

    def get_box_account_name(self, cat):
        """اسم الحساب الخاص بصندوق الخياس (لاستخدامه في القيود اليومية وإقفاله من شاشة الخسائر) - يغطي الأقسام الثابتة والديناميكية"""
        if cat in self.categories.get("أقسام_خياس_إضافية", []):
            return cat
        return {
            "خياس الطقوم": "خياس الطقوم",
            "الكاستنج": "الكاستنج",
            "المصنعين": "صندوق خياس المصنعين",
            "المركبين": "صندوق خياس المركبين",
            "التلميع": "التلميع/البف",
            "التلميع/البف": "البوليش",
        }.get(cat)

    def ensure_default_khayas_boxes(self):
        """لا صناديق تُنشأ تلقائياً بعد الآن (أُلغي إنشاء قسم الصب).

        تُركت الدالة لأن نقاط استدعائها قائمة، وإفراغ قائمتها أوضح وأأمن من
        حذف الاستدعاءات المتفرقة.
        """
        DEFAULTS = []
        added = False
        for box in DEFAULTS:
            existing = self.categories.get("أقسام_خياس_إضافية", [])
            if box in existing:
                continue
            # لا نُنشئه لو كان الاسم مستخدماً لحساب آخر (تفادياً لالتباس محاسبي)
            if box in self.get_account_statement_options():
                continue
            self.categories.setdefault("أقسام_خياس_إضافية", []).append(box)
            self.save_name_to_db(box, "أقسام_خياس_إضافية")
            self.categories.setdefault(box, [])
            added = True
        return added

    PROFIT_SECTION = "ربح/خسارة الطقم"

    # مفاتيح أنواع الخياس الثلاثة ونِسَب استرجاعها الافتراضية
    RECOVERY_KEYS = (("تلميع", "خياس التلميع النهائي"),
                     ("بوليش", "خياس البوليش"),
                     ("مركب", "خياس المركب"))
    RECOVERY_DEFAULT = 0.0   # الافتراضي صفر: لا استرجاع حتى يحدّده المستخدم بنفسه

    def get_recovery_pct(self, key):
        """نسبة استرجاع نوع خياس معيّن (٪) — محفوظة وتبقى بعد إغلاق البرنامج"""
        try:
            return float(self.get_setting(f"recovery_pct_{key}", "") or self.RECOVERY_DEFAULT)
        except (TypeError, ValueError):
            return self.RECOVERY_DEFAULT

    def set_recovery_pct(self, key, value):
        try:
            pct = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return
        self.set_setting(f"recovery_pct_{key}", str(pct))

    def open_recovery_settings(self):
        """نافذة ضبط نسب الاسترجاع الثلاث (تُفتح بالضغط على رأس عمود المسترجع)"""
        win = ctk.CTkToplevel(self)
        win.title("نسب استرجاع الخياس")
        win.geometry("430x360")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="⚙️ نسب استرجاع الخياس", font=("Cairo", 18, "bold"),
                     text_color="#d4af37").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="لكل نوع خياس نسبة تُسترجع منه — والباقي هو الربح",
                     font=("Cairo", 11), text_color="#8b8f95").pack(pady=(0, 12))

        entries = {}
        for key, label in self.RECOVERY_KEYS:
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=28, pady=6)
            ctk.CTkLabel(row, text=label, font=("Cairo", 13, "bold"),
                         width=170, anchor="e").pack(side="right")
            ent = ctk.CTkEntry(row, justify="center", font=("Cairo", 14), width=90, height=34)
            ent.insert(0, f"{self.get_recovery_pct(key):g}")
            ent.pack(side="right", padx=8)
            ctk.CTkLabel(row, text="%", font=("Cairo", 13, "bold")).pack(side="right")
            entries[key] = ent

        def save_and_close():
            for key, _ in self.RECOVERY_KEYS:
                self.set_recovery_pct(key, entries[key].get().strip() or 0)
            win.destroy()
            self.refresh_sets_profit_tab()

        ctk.CTkButton(win, text="💾 حفظ وتطبيق", font=("Cairo", 15, "bold"), fg_color="#1e8449",
                      hover_color="#145a32", width=190, height=42, command=save_and_close).pack(pady=(18, 6))
        ctk.CTkButton(win, text="إلغاء", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=34, command=win.destroy).pack()

    def get_sets_gems_stones(self, month):
        """(الفصوص + الأحجار بعد الخصم) لكل رقم تشغيل، من حركات المبيعات.

        التمييز بين الفصوص والأحجار بعد الخصم يتم بعلامة trees_count == 3
        وهي العلامة المستخدمة أصلاً في هذا النظام لسطر (الأحجار بعد الخصم).
        الأحجار الخام لا تُحتسب — المعتمد محاسبياً هو ما بعد الخصم.
        """
        out = {}
        for inv in self.invoices.values():
            if inv.get("النوع") != "مبيعات فصوص وأحجار":
                continue
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue
            if month and not self.inv_in_period(inv, month):
                continue
            key = inv.get("set_number", "") or "-"
            out[key] = round(out.get(key, 0.0) + inv.get("الوزن", 0.0), 2)
        return out

    def get_sets_profit_rows(self, month):
        """تفصيل كل طقم في شهر: خياساته الثلاثة، إجماليها، مسترجعها، وربحه/خسارته.

        الربح = إجمالي الخياس − المسترجع. الطقم ذو الربح السالب يُعدّ خسارة
        ويخرج كلياً من عمود الربح، فلا يُقاصّ ربح طقم خسارة طقم آخر.
        """
        breakdown = self.get_set_khayas_breakdown(month)
        pct = {k: self.get_recovery_pct(k) / 100.0 for k, _ in self.RECOVERY_KEYS}

        # صافي كل طقم من شاشة المبيعات: هو ما يحدّد إن كان الطقم رابحاً أم خاسراً.
        # (نسبة الاسترجاع مقيّدة بـ ١٠٠٪ فلا يمكن أن تُنتج ربحاً سالباً وحدها،
        #  والطقم الخاسر فعلياً هو الذي خرج صافيه سالباً عند البيع)
        gems = self.get_sets_gems_stones(month)

        rows = []
        for set_no in sorted(breakdown):
            k = breakdown[set_no]
            total = round(k["تلميع"] + k["بوليش"] + k["مركب"], 2)
            recovered = round(k["تلميع"] * pct["تلميع"]
                              + k["بوليش"] * pct["بوليش"]
                              + k["مركب"] * pct["مركب"], 2)
            # صافي/خياس = ما تبقّى من الخياس بعد استرجاع نسبته
            net_khayas = round(total - recovered, 2)
            # فصوص/أحجار = قيمة ما بيع مع الطقم (الفصوص + الأحجار بعد الخصم)
            gems_stones = gems.get(set_no, 0.0)
            # الربح = قيمة الفصوص والأحجار ناقص ما تبقّى على الطقم من خياس
            profit = round(gems_stones - net_khayas, 2)

            is_loss = profit < 0
            rows.append({
                "رقم التشغيل": set_no,
                "تلميع": k["تلميع"], "بوليش": k["بوليش"], "مركب": k["مركب"],
                "إجمالي": total, "المسترجع": recovered,
                "صافي/خياس": net_khayas, "فصوص/أحجار": gems_stones,
                # الطقم الخاسر يخرج كلياً من عمود الربح ويظهر بخسارته وحدها،
                # فلا يُقاصّ ربح طقم خسارة طقم آخر
                "الربح": 0.0 if is_loss else profit,
                "خسارة": round(abs(profit), 2) if is_loss else 0.0,
            })
        return rows

    def get_sets_profit_totals(self, month):
        rows = self.get_sets_profit_rows(month)
        agg = {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع",
                                "صافي/خياس", "فصوص/أحجار", "الربح", "خسارة")}
        for r in rows:
            for k in agg:
                agg[k] = round(agg[k] + r[k], 2)
        agg["عدد"] = len(rows)
        return agg



    def remove_legacy_casting_box(self):
        """يزيل قسم (الصب) الذي كان يُنشأ تلقائياً في نسخة سابقة.

        الحذف يقتصر على القسم الفارغ: لو كانت عليه حركات مسجّلة نُبقيه ونُنبّه،
        لأن حذف حركات محاسبية بلا علم المستخدم غير مقبول.
        """
        try:
            if "الصب" not in self.categories.get("أقسام_خياس_إضافية", []):
                return
            if self.count_box_transactions("الصب") > 0:
                return   # عليه حركات: يبقى، ويستطيع المستخدم حذفه يدوياً
            self.categories["أقسام_خياس_إضافية"].remove("الصب")
            self.categories.pop("الصب", None)
            self.delete_worker_from_db("الصب", "أقسام_خياس_إضافية")
            # القسم اختفى من شجرة الحسابات، فنعيد الحساب ليختفي من كل الشاشات
            # المشتقّة منها (الصناديق، الخسائر، الرصيد الحالي) بلا بقايا
            self.recalculate_all()
        except Exception as e:
            log_cloud_error("تعذّر إزالة قسم الصب القديم", e)

    def build_sets_profit_tab(self):
        """شاشة (ربح/خسارة الطقم) المستقلة — عرض فقط، بلا أي أثر على الخزينة"""
        tab = self.tabview.tab("ربح/خسارة الطقم")

        head = ctk.CTkFrame(tab, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(head, text="📈 ربح/خسارة الطقم", font=("Cairo", 20, "bold"),
                     text_color="#d4af37").pack(side="right", padx=8)
        ctk.CTkLabel(head, text="(عرض فقط — لا يؤثر على الخزينة)",
                     font=("Cairo", 11), text_color="#8b8f95").pack(side="right", padx=6)

        ctk.CTkButton(head, text="⚙️ نسب الاسترجاع", font=("Cairo", 13, "bold"),
                      fg_color="#b8860b", hover_color="#daa520", width=150, height=34,
                      command=self.open_recovery_settings).pack(side="left", padx=5)
        ctk.CTkButton(head, text="👁️ عرض كامل", font=("Cairo", 13, "bold"),
                      fg_color="#1f77b4", hover_color="#144d75", width=130, height=34,
                      command=lambda: self.view_treeview_fullscreen(
                          getattr(self, "sets_profit_tree", None), "ربح/خسارة الطقم")).pack(side="left", padx=5)
        ctk.CTkButton(head, text="🔄 تحديث", font=("Cairo", 13, "bold"),
                      fg_color="#555555", hover_color="#333333", width=110, height=34,
                      command=self.refresh_sets_profit_tab).pack(side="left", padx=5)

        self.lbl_sets_profit_hint = ctk.CTkLabel(
            tab, text="اضغط على رأس عمود (المسترجع) لضبط النسب  •  اضغط على أي صف لعرض تفاصيل أطقمه",
            font=("Cairo", 11), text_color="#8b8f95")
        self.lbl_sets_profit_hint.pack(pady=(0, 6))

        self.sets_profit_table_frame = ttk.Frame(tab)
        self.sets_profit_table_frame.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.sets_profit_tree = None

        self.lbl_sets_profit_summary = ctk.CTkLabel(
            tab, text="", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"),
            text_color="#2ecc71")
        self.lbl_sets_profit_summary.pack(pady=(0, 10))

        self.refresh_sets_profit_tab()

    SETS_PROFIT_COLS = ("التاريخ", "عدد الأطقم", "خياس التلميع النهائي", "خياس البوليش",
                        "خياس المركب", "إجمالي الخياس", "المسترجع", "صافي/خياس",
                        "فصوص/أحجار", "الربح", "خسارة")   # أسماء كاملة صريحة

    def refresh_sets_profit_tab(self):
        if not getattr(self, "sets_profit_table_frame", None):
            return
        for w in self.sets_profit_table_frame.winfo_children():
            w.destroy()

        cols = self.SETS_PROFIT_COLS
        self.sets_profit_tree = self.create_standard_treeview(self.sets_profit_table_frame, cols, height=16)
        self.sets_profit_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.sets_profit_tree.bind("<Double-1>", self._on_sets_profit_row_click)

        # الضغط على رأس عمود المسترجع يفتح ضبط النسب
        def on_head(event):
            if self.sets_profit_tree.identify_region(event.x, event.y) != "heading":
                return
            try:
                idx = int(self.sets_profit_tree.identify_column(event.x).replace("#", "")) - 1
                if 0 <= idx < len(cols) and cols[idx] == "المسترجع":
                    self.open_recovery_settings()
            except (ValueError, IndexError):
                pass

        self.sets_profit_tree.bind("<Button-1>", on_head, add="+")

        months = sorted({self.inv_period(inv) for inv in self.invoices.values()
                         if inv.get("النوع") == "خياس طقوم" and inv.get("التاريخ")})

        self.sets_profit_month_map = {}
        grand = {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع",
                                  "صافي/خياس", "فصوص/أحجار", "الربح", "خسارة")}
        grand_count = 0

        for m in months:
            t = self.get_sets_profit_totals(m)
            if t["عدد"] == 0:
                continue
            grand_count += t["عدد"]
            for k in grand:
                grand[k] = round(grand[k] + t[k], 2)

            row_id = self.sets_profit_tree.insert("", "end", values=(
                m, str(t["عدد"]),
                f"{t['تلميع']:.2f}" if t["تلميع"] else "-",
                f"{t['بوليش']:.2f}" if t["بوليش"] else "-",
                f"{t['مركب']:.2f}" if t["مركب"] else "-",
                f"{t['إجمالي']:.2f}" if t["إجمالي"] else "-",
                f"{t['المسترجع']:.2f}" if t["المسترجع"] else "-",
                f"{t['صافي/خياس']:.2f}" if t["صافي/خياس"] else "-",
                f"{t['فصوص/أحجار']:.2f}" if t["فصوص/أحجار"] else "-",
                f"{t['الربح']:.2f}" if t["الربح"] else "-",
                f"{t['خسارة']:.2f}" if t["خسارة"] else "-",
            ))
            self.sets_profit_month_map[row_id] = m

        if grand_count:
            self.sets_profit_tree.insert("", "end", values=(
                "الإجمالي", str(grand_count),
                f"{grand['تلميع']:.2f}", f"{grand['بوليش']:.2f}", f"{grand['مركب']:.2f}",
                f"{grand['إجمالي']:.2f}", f"{grand['المسترجع']:.2f}",
                f"{grand['صافي/خياس']:.2f}", f"{grand['فصوص/أحجار']:.2f}",
                f"{grand['الربح']:.2f}", f"{grand['خسارة']:.2f}"), tags=("total_tag",))

        self.apply_column_labels(self.sets_profit_tree, "sets_profit")
        self.fit_columns_to_content(self.sets_profit_tree, "sets_profit", min_width=54, max_width=170)
        self.enable_column_rename(self.sets_profit_tree, "sets_profit",
                                  on_renamed=self.refresh_sets_profit_tab)

        pcts = "  |  ".join(f"{label}: {self.get_recovery_pct(k):g}%"
                            for k, label in self.RECOVERY_KEYS)
        self.lbl_sets_profit_summary.configure(
            text=(f"الأطقم: {grand_count}  |  إجمالي الخياس: {en(grand['إجمالي'])}  |  "
                  f"المسترجع: {en(grand['المسترجع'])}  |  صافي/خياس: {en(grand['صافي/خياس'])}  |  "
                  f"فصوص/أحجار: {en(grand['فصوص/أحجار'])}  |  الربح: {en(grand['الربح'])}  |  "
                  f"خسارة: {en(grand['خسارة'])} جم\n{pcts}"))

    def _on_sets_profit_row_click(self, event=None):
        """يفتح كشف أطقم الشهر المحدد بنفس أعمدة الجدول"""
        sel = self.sets_profit_tree.selection() if self.sets_profit_tree else []
        if not sel:
            return
        month = getattr(self, "sets_profit_month_map", {}).get(sel[0])
        if not month:
            return
        self.show_sets_profit_detail(month)

    def show_sets_profit_detail(self, month, losses_only=False):
        """كشف تفصيلي لكل طقم بنفس أعمدة الجدول الرئيسي"""
        rows = self.get_sets_profit_rows(month)
        if losses_only:
            rows = [r for r in rows if r["خسارة"] > 0]
            title = f"أطقم الخسارة — {month}"
        else:
            title = f"تفاصيل أطقم — {month}"

        if not rows:
            messagebox.showinfo("لا يوجد", f"لا توجد أطقم لعرضها في {title}.")
            return

        cols = ("رقم التشغيل", "خياس التلميع النهائي", "خياس البوليش", "خياس المركب",
                "إجمالي الخياس", "المسترجع", "صافي/خياس", "فصوص/أحجار", "الربح", "خسارة")
        data, agg = [], {k: 0.0 for k in ("تلميع", "بوليش", "مركب", "إجمالي", "المسترجع",
                                          "صافي/خياس", "فصوص/أحجار", "الربح", "خسارة")}
        for r in rows:
            for k in agg:
                agg[k] = round(agg[k] + r[k], 2)
            data.append((
                r["رقم التشغيل"],
                f"{r['تلميع']:.2f}" if r["تلميع"] else "-",
                f"{r['بوليش']:.2f}" if r["بوليش"] else "-",
                f"{r['مركب']:.2f}" if r["مركب"] else "-",
                f"{r['إجمالي']:.2f}" if r["إجمالي"] else "-",
                f"{r['المسترجع']:.2f}" if r["المسترجع"] else "-",
                f"{r['صافي/خياس']:.2f}" if r["صافي/خياس"] else "-",
                f"{r['فصوص/أحجار']:.2f}" if r["فصوص/أحجار"] else "-",
                f"{r['الربح']:.2f}" if r["الربح"] else "-",
                f"{r['خسارة']:.2f}" if r["خسارة"] else "-",
            ))

        totals = ("الإجمالي", f"{agg['تلميع']:.2f}", f"{agg['بوليش']:.2f}", f"{agg['مركب']:.2f}",
                  f"{agg['إجمالي']:.2f}", f"{agg['المسترجع']:.2f}",
                  f"{agg['صافي/خياس']:.2f}", f"{agg['فصوص/أحجار']:.2f}",
                  f"{agg['الربح']:.2f}", f"{agg['خسارة']:.2f}")
        self.open_fullscreen_table_view(title, cols, data, totals_values=totals)

    def get_all_stage_categories(self):
        """كل أقسام صناديق الخياس: الثابتة الثلاثة (كاستنج/تلميع/تلميع-بف) + أي قسم أُضيف ديناميكياً من شجرة الحسابات"""
        return ["الكاستنج", "التلميع", "التلميع/البف", "خياس الطقوم"] + list(self.categories.get("أقسام_خياس_إضافية", []))

    def get_all_mustarja_names(self):
        """كل أسماء المسترجع الحالية (لكل صناديق الخياس، ثابتة وديناميكية) - مصدر واحد موحّد لتفادي أي تعارض مع إعادة التسمية"""
        names = []
        for cat in self.get_all_stage_categories():
            _, _, mustarja = self.get_stage_config(cat)
            if mustarja and mustarja not in names:
                names.append(mustarja)
        return names

    def get_stage_totals_for_month(self, cat, month):
        """مدين = إجمالي حركة الصرف/الخياس لهذا الصندوق خلال الشهر، دائن = القبض المباشر (إن وجد) + المسترجع الوارد من شاشة الوارد + أي قيود يومية"""
        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        box_account_name = self.get_box_account_name(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        tot_madin = tot_daen = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if not self.inv_in_period(inv, month): continue
            t = inv.get("النوع")
            if t == madin_type:
                tot_madin += inv["الوزن"]
            elif qabd_type and t == qabd_type:
                tot_daen += inv["الوزن"]
            elif t in in_types and inv.get("الاسم") == mustarja_name:
                tot_daen += inv["الوزن"]
            elif t == "قيد يومي مدين" and inv.get("الاسم") == box_account_name:
                tot_madin += inv["الوزن"]
            elif t == "قيد يومي دائن" and inv.get("الاسم") == box_account_name:
                tot_daen += inv["الوزن"]
        return round(tot_madin, 2), round(tot_daen, 2)

    def get_sales_ops_khayas_total(self, month=None):
        """إجمالي عمود (خياس) في صف الإجمالي بشاشة المبيعات/الصادر ← قسم العمليات.

        يُبنى من **نفس** دالة تجميع الفواتير التي يستخدمها ذلك الجدول
        (get_sale_invoice_groups)، فيكون الرقم مطابقاً لما يراه المستخدم هناك
        حرفياً — لا حساباً موازياً قد ينحرف عنه.
        """
        if month is None:
            month = self.current_display_month
        try:
            groups = self.get_sale_invoice_groups(month)
        except Exception as e:
            log_cloud_error("تعذّر قراءة إجمالي خياس المبيعات", e)
            return 0.0
        return round(sum(g.get("خياس", 0.0) for g in groups), 2)

    def get_box_khayas_cumulative(self, cat, month=None):
        """خياس الصندوق (مدين − دائن).

        month: يقصر الحساب على فترة معيّنة. الافتراضي (None) = الفترة
        المعروضة حالياً، لأن كل فترة مستقلة بأرقامها في هذا النظام.
        تمرير "" صراحةً يعني كل الفترات.
        """
        if month is None:
            month = self.current_display_month

        # خياس التلميع النهائي مصدره شاشة المبيعات/الصادر: نأخذ إجمالي عمود
        # (خياس) من صف الإجمالي هناك، ثم نخصم ما استُرجع من الصندوق وما أُقفل
        # منه — فيبقى الرقم مطابقاً لشاشة المبيعات ومحاسبياً سليماً معاً.
        if cat == "خياس الطقوم":
            sales_total = self.get_sales_ops_khayas_total(month)
            box_account_name = self.get_box_account_name(cat)
            _m, _q, mustarja = self.get_stage_config(cat)
            in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
            recovered = closed = 0.0
            for inv in self.invoices.values():
                if inv.get("settled_status") != "ACTIVE": continue
                if not self.inv_in_period(inv, month): continue
                t = inv.get("النوع")
                if t in in_types and inv.get("الاسم") == mustarja:
                    recovered += inv["الوزن"]
                elif inv.get("الاسم") == box_account_name:
                    if t == "قيد يومي دائن":
                        closed += inv["الوزن"]
                    elif t == "قيد يومي مدين":
                        closed -= inv["الوزن"]
            return round(sales_total - recovered - closed, 2)

        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        box_account_name = self.get_box_account_name(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        tot_madin = tot_daen = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if not self.inv_in_period(inv, month): continue
            t = inv.get("النوع")
            if t == madin_type:
                tot_madin += inv["الوزن"]
            elif qabd_type and t == qabd_type:
                tot_daen += inv["الوزن"]
            elif t in in_types and inv.get("الاسم") == mustarja_name:
                tot_daen += inv["الوزن"]
            elif t == "قيد يومي مدين" and inv.get("الاسم") == box_account_name:
                tot_madin += inv["الوزن"]
            elif t == "قيد يومي دائن" and inv.get("الاسم") == box_account_name:
                tot_daen += inv["الوزن"]
        return round(tot_madin - tot_daen, 2)

    def show_gold_balance_breakdown(self):
        """يعرض من أين تكوّن الرصيد الحالي، ليطمئن المستخدم أن الرقم مفهوم لا سحري"""
        parts = self.get_gold_balance_breakdown()
        total = round(sum(v for _, v in parts), 2)

        win = ctk.CTkToplevel(self)
        win.title("تفصيل الرصيد الحالي")
        win.geometry("430x520")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="💰 تفصيل الرصيد الحالي", font=("Cairo", 18, "bold"),
                     text_color="#2ecc71").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="إجمالي الذهب الذي نملكه الآن، أينما كان",
                     font=("Cairo", 11), text_color="#8b8f95").pack(pady=(0, 10))

        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=6)

        for label, value in parts:
            if abs(value) < 0.005:
                continue      # لا نزحم القائمة بأصفار
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, font=("Cairo", 13, "bold"), anchor="e").pack(side="right")
            ctk.CTkLabel(row, text=f"{value:.2f} جم", font=("Cairo", 13),
                         text_color="#d4af37" if value >= 0 else "#e74c3c").pack(side="left")

        sep = ctk.CTkFrame(win, height=2, fg_color="#d4af37")
        sep.pack(fill="x", padx=18, pady=8)

        ctk.CTkLabel(win, text=f"الإجمالي: {total:.2f} جم", font=("Cairo", 17, "bold"),
                     text_color="#2ecc71").pack(pady=(0, 6))
        ctk.CTkLabel(
            win,
            text="ملاحظة: الخياس المُقفل لا يظهر هنا لأنه رُحّل لحساب الخسائر\nوأصبح فاقداً فعلياً لا ذهباً نملكه.",
            font=("Cairo", 10), text_color="#8b8f95", justify="center").pack(pady=(0, 10))

        ctk.CTkButton(win, text="إغلاق", font=("Cairo", 14, "bold"), width=140, height=38,
                      command=win.destroy).pack(pady=(0, 14))

    def get_total_gold_balance(self):
        """إجمالي الذهب الذي نملكه فعلياً الآن = الخزينة + كل ما هو خارجها في الورش.

        رصيد الخزينة يخصم الذهب الذي خرج لصناديق الخياس (المصنعين، المركبين،
        الكاستنج، التلميع، وأي صندوق آخر) لأنه لم يعد بين يدينا في الخزينة.
        لكنه ما زال ذهبنا. هذه الدالة تعيده لنعرف الإجمالي الحقيقي.

        الخياس المُقفل لا يُحتسب: عند إقفاله يُرحَّل لحساب الخسائر بقيد مزدوج،
        فيصبح فاقداً فعلياً لا ذهباً نملكه.
        """
        # يبني على رصيد الخزينة للفترة المعروضة، والصناديق تُحسب بالفترة أصلاً
        total = getattr(self, "current_treasury_balance", 0.0)

        # المصنعون والمركبون: المعتمد هو **الخياس الفعلي** لكل قسم
        # (ذهب/باقي − المرجع ٧٥٠ − الخياس الموجب)، لا فرق المدين والدائن.
        # يصبح صفراً بعد إقفال خياسهم لأن المُقفل يُرحَّل للخسائر.
        total += self.get_current_unclosed_khayas("المصنعين")
        total += self.get_current_unclosed_khayas("المركبين")

        # كل صناديق الخياس: الثابتة والمضافة حديثاً — تُقرأ ديناميكياً
        # فأي صندوق يُضاف مستقبلاً يدخل في الحساب تلقائياً بلا تعديل كود
        for cat in self.get_all_stage_categories():
            total += self.get_box_khayas_cumulative(cat)

        return round(total, 2)

    def get_gold_balance_breakdown(self):
        """تفصيل الرصيد الحالي لعرضه عند الطلب (تلميح الشريط)"""
        # المصنعون والمركبون بالخياس الفعلي — نفس ما تعرضه لوحة كل قسم
        parts = [("الخزينة", getattr(self, "current_treasury_balance", 0.0)),
                 ("الخياس الفعلي (المصنعين)", self.get_current_unclosed_khayas("المصنعين")),
                 ("الخياس الفعلي (المركبين)", self.get_current_unclosed_khayas("المركبين"))]
        for cat in self.get_all_stage_categories():
            parts.append((self.get_display_label(cat), self.get_box_khayas_cumulative(cat)))
        return parts

    def get_box_closing_entries(self, cat, month=None):
        """قيود إقفال صندوق معيّن (مجمّعة بمرجع القيد)، الأحدث أولاً.

        كل إقفال قيد مزدوج: دائن على حساب الصندوق ومدين على حساب الخسائر،
        ويجمعهما مرجع واحد في حقل set_number.
        """
        box_account = self.get_box_account_name(cat)
        groups = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE":
                continue
            if inv.get("النوع") not in ("قيد يومي دائن", "قيد يومي مدين"):
                continue
            ref = (inv.get("set_number", "") or "").strip()
            if not ref:
                continue
            if month and self.inv_period(inv) != month:
                continue
            g = groups.setdefault(ref, {"ids": [], "amount": 0.0, "date": "",
                                        "bayan": "", "touches_box": False})
            g["ids"].append(inv["رقم الفاتورة"])
            if inv.get("الاسم") == box_account:
                g["touches_box"] = True
                if inv.get("النوع") == "قيد يومي دائن":
                    g["amount"] = round(g["amount"] + inv.get("الوزن", 0.0), 2)
                else:
                    g["amount"] = round(g["amount"] - inv.get("الوزن", 0.0), 2)
            if not g["date"]:
                g["date"] = inv.get("التاريخ", "")
            if not g["bayan"]:
                g["bayan"] = inv.get("البيان", "")

        # قيود الإقفال فقط: التي تمسّ حساب هذا الصندوق فعلاً
        out = [{"ref": r, **g} for r, g in groups.items() if g["touches_box"] and g["amount"]]
        out.sort(key=lambda x: x["date"], reverse=True)
        return out

    def reopen_khayas_box_dialog(self):
        """التراجع عن إقفال خياس: يحذف قيد الإقفال فيعود الخياس للصندوق.

        الأثر المحاسبي كامل: بحذف القيد المزدوج يرجع رصيد الصندوق ويخرج
        المبلغ من حساب الخسائر، ويُعاد حساب النظام كله.
        """
        cat = self.current_view_cat
        display = self.get_display_label(cat)
        entries = self.get_box_closing_entries(cat)

        if not entries:
            messagebox.showinfo("لا يوجد",
                                f"لا توجد إقفالات مسجّلة لصندوق ({display}) يمكن التراجع عنها.")
            return
        if not self.check_edit_permission():
            return

        win = ctk.CTkToplevel(self)
        win.title(f"تراجع عن إقفال — {display}")
        win.geometry("760x600")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"↩️ التراجع عن إقفال ({display})",
                     font=("Cairo", 18, "bold"), text_color="#e67e22").pack(pady=(16, 2))
        ctk.CTkLabel(win, text="اختر الإقفال المراد التراجع عنه — سيعود الخياس للصندوق ويخرج من الخسائر",
                     font=("Cairo", 11), text_color="#8b8f95").pack(pady=(0, 10))

        # الأزرار تُرصف أولاً من الأسفل: لو رُصف الجدول أولاً بـ expand=True
        # التهم المساحة كلها ودُفعت الأزرار خارج النافذة فتعذّر الضغط عليها
        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(side="bottom", pady=(6, 12))

        frame = ttk.Frame(win)
        frame.pack(fill="both", expand=True, padx=16, pady=6)
        cols = ("التاريخ", "البيان", "المبلغ", "المرجع")
        tree = self.create_standard_treeview(frame, cols, height=10)
        for c, w in zip(cols, (150, 220, 110, 110)):
            tree.column(c, width=w, anchor="center")

        for e in entries:
            tree.insert("", "end", iid=e["ref"], values=(
                str(e["date"])[:19], e["bayan"] or "إقفال خياس",
                f"{e['amount']:.2f}", e["ref"]))

        def do_reopen():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "اختر الإقفال المراد التراجع عنه.", parent=win)
                return
            ref = sel[0]
            entry = next((e for e in entries if e["ref"] == ref), None)
            if not entry:
                return

            if not messagebox.askyesno(
                    "تأكيد التراجع",
                    f"سيُحذف قيد الإقفال ({ref}) بمبلغ {en(entry['amount'])} جم.\n\n"
                    f"• يعود الخياس إلى صندوق ({display})\n"
                    f"• ويخرج المبلغ من حساب الخسائر\n\n"
                    "هل تريد المتابعة؟", parent=win):
                return

            # لقطة تراجع قبل التنفيذ (يمكن التراجع عن التراجع نفسه)
            self.push_undo(f"تراجع عن إقفال ({display})")

            deleted = blocked = 0
            for inv_id in entry["ids"]:
                if self.delete_invoice_from_db(inv_id):
                    deleted += 1
                else:
                    blocked += 1
            win.destroy()

            if deleted == 0:
                messagebox.showerror(
                    "تعذّر التراجع",
                    "لم يُحذف أي قيد من قيود هذا الإقفال.\n"
                    "قد يكون حُذف مسبقاً — حدّث الشاشة وحاول مجدداً.")
                return
            self.recalculate_all()
            self.refresh_losses_tab()
            msg = (f"عاد خياس ({display}) بمقدار {en(entry['amount'])} جم إلى الصندوق،\n"
                   "وخرج من حساب الخسائر.")
            if blocked:
                msg += f"\n\nتنبيه: تعذّر حذف {blocked} قيد من قيود هذا الإقفال."
            messagebox.showinfo("تم التراجع", msg)

        ctk.CTkButton(btns, text="↩️ تراجع عن الإقفال المحدد", font=("Cairo", 15, "bold"),
                      fg_color="#e67e22", hover_color="#b35f10", width=260, height=46,
                      command=do_reopen).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="إغلاق", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=46,
                      command=win.destroy).pack(side="left", padx=8)

        # النقر المزدوج على الصف يتراجع عنه مباشرة
        tree.bind("<Double-1>", lambda e: do_reopen())

    def get_box_closed_total(self, cat, month=None):
        """صافي كل الإقفالات المسجّلة لهذا الصندوق (دائن الإقفالات ناقص أي استرجاع لاحق).

        month: يقصر الحساب على فترة معيّنة (تُستخدم في شاشة الخسائر).
        """
        box_account_name = self.get_box_account_name(cat)
        daen_total = madin_total = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if inv.get("الاسم") != box_account_name: continue
            if month and not self.inv_in_period(inv, month): continue
            if inv.get("النوع") == "قيد يومي دائن":
                daen_total += inv["الوزن"]
            elif inv.get("النوع") == "قيد يومي مدين":
                madin_total += inv["الوزن"]
        return round(daen_total - madin_total, 2)

    def get_section_excess_loss(self, cat_name, target_month=None):
        """إجمالي عمود (ذهب/صافي) لكل عمال القسم — وهو ما يظهر أسفل الجدول"""
        total = 0.0
        for n in self.categories.get(cat_name, []):
            res = self.calculate_single_ledger(n, cat_name, target_month=target_month)
            total += res.get("ذهب/صافي", 0.0)
        return round(total, 2)

    def get_gold_at_section(self, cat_name):
        """الذهب الموجود فعلياً عند القسم الآن.

        = إجمالي عمود (ذهب/صافي)، ناقص ما سبق إقفاله.
        بعد الإقفال يصبح صفراً، لأن المُقفل رُحّل لحساب الخسائر ولم يعد ذهباً نملكه.
        الشريط البارز والجدول أسفله لا يتأثران — يبقيان يعرضان الأرقام التفصيلية كما هي.
        """
        if cat_name not in ("المصنعين", "المركبين"):
            return self.get_current_unclosed_khayas(cat_name)

        excess = self.get_section_excess_loss(cat_name)
        closed = self.get_box_closed_total(cat_name)

        # كل الخياس مُقفل: لم يبقَ ذهب عند القسم إطلاقاً
        if self.get_current_unclosed_khayas(cat_name) <= 0.005:
            return 0.0

        if closed > 0:
            return round(max(excess - closed, 0.0), 2)
        return excess

    def get_box_breakdown_text(self, cat, month=None):
        """تفصيل بطاقة الصندوق في شاشة الخسائر: الحالي والمُقفل بمكوّناتهما"""
        if cat not in ("المصنعين", "المركبين"):
            return ""
        month = month or self.current_display_month
        faqid_k, marja_k, pos_k, live = self.get_section_khayas_parts(
            cat, target_month=month)
        closed = self.get_box_closed_total(cat, month=month)
        ratio = (closed / live) if abs(live) > 0.005 else 0.0

        return (
            "الخياس الحالي:\n"
            f"   • ذهب/باقي: {en(faqid_k)}\n"
            f"   • المرجع ٧٥٠: −{en(marja_k)}\n"
            f"   • الخياس الموجب: −{en(pos_k)}\n"
            f"   = الخياس الفعلي: {en(live)}\n"
            "الخياس المُقفل:\n"
            f"   • ذهب/باقي: {en(round(faqid_k * ratio, 2))}\n"
            f"   • المرجع ٧٥٠: −{en(round(marja_k * ratio, 2))}\n"
            f"   • الخياس الموجب: −{en(round(pos_k * ratio, 2))}")

    def get_current_unclosed_khayas(self, cat, month=None):
        """الخياس الحالي غير المُقفل لأي قسم.

        month: يقصر الحساب على فترة معيّنة (شاشة الخسائر تبحث بالفترات).
        """
        # الفترة المعروضة هي الأساس: خياس كل فترة مستقل، ويُخصم منه ما أُقفل
        # **في تلك الفترة وحدها**. خصم إقفالات الفترات السابقة كان يجعل
        # الفترة الجديدة تبدأ برصيد سالب أو صفر خاطئ.
        month = month or self.current_display_month
        if cat in ("المصنعين", "المركبين"):
            live_total = self.get_actual_section_khayas(cat, target_month=month)
            closed_total = self.get_box_closed_total(cat, month=month)
            return round(live_total - closed_total, 2)
        return self.get_box_khayas_cumulative(cat, month=month)

    def get_sets_net_rows(self, month):
        """صافي كل طقم (رقم تشغيل) خلال شهر معيّن، من سطور الصافي المرحّلة
        في شاشة المبيعات/الصادر.

        الفصل المحاسبي المطلوب: الصافي الموجب يُعرض في عمود (الصافي)،
        والسالب يُعرض في عمود (الخسارة) — فلا يظهر رقم واحد في العمودين.
        يرجع: [(رقم التشغيل, الصافي, الخسارة)]
        """
        rows = {}
        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if (inv.get("trees_count", 0.0) or 0.0) != KHAYAS_MARK_NET:
                continue
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue
            if not self.inv_in_period(inv, month):
                continue
            key = inv.get("set_number", "") or "-"
            rows[key] = round(rows.get(key, 0.0) + inv.get("الوزن", 0.0), 2)

        out = []
        for set_no, net in sorted(rows.items()):
            if net < 0:
                out.append((set_no, 0.0, round(abs(net), 2)))
            else:
                out.append((set_no, net, 0.0))
        return out

    def get_sets_net_totals(self, month):
        """إجمالي الصافي وإجمالي الخسارة لشهر معيّن"""
        rows = self.get_sets_net_rows(month)
        return (round(sum(r[1] for r in rows), 2), round(sum(r[2] for r in rows), 2))

    def get_set_khayas_breakdown(self, month):
        """خياسات كل طقم (تلميع نهائي / بوليش / مركب) مفصولة برقم التشغيل"""
        out = {}
        for inv in self.invoices.values():
            if inv.get("النوع") != "خياس طقوم":
                continue
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue
            if not self.inv_in_period(inv, month):
                continue
            mark = inv.get("trees_count", 0.0) or 0.0
            if mark == KHAYAS_MARK_NET:
                continue      # سطر الصافي يُعرض في عموده الخاص
            key = inv.get("set_number", "") or "-"
            d = out.setdefault(key, {"تلميع": 0.0, "بوليش": 0.0, "مركب": 0.0})
            w = inv.get("الوزن", 0.0)
            if mark == KHAYAS_MARK_POLISH:
                d["بوليش"] = round(d["بوليش"] + w, 2)
            elif mark == KHAYAS_MARK_ASSEMBLER:
                d["مركب"] = round(d["مركب"] + w, 2)
            else:
                d["تلميع"] = round(d["تلميع"] + w, 2)
        return out

    def show_sets_net_detail(self, month, losses_only=False):
        """كشف تفصيلي لكل طقم: خياساته الثلاثة + الصافي (أو الخسارة).

        عرض الخياسات بجانب الصافي يوضّح للمستخدم **سبب** الربح أو الخسارة،
        بدل رقم نهائي لا يُفسَّر.
        """
        rows = self.get_sets_net_rows(month)
        khayas = self.get_set_khayas_breakdown(month)

        if losses_only:
            rows = [r for r in rows if r[2] > 0]
            title = f"كشف خسائر الطقوم — {month}"
            value_label = "الخسارة"
            picker = lambda r: r[2]
        else:
            rows = [r for r in rows if r[1] > 0]
            title = f"كشف صافي الطقوم — {month}"
            value_label = "الصافي"
            picker = lambda r: r[1]

        cols = ("رقم التشغيل", "خياس التلميع النهائي", "خياس البوليش",
                "خياس المركب", "إجمالي الخياس", value_label)

        data = []
        tot_final = tot_polish = tot_asm = tot_value = 0.0
        for r in rows:
            k = khayas.get(r[0], {"تلميع": 0.0, "بوليش": 0.0, "مركب": 0.0})
            k_sum = round(k["تلميع"] + k["بوليش"] + k["مركب"], 2)
            value = picker(r)
            tot_final = round(tot_final + k["تلميع"], 2)
            tot_polish = round(tot_polish + k["بوليش"], 2)
            tot_asm = round(tot_asm + k["مركب"], 2)
            tot_value = round(tot_value + value, 2)
            data.append((r[0],
                         f"{k['تلميع']:.2f}" if k["تلميع"] else "-",
                         f"{k['بوليش']:.2f}" if k["بوليش"] else "-",
                         f"{k['مركب']:.2f}" if k["مركب"] else "-",
                         f"{k_sum:.2f}" if k_sum else "-",
                         f"{value:.2f}"))

        if not data:
            messagebox.showinfo("لا يوجد", f"لا توجد بيانات لعرضها في {title}.")
            return

        total = ("الإجمالي", f"{tot_final:.2f}", f"{tot_polish:.2f}", f"{tot_asm:.2f}",
                 f"{round(tot_final + tot_polish + tot_asm, 2):.2f}", f"{tot_value:.2f}")
        self.open_fullscreen_table_view(title, cols, data, totals_values=total)

    def get_stage_monthly_tree_totals(self, cat, month):
        """عدد الأشجار الكلي وخياس كل شجرة لصندوق الكاستنج خلال شهر معيّن.

        نُعيد استخدام نفس منطق تجميع الصفوف المستخدم في مراحل التصنيع
        (collect_stage_ops_rows) حتى يبقى الرقمان متطابقين بين الشاشتين دائماً،
        بدل حساب منفصل قد ينحرف عنه.
        """
        madin_type, qabd_type, _ = self.get_stage_config(cat)
        saved_month = self.current_display_month
        self.current_display_month = month
        try:
            rows = self.collect_stage_ops_rows(madin_type, qabd_type)
        finally:
            self.current_display_month = saved_month

        total_trees = sum(g.get("أشجار", 0.0) for _, _, g in rows)
        total_khayas = sum(round(g["مدين"] - g["دائن"], 2) for _, _, g in rows)
        per_tree = round(total_khayas / total_trees, 2) if total_trees > 0 else 0.0
        return round(total_trees, 2), per_tree

    def render_stage_monthly_inquiry(self):
        """جدول عرض أرصدة صناديق الكاستنج/التلميع/التلميع-البف: شهر وسنة + مدين + دائن + رصيد تراكمي"""
        cat = self.current_view_cat
        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        show_trees = (cat == "الكاستنج")
        show_net = False

        # هذا الفرع يبني رأسه بنفسه، فيجب تنظيف الإطار أولاً وإلا تراكمت
        # الرؤوس مع كل تحديث (الاستدعاء لم يعد يُنظّف قبل التفرّع)
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        self._inquiry_holder = None

        header_row = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header_row.pack(side="top", fill="x", padx=4, pady=(0, 4))
        ctk.CTkButton(header_row, text="👁️ عرض الجدول كاملاً", font=("Cairo", 13, "bold"),
                      fg_color="#1f77b4", hover_color="#144d75", width=170, height=32,
                      command=lambda: self.view_stage_monthly_fullscreen(cat)
                      ).pack(side="left", padx=4)

        tree_container = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        tree_container.pack(side="top", fill="both", expand=True)

        columns = ("الشهر والسنة", "مدين", "دائن", "الرصيد")
        if show_trees:
            columns = columns + ("عدد الأشجار", "خياس كل شجرة")
        if show_net:
            columns = columns + ("الصافي", "الخسارة")
        self.tree, _t, _reused = self.reuse_or_create_tree(tree_container, columns, height=18)
        for col in columns:
            self.tree.column(col, width=170 if col in ("الشهر والسنة", "مدين", "دائن", "الرصيد") else 130,
                             anchor="center")
        if cat == "خياس الطقوم":
            # هذا الصندوق يُغذّى من خانة الخياس بشاشة المبيعات، فتوضيح المسميات أدق للمستخدم
            self.tree.heading("مدين", text="الخياس")
            self.tree.heading("دائن", text="المسترجع/القبض")
            self.tree.heading("الرصيد", text="الرصيد التراكمي")

        self.tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self._on_stage_monthly_click)

        # الفترة المعروضة وحدها: كل فترة مستقلة بعملياتها وأرقامها.
        # كانت تُجمع الشهور من **تاريخ** الحركة، فتظهر فترة ٩ داخل فترة ٨
        # لأن حركات فترة ٨ قد تحمل تواريخ شهر ٩.
        months = set()
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if self.inv_period(inv) != self.current_display_month: continue
            t = inv.get("النوع")
            if not inv.get("التاريخ"): continue
            if t == madin_type or (qabd_type and t == qabd_type) or (t in in_types and inv.get("الاسم") == mustarja_name):
                months.add(self.current_display_month)

        self.stage_month_rows_map = {}
        self._stage_monthly_rows_cache = []
        running = 0.0
        grand_trees = 0.0
        grand_net = grand_loss = 0.0
        for m in sorted(months):
            tot_madin, tot_daen = self.get_stage_totals_for_month(cat, m)
            # خياس التلميع النهائي مصدره الوحيد: إجمالي عمود (خياس) في
            # شاشة المبيعات/الصادر ← قسم العمليات لنفس الفترة
            if cat == "خياس الطقوم":
                tot_madin = self.get_sales_ops_khayas_total(m)
            running += (tot_daen - tot_madin)
            vals = [m, f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"]
            if show_trees:
                m_trees, m_per_tree = self.get_stage_monthly_tree_totals(cat, m)
                grand_trees += m_trees
                vals += [f"{m_trees:g}" if m_trees else "-", f"{m_per_tree:.2f}" if m_trees else "-"]
            if show_net:
                m_net, m_loss = self.get_sets_net_totals(m)
                grand_net += m_net
                grand_loss += m_loss
                vals += [f"{m_net:.2f}" if m_net else "-", f"{m_loss:.2f}" if m_loss else "-"]
            row_id = self.tree.insert("", "end", values=tuple(vals))
            self.stage_month_rows_map[row_id] = m
            self._stage_monthly_rows_cache.append(tuple(vals))

        if months:
            total_vals = ["الرصيد التراكمي الحالي", "-", "-", f"{running:.2f}"]
            if show_trees:
                overall_per_tree = round(running / grand_trees, 2) if grand_trees else 0.0
                total_vals += [f"{grand_trees:g}" if grand_trees else "-",
                               f"{overall_per_tree:.2f}" if grand_trees else "-"]
            if show_net:
                total_vals += [f"{grand_net:.2f}" if grand_net else "-",
                               f"{grand_loss:.2f}" if grand_loss else "-"]
            self.tree.insert("", "end", values=tuple(total_vals), tags=("total_tag",))
            self._stage_monthly_totals_cache = tuple(total_vals)
        else:
            self._stage_monthly_totals_cache = None
        self._stage_monthly_columns_cache = columns

        cur_madin, cur_daen = self.get_stage_totals_for_month(cat, self.current_display_month)
        if hasattr(self, 'lbl_dash_alert'):
            # المصنعون والمركبون: المعروض هو **الخياس الفعلي** بالمعادلة
            # المعتمدة، لا فرق المدين والدائن — فالتسمية تتبع المعنى
            if cat in ("المصنعين", "المركبين"):
                self.lbl_dash_alert.configure(
                    text=f"الخياس الفعلي ({self.get_display_label(cat)}): "
                         f"{self.get_actual_section_khayas(cat):.2f} جم")
            else:
                self.lbl_dash_alert.configure(
                    text=f"الذهب عند {self.get_display_label(cat)}: "
                         f"{round(cur_madin - cur_daen, 2):.2f} جم")
        self.last_computed_actual_khayas = 0.0  # الإقفال الجماعي غير مطبق على هذا القسم
        self.lbl_section_summary.configure(text=f"({cat}) لشهر ({self.current_display_month}): مدين {cur_madin:.2f} | دائن {cur_daen:.2f} | الرصيد التراكمي {running:.2f} جم")

    def show_final_polish_khayas_detail(self, month):
        """كشف خياس التلميع النهائي: كل فاتورة من شاشة المبيعات بخياسها.

        المصدر هو نفس تجميع شاشة المبيعات/العمليات، فيطابق الكشفُ الجدولَ هناك
        فاتورةً بفاتورة، ويطابق مجموعُه عمودَ الخياس في الصندوق.
        """
        groups = [g for g in self.get_sale_invoice_groups(month) if g.get("خياس")]
        if not groups:
            messagebox.showinfo("لا يوجد", f"لا توجد فواتير بخياس في فترة ({month}).")
            return

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "الذهب", "خياس")
        data, tot_gold, tot_khayas = [], 0.0, 0.0
        for g in groups:
            tot_gold = round(tot_gold + g.get("ذهب", 0.0), 2)
            tot_khayas = round(tot_khayas + g.get("خياس", 0.0), 2)
            data.append((
                g.get("manual_no") or "-",
                str(g.get("date", ""))[:16],
                g.get("name", "-"),
                f"{g.get('ذهب', 0.0):.2f}" if g.get("ذهب") else "-",
                f"{g.get('خياس', 0.0):.2f}",
            ))

        totals = ("الإجمالي", "-", f"{len(groups)} فاتورة",
                  f"{tot_gold:.2f}", f"{tot_khayas:.2f}")
        self.open_fullscreen_table_view(
            f"كشف خياس التلميع النهائي — {month}", cols, data, totals_values=totals)

    def _on_stage_monthly_click(self, event=None):
        """الضغط على عمود الصافي أو الخسارة يفتح كشفه التفصيلي،
        وأي عمود آخر يفتح تفاصيل حركات الشهر كالمعتاد."""
        if self.current_view_cat == "خياس الطقوم" and event is not None:
            try:
                cols = self.tree["columns"]
                idx = int(self.tree.identify_column(event.x).replace("#", "")) - 1
                col_name = cols[idx] if 0 <= idx < len(cols) else ""
            except (ValueError, IndexError):
                col_name = ""

            if col_name in ("الصافي", "الخسارة"):
                sel = self.tree.selection()
                if not sel:
                    return
                month = self.stage_month_rows_map.get(sel[0])
                if month:
                    self.show_sets_net_detail(month, losses_only=(col_name == "الخسارة"))
                return

        # خياس التلميع النهائي: الكشف يعرض فواتير المبيعات بخياس كل منها
        if self.current_view_cat == "خياس الطقوم":
            sel = self.tree.selection()
            month = self.stage_month_rows_map.get(sel[0]) if sel else self.current_display_month
            self.show_final_polish_khayas_detail(month or self.current_display_month)
            return

        self.open_stage_month_detail(event)

    def view_stage_monthly_fullscreen(self, cat):
        """يعرض جدول القسم الشهري كاملاً بشاشة ملء الشاشة وصف إجمالي ثابت"""
        rows = getattr(self, "_stage_monthly_rows_cache", [])
        cols = getattr(self, "_stage_monthly_columns_cache", ("الشهر والسنة", "مدين", "دائن", "الرصيد"))
        totals = getattr(self, "_stage_monthly_totals_cache", None)
        self.open_fullscreen_table_view(
            f"عرض كامل — {self.get_display_label(cat)}", cols, rows, totals_values=totals)

    def open_stage_month_detail(self, event=None):
        if not (hasattr(self, 'tree') and self.tree):
            return
        sel = self.tree.selection()
        if not sel:
            return
        month = self.stage_month_rows_map.get(sel[0])
        if not month:
            return
        cat = self.current_view_cat
        madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
        box_account_name = self.get_box_account_name(cat)
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]

        # الرصيد التراكمي (دائن - مدين) حتى بداية هذا الشهر، قبل عملياته
        month_start = f"{month}-01"
        running = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            t = inv.get("النوع")
            dt = inv.get("التاريخ", "")
            if not dt or dt >= month_start: continue
            if t == madin_type:
                running -= inv["الوزن"]
            elif qabd_type and t == qabd_type:
                running += inv["الوزن"]
            elif t in in_types and inv.get("الاسم") == mustarja_name:
                running += inv["الوزن"]
            elif t == "قيد يومي مدين" and inv.get("الاسم") == box_account_name:
                running -= inv["الوزن"]
            elif t == "قيد يومي دائن" and inv.get("الاسم") == box_account_name:
                running += inv["الوزن"]

        # عمليات هذا الشهر بالتفصيل، كل عملية بصف
        recs = []
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            t = inv.get("النوع")
            dt = inv.get("التاريخ", "")
            if not dt or not dt.startswith(month): continue
            set_no = inv.get("set_number", "") or "-"
            if t == madin_type:
                recs.append((dt, inv.get("الاسم", ""), inv["الوزن"], 0.0, inv.get("رقم الفاتورة", 0), set_no))
            elif qabd_type and t == qabd_type:
                recs.append((dt, inv.get("الاسم", ""), 0.0, inv["الوزن"], inv.get("رقم الفاتورة", 0), set_no))
            elif t in in_types and inv.get("الاسم") == mustarja_name:
                recs.append((dt, inv.get("الاسم", ""), 0.0, inv["الوزن"], inv.get("رقم الفاتورة", 0), set_no))
            elif t == "قيد يومي مدين" and inv.get("الاسم") == box_account_name:
                recs.append((dt, "قيد يومي", inv["الوزن"], 0.0, inv.get("رقم الفاتورة", 0), set_no))
            elif t == "قيد يومي دائن" and inv.get("الاسم") == box_account_name:
                recs.append((dt, "قيد يومي", 0.0, inv["الوزن"], inv.get("رقم الفاتورة", 0), set_no))
        recs.sort(key=lambda r: (r[0], r[4]))

        win = ctk.CTkToplevel(self)
        win.title(f"تفاصيل {self.get_display_label(cat)} - {month}")
        win.geometry("700x520")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"تفاصيل حركة ({self.get_display_label(cat)}) لشهر ({month})", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=15)

        cols = ("التاريخ", "رقم التشغيل", "الاسم", "مدين", "دائن", "الرصيد")
        col_widths = {"الاسم": 170, "التاريخ": 140}
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        tree, total_tree = self.create_sticky_total_tree(body, cols, height=13, col_widths=col_widths)
        if cat == "خياس الطقوم":
            tree.heading("مدين", text="الخياس")
            tree.heading("دائن", text="المسترجع/القبض")

        tot_madin = tot_daen = 0.0
        for dt, name, madin_v, daen_v, _, set_no in recs:
            running += (daen_v - madin_v)
            tot_madin = round(tot_madin + madin_v, 2)
            tot_daen = round(tot_daen + daen_v, 2)
            tree.insert("", "end", values=(
                dt, set_no, name,
                f"{madin_v:.2f}" if madin_v else "-",
                f"{daen_v:.2f}" if daen_v else "-",
                f"{running:.2f}"
            ))

        if recs:
            total_tree.insert("", "end", values=("إجمالي الشهر", "-", "-", f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{running:.2f}"), tags=("total_tag",))
        else:
            ctk.CTkLabel(win, text="لا توجد عمليات مسجّلة لهذا الشهر", font=("Cairo", 15, "bold"), text_color="#e74c3c").pack(pady=10)

    def refresh_inquiry_table(self):
        if not (hasattr(self, 'table_frame') and self.table_frame):
            return

        # التفرّع **قبل** التنظيف: كان الإطار يُهدَم ثم يُعاد بناؤه في الفرع
        # الآخر — أي بناءان في كل تحديث، وهو ما يظهر كـ«تكوّن» للشاشة
        if self.current_view_cat in self.get_all_stage_categories():
            self.render_stage_monthly_inquiry()
            return

        holder = getattr(self, "_inquiry_holder", None)
        if holder is None or not holder.winfo_exists():
            for widget in self.table_frame.winfo_children():
                widget.destroy()
            holder = ctk.CTkFrame(self.table_frame, fg_color="transparent")
            holder.pack(fill="both", expand=True)
            self._inquiry_holder = holder

            self._inquiry_hsb = ttk.Scrollbar(holder, orient="horizontal")
            self._inquiry_hsb.pack(side="bottom", fill="x")

            self._inquiry_tree_container = ctk.CTkFrame(holder, fg_color="transparent")
            self._inquiry_tree_container.pack(side="top", fill="both", expand=True)

        hsb = self._inquiry_hsb
        tree_container = self._inquiry_tree_container

        if self.current_view_cat == "الآلة/المكائن":
            columns = ("الاسم", "قبل", "بعد", "الفارق/الخياس")
            self.tree, _t, _reused = self.reuse_or_create_tree(tree_container, columns, height=18)
            for col in columns:
                w = 200 if col == "الاسم" else 150 
                self.tree.column(col, width=w, anchor="center")
        
        elif self.current_view_cat == "المركبين":
            columns = ("الاسم", "الصرف", "القبض", "الليز", "ذهب/باقي", "مسموح 8", "ذهب/صافي", "السلك الراجع", "عيار الفحص", "المرجع 750", "الإنتاج", "الخياس")
            self.tree, _t, _reused = self.reuse_or_create_tree(tree_container, columns, height=18)
            for col in columns:
                w = 120 if col == "الاسم" else 85 
                self.tree.column(col, width=w, anchor="center")
            
        else:
            columns = ("الاسم", "الصرف", "القبض", "الليز", "البوليش", "مفنش 8", "مفنش 4", "ذهب/باقي", "مسموح 8", "مسموح 4", "ذهب/صافي", "السلك الراجع", "عيار الفحص", "المرجع 750", "الإنتاج", "الخياس")
            self.tree, _t, _reused = self.reuse_or_create_tree(tree_container, columns, height=18)
            for col in columns:
                w = 110 if col == "الاسم" else 75 
                self.tree.column(col, width=w, anchor="center")
            if self.current_view_cat == "المصنعين":
                self.tree.heading("القبض", text="قبض/كسر")
                self.tree.heading("مفنش 8", text="قبض/٨")
                self.tree.heading("مفنش 4", text="قبض/٤")

        self.tree.configure(xscrollcommand=hsb.set)
        hsb.configure(command=self.tree.xview)

        # لون واحد أسود لكل أرقام الجدول في جميع الأقسام.
        # الوسمان القديمان (الأخضر/الأحمر) يبقيان معرّفين بنفس اللون الأسود،
        # فتعمل كل مواضع الإدراج القائمة دون تعديلها ولا يتغيّر أي منطق حسابي.
        self.tree.tag_configure("green_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self.tree.tag_configure("red_tag", foreground="#000000", font=("Cairo", 13, "bold"))
        self._inquiry_table_key = f"inquiry_{self.current_view_cat}"
        # صف الإجمالي برتقالي ليتميّز بوضوح عن باقي الصفوف السوداء
        self.tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 14, "bold"))
        self.tree.bind("<Double-1>", self.open_worker_ledger_window)

        tot = {c: 0.0 for c in columns if c != "الاسم"}

        for name in self.categories[self.current_view_cat]:
            res = self.calculate_single_ledger(name, self.current_view_cat)
            
            if self.current_view_cat == "الآلة/المكائن":
                khayas_val = res["الخياس"]
                if name == "التلميع النهائي":
                    tot["الفارق/الخياس"] += khayas_val
                    tag_name = "green_tag" if khayas_val >= 0 else "red_tag"
                    self.tree.insert("", "end", values=(name, "-", "-", f"{khayas_val:.2f}"), tags=(tag_name,))
                else:
                    tot["قبل"] += res['قبل']
                    tot["بعد"] += res['بعد']
                    tot["الفارق/الخياس"] += khayas_val
                    tag_name = "green_tag" if khayas_val >= 0 else "red_tag"
                    self.tree.insert("", "end", values=(name, f"{res['قبل']:.2f}", f"{res['بعد']:.2f}", f"{khayas_val:.2f}"), tags=(tag_name,))
            
            elif self.current_view_cat == "المركبين":
                khayas_val = res["الخياس"]
                tot["الصرف"] += res['الصرف']
                tot["القبض"] += res['القبض']
                tot["الليز"] += res['الليز']
                tot["ذهب/باقي"] += res['ذهب/باقي']
                tot["مسموح 8"] += res['مسموح 8']
                tot["ذهب/صافي"] += res['ذهب/صافي']
                tot["السلك الراجع"] += res['السلك الراجع']
                tot["المرجع 750"] += res['المرجع 750']
                tot["الإنتاج"] += res['حجم الإنتاج']
                tot["الخياس"] += khayas_val

                tag_name = "green_tag" if khayas_val >= 0 else "red_tag"
                self.tree.insert("", "end", values=(
                    name, f"{res['الصرف']:.2f}", f"{res['القبض']:.2f}", f"{res['الليز']:.2f}", f"{res['ذهب/باقي']:.2f}", 
                    f"{res['مسموح 8']:.2f}", f"{res['ذهب/صافي']:.2f}", f"{res['السلك الراجع']:.2f}", 
                    f"{res['العيار بعد الفحص']:.1f}", f"{res['المرجع 750']:.2f}",
                    f"{res['حجم الإنتاج']:.2f}", f"{khayas_val:.2f}"
                ), tags=(tag_name,))
            else:
                khayas_val = res["الخياس"]
                tot["الصرف"] += res['الصرف']
                tot["القبض"] += res['القبض']
                tot["الليز"] += res['الليز']
                tot["البوليش"] += res['البوليش']
                tot["مفنش 8"] += res['المفنش ٨ بالالف']
                tot["مفنش 4"] += res['المفنش ٤ بالالف']
                tot["ذهب/باقي"] += res['ذهب/باقي']
                tot["مسموح 8"] += res['مسموح 8']
                tot["مسموح 4"] += res['مسموح 4']
                tot["ذهب/صافي"] += res['ذهب/صافي']
                tot["السلك الراجع"] += res['السلك الراجع']
                tot["المرجع 750"] += res['المرجع 750']
                tot["الإنتاج"] += res['حجم الإنتاج']
                tot["الخياس"] += khayas_val

                tag_name = "green_tag" if khayas_val >= 0 else "red_tag"
                self.tree.insert("", "end", values=(
                    name, f"{res['الصرف']:.2f}", f"{res['القبض']:.2f}", f"{res['الليز']:.2f}", f"{res['البوليش']:.2f}", 
                    f"{res['المفنش ٨ بالالف']:.2f}", f"{res['المفنش ٤ بالالف']:.2f}", f"{res['ذهب/باقي']:.2f}", 
                    f"{res['مسموح 8']:.2f}", f"{res['مسموح 4']:.2f}", f"{res['ذهب/صافي']:.2f}", 
                    f"{res['السلك الراجع']:.2f}", f"{res['العيار بعد الفحص']:.1f}", f"{res['المرجع 750']:.2f}", 
                    f"{res['حجم الإنتاج']:.2f}", f"{khayas_val:.2f}"
                ), tags=(tag_name,))

        if self.categories[self.current_view_cat]:
            if self.current_view_cat == "الآلة/المكائن":
                self.tree.insert("", "end", values=("الإجمالي العام", f"{tot['قبل']:.2f}", f"{tot['بعد']:.2f}", f"{tot['الفارق/الخياس']:.2f}"), tags=("total_tag",))
            elif self.current_view_cat == "المركبين":
                self.tree.insert("", "end", values=(
                    "الإجمالي العام", f"{tot['الصرف']:.2f}", f"{tot['القبض']:.2f}", f"{tot['الليز']:.2f}", f"{tot['ذهب/باقي']:.2f}",
                    f"{tot['مسموح 8']:.2f}", f"{tot['ذهب/صافي']:.2f}", f"{tot['السلك الراجع']:.2f}", "-",
                    f"{tot['المرجع 750']:.2f}", f"{tot['الإنتاج']:.2f}", f"{tot['الخياس']:.2f}"
                ), tags=("total_tag",))
            else:
                self.tree.insert("", "end", values=(
                    "الإجمالي العام", f"{tot['الصرف']:.2f}", f"{tot['القبض']:.2f}", f"{tot['الليز']:.2f}", f"{tot['البوليش']:.2f}",
                    f"{tot['مفنش 8']:.2f}", f"{tot['مفنش 4']:.2f}", f"{tot['ذهب/باقي']:.2f}", f"{tot['مسموح 8']:.2f}",
                    f"{tot['مسموح 4']:.2f}", f"{tot['ذهب/صافي']:.2f}", f"{tot['السلك الراجع']:.2f}", "-",
                    f"{tot['المرجع 750']:.2f}", f"{tot['الإنتاج']:.2f}", f"{tot['الخياس']:.2f}"
                ), tags=("total_tag",))

        # عناوين بسطرين + عرض محكوم بالمحتوى + تعديل اسم أي عمود بالضغط عليه
        self.apply_column_labels(self.tree, self._inquiry_table_key)
        self.fit_columns_to_content(self.tree, self._inquiry_table_key,
                                     min_width=44, max_width=150)
        self.enable_column_rename(self.tree, self._inquiry_table_key,
                                  on_renamed=self.refresh_inquiry_table)

        # المصنعون والمركبون: اللوحة تعرض **الخياس الفعلي** بالمعادلة المعتمدة،
        # لا (الذهب عند القسم) — فالتسمية والرقم يتبعان المعنى المطلوب.
        if hasattr(self, 'lbl_dash_alert'):
            cat_now = self.current_view_cat
            if cat_now in ("المصنعين", "المركبين"):
                self.lbl_dash_alert.configure(
                    text=f"الخياس الفعلي ({self.get_display_label(cat_now)}): "
                         f"{self.get_actual_section_khayas(cat_now):.2f} جم")
            else:
                self.lbl_dash_alert.configure(
                    text=f"الذهب عند {self.get_display_label(cat_now)}: "
                         f"{self.get_gold_at_section(cat_now):.2f} جم")

        final_actual_khayas = self.get_actual_section_khayas(self.current_view_cat)
        self.last_computed_actual_khayas = final_actual_khayas
        if self.current_view_cat in ("المصنعين", "المركبين"):
            faqid_k, marja_k, pos_k, total_k = self.get_section_khayas_parts(
                self.current_view_cat)
            self.lbl_section_summary.configure(
                text=(f"({self.get_display_label(self.current_view_cat)}) — "
                      f"ذهب/باقي: {en(faqid_k)}  −  "
                      f"المرجع ٧٥٠: {en(marja_k)}  −  "
                      f"الخياس الموجب: {en(pos_k)}  =  "
                      f"الخياس الفعلي: {en(total_k)} جم"))
        else:
            self.lbl_section_summary.configure(text=f"إجمالي الخياس الفعلي لـ ({self.current_view_cat}): {final_actual_khayas:.2f} جم")

    def delete_selected_worker_ui(self):
        sel = self.tree.selection()
        if not sel: return
        worker_name = self.tree.item(sel, "values")[0]
        if worker_name == "الإجمالي العام": return
        
        if messagebox.askyesno(
                "تأكيد حذف الاسم",
                f"هل أنت متأكد من حذف الاسم ({worker_name})؟\n\n"
                "ملاحظة: تُحذف التسمية فقط، أما حركاته المحاسبية فتبقى مسجّلة كما هي.\n"
                "ويمكنك التراجع عن هذه الخطوة بزر (تراجع)."):
            if not self.delete_worker_from_db(worker_name, self.current_view_cat):
                return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
            self.recalculate_all()
            messagebox.showinfo(
                "تم الحذف",
                "تم حذف الاسم. حركاته المحاسبية باقية كما هي،\n"
                "ويمكنك التراجع بزر (تراجع) إن كان الحذف بالخطأ.")

    # =========================================================================
    # --- التعديل الجوهري: كشف العامل المدمج مع عرض إجماليات الأحجار والزركون والألماس ---
    # =========================================================================
    def open_worker_ledger_window(self, event):
        selected_item = self.tree.selection()
        if not selected_item: return
        worker_name = self.tree.item(selected_item, "values")[0]
        if worker_name == "الإجمالي العام": return

        win = ctk.CTkToplevel(self)
        win.title(f"كشف حركة وتفاصيل: {worker_name} للفترة ({self.current_display_month})")
        
        # ضبط حجم النافذة لتكون متوسطة وتستوعب الشريط الإجمالي الجديد بالأسفل
        win.geometry("1100x670")
        
        # الاعتماد على الطرق الصحيحة لإظهار النافذة دون الاختفاء المفاجئ
        win.transient(self)
        win.grab_set()
        win.focus_force()

        t_frame = ttk.Frame(win)
        t_frame.pack(fill="both", expand=True, padx=20, pady=15)

        cat = self.current_view_cat
        if worker_name == "الكاستينج":
            cols = ("رقم الفاتورة", "التاريخ", "قبل", "بعد", "عدد الشجر", "الخياس الكلي", "خياس الشجرة", "البيان")
        elif worker_name == "التلميع النهائي":
            cols = ("رقم الفاتورة", "التاريخ", "الخياس الكلي", "البيان")
        elif cat == "الآلة/المكائن":
            cols = ("رقم الفاتورة", "التاريخ", "قبل", "بعد", "الخياس الكلي", "البيان")
        elif cat == "المركبين":
            cols = ("رقم الفاتورة", "التاريخ", "رقم التشغيل", "صرف", "قبض", "ليز", "سلك راجع", "عيار", "الفاقد اللحظي", "البيان")
        else: # المصنعين
            cols = ("رقم الفاتورة", "التاريخ", "رقم التشغيل", "صرف", "قبض", "ليز", "بوليش", "مفنش 8", "مفنش 4", "سلك راجع", "عيار", "الفاقد اللحظي", "البيان")

        sub_tree = self.create_standard_treeview(t_frame, cols, height=13)
        sub_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))

        if cat == "المصنعين" and worker_name not in ("الكاستينج", "التلميع النهائي"):
            sub_tree.heading("قبض", text="قبض/كسر")
            sub_tree.heading("مفنش 8", text="قبض/٨")
            sub_tree.heading("مفنش 4", text="قبض/٤")

        for c in cols:
            w = 180 if c == "البيان" else 110 if c == "التاريخ" else 90 if c == "رقم الفاتورة" else 85 if c == "رقم التشغيل" else 75
            sub_tree.column(c, width=w, anchor="center")

        worker_invs = [inv for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month)]
        worker_invs = sorted(worker_invs, key=lambda x: x.get("التاريخ", ""))

        # حساب إجماليات تصنيف القبض للنوع المحدد
        type_totals = {"احجار": 0.0, "زركون": 0.0, "الماس": 0.0, "ايطالي": 0.0}
        for inv in worker_invs:
            if inv["النوع"] == "قبض ذهب":
                note_str = inv["البيان"] or ""
                for k_type in type_totals.keys():
                    if k_type in note_str:
                        type_totals[k_type] += inv["الوزن"]
                        break

        # تجميع الذاتي للحركات المجمعة بناءً على بصمة التوقيت والبيان
        grouped_data = {}
        for inv in worker_invs:
            dt = inv["التاريخ"]
            if dt not in grouped_data:
                grouped_data[dt] = {
                    "inv_id": inv["رقم الفاتورة"],
                    "dt": dt,
                    "note": inv["البيان"] or "",
                    "set_number": inv.get("set_number", ""),
                    "صرف": 0.0, "قبض": 0.0, "ليز": 0.0, "بوليش": 0.0,
                    "مفنش 8": 0.0, "مفنش 4": 0.0, "سلك راجع": 0.0, "عيار": 0.0,
                    "قبل": 0.0, "بعد": 0.0, "الخياس": 0.0, "trees": 0.0
                }
                
            data = grouped_data[dt]
            if inv["البيان"] and inv["البيان"] not in data["note"]:
                if data["note"] in ["", "حركة مجمعة"]:
                    data["note"] = inv["البيان"]
                else:
                    data["note"] += " | " + inv["البيان"]
                    
            if not data["set_number"] and inv.get("set_number"):
                data["set_number"] = inv["set_number"]
                    
            t = inv["النوع"]
            w = inv["الوزن"]
            if t == "صرف ذهب": data["صرف"] = w
            elif t == "قبض ذهب": data["قبض"] = w
            elif t == "الليز": data["ليز"] = w
            elif t == "البوليش": data["بوليش"] = w
            elif t == "المفنش ٨ بالالف": data["مفنش 8"] = w
            elif t == "المفنش ٤ بالالف": data["مفنش 4"] = w
            elif t == "السلك الراجع": data["سلك راجع"] = w
            elif t == "العيار بعد الفحص": data["عيار"] = w
            elif t == "خياس الاله/المكائن":
                data["قبل"] = inv.get("قبل", 0.0)
                data["بعد"] = inv.get("بعد", 0.0)
                data["الخياس"] = w
                data["trees"] = inv.get("trees_count", 0.0)

        for dt, data in grouped_data.items():
            inv_str = str(data["inv_id"])
            note = data["note"]
            
            if worker_name == "الكاستينج":
                k_per_tree = round(data["الخياس"] / data["trees"], 2) if data["trees"] > 0 else 0.0
                sub_tree.insert("", "end", values=(inv_str, dt, f"{data['قبل']:.2f}", f"{data['بعد']:.2f}", f"{data['trees']:.1f}", f"{data['الخياس']:.2f}", f"{k_per_tree:.2f}", note))
            elif worker_name == "التلميع النهائي":
                sub_tree.insert("", "end", values=(inv_str, dt, f"{data['الخياس']:.2f}", note))
            elif cat == "الآلة/المكائن":
                sub_tree.insert("", "end", values=(inv_str, dt, f"{data['قبل']:.2f}", f"{data['بعد']:.2f}", f"{data['الخياس']:.2f}", note))
            elif cat == "المركبين":
                faqid = data['صرف'] - data['قبض'] + data['ليز']
                sub_tree.insert("", "end", values=(inv_str, dt, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", note))
            else: # المصنعين
                faqid = data['صرف'] - data['قبض'] - data['بوليش'] + data['ليز'] - data['مفنش 8'] - data['مفنش 4']
                sub_tree.insert("", "end", values=(inv_str, dt, data['set_number'], f"{data['صرف']:.2f}", f"{data['قبض']:.2f}", f"{data['ليز']:.2f}", f"{data['بوليش']:.2f}", f"{data['مفنش 8']:.2f}", f"{data['مفنش 4']:.2f}", f"{data['سلك راجع']:.2f}", f"{data['عيار']:.1f}", f"{faqid:.2f}", note))

        def delete_single_inv():
            sub_sel = sub_tree.selection()
            if not sub_sel: return
            vals = sub_tree.item(sub_sel, "values")
            ref_dt = vals[1]
            
            if messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف العمليات المنفذة في تاريخ ({ref_dt})؟", parent=win):
                to_delete = [inv["رقم الفاتورة"] for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("التاريخ") == ref_dt]
                any_blocked = False
                for inv_ref in to_delete:
                    if not self.delete_invoice_from_db(inv_ref):
                        any_blocked = True
                if any_blocked:
                    return  # تم منع الحذف (رسالة "غير مسموح" ظهرت بالفعل)
                win.destroy()
                self.update_period_selector()
                self.recalculate_all()
                messagebox.showinfo("تم الحذف", "تم حذف العمليات بنجاح.")

        def edit_single_inv():
            if not self.check_edit_permission():
                return
            sub_sel = sub_tree.selection()
            if not sub_sel: return
            vals = sub_tree.item(sub_sel, "values")
            ref_dt = vals[1]
            worker_category = self.current_view_cat
            
            # جلب كل الحركات المرتبطة بهذه البصمة الزمنية
            invs_to_edit = [inv for inv in self.invoices.values() if inv.get("الاسم") == worker_name and inv.get("التاريخ") == ref_dt]
            if not invs_to_edit: return
            
            edit_win = ctk.CTkToplevel(self)
            edit_win.title(f"تعديل سجلات الحركة المجمعة - {ref_dt}")
            edit_win.geometry("900x450")
            
            # إصلاح الخلل: ضمان عدم اختفاء النافذة عبر التركيز الإجباري
            edit_win.transient(win)
            edit_win.grab_set()
            edit_win.focus_force()
            
            ctk.CTkLabel(edit_win, text="قم بتعديل الأرقام في أي عمود وسيتحدث النظام بالكامل", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=10)
            
            fields_frame = ctk.CTkFrame(edit_win)
            fields_frame.pack(fill="both", expand=True, padx=20, pady=10)
            
            current_vals = {}
            inv_ids = {}
            common_note = ""
            common_set = ""
            for inv in invs_to_edit:
                current_vals[inv["النوع"]] = inv["الوزن"]
                inv_ids[inv["النوع"]] = inv["رقم الفاتورة"]
                if inv["البيان"] and inv["البيان"] not in common_note:
                    common_note += (" | " if common_note else "") + inv["البيان"]
                if inv.get("set_number") and not common_set:
                    common_set = inv["set_number"]
                    
            if worker_category == "المركبين":
                fields = [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض"), ("الليز", "الليز"), ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "العيار بعد الفحص")]
            elif worker_category == "المصنعين":
                fields = [("صرف ذهب", "صرف"), ("قبض ذهب", "قبض"), ("الليز", "الليز"), ("البوليش", "بوليش"), ("المفنش ٨ بالالف", "مفنش 8"), ("المفنش ٤ بالالف", "مفنش 4"), ("السلك الراجع", "سلك راجع"), ("العيار بعد الفحص", "عيار بعد الفحص")]
            else: # مكائن
                fields = [("قبل", "قبل التشغيل"), ("بعد", "بعد التشغيل"), ("خياس الاله/المكائن", "الخياس")]
                
            entries = {}
            for i, (f_key, f_name) in enumerate(fields):
                row = i // 4 * 2
                col = i % 4
                lbl = ctk.CTkLabel(fields_frame, text=f_name, font=("Cairo", 16, "bold"))
                lbl.grid(row=row, column=col, padx=15, pady=(10, 0))
                ent = ctk.CTkEntry(fields_frame, justify="center", font=("Cairo", 16), width=120)
                
                if worker_category == "الآلة/المكائن" and f_key in ["قبل", "بعد"]:
                    val_to_show = 0.0
                    for inv in invs_to_edit:
                        val_to_show = inv.get(f_key, 0.0)
                        if val_to_show > 0: break
                    ent.insert(0, str(val_to_show))
                else:
                    ent.insert(0, str(current_vals.get(f_key, 0.0)))
                    
                ent.grid(row=row+1, column=col, padx=15, pady=(0, 15))
                entries[f_key] = ent
                
            bottom_frame = ctk.CTkFrame(edit_win, fg_color="transparent")
            bottom_frame.pack(fill="x", padx=20, pady=5)
            
            ctk.CTkLabel(bottom_frame, text="رقم التشغيل:", font=("Cairo", 16, "bold")).pack(side="right", padx=5)
            ent_set = ctk.CTkEntry(bottom_frame, justify="center", font=("Cairo", 16), width=120)
            ent_set.insert(0, common_set)
            ent_set.pack(side="right", padx=10)
            
            ctk.CTkLabel(bottom_frame, text="البيان:", font=("Cairo", 16, "bold")).pack(side="right", padx=5)
            ent_note = ctk.CTkEntry(bottom_frame, justify="right", font=("Cairo", 16), width=350)
            ent_note.insert(0, common_note)
            ent_note.pack(side="right", padx=10)
            
            def save_advanced_changes():
                new_set = ent_set.get().strip()
                new_note = ent_note.get().strip()
                any_blocked = False
                
                if worker_category == "الآلة/المكائن":
                    try:
                        w_b = float(entries.get("قبل").get() if "قبل" in entries else 0)
                        w_a = float(entries.get("بعد").get() if "بعد" in entries else 0)
                        w_k = float(entries.get("خياس الاله/المكائن").get() if "خياس الاله/المكائن" in entries else 0)
                        
                        if "خياس الاله/المكائن" in inv_ids:
                            idx = inv_ids["خياس الاله/المكائن"]
                            self.invoices[idx]["قبل"] = w_b
                            self.invoices[idx]["بعد"] = w_a
                            self.invoices[idx]["الوزن"] = w_k
                            self.invoices[idx]["البيان"] = new_note
                            if not self.save_invoice_to_db(idx, self.invoices[idx]):
                                any_blocked = True
                    except: pass
                else:
                    for f_key, ent in entries.items():
                        try:
                            val = round(float(ent.get()), 2)
                        except:
                            val = 0.0
                            
                        if val > 0:
                            if f_key in inv_ids:
                                idx = inv_ids[f_key]
                                self.invoices[idx]["الوزن"] = val
                                self.invoices[idx]["set_number"] = new_set
                                self.invoices[idx]["البيان"] = new_note
                                if not self.save_invoice_to_db(idx, self.invoices[idx]):
                                    any_blocked = True
                            else:
                                self.invoice_counter += 1
                                inv_data = {
                                    "رقم الفاتورة": self.invoice_counter, "التاريخ": ref_dt,
                                    "الاسم": worker_name, "النوع": f_key, "الوزن": val,
                                    "البيان": new_note, "settled_status": "ACTIVE",
                                    "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": new_set
                                }
                                self.invoices[self.invoice_counter] = inv_data
                                self.save_invoice_to_db(self.invoice_counter, inv_data)
                        elif val == 0 and f_key in inv_ids:
                            if f_key != "العيار بعد الفحص":
                                idx = inv_ids[f_key]
                                if not self.delete_invoice_from_db(idx):
                                    any_blocked = True
                
                if any_blocked:
                    return  # تم منع تعديل/حذف حركة موجودة (رسالة "غير مسموح" ظهرت بالفعل)
                self.recalculate_all()
                edit_win.destroy()
                win.destroy()
                messagebox.showinfo("تم", "تم تحديث الأرقام الجديدة لجميع الأعمدة بنجاح!")
                
            btn_save = ctk.CTkButton(edit_win, text="حفظ التعديلات الشاملة 💾", font=("Cairo", 17, "bold"), fg_color="#2ecc71", hover_color="#27ae60", height=45, command=save_advanced_changes)
            self.apply_edit_lock_to_button(btn_save, edit_win)
            btn_save.pack(pady=15)

        # شريط عرض الإجماليات أسفل النافذة باللغة العربية بناءً على طلبك وخط عريض وواضح
        totals_frame = ctk.CTkFrame(win, fg_color="#2c3e50", corner_radius=8, height=45)
        totals_frame.pack(fill="x", padx=20, pady=(5, 5))
        
        lbl_st = ctk.CTkLabel(totals_frame, text=f"💎 إجمالي الأحجار: {type_totals['احجار']:.2f}", font=("Cairo", 18, "bold"), text_color="#1f77b4")
        lbl_st.pack(side="right", padx=25, pady=8)
        
        lbl_zi = ctk.CTkLabel(totals_frame, text=f"✨ إجمالي الزركون: {type_totals['زركون']:.2f}", font=("Cairo", 18, "bold"), text_color="#e67e22")
        lbl_zi.pack(side="right", padx=25, pady=8)
        
        lbl_di = ctk.CTkLabel(totals_frame, text=f"⭐ إجمالي الألماس: {type_totals['الماس']:.2f}", font=("Cairo", 18, "bold"), text_color="#9b59b6")
        lbl_di.pack(side="right", padx=25, pady=8)

        lbl_it = ctk.CTkLabel(totals_frame, text=f"🔱 إجمالي إيطالي: {type_totals['ايطالي']:.2f}", font=("Cairo", 18, "bold"), text_color="#2ecc71")
        lbl_it.pack(side="right", padx=25, pady=8)

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", pady=15)
        
        btn_delete = ctk.CTkButton(btn_frame, text="حذف العملية 🗑️", font=("Cairo", 16, "bold"), fg_color="#8b0000", hover_color="#a52a2a", height=45, command=delete_single_inv)
        btn_delete.pack(side="left", expand=True, padx=15)

        btn_edit = ctk.CTkButton(btn_frame, text="تعديل الحركة ✏️", font=("Cairo", 16, "bold"), fg_color="#b8860b", hover_color="#daa520", height=45, command=edit_single_inv)
        btn_edit.pack(side="left", expand=True, padx=15)

    # =========================================================================
    # --- التعديل الجوهري: نافذة البحث المتقدم برقم الفاتورة وتعديله وحذفه ---
    # =========================================================================
    def search_op_number_window(self):
        op_num = self.entry_search_op.get().strip()
        if not op_num:
            messagebox.showwarning("تنبيه", "الرجاء إدخال رقم التشغيل أولاً في الخانة المخصصة.")
            return

        win = ctk.CTkToplevel(self)
        win.title(f"تقرير وتعديل رقم التشغيل: {op_num}")
        win.geometry("1000x620")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        lbl_title = ctk.CTkLabel(win, text=f"📋 كشف تفصيلي وتعديل لرقم التشغيل: ({op_num})", font=("Cairo", 20, "bold"), text_color="#d4af37")
        lbl_title.pack(pady=10)

        t_frame = ttk.Frame(win)
        t_frame.pack(fill="both", expand=True, padx=20, pady=10)

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "البيان")
        tree = ttk.Treeview(t_frame, columns=cols, show="headings", height=9)
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=160 if c in ["التاريخ", "البيان"] else 120, anchor="center")
        
        vsb = ttk.Scrollbar(t_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        def refresh_search_tree():
            for item in tree.get_children():
                tree.delete(item)
            
            records_to_show = [inv for inv in self.invoices.values() if str(inv.get("set_number", "")).strip() == op_num]
            
            tot_sarf = 0.0
            tot_qabd = 0.0
            for inv in sorted(records_to_show, key=lambda x: (x["التاريخ"], x["رقم الفاتورة"])):
                tree.insert("", "end", values=(
                    inv["رقم الفاتورة"], inv["التاريخ"], inv["الاسم"],
                    inv["النوع"], f"{inv['الوزن']:.2f}", inv["البيان"]
                ))
                if inv["النوع"] == "صرف ذهب": tot_sarf += inv['الوزن']
                elif inv["النوع"] == "قبض ذهب": tot_qabd += inv['الوزن']
                
            tree.tag_configure("total_tag", foreground="#2ecc71", font=("Cairo", 15, "bold"))
            tree.insert("", "end", values=("الإجمالي", "-", "-", "صرف:", f"{tot_sarf:.2f}", f"قبض: {tot_qabd:.2f}"), tags=("total_tag",))

        refresh_search_tree()

        edit_frame = ctk.CTkFrame(win)
        edit_frame.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(edit_frame, text="الوزن:", font=("Cairo", 14, "bold")).grid(row=0, column=5, padx=5, pady=8)
        ent_weight = ctk.CTkEntry(edit_frame, width=110, justify="center")
        ent_weight.grid(row=0, column=4, padx=5, pady=8)

        ctk.CTkLabel(edit_frame, text="رقم التشغيل:", font=("Cairo", 14, "bold")).grid(row=0, column=3, padx=5, pady=8)
        ent_set_num = ctk.CTkEntry(edit_frame, width=110, justify="center")
        ent_set_num.grid(row=0, column=2, padx=5, pady=8)

        ctk.CTkLabel(edit_frame, text="البيان:", font=("Cairo", 14, "bold")).grid(row=0, column=1, padx=5, pady=8)
        ent_note = ctk.CTkEntry(edit_frame, width=340, justify="right")
        ent_note.grid(row=0, column=0, padx=5, pady=8)

        def on_tree_select(event):
            sel = tree.selection()
            if not sel: return
            vals = tree.item(sel, "values")
            if vals[0] == "الإجمالي": return
            
            inv_id = int(vals[0])
            inv = self.invoices[inv_id]
            
            ent_weight.delete(0, 'end')
            ent_weight.insert(0, str(inv["الوزن"]))
            
            ent_set_num.delete(0, 'end')
            ent_set_num.insert(0, str(inv.get("set_number", "")))
            
            ent_note.delete(0, 'end')
            ent_note.insert(0, str(inv["البيان"]))

        tree.bind("<<TreeviewSelect>>", on_tree_select)

        btn_action_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_action_frame.pack(fill="x", padx=20, pady=10)

        def save_modifications():
            sel = tree.selection()
            if not sel or tree.item(sel, "values")[0] == "الإجمالي":
                messagebox.showwarning("تنبيه", "الرجاء النقر على السجل المطلوب من الجدول أولاً.", parent=win)
                return
            try:
                inv_id = int(tree.item(sel, "values")[0])
                new_w = float(ent_weight.get().strip())
                new_set = ent_set_num.get().strip()
                new_nt = ent_note.get().strip()

                self.invoices[inv_id]["الوزن"] = new_w
                self.invoices[inv_id]["set_number"] = new_set
                self.invoices[inv_id]["البيان"] = new_nt

                if not self.save_invoice_to_db(inv_id, self.invoices[inv_id]):
                    return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
                self.recalculate_all()  
                refresh_search_tree()
                
                if hasattr(self, 'refresh_inquiry_table'):
                    self.refresh_inquiry_table()
                    
                messagebox.showinfo("تعديل ناجح", "تم تحديث بيانات التشغيل وتعديل الأرقام تلقائياً في الخزينة وكشف العامل.", parent=win)
            except ValueError:
                messagebox.showerror("خطأ إدخال", "يرجى كتابة أرقام صحيحة.", parent=win)

        def delete_record():
            sel = tree.selection()
            if not sel or tree.item(sel, "values")[0] == "الإجمالي":
                messagebox.showwarning("تنبيه", "الرجاء تحديد السجل المراد مسحه.", parent=win)
                return
            inv_id = int(tree.item(sel, "values")[0])
            if messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف القيد رقم {inv_id}؟", parent=win):
                if not self.delete_invoice_from_db(inv_id):
                    return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
                self.recalculate_all()  
                refresh_search_tree()
                ent_weight.delete(0, 'end')
                ent_set_num.delete(0, 'end')
                ent_note.delete(0, 'end')
                
                if hasattr(self, 'refresh_inquiry_table'):
                    self.refresh_inquiry_table()
                    
                messagebox.showinfo("تم الحذف", "تم حذف الحركة المطلوبة وتحديث الأرصدة التلقائي.", parent=win)

        btn_save = ctk.CTkButton(btn_action_frame, text="حفظ التعديلات 💾", font=("Cairo", 15, "bold"), fg_color="#2ecc71", hover_color="#27ae60", command=save_modifications)
        self.apply_edit_lock_to_button(btn_save, win)
        btn_save.pack(side="right", padx=10, expand=True, fill="x")

        btn_del = ctk.CTkButton(btn_action_frame, text="حذف السجل 🗑️", font=("Cairo", 15, "bold"), fg_color="#e74c3c", hover_color="#c0392b", command=delete_record)
        btn_del.pack(side="left", padx=10, expand=True, fill="x")

    def bulk_settle_current_category(self):
        target_list = self.categories[self.current_view_cat]
        if not target_list: return

        actual_khayas = getattr(self, 'last_computed_actual_khayas', 0.0)

        if not messagebox.askyesno("تأكيد الإقفال", f"هل أنت متأكد من إقفال قسم ({self.current_view_cat}) لشهر {self.current_display_month}؟"): return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            self.invoice_counter += 1
            treasury_inv_id = self.invoice_counter
            settle_date_time = f"{self.current_display_month}-28 23:59"
            cursor.execute("""
                INSERT INTO invoices (invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'ACTIVE')
            """, (treasury_inv_id, settle_date_time, 
                  f"الخياس الفعلي لقسم ({self.current_view_cat})", "صرف خياس مقفل", abs(actual_khayas), 
                  f"إقفال شهري عام للقسم عن فترة ({self.current_display_month})"))
            
            self.invoices[treasury_inv_id] = {
                "رقم الفاتورة": treasury_inv_id, "التاريخ": settle_date_time,
                "الاسم": f"الخياس الفعلي لقسم ({self.current_view_cat})", "النوع": "صرف خياس مقفل",
                "الوزن": abs(actual_khayas), "قبل": 0.0, "بعد": 0.0, "trees_count": 0.0,
                "البيان": f"إقفال شهري للقسم", "settled_status": "ACTIVE"
            }

            for name in target_list:
                res = self.calculate_single_ledger(name, self.current_view_cat)
                prod_val = res["حجم الإنتاج"]
                khayas_val = res["الخياس"]
                
                if self.current_view_cat == "الآلة/المكائن":
                    if res["قبل"] == 0 and res["بعد"] == 0 and khayas_val == 0: continue
                else:
                    if khayas_val == 0 and res["الصرف"] == 0 and prod_val == 0: continue

                cursor.execute("""
                    INSERT INTO monthly_archive (archive_date, name, category, sarf, qabd, leez, polish, mufanish_8, mufanish_4, salk_rajia, ayar_fahs, before_w, after_w, khayas, production, note, linked_inv_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (self.current_display_month, name, self.current_view_cat, 
                      res["الصرف"], res["القبض"], res["الليز"], res["البوليش"], res["المفنش ٨ بالالف"], res["المفنش ٤ بالالف"],
                      res["السلك الراجع"], res["العيار بعد الفحص"], res["قبل"], res["بعد"], khayas_val, prod_val, "أرشيف", treasury_inv_id))
                
                for inv_id, inv in self.invoices.items():
                    if inv.get("الاسم") == name and inv.get("settled_status") == "ACTIVE" and self.inv_in_period(inv, self.current_display_month):
                        cursor.execute("UPDATE invoices SET settled_status = 'SETTLED' WHERE invoice_id = ?", (inv_id,))
                        self.invoices[inv_id]["settled_status"] = "SETTLED"
            conn.commit()
        
        self.sync_all_archives()
        self.update_period_selector()
        self.recalculate_all()
        messagebox.showinfo("تم الإقفال", "تمت الأرشفة وإغلاق فترة القسم بنجاح!")

    def add_new_name_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("تأسيس اسم جديد")
        win.geometry("400x250")
        win.attributes("-topmost", True)
        
        # تكبير خط الاسم عند الإضافة
        entry = ctk.CTkEntry(win, placeholder_text="اكتب الاسم هنا...", font=("Cairo", 18, "bold"), justify="center", width=280, height=45)
        entry.pack(pady=35)
        
        # ربط زر إنتر بالحفظ
        entry.bind("<Return>", lambda e: save())

        def save():
            name = entry.get().strip()
            if not name: return
            if self.check_name_exists(name):
                messagebox.showerror("خطأ", "الاسم مسجل مسبقاً!", parent=win)
                return
            self.categories[self.current_view_cat].append(name)
            self.save_name_to_db(name, self.current_view_cat)
            self.refresh_inquiry_table()
            win.destroy()

        ctk.CTkButton(win, text="حفظ الاسم", font=("Cairo", 16, "bold"), height=40, command=save).pack(pady=5)

    # =========================================================================
    # --- شاشة صناديق المصنع: ذهب / الماس / فصوص / أحجار بفترة زمنية محددة (لا تُصفّر شهرياً) ---
    # =========================================================================
    def build_factory_boxes_tab(self):
        tab = self.tabview.tab("صناديق المصنع")

        ctk.CTkLabel(tab, text="📦 صناديق المصنع", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(pady=(15, 6))

        range_row = ctk.CTkFrame(tab, fg_color="transparent")
        range_row.pack(pady=(0, 10))
        ctk.CTkLabel(range_row, text="من شهر:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.factory_from_month = ctk.CTkEntry(range_row, placeholder_text="YYYY-MM", font=("Cairo", 13), justify="center", width=110, height=36)
        self.factory_from_month.insert(0, self.current_display_month)
        self.factory_from_month.pack(side="right", padx=5)
        ctk.CTkLabel(range_row, text="إلى شهر:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.factory_to_month = ctk.CTkEntry(range_row, placeholder_text="YYYY-MM", font=("Cairo", 13), justify="center", width=110, height=36)
        self.factory_to_month.insert(0, self.current_display_month)
        self.factory_to_month.pack(side="right", padx=5)
        ctk.CTkButton(range_row, text="تصفية 🔍", font=("Cairo", 13, "bold"), fg_color="#1e8449", hover_color="#145a32", width=100, height=36, command=self.refresh_factory_boxes_table).pack(side="right", padx=8)
        ctk.CTkButton(range_row, text="الشهر الحالي ↺", font=("Cairo", 13, "bold"), fg_color="#555555", hover_color="#333333", width=120, height=36, command=self.reset_factory_boxes_period).pack(side="right", padx=5)

        self.factory_cards_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.factory_cards_frame.pack(fill="x", padx=20, pady=10)

        self.factory_card_widgets = {}
        box_defs = [("ذهب", "🥇"), ("فصوص وأحجار", "🔷"), ("الماس", "💎")]
        for i, (box, icon) in enumerate(box_defs):
            card = ctk.CTkFrame(self.factory_cards_frame, corner_radius=14, border_width=2, border_color="#d4af37", fg_color=("gray90", "gray15"))
            card.grid(row=0, column=i, padx=10, pady=5, sticky="nsew")
            self.factory_cards_frame.grid_columnconfigure(i, weight=1)

            ctk.CTkLabel(card, text=f"{icon} {box}", font=ctk.CTkFont(family="Cairo", size=19, weight="bold"), text_color="#d4af37").pack(pady=(14, 6))

            if box == "الماس":
                # لوحة الألماس مختلفة: تعرض مبيعات الذهب المرافق للألماس، ثم إجمالي الألماس
                lbl_gold_linked = ctk.CTkLabel(card, text="مبيعات ذهب: 0.00", font=("Cairo", 18, "bold"), text_color="#e74c3c")
                lbl_gold_linked.pack(pady=4)

                lbl_diamond_total = ctk.CTkLabel(card, text="الألماس: 0.00", font=("Cairo", 24, "bold"), text_color="#2ecc71")
                lbl_diamond_total.pack(pady=(4, 12))

                btn = ctk.CTkButton(card, text="عرض كشف الحساب 🔍", font=("Cairo", 14, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=170, height=34, command=lambda b=box: self.open_factory_box_statement(b))
                btn.pack(pady=(0, 14))

                self.factory_card_widgets[box] = {"gold_linked": lbl_gold_linked, "diamond_total": lbl_diamond_total}
            else:
                lbl_sales = ctk.CTkLabel(card, text="المبيعات: 0.00", font=("Cairo", 18, "bold"), text_color="#e74c3c")
                lbl_sales.pack(pady=4)

                lbl_incoming = ctk.CTkLabel(card, text="الوارد: 0.00", font=("Cairo", 24, "bold"), text_color="#2ecc71")
                lbl_incoming.pack(pady=(4, 12))

                btn = ctk.CTkButton(card, text="عرض كشف الحساب 🔍", font=("Cairo", 14, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=170, height=34, command=lambda b=box: self.open_factory_box_statement(b))
                btn.pack(pady=(0, 14))

                self.factory_card_widgets[box] = {"sales": lbl_sales, "incoming": lbl_incoming}

        prod_bar1 = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        prod_bar1.pack(fill="x", padx=20, pady=(15, 6))
        self.lbl_prod_gold_stones = ctk.CTkLabel(prod_bar1, text="", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#f1c40f")
        self.lbl_prod_gold_stones.pack(pady=8)

        prod_bar2 = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        prod_bar2.pack(fill="x", padx=20, pady=6)
        self.lbl_prod_gold_diamond = ctk.CTkLabel(prod_bar2, text="", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#f1c40f")
        self.lbl_prod_gold_diamond.pack(pady=8)

        prod_bar_total = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        prod_bar_total.pack(fill="x", padx=20, pady=6)
        self.lbl_prod_total = ctk.CTkLabel(prod_bar_total, text="", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), text_color="#d4af37")
        self.lbl_prod_total.pack(pady=8)

        ratio_bar = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        ratio_bar.pack(fill="x", padx=20, pady=(6, 10))
        self.lbl_prod_ratios = ctk.CTkLabel(ratio_bar, text="", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#2ecc71")
        self.lbl_prod_ratios.pack(pady=8)

        btn_print = ctk.CTkButton(tab, text="🖨️ طباعة صناديق المصنع", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=42, command=self.print_factory_boxes_screen)
        btn_print.pack(pady=(0, 15))

        self.refresh_factory_boxes_table()

    def reset_factory_boxes_period(self):
        self.factory_from_month.delete(0, 'end')
        self.factory_from_month.insert(0, self.current_display_month)
        self.factory_to_month.delete(0, 'end')
        self.factory_to_month.insert(0, self.current_display_month)
        self.refresh_factory_boxes_table()

    def open_factory_box_statement(self, box):
        account_map = {"ذهب": "المبيعات", "الماس": "حساب الألماس", "فصوص وأحجار": "حساب فصوص وأحجار"}
        account_key = account_map.get(box)
        if not account_key:
            return
        self.navigate_to_screen("كشف حساب")
        if hasattr(self, 'kh_account_name'):
            self.kh_account_name.set(account_key)
            self.refresh_account_statement()

    def refresh_factory_boxes_table(self):
        if not hasattr(self, 'factory_card_widgets') or not self.factory_card_widgets:
            return

        from_m = (self.factory_from_month.get().strip() if hasattr(self, 'factory_from_month') else "") or self.current_display_month
        to_m = (self.factory_to_month.get().strip() if hasattr(self, 'factory_to_month') else "") or self.current_display_month

        # ====== لوحتا الذهب وفصوص وأحجار: المبيعات والوارد كلاهما يُحسبان ضمن الفترة المحددة فقط ======
        in_type_map = {"ذهب": "وارد ذهب (عيار 18)", "فصوص وأحجار": "وارد فصوص وأحجار"}
        sale_type_map = {"ذهب": "مبيعات ذهب", "فصوص وأحجار": "مبيعات فصوص وأحجار"}

        sales_totals = {}
        for box in ["ذهب", "فصوص وأحجار"]:
            in_type = in_type_map[box]
            sale_type = sale_type_map[box]
            tot_in_period = tot_sale_period = 0.0
            for inv in self.invoices.values():
                if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                dt_m = self.inv_period(inv)
                if not (from_m <= dt_m <= to_m): continue
                t = inv.get("النوع")
                if t == in_type:
                    tot_in_period += inv["الوزن"]
                elif t == sale_type:
                    tot_sale_period += inv["الوزن"]

            sales_totals[box] = round(tot_sale_period, 2)

            widgets = self.factory_card_widgets.get(box)
            if widgets:
                widgets["sales"].configure(text=f"المبيعات: {round(tot_sale_period, 2):.2f}")
                widgets["incoming"].configure(text=f"الوارد: {round(tot_in_period, 2):.2f}")

        # ====== لوحة الألماس: مبيعات الذهب المرافق للألماس + إجمالي الألماس، ضمن نفس الفترة ======
        tot_gold_linked = tot_diamond = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            dt_m = self.inv_period(inv)
            if not (from_m <= dt_m <= to_m): continue
            t = inv.get("النوع")
            if t == "مبيعات ذهب مع الماس":
                tot_gold_linked += inv["الوزن"]
            elif t == "مبيعات الماس":
                tot_diamond += inv["الوزن"]

        tot_gold_linked = round(tot_gold_linked, 2)
        tot_diamond = round(tot_diamond, 2)
        sales_totals["الماس"] = tot_diamond

        diamond_widgets = self.factory_card_widgets.get("الماس")
        if diamond_widgets:
            diamond_widgets["gold_linked"].configure(text=f"مبيعات ذهب: {tot_gold_linked:.2f}")
            diamond_widgets["diamond_total"].configure(text=f"الألماس: {tot_diamond:.2f}")

        # ====== الأشرطة البارزة (الإنتاج والنسب) تُحسب من رصيد المبيعات التراكمي ======
        prod_gold_stones = round(sales_totals.get("ذهب", 0.0) + sales_totals.get("فصوص وأحجار", 0.0), 2)
        prod_gold_diamond = round(tot_gold_linked + tot_diamond, 2)
        prod_total = round(prod_gold_stones + prod_gold_diamond, 2)

        if hasattr(self, 'lbl_prod_gold_stones'):
            self.lbl_prod_gold_stones.configure(text=f"📊 إنتاج (الذهب + فصوص وأحجار): {prod_gold_stones:.2f}")
        if hasattr(self, 'lbl_prod_gold_diamond'):
            self.lbl_prod_gold_diamond.configure(text=f"📊 إنتاج (الذهب + الألماس): {prod_gold_diamond:.2f}")
        if hasattr(self, 'lbl_prod_total'):
            self.lbl_prod_total.configure(text=f"🏆 إجمالي الإنتاج: {prod_total:.2f}")

        gold_sales = sales_totals.get("ذهب", 0.0)
        if gold_sales:
            ratio_stones = round((sales_totals.get("فصوص وأحجار", 0.0) / gold_sales) * 100, 2)
            ratio_diamond = round((tot_diamond / gold_sales) * 100, 2)
        else:
            ratio_stones = ratio_diamond = 0.0

        if hasattr(self, 'lbl_prod_ratios'):
            self.lbl_prod_ratios.configure(text=f"⚖️ نسبة (الفصوص + الأحجار) / الذهب: {ratio_stones:.2f}%    |    نسبة الألماس / الذهب: {ratio_diamond:.2f}%")

    def print_factory_boxes_screen(self):
        """يولّد ويعرض/يطبع صفحة PDF بنفس شكل شاشة صناديق المصنع (لوحات المواد الثلاث + أشرطة الإنتاج والنسب)"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "ميزة الطباعة تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return

        from_m = (self.factory_from_month.get().strip() if hasattr(self, 'factory_from_month') else "") or self.current_display_month
        to_m = (self.factory_to_month.get().strip() if hasattr(self, 'factory_to_month') else "") or self.current_display_month

        in_type_map = {"ذهب": "وارد ذهب (عيار 18)", "فصوص وأحجار": "وارد فصوص وأحجار"}
        sale_type_map = {"ذهب": "مبيعات ذهب", "فصوص وأحجار": "مبيعات فصوص وأحجار"}
        sales_totals, incoming_totals = {}, {}
        for box in ["ذهب", "فصوص وأحجار"]:
            in_type = in_type_map[box]; sale_type = sale_type_map[box]
            tot_in = tot_sale = 0.0
            for inv in self.invoices.values():
                if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                dt_m = self.inv_period(inv)
                if not (from_m <= dt_m <= to_m): continue
                t = inv.get("النوع")
                if t == in_type: tot_in += inv["الوزن"]
                elif t == sale_type: tot_sale += inv["الوزن"]
            sales_totals[box] = round(tot_sale, 2)
            incoming_totals[box] = round(tot_in, 2)

        tot_gold_linked = tot_diamond = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            dt_m = self.inv_period(inv)
            if not (from_m <= dt_m <= to_m): continue
            t = inv.get("النوع")
            if t == "مبيعات ذهب مع الماس": tot_gold_linked += inv["الوزن"]
            elif t == "مبيعات الماس": tot_diamond += inv["الوزن"]
        tot_gold_linked, tot_diamond = round(tot_gold_linked, 2), round(tot_diamond, 2)
        sales_totals["الماس"] = tot_diamond

        prod_gold_stones = round(sales_totals.get("ذهب", 0.0) + sales_totals.get("فصوص وأحجار", 0.0), 2)
        prod_gold_diamond = round(tot_gold_linked + tot_diamond, 2)
        prod_total = round(prod_gold_stones + prod_gold_diamond, 2)
        gold_sales = sales_totals.get("ذهب", 0.0)
        ratio_stones = round((sales_totals.get("فصوص وأحجار", 0.0) / gold_sales) * 100, 2) if gold_sales else 0.0
        ratio_diamond = round((tot_diamond / gold_sales) * 100, 2) if gold_sales else 0.0

        out_dir = INVOICES_DIR
        out_path = os.path.join(out_dir, f"factory_boxes_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        from reportlab.lib.colors import Color
        PW, PH = A4
        M = 10 * mm
        gold_color = Color(0.83, 0.69, 0.22)

        def txt(c, x, y, s, size=9, bold=False, align="right", color=None):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            if color: c.setFillColor(color)
            s = ar(s)
            if align == "right": c.drawRightString(x, y, s)
            elif align == "left": c.drawString(x, y, s)
            else: c.drawCentredString(x, y, s)
            if color: c.setFillColorRGB(0, 0, 0)

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        y = PH - M

        txt(c, M, y - 6, "Jadeite Factory", size=12, bold=True, align="left")
        txt(c, M, y - 13, "Saudi Arabia, Riyadh", size=8, align="left")
        txt(c, PW - M, y - 6, "مصنع جاديت للتصنيع", size=12, bold=True, align="right")
        txt(c, PW - M, y - 13, "المملكة العربية السعودية", size=8, align="right")
        logo_bottom = y - 13
        try:
            logo_bytes = base64.b64decode(APP_LOGO_B64)
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            lw, lh = 45 * mm, 10 * mm
            logo_top = y - 4
            logo_bottom = logo_top - lh
            c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass
        y = min(y - 13, logo_bottom) - 9 * mm

        txt(c, PW / 2, y, "📦 صناديق المصنع", size=17, bold=True, align="center", color=gold_color)
        y -= 8 * mm
        txt(c, PW / 2, y, f"الفترة: {from_m} إلى {to_m}", size=10, align="center")
        y -= 8 * mm

        box_defs = [("ذهب", "🥇"), ("فصوص وأحجار", "🔷"), ("الماس", "💎")]
        n_cols = 3
        card_w = (PW - 2 * M - 2 * 6 * mm) / n_cols
        card_h = 34 * mm
        for i, (box, icon) in enumerate(box_defs):
            cx0 = M + i * (card_w + 6 * mm)
            c.setStrokeColor(gold_color)
            c.rect(cx0, y - card_h, card_w, card_h, fill=0, stroke=1)
            txt(c, cx0 + card_w / 2, y - 8 * mm, f"{icon} {box}", size=13, bold=True, align="center", color=gold_color)
            if box == "الماس":
                txt(c, cx0 + card_w / 2, y - 17 * mm, f"مبيعات ذهب: {tot_gold_linked:.2f}", size=10, bold=True, align="center")
                txt(c, cx0 + card_w / 2, y - 26 * mm, f"الألماس: {tot_diamond:.2f}", size=14, bold=True, align="center")
            else:
                txt(c, cx0 + card_w / 2, y - 17 * mm, f"المبيعات: {sales_totals.get(box, 0):.2f}", size=10, bold=True, align="center")
                txt(c, cx0 + card_w / 2, y - 26 * mm, f"الوارد: {incoming_totals.get(box, 0):.2f}", size=14, bold=True, align="center")
        y -= card_h + 12

        bars = [
            f"📊 إنتاج (الذهب + فصوص وأحجار): {prod_gold_stones:.2f}",
            f"📊 إنتاج (الذهب + الألماس): {prod_gold_diamond:.2f}",
            f"🏆 إجمالي الإنتاج: {prod_total:.2f}",
            f"⚖️ نسبة (الفصوص + الأحجار)/الذهب: {ratio_stones:.2f}%    |    نسبة الألماس/الذهب: {ratio_diamond:.2f}%",
        ]
        bar_h = 12 * mm
        for bar_text in bars:
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.rect(M, y - bar_h, PW - 2 * M, bar_h, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1)
            txt(c, PW / 2, y - bar_h + 4 * mm, bar_text, size=11, bold=True, align="center")
            c.setFillColorRGB(0, 0, 0)
            y -= bar_h + 3 * mm

        txt(c, PW / 2, 15 * mm, f"تاريخ الطباعة: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", size=9, align="center")

        c.showPage()
        c.save()
        self._open_file(out_path)

    # =========================================================================
    # --- شاشة كشف حساب: استعلام موحّد عن أي حساب (مورد / مادة / مسترجع / خزينة) ---
    # =========================================================================
    def get_account_statement_options(self):
        hidden_mustarja = set(self.get_all_mustarja_names())
        names = [n for n in self.get_supplier_name_values() if n not in hidden_mustarja]
        names += ["حساب الذهب", "حساب الألماس", "حساب فصوص وأحجار"]
        names += self.get_all_mustarja_names()
        names += ["حساب الخزينة", "المبيعات"]
        names += [self.get_box_account_name(c) for c in self.get_all_stage_categories() + ["المصنعين", "المركبين"]]
        names += ["حساب الخسائر"]
        names += [n for n in self.categories.get("حسابات إضافية", []) if n not in names]
        # أي اسم/حساب جديد استُخدم بقيد يومي سابقاً يظهر تلقائياً هنا أيضاً
        extra_names = set()
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if inv.get("النوع") in ("قيد يومي مدين", "قيد يومي دائن"):
                nm = inv.get("الاسم", "")
                if nm and nm not in names:
                    extra_names.add(nm)
        names += sorted(extra_names)
        return names

    # حسابات رصيدها = مدين − دائن (الخزينة والمواد)، وبقية الحسابات دائن − مدين
    MADIN_DAEN_ACCOUNTS = frozenset({"حساب الخزينة", "حساب الذهب", "حساب الألماس", "حساب فصوص وأحجار"})

    def get_account_ledger_rows(self, account_key, from_m, to_m):
        """صفوف كشف الحساب (رقم فاتورة/تاريخ/اسم/مدين/دائن/بيان/فترة) لأي حساب، ضمن نطاق فترات اختياري.

        النطاق بالفترة المحاسبية (عمود period) لا بشهر التاريخ — مثل كل الشاشات:
        حركة سُجّلت وأنت على فترة ٨ تظهر في كشف فترة ٨ ولو كان تاريخها ٢٠٢٦-٠٩-٠١.
        وعند تحديد «من فترة» يُضاف أولاً سطر «رصيد أول المدة» = رصيد الحساب في
        نهاية الفترة السابقة، فيبدأ الكشف من رصيد الحساب الفعلي لا من الصفر.
        """
        all_rows = self._account_ledger_rows_all(account_key)
        rows = [r for r in all_rows
                if (not from_m or r["period"] >= from_m) and (not to_m or r["period"] <= to_m)]
        if from_m:
            use_madin_daen = account_key in self.MADIN_DAEN_ACCOUNTS
            opening = round(sum((r["مدين"] - r["دائن"]) if use_madin_daen else (r["دائن"] - r["مدين"])
                                for r in all_rows if r["period"] < from_m), 2)
            debit_side = (opening > 0) == use_madin_daen
            rows.insert(0, {
                "رقم الفاتورة": "-", "التاريخ": from_m, "الاسم": "رصيد أول المدة",
                "مدين": abs(opening) if debit_side else 0.0,
                "دائن": 0.0 if debit_side else abs(opening),
                "البيان": "رصيد نهاية الفترة السابقة (مُرحَّل)",
                "period": from_m, "is_opening": True,
            })
        return rows

    def _account_ledger_rows_all(self, account_key):
        """كل صفوف الحساب في كل الفترات مرتّبة (فترة ← تاريخ ← رقم)، ولكل صف فترته."""
        rows = []
        material_map = {
            "حساب الذهب": (None, ["مبيعات ذهب", "مبيعات ذهب مع الماس"]),
            "حساب الألماس": ("وارد الماس", ["مبيعات الماس"]),
            "حساب فصوص وأحجار": ("وارد فصوص وأحجار", ["مبيعات فصوص وأحجار"]),
        }
        in_types_all = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        sale_material_label = {"مبيعات ذهب": "ذهب", "مبيعات ذهب مع الماس": "ذهب", "مبيعات فصوص وأحجار": "فصوص وأحجار", "مبيعات الماس": "الماس"}
        in_material_label = {"وارد ذهب (عيار 18)": "ذهب", "وارد فصوص وأحجار": "فصوص وأحجار", "وارد الماس": "الماس"}

        def add(inv, madin_v, daen_v, bayan, name=None):
            rows.append({"رقم الفاتورة": inv["رقم الفاتورة"], "التاريخ": inv.get("التاريخ", ""),
                         "الاسم": inv.get("الاسم", "") if name is None else name,
                         "مدين": madin_v, "دائن": daen_v, "البيان": bayan,
                         "period": self.inv_period(inv)})

        if account_key in material_map:
            in_type, sale_types = material_map[account_key]
            for inv in self.invoices.values():
                if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                t = inv.get("النوع")
                if t != in_type and t not in sale_types: continue
                is_in = bool(in_type and t == in_type)
                add(inv, inv["الوزن"] if is_in else 0.0, inv["الوزن"] if t in sale_types else 0.0,
                    "وارد" if is_in else "مبيعات")

        elif account_key == "المبيعات":
            for inv in self.invoices.values():
                if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                t = inv.get("النوع")
                if t not in sale_material_label: continue
                add(inv, 0.0, inv["الوزن"], f"مبيعات {sale_material_label[t]}",
                    name=f"{inv.get('الاسم', '')} - {sale_material_label[t]}")

        elif account_key == "حساب الخزينة":
            # من المصدر الموحّد نفسه الذي يبني شريط الخزينة ورصيد أول المدة
            # والتقرير الشهري (treasury_bucket) — فرصيد الكشف في نهاية أي فترة
            # = رصيد نهاية تلك الفترة في التقرير = الشريط عند عرضها.
            type_sets = self.get_treasury_type_sets()
            by_period = {}
            for inv in self.invoices.values():
                if not inv.get("التاريخ"): continue
                period = self.inv_period(inv)
                if period:
                    by_period.setdefault(period, []).append(inv)
                bucket, amount = self.treasury_bucket(inv, type_sets)
                # قيود «حساب الخزينة» اليومية تُضاف في القسم الموحّد أسفل الدالة
                if not bucket or bucket == "journal": continue
                add(inv, amount if amount > 0 else 0.0, -amount if amount < 0 else 0.0, inv.get("البيان", ""))

            # الخياس الفعلي للمصنعين والمركبين — سطر لكل فترة بقيمته **كاملة**.
            # الإقفال قيد بين «حساب الخسائر» والصندوق لا يمسّ الخزينة، فالخياس
            # يبقى مخصوماً بعده (كان يُعرض غير المُقفل فقط، فيرتفع رصيد الخزينة
            # بمجرد الإقفال وتبدأ الفترة التالية برصيد مختلف عن نهاية سابقتها).
            for period, invs in sorted(by_period.items()):
                for cat, label in (("المصنعين", "الخياس الفعلي - المصنعين"),
                                   ("المركبين", "الخياس الفعلي - المركبين")):
                    amount = self.get_actual_section_khayas(cat, target_month=period, invoices=invs)
                    if abs(amount) < 0.005:
                        continue
                    bayan = f"خياس فعلي — فترة {period}"
                    closed = self.get_box_closed_total(cat, month=period)
                    if abs(closed) >= 0.005:
                        bayan += f" (أُقفل منه {closed:.2f} لحساب الخسائر)"
                    rows.append({
                        "رقم الفاتورة": "-",
                        # يُؤرَّخ في آخر فترته فيقع في نهايتها من الكشف
                        "التاريخ": self.period_closing_datetime(period)[:16],
                        "الاسم": label,
                        "مدين": 0.0 if amount > 0 else abs(amount),
                        "دائن": amount if amount > 0 else 0.0,
                        "البيان": bayan, "period": period, "_last": True,
                    })

        elif account_key in ([self.get_box_account_name(c) for c in self.get_all_stage_categories()] +
                              [self.get_box_account_name("المصنعين"), self.get_box_account_name("المركبين")]):
            # صناديق الخياس: كشف الحساب يعرض كل حركاته الخام من مراحل التصنيع (القيود اليومية تُضاف تلقائياً لاحقاً بأسفل الدالة)
            box_names = {self.get_box_account_name(c): c for c in self.get_all_stage_categories() + ["المصنعين", "المركبين"]}
            cat = box_names[account_key]
            if cat in ("المصنعين", "المركبين"):
                worker_types_madin = {"صرف ذهب", "الليز"}
                worker_types_daen = {"قبض ذهب", "البوليش", "المفنش ٨ بالالف", "المفنش ٤ بالالف"}
                names_in_cat = set(self.categories.get(cat, []))
                for inv in self.invoices.values():
                    if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                    if inv.get("الاسم") not in names_in_cat: continue
                    t = inv.get("النوع")
                    if t not in worker_types_madin and t not in worker_types_daen: continue
                    add(inv, inv["الوزن"] if t in worker_types_madin else 0.0,
                        inv["الوزن"] if t in worker_types_daen else 0.0, t)
            else:
                madin_type, qabd_type, mustarja_name = self.get_stage_config(cat)
                in_types_local = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
                for inv in self.invoices.values():
                    if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                    t = inv.get("النوع")
                    if t == madin_type:
                        add(inv, inv["الوزن"], 0.0, inv.get("البيان") or "صرف")
                    elif qabd_type and t == qabd_type:
                        add(inv, 0.0, inv["الوزن"], "قبض")
                    elif t in in_types_local and inv.get("الاسم") == mustarja_name:
                        add(inv, 0.0, inv["الوزن"], "وارد مسترجع")

        else:  # مورد عادي أو اسم مسترجع
            sale_types_all = ["مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس"]
            for inv in self.invoices.values():
                if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
                if inv.get("الاسم") != account_key: continue
                t = inv.get("النوع")
                if t not in in_types_all and t != "صادر ذهب" and t not in sale_types_all: continue
                if t in sale_types_all:
                    bayan = f"مبيعات {sale_material_label[t]}"
                elif t in in_types_all:
                    bayan = f"وارد {in_material_label[t]}"
                else:
                    bayan = inv.get("البيان", "")
                add(inv, inv["الوزن"] if (t == "صادر ذهب" or t in sale_types_all) else 0.0,
                    inv["الوزن"] if t in in_types_all else 0.0, bayan)

        # القيود اليومية: تُضاف لأي حساب في النظام أياً كان نوعه (موحّد على كل الحسابات)،
        # بفلتر الحالة نفسه الذي يحتسبها في الأرصدة
        for inv in self.invoices.values():
            if inv.get("settled_status") not in COUNTED_STATUSES: continue
            if inv.get("الاسم") != account_key: continue
            if account_key == "حساب الخزينة" and not inv.get("التاريخ"): continue
            t = inv.get("النوع")
            if t not in ("قيد يومي مدين", "قيد يومي دائن"): continue
            add(inv, inv["الوزن"] if t == "قيد يومي مدين" else 0.0,
                inv["الوزن"] if t == "قيد يومي دائن" else 0.0, inv.get("البيان") or "قيد يومي")

        rows.sort(key=lambda r: (r["period"], r.get("_last", False), r["التاريخ"],
                                 r["رقم الفاتورة"] if isinstance(r["رقم الفاتورة"], int) else 0))
        return rows

    def build_account_statement_tab(self):
        tab = self.tabview.tab("كشف حساب")

        top_row = ctk.CTkFrame(tab, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=(12, 6))

        ctk.CTkLabel(top_row, text="📋 كشف حساب", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(side="right", padx=10)

        self.kh_from_month = ctk.CTkEntry(top_row, placeholder_text="YYYY-MM", font=("Cairo", 15), justify="center", width=110, height=36)
        self.kh_from_month.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="من شهر:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        self.kh_to_month = ctk.CTkEntry(top_row, placeholder_text="YYYY-MM", font=("Cairo", 15), justify="center", width=110, height=36)
        self.kh_to_month.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="إلى شهر:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top_row, text="الاسم:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.kh_account_name = ctk.CTkComboBox(top_row, values=self.get_account_statement_options(), font=("Cairo", 15), width=230, height=36, justify="right")
        self.kh_account_name.pack(side="right", padx=5)
        self.bind_name_autocomplete(self.kh_account_name, self.get_account_statement_options)

        ctk.CTkButton(top_row, text="بحث 🔍", font=("Cairo", 15, "bold"), fg_color="#1e8449", hover_color="#145a32", width=100, height=36, command=self.refresh_account_statement).pack(side="right", padx=10)

        self.account_statement_table_frame = ttk.Frame(tab)
        self.account_statement_table_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.account_statement_tree = None

        balance_bar = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        balance_bar.pack(fill="x", padx=20, pady=(0, 6))
        self.lbl_account_statement_balance = ctk.CTkLabel(balance_bar, text="", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#f1c40f")
        self.lbl_account_statement_balance.pack(pady=10)

        ctk.CTkLabel(tab, text="اضغط مرتين على أي سطر لمعاينة فاتورته (إن وُجدت)، أو حدّده واضغط تعديل", font=("Cairo", 11), text_color="#aaaaaa").pack(pady=(0, 4))

        btns_row = ctk.CTkFrame(tab, fg_color="transparent")
        btns_row.pack(pady=(0, 12))
        btn_print = ctk.CTkButton(btns_row, text="🖨️ طباعة كشف الحساب", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=42, command=self.print_account_statement)
        btn_print.pack(side="right", padx=5)
        btn_edit_row = ctk.CTkButton(btns_row, text="✏️ تعديل السطر المحدد", font=("Cairo", 14, "bold"), fg_color="#8b6d00", hover_color="#6b5400", height=42, command=self.edit_selected_account_statement_row)
        btn_edit_row.pack(side="right", padx=5)

    def print_account_statement(self):
        """يولّد ويعرض/يطبع كشف الحساب الحالي (أي حساب مختار) بجدول مطابق للشاشة، مع دعم تعدد الصفحات"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "ميزة الطباعة تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return
        account_key = self.kh_account_name.get().strip() if hasattr(self, 'kh_account_name') else ""
        if not account_key:
            messagebox.showwarning("تنبيه", "الرجاء اختيار حساب أولاً.")
            return
        from_m = self.kh_from_month.get().strip()
        to_m = self.kh_to_month.get().strip()

        rows = self.get_account_ledger_rows(account_key, from_m, to_m)
        use_madin_daen = account_key in self.MADIN_DAEN_ACCOUNTS

        out_dir = INVOICES_DIR
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in account_key)[:30]
        out_path = os.path.join(out_dir, f"account_{safe_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        from reportlab.lib.colors import Color
        PW, PH = A4
        M = 10 * mm
        header_fill = Color(0.78, 0.80, 0.93)
        border_color = Color(0.15, 0.15, 0.55)

        def txt(c, x, y, s, size=9, bold=False, align="right", color=None):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            if color: c.setFillColor(color)
            s = ar(s)
            if align == "right": c.drawRightString(x, y, s)
            elif align == "left": c.drawString(x, y, s)
            else: c.drawCentredString(x, y, s)
            if color: c.setFillColorRGB(0, 0, 0)

        def rect(c, x, y, w, h, fill=None, stroke_color=None):
            c.saveState()
            if stroke_color: c.setStrokeColor(stroke_color)
            if fill:
                c.setFillColor(fill)
                c.rect(x, y - h, w, h, fill=1, stroke=1)
            else:
                c.rect(x, y - h, w, h, fill=0, stroke=1)
            c.restoreState()

        cols = ["رقم الفاتورة", "التاريخ", "الاسم", "مدين", "دائن", "الرصيد", "البيان"]
        col_ratios = [0.8, 1.1, 1.3, 0.8, 0.8, 0.9, 1.3]
        table_w = PW - 2 * M
        ratio_sum = sum(col_ratios)
        col_ws = [table_w * r / ratio_sum for r in col_ratios]
        col_x_starts = []
        acc = 0.0
        for w in col_ws:
            col_x_starts.append(acc); acc += w

        row_h = 8 * mm
        header_h = 10 * mm
        max_rows_per_page = 26

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        idx = 0
        total_rows = len(rows)
        running = 0.0
        page_num = 1

        while idx < total_rows or (idx == 0 and total_rows == 0):
            y = PH - M
            txt(c, M, y - 6, "Jadeite Factory", size=11, bold=True, align="left")
            txt(c, M, y - 12, "Saudi Arabia, Riyadh", size=7, align="left")
            txt(c, PW - M, y - 6, "مصنع جاديت للتصنيع", size=11, bold=True, align="right")
            txt(c, PW - M, y - 12, "المملكة العربية السعودية", size=7, align="right")
            logo_bottom = y - 12
            try:
                logo_bytes = base64.b64decode(APP_LOGO_B64)
                logo_img = ImageReader(io.BytesIO(logo_bytes))
                lw, lh = 40 * mm, 9 * mm
                logo_top = y - 3
                logo_bottom = logo_top - lh
                c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
            except Exception:
                pass
            y = min(y - 12, logo_bottom) - 8 * mm

            txt(c, PW / 2, y, "📋 كشف حساب", size=15, bold=True, align="center", color=border_color)
            y -= 6 * mm
            txt(c, PW - M, y, f"الحساب: {account_key}", size=11, bold=True, align="right")
            period_txt = f"{from_m or 'البداية'} إلى {to_m or 'الآن'}"
            txt(c, M, y, period_txt, size=10, align="left")
            if page_num > 1:
                y -= 5 * mm
                txt(c, M, y, f"(تابع - صفحة {page_num})", size=9, align="left")
            y -= 7 * mm

            table_top = y
            rect(c, M, table_top, table_w, header_h, fill=header_fill, stroke_color=border_color)
            for i, lbl in enumerate(cols):
                cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                hdr_size = fit_font_size(lbl, col_ws[i] - 3 * mm, 10, bold=True, min_size=6.5)
                txt(c, cx, vcenter_baseline(table_top, header_h, hdr_size), lbl, size=hdr_size, bold=True, align="center", color=border_color)
                if i > 0:
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], table_top - header_h, M + table_w - col_x_starts[i], table_top)

            y = table_top - header_h
            page_rows = rows[idx: idx + max_rows_per_page]
            for r in page_rows:
                running += (r["مدين"] - r["دائن"]) if use_madin_daen else (r["دائن"] - r["مدين"])
                rect(c, M, y, table_w, row_h, stroke_color=border_color)
                for i in range(1, len(cols)):
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], y - row_h, M + table_w - col_x_starts[i], y)
                values = [
                    str(r["رقم الفاتورة"]), str(r["التاريخ"])[:16], str(r["الاسم"]),
                    f"{r['مدين']:.2f}" if r["مدين"] else "-",
                    f"{r['دائن']:.2f}" if r["دائن"] else "-",
                    f"{running:.2f}", str(r.get("البيان", "")),
                ]
                for i, val in enumerate(values):
                    cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                    val_size = fit_font_size(val, col_ws[i] - 3 * mm, 9, min_size=6)
                    txt(c, cx, vcenter_baseline(y, row_h, val_size), val, size=val_size, align="center")
                y -= row_h
            idx += len(page_rows)

            if idx >= total_rows:
                txt(c, PW / 2, y - 8 * mm, f"الرصيد النهائي: {running:.2f}", size=13, bold=True, align="center", color=border_color)
                y -= 16 * mm
                txt(c, PW / 2, max(y, 15 * mm), f"تاريخ الطباعة: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", size=9, align="center")

            c.showPage()
            page_num += 1
            if total_rows == 0:
                break

        c.save()
        self._open_file(out_path)

    def on_account_statement_row_click(self, event=None):
        """عند النقر المزدوج على سطر بكشف الحساب: إن كان مرتبطاً بفاتورة مبيعات (له رقم تشغيل)، تُفتح معاينة قالبها"""
        if not (hasattr(self, 'account_statement_tree') and self.account_statement_tree):
            return
        sel = self.account_statement_tree.selection()
        if not sel:
            return
        values = self.account_statement_tree.item(sel[0], "values")
        if not values:
            return
        inv_id_str = str(values[0])
        if not inv_id_str.isdigit():
            return
        inv = self.invoices.get(int(inv_id_str))
        if not inv or not inv.get("set_number"):
            messagebox.showinfo("تنبيه", "هذه العملية غير مرتبطة بفاتورة مبيعات قابلة للمعاينة.")
            return
        self.preview_invoice_groups([(inv["set_number"], inv["التاريخ"], inv["الاسم"])])

    def edit_selected_account_statement_row(self):
        """يفتح نافذة تعديل الفاتورة/العملية للسطر المحدد بكشف الحساب - أي تعديل يُعاد حسابه فوراً بكل مكان (الخزينة، المصنع، أي حساب مرتبط)"""
        if not self.check_edit_permission():
            return
        if not (hasattr(self, 'account_statement_tree') and self.account_statement_tree):
            return
        sel = self.account_statement_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد السطر المراد تعديله أولاً.")
            return
        values = self.account_statement_tree.item(sel[0], "values")
        if not values:
            return
        inv_id_str = str(values[0])
        if not inv_id_str.isdigit():
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للتعديل المباشر (قيمة محسوبة تلقائياً وليست فاتورة مستقلة).")
            return
        self.open_edit_invoice_ui(int(inv_id_str), is_archived=True)

    def refresh_account_statement(self):
        if not hasattr(self, 'account_statement_table_frame') or not self.account_statement_table_frame:
            return
        for widget in self.account_statement_table_frame.winfo_children():
            widget.destroy()

        if hasattr(self, 'kh_account_name'):
            self.kh_account_name.configure(values=self.get_account_statement_options())

        account_key = self.kh_account_name.get().strip() if hasattr(self, 'kh_account_name') else ""
        if not account_key:
            return
        from_m = self.kh_from_month.get().strip()
        to_m = self.kh_to_month.get().strip()

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "مدين", "دائن", "الرصيد", "البيان")
        self.account_statement_tree = self.create_standard_treeview(self.account_statement_table_frame, cols, height=16)
        self.account_statement_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 14, "bold"))
        for c in cols:
            w = 220 if c == "البيان" else 200 if c == "الاسم" else 140 if c == "التاريخ" else 110
            self.account_statement_tree.column(c, width=w, anchor="center")
        self.account_statement_tree.bind("<Double-1>", self.on_account_statement_row_click)

        rows = self.get_account_ledger_rows(account_key, from_m, to_m)
        # الرصيد = مدين - دائن لحسابات الخزينة والذهب والألماس وفصوص وأحجار تحديداً (حسب الاعتماد الأخير)
        # وبقية الحسابات (الموردين، المسترجعات، المبيعات) تبقى على صيغة دائن - مدين
        use_madin_daen = account_key in self.MADIN_DAEN_ACCOUNTS
        self.account_statement_tree.tag_configure("opening_tag", foreground="#1f77b4", font=("Cairo", 13, "bold"))
        running = 0.0
        opening = None
        tot_madin = tot_daen = 0.0
        for r in rows:
            running += (r["مدين"] - r["دائن"]) if use_madin_daen else (r["دائن"] - r["مدين"])
            if r.get("is_opening"):
                # رصيد مُرحَّل لا حركة فترة: لا يدخل إجمالي المدين/الدائن
                opening = running
            else:
                tot_madin += r["مدين"]
                tot_daen += r["دائن"]
            self.account_statement_tree.insert("", "end", values=(
                r["رقم الفاتورة"], r["التاريخ"], r["الاسم"],
                f"{r['مدين']:.2f}" if r["مدين"] else "-",
                f"{r['دائن']:.2f}" if r["دائن"] else "-",
                f"{running:.2f}",
                r.get("البيان", "")
            ), tags=("opening_tag",) if r.get("is_opening") else ())

        if rows:
            self.account_statement_tree.insert("", "end", values=("-", "-", "الرصيد الحالي", "-", "-", f"{running:.2f}", "-"), tags=("total_tag",))

        if hasattr(self, 'lbl_account_statement_balance'):
            opening_txt = f"رصيد أول المدة: {opening:.2f}   |   " if opening is not None else ""
            self.lbl_account_statement_balance.configure(text=f"{opening_txt}إجمالي المدين: {tot_madin:.2f}   |   إجمالي الدائن: {tot_daen:.2f}   |   الرصيد: {round(running, 2):.2f}")

    def build_monthly_report_tab(self):
        tab = self.tabview.tab("التقرير الشهري")

        lbl_desc = ctk.CTkLabel(tab, text="📊 التقرير الشهري لرصيد الخزينة (نهاية الفترة = بداية الفترة − المبيعات/الصادر − الخياس + الوارد ± قيود الخزينة)", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#1f77b4")
        lbl_desc.pack(pady=(15, 2))
        ctk.CTkLabel(tab, text="كل فترة تبدأ برصيد نهاية الفترة التي قبلها تلقائياً، والأرقام لا تتغيّر بتغيير الفترة المعروضة — ورصيد نهاية الفترة المعروضة = شريط رصيد الخزينة",
                     font=("Cairo", 12), text_color="#aaaaaa").pack(pady=(0, 10))

        t_frame = ttk.Frame(tab)
        t_frame.pack(fill="both", expand=True, padx=15, pady=5)

        cols = ("الشهر", "رصيد بداية الفترة", "المبيعات / الصادر ➖", "الخياس ➖", "الوارد ➕", "قيود الخزينة ±", "رصيد نهاية الفترة ⚖️")
        self.report_tree = self.create_standard_treeview(t_frame, cols, height=16)
        self.report_tree.tag_configure("highlight_row", foreground="#d4af37", font=("Cairo", 13, "bold"))

        for c in cols:
            self.report_tree.column(c, width=170, anchor="center")

        self.calculate_and_refresh_monthly_report()

    def get_monthly_report_rows(self):
        """صفوف التقرير الشهري — مبنية من دفتر الخزينة الموحّد وحده.

        كان التقرير يحسب بمعادلته الخاصة (ACTIVE فقط، والذهب المسترجع يُعدّ
        مرتين: وارداً وخصماً من خياس الصندوق، وبلا صادر ولا قيود خزينة، ورصيد
        البداية من القيود الافتتاحية المعلَّمة فقط)، بينما يبني شريط الخزينة
        رصيد أول المدة بطريقة ثالثة. فتطابقت فترة ٨ صدفةً واختلفت فترة ٩.
        الآن: رصيد بداية كل فترة = رصيد نهاية سابقتها بالضبط، ورصيد نهاية
        الفترة المعروضة = شريط الخزينة، من أي فترة فُتح التقرير.
        """
        rows = []
        for r in self.get_treasury_ledger():
            rows.append({
                "period": r["period"],
                # «رصيد افتتاحي» والقيود الافتتاحية جزء من رصيد البداية لا من حركة الفترة
                "start": round(r["carry"] + r["opening"], 2),
                "sales": round(-r["sales"], 2),
                "khayas": round(-(r["boxes"] + r["workers"] + r["closed"]), 2),
                "inbound": round(r["inbound"], 2),
                "journal": round(r["journal"], 2),
                "end": r["closing"],
            })
        return rows

    def calculate_and_refresh_monthly_report(self):
        if not hasattr(self, 'report_tree') or not self.report_tree: return
        for item in self.report_tree.get_children(): self.report_tree.delete(item)

        for r in self.get_monthly_report_rows():
            tag = ("highlight_row",) if r["period"] == self.current_display_month else ()
            self.report_tree.insert("", "end", values=(
                f"شهر {r['period']}",
                f"{r['start']:.2f} جم",
                f"{r['sales']:.2f} جم",
                f"{r['khayas']:.2f} جم",
                f"{r['inbound']:.2f} جم",
                f"{r['journal']:+.2f} جم" if abs(r["journal"]) >= 0.005 else "-",
                f"{r['end']:.2f} جم"
            ), tags=tag)

    def get_supplier_name_values(self):
        """قائمة أسماء الموردين: المصنع + أسماء المسترجعات (كل اسم يخص صندوقه، بما فيها الأقسام الديناميكية) + الموردون المسجلون"""
        fixed = ["المصنع"] + self.get_all_mustarja_names()
        others = [n for n in self.categories.get("الموردين", []) if n not in fixed]
        return fixed + others

    def get_supplier_name_values_no_mustarja(self):
        """نفس قائمة الموردين لكن بدون أسماء المسترجعات (كل صناديق الخياس) - لشاشات لا يصح ظهورها فيها"""
        hidden = set(self.get_all_mustarja_names())
        return [n for n in self.get_supplier_name_values() if n not in hidden]

    def bind_name_autocomplete(self, combobox, values_getter):
        """يجعل خانة الاسم لا تعرض أي قيمة إلا عند اختيار من القائمة أو كتابة نص، وعندها يضيق الخيارات على الأسماء المقاربة لما كُتب"""
        def on_key(event=None):
            # المقارنة على الاسم بعد تنظيفه من علامة الاتجاه، وإلا لم يطابق
            # النص المكتوب أي اسم معروض فتختفي كل الخيارات
            typed = self.clean_name(combobox.get())
            full_list = values_getter()
            if typed:
                filtered = [n for n in full_list if typed in self.clean_name(n)]
                combobox.configure(values=filtered if filtered else full_list)
            else:
                combobox.configure(values=full_list)
        combobox.bind("<KeyRelease>", on_key)

    def toggle_in_carat_field(self, choice):
        """يظهر حقل العيار فقط عند اختيار (ذهب)، لأن باقي الأنواع لا تُحسب بعيار"""
        if choice == "ذهب":
            self.lbl_in_carat.pack(side="right", padx=3)
            self.in_carat.pack(side="right", padx=8, pady=8)
        else:
            self.lbl_in_carat.pack_forget()
            self.in_carat.pack_forget()
            self.in_carat.delete(0, 'end')

    def build_inout_tab(self):
        tab = self.tabview.tab("الوارد")

        main_frame = ctk.CTkFrame(tab, corner_radius=10)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)
        ctk.CTkLabel(main_frame, text="📥 الوارد/قبض (مورد / مصنع / مسترجعات)", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), text_color="#2ecc71").pack(pady=10)

        # ====== الصف العلوي: رقم الفاتورة (تلقائي) / رقم السند / التاريخ / الاسم ======
        top_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=15, pady=(0, 8))

        self.in_date = ctk.CTkEntry(top_row, placeholder_text="التاريخ", font=("Cairo", 14), justify="center", width=120, height=36)
        self.in_date.insert(0, self.get_smart_default_date())
        self.in_date.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="التاريخ:", font=("Cairo", 14, "bold")).pack(side="right", padx=3)

        ctk.CTkLabel(top_row, text="الاسم:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=3)
        self.in_supplier = ctk.CTkComboBox(top_row, values=self.get_supplier_name_values(), font=("Cairo", 14), width=230, height=36, justify="right")
        self.in_supplier.set("المصنع")
        self.in_supplier.pack(side="right", padx=5)
        self.bind_name_autocomplete(self.in_supplier, self.get_supplier_name_values)

        self.in_invoice_num = ctk.CTkEntry(top_row, font=("Cairo", 15, "bold"), justify="center", width=110, height=36,
                                            placeholder_text="رقم الفاتورة")
        self.in_invoice_num.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="رقم الفاتورة (يدوي):", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=3)

        # ====== صف نوع الوارد والعمليات (الوزن أولاً ثم العيار) ======
        ops_row = ctk.CTkFrame(main_frame, corner_radius=10)
        ops_row.pack(fill="x", padx=15, pady=6)

        self.in_weight = ctk.CTkEntry(ops_row, placeholder_text="الوزن", font=("Cairo", 14), justify="center", width=100, height=36)
        self.in_weight.pack(side="right", padx=8, pady=8)
        ctk.CTkLabel(ops_row, text="الوزن:", font=("Cairo", 14, "bold")).pack(side="right", padx=3)

        self.lbl_in_carat = ctk.CTkLabel(ops_row, text="العيار:", font=("Cairo", 14, "bold"))
        self.in_carat = ctk.CTkEntry(ops_row, placeholder_text="العيار", font=("Cairo", 14), justify="center", width=90, height=36)
        self.lbl_in_carat.pack(side="right", padx=3)
        self.in_carat.pack(side="right", padx=8, pady=8)

        self.in_type = ctk.CTkOptionMenu(ops_row, values=["ذهب", "الماس", "فصوص وأحجار"], font=("Cairo", 14, "bold"), width=130, height=36, command=self.toggle_in_carat_field)
        self.in_type.set("ذهب")
        self.in_type.pack(side="right", padx=8, pady=8)
        ctk.CTkLabel(ops_row, text="نوع الوارد:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=3)

        self.in_note = ctk.CTkEntry(main_frame, placeholder_text="البيان والشرح...", font=("Cairo", 14), justify="right", height=36)
        self.in_note.pack(fill="x", padx=15, pady=6)

        in_nav_fields = [self.in_supplier, self.in_weight, self.in_carat, self.in_note]
        self.bind_arrow_navigation(in_nav_fields)
        for i, f in enumerate(in_nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=in_nav_fields[i + 1]: nxt.focus_set() or "break")
        in_nav_fields[-1].bind("<Return>", lambda e: (self.submit_inbound(), "break")[1])

        btn_submit_in = ctk.CTkButton(main_frame, text="تسجيل الوارد للخزينة ➕", font=("Cairo", 15, "bold"), fg_color="#1e8449", hover_color="#145a32", height=38, command=self.submit_inbound)
        btn_submit_in.pack(pady=8)

        cols_in = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18", "البيان")
        self.tree_in = ttk.Treeview(main_frame, columns=cols_in, show="headings", height=16)
        self.tree_in.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols_in:
            self.tree_in.heading(c, text=c)
            w = 220 if c == "البيان" else (150 if c in ("التاريخ", "الاسم") else 90)
            self.tree_in.column(c, width=w, anchor="center")
        # ====== أزرار تعديل/حذف الحركة أعلى الجدول ======
        table_top_in = ctk.CTkFrame(main_frame, fg_color="transparent")
        table_top_in.pack(fill="x", padx=15, pady=(10, 2))
        ctk.CTkLabel(table_top_in, text="📋 كشف حركة الوارد", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#d4af37").pack(side="right")

        btn_del_in = ctk.CTkButton(table_top_in, text="حذف الحركة المحددة 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=32, command=self.delete_selected_inout_row)
        btn_del_in.pack(side="left", padx=5)

        btn_edit_in = ctk.CTkButton(table_top_in, text="تعديل الحركة المحددة ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=170, height=32, command=self.edit_selected_inout_row)
        btn_edit_in.pack(side="left", padx=5)

        self.tree_in.pack(fill="both", expand=True, padx=15, pady=(2, 4))
        self.tree_in.bind("<Double-1>", lambda e: self.edit_inout_record(self.tree_in))

        ctk.CTkLabel(main_frame, text="اضغط مرتين على أي سطر لتعديله، أو حدّده واضغط معاينة", font=("Cairo", 11), text_color="#aaaaaa").pack(pady=(0, 4))
        btn_preview_in_row = ctk.CTkButton(main_frame, text="👁️ معاينة السطر المحدد", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", height=36, command=self.preview_selected_inout_row)
        btn_preview_in_row.pack(pady=(0, 6))

        balance_bar = ctk.CTkFrame(main_frame, corner_radius=10, fg_color="#1a1a1a")
        balance_bar.pack(fill="x", padx=15, pady=(4, 6))
        self.lbl_in_summary = ctk.CTkLabel(balance_bar, text="إجمالي الوارد: 0.00 جم", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), text_color="#f1c40f")
        self.lbl_in_summary.pack(pady=10)

        btn_print_in = ctk.CTkButton(main_frame, text="🖨️ طباعة كشف الوارد", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=40, command=self.print_inout_screen)
        btn_print_in.pack(pady=(0, 10))

    def submit_inbound(self):
        try:
            d_val = self.in_date.get().strip()
            voucher = self.in_invoice_num.get().strip()
            if not voucher:
                messagebox.showwarning("رقم الفاتورة مطلوب", "لازم تسجل رقم الفاتورة يدوياً قبل الترحيل.")
                return
            dup = any(inv.get("set_number") == voucher and inv.get("settled_status") == "ACTIVE"
                      and str(inv.get("النوع", "")).startswith("وارد") for inv in self.invoices.values())
            # لا ننبّه لو كان نفس الرقم المُحتفظ به عمداً من آخر ترحيل بنفس الجلسة (فاتورة واحدة بعدة أسطر)
            if dup and voucher != getattr(self, '_last_inbound_voucher', None):
                if not messagebox.askyesno("رقم فاتورة مكرر", f"رقم الفاتورة ({voucher}) مسجل من قبل بحركة وارد أخرى.\nهل تريد المتابعة برغم ذلك؟"):
                    return
            supplier = self.in_supplier.get().strip() or "المصنع"
            in_type = self.in_type.get()
            raw_w = round(float(self.in_weight.get()), 2)
            if raw_w <= 0: raise ValueError

            if in_type == "ذهب":
                carat = round(float(self.in_carat.get()), 2)
                if carat <= 0: raise ValueError
                final_w = round((raw_w * carat) / 18.0, 2)
                op_type = "وارد ذهب (عيار 18)"
            else:
                carat = 0.0
                final_w = raw_w
                op_type = {"فصوص وأحجار": "وارد فصوص وأحجار", "الماس": "وارد الماس"}[in_type]

            # البيان يبقى فارغاً تماماً إلا لو سجّل المستخدم بياناً فعلياً
            note = self.in_note.get().strip()

            if not messagebox.askyesno("تأكيد الترحيل", "هل أنت متأكد من ترحيل حركة الوارد؟"):
                return

            # التعرف على أي اسم صندوق خياس (أو اسم مسترجعه) لمعاملته كاسترجاع خياس، وليس كمورد جديد
            mustarja_map = {}  # اسم صندوق الخياس -> اسم المسترجع الخاص به
            box_cat_map = {}   # اسم صندوق الخياس -> مفتاح القسم (cat) لاستخدامه بحساب الخياس الحالي
            for _stage_cat in self.get_all_stage_categories():
                _box_acc = self.get_box_account_name(_stage_cat)
                _, _, _mustarja_name = self.get_stage_config(_stage_cat)
                if _box_acc and _mustarja_name:
                    mustarja_map[_box_acc] = _mustarja_name
                    box_cat_map[_box_acc] = _stage_cat

            all_mustarja_names = set(mustarja_map.values())

            recovered_box_account = None
            if supplier in mustarja_map:
                recovered_box_account = supplier
                supplier = mustarja_map[supplier]
            elif supplier in all_mustarja_names:
                recovered_box_account = next((box for box, must in mustarja_map.items() if must == supplier), None)

            # نلتقط الخياس الحالي (غير المُقفل) للصندوق *قبل* ترحيل عملية الوارد، لأنه هو المبلغ المُعتمد للتصفير/الاسترجاع
            pre_khayas = 0.0
            if recovered_box_account:
                _box_cat = box_cat_map.get(recovered_box_account)
                if _box_cat:
                    pre_khayas = self.get_current_unclosed_khayas(_box_cat)

            fixed_names = set(mustarja_map.values())
            if supplier != "المصنع" and supplier not in fixed_names and not self.check_name_exists(supplier):
                self.categories["الموردين"].append(supplier)
                self.save_name_to_db(supplier, "الموردين")

            self.invoice_counter += 1
            main_inv_id = self.invoice_counter
            full_date = f"{d_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
            inv_data = {
                "رقم الفاتورة": self.invoice_counter,
                "التاريخ": full_date,
                "الاسم": supplier,
                "النوع": op_type,
                "الوزن": final_w, "قبل": raw_w, "بعد": carat, "البيان": note, "settled_status": "ACTIVE",
                "trees_count": 0.0, "set_number": voucher
            }
            self.invoices[self.invoice_counter] = inv_data
            self.save_invoice_to_db(self.invoice_counter, inv_data)

            # إذا كان استرجاعاً لصندوق خياس: العملية نفسها تُسهم طبيعياً بجزء منها (باسم المسترجع)،
            # والباقي (آخر خياس قبل هذه العملية ناقص وزن هذه العملية) يُصفِّر الصندوق دائماً عبر قيد يومي،
            # بصرف النظر عن إشارته (سواء كان الصندوق عليه خياس موجب أو كان دائناً)، ويُسجَّل في صندوق الخسائر ببيان "مسترجع"
            remainder = round(pre_khayas - final_w, 2) if recovered_box_account else 0.0
            if recovered_box_account and remainder != 0:
                entry_ref = f"JE-{self.invoice_counter + 1}"
                full_dt2 = full_date
                je_amount = abs(remainder)
                # remainder > 0: الصندوق ما زال عليه خياس متبقٍّ بعد هذه العملية -> إقفاله بقيد عادي (مدين الخسائر / دائن الصندوق)
                # remainder < 0: هذه العملية تجاوزت ما كان مطلوباً (تصفير + زيادة) -> قيد معاكس (دائن الخسائر / مدين الصندوق)
                from_name, from_type = ("حساب الخسائر", "قيد يومي مدين") if remainder > 0 else (recovered_box_account, "قيد يومي مدين")
                to_name, to_type = (recovered_box_account, "قيد يومي دائن") if remainder > 0 else ("حساب الخسائر", "قيد يومي دائن")

                self.invoice_counter += 1
                je_from = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt2, "الاسم": from_name,
                           "النوع": from_type, "الوزن": je_amount, "البيان": "مسترجع", "settled_status": "ACTIVE",
                           "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
                self.invoices[self.invoice_counter] = je_from
                self.save_invoice_to_db(self.invoice_counter, je_from)

                self.invoice_counter += 1
                je_to = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt2, "الاسم": to_name,
                         "النوع": to_type, "الوزن": je_amount, "البيان": "مسترجع", "settled_status": "ACTIVE",
                         "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
                self.invoices[self.invoice_counter] = je_to
                self.save_invoice_to_db(self.invoice_counter, je_to)

            self.in_weight.delete(0, 'end')
            self.in_carat.delete(0, 'end')
            self.in_note.delete(0, 'end')
            # الاحتفاظ برقم الفاتورة المسجَّل كما هو (لا يُستبدل برقم تلقائي)
            self._last_inbound_voucher = voucher
            self.in_invoice_num.delete(0, 'end')
            self.in_invoice_num.insert(0, voucher)
            self.in_supplier.configure(values=self.get_supplier_name_values())
            self.in_supplier.set("المصنع")

            self.register_operation_period(d_val)
            self.recalculate_all()
            messagebox.showinfo("نجاح", f"تم تسجيل الوارد ({in_type}) بنجاح.")
            if messagebox.askyesno("طباعة", "هل تريد طباعة العملية؟"):
                self.print_single_inout_operation(main_inv_id)

            self.in_weight.focus()
        except ValueError:
            messagebox.showerror("خطأ", "الرجاء إدخال التاريخ والأوزان بشكل صحيح")

    def print_generic_table_screen(self, title, cols, col_ratios, rows, filename_prefix, subtitle=""):
        """قالب طباعة عام: نفس رأس الصفحة الموحّد (شعار + بيانات الشركة بدون تداخل) + جدول بأعمدة ديناميكية + دعم تعدد الصفحات"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "ميزة الطباعة تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return
        out_dir = INVOICES_DIR
        out_path = os.path.join(out_dir, f"{filename_prefix}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        from reportlab.lib.colors import Color
        PW, PH = A4
        M = 10 * mm
        header_fill = Color(0.78, 0.80, 0.93)
        border_color = Color(0.15, 0.15, 0.55)

        def txt(c, x, y, s, size=9, bold=False, align="right", color=None):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            if color: c.setFillColor(color)
            s = ar(s)
            if align == "right": c.drawRightString(x, y, s)
            elif align == "left": c.drawString(x, y, s)
            else: c.drawCentredString(x, y, s)
            if color: c.setFillColorRGB(0, 0, 0)

        def rect(c, x, y, w, h, fill=None, stroke_color=None):
            c.saveState()
            if stroke_color: c.setStrokeColor(stroke_color)
            if fill:
                c.setFillColor(fill)
                c.rect(x, y - h, w, h, fill=1, stroke=1)
            else:
                c.rect(x, y - h, w, h, fill=0, stroke=1)
            c.restoreState()

        table_w = PW - 2 * M
        ratio_sum = sum(col_ratios)
        col_ws = [table_w * r / ratio_sum for r in col_ratios]
        col_x_starts = []
        acc = 0.0
        for w in col_ws:
            col_x_starts.append(acc); acc += w

        row_h = 8 * mm
        header_h = 10 * mm
        max_rows_per_page = 26

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        idx = 0
        total_rows = len(rows)
        page_num = 1

        while idx < total_rows or (idx == 0 and total_rows == 0):
            y = PH - M
            txt(c, M, y - 6, "Jadeite Factory", size=11, bold=True, align="left")
            txt(c, M, y - 12, "Saudi Arabia, Riyadh", size=7, align="left")
            txt(c, PW - M, y - 6, "مصنع جاديت للتصنيع", size=11, bold=True, align="right")
            txt(c, PW - M, y - 12, "المملكة العربية السعودية", size=7, align="right")
            logo_bottom = y - 12
            try:
                logo_bytes = base64.b64decode(APP_LOGO_B64)
                logo_img = ImageReader(io.BytesIO(logo_bytes))
                lw, lh = 40 * mm, 9 * mm
                logo_top = y - 3
                logo_bottom = logo_top - lh
                c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
            except Exception:
                pass
            y = min(y - 12, logo_bottom) - 8 * mm

            txt(c, PW / 2, y, title, size=15, bold=True, align="center", color=border_color)
            y -= 6 * mm
            if subtitle:
                txt(c, PW / 2, y, subtitle, size=10, align="center")
                y -= 5 * mm
            if page_num > 1:
                txt(c, M, y, f"(تابع - صفحة {page_num})", size=9, align="left")
            y -= 7 * mm

            table_top = y
            rect(c, M, table_top, table_w, header_h, fill=header_fill, stroke_color=border_color)
            for i, lbl in enumerate(cols):
                cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                hdr_size = fit_font_size(lbl, col_ws[i] - 3 * mm, 10, bold=True, min_size=6.5)
                txt(c, cx, vcenter_baseline(table_top, header_h, hdr_size), lbl, size=hdr_size, bold=True, align="center", color=border_color)
                if i > 0:
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], table_top - header_h, M + table_w - col_x_starts[i], table_top)

            y = table_top - header_h
            page_rows = rows[idx: idx + max_rows_per_page]
            for row_vals in page_rows:
                rect(c, M, y, table_w, row_h, stroke_color=border_color)
                for i in range(1, len(cols)):
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], y - row_h, M + table_w - col_x_starts[i], y)
                for i, val in enumerate(row_vals):
                    cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                    val_str = str(val)
                    val_size = fit_font_size(val_str, col_ws[i] - 3 * mm, 9, min_size=6)
                    txt(c, cx, vcenter_baseline(y, row_h, val_size), val_str, size=val_size, align="center")
                y -= row_h
            idx += len(page_rows)

            if idx >= total_rows:
                txt(c, PW / 2, max(y - 8 * mm, 15 * mm), f"تاريخ الطباعة: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", size=9, align="center")

            c.showPage()
            page_num += 1
            if total_rows == 0:
                break

        c.save()
        self._open_file(out_path)

    def print_inout_screen(self):
        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18", "البيان")
        col_ratios = [0.8, 1.1, 1.2, 1.3, 0.8, 0.7, 0.8, 1.3]
        rows = []
        for inv in sorted(self.invoices.values(), key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0))):
            if inv.get("settled_status") != "ACTIVE": continue
            t = inv.get("النوع", "")
            if not t.startswith("وارد"): continue
            if not self.inv_in_period(inv, self.current_display_month): continue
            carat_disp = f"{inv.get('بعد', 0):.2f}" if t == "وارد ذهب (عيار 18)" else "-"
            raw_w_disp = inv.get("قبل", 0.0) or inv["الوزن"]
            rows.append((inv.get("set_number") or inv["رقم الفاتورة"], inv["التاريخ"][:16], inv["الاسم"], t.replace("وارد ", ""),
                         f"{raw_w_disp:.2f}", carat_disp, f"{inv['الوزن']:.2f}", inv.get("البيان", "")))
        self.print_generic_table_screen("📥 كشف الوارد/قبض", cols, col_ratios, rows, "inout_screen",
                                         subtitle=f"الفترة: {self.current_display_month}")

    def print_single_inout_operation(self, inv_id):
        """يطبع عملية وارد واحدة بعينها فقط (وليس الكشف الشهري كاملاً)"""
        inv = self.invoices.get(inv_id)
        if not inv:
            return
        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "النوع", "الوزن", "العيار", "وزن 18", "البيان")
        col_ratios = [0.8, 1.1, 1.2, 1.3, 0.8, 0.7, 0.8, 1.3]
        t = inv.get("النوع", "")
        carat_disp = f"{inv.get('بعد', 0):.2f}" if t == "وارد ذهب (عيار 18)" else "-"
        raw_w_disp = inv.get("قبل", 0.0) or inv["الوزن"]
        rows = [(inv.get("set_number") or inv["رقم الفاتورة"], inv["التاريخ"][:16], inv["الاسم"], t.replace("وارد ", ""),
                 f"{raw_w_disp:.2f}", carat_disp, f"{inv['الوزن']:.2f}", inv.get("البيان", ""))]
        self.print_generic_table_screen("📥 عملية وارد/قبض", cols, col_ratios, rows, "inout_operation")

    def refresh_inout_tables(self):
        if not hasattr(self, 'tree_in') or not self.tree_in: return
        for item in self.tree_in.get_children(): self.tree_in.delete(item)

        sorted_inout = sorted(self.invoices.values(), key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)), reverse=True)

        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        tot_gold_18 = tot_gems_stones = tot_diamond = 0.0

        for inv in sorted_inout:
            if (inv.get("settled_status") == "ACTIVE" and inv.get("النوع") in in_types
                    and self.inv_in_period(inv, self.current_display_month)
                    and inv.get("trees_count") != 1.0):  # استبعاد قيود الرصيد الافتتاحي (تظهر في شاشتها فقط)
                carat_disp = f"{inv['بعد']:.1f}" if inv["النوع"] == "وارد ذهب (عيار 18)" else "-"
                raw_w_disp = inv.get("قبل", inv["الوزن"])
                voucher_disp = inv.get("set_number") or inv["رقم الفاتورة"]
                self.tree_in.insert("", "end", iid=str(inv["رقم الفاتورة"]), values=(
                    voucher_disp, inv["التاريخ"], inv["الاسم"],
                    inv["النوع"].replace("وارد ", ""), f"{raw_w_disp:.2f}", carat_disp, f"{inv['الوزن']:.2f}", inv["البيان"]
                ))
                if inv["النوع"] == "وارد ذهب (عيار 18)": tot_gold_18 += inv["الوزن"]
                elif inv["النوع"] == "وارد فصوص وأحجار": tot_gems_stones += inv["الوزن"]
                elif inv["النوع"] == "وارد الماس": tot_diamond += inv["الوزن"]

        if self.tree_in.get_children():
            self.tree_in.insert("", "end", iid="total_in", values=("-", "-", "-", "الإجمالي", "-", "-", f"{tot_gold_18:.2f}", f"فصوص وأحجار {tot_gems_stones:.2f} | ماس {tot_diamond:.2f}"), tags=("total_tag",))

        if hasattr(self, 'lbl_in_summary'):
            self.lbl_in_summary.configure(text=f"إجمالي الوارد: ذهب (صافي 18) {tot_gold_18:.2f} جم | فصوص وأحجار {tot_gems_stones:.2f} | ماس {tot_diamond:.2f}")

    # =========================================================================
    # --- شاشة الموردين: كشف مدين/دائن/رصيد لكل مورد (بما فيهم أسماء المسترجعات) ---
    # =========================================================================
    def get_material_balance(self, material):
        """الرصيد التراكمي لمادة: ذهب من رصيد الخزينة الحي، وباقي المواد = مدين(وارد) - دائن(مبيعات) عبر كل الوقت"""
        if material == "ذهب":
            return round(getattr(self, 'current_treasury_balance', 0.0), 2)
        in_type = {"فصوص وأحجار": "وارد فصوص وأحجار", "الماس": "وارد الماس"}.get(material)
        sale_type = {"فصوص وأحجار": "مبيعات فصوص وأحجار", "الماس": "مبيعات الماس"}.get(material)
        tot_in = tot_sale = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            if inv.get("النوع") == in_type: tot_in += inv["الوزن"]
            elif inv.get("النوع") == sale_type: tot_sale += inv["الوزن"]
        return round(tot_in - tot_sale, 2)

    # =========================================================================
    # --- شاشة المبيعات: ذهب / فصوص / أحجار / ماس في سطر واحد لكل عملية ---
    # =========================================================================
    def next_sale_row_number(self):
        """رقم السطر التالي في الفاتورة الحالية"""
        top = 0
        for r in getattr(self, "pending_sale_rows", []):
            try:
                top = max(top, int(str(r.get("row_number", "") or 0).strip() or 0))
            except (TypeError, ValueError):
                continue
        return top + 1

    def renumber_pending_sale_rows(self):
        """يُعيد ترقيم سطور الفاتورة ١..ن بعد أي حذف.

        بدونه تبقى فجوة في الترقيم (١، ٣، ٤) فيبدو للمستخدم أن سطراً ضاع.
        """
        for i, r in enumerate(getattr(self, "pending_sale_rows", []), start=1):
            r["row_number"] = str(i)

    def check_sale_row_duplicate(self, rows, row_num, set_num, skip_index=None, parent=None):
        """يمنع تكرار رقم الصف (ورقم التشغيل) داخل سطور الفاتورة الواحدة فقط.
        بعد الترحيل تبدأ فاتورة جديدة، فيجوز استخدام رقم الصف ١ من جديد بشكل طبيعي.
        يرجع True لو فيه تكرار (أي يجب إيقاف الإضافة)."""
        for i, r in enumerate(rows):
            if skip_index is not None and i == skip_index:
                continue
            if row_num and (r.get("row_number", "") or "") == row_num:
                messagebox.showwarning(
                    "رقم صف مكرر",
                    f"رقم الصف ({row_num}) مسجّل بالفعل في سطر آخر من هذه الفاتورة.\n\n"
                    "استخدم رقم صف مختلف، أو عدّل السطر الموجود بدل إضافة سطر جديد.",
                    parent=parent)
                return True
            if set_num and (r.get("set_number", "") or "") == set_num:
                messagebox.showwarning(
                    "رقم تشغيل مكرر",
                    f"رقم التشغيل ({set_num}) مسجّل بالفعل في سطر آخر من هذه الفاتورة.\n\n"
                    "لا يصح تكراره لأن كل رقم تشغيل يُطبع كفاتورة مستقلة، وتكراره يدمج السطرين في قالب واحد.",
                    parent=parent)
                return True
        return False

    def build_sales_tab(self):
        outer_raw = self.tabview.tab("المبيعات")

        # الشاشة تحوي عدداً كبيراً من الحقول والجداول، وبدون تمرير كانت
        # عناصرها السفلية تُقطع على الشاشات الأصغر بلا وسيلة للوصول إليها.
        # الحاوية بلون النظام لا ttk.Frame الافتراضي (كان يكشف خلفية سوداء
        # في الفراغ أعلى المحتوى أو أسفله أثناء التمرير)
        sales_scroll_outer = ctk.CTkFrame(outer_raw, fg_color=("#d9d9d9", "#1c1c1c"),
                                           corner_radius=0)
        sales_scroll_outer.pack(fill="both", expand=True)
        try:
            outer_raw.configure(fg_color=("#d9d9d9", "#1c1c1c"))
        except Exception:
            pass

        # لون الخلفية يتبع سمة النظام: رصاصي فاتح في المظهر الفاتح، وداكن في الداكن
        sales_bg = "#d9d9d9" if ctk.get_appearance_mode() == "Light" else "#1c1c1c"
        sales_canvas = tk.Canvas(sales_scroll_outer, highlightthickness=0, bd=0, bg=sales_bg)
        sales_vsb = ttk.Scrollbar(sales_scroll_outer, orient="vertical", command=sales_canvas.yview)
        sales_canvas.configure(yscrollcommand=sales_vsb.set)
        sales_vsb.pack(side="right", fill="y")
        sales_canvas.pack(side="left", fill="both", expand=True)

        outer = ctk.CTkFrame(sales_canvas, fg_color=("#d9d9d9", "#1c1c1c"))
        sales_canvas_window = sales_canvas.create_window((0, 0), window=outer, anchor="nw")

        def _on_sales_frame_configure(event=None):
            sales_canvas.configure(scrollregion=sales_canvas.bbox("all"))

        def _on_sales_canvas_configure(event):
            # المحتوى يُمدّد ليملأ عرض وارتفاع اللوحة معاً: بدون تمديد الارتفاع
            # يبقى فراغ أسفل المحتوى تظهر فيه خلفية اللوحة كشريط داكن
            sales_canvas.itemconfig(sales_canvas_window, width=event.width)
            content_h = outer.winfo_reqheight()
            if content_h < event.height:
                sales_canvas.itemconfig(sales_canvas_window, height=event.height)
            else:
                sales_canvas.itemconfig(sales_canvas_window, height="")

        outer.bind("<Configure>", _on_sales_frame_configure)
        sales_canvas.bind("<Configure>", _on_sales_canvas_configure)

        def _sales_mousewheel(event):
            sales_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        sales_canvas.bind("<Enter>", lambda e: sales_canvas.bind_all("<MouseWheel>", _sales_mousewheel))
        sales_canvas.bind("<Leave>", lambda e: sales_canvas.unbind_all("<MouseWheel>"))

        # ====== شريط التبويب الداخلي: (المبيعات) للإدخال و(العمليات) للفواتير المرحّلة ======
        sub_bar = ctk.CTkFrame(outer, fg_color="transparent")
        sub_bar.pack(fill="x", padx=20, pady=(10, 0))

        self.sales_subtab_buttons = {}
        for key, label in [("المبيعات", "🧾 المبيعات"), ("العمليات", "📚 العمليات")]:
            b = ctk.CTkButton(sub_bar, text=label, font=("Cairo", 16, "bold"), width=150, height=42,
                              command=lambda k=key: self.switch_sales_subtab(k))
            b.pack(side="right", padx=5)
            self.sales_subtab_buttons[key] = b

        self.sales_entry_frame = ctk.CTkFrame(outer, fg_color="transparent")
        self.sales_ops_frame = ctk.CTkFrame(outer, fg_color="transparent")

        # كل واجهة الإدخال الحالية تُبنى داخل تبويب (المبيعات)
        tab = self.sales_entry_frame

        top_row = ctk.CTkFrame(tab, fg_color="transparent")
        top_row.pack(fill="x", padx=20, pady=(12, 4))

        ctk.CTkLabel(top_row, text="🧾 شاشة المبيعات/الصادر", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(side="right", padx=10)

        self.sale_date = ctk.CTkEntry(top_row, font=("Cairo", 15), justify="center", width=120, height=36)
        self.sale_date.insert(0, self.get_smart_default_date())
        self.sale_date.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="التاريخ:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        self.sale_invoice_num = ctk.CTkEntry(top_row, font=("Cairo", 15, "bold"), justify="center", width=110, height=36,
                                             placeholder_text="رقم الفاتورة")
        self.sale_invoice_num.pack(side="right", padx=5)
        ctk.CTkLabel(top_row, text="رقم الفاتورة (يدوي):", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        ctk.CTkLabel(top_row, text="الاسم (من الموردين):", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.sale_name = ctk.CTkComboBox(top_row, values=self.get_supplier_name_values_no_mustarja(), font=("Cairo", 15), justify="right", width=210, height=36)
        self.sale_name.set("المصنع")
        self.sale_name.pack(side="right", padx=5)
        self.bind_name_autocomplete(self.sale_name, self.get_supplier_name_values_no_mustarja)

        self.lbl_sales_status = ctk.CTkLabel(tab, text="", font=("Cairo", 15, "bold"), text_color="#2ecc71")
        self.lbl_sales_status.pack()

        fields_row = ctk.CTkFrame(tab, corner_radius=10)
        fields_row.pack(fill="x", padx=20, pady=8)

        def add_field(label_text):
            col = ctk.CTkFrame(fields_row, fg_color="transparent")
            col.pack(side="right", padx=12, pady=10)
            ctk.CTkLabel(col, text=label_text, font=("Cairo", 14, "bold")).pack(pady=(2, 3))
            ent = ctk.CTkEntry(col, justify="center", font=("Cairo", 14), width=78, height=32)
            ent.pack()
            return ent

        # رقم الصف يُرقَّم تلقائياً حسب ترتيب السطر في الفاتورة، فلا حاجة
        # لخانة إدخال له. يبقى الكائن مخفياً لأن كوداً آخر يقرأ منه ويكتب فيه.
        _row_holder = ctk.CTkFrame(fields_row, fg_color="transparent")
        self.sale_row_number = ctk.CTkEntry(_row_holder, width=1)
        self.sale_set_number = add_field("رقم التشغيل")
        self.sale_gold = add_field("الذهب")
        self.sale_gems = add_field("الفصوص")
        self.sale_stones = add_field("الأحجار")
        self.sale_stones_discount = add_field("الأحجار بعد الخصم")
        self.sale_khayas = add_field("خياس التلميع النهائي")
        self.sale_khayas_polish = add_field("خياس البوليش")
        self.sale_khayas_assembler = add_field("خياس المركب")
        self.sale_diamond = add_field("الماس")

        # خياس المركب يُجلب تلقائياً من مراحل التصنيع بمجرد كتابة رقم التشغيل
        self.sale_set_number.bind("<KeyRelease>", self.autofill_assembler_khayas, add="+")
        self.sale_set_number.bind("<FocusOut>", self.autofill_assembler_khayas, add="+")
        # الوزنان يُحسبان تلقائياً ويظهران في الجدول، فلا داعي لخانتَي إدخال لهما.
        # نُبقيهما ككائنين مخفيّين لأن كوداً آخر يقرأ منهما ويكتب فيهما.
        hidden_holder = ctk.CTkFrame(fields_row, fg_color="transparent")
        self.sale_weight_standing = ctk.CTkEntry(hidden_holder, width=1)
        self.sale_weight_bound = ctk.CTkEntry(hidden_holder, width=1)

        # ====== نسبة الخصم القابلة للاختيار والإضافة (تُضرب في الأحجار تلقائياً) ======
        pct_col = ctk.CTkFrame(fields_row, fg_color="transparent")
        pct_col.pack(side="right", padx=12, pady=10)
        ctk.CTkLabel(pct_col, text="نسبة الخصم", font=("Cairo", 14, "bold")).pack(pady=(2, 3))
        pct_row = ctk.CTkFrame(pct_col, fg_color="transparent")
        pct_row.pack()
        self.sale_discount_pct = ctk.CTkComboBox(pct_row, values=[f"{p}%" for p in self.get_discount_percentages()],
                                                   font=("Cairo", 13), width=80, height=34, justify="center",
                                                   command=lambda choice: self.on_discount_pct_change())
        self.sale_discount_pct.set(f"{self.get_last_discount_percentage()}%")
        self.sale_discount_pct.pack(side="right", padx=(3, 0))
        btn_add_pct = ctk.CTkButton(pct_row, text="➕", font=("Cairo", 13, "bold"), width=30, height=34, fg_color="#1e8449", hover_color="#145a32", command=self.open_add_discount_pct_dialog)
        btn_add_pct.pack(side="right", padx=(3, 0))

        def safe_read(entry):
            try:
                return float(entry.get().strip()) if entry.get().strip() else 0.0
            except ValueError:
                return 0.0

        def recompute_sale_totals(event=None):
            gold_v = safe_read(self.sale_gold)
            gems_v = safe_read(self.sale_gems)
            stones_v = safe_read(self.sale_stones)
            stones_disc_v = safe_read(self.sale_stones_discount)
            diamond_v = safe_read(self.sale_diamond)
            weight_standing = round(gold_v + gems_v + stones_v + diamond_v, 2)
            weight_bound = round(gold_v + gems_v + stones_disc_v + diamond_v, 2)
            self.sale_weight_standing.delete(0, 'end')
            self.sale_weight_bound.delete(0, 'end')
            if gold_v or gems_v or stones_v or diamond_v:
                self.sale_weight_standing.insert(0, f"{weight_standing}")
                self.sale_weight_bound.insert(0, f"{weight_bound}")
        self._recompute_sale_totals = recompute_sale_totals

        def auto_compute_stones_discount(event=None):
            try:
                raw = float(self.sale_stones.get().strip()) if self.sale_stones.get().strip() else 0.0
            except ValueError:
                raw = 0.0
            try:
                pct = float(self.sale_discount_pct.get().strip().replace("%", "")) / 100.0
            except ValueError:
                pct = 0.30
            self.sale_stones_discount.delete(0, 'end')
            if raw > 0:
                self.sale_stones_discount.insert(0, f"{round(raw * pct, 2)}")
            recompute_sale_totals()
        self._auto_compute_stones_discount = auto_compute_stones_discount
        self.sale_stones.bind("<KeyRelease>", auto_compute_stones_discount)
        self.sale_gold.bind("<KeyRelease>", recompute_sale_totals)
        self.sale_gems.bind("<KeyRelease>", recompute_sale_totals)
        self.sale_diamond.bind("<KeyRelease>", recompute_sale_totals)

        bottom_entry_frame = ctk.CTkFrame(tab, fg_color="transparent")
        bottom_entry_frame.pack(fill="x", padx=20, pady=(0, 8))
        btn_add_row = ctk.CTkButton(bottom_entry_frame, text="➕ إضافة سطر للفاتورة الحالية", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), height=38, width=220, fg_color="#1e8449", hover_color="#145a32", command=self.stage_sale_row)
        btn_add_row.pack(side="right", padx=8)

        # التنقل بزر Enter بين الخانات، وإضافة السطر تلقائياً عند آخر خانة (بدون ترحيل الفاتورة)
        nav_fields = [self.sale_name, self.sale_set_number, self.sale_gold, self.sale_gems,
                      self.sale_stones, self.sale_stones_discount, self.sale_khayas, self.sale_khayas_polish,
                      self.sale_khayas_assembler, self.sale_diamond]
        for i, f in enumerate(nav_fields[:-1]):
            f.bind("<Return>", lambda e, nxt=nav_fields[i + 1]: nxt.focus_set() or "break")
        nav_fields[-1].bind("<Return>", lambda e: self.stage_sale_row() or "break")

        # التنقل بالأسهم يمين/يسار بين الخانات.
        # الترتيب معكوس عمداً: الخانات مرصوفة من اليمين لليسار (side="right")،
        # فالسهم الأيسر ينتقل للخانة التالية بصرياً، والأيمن للسابقة.
        self.bind_arrow_navigation(nav_fields)

        # ====== جدول السطور المعلّقة (غير مرحّلة بعد) ======
        pending_top = ctk.CTkFrame(tab, fg_color="transparent")
        pending_top.pack(fill="x", padx=20, pady=(10, 2))
        ctk.CTkLabel(pending_top, text="📝 سطور الفاتورة الحالية (لم تُرحَّل بعد)", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), text_color="#f1c40f").pack(side="right")
        btn_del_pending = ctk.CTkButton(pending_top, text="حذف السطر المعلّق 🗑️", font=("Cairo", 14, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=32, command=self.delete_pending_sale_row)
        btn_del_pending.pack(side="left", padx=5)

        self.btn_sales_sort = ctk.CTkButton(
            pending_top, text="⬇️ تنازلي", font=("Cairo", 14, "bold"),
            fg_color="#555555", hover_color="#333333", width=110, height=32,
            command=self.toggle_pending_sales_order)
        self.btn_sales_sort.pack(side="left", padx=5)

        ctk.CTkButton(pending_top, text="✅ ترحيل الفاتورة", font=("Cairo", 14, "bold"),
                      fg_color="#1e8449", hover_color="#145a32", width=160, height=32,
                      command=self.commit_sale_invoice).pack(side="left", padx=5)

        btn_edit_pending = ctk.CTkButton(pending_top, text="تعديل السطر المعلّق ✏️", font=("Cairo", 14, "bold"), fg_color="#b8860b", hover_color="#daa520", width=170, height=32, command=self.edit_pending_sale_row)
        btn_edit_pending.pack(side="left", padx=5)

        self.pending_sales_table_frame = ttk.Frame(tab)
        self.pending_sales_table_frame.pack(fill="both", expand=True, padx=20, pady=(2, 6))
        self.pending_sales_tree = None
        self.pending_sale_rows = []

        btn_commit = ctk.CTkButton(tab, text="✅ ترحيل واعتماد الفاتورة", font=ctk.CTkFont(family="Cairo", size=15, weight="bold"), height=44, fg_color="#144d75", hover_color="#0d3350", command=self.commit_sale_invoice)
        btn_commit.pack(pady=8)

        # ====== كشف حركة المبيعات المرحّلة ======
        # شريط الأرصدة يتبع سمة النظام بدل الأسود الثابت، وبارتفاع أصغر
        # لتُترك المساحة للجدول
        balance_bar = ctk.CTkFrame(tab, corner_radius=8, fg_color=("#c9cdd2", "#2a2f36"))
        balance_bar.pack(fill="x", padx=20, pady=(6, 6))
        self.lbl_sales_balance = ctk.CTkLabel(balance_bar, text="", font=ctk.CTkFont(family="Cairo", size=14, weight="bold"), text_color=("#7a5c00", "#f1c40f"))
        self.lbl_sales_balance.pack(pady=6)

        self.build_sales_ops_ui(self.sales_ops_frame)
        self.switch_sales_subtab("المبيعات")

        self.refresh_pending_sales_table()
        self.refresh_sales_table()

    def switch_sales_subtab(self, key):
        """التنقل بين تبويب إدخال المبيعات وتبويب الفواتير المرحّلة"""
        self.current_sales_subtab = key
        for k, btn in self.sales_subtab_buttons.items():
            btn.configure(fg_color="#d4af37" if k == key else "#1f77b4",
                          text_color="#000000" if k == key else "#ffffff")
        self.sales_entry_frame.pack_forget()
        self.sales_ops_frame.pack_forget()
        if key == "العمليات":
            self.sales_ops_frame.pack(fill="both", expand=True)
            self.refresh_sales_ops_table()
        else:
            self.sales_entry_frame.pack(fill="both", expand=True)

    # =====================================================================
    # ---------- تبويب (العمليات): كل فاتورة مبيعات مرحّلة في صف واحد ----------
    # =====================================================================
    SALE_TYPES = ("مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس")

    def get_sale_invoice_groups(self, month=None):
        """يجمع حركات المبيعات في فواتير: مفتاح كل فاتورة (رقم الفاتورة اليدوي + التاريخ + الاسم).
        يرجع قائمة قواميس بإجماليات كل فاتورة وقائمة أرقام حركاتها.

        تشمل السطور المعلوماتية (MEMO) لأنها جزء من الفاتورة عرضاً وتعديلاً،
        لكنها مستبعدة من كل الحسابات المالية في مواضعها."""
        groups = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue
            t = inv.get("النوع")
            if t not in self.SALE_TYPES and t != "خياس طقوم":
                continue
            dt = inv.get("التاريخ", "")
            # التصفية بالفترة المحاسبية لا بتاريخ الحركة: فاتورة فترة ٨ قد
            # تحمل تاريخ شهر ٩، وكانت تختفي من عمليات فترة ٨ بسببه
            if not self.inv_in_period(inv, month):
                continue
            key = (inv.get("رقم الفاتورة اليدوي", "") or "", dt, inv.get("الاسم", ""))
            g = groups.setdefault(key, {
                "manual_no": key[0], "date": dt, "name": key[2], "ids": [], "sets": set(),
                "ذهب": 0.0, "فصوص": 0.0, "أحجار": 0.0, "أحجار بعد الخصم": 0.0, "الماس": 0.0, "خياس": 0.0,
                "first_id": inv.get("رقم الفاتورة", 0)})
            g["ids"].append(inv.get("رقم الفاتورة", 0))
            if inv.get("set_number"):
                g["sets"].add(inv.get("set_number"))
            g["first_id"] = min(g["first_id"], inv.get("رقم الفاتورة", 0))
            w = inv.get("الوزن", 0.0)
            if t in ("مبيعات ذهب", "مبيعات ذهب مع الماس"):
                g["ذهب"] = round(g["ذهب"] + w, 2)
            elif t == "مبيعات فصوص وأحجار":
                if inv.get("trees_count") == 3.0:
                    g["أحجار"] = round(g["أحجار"] + inv.get("قبل", 0.0), 2)
                    g["أحجار بعد الخصم"] = round(g["أحجار بعد الخصم"] + w, 2)
                else:
                    g["فصوص"] = round(g["فصوص"] + w, 2)
            elif t == "مبيعات الماس":
                g["الماس"] = round(g["الماس"] + w, 2)
            elif t == "خياس طقوم":
                if (inv.get("trees_count", 0.0) or 0.0) in (KHAYAS_MARK_NET, KHAYAS_MARK_ASSEMBLER,
                                                            KHAYAS_MARK_POLISH):
                    continue      # سطور معلوماتية لا تُضاف لإجمالي خياس الصندوق
                g["خياس"] = round(g["خياس"] + w, 2)

        result = list(groups.values())
        result.sort(key=lambda g: (g["date"], g["first_id"]))
        return result

    def build_sales_ops_ui(self, parent):
        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkLabel(head, text="📚 الفواتير المرحّلة (كل فاتورة في صف)", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(side="right", padx=10)

        ctk.CTkButton(head, text="🖨️ معاينة وطباعة", font=("Cairo", 14, "bold"), width=155, height=34,
                      fg_color="#1f77b4", hover_color="#144d75", command=self.preview_selected_sale_invoice).pack(side="left", padx=5)
        ctk.CTkButton(head, text="حذف الفاتورة 🗑️", font=("Cairo", 14, "bold"), width=155, height=34,
                      fg_color="#8b0000", hover_color="#a52a2a", command=self.delete_selected_sale_invoice).pack(side="left", padx=5)
        ctk.CTkButton(head, text="تعديل الفاتورة ✏️", font=("Cairo", 14, "bold"), width=155, height=34,
                      fg_color="#b8860b", hover_color="#daa520", command=self.edit_selected_sale_invoice).pack(side="left", padx=5)

        self.sales_ops_table_frame = ttk.Frame(parent)
        self.sales_ops_table_frame.pack(fill="both", expand=True, padx=20, pady=(4, 4))
        self.sales_ops_tree = None
        self.sales_ops_map = {}

        self.lbl_sales_ops_totals = ctk.CTkLabel(parent, text="", font=("Cairo", 15, "bold"), text_color="#d4af37")
        self.lbl_sales_ops_totals.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(parent, text="اضغط مرتين على أي فاتورة لفتح نافذة تعديلها بكل سطورها",
                     font=("Cairo", 11), text_color="#aaaaaa").pack(pady=(0, 8))

    def refresh_sales_ops_table(self):
        if not hasattr(self, 'sales_ops_table_frame') or not self.sales_ops_table_frame:
            return
        for widget in self.sales_ops_table_frame.winfo_children():
            widget.destroy()

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "الذهب", "الفصوص", "الأحجار بعد الخصم", "الماس", "خياس", "عدد الأسطر")
        self.sales_ops_tree = self.create_standard_treeview(self.sales_ops_table_frame, cols, height=13)
        self.sales_ops_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 175 if c == "التاريخ" else 165 if c == "الاسم" else 120
            self.sales_ops_tree.column(c, width=w, anchor="center")
        self.sales_ops_tree.bind("<Double-1>", lambda e: self.edit_selected_sale_invoice())

        self.sales_ops_map = {}
        tot = {k: 0.0 for k in ("ذهب", "فصوص", "أحجار بعد الخصم", "الماس", "خياس")}
        groups = self.get_sale_invoice_groups(self.current_display_month)

        for g in groups:
            for k in tot:
                tot[k] = round(tot[k] + g[k], 2)
            item = self.sales_ops_tree.insert("", "end", values=(
                g["manual_no"] or g["first_id"], g["date"], g["name"],
                f"{g['ذهب']:.2f}" if g["ذهب"] else "-",
                f"{g['فصوص']:.2f}" if g["فصوص"] else "-",
                f"{g['أحجار بعد الخصم']:.2f}" if g["أحجار بعد الخصم"] else "-",
                f"{g['الماس']:.2f}" if g["الماس"] else "-",
                f"{g['خياس']:.2f}" if g["خياس"] else "-",
                len(g["sets"]) or 1,
            ))
            self.sales_ops_map[item] = (g["manual_no"], g["date"], g["name"])

        if groups:
            self.sales_ops_tree.insert("", "end", values=(
                "إجمالي الشهر", "-", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}",
                f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}", len(groups)
            ), tags=("total_tag",))

        if hasattr(self, 'lbl_sales_ops_totals'):
            self.lbl_sales_ops_totals.configure(
                text=(f"إجماليات الفترة ({self.current_display_month}) — الذهب: {tot['ذهب']:.2f}  |  "
                      f"الفصوص: {tot['فصوص']:.2f}  |  الأحجار بعد الخصم: {tot['أحجار بعد الخصم']:.2f}  |  "
                      f"الماس: {tot['الماس']:.2f}  |  الخياس: {tot['خياس']:.2f} جم"))

    def get_selected_sale_invoice_key(self, action="تعديل"):
        if not (hasattr(self, 'sales_ops_tree') and self.sales_ops_tree):
            return None
        sel = self.sales_ops_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", f"الرجاء تحديد الفاتورة المراد {action}ها من الجدول أولاً.")
            return None
        key = self.sales_ops_map.get(sel[0])
        if not key:
            messagebox.showinfo("تنبيه", "هذا السطر إجمالي وليس فاتورة مستقلة.")
            return None
        return key

    def get_sale_invoice_records(self, key):
        """كل حركات فاتورة مبيعات واحدة حسب مفتاحها (رقم يدوي + تاريخ + اسم).

        تشمل السطور المعلوماتية ليُعاد بناؤها عند التعديل، ولتُحذف مع الفاتورة
        فلا تبقى سطور يتيمة بلا فاتورة."""
        manual_no, date_str, name = key
        recs = []
        for inv in self.invoices.values():
            if inv.get("settled_status") not in SALE_READ_STATUSES:
                continue
            t = inv.get("النوع")
            if t not in self.SALE_TYPES and t != "خياس طقوم":
                continue
            if (inv.get("رقم الفاتورة اليدوي", "") or "") != manual_no:
                continue
            if inv.get("التاريخ") != date_str or inv.get("الاسم") != name:
                continue
            recs.append(inv)
        return recs

    def sale_records_to_rows(self, recs):
        """يعيد بناء سطور الفاتورة (نفس شكل السطور المعلّقة) من الحركات المسجّلة"""
        rows = {}
        order = []
        for inv in sorted(recs, key=lambda x: x.get("رقم الفاتورة", 0)):
            set_num = inv.get("set_number", "") or ""
            if set_num not in rows:
                rows[set_num] = {"set_number": set_num, "row_number": inv.get("row_number", "") or "",
                                 "ذهب": 0.0, "فصوص": 0.0, "أحجار": 0.0, "أحجار بعد الخصم": 0.0,
                                 "الماس": 0.0, "خياس": 0.0, "خياس البوليش": 0.0,
                                 "خياس المركب": 0.0}
                order.append(set_num)
            r = rows[set_num]
            if not r["row_number"] and inv.get("row_number"):
                r["row_number"] = inv.get("row_number")
            t = inv.get("النوع")
            w = inv.get("الوزن", 0.0)
            if t in ("مبيعات ذهب", "مبيعات ذهب مع الماس"):
                r["ذهب"] = round(r["ذهب"] + w, 2)
            elif t == "مبيعات فصوص وأحجار":
                if inv.get("trees_count") == 3.0:
                    r["أحجار"] = round(r["أحجار"] + inv.get("قبل", 0.0), 2)
                    r["أحجار بعد الخصم"] = round(r["أحجار بعد الخصم"] + w, 2)
                else:
                    r["فصوص"] = round(r["فصوص"] + w, 2)
            elif t == "مبيعات الماس":
                r["الماس"] = round(r["الماس"] + w, 2)
            elif t == "خياس طقوم":
                mark = inv.get("trees_count", 0.0) or 0.0
                if mark == KHAYAS_MARK_NET:
                    continue      # سطر الصافي معلوماتي ويُعاد حسابه، فلا يُعاد تحميله
                if mark == KHAYAS_MARK_POLISH:
                    r["خياس البوليش"] = round(r["خياس البوليش"] + w, 2)
                elif mark == KHAYAS_MARK_ASSEMBLER:
                    r["خياس المركب"] = round(r["خياس المركب"] + w, 2)
                else:
                    r["خياس"] = round(r["خياس"] + w, 2)
        return [rows[s] for s in order]

    def post_sale_rows(self, rows, name, full_dt, manual_no):
        """يسجّل سطور فاتورة مبيعات كحركات محاسبية (نفس منطق الترحيل الأصلي، مصدر واحد موحّد
        يستخدمه الترحيل الجديد وتعديل الفاتورة المرحّلة معاً). يرجع قائمة (رقم التشغيل، التاريخ، الاسم)."""
        committed_groups = []
        for row in rows:
            gold_v = row.get("ذهب", 0.0)
            diamond_v = row.get("الماس", 0.0)
            gems_v = row.get("فصوص", 0.0)
            stones_raw_v = row.get("أحجار", 0.0)
            stones_discount_v = row.get("أحجار بعد الخصم", 0.0)
            set_num = row.get("set_number", "")
            row_num = row.get("row_number", "")
            khayas_v = row.get("خياس", 0.0)
            khayas_polish_v = row.get("خياس البوليش", 0.0)
            khayas_assembler_v = row.get("خياس المركب", 0.0)
            net_v = sale_net_weight(row)

            # إذا كان السطر يجمع ذهب وماس معاً، الذهب المرافق للماس يُسجَّل بنوع خاص
            gold_type = "مبيعات ذهب مع الماس" if (gold_v > 0 and diamond_v > 0) else "مبيعات ذهب"

            # "الأحجار" الخام لا تُعتمد كمبيعات؛ المعتمد محاسبياً هو "الأحجار بعد الخصم" فقط
            line_items = [
                (gold_v, gold_type, "مبيعات", 0.0, 0.0),
                (gems_v, "مبيعات فصوص وأحجار", "مبيعات", 0.0, 0.0),
                (stones_discount_v, "مبيعات فصوص وأحجار", "مبيعات", 3.0, stones_raw_v),
                (diamond_v, "مبيعات الماس", "مبيعات", 0.0, 0.0),
            ]
            for val, op_type, bayan, marker, raw_ref in line_items:
                if val > 0:
                    self.invoice_counter += 1
                    inv_data = {
                        "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name, "النوع": op_type,
                        "الوزن": val, "البيان": bayan, "settled_status": "ACTIVE", "trees_count": marker,
                        "قبل": raw_ref, "بعد": 0.0, "set_number": set_num, "row_number": row_num,
                        "رقم الفاتورة اليدوي": manual_no
                    }
                    self.invoices[self.invoice_counter] = inv_data
                    self.save_invoice_to_db(self.invoice_counter, inv_data)

            # خياس البوليش: حالته MEMO فيُستثنى من الخزينة وكشفها ومن صندوق
            # خياس التلميع النهائي، ويبقى محفوظاً للعرض وإعادة البناء والقالب.
            if khayas_polish_v > 0:
                self.invoice_counter += 1
                polish_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_polish_v, "البيان": "خياس بوليش",
                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_POLISH, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = polish_data
                self.save_invoice_to_db(self.invoice_counter, polish_data)

            # خياس المركب: مصدره حركات المركبين في مراحل التصنيع وهو محمّل هناك
            # أصلاً على صندوق المركبين. يُسجَّل هنا بحالة MEMO لحفظه مع الفاتورة
            # وحساب الصافي — تحميله ثانيةً يعني احتساب الفاقد مرتين.
            if abs(khayas_assembler_v) > 0.0001:
                self.invoice_counter += 1
                asm_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": khayas_assembler_v, "البيان": "خياس المركب",
                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_ASSEMBLER,
                    "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = asm_data
                self.save_invoice_to_db(self.invoice_counter, asm_data)

            # سطر الصافي: معلوماتي بحت بحالة MEMO — خارج كل حسابات الخزينة
            # والفواقد، ووظيفته الوحيدة عرض الصافي بلا إعادة حسابه من حركات متفرقة
            if abs(net_v) > 0.0001:
                self.invoice_counter += 1
                net_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    "النوع": "خياس طقوم", "الوزن": net_v, "البيان": "صافي الطقم",
                    "settled_status": MEMO_STATUS, "trees_count": KHAYAS_MARK_NET, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = net_data
                self.save_invoice_to_db(self.invoice_counter, net_data)

            # خياس الطقم: لا يدخل ضمن أوزان الطقم المباعة، بل يُرحّل لصندوق (خياس الطقوم)
            if khayas_v > 0:
                self.invoice_counter += 1
                khayas_data = {
                    "رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                    # البيان يطابق اسم الصندوق ليظهر واضحاً في كشف حساب الخزينة
                    "النوع": "خياس طقوم", "الوزن": khayas_v, "البيان": "خياس التلميع النهائي",
                    "settled_status": "ACTIVE", "trees_count": KHAYAS_MARK_FINAL, "قبل": 0.0, "بعد": 0.0,
                    "set_number": set_num, "row_number": row_num, "رقم الفاتورة اليدوي": manual_no
                }
                self.invoices[self.invoice_counter] = khayas_data
                self.save_invoice_to_db(self.invoice_counter, khayas_data)

            committed_groups.append((set_num, full_dt, name))
        return committed_groups

    def preview_selected_sale_invoice(self):
        key = self.get_selected_sale_invoice_key("معاينة")
        if not key:
            return
        recs = self.get_sale_invoice_records(key)
        if not recs:
            messagebox.showwarning("تنبيه", "لم يتم العثور على حركات هذه الفاتورة.")
            return
        manual_no, date_str, name = key
        sets = []
        for r in sorted(recs, key=lambda x: x.get("رقم الفاتورة", 0)):
            s = r.get("set_number", "") or ""
            if s not in [g[0] for g in sets]:
                sets.append((s, date_str, name))
        self.preview_invoice_groups(sets)

    def delete_selected_sale_invoice(self):
        """حذف فاتورة مبيعات مرحّلة بالكامل (كل سطورها وخياسها) مع إعادة حساب الخزينة وكل الحسابات"""
        key = self.get_selected_sale_invoice_key("حذف")
        if not key:
            return
        recs = self.get_sale_invoice_records(key)
        if not recs:
            return
        manual_no, date_str, name = key
        tot_w = round(sum(r.get("الوزن", 0.0) for r in recs), 2)
        if not messagebox.askyesno(
                "تأكيد حذف الفاتورة",
                f"سيتم حذف فاتورة المبيعات رقم ({manual_no or '-'}) للعميل ({name})\n"
                f"بتاريخ {date_str}، وعدد حركاتها {len(recs)} بإجمالي {tot_w:.2f} جم.\n\n"
                "سيتم إعادة حساب الخزينة وكل الحسابات المرتبطة تلقائياً. هل تريد المتابعة؟"):
            return

        blocked = False
        for r in list(recs):
            if not self.delete_invoice_from_db(r["رقم الفاتورة"]):
                blocked = True
        if blocked:
            return
        self.recalculate_all()
        self.refresh_sales_ops_table()
        messagebox.showinfo("تم الحذف", "تم حذف الفاتورة بالكامل وتحديث كل الأرصدة والحسابات.")

    def edit_selected_sale_invoice(self):
        key = self.get_selected_sale_invoice_key("تعديل")
        if key:
            self.open_sale_invoice_editor(key)

    def open_sale_invoice_editor(self, key):
        """نافذة تعديل فاتورة مبيعات مرحّلة: نفس خانات العمليات + جدول سطورها مع تعديل/حذف/إضافة سطر،
        وعند الحفظ تُعاد كتابة حركات الفاتورة بالكامل فتتحدث الخزينة وكل الحسابات محاسبياً."""
        if not self.check_edit_permission():
            return
        recs = self.get_sale_invoice_records(key)
        if not recs:
            messagebox.showwarning("تنبيه", "لم يتم العثور على حركات هذه الفاتورة.")
            return
        old_manual_no, old_date, old_name = key
        edit_rows = self.sale_records_to_rows(recs)

        win = ctk.CTkToplevel(self)
        win.title("تعديل فاتورة مبيعات مرحّلة")
        win.geometry("1180x720")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="✏️ تعديل فاتورة مبيعات مرحّلة", font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(12, 6))

        head = ctk.CTkFrame(win)
        head.pack(fill="x", padx=18, pady=6)

        ctk.CTkLabel(head, text="رقم الفاتورة:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=(10, 4), pady=10)
        ent_manual = ctk.CTkEntry(head, justify="center", width=110, height=34)
        ent_manual.insert(0, old_manual_no)
        ent_manual.pack(side="right", padx=4, pady=10)

        ctk.CTkLabel(head, text="التاريخ:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=(10, 4), pady=10)
        ent_date = ctk.CTkEntry(head, justify="center", width=120, height=34)
        ent_date.insert(0, old_date[:10])
        ent_date.pack(side="right", padx=4, pady=10)

        ctk.CTkLabel(head, text="الاسم:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=(10, 4), pady=10)
        cmb_name = ctk.CTkComboBox(head, values=self.get_supplier_name_values_no_mustarja(), justify="right", width=190, height=34)
        cmb_name.set(old_name)
        cmb_name.pack(side="right", padx=4, pady=10)

        fields_row = ctk.CTkFrame(win, corner_radius=10)
        fields_row.pack(fill="x", padx=18, pady=6)

        entries = {}

        def add_field(label_text, key_name):
            col = ctk.CTkFrame(fields_row, fg_color="transparent")
            col.pack(side="right", padx=10, pady=10)
            ctk.CTkLabel(col, text=label_text, font=("Cairo", 13, "bold")).pack(pady=(2, 3))
            ent = ctk.CTkEntry(col, justify="center", font=("Cairo", 14), width=95, height=32)
            ent.pack()
            entries[key_name] = ent
            return ent

        add_field("رقم الصف", "row_number")
        add_field("رقم التشغيل", "set_number")
        add_field("الذهب", "ذهب")
        add_field("الفصوص", "فصوص")
        add_field("الأحجار", "أحجار")
        add_field("الأحجار بعد الخصم", "أحجار بعد الخصم")
        add_field("خياس التلميع النهائي", "خياس")
        add_field("خياس البوليش", "خياس البوليش")
        add_field("خياس المركب", "خياس المركب")
        add_field("الماس", "الماس")

        lbl_state = ctk.CTkLabel(win, text="", font=("Cairo", 13, "bold"), text_color="#f1c40f")
        lbl_state.pack(pady=(0, 2))

        btns_row = ctk.CTkFrame(win, fg_color="transparent")
        btns_row.pack(fill="x", padx=18, pady=(2, 4))

        table_frame = ttk.Frame(win)
        table_frame.pack(fill="both", expand=True, padx=18, pady=(4, 4))

        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع النهائي", "خياس البوليش", "الصافي")
        rows_tree = self.create_standard_treeview(table_frame, cols, height=9)
        rows_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols:
            rows_tree.column(c, width=130, anchor="center")

        selected_idx = {"i": None}

        def read_fields():
            vals = {"set_number": entries["set_number"].get().strip(),
                    "row_number": entries["row_number"].get().strip()}
            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس",
                      "خياس البوليش", "خياس المركب"):
                txt = entries[k].get().strip()
                try:
                    v = round(float(txt), 2) if txt else 0.0
                except ValueError:
                    messagebox.showerror("خطأ", f"القيمة المدخلة في خانة ({k}) ليست رقماً صحيحاً.", parent=win)
                    return None
                if v < 0:
                    messagebox.showerror("خطأ", "لا يمكن إدخال أوزان بالسالب.", parent=win)
                    return None
                vals[k] = v
            if (vals["ذهب"] <= 0 and vals["فصوص"] <= 0 and vals["أحجار بعد الخصم"] <= 0
                    and vals["الماس"] <= 0 and vals["خياس"] <= 0 and vals["خياس البوليش"] <= 0):
                messagebox.showwarning("تنبيه", "لا بد من قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).", parent=win)
                return None
            return vals

        def clear_fields():
            for ent in entries.values():
                ent.delete(0, 'end')
            selected_idx["i"] = None
            lbl_state.configure(text="")

        def refresh_rows_tree():
            for item in rows_tree.get_children():
                rows_tree.delete(item)
            tot = {k: 0.0 for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                                    "خياس", "خياس البوليش")}
            tot_net = 0.0
            for r in edit_rows:
                for k in tot:
                    tot[k] = round(tot[k] + r.get(k, 0.0), 2)
                net_r = sale_net_weight(r)
                tot_net = round(tot_net + net_r, 2)
                rows_tree.insert("", "end", values=(
                    r.get("row_number", "") or "-", r.get("set_number", "") or "-",
                    f"{r.get('ذهب', 0):.2f}" if r.get("ذهب") else "-",
                    f"{r.get('فصوص', 0):.2f}" if r.get("فصوص") else "-",
                    f"{r.get('أحجار', 0):.2f}" if r.get("أحجار") else "-",
                    f"{r.get('أحجار بعد الخصم', 0):.2f}" if r.get("أحجار بعد الخصم") else "-",
                    f"{r.get('الماس', 0):.2f}" if r.get("الماس") else "-",
                    f"{r.get('خياس', 0):.2f}" if r.get("خياس") else "-",
                    f"{r.get('خياس البوليش', 0):.2f}" if r.get("خياس البوليش") else "-",
                    f"{net_r:.2f}",
                ))
            if edit_rows:
                rows_tree.insert("", "end", values=(
                    "الإجمالي", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",
                    f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}",
                    f"{tot['خياس البوليش']:.2f}", f"{tot_net:.2f}"), tags=("total_tag",))

        def get_sel_index():
            sel = rows_tree.selection()
            if not sel:
                messagebox.showwarning("تنبيه", "الرجاء تحديد السطر من الجدول أولاً.", parent=win)
                return None
            idx = rows_tree.get_children().index(sel[0])
            if not (0 <= idx < len(edit_rows)):
                messagebox.showinfo("تنبيه", "هذا السطر إجمالي وليس سطر فاتورة.", parent=win)
                return None
            return idx

        def load_row_to_fields():
            idx = get_sel_index()
            if idx is None:
                return
            r = edit_rows[idx]
            for k, ent in entries.items():
                ent.delete(0, 'end')
                val = r.get(k, "")
                ent.insert(0, str(val) if k in ("set_number", "row_number") else (f"{val:g}" if val else ""))
            selected_idx["i"] = idx
            lbl_state.configure(text=f"✏️ يتم الآن تعديل السطر رقم ({idx + 1}) — اضغط (حفظ السطر) بعد التعديل")

        def save_row():
            vals = read_fields()
            if vals is None:
                return
            if self.check_sale_row_duplicate(edit_rows, vals["row_number"], vals["set_number"],
                                             skip_index=selected_idx["i"], parent=win):
                return
            if selected_idx["i"] is None:
                edit_rows.append(vals)
            else:
                edit_rows[selected_idx["i"]] = vals
            clear_fields()
            refresh_rows_tree()

        def delete_row():
            idx = get_sel_index()
            if idx is None:
                return
            if not messagebox.askyesno("تأكيد", "هل تريد حذف هذا السطر من الفاتورة؟", parent=win):
                return
            del edit_rows[idx]
            clear_fields()
            refresh_rows_tree()

        ctk.CTkButton(btns_row, text="💾 حفظ السطر (إضافة/تعديل)", font=("Cairo", 13, "bold"), width=205, height=34,
                      fg_color="#1e8449", hover_color="#145a32", command=save_row).pack(side="right", padx=5)
        ctk.CTkButton(btns_row, text="✏️ تحميل السطر المحدد للتعديل", font=("Cairo", 13, "bold"), width=215, height=34,
                      fg_color="#b8860b", hover_color="#daa520", command=load_row_to_fields).pack(side="right", padx=5)
        ctk.CTkButton(btns_row, text="🗑️ حذف السطر المحدد", font=("Cairo", 13, "bold"), width=175, height=34,
                      fg_color="#8b0000", hover_color="#a52a2a", command=delete_row).pack(side="right", padx=5)
        ctk.CTkButton(btns_row, text="🧹 تفريغ الخانات", font=("Cairo", 13, "bold"), width=140, height=34,
                      fg_color="#555555", hover_color="#333333", command=clear_fields).pack(side="right", padx=5)

        rows_tree.bind("<Double-1>", lambda e: load_row_to_fields())
        refresh_rows_tree()

        def save_invoice_changes():
            new_manual = ent_manual.get().strip()
            new_date = ent_date.get().strip()
            new_name = cmb_name.get().strip()
            if not new_manual:
                messagebox.showwarning("تنبيه", "رقم الفاتورة مطلوب.", parent=win)
                return
            if len(new_date) < 10 or new_date[4] != '-':
                messagebox.showerror("خطأ", "الرجاء إدخال التاريخ بالصيغة الصحيحة YYYY-MM-DD.", parent=win)
                return
            if not new_name or new_name not in self.get_supplier_name_values_no_mustarja():
                messagebox.showwarning("تنبيه", "الرجاء اختيار اسم من الموردين المسجلين.", parent=win)
                return
            if not edit_rows:
                messagebox.showwarning("تنبيه", "لا توجد سطور في الفاتورة.\nلحذف الفاتورة بالكامل استخدم زر (حذف الفاتورة) من جدول العمليات.", parent=win)
                return
            if not messagebox.askyesno(
                    "تأكيد الحفظ",
                    f"سيتم إعادة تسجيل الفاتورة بـ {len(edit_rows)} سطر/أسطر،\n"
                    "وسيتم تحديث الخزينة وصندوق خياس الطقوم وكل الحسابات المرتبطة تلقائياً.\n\nهل تريد المتابعة؟", parent=win):
                return

            # وقت الفاتورة يبقى كما هو ما دام اليوم لم يتغيّر، حتى لا يتغيّر ترتيبها المحاسبي بلا داعٍ
            old_time = old_date[11:] if len(old_date) > 11 else datetime.datetime.now().strftime('%H:%M:%S')
            new_full_dt = f"{new_date} {old_time}" if new_date == old_date[:10] else f"{new_date} {datetime.datetime.now().strftime('%H:%M:%S')}"

            # حذف الحركات القديمة ثم إعادة كتابتها بالكامل — يضمن تطابق الحسابات مع الفاتورة بعد التعديل
            for r in list(self.get_sale_invoice_records(key)):
                if not self.delete_invoice_from_db(r["رقم الفاتورة"]):
                    messagebox.showerror("تعذّر الحفظ", "تم منع حذف إحدى الحركات القديمة، وأُلغي التعديل حفاظاً على سلامة الحسابات.", parent=win)
                    self.recalculate_all()
                    return

            self.post_sale_rows(edit_rows, new_name, new_full_dt, new_manual)

            self.register_operation_period(new_date)
            self.recalculate_all()
            self.refresh_sales_ops_table()
            win.destroy()
            messagebox.showinfo("تم", "تم حفظ تعديلات الفاتورة وتحديث الخزينة وكل الحسابات المرتبطة.")

        btn_save_inv = ctk.CTkButton(win, text="✅ حفظ تعديلات الفاتورة", font=("Cairo", 16, "bold"), height=44,
                                     width=280, fg_color="#144d75", hover_color="#0d3350", command=save_invoice_changes)
        btn_save_inv.pack(pady=10)
        self.apply_edit_lock_to_button(btn_save_inv, win)

    def on_discount_pct_change(self):
        """عند تغيير نسبة الخصم المختارة: يُعاد حساب الأحجار بعد الخصم فوراً، وتُحفظ النسبة كآخر نسبة مستخدمة"""
        pct_text = self.sale_discount_pct.get().strip().replace("%", "")
        self.set_last_discount_percentage(pct_text)
        if hasattr(self, '_auto_compute_stones_discount'):
            self._auto_compute_stones_discount()

    def open_add_discount_pct_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("إضافة نسبة خصم جديدة")
        win.geometry("360x200")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="➕ إضافة نسبة خصم جديدة", font=("Cairo", 15, "bold"), text_color="#d4af37").pack(pady=(20, 10))
        ctk.CTkLabel(win, text="النسبة (%):", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(pady=(5, 3))
        entry = ctk.CTkEntry(win, font=("Cairo", 14), justify="center", width=140, height=38)
        entry.pack(pady=5)
        entry.focus_set()

        lbl_status = ctk.CTkLabel(win, text="", font=("Cairo", 12, "bold"), text_color="#e74c3c")
        lbl_status.pack(pady=3)

        def do_add():
            val = entry.get().strip()
            try:
                pct_num = float(val)
                if pct_num <= 0 or pct_num > 100:
                    raise ValueError
            except ValueError:
                lbl_status.configure(text="الرجاء إدخال نسبة صحيحة بين 0 و100.")
                return
            pct_str = str(pct_num) if pct_num % 1 else str(int(pct_num))
            self.add_discount_percentage(pct_str)
            self.sale_discount_pct.configure(values=[f"{p}%" for p in self.get_discount_percentages()])
            self.sale_discount_pct.set(f"{pct_str}%")
            self.on_discount_pct_change()
            win.destroy()

        entry.bind("<Return>", lambda e: do_add())
        ctk.CTkButton(win, text="✅ إضافة", font=("Cairo", 14, "bold"), fg_color="#1e8449", hover_color="#145a32", width=140, height=38, command=do_add).pack(pady=15)

    def get_assembler_khayas_for_set(self, set_number, month=None):
        """قيمة عمود (مسموح/٨) لرقم تشغيل معيّن، من قسم **المركبين** حصراً.

        تُحاكي هذه الدالة كشف مراحل التصنيع خطوةً بخطوة حتى يتطابق الرقم معه
        حرفياً:
          ١) تُجمَّع حركات كل عامل مركّب في صفوف حسب (رقم الصف) — نفس تجميع الكشف.
          ٢) رقم تشغيل الصف = **أول رقم غير فارغ** يظهر في حركاته، وهو بالضبط
             ما يعرضه الكشف في عمود رقم التشغيل.
          ٣) الصفوف التي رقم تشغيلها = المطلوب فقط تدخل الحساب.
          ٤) مسموح/٨ = مجموع (قبض ذهب) لتلك الصفوف × ٨ بالألف.

        سبب الأرقام الخاطئة سابقاً: كان الحساب يشمل قسم المصنعين أيضاً، ويضم
        كل حركات الصف حتى لو حملت أرقام تشغيل أخرى. الآن التطابق مع الكشف تام.

        البحث يشمل كل الفترات (رقم التشغيل فريد عبر الزمن)، ما لم يُمرَّر شهر.
        """
        set_number = (set_number or "").strip()
        if not set_number:
            return 0.0

        assemblers = set(self.categories.get("المركبين", []))
        if not assemblers:
            return 0.0

        # (١) تجميع حركات المركبين في صفوف: (العامل، رقم الصف)
        groups = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue
            name = inv.get("الاسم")
            if name not in assemblers:
                continue
            if month and not self.inv_in_period(inv, month):
                continue

            key = (name, (inv.get("row_number", "") or "").strip())
            g = groups.setdefault(key, {"set_number": "", "قبض": 0.0})

            # (٢) أول رقم تشغيل غير فارغ هو رقم الصف — كما في الكشف تماماً
            if not g["set_number"] and (inv.get("set_number", "") or "").strip():
                g["set_number"] = (inv.get("set_number", "") or "").strip()

            if inv.get("النوع") == "قبض ذهب":
                g["قبض"] += inv.get("الوزن", 0.0)

        # (٣) و(٤) الصفوف المطابقة فقط، ومسموح/٨ عليها
        total = sum(g["قبض"] for g in groups.values() if g["set_number"] == set_number)
        return round(total * ALLOWANCE_8, 2)

    def autofill_assembler_khayas(self, event=None):
        """يملأ خانة (خياس المركب) تلقائياً حسب رقم التشغيل المكتوب.

        الأخطاء تُسجَّل ولا تُكتم: كتمها سابقاً جعل فشل الجلب يبدو كأن الرقم
        غير موجود، فيصعب تشخيص السبب.
        """
        if not hasattr(self, "sale_khayas_assembler"):
            return
        try:
            value = self.get_assembler_khayas_for_set(self.sale_set_number.get())
            self.sale_khayas_assembler.delete(0, 'end')
            if abs(value) > 0.0001:
                self.sale_khayas_assembler.insert(0, f"{value:g}")
            if hasattr(self, "_recompute_sale_totals"):
                self._recompute_sale_totals()
        except Exception as e:
            log_cloud_error("تعذّر جلب خياس المركب تلقائياً", e)

    def bind_vertical_navigation(self, fields, on_last=None, window=None):
        """تنقّل بين خانات نافذة التعديل بـ Enter و↑ ↓.

        الربط يتم على **النافذة نفسها** لا على كل خانة:
        CTkEntry غلافٌ حول خانة داخلية، والربط على الغلاف قد لا يصل لها في
        بعض إصدارات المكتبة — فلا يستجيب المفتاح. الربط على النافذة يلتقط
        المفتاح دائماً، ثم نحدّد الخانة الحالية من موضع التركيز.

        on_last: يُستدعى عند Enter في آخر خانة (الحفظ عادةً).
        """
        widgets = [f for f in fields if f is not None]
        if not widgets:
            return

        win = window
        if win is None:
            try:
                win = widgets[0].winfo_toplevel()
            except Exception:
                return

        def inner(w):
            """الخانة الداخلية الحقيقية لـ CTkEntry (أو الأداة نفسها)"""
            return getattr(w, "_entry", w)

        def current_index():
            """موضع الخانة التي فيها التركيز الآن"""
            try:
                focused = win.focus_get()
            except Exception:
                return None
            for i, w in enumerate(widgets):
                if focused is w or focused is inner(w):
                    return i
            return None

        def go(step, wrap_to_save=False):
            i = current_index()
            if i is None:
                return None          # التركيز خارج الخانات: لا نتدخّل
            j = i + step
            if j >= len(widgets):
                if wrap_to_save and on_last is not None:
                    on_last()
                return "break"
            if j < 0:
                return "break"
            target = widgets[j]
            try:
                target.focus_set()
                inner(target).select_range(0, "end")
            except Exception:
                pass
            return "break"

        win.bind("<Down>", lambda e: go(1), add="+")
        win.bind("<Up>", lambda e: go(-1), add="+")
        win.bind("<Return>", lambda e: go(1, wrap_to_save=True), add="+")
        win.bind("<KP_Enter>", lambda e: go(1, wrap_to_save=True), add="+")


    def bind_arrow_navigation(self, fields):
        """تنقّل بالأسهم يمين/يسار بين خانات الإدخال المرصوفة من اليمين لليسار.

        لا يتدخّل عندما يكون المؤشر داخل النص: السهم الأيسر ينتقل للخانة
        التالية فقط إذا كان المؤشر في نهاية النص، والأيمن فقط إذا كان في
        بدايته — حتى يبقى تحريك المؤشر داخل الرقم ممكناً كالمعتاد.
        """
        widgets = [f for f in fields if f is not None]

        def go(idx, event):
            if 0 <= idx < len(widgets):
                widgets[idx].focus_set()
                return "break"
            return None

        # الأسهم تنتقل بين الخانات دائماً (لا تحرّك المؤشر داخل الرقم).
        # الشرط السابق كان يمنع الانتقال يميناً كلما كان المؤشر بعد أول حرف،
        # فبدا وكأن التنقل يعمل في اتجاه واحد فقط.
        # لتحريك المؤشر داخل النص: Home و End.
        for i, field in enumerate(widgets):
            def on_left(e, i=i):
                return go(i + 1, e)

            def on_right(e, i=i):
                return go(i - 1, e)

            try:
                field.bind("<Left>", on_left)
                field.bind("<Right>", on_right)
            except Exception:
                pass

    def stage_sale_row(self):
        """إضافة سطر إلى الفاتورة الحالية (تجهيز فقط، بدون ترحيل فعلي بعد)"""
        name = self.sale_name.get().strip()
        if not name or name not in self.get_supplier_name_values_no_mustarja():
            messagebox.showwarning("تنبيه", "لا يمكن إضافة سطر إلا بعد اختيار اسم من الموردين المسجلين.")
            return

        def safe_val(entry):
            try:
                return round(float(entry.get().strip()), 2) if entry.get().strip() else 0.0
            except ValueError:
                return 0.0

        gold_v = safe_val(self.sale_gold)
        gems_v = safe_val(self.sale_gems)
        stones_v = safe_val(self.sale_stones)
        stones_discount_v = safe_val(self.sale_stones_discount)
        diamond_v = safe_val(self.sale_diamond)
        khayas_v = safe_val(self.sale_khayas)
        khayas_polish_v = safe_val(self.sale_khayas_polish)
        khayas_assembler_v = safe_val(self.sale_khayas_assembler)
        set_num = self.sale_set_number.get().strip()
        # الترقيم التلقائي: أكبر رقم موجود + ١، فلا يتكرر رقم حتى لو حُذف
        # سطر من وسط الفاتورة (الترقيم يُعاد ضبطه بعد الحذف على كل حال)
        row_num = str(self.next_sale_row_number())

        if (gold_v <= 0 and gems_v <= 0 and stones_v <= 0 and diamond_v <= 0
                and khayas_v <= 0 and khayas_polish_v <= 0 and khayas_assembler_v == 0):
            messagebox.showwarning("تنبيه", "الرجاء إدخال قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).")
            return
        if khayas_v < 0 or khayas_polish_v < 0:
            messagebox.showwarning("تنبيه", "لا يمكن إدخال خياس بالسالب.")
            return
        if self.check_sale_row_duplicate(self.pending_sale_rows, row_num, set_num):
            return

        self.pending_sale_rows.append({
            "row_number": row_num, "set_number": set_num, "ذهب": gold_v, "فصوص": gems_v, "أحجار": stones_v,
            "أحجار بعد الخصم": stones_discount_v, "الماس": diamond_v, "خياس": khayas_v,
            "خياس البوليش": khayas_polish_v, "خياس المركب": khayas_assembler_v
        })

        self.sale_row_number.delete(0, 'end')
        self.sale_khayas.delete(0, 'end')
        self.sale_khayas_polish.delete(0, 'end')
        self.sale_khayas_assembler.delete(0, 'end')
        self.sale_set_number.delete(0, 'end')
        self.sale_gold.delete(0, 'end')
        self.sale_gems.delete(0, 'end')
        self.sale_stones.delete(0, 'end')
        self.sale_stones_discount.delete(0, 'end')
        self.sale_diamond.delete(0, 'end')
        self.sale_weight_standing.delete(0, 'end')
        self.sale_weight_bound.delete(0, 'end')
        self.sale_set_number.focus_set()

        self.refresh_pending_sales_table()

    def toggle_pending_sales_order(self):
        """يعكس ترتيب عرض سطور الفاتورة (تصاعدي/تنازلي).

        الترتيب عرضٌ فقط ولا يمسّ ترتيب السطور المحفوظ ولا أرقامها — الغرض
        رؤية آخر سطر سُجِّل بلا نزول إلى آخر الجدول.
        """
        self.pending_sales_desc = not getattr(self, "pending_sales_desc", False)
        if hasattr(self, "btn_sales_sort"):
            self.btn_sales_sort.configure(
                text="⬆️ تصاعدي" if self.pending_sales_desc else "⬇️ تنازلي")
        self.refresh_pending_sales_table()

    def refresh_pending_sales_table(self):
        if not hasattr(self, 'pending_sales_table_frame') or not self.pending_sales_table_frame:
            return
        # أسماء مختصرة واضحة: العمود الأول (خياس) هو التلميع النهائي،
        # ثم (بوليش) ثم (مركب) — بدل تكرار كلمة خياس في ثلاثة عناوين
        cols = ("رقم الصف", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم",
                "الماس", "خياس التلميع", "بوليش", "مركب", "الصافي",
                "الوزن القائم", "الوزن المقيد")
        self.pending_sales_tree, _t, reused = self.reuse_or_create_tree(
            self.pending_sales_table_frame, cols, height=16)
        self.pending_sales_tree.tag_configure("total_tag", foreground="#e67e22", font=("Cairo", 13, "bold"))
        for c in cols:
            self.pending_sales_tree.column(c, width=70, anchor="center", stretch=False)

        tot = dict.fromkeys(["ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس",
                             "خياس", "خياس البوليش", "خياس المركب",
                             "الصافي", "القائم", "المقيد"], 0.0)

        def num(row, key):
            try:
                return float(row.get(key, 0.0) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        # نسخة معروضة فقط: الترتيب لا يمسّ self.pending_sale_rows المحفوظة
        display_rows = list(self.pending_sale_rows)
        if getattr(self, "pending_sales_desc", False):
            display_rows.reverse()

        for row in display_rows:
            net = sale_net_weight(row)
            # الوزن القائم يحسب الأحجار الخام، والمقيد يحسبها بعد الخصم
            standing = round(num(row, "ذهب") + num(row, "فصوص") + num(row, "أحجار") + num(row, "الماس"), 2)
            bound = round(num(row, "ذهب") + num(row, "فصوص") + num(row, "أحجار بعد الخصم") + num(row, "الماس"), 2)

            for k in ("ذهب", "فصوص", "أحجار", "أحجار بعد الخصم", "الماس", "خياس",
                      "خياس البوليش", "خياس المركب"):
                tot[k] = round(tot[k] + num(row, k), 2)
            tot["الصافي"] = round(tot["الصافي"] + net, 2)
            tot["القائم"] = round(tot["القائم"] + standing, 2)
            tot["المقيد"] = round(tot["المقيد"] + bound, 2)

            self.pending_sales_tree.insert("", "end", values=(
                row.get("row_number", "") or "-",
                row.get("set_number", "") or "-",
                f"{num(row, 'ذهب'):.2f}" if num(row, "ذهب") else "-",
                f"{num(row, 'فصوص'):.2f}" if num(row, "فصوص") else "-",
                f"{num(row, 'أحجار'):.2f}" if num(row, "أحجار") else "-",
                f"{num(row, 'أحجار بعد الخصم'):.2f}" if num(row, "أحجار بعد الخصم") else "-",
                f"{num(row, 'الماس'):.2f}" if num(row, "الماس") else "-",
                f"{num(row, 'خياس'):.2f}" if num(row, "خياس") else "-",
                f"{num(row, 'خياس البوليش'):.2f}" if num(row, "خياس البوليش") else "-",
                f"{num(row, 'خياس المركب'):.2f}" if num(row, "خياس المركب") else "-",
                f"{net:.2f}",
                f"{standing:.2f}" if standing else "-",
                f"{bound:.2f}" if bound else "-",
            ))

        self.apply_column_labels(self.pending_sales_tree, "pending_sales")
        self.fit_columns_to_content(self.pending_sales_tree, "pending_sales",
                                     min_width=44, max_width=150)
        self.enable_column_rename(self.pending_sales_tree, "pending_sales",
                                  on_renamed=self.refresh_pending_sales_table)

        if self.pending_sale_rows:
            self.pending_sales_tree.insert("", "end", values=(
                "إجمالي الفاتورة", "-", f"{tot['ذهب']:.2f}", f"{tot['فصوص']:.2f}", f"{tot['أحجار']:.2f}",
                f"{tot['أحجار بعد الخصم']:.2f}", f"{tot['الماس']:.2f}", f"{tot['خياس']:.2f}",
                f"{tot['خياس البوليش']:.2f}", f"{tot['خياس المركب']:.2f}", f"{tot['الصافي']:.2f}",
                f"{tot['القائم']:.2f}", f"{tot['المقيد']:.2f}"), tags=("total_tag",))

    def delete_pending_sale_row(self):
        if not (hasattr(self, 'pending_sales_tree') and self.pending_sales_tree):
            return
        sel = self.pending_sales_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد السطر المعلّق المراد حذفه أولاً.")
            return
        idx = self.pending_sales_tree.get_children().index(sel[0])
        if 0 <= idx < len(self.pending_sale_rows):
            del self.pending_sale_rows[idx]
        # إعادة الترقيم بعد الحذف: تبقى الأرقام ١..ن بلا فجوات
        self.renumber_pending_sale_rows()
        self.refresh_pending_sales_table()

    def edit_pending_sale_row(self):
        """تعديل سطر معلّق في الفاتورة الحالية قبل ترحيلها"""
        if not (hasattr(self, 'pending_sales_tree') and self.pending_sales_tree):
            return
        sel = self.pending_sales_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد السطر المعلّق المراد تعديله أولاً.")
            return
        idx = self.pending_sales_tree.get_children().index(sel[0])
        if not (0 <= idx < len(self.pending_sale_rows)):
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للتعديل (سطر إجماليات).")
            return
        row = self.pending_sale_rows[idx]

        win = ctk.CTkToplevel(self)
        win.title("تعديل السطر المعلّق")
        win.geometry("470x620")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="✏️ تعديل سطر الفاتورة الحالية", font=("Cairo", 17, "bold"), text_color="#d4af37").pack(pady=12)

        frm = ctk.CTkFrame(win)
        frm.pack(fill="x", padx=20, pady=8)

        fields = [("رقم الصف", "row_number"), ("رقم التشغيل", "set_number"), ("الذهب", "ذهب"), ("الفصوص", "فصوص"),
                  ("الأحجار", "أحجار"), ("الأحجار بعد الخصم", "أحجار بعد الخصم"), ("الماس", "الماس"), ("خياس", "خياس")]
        text_keys = ("set_number", "row_number")
        entries = {}
        for i, (lbl, key) in enumerate(fields):
            ctk.CTkLabel(frm, text=f"{lbl}:", font=("Cairo", 14, "bold")).grid(row=i, column=1, padx=10, pady=7, sticky="e")
            ent = ctk.CTkEntry(frm, justify="center", width=150)
            val = row.get(key, "")
            if key not in text_keys:
                ent.insert(0, f"{float(val or 0):g}")
            else:
                ent.insert(0, str(val or ""))
            ent.grid(row=i, column=0, padx=10, pady=7)
            entries[key] = ent

        def save_row():
            new_row = {"set_number": entries["set_number"].get().strip(),
                       "row_number": entries["row_number"].get().strip()}
            for _, key in [f for f in fields if f[1] not in text_keys]:
                try:
                    v = round(float(entries[key].get().strip() or 0), 2)
                except ValueError:
                    messagebox.showerror("خطأ", "الرجاء إدخال أرقام صحيحة في خانات الأوزان.", parent=win)
                    return
                if v < 0:
                    messagebox.showerror("خطأ", "لا يمكن إدخال أوزان بالسالب.", parent=win)
                    return
                new_row[key] = v
            if (new_row["ذهب"] <= 0 and new_row["فصوص"] <= 0 and new_row["أحجار"] <= 0
                    and new_row["الماس"] <= 0 and new_row.get("خياس", 0.0) <= 0):
                messagebox.showwarning("تنبيه", "لا بد من قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).", parent=win)
                return
            if self.check_sale_row_duplicate(self.pending_sale_rows, new_row["row_number"],
                                             new_row["set_number"], skip_index=idx, parent=win):
                return
            self.pending_sale_rows[idx] = new_row
            self.refresh_pending_sales_table()
            win.destroy()

        ctk.CTkButton(win, text="حفظ التعديلات 💾", font=("Cairo", 16, "bold"), fg_color="#2ecc71",
                      hover_color="#27ae60", height=42, command=save_row).pack(pady=18)

    def commit_sale_invoice(self):
        """اعتماد وترحيل كل السطور المعلّقة، كل سطر يصبح فاتورة طباعة مستقلة، ثم فتح معاينة الفواتير دفعة واحدة"""
        name = self.sale_name.get().strip()
        if not name or name not in self.get_supplier_name_values_no_mustarja():
            messagebox.showwarning("تنبيه", "الرجاء اختيار اسم من الموردين المسجلين قبل الترحيل.")
            return
        if not self.pending_sale_rows:
            messagebox.showwarning("تنبيه", "لا توجد سطور معلّقة لترحيلها. الرجاء إضافة سطر واحد على الأقل أولاً.")
            return

        manual_no = self.sale_invoice_num.get().strip()
        if not manual_no:
            messagebox.showwarning("رقم الفاتورة مطلوب", "لازم تسجل رقم الفاتورة يدوياً قبل اعتماد الفاتورة.")
            self.sale_invoice_num.focus_set()
            return
        sale_types_chk = ("مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس")
        if any(inv.get("رقم الفاتورة اليدوي", "") == manual_no and inv.get("settled_status") == "ACTIVE"
               and inv.get("النوع") in sale_types_chk for inv in self.invoices.values()):
            if not messagebox.askyesno("رقم فاتورة مكرر", f"رقم الفاتورة ({manual_no}) مسجل من قبل بفاتورة مبيعات أخرى.\nهل تريد المتابعة برغم ذلك؟"):
                return

        if not messagebox.askyesno("تأكيد الاعتماد", f"هل أنت متأكد من اعتماد وترحيل هذه الفاتورة لـ ({name})؟\nسيتم تسجيل {len(self.pending_sale_rows)} سطر/أسطر ولا يمكن التراجع إلا بالتعديل أو الحذف لاحقاً."):
            return

        date_val = self.sale_date.get().strip() or self.get_smart_default_date()
        full_dt = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"

        # الترحيل يمر عبر الدالة الموحّدة نفسها المستخدمة في تعديل الفاتورة، لضمان تطابق المعالجة المحاسبية
        committed_groups = self.post_sale_rows(self.pending_sale_rows, name, full_dt, manual_no)

        self.pending_sale_rows = []
        self.sale_name.set("المصنع")
        self.sale_invoice_num.delete(0, 'end')

        self.register_operation_period(date_val)
        self.recalculate_all()

        self.lbl_sales_status.configure(text=f"✅ تم اعتماد وترحيل الفاتورة لـ ({name})")
        self.after(2500, lambda: self.lbl_sales_status.configure(text=""))
        self.refresh_pending_sales_table()
        self.refresh_sales_table()
        self.refresh_sales_ops_table()

        # نسأل المستخدم قبل فتح معاينة الطباعة (بدل فتحها تلقائياً بدون تأكيد)
        if messagebox.askyesno("معاينة الطباعة", "تم ترحيل الفاتورة بنجاح.\nهل تريد معاينة الطباعة؟"):
            self.preview_invoice_groups(committed_groups)

    def refresh_sales_table(self):
        if hasattr(self, 'lbl_sales_balance'):
            bal_gold = self.get_material_balance("ذهب")
            bal_gems_stones = self.get_material_balance("فصوص وأحجار")
            bal_diamond = self.get_material_balance("الماس")
            self.lbl_sales_balance.configure(text=f"رصيد الذهب: {bal_gold:.2f} جم   |   رصيد فصوص وأحجار: {bal_gems_stones:.2f}   |   رصيد الماس: {bal_diamond:.2f}")

    # =========================================================================
    # --- محرك طباعة الفواتير: تجميع بيانات السطر + رسم القالب + معاينة/طباعة ---
    # =========================================================================
    SALE_READ_STATUSES_FOR_PRINT = SALE_READ_STATUSES

    def get_invoice_group_data(self, set_number, date_str, name):
        """يجمع كل فواتير سطر مبيعات واحد (بنفس رقم التشغيل والتاريخ والاسم) في قاموس بيانات فاتورة مستقلة"""
        data = {
            "set_number": set_number, "date": date_str, "name": name,
            "gold": 0.0, "gems": 0.0, "stones": 0.0, "stones_discount": "",
            "diamond": 0.0, "khayas": 0.0, "khayas_polish": 0.0, "khayas_assembler": 0.0, "net": 0.0,
            "row_number": "", "invoice_no": None, "voucher": ""
        }
        for inv in self.invoices.values():
            if inv.get("set_number") != set_number: continue
            if inv.get("التاريخ") != date_str: continue
            if inv.get("الاسم") != name: continue
            t = inv.get("النوع")
            if t in ("مبيعات ذهب", "مبيعات ذهب مع الماس"):
                data["gold"] += inv["الوزن"]
                data["voucher"] = data["voucher"] or inv.get("البيان", "")
            elif t == "مبيعات فصوص وأحجار":
                if inv.get("trees_count") == 3.0:
                    data["stones"] += inv.get("قبل", 0.0)  # الوزن الخام قبل الخصم (للعرض على الفاتورة)
                    data["stones_discount"] = f"{inv['الوزن']:.2f}"  # القيمة بعد الخصم (٣٠٪) وهي المعتمدة محاسبياً
                    data["voucher"] = data["voucher"] or inv.get("البيان", "")
                else:
                    data["gems"] += inv["الوزن"]
                    data["voucher"] = data["voucher"] or inv.get("البيان", "")
            elif t == "مبيعات الماس":
                data["diamond"] += inv["الوزن"]
                data["voucher"] = data["voucher"] or inv.get("البيان", "")
            elif t == "خياس طقوم":
                mark = inv.get("trees_count", 0.0) or 0.0
                if mark == KHAYAS_MARK_POLISH:
                    data["khayas_polish"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_ASSEMBLER:
                    data["khayas_assembler"] += inv["الوزن"]
                elif mark == KHAYAS_MARK_NET:
                    data["net"] += inv["الوزن"]
                else:
                    data["khayas"] += inv["الوزن"]
            if not data["row_number"] and inv.get("row_number"):
                data["row_number"] = inv.get("row_number")
            if data["invoice_no"] is None:
                data["invoice_no"] = inv.get("رقم الفاتورة")
        return data

    def get_sale_batch_set_numbers(self, date_str, name):
        """يرجع كل أرقام التشغيل التي رُحّلت ضمن نفس دفعة المبيعات (نفس التاريخ والاسم)، بترتيب إدخالها الأصلي"""
        sale_types = ["مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس"]
        seen = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            if inv.get("النوع") not in sale_types: continue
            if inv.get("التاريخ") != date_str or inv.get("الاسم") != name: continue
            sn = inv.get("set_number", "")
            inv_no = inv.get("رقم الفاتورة", 0)
            if sn not in seen or inv_no < seen[sn]:
                seen[sn] = inv_no
        return [sn for sn, _ in sorted(seen.items(), key=lambda kv: kv[1])]

    def draw_invoice_page(self, c, data):
        """يرسم صفحة فاتورة واحدة مطابقة لقالب المصنع (شعار + بيانات العميل + جداول الأوزان)"""
        PW, PH = A4
        M = 8 * mm

        gold = data.get("gold", 0.0)
        gems = data.get("gems", 0.0)
        stones = data.get("stones", 0.0)
        diamond = data.get("diamond", 0.0)
        weight_with_gems = round(gold + gems, 2)
        weight_standing = round(gold + gems + stones + diamond, 2)
        try:
            stones_discount_num = float(data.get("stones_discount") or 0)
        except ValueError:
            stones_discount_num = 0.0
        weight_bound = round(gold + gems + stones_discount_num + diamond, 2)

        def txt(x, y, s, size=9, bold=False, align="right"):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            s = ar(s)
            if align == "right":
                c.drawRightString(x, y, s)
            elif align == "left":
                c.drawString(x, y, s)
            else:
                c.drawCentredString(x, y, s)

        def rect(x, y, w, h, fill=None, stroke=1):
            if fill:
                c.setFillColor(fill)
                c.rect(x, y - h, w, h, fill=1, stroke=stroke)
                c.setFillColorRGB(0, 0, 0)
            else:
                c.rect(x, y - h, w, h, fill=0, stroke=stroke)

        # ====== الرأس: الاسم الإنجليزي (يسار) - الشعار (وسط) - الاسم العربي (يمين) ======
        y = PH - M
        txt(M, y - 6, "Jadeite Factory", size=13, bold=True, align="left")
        txt(M, y - 14, "Saudi Arabia, Riyadh", size=9, align="left")
        txt(M, y - 21, "Industrial City", size=9, align="left")
        txt(M, y - 28, "C.R: 1010851840", size=9, align="left")

        txt(PW - M, y - 6, "مصنع جاديت للتصنيع", size=13, bold=True, align="right")
        txt(PW - M, y - 14, "المملكة العربية السعودية", size=9, align="right")
        txt(PW - M, y - 21, "الرياض - صناعية الموسى", size=9, align="right")
        txt(PW - M, y - 28, "سجل تجاري: 1010851840", size=9, align="right")

        logo_bottom = y - 28  # قيمة احتياطية إن تعذّر تحميل الشعار (أسفل آخر سطر بيانات الشركة)
        try:
            logo_bytes = base64.b64decode(APP_LOGO_B64)
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            lw, lh = 55 * mm, 12 * mm
            logo_top = y - 6
            logo_bottom = logo_top - lh
            c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass

        y = min(y - 28, logo_bottom) - 8 * mm  # مسافة أمان واضحة أسفل أعمق عنصر بالرأس (الشعار أو نص الشركة)

        # ====== رقم التشغيل (بدل NO. الأحمر) + بيانات العميل ======
        rect(M, y, 32 * mm, 9 * mm)
        set_no_txt = str(data.get("set_number") or "-")
        set_no_size = fit_font_size(set_no_txt, 30 * mm, 13, bold=True)
        txt(M + 16 * mm, y - 6 * mm, set_no_txt, size=set_no_size, bold=True, align="center")
        txt(M + 32 * mm + 3, y - 6 * mm, "رقم التشغيل", size=10, bold=True, align="left")

        info_max_w = PW - M - (M + 32 * mm + 3) - 5 * mm
        name_line = f"اسم العميل: {data.get('name','')}"
        name_size = fit_font_size(name_line, info_max_w, 11, min_size=8)
        txt(PW - M, y - 3.5 * mm, name_line, size=name_size, align="right")
        y -= 9 * mm
        date_line = f"التاريخ: {data.get('date','')}"
        date_size = fit_font_size(date_line, info_max_w, 11, min_size=8)
        txt(PW - M, y - 3.5 * mm, date_line, size=date_size, align="right")
        y -= 10 * mm

        table_top = y - 4

        # ====== شبكة الجداول (3 أعمدة رئيسية) - كل صف جداول بارتفاع موحّد لتفادي أي تراكب ======
        col_w = (PW - 2 * M) / 3
        header_color = (0.65, 0.80, 0.45)  # أخضر فاتح مطابق للقالب
        subheader_color = (0.10, 0.20, 0.45)  # كحلي مطابق للقالب
        ROW_H = 11 * mm
        HEAD_H = 7 * mm
        SUB_H = 6.5 * mm

        def draw_mini_table(x, y0, w, title, sub_cols, n_rows, row_h=ROW_H, fill_map=None):
            """يرسم جدولاً صغيراً: عنوان أخضر + رأس أعمدة كحلي + صفوف بيانات فارغة/معبأة، ويرجع (y_نهاية، ارتفاع_كلي)"""
            from reportlab.lib.colors import Color
            rect(x, y0, w, HEAD_H, fill=Color(*header_color))
            title_size = fit_font_size(title, w - 3 * mm, 11, bold=True)
            txt(x + w / 2, vcenter_baseline(y0, HEAD_H, title_size), title, size=title_size, bold=True, align="center")
            n = len(sub_cols)
            cw = w / n
            cell_pad = 1.5 * mm
            rect(x, y0 - HEAD_H, w, SUB_H, fill=Color(*subheader_color))
            c.setFillColorRGB(1, 1, 1)
            for i, lbl in enumerate(sub_cols):
                lbl_size = fit_font_size(lbl, cw - 2 * cell_pad, 8.5, bold=True, min_size=5.5)
                c.setFont(_ARABIC_FONT_BOLD_NAME, lbl_size)
                c.drawCentredString(x + w - cw * i - cw / 2, vcenter_baseline(y0 - HEAD_H, SUB_H, lbl_size), ar(lbl))
            c.setFillColorRGB(0, 0, 0)
            yy = y0 - HEAD_H - SUB_H
            for r in range(n_rows):
                rect(x, yy, w, row_h)
                for i in range(1, n):
                    c.line(x + i * cw, yy - row_h, x + i * cw, yy)
                if fill_map and r in fill_map:
                    for col_idx, val in fill_map[r].items():
                        cx = x + w - cw * col_idx - cw / 2
                        val_size = fit_font_size(val, cw - 2 * cell_pad, 10, bold=True, min_size=6.5)
                        txt(cx, vcenter_baseline(yy, row_h, val_size), val, size=val_size, bold=True, align="center")
                yy -= row_h
            total_h = HEAD_H + SUB_H + n_rows * row_h
            return yy, total_h

        GAP = 2.5 * mm
        cols3 = ["النقاص", "الوزن بعد", "الوزن قبل"]

        # صف 1: الأوزان | التركيب | التصنيع (فارغة، للتعبئة اليدوية لاحقاً) - صفان لكل جدول
        y1, h1 = draw_mini_table(M, table_top, col_w, "الأوزان", cols3, 2)
        draw_mini_table(M + col_w, table_top, col_w, "التركيب", cols3, 2)
        draw_mini_table(M + 2 * col_w, table_top, col_w, "التصنيع", cols3, 2)
        row2_top = table_top - h1 - GAP

        # صف 2: الذهب الصافي (فارغة الآن - القيمة انتقلت لجدول تفاصيل الأوزان) | التركيب | البوليش - صفان لتوحيد الارتفاع
        y2, h2 = draw_mini_table(M, row2_top, col_w, "الذهب الصافي", ["البيان", "الوزن"], 2)
        draw_mini_table(M + col_w, row2_top, col_w, "التركيب", cols3, 2)
        draw_mini_table(M + 2 * col_w, row2_top, col_w, "البوليش", cols3, 2)
        row3_top = row2_top - h2 - GAP

        # صف موحّد: جدول واحد يعرض الذهب/الفصوص/الأحجار/الأحجار بعد الخصم (مع توضيح النسبة)/الماس، بدل الجداول المتفرقة السابقة
        try:
            discount_pct_display = round((stones_discount_num / stones) * 100, 1) if stones > 0 else 0.0
        except Exception:
            discount_pct_display = 0.0
        materials_cols = ["البيان", "القيمة"]
        khayas_val = data.get("khayas", 0.0) or 0.0

        # ══════════════════════════════════════════════════════════════════
        #  جدول (الوزن النهائي) بترتيب النموذج الورقي المعتمد، من الأسفل لأعلى:
        #      الوزن الصافي   = الذهب
        #      ناقص الماس     = الماس
        #      ناقص احجار     = الأحجار
        #      ناقص فصوص      = الفصوص
        #      الوزن النهائي  = مجموع الأربعة أعلاه
        #
        #  التسميات «ناقص …» كما في النموذج الورقي؛ والقيم تُجمع لا تُطرح،
        #  لأن الوزن النهائي في النموذج هو الوزن الكلي قبل استبعاد الأصناف.
        # ══════════════════════════════════════════════════════════════════
        final_weight = round(gold + diamond + stones + gems, 2)
        materials_fill = {
            0: {0: "الوزن النهائي", 1: f"{final_weight:.2f}"},
            1: {0: "ناقص فصوص", 1: f"{gems:.2f}"},
            2: {0: "ناقص احجار", 1: f"{stones:.2f}"},
            3: {0: "ناقص الماس", 1: f"{diamond:.2f}"},
            4: {0: "الوزن الصافي", 1: f"{gold:.2f}"},
            5: {0: f"الأحجار بعد الخصم ({discount_pct_display:g}%)", 1: f"{stones_discount_num:.2f}"},
            6: {0: "خياس التلميع النهائي", 1: f"{khayas_val:.2f}"},
            7: {0: "خياس البوليش", 1: f"{data.get('khayas_polish', 0.0):.2f}"},
            8: {0: "خياس المركب", 1: f"{data.get('khayas_assembler', 0.0):.2f}"},
            9: {0: "الصافي", 1: f"{data.get('net', 0.0):.2f}"},
        }
        y34, h34 = draw_mini_table(M, row3_top, col_w, "الوزن النهائي", materials_cols, 10, row_h=7 * mm, fill_map=materials_fill)
        rect(M + col_w, row3_top, 2 * col_w, h34)
        row5_top = row3_top - h34 - GAP

        # صف 5: الإجمالي (محسوب تلقائياً) | تاريخ استلام الطلب + مساحة إضافية
        total_cols = ["البيان", "الوزن"]
        totals_fill = {
            0: {0: "الوزن مع الفصوص", 1: f"{weight_with_gems:.2f}"},
            1: {0: "الوزن القائم", 1: f"{weight_standing:.2f}"},
            2: {0: "الوزن المقيد", 1: f"{weight_bound:.2f}"},
        }
        y5, h5 = draw_mini_table(M, row5_top, col_w, "الإجمالي", total_cols, 3, row_h=9 * mm, fill_map=totals_fill)

        from reportlab.lib.colors import Color
        recv_h = 8 * mm
        rect(M + col_w, row5_top, 2 * col_w, recv_h, fill=Color(*header_color))
        recv_size = fit_font_size("تاريخ استلام الطلب", 2 * col_w - 6 * mm, 11, bold=True)
        txt(M + col_w + col_w, vcenter_baseline(row5_top, recv_h, recv_size), "تاريخ استلام الطلب", size=recv_size, bold=True, align="center")
        rect(M + col_w, row5_top - recv_h, 2 * col_w, h5 - recv_h)

        # ====== التوقيعات ======
        sig_y = 18 * mm
        sig_w = (PW - 2 * M) / 3
        for i, label in enumerate(["توقيع المدير", "توقيع المحاسب", "توقيع مسؤول الصالة"]):
            cx = M + sig_w * i + sig_w / 2
            c.line(M + sig_w * i + 10, sig_y, M + sig_w * (i + 1) - 10, sig_y)
            sig_size = fit_font_size(label, sig_w - 20, 10, bold=True)
            txt(cx, sig_y - 6, label, size=sig_size, bold=True, align="center")

    def draw_sales_summary_pages(self, c, rows_data, name, date_str):
        """يرسم صفحة (أو أكثر عند كثرة الأسطر) لفاتورة المبيعات الإجمالية: جدول مرقّم بكل الأسطر + صف الإجمالي، بنفس تصميم قالب فاتورة المبيعات (الأزرق)، قبل صفحات أرقام التشغيل التفصيلية"""
        from reportlab.lib.colors import Color
        PW, PH = A4
        M = 10 * mm
        header_fill = Color(0.78, 0.80, 0.93)   # لافندر فاتح مطابق لقالب فاتورة المبيعات
        border_color = Color(0.15, 0.15, 0.55)  # كحلي غامق للحدود والنصوص

        def txt(x, y, s, size=9, bold=False, align="right", color=None):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            if color:
                c.setFillColor(color)
            s = ar(s)
            if align == "right":
                c.drawRightString(x, y, s)
            elif align == "left":
                c.drawString(x, y, s)
            else:
                c.drawCentredString(x, y, s)
            if color:
                c.setFillColorRGB(0, 0, 0)

        def rect(x, y, w, h, fill=None, stroke_color=None):
            c.saveState()
            if stroke_color:
                c.setStrokeColor(stroke_color)
            if fill:
                c.setFillColor(fill)
                c.rect(x, y - h, w, h, fill=1, stroke=1)
            else:
                c.rect(x, y - h, w, h, fill=0, stroke=1)
            c.restoreState()

        # الأعمدة من اليمين لليسار: التسلسل، رقم التشغيل، الذهب، الفصوص، الأحجار، الأحجار بعد الخصم، الماس، الوزن القائم، الوزن المقيد
        cols = ["#", "رقم التشغيل", "الذهب", "الفصوص", "الأحجار", "الأحجار بعد الخصم", "الماس", "خياس", "الوزن القائم", "الوزن المقيد"]
        col_ratios = [0.45, 0.95, 0.85, 0.85, 0.85, 1.05, 0.85, 0.8, 0.95, 0.95]
        n_cols = len(cols)
        table_w = PW - 2 * M
        ratio_sum = sum(col_ratios)
        col_ws = [table_w * r / ratio_sum for r in col_ratios]
        col_x_starts = []
        acc = 0.0
        for w in col_ws:
            col_x_starts.append(acc)
            acc += w

        row_h = 8.5 * mm
        header_h = 11 * mm
        max_rows_per_page = 24

        total_rows = len(rows_data)
        idx = 0
        page_num = 1

        while idx < total_rows or (idx == 0 and total_rows == 0):
            y = PH - M

            # رأس الصفحة: نفس شعار وبيانات الشركة المعتمدة بباقي صفحات الفاتورة
            txt(M, y - 6, "Jadeite Factory", size=12, bold=True, align="left")
            txt(M, y - 13, "Saudi Arabia, Riyadh", size=8, align="left")
            txt(PW - M, y - 6, "مصنع جاديت للتصنيع", size=12, bold=True, align="right")
            txt(PW - M, y - 13, "المملكة العربية السعودية", size=8, align="right")
            logo_bottom = y - 13  # قيمة احتياطية إن تعذّر تحميل الشعار
            try:
                logo_bytes = base64.b64decode(APP_LOGO_B64)
                logo_img = ImageReader(io.BytesIO(logo_bytes))
                lw, lh = 45 * mm, 10 * mm
                logo_top = y - 4
                logo_bottom = logo_top - lh
                c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
            except Exception:
                pass
            y = min(y - 13, logo_bottom) - 9 * mm  # مسافة أمان واضحة أسفل أعمق عنصر بالرأس (الشعار أو نص الشركة)

            txt(PW / 2, y, "فاتورة مبيعات", size=16, bold=True, align="center", color=border_color)
            y -= 8 * mm
            name_line = f"العميل: {name}"
            name_size = fit_font_size(name_line, (PW - 2 * M) * 0.62, 11, bold=True, min_size=8)
            txt(PW - M, y, name_line, size=name_size, bold=True, align="right")
            txt(M, y, f"عدد الأسطر: {total_rows}", size=10, align="left")
            y -= 6.5 * mm
            txt(PW - M, y, f"التاريخ: {date_str}", size=11, align="right")
            if page_num > 1:
                txt(M, y, f"(تابع - صفحة {page_num})", size=10, align="left")
            y -= 8 * mm

            table_top = y
            rect(M, table_top, table_w, header_h, fill=header_fill, stroke_color=border_color)
            for i, lbl in enumerate(cols):
                cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                hdr_size = fit_font_size(lbl, col_ws[i] - 3 * mm, 10, bold=True, min_size=6.5)
                txt(cx, vcenter_baseline(table_top, header_h, hdr_size), lbl, size=hdr_size, bold=True, align="center", color=border_color)
                if i > 0:
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], table_top - header_h, M + table_w - col_x_starts[i], table_top)

            y = table_top - header_h
            page_rows = rows_data[idx: idx + max_rows_per_page]

            for row_i, data in enumerate(page_rows):
                rect(M, y, table_w, row_h, stroke_color=border_color)
                for i in range(1, n_cols):
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], y - row_h, M + table_w - col_x_starts[i], y)
                gold_v = data.get('gold', 0) or 0.0
                gems_v = data.get('gems', 0) or 0.0
                stones_v = data.get('stones', 0) or 0.0
                diamond_v = data.get('diamond', 0) or 0.0
                try:
                    stones_disc_v = float(data.get("stones_discount") or 0)
                except (ValueError, TypeError):
                    stones_disc_v = 0.0
                row_weight_standing = round(gold_v + gems_v + stones_v + diamond_v, 2)
                row_weight_bound = round(gold_v + gems_v + stones_disc_v + diamond_v, 2)
                khayas_v = data.get("khayas", 0) or 0.0
                values = [
                    str(idx + row_i + 1),
                    str(data.get("set_number") or "-"),
                    f"{gold_v:.2f}" if gold_v else "-",
                    f"{gems_v:.2f}" if gems_v else "-",
                    f"{stones_v:.2f}" if stones_v else "-",
                    str(data.get("stones_discount") or "-"),
                    f"{diamond_v:.2f}" if diamond_v else "-",
                    f"{khayas_v:.2f}" if khayas_v else "-",
                    f"{row_weight_standing:.2f}" if row_weight_standing else "-",
                    f"{row_weight_bound:.2f}" if row_weight_bound else "-",
                ]
                for i, val in enumerate(values):
                    cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                    val_size = fit_font_size(val, col_ws[i] - 3 * mm, 9.5, min_size=6.5)
                    txt(cx, vcenter_baseline(y, row_h, val_size), val, size=val_size, align="center")
                y -= row_h

            idx += len(page_rows)

            # صف الإجمالي والتوقيعات تظهر فقط في آخر صفحة من الجدول
            if idx >= total_rows:
                tot_gold = sum(d.get("gold", 0.0) for d in rows_data)
                tot_gems = sum(d.get("gems", 0.0) for d in rows_data)
                tot_stones = sum(d.get("stones", 0.0) for d in rows_data)
                tot_stones_discount = 0.0
                for d in rows_data:
                    try:
                        tot_stones_discount += float(d.get("stones_discount") or 0)
                    except ValueError:
                        pass
                tot_diamond = sum(d.get("diamond", 0.0) for d in rows_data)
                tot_khayas = sum(d.get("khayas", 0.0) or 0.0 for d in rows_data)
                tot_weight_standing = round(tot_gold + tot_gems + tot_stones + tot_diamond, 2)
                tot_weight_bound = round(tot_gold + tot_gems + tot_stones_discount + tot_diamond, 2)

                rect(M, y, table_w, row_h, fill=header_fill, stroke_color=border_color)
                # "الإجمالي" تمتد على عمودي التسلسل ورقم التشغيل، والقيم تحت كل عمود مادة
                total_lbl_w = col_ws[0] + col_ws[1]
                total_lbl_size = fit_font_size("الإجمالي", total_lbl_w - 3 * mm, 11, bold=True)
                txt(M + table_w - (col_x_starts[0] + col_ws[0] + col_ws[1]) / 2 - col_ws[0] / 2, vcenter_baseline(y, row_h, total_lbl_size), "الإجمالي", size=total_lbl_size, bold=True, align="center", color=border_color)
                totals_by_col = {2: tot_gold, 3: tot_gems, 4: tot_stones, 5: tot_stones_discount, 6: tot_diamond,
                                 7: tot_khayas, 8: tot_weight_standing, 9: tot_weight_bound}
                for i, val in totals_by_col.items():
                    cx = M + table_w - col_x_starts[i] - col_ws[i] / 2
                    val_txt = f"{val:.2f}"
                    tot_val_size = fit_font_size(val_txt, col_ws[i] - 3 * mm, 10.5, bold=True, min_size=7)
                    txt(cx, vcenter_baseline(y, row_h, tot_val_size), val_txt, size=tot_val_size, bold=True, align="center", color=border_color)
                for i in range(1, n_cols):
                    c.setStrokeColor(border_color)
                    c.line(M + table_w - col_x_starts[i], y - row_h, M + table_w - col_x_starts[i], y)
                y -= row_h

                sig_y = 20 * mm
                sig_w = table_w / 3
                for i, label in enumerate(["توقيع المدير", "توقيع المحاسب", "توقيع مسؤول الصالة"]):
                    cx = M + sig_w * i + sig_w / 2
                    c.line(M + sig_w * i + 10, sig_y, M + sig_w * (i + 1) - 10, sig_y)
                    txt(cx, sig_y - 6, label, size=9, bold=True, align="center")

            c.showPage()
            page_num += 1

            if total_rows == 0:
                break

    def generate_invoice_pdf(self, groups, output_path):
        """ينشئ ملف PDF: صفحة فاتورة مبيعات إجمالية أولاً (إن كانت كل الأسطر بنفس التاريخ والاسم)، ثم صفحة مستقلة لكل رقم تشغيل، بنفس تصميم الفاتورة الثابت"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "ميزة طباعة الفواتير تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return False
        c = pdf_canvas.Canvas(output_path, pagesize=A4)

        if groups:
            dates = set(g[1] for g in groups)
            names = set(g[2] for g in groups)
            if len(dates) == 1 and len(names) == 1:
                batch_date, batch_name = groups[0][1], groups[0][2]
                rows_data = [self.get_invoice_group_data(sn, batch_date, batch_name) for sn, _, _ in groups]
                self.draw_sales_summary_pages(c, rows_data, batch_name, batch_date)

        for (set_number, date_str, name) in groups:
            data = self.get_invoice_group_data(set_number, date_str, name)
            self.draw_invoice_page(c, data)
            c.showPage()
        c.save()
        return True

    def preview_invoice_groups(self, groups):
        """يولّد PDF للفواتير المحدّدة (صفحة لكل سطر) ويفتحه للمعاينة بعارض PDF الافتراضي"""
        if not groups:
            return
        if not REPORTLAB_AVAILABLE:
            messagebox.showwarning("تنبيه", "ميزة معاينة الفواتير تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi\n\nتم ترحيل المبيعات بنجاح رغم ذلك.")
            return
        out_dir = INVOICES_DIR
        fname = f"invoice_preview_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        out_path = os.path.join(out_dir, fname)
        try:
            ok = self.generate_invoice_pdf(groups, out_path)
            if not ok:
                return
            self.last_generated_invoice_pdf = out_path
            self._open_file(out_path)
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر إنشاء/فتح ملف الفاتورة:\n{e}")

    def print_invoice_groups(self, groups):
        """يولّد PDF للفواتير المحدّدة ويرسلها مباشرة للطابعة الافتراضية"""
        if not groups:
            messagebox.showwarning("تنبيه", "لا توجد فواتير لطباعتها.")
            return
        if not REPORTLAB_AVAILABLE:
            messagebox.showwarning("تنبيه", "ميزة طباعة الفواتير تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return
        out_dir = INVOICES_DIR
        fname = f"invoice_print_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        out_path = os.path.join(out_dir, fname)
        try:
            ok = self.generate_invoice_pdf(groups, out_path)
            if not ok:
                return
            self.last_generated_invoice_pdf = out_path
            self._print_file(out_path)
            messagebox.showinfo("تم", f"تم إرسال {len(groups)} فاتورة إلى الطابعة الافتراضية.")
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر طباعة الفاتورة:\n{e}")

    def _open_file(self, path):
        """يفتح ملفاً بالبرنامج الافتراضي لنظام التشغيل (لمعاينة PDF مثلاً)"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّر فتح الملف تلقائياً، يمكنك فتحه يدوياً من:\n{path}\n\n{e}")

    def _print_file(self, path):
        """يرسل ملفاً للطباعة على الطابعة الافتراضية لنظام التشغيل"""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path, "print")
            elif sys.platform == "darwin":
                subprocess.Popen(["lp", path])
            else:
                subprocess.Popen(["lp", path])
        except Exception as e:
            messagebox.showerror("خطأ", f"تعذّرت الطباعة المباشرة، تم فتح الملف بدلاً من ذلك لتطبعه يدوياً.\n{e}")
            self._open_file(path)

    # =========================================================================
    # --- القيود اليومية: نظام محاسبي عام (من حساب مدين / إلى حساب دائن) يؤثر في أي حساب بالنظام ---
    # =========================================================================
    def get_journal_entry_account_options(self):
        """كل الحسابات المعروفة بالنظام + أي اسم جديد استُخدم سابقاً بقيد يومي (لخانتي المدين والدائن)"""
        return self.get_account_statement_options()

    def build_journal_entries_tab(self):
        tab = self.tabview.tab("القيود اليومية")

        ctk.CTkLabel(tab, text="📖 القيود اليومية", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(pady=(15, 8))

        date_row = ctk.CTkFrame(tab, fg_color="transparent")
        date_row.pack(pady=6)
        ctk.CTkLabel(date_row, text="التاريخ:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.je_date = ctk.CTkEntry(date_row, font=("Cairo", 14), justify="center", width=140, height=38)
        self.je_date.insert(0, self.get_smart_default_date())
        self.je_date.pack(side="right", padx=5)

        self.je_invoice_display = ctk.CTkLabel(date_row, text=f"# {self.invoice_counter + 1}", font=("Cairo", 15, "bold"), text_color="#d4af37", fg_color="#1a1a1a", corner_radius=6, width=90, height=38)
        self.je_invoice_display.pack(side="right", padx=5)
        ctk.CTkLabel(date_row, text="رقم الفاتورة:", font=("Cairo", 14, "bold"), text_color="#1f77b4").pack(side="right", padx=5)

        # ====== الصف الأول: من حساب (مدين) ======
        row1 = ctk.CTkFrame(tab, corner_radius=10)
        row1.pack(fill="x", padx=30, pady=8)
        ctk.CTkLabel(row1, text="من حساب (مدين):", font=("Cairo", 15, "bold"), text_color="#e74c3c").pack(side="right", padx=10, pady=12)
        self.je_from_name = ctk.CTkComboBox(row1, values=self.get_journal_entry_account_options(), font=("Cairo", 14), justify="right", width=280, height=38)
        self.je_from_name.set("")
        self.je_from_name.pack(side="right", padx=10, pady=12)
        self.bind_name_autocomplete(self.je_from_name, self.get_journal_entry_account_options)

        # ====== الصف الثاني: إلى حساب (دائن) ======
        row2 = ctk.CTkFrame(tab, corner_radius=10)
        row2.pack(fill="x", padx=30, pady=8)
        ctk.CTkLabel(row2, text="إلى حساب (دائن):", font=("Cairo", 15, "bold"), text_color="#2ecc71").pack(side="right", padx=10, pady=12)
        self.je_to_name = ctk.CTkComboBox(row2, values=self.get_journal_entry_account_options(), font=("Cairo", 14), justify="right", width=280, height=38)
        self.je_to_name.set("")
        self.je_to_name.pack(side="right", padx=10, pady=12)
        self.bind_name_autocomplete(self.je_to_name, self.get_journal_entry_account_options)

        amount_row = ctk.CTkFrame(tab, fg_color="transparent")
        amount_row.pack(pady=10)
        ctk.CTkLabel(amount_row, text="الوزن / القيمة:", font=("Cairo", 15, "bold"), text_color="#1f77b4").pack(side="right", padx=8)
        self.je_amount = ctk.CTkEntry(amount_row, justify="center", font=("Cairo", 15), width=140, height=40)
        self.je_amount.pack(side="right", padx=8)

        btn_submit = ctk.CTkButton(tab, text="✅ ترحيل العملية", font=ctk.CTkFont(family="Cairo", size=16, weight="bold"), height=46, fg_color="#144d75", hover_color="#0d3350", command=self.submit_journal_entry)
        btn_submit.pack(pady=15)

        self.lbl_je_status = ctk.CTkLabel(tab, text="", font=("Cairo", 13, "bold"), text_color="#2ecc71")
        self.lbl_je_status.pack()

        ctk.CTkLabel(tab, text="آخر القيود اليومية المرحّلة", font=("Cairo", 14, "bold"), text_color="#d4af37").pack(pady=(15, 4))
        self.je_table_frame = ttk.Frame(tab)
        self.je_table_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self.je_tree = None

        btn_print_je = ctk.CTkButton(tab, text="🖨️ طباعة القيود اليومية", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=40, command=self.print_journal_entries_screen)
        btn_print_je.pack(pady=(0, 15))

        self.refresh_journal_entries_table()

    def print_journal_entries_screen(self):
        cols = ("التاريخ", "من حساب (مدين)", "إلى حساب (دائن)", "القيمة")
        col_ratios = [1.1, 1.5, 1.5, 0.9]
        debit_by_ref, credit_by_ref = {}, {}
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            ref = inv.get("set_number", "")
            if inv.get("النوع") == "قيد يومي مدين":
                debit_by_ref[ref] = inv
            elif inv.get("النوع") == "قيد يومي دائن":
                credit_by_ref[ref] = inv
        refs = sorted(set(debit_by_ref) | set(credit_by_ref),
                      key=lambda r: (debit_by_ref.get(r) or credit_by_ref.get(r)).get("التاريخ", ""))
        rows = []
        for ref in refs:
            d = debit_by_ref.get(ref)
            cr = credit_by_ref.get(ref)
            base = d or cr
            rows.append((base.get("التاريخ", "")[:16], d.get("الاسم", "-") if d else "-", cr.get("الاسم", "-") if cr else "-", f"{base.get('الوزن', 0):.2f}"))
        self.print_generic_table_screen("📖 القيود اليومية", cols, col_ratios, rows, "journal_entries_screen")

    def submit_journal_entry(self):
        from_name = self.je_from_name.get().strip()
        to_name = self.je_to_name.get().strip()
        date_val = self.je_date.get().strip()

        if not from_name or not to_name:
            messagebox.showwarning("تنبيه", "الرجاء إدخال اسم حساب المدين واسم حساب الدائن.")
            return
        if from_name == to_name:
            messagebox.showwarning("تنبيه", "لا يمكن أن يكون حساب المدين وحساب الدائن نفس الاسم.")
            return
        try:
            amount = round(float(self.je_amount.get().strip()), 2)
            if amount <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("خطأ", "الرجاء إدخال قيمة صحيحة أكبر من صفر.")
            return

        if not messagebox.askyesno("تأكيد الترحيل", f"هل أنت متأكد من ترحيل هذا القيد اليومي؟\nمن حساب (مدين): {from_name}\nإلى حساب (دائن): {to_name}\nالقيمة: {amount:.2f}"):
            return

        full_dt = f"{date_val} {datetime.datetime.now().strftime('%H:%M:%S')}"
        entry_ref = f"JE-{self.invoice_counter + 1}"

        self.invoice_counter += 1
        inv_from = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": from_name,
                    "النوع": "قيد يومي مدين", "الوزن": amount, "البيان": "", "settled_status": "ACTIVE",
                    "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
        self.invoices[self.invoice_counter] = inv_from
        self.save_invoice_to_db(self.invoice_counter, inv_from)

        self.invoice_counter += 1
        inv_to = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": to_name,
                  "النوع": "قيد يومي دائن", "الوزن": amount, "البيان": "", "settled_status": "ACTIVE",
                  "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
        self.invoices[self.invoice_counter] = inv_to
        self.save_invoice_to_db(self.invoice_counter, inv_to)

        self.je_from_name.set("")
        self.je_to_name.set("")
        self.je_amount.delete(0, 'end')

        self.register_operation_period(date_val)
        self.recalculate_all()
        self.lbl_je_status.configure(text="✅ تم ترحيل القيد اليومي بنجاح")
        self.after(2500, lambda: self.lbl_je_status.configure(text=""))
        if messagebox.askyesno("طباعة", "هل تريد طباعة القيد؟"):
            self.print_single_journal_entry(entry_ref)

    def print_single_journal_entry(self, entry_ref):
        """يطبع قيداً يومياً واحداً بعينه بقالب فاتورة (من حساب / إلى حساب / القيمة / التاريخ)"""
        debit_inv = credit_inv = None
        for inv in self.invoices.values():
            if inv.get("set_number") != entry_ref: continue
            if inv.get("النوع") == "قيد يومي مدين": debit_inv = inv
            elif inv.get("النوع") == "قيد يومي دائن": credit_inv = inv
        if not debit_inv or not credit_inv:
            return
        cols = ("رقم القيد", "التاريخ", "من حساب (مدين)", "إلى حساب (دائن)", "القيمة", "البيان")
        col_ratios = [0.8, 1.1, 1.3, 1.3, 0.8, 1.0]
        rows = [(entry_ref, debit_inv["التاريخ"][:16], debit_inv["الاسم"], credit_inv["الاسم"],
                 f"{debit_inv['الوزن']:.2f}", debit_inv.get("البيان") or "قيد يومي")]
        self.print_generic_table_screen("📖 فاتورة قيد يومي", cols, col_ratios, rows, "journal_entry_operation")

    def refresh_journal_entries_table(self):
        if not hasattr(self, 'je_table_frame') or not self.je_table_frame:
            return
        for widget in self.je_table_frame.winfo_children():
            widget.destroy()

        if hasattr(self, 'je_invoice_display'):
            self.je_invoice_display.configure(text=f"# {self.invoice_counter + 1}")
        if hasattr(self, 'je_from_name'):
            self.je_from_name.configure(values=self.get_journal_entry_account_options())
        if hasattr(self, 'je_to_name'):
            self.je_to_name.configure(values=self.get_journal_entry_account_options())

        cols = ("التاريخ", "من حساب (مدين)", "إلى حساب (دائن)", "القيمة")
        self.je_tree = self.create_standard_treeview(self.je_table_frame, cols, height=10)
        for c in cols:
            w = 220 if "حساب" in c else 150
            self.je_tree.column(c, width=w, anchor="center")

        debit_by_ref, credit_by_ref = {}, {}
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            ref = inv.get("set_number", "")
            if inv.get("النوع") == "قيد يومي مدين":
                debit_by_ref[ref] = inv
            elif inv.get("النوع") == "قيد يومي دائن":
                credit_by_ref[ref] = inv

        refs = sorted(set(debit_by_ref) | set(credit_by_ref),
                      key=lambda r: (debit_by_ref.get(r) or credit_by_ref.get(r)).get("التاريخ", ""), reverse=True)

        for ref in refs[:150]:
            d = debit_by_ref.get(ref)
            cr = credit_by_ref.get(ref)
            base = d or cr
            self.je_tree.insert("", "end", values=(
                base.get("التاريخ", ""), d.get("الاسم", "-") if d else "-", cr.get("الاسم", "-") if cr else "-",
                f"{base.get('الوزن', 0):.2f}"
            ))

    # =========================================================================
    # --- شاشة الخسائر: إقفال صناديق الخياس (الكاستنج/التلميع/التلميع-البف) عبر قيد يومي ---
    # =========================================================================
    def build_losses_tab(self):
        outer = self.tabview.tab("شاشة الخسائر")

        # إطار قابل للتمرير: عدد الصناديق يزيد مع الأقسام المضافة،
        # وبدون تمرير كانت البطاقات الأخيرة وأزرار الكشف والطباعة تختفي أسفل الشاشة
        tab = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        tab.pack(fill="both", expand=True, padx=4, pady=4)

        # شريط اختيار الفترة: يعرض الفترات المسجّلة فقط، وكل صندوق يُعرض
        # بأرقام تلك الفترة وحدها
        period_bar = ctk.CTkFrame(tab, fg_color="transparent")
        period_bar.pack(fill="x", padx=10, pady=(6, 0))

        ctk.CTkLabel(period_bar, text="الفترة:", font=("Cairo", 14, "bold")).pack(side="right", padx=6)
        self.combo_losses_period = ctk.CTkComboBox(
            period_bar, values=self.get_recorded_periods(), font=("Cairo", 14),
            width=150, height=34, justify="center", state="readonly",
            command=lambda _v: self.refresh_losses_tab())
        self.combo_losses_period.set(self.current_display_month)
        self.combo_losses_period.pack(side="right", padx=4)

        ctk.CTkButton(period_bar, text="🔍 بحث", font=("Cairo", 13, "bold"),
                      fg_color="#1e8449", hover_color="#145a32", width=100, height=34,
                      command=self.refresh_losses_tab).pack(side="right", padx=6)

        ctk.CTkLabel(tab, text="📉 شاشة الخسائر - إقفال صناديق الخياس", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(pady=(15, 10))

        search_row = ctk.CTkFrame(tab, fg_color="transparent")
        search_row.pack(pady=(0, 10))
        ctk.CTkLabel(search_row, text="من شهر:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.losses_from_month = ctk.CTkEntry(search_row, placeholder_text="YYYY-MM", font=("Cairo", 13), justify="center", width=110, height=36)
        self.losses_from_month.pack(side="right", padx=5)
        ctk.CTkLabel(search_row, text="إلى شهر:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.losses_to_month = ctk.CTkEntry(search_row, placeholder_text="YYYY-MM", font=("Cairo", 13), justify="center", width=110, height=36)
        self.losses_to_month.pack(side="right", padx=5)
        ctk.CTkButton(search_row, text="عرض الكل ↺", font=("Cairo", 13, "bold"), fg_color="#555555", hover_color="#333333", width=100, height=36, command=self.clear_losses_period).pack(side="right", padx=8)

        self.losses_cards_frame = ctk.CTkFrame(tab, fg_color="transparent")
        self.losses_cards_frame.pack(fill="x", padx=20, pady=10)

        self.losses_card_widgets = {}
        self.refresh_losses_cards()

        btn_statement = ctk.CTkButton(tab, text="📋 كشف حساب الخسائر (كل الإقفالات)", font=("Cairo", 14, "bold"), fg_color="#1f77b4", hover_color="#144d75", height=42, command=self.open_losses_statement)
        btn_statement.pack(pady=(15, 6))

        btn_print = ctk.CTkButton(tab, text="🖨️ طباعة شاشة الخسائر", font=("Cairo", 14, "bold"), fg_color="#144d75", hover_color="#0d3350", height=42, command=self.print_losses_screen)
        btn_print.pack(pady=(0, 15))

        self.refresh_losses_tab()

    def clear_losses_period(self):
        self.losses_from_month.delete(0, 'end')
        self.losses_to_month.delete(0, 'end')

    def open_box_statement(self, cat):
        box_account = self.get_box_account_name(cat)
        from_m = self.losses_from_month.get().strip() if hasattr(self, 'losses_from_month') else ""
        to_m = self.losses_to_month.get().strip() if hasattr(self, 'losses_to_month') else ""
        self.navigate_to_screen("كشف حساب")
        if hasattr(self, 'kh_account_name'):
            self.kh_account_name.set(box_account)
            if hasattr(self, 'kh_from_month'):
                self.kh_from_month.delete(0, 'end')
                if from_m: self.kh_from_month.insert(0, from_m)
            if hasattr(self, 'kh_to_month'):
                self.kh_to_month.delete(0, 'end')
                if to_m: self.kh_to_month.insert(0, to_m)
            self.refresh_account_statement()

    def refresh_losses_cards(self):
        """يعيد بناء لوحات شاشة الخسائر، متضمّناً أي قسم أُضيف ديناميكياً من شجرة الحسابات"""
        for widget in self.losses_cards_frame.winfo_children():
            widget.destroy()
        self.losses_card_widgets = {}

        box_defs = [("الكاستنج", "🏗️"), ("المصنعين", "👨‍🏭"), ("المركبين", "🔧"), ("التلميع", "✨"), ("التلميع/البف", "🪄"), ("خياس الطقوم", "💍")]
        for stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            box_defs.append((stage_name, "➕"))

        n_cols = 3
        for i, (cat, icon) in enumerate(box_defs):
            row, col = divmod(i, n_cols)
            card = ctk.CTkFrame(self.losses_cards_frame, corner_radius=14, border_width=2, border_color="#8b0000", fg_color=("gray90", "gray15"))
            card.grid(row=row, column=col, padx=10, pady=8, sticky="nsew")
            self.losses_cards_frame.grid_columnconfigure(col, weight=1)

            display_name = self.get_display_label(cat)
            ctk.CTkLabel(card, text=f"{icon} صندوق خياس {display_name}", font=ctk.CTkFont(family="Cairo", size=17, weight="bold"), text_color="#d4af37").pack(pady=(14, 6))
            lbl_current = ctk.CTkLabel(card, text="الخياس الحالي: 0.00", font=("Cairo", 15, "bold"), text_color="#e74c3c")
            lbl_current.pack(pady=4)
            lbl_closed = ctk.CTkLabel(card, text="إجمالي المُقفل: 0.00", font=("Cairo", 22, "bold"), text_color="#2ecc71")
            lbl_closed.pack(pady=(4, 12))

            btns_row = ctk.CTkFrame(card, fg_color="transparent")
            btns_row.pack(pady=(0, 14))
            btn_close = ctk.CTkButton(btns_row, text="🔒 إقفال الخياس", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=140, height=36, command=lambda c=cat: self.close_khayas_box(c))
            btn_close.pack(side="right", padx=4)
            btn_stmt = ctk.CTkButton(btns_row, text="📋 كشف حساب", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=110, height=36, command=lambda c=cat: self.open_box_statement(c))
            btn_stmt.pack(side="right", padx=4)

            lbl_detail = ctk.CTkLabel(card, text="", font=("Cairo", 11),
                                      justify="right", anchor="e", text_color="#8b8f95")
            lbl_detail.pack(fill="x", padx=12, pady=(2, 6))
            self.losses_card_widgets[cat] = {"current": lbl_current, "closed": lbl_closed,
                                             "detail": lbl_detail}

    def get_unclosed_periods(self, cat):
        """الفترات **المنتهية** التي ما زال فيها خياس غير مُقفل لهذا القسم.

        الفترة الحالية مستثناة: عملها لم ينتهِ بعد فلا معنى لإقفالها.
        """
        current = self.current_display_month
        out = []
        for month in self.get_recorded_periods():
            if month >= current:
                continue
            remaining = self.get_current_unclosed_khayas(cat, month=month)
            if abs(remaining) >= 0.005:
                out.append((month, remaining))
        return sorted(out)

    def check_unclosed_previous_periods(self):
        """ينبّه عند وجود فترات سابقة لم يُقفل خياسها، ويعرض إقفالها فوراً.

        يُستدعى عند تغيير الفترة: فمن السهل أن ينتقل المستخدم لشهر جديد ناسياً
        إقفال خياس الشهر المنتهي، فيبقى معلّقاً بلا أثر محاسبي.
        """
        pending = []
        for cat in ("المصنعين", "المركبين"):
            for month, amount in self.get_unclosed_periods(cat):
                pending.append((cat, month, amount))
        if not pending:
            return

        lines = "\n".join(
            f"   • {self.get_display_label(c)} — فترة {m}: {en(a)} جم" for c, m, a in pending)
        if not messagebox.askyesno(
                "خياس فترات سابقة لم يُقفل",
                f"هناك خياس فعلي في فترات منتهية لم يُقفل بعد:\n\n{lines}\n\n"
                "الإقفال يُثبّت خياس كل فترة في حسابها ويُرحّله للخسائر،\n"
                "وتبدأ الفترة الجديدة بخياس جديد خاص بها.\n\n"
                "هل تريد إقفالها الآن؟"):
            return

        for cat, month, _amount in pending:
            try:
                self.close_split_khayas_box(cat, month=month)
            except Exception as e:
                log_cloud_error(f"تعذّر إقفال خياس ({cat}) لفترة {month}", e)

    def get_recorded_periods(self):
        """الفترات التي سُجّلت فيها حركات فعلاً، الأحدث أولاً"""
        periods = {self.inv_period(inv) for inv in self.invoices.values()
                   if inv.get("settled_status") == "ACTIVE" and self.inv_period(inv)}
        periods.add(self.current_display_month)
        return sorted(periods, reverse=True)

    def refresh_losses_tab(self):
        if not hasattr(self, 'losses_card_widgets') or not self.losses_card_widgets:
            return

        # الفترة المختارة من شريط البحث، وإلا الفترة المعروضة حالياً
        month = self.current_display_month
        if hasattr(self, "combo_losses_period"):
            try:
                self.combo_losses_period.configure(values=self.get_recorded_periods())
                chosen = self.combo_losses_period.get().strip()
                if chosen:
                    month = chosen
            except Exception:
                pass

        for cat, widgets in self.losses_card_widgets.items():
            current = self.get_current_unclosed_khayas(cat, month=month)
            closed = self.get_box_closed_total(cat, month=month)
            widgets["current"].configure(text=f"الخياس الحالي: {current:.2f}")
            widgets["closed"].configure(text=f"إجمالي المُقفل: {closed:.2f}")

            # المصنعون والمركبون: تفصيل المكوّنات الثلاثة للحالي والمُقفل
            detail_widget = widgets.get("detail")
            if detail_widget is not None:
                try:
                    detail_widget.configure(text=self.get_box_breakdown_text(cat, month=month))
                except Exception:
                    pass

    def _post_closing_entry(self, box_account_name, amount, bayan, full_dt, period=None):
        """يسجّل قيد إقفال مزدوجاً (مدين الخسائر / دائن الصندوق أو العكس).

        الفصل في قيود منفصلة مقصود: يظهر في كشف حساب الخسائر سبب كل مبلغ
        (فاقد ٨/٤ أم خياس عمال) بدل مبلغ واحد مجمّع لا يُفسَّر لاحقاً.

        period: **فترة الشهر المُقفَل** لا الفترة المعروضة. بدون تمريرها كان
        القيد يُختم بالفترة التي تعمل فيها وقت الإقفال — فإقفال خياس شهر ٩
        من داخل شهر ١٠ كان يُسجَّل في شهر ١٠، فيختفي من سجل شهر ٩ ويُحمَّل
        على شهر ١٠ ظلماً.
        """
        if abs(amount) < 0.005:
            return
        entry_ref = f"JE-{self.invoice_counter + 1}"
        if amount > 0:
            from_name, to_name = "حساب الخسائر", box_account_name
        else:
            from_name, to_name = box_account_name, "حساب الخسائر"
        value = abs(amount)

        for name, op_type in ((from_name, "قيد يومي مدين"), (to_name, "قيد يومي دائن")):
            self.invoice_counter += 1
            inv = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": name,
                   "النوع": op_type, "الوزن": value, "البيان": bayan, "settled_status": "ACTIVE",
                   "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref}
            if period:
                inv["period"] = period
            self.invoices[self.invoice_counter] = inv
            self.save_invoice_to_db(self.invoice_counter, inv)

    def close_split_khayas_box(self, cat, month=None):
        """إقفال خياس المصنعين/المركبين بمكوّنيه المفصولين في قيدين مستقلين.

        month: الفترة المراد إقفالها (الافتراضي: الفترة المعروضة).
        """
        month = month or self.current_display_month
        display_name = f"{self.get_display_label(cat)} — فترة {month}"
        # مكوّنات المعادلة المعتمدة: (ذهب/باقي − المرجع ٧٥٠) ثم خصم الخياس الموجب
        faqid_k, marja_k, pos_k, total_k = self.get_section_khayas_parts(
            cat, target_month=month)
        net_before_pos = round(faqid_k - marja_k, 2)
        already_closed = self.get_box_closed_total(cat, month=month)
        remaining = round(total_k - already_closed, 2)

        if abs(remaining) < 0.005:
            messagebox.showinfo("لا يوجد خياس",
                                f"لا يوجد خياس غير مُقفل حالياً لصندوق ({display_name}).")
            return

        if not messagebox.askyesno(
                "تأكيد الإقفال",
                f"إقفال خياس صندوق ({display_name}):\n\n"
                f"• ذهب/باقي: {en(faqid_k)} جم\n"
                f"• المرجع ٧٥٠: −{en(marja_k)} جم\n"
                f"• الخياس الموجب: −{en(pos_k)} جم\n"
                f"• الإجمالي: {en(total_k)} جم\n"
                f"• سبق إقفاله: {en(already_closed)} جم\n"
                f"• المتبقّي للإقفال الآن: {en(remaining)} جم\n\n"
                "سيُرحَّل المتبقّي لحساب الخسائر بقيدين منفصلين. هل تريد المتابعة؟"):
            return

        box_account_name = self.get_box_account_name(cat)
        # تاريخ القيد: آخر يوم في الشهر المُقفَل، فيظهر في نهاية سجل فترته
        # بدل أن يبدو حركةً من شهر لاحق
        full_dt = self.period_closing_datetime(month)

        # نوزّع المتبقّي على مكوّنَي المعادلة بنسبتهما، فلا يُقفل شيء أُقفل
        # سابقاً، ويبقى مجموع القيدين = المتبقّي بالضبط
        if abs(total_k) > 0.005:
            share_net = round(remaining * (net_before_pos / total_k), 2)
        else:
            share_net = remaining
        share_pos = round(remaining - share_net, 2)

        # قيدان يوضّحان سبب المبلغ في كشف الخسائر، ومجموعهما = الخياس الفعلي
        self._post_closing_entry(box_account_name, share_net,
                                 f"إقفال خياس (ذهب/باقي − المرجع ٧٥٠) — فترة {month}",
                                 full_dt, period=month)
        self._post_closing_entry(box_account_name, share_pos,
                                 f"إقفال خصم الخياس الموجب — فترة {month}",
                                 full_dt, period=month)

        self.recalculate_all()
        messagebox.showinfo(
            "تم الإقفال",
            f"تم إقفال خياس صندوق ({display_name}):\n"
            f"(ذهب/باقي − المرجع ٧٥٠): {en(share_net)} جم  |  "
            f"خصم الخياس الموجب: {en(share_pos)} جم")
        self.refresh_losses_tab()

    def close_khayas_box(self, cat, month=None):
        # المصنعون والمركبون لهم مكوّنان مفصولان، فيُقفلان بمسار مستقل
        month = month or self.current_display_month
        if cat in ("المصنعين", "المركبين"):
            return self.close_split_khayas_box(cat, month=month)

        current = self.get_current_unclosed_khayas(cat, month=month)
        display_name = self.get_display_label(cat)
        if current == 0:
            messagebox.showinfo("لا يوجد خياس", f"لا يوجد خياس مسجّل حالياً لصندوق ({display_name}) لإقفاله.")
            return
        box_account_name = self.get_box_account_name(cat)

        if not messagebox.askyesno("تأكيد الإقفال", f"هل أنت متأكد من إقفال خياس صندوق ({display_name}) بقيمة {current:.2f}؟\nسيتم تصفير الخياس الحالي عبر قيد يومي."):
            return

        # القيد يُؤرَّخ في آخر الفترة المُقفَلة ويُختم بها، فيبقى في سجلّها
        full_dt = self.period_closing_datetime(month)
        entry_ref = f"JE-{self.invoice_counter + 1}"
        bayan = "إقفال"
        amount = abs(current)

        # current موجب (خياس عادي): مدين حساب الخسائر / دائن الصندوق - يزيد المُقفل
        # current سالب (الصندوق دائن/بالزيادة): دائن حساب الخسائر / مدين الصندوق - عكسي، يُخفّض المُقفل
        if current > 0:
            from_name, to_name = "حساب الخسائر", box_account_name
        else:
            from_name, to_name = box_account_name, "حساب الخسائر"

        self.invoice_counter += 1
        inv_from = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": from_name,
                    "النوع": "قيد يومي مدين", "الوزن": amount, "البيان": bayan, "settled_status": "ACTIVE",
                    "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref, "period": month}
        self.invoices[self.invoice_counter] = inv_from
        self.save_invoice_to_db(self.invoice_counter, inv_from)

        self.invoice_counter += 1
        inv_to = {"رقم الفاتورة": self.invoice_counter, "التاريخ": full_dt, "الاسم": to_name,
                  "النوع": "قيد يومي دائن", "الوزن": amount, "البيان": bayan, "settled_status": "ACTIVE",
                  "trees_count": 0.0, "قبل": 0.0, "بعد": 0.0, "set_number": entry_ref, "period": month}
        self.invoices[self.invoice_counter] = inv_to
        self.save_invoice_to_db(self.invoice_counter, inv_to)

        self.recalculate_all()
        messagebox.showinfo("تم الإقفال", f"تم إقفال خياس صندوق ({display_name}) بنجاح.")
        self.refresh_losses_tab()

    def open_losses_statement(self):
        self.navigate_to_screen("كشف حساب")
        if hasattr(self, 'kh_account_name'):
            self.kh_account_name.set("حساب الخسائر")
            self.refresh_account_statement()

    def print_losses_screen(self):
        """يولّد وعرض/يطبع صفحة PDF بنفس شكل شاشة الخسائر (لوحات لكل صندوق: الخياس الحالي + إجمالي المُقفل)"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "ميزة الطباعة تحتاج تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return
        out_dir = INVOICES_DIR
        out_path = os.path.join(out_dir, f"losses_screen_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        from reportlab.lib.colors import Color
        PW, PH = A4
        M = 10 * mm
        border_color = Color(0.55, 0.10, 0.10)

        def txt(c, x, y, s, size=9, bold=False, align="right", color=None):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            if color: c.setFillColor(color)
            s = ar(s)
            if align == "right": c.drawRightString(x, y, s)
            elif align == "left": c.drawString(x, y, s)
            else: c.drawCentredString(x, y, s)
            if color: c.setFillColorRGB(0, 0, 0)

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        y = PH - M

        txt(c, M, y - 6, "Jadeite Factory", size=12, bold=True, align="left")
        txt(c, M, y - 13, "Saudi Arabia, Riyadh", size=8, align="left")
        txt(c, PW - M, y - 6, "مصنع جاديت للتصنيع", size=12, bold=True, align="right")
        txt(c, PW - M, y - 13, "المملكة العربية السعودية", size=8, align="right")
        logo_bottom = y - 13
        try:
            logo_bytes = base64.b64decode(APP_LOGO_B64)
            logo_img = ImageReader(io.BytesIO(logo_bytes))
            lw, lh = 45 * mm, 10 * mm
            logo_top = y - 4
            logo_bottom = logo_top - lh
            c.drawImage(logo_img, (PW - lw) / 2, logo_bottom, width=lw, height=lh, mask='auto', preserveAspectRatio=True)
        except Exception:
            pass
        y = min(y - 13, logo_bottom) - 9 * mm

        txt(c, PW / 2, y, "📉 شاشة الخسائر - إقفال صناديق الخياس", size=17, bold=True, align="center", color=border_color)
        y -= 8 * mm
        txt(c, PW / 2, y, f"تاريخ الطباعة: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", size=10, align="center")
        y -= 8 * mm

        box_defs = [("الكاستنج", "الكاستنج"), ("المصنعين", "المصنعين"), ("المركبين", "المركبين"),
                    ("التلميع", self.get_display_label("التلميع")), ("التلميع/البف", self.get_display_label("التلميع/البف"))]
        for stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            box_defs.append((stage_name, stage_name))

        n_cols = 3
        card_w = (PW - 2 * M - 2 * 6 * mm) / n_cols
        card_h = 32 * mm
        gap = 6 * mm

        for i, (cat, disp) in enumerate(box_defs):
            row, col = divmod(i, n_cols)
            cx0 = M + col * (card_w + gap)
            cy0 = y - row * (card_h + gap)
            c.setStrokeColor(border_color)
            c.rect(cx0, cy0 - card_h, card_w, card_h, fill=0, stroke=1)
            txt(c, cx0 + card_w / 2, cy0 - 8 * mm, f"صندوق خياس {disp}", size=12, bold=True, align="center", color=border_color)
            current = self.get_current_unclosed_khayas(cat)
            closed = self.get_box_closed_total(cat)
            txt(c, cx0 + card_w / 2, cy0 - 16 * mm, f"الخياس الحالي: {current:.2f}", size=10, bold=True, align="center")
            txt(c, cx0 + card_w / 2, cy0 - 24 * mm, f"إجمالي المُقفل: {closed:.2f}", size=13, bold=True, align="center")

        c.showPage()
        c.save()
        self._open_file(out_path)

    # =========================================================================
    # --- شجرة الحسابات: عرض هرمي لكل حسابات النظام مصنّفة، مع الانتقال المباشر لكشف حسابها ---
    # =========================================================================
    def build_chart_of_accounts_tab(self):
        tab = self.tabview.tab("الحسابات")

        ctk.CTkLabel(tab, text="🌳 الحسابات", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(pady=(15, 8))
        ctk.CTkLabel(tab, text="اضغط مرتين على أي حساب فرعي لفتح كشف حسابه مباشرة", font=("Cairo", 12), text_color="#aaaaaa").pack(pady=(0, 8))

        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.coa_tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        self.coa_tree.pack(side="right", fill="both", expand=True)
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.coa_tree.yview)
        vsb.pack(side="left", fill="y")
        self.coa_tree.configure(yscrollcommand=vsb.set)
        self.coa_tree.tag_configure("group", foreground="#d4af37")
        self.coa_tree.tag_configure("leaf", foreground="#1f77b4")

        style = ttk.Style()
        try:
            style.configure("Treeview", font=("Cairo", 13), rowheight=30)
            style.configure("Treeview.Heading", font=("Cairo", 13, "bold"))
        except Exception:
            pass

        self.coa_tree.bind("<Double-1>", self.on_coa_double_click)

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(pady=(0, 12))
        ctk.CTkButton(btn_row, text="↺ تحديث الشجرة", font=("Cairo", 13, "bold"), fg_color="#1e8449", hover_color="#145a32", width=140, height=38, command=self.refresh_chart_of_accounts).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="➕ إضافة حساب", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=140, height=38, command=self.open_add_account_dialog).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="🗑️ حذف صندوق خياس", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=170, height=38, command=self.delete_khayas_box_dialog).pack(side="left", padx=5)

        self.refresh_chart_of_accounts()

    def get_deletable_khayas_boxes(self):
        """كل صناديق الخياس قابلة للحذف — الأساسية والمضافة.

        تنبيه: حذف صندوق أساسي يحذف حركاته ومسترجعه ويغيّر رصيد الخزينة
        وإجمالي الفواقد، ويُخفي شاشته من مراحل التصنيع. نافذة الحذف تعرض
        عدد حركاته وتطلب تأكيدين قبل التنفيذ.
        """
        return list(self.get_all_stage_categories())

    def count_box_transactions(self, stage_name):
        """عدد الحركات المرتبطة بالصندوق (صرف/قبض/مسترجع/قيود حسابه)"""
        madin, qabd, mustarja = self.get_stage_config(stage_name)
        box_account = self.get_box_account_name(stage_name)
        n = 0
        for inv in self.invoices.values():
            t = inv.get("النوع")
            name = inv.get("الاسم")
            if t in (madin, qabd) or name == mustarja or name == box_account or name == stage_name:
                n += 1
        return n

    def delete_khayas_box_dialog(self):
        """حذف صندوق خياس مضاف، مع كل ما يخصه: حركاته ومسترجعه وحسابه وعمّاله"""
        boxes = self.get_deletable_khayas_boxes()
        if not boxes:
            messagebox.showinfo(
                "لا يوجد",
                "لا توجد صناديق خياس مضافة يمكن حذفها.\n\n"
                "الصناديق الأساسية (الكاستنج، التلميع، التلميع/البف، خياس الطقوم) "
                "مرتبطة بمنطق النظام ولا يمكن حذفها.")
            return

        win = ctk.CTkToplevel(self)
        win.title("حذف صندوق خياس")
        win.geometry("460x360")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="🗑️ حذف صندوق خياس", font=("Cairo", 18, "bold"),
                     text_color="#e74c3c").pack(pady=(16, 4))
        ctk.CTkLabel(win, text="سيُحذف الصندوق وكل ما يخصه نهائياً", font=("Cairo", 12),
                     text_color="#8b8f95").pack(pady=(0, 12))

        combo = ctk.CTkComboBox(win, values=boxes, font=("Cairo", 15), justify="right",
                                width=280, height=40, state="readonly")
        combo.set(boxes[0])
        combo.pack(pady=6)

        lbl_info = ctk.CTkLabel(win, text="", font=("Cairo", 12, "bold"), text_color="#e67e22",
                                wraplength=400, justify="center")
        lbl_info.pack(pady=10)

        def refresh_info(_=None):
            box = combo.get()
            n = self.count_box_transactions(box)
            lbl_info.configure(
                text=f"الحركات المرتبطة بهذا الصندوق: {n}" if n
                else "لا توجد حركات مرتبطة — الحذف آمن تماماً")

        combo.configure(command=refresh_info)
        refresh_info()

        def do_delete():
            box = combo.get()
            n = self.count_box_transactions(box)
            if not messagebox.askyesno(
                    "تأكيد الحذف النهائي",
                    f"سيتم حذف صندوق ({box}) نهائياً، ومعه:\n\n"
                    f"• {n} حركة مسجّلة (صرف/قبض/مسترجع/قيود)\n"
                    f"• حساب المسترجع الخاص به\n"
                    f"• شاشته في مراحل التصنيع وصناديق الخياس وشاشة الخسائر\n\n"
                    "لا يمكن التراجع عن هذه العملية. هل أنت متأكد؟", parent=win):
                return

            if n > 0 and not messagebox.askyesno(
                    "تحذير أخير",
                    f"هذا الصندوق عليه {n} حركة محاسبية مسجّلة.\n"
                    "حذفها سيغيّر رصيد الخزينة وإجمالي الفواقد.\n\n"
                    "هل تريد المتابعة فعلاً؟", parent=win):
                return

            self.perform_khayas_box_deletion(box)
            win.destroy()

        ctk.CTkButton(win, text="🗑️ حذف نهائياً", font=("Cairo", 15, "bold"), fg_color="#8b0000",
                      hover_color="#a52a2a", width=180, height=42, command=do_delete).pack(pady=8)
        ctk.CTkButton(win, text="إلغاء", font=("Cairo", 13), fg_color="#555555",
                      hover_color="#333333", width=120, height=34, command=win.destroy).pack()

    def perform_khayas_box_deletion(self, stage_name):
        """التنفيذ الفعلي للحذف: الحركات ثم الحسابات ثم إعادة بناء الشاشات"""
        madin, qabd, mustarja = self.get_stage_config(stage_name)
        box_account = self.get_box_account_name(stage_name)

        # ١) حذف كل الحركات المرتبطة
        to_delete = [inv["رقم الفاتورة"] for inv in self.invoices.values()
                     if inv.get("النوع") in (madin, qabd)
                     or inv.get("الاسم") in (mustarja, box_account, stage_name)]
        blocked = 0
        for inv_id in to_delete:
            if not self.delete_invoice_from_db(inv_id):
                blocked += 1

        # ٢) حذف عمّال القسم من شجرة الحسابات
        for worker in list(self.categories.get(stage_name, [])):
            # هنا الحذف الكامل مقصود: المستخدم أكّد على عدد حركات الصندوق
            self.delete_worker_from_db(worker, stage_name, keep_transactions=False)
        self.categories.pop(stage_name, None)

        # ٣) حذف القسم نفسه
        if stage_name in self.categories.get("أقسام_خياس_إضافية", []):
            self.categories["أقسام_خياس_إضافية"].remove(stage_name)
        self.delete_worker_from_db(stage_name, "أقسام_خياس_إضافية")

        # ٤) إزالة إعداداته المحفوظة (لون التلوين مثلاً) حتى لا تتراكم
        try:
            self.set_setting(f"neg_color_{stage_name}", "")
        except Exception:
            pass

        # ٥) إعادة بناء كل الشاشات المرتبطة
        for fn in ("refresh_stage_buttons", "refresh_khayas_category_buttons",
                   "refresh_losses_cards", "refresh_chart_of_accounts"):
            if hasattr(self, fn):
                try:
                    getattr(self, fn)()
                except Exception as e:
                    log_cloud_error(f"تعذّر تحديث {fn} بعد حذف الصندوق", e)

        self.update_period_selector()
        self.recalculate_all()

        msg = f"تم حذف صندوق ({stage_name}) وكل ما يخصه."
        if blocked:
            msg += f"\n\nتنبيه: تعذّر حذف {blocked} حركة (التعديل مقفول من المدير)."
        messagebox.showinfo("تم الحذف", msg)

    def open_add_account_dialog(self):
        # تحديد الفرع المختار حالياً بالشجرة (إن وجد) لمعرفة نوع الحساب المطلوب إضافته
        selected_branch = None
        if hasattr(self, 'coa_tree') and self.coa_tree:
            sel = self.coa_tree.selection()
            if sel:
                item = sel[0]
                tags = self.coa_tree.item(item, "tags")
                if "group" in tags:
                    selected_branch = self.coa_tree.item(item, "text")
                else:
                    parent = self.coa_tree.parent(item)
                    if parent:
                        selected_branch = self.coa_tree.item(parent, "text")

        is_khayas_branch = bool(selected_branch and "صناديق الخياس" in selected_branch)

        win = ctk.CTkToplevel(self)
        win.title("إضافة حساب جديد")
        win.geometry("420x260")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="➕ إضافة حساب جديد", font=("Cairo", 16, "bold"), text_color="#d4af37").pack(pady=(20, 6))
        if selected_branch:
            ctk.CTkLabel(win, text=f"الفرع المحدد: {selected_branch}", font=("Cairo", 12, "bold"), text_color="#aaaaaa").pack(pady=(0, 6))
        if is_khayas_branch:
            ctk.CTkLabel(win, text="سيُضاف كصندوق خياس فعّال بصرف/قبض خاص به\nويظهر في مراحل التصنيع وصناديق الخياس وشاشة الخسائر", font=("Cairo", 11), text_color="#2ecc71").pack(pady=(0, 6))

        ctk.CTkLabel(win, text="اسم الحساب:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(pady=(5, 3))
        entry = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=280, height=38)
        entry.pack(pady=5)
        entry.focus_set()

        lbl_status = ctk.CTkLabel(win, text="", font=("Cairo", 12, "bold"), text_color="#e74c3c")
        lbl_status.pack(pady=3)

        def do_add():
            name = entry.get().strip()
            if not name:
                lbl_status.configure(text="الرجاء إدخال اسم الحساب.")
                return
            all_existing = self.get_account_statement_options()
            if name in all_existing:
                lbl_status.configure(text="هذا الاسم موجود مسبقاً كحساب بالنظام.")
                return

            if is_khayas_branch:
                self.categories.setdefault("أقسام_خياس_إضافية", []).append(name)
                self.save_name_to_db(name, "أقسام_خياس_إضافية")
                self.categories.setdefault(name, [])
                # إعادة بناء كل الشاشات المرتبطة لتضمين القسم الجديد فوراً
                if hasattr(self, 'refresh_stage_buttons'):
                    self.refresh_stage_buttons()
                if hasattr(self, 'refresh_khayas_category_buttons'):
                    self.refresh_khayas_category_buttons()
                if hasattr(self, 'refresh_losses_cards'):
                    self.refresh_losses_cards()
            else:
                self.categories.setdefault("حسابات إضافية", []).append(name)
                self.save_name_to_db(name, "حسابات إضافية")

            self.refresh_chart_of_accounts()
            if hasattr(self, 'refresh_journal_entries_table'):
                self.refresh_journal_entries_table()
            self.recalculate_all()
            extra_msg = "\nصار بإمكانك تسجيل صرف/قبض له من شاشة مراحل التصنيع." if is_khayas_branch else ""
            messagebox.showinfo("تم", f"تمت إضافة الحساب ({name}) بنجاح.{extra_msg}")
            win.destroy()

        entry.bind("<Return>", lambda e: do_add())
        ctk.CTkButton(win, text="✅ إضافة", font=("Cairo", 14, "bold"), fg_color="#1e8449", hover_color="#145a32", width=150, height=40, command=do_add).pack(pady=15)

    def refresh_chart_of_accounts(self):
        if not hasattr(self, 'coa_tree') or not self.coa_tree:
            return
        for item in self.coa_tree.get_children():
            self.coa_tree.delete(item)

        def add_group(label):
            return self.coa_tree.insert("", "end", text=label, open=True, tags=("group",))

        def add_leaf(parent, label):
            self.coa_tree.insert(parent, "end", text=label, tags=("leaf",))

        # حساب الخزينة
        g_treasury = add_group("💰 حساب الخزينة")
        add_leaf(g_treasury, "حساب الخزينة")

        # حسابات المواد
        g_materials = add_group("📦 حسابات المواد")
        for acc in ["حساب الذهب", "حساب الألماس", "حساب فصوص وأحجار"]:
            add_leaf(g_materials, acc)

        # صناديق الخياس
        g_khayas = add_group("🏗️ صناديق الخياس")
        for cat in self.get_all_stage_categories() + ["المصنعين", "المركبين"]:
            add_leaf(g_khayas, self.get_box_account_name(cat))

        # حساب الخسائر
        g_losses = add_group("📉 حساب الخسائر")
        add_leaf(g_losses, "حساب الخسائر")

        # المبيعات
        g_sales = add_group("🧾 المبيعات")
        add_leaf(g_sales, "المبيعات")

        # حسابات المسترجع
        g_mustarja = add_group("↩️ حسابات المسترجع")
        for acc in self.get_all_mustarja_names():
            add_leaf(g_mustarja, acc)

        # حسابات الموردين
        g_suppliers = add_group("👥 حسابات الموردين")
        for acc in sorted(self.categories.get("الموردين", [])):
            add_leaf(g_suppliers, acc)

        # حسابات أُضيفت يدوياً من شجرة الحسابات
        manual_accounts = sorted(self.categories.get("حسابات إضافية", []))
        if manual_accounts:
            g_manual = add_group("➕ حسابات مُضافة يدوياً")
            for acc in manual_accounts:
                add_leaf(g_manual, acc)

        # حسابات أخرى (أي اسم جديد استُخدم بقيد يومي وليس ضمن ما سبق)
        known_names = set()
        for cat in self.get_all_stage_categories() + ["المصنعين", "المركبين"]:
            known_names.add(self.get_box_account_name(cat))
        known_names |= {"حساب الخزينة", "حساب الذهب", "حساب الألماس", "حساب فصوص وأحجار",
                         "حساب الخسائر", "المبيعات"} | set(self.get_all_mustarja_names())
        known_names |= set(self.categories.get("الموردين", []))
        known_names |= set(manual_accounts)

        extra_names = set()
        for inv in self.invoices.values():
            if inv.get("settled_status") != "ACTIVE": continue
            if inv.get("النوع") in ("قيد يومي مدين", "قيد يومي دائن"):
                nm = inv.get("الاسم", "")
                if nm and nm not in known_names:
                    extra_names.add(nm)
        if extra_names:
            g_other = add_group("🔹 حسابات أخرى (من القيود اليومية)")
            for acc in sorted(extra_names):
                add_leaf(g_other, acc)

    def on_coa_double_click(self, event=None):
        if not (hasattr(self, 'coa_tree') and self.coa_tree):
            return
        sel = self.coa_tree.selection()
        if not sel:
            return
        item = sel[0]
        if "leaf" not in self.coa_tree.item(item, "tags"):
            return
        account_name = self.coa_tree.item(item, "text")
        self.navigate_to_screen("كشف حساب")
        if hasattr(self, 'kh_account_name'):
            self.kh_account_name.set(account_name)
            self.refresh_account_statement()

    # =========================================================================
    # --- أرشيف الفواتير: بحث + عرض + إعادة معاينة/طباعة أي فاتورة مرحّلة سابقاً ---
    # =========================================================================
    def get_all_invoice_groups(self):
        """يرجع كل مجموعات فواتير المبيعات المرحّلة (فاتورة مستقلة لكل رقم تشغيل/تاريخ/اسم) للأرشفة والبحث"""
        sale_types = ["مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس"]
        seen = {}
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            if inv.get("النوع") not in sale_types: continue
            key = (inv.get("set_number", ""), inv.get("التاريخ", ""), inv.get("الاسم", ""))
            inv_no = inv.get("رقم الفاتورة", 0)
            if key not in seen or inv_no < seen[key]["invoice_no"]:
                seen[key] = {"set_number": key[0], "date": key[1], "name": key[2], "invoice_no": inv_no,
                             "manual_no": inv.get("رقم الفاتورة اليدوي", "") or ""}
        return sorted(seen.values(), key=lambda g: (g["date"], g["invoice_no"]), reverse=True)

    def build_invoice_archive_tab(self):
        tab = self.tabview.tab("أرشيف الفواتير")

        ctk.CTkLabel(tab, text="🗂️ أرشيف الفواتير", font=ctk.CTkFont(family="Cairo", size=18, weight="bold"), text_color="#d4af37").pack(pady=(15, 6))

        search_row = ctk.CTkFrame(tab, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=6)

        ctk.CTkLabel(search_row, text="رقم الفاتورة:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.archive_search_invoice = ctk.CTkEntry(search_row, justify="center", font=("Cairo", 14), width=110, height=36)
        self.archive_search_invoice.pack(side="right", padx=5)

        ctk.CTkLabel(search_row, text="اسم العميل:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.archive_search_name = ctk.CTkEntry(search_row, justify="right", font=("Cairo", 14), width=170, height=36)
        self.archive_search_name.pack(side="right", padx=5)

        ctk.CTkLabel(search_row, text="التاريخ:", font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(side="right", padx=5)
        self.archive_search_date = ctk.CTkEntry(search_row, placeholder_text="YYYY-MM-DD", justify="center", font=("Cairo", 14), width=130, height=36)
        self.archive_search_date.pack(side="right", padx=5)

        ctk.CTkButton(search_row, text="بحث 🔍", font=("Cairo", 14, "bold"), fg_color="#1e8449", hover_color="#145a32", width=100, height=36, command=self.refresh_invoice_archive_table).pack(side="right", padx=10)
        ctk.CTkButton(search_row, text="عرض الكل ↺", font=("Cairo", 14, "bold"), fg_color="#555555", hover_color="#333333", width=100, height=36, command=self.clear_invoice_archive_search).pack(side="right", padx=5)

        self.archive_table_frame = ttk.Frame(tab)
        self.archive_table_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.archive_tree = None
        self.archive_rows_map = {}

        # ====== لوحة إجراءات الفاتورة المحددة ======
        action_bar = ctk.CTkFrame(tab, corner_radius=10, fg_color="#1a1a1a")
        action_bar.pack(fill="x", padx=20, pady=(0, 15))
        self.lbl_archive_selected = ctk.CTkLabel(action_bar, text="اختر فاتورة من الجدول أعلاه لعرض إجراءاتها", font=("Cairo", 13, "bold"), text_color="#aaaaaa")
        self.lbl_archive_selected.pack(side="right", padx=15, pady=12)

        ctk.CTkButton(action_bar, text="إغلاق ✖️", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=110, height=38, command=lambda: self.navigate_to_screen("أرشيف الفواتير")).pack(side="left", padx=8, pady=10)
        ctk.CTkButton(action_bar, text="🖨️ طباعة الفاتورة", font=("Cairo", 13, "bold"), fg_color="#144d75", hover_color="#0d3350", width=150, height=38, command=self.print_selected_archive_invoice).pack(side="left", padx=8, pady=10)
        ctk.CTkButton(action_bar, text="👁️ معاينة الفاتورة", font=("Cairo", 13, "bold"), fg_color="#1f77b4", hover_color="#144d75", width=150, height=38, command=self.preview_selected_archive_invoice).pack(side="left", padx=8, pady=10)
        ctk.CTkButton(action_bar, text="🔤 اختبار الخط العربي", font=("Cairo", 13, "bold"), fg_color="#8e44ad", hover_color="#6c3483", width=170, height=38, command=self.generate_arabic_test_pdf).pack(side="left", padx=8, pady=10)

        self.refresh_invoice_archive_table()

    def generate_arabic_test_pdf(self):
        """يولّد صفحة اختبار للتأكد من صحة عرض النص العربي، ويشخّص أي مكتبة أو خط ناقص"""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("غير متاح", "يجب تثبيت مكتبة reportlab أولاً:\npip install reportlab arabic-reshaper python-bidi")
            return
        out_dir = INVOICES_DIR
        out_path = os.path.join(out_dir, "arabic_test.pdf")

        c = pdf_canvas.Canvas(out_path, pagesize=A4)
        PW, PH = A4
        y = [PH - 20 * mm]

        def line(s, size=14, bold=False):
            c.setFont(_ARABIC_FONT_BOLD_NAME if bold else _ARABIC_FONT_NAME, size)
            c.drawRightString(PW - 20 * mm, y[0], ar(s))
            y[0] -= 9 * mm

        line("صفحة اختبار الخط العربي", size=18, bold=True)
        y[0] -= 4 * mm
        line(f"مكتبة arabic-reshaper و python-bidi مثبّتتان: {'نعم' if ARABIC_SHAPING_AVAILABLE else 'لا (يجب التثبيت!)'}")
        line(f"الخط المستخدم حالياً: {_ARABIC_FONT_NAME}")
        line(f"مسار الخط: {_ARABIC_FONT_PATH_USED or 'لم يُعثر على خط عربي على هذا الجهاز'}")
        y[0] -= 4 * mm
        line("نص تجريبي: مصنع جاديت للتصنيع - المملكة العربية السعودية")
        line("اسم العميل: أحمد محمد العتيبي")
        line("التاريخ: 2026-07-20")
        line("الوزن: 12.50 جرام - العيار: 18")
        y[0] -= 4 * mm
        if _ARABIC_FONT_NAME == "Helvetica":
            line("⚠️ لم يُعثر على أي خط يدعم العربية - النص أعلاه سيظهر فارغاً أو غير صحيح", size=12, bold=True)
        if not ARABIC_SHAPING_AVAILABLE:
            line("⚠️ مكتبات التشكيل غير مثبّتة - نفّذ: pip install arabic-reshaper python-bidi", size=12, bold=True)
        if _ARABIC_FONT_NAME != "Helvetica" and ARABIC_SHAPING_AVAILABLE:
            line("✅ كل المتطلبات مكتشَفة - إذا ظل النص أعلاه غير صحيح فالمشكلة بالخط نفسه لا الإعداد", size=12, bold=True)

        c.showPage()
        c.save()
        self._open_file(out_path)

    def clear_invoice_archive_search(self):
        self.archive_search_invoice.delete(0, 'end')
        self.archive_search_name.delete(0, 'end')
        self.archive_search_date.delete(0, 'end')
        self.refresh_invoice_archive_table()

    def refresh_invoice_archive_table(self):
        if not hasattr(self, 'archive_table_frame') or not self.archive_table_frame:
            return
        for widget in self.archive_table_frame.winfo_children():
            widget.destroy()

        cols = ("رقم الفاتورة", "التاريخ", "الاسم", "رقم التشغيل")
        self.archive_tree = self.create_standard_treeview(self.archive_table_frame, cols, height=16)
        for c in cols:
            w = 220 if c == "الاسم" else 160
            self.archive_tree.column(c, width=w, anchor="center")

        groups = self.get_all_invoice_groups()

        inv_filter = self.archive_search_invoice.get().strip() if hasattr(self, 'archive_search_invoice') else ""
        name_filter = self.archive_search_name.get().strip() if hasattr(self, 'archive_search_name') else ""
        date_filter = self.archive_search_date.get().strip() if hasattr(self, 'archive_search_date') else ""

        self.archive_rows_map = {}
        for g in groups:
            disp_no = g.get("manual_no") or g["invoice_no"]
            if inv_filter and inv_filter not in str(disp_no) and inv_filter not in str(g["invoice_no"]): continue
            if name_filter and name_filter not in g["name"]: continue
            if date_filter and not g["date"].startswith(date_filter): continue
            row_id = self.archive_tree.insert("", "end", values=(disp_no, g["date"], g["name"], g["set_number"] or "-"))
            self.archive_rows_map[row_id] = g

        self.archive_tree.bind("<<TreeviewSelect>>", self.on_archive_row_selected)
        self.archive_tree.bind("<Double-1>", lambda e: self.preview_selected_archive_invoice())

    def on_archive_row_selected(self, event=None):
        if not (hasattr(self, 'archive_tree') and self.archive_tree):
            return
        sel = self.archive_tree.selection()
        if not sel:
            return
        g = self.archive_rows_map.get(sel[0])
        if g and hasattr(self, 'lbl_archive_selected'):
            self.lbl_archive_selected.configure(text=f"الفاتورة المحددة: #{g.get('manual_no') or g['invoice_no']} - {g['name']} - {g['date']}")

    def get_selected_archive_group(self):
        if not (hasattr(self, 'archive_tree') and self.archive_tree):
            return None
        sel = self.archive_tree.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء اختيار فاتورة من الجدول أولاً.")
            return None
        return self.archive_rows_map.get(sel[0])

    def preview_selected_archive_invoice(self):
        g = self.get_selected_archive_group()
        if not g:
            return
        batch_set_numbers = self.get_sale_batch_set_numbers(g["date"], g["name"])
        groups = [(sn, g["date"], g["name"]) for sn in batch_set_numbers] if batch_set_numbers else [(g["set_number"], g["date"], g["name"])]
        self.preview_invoice_groups(groups)

    def print_selected_archive_invoice(self):
        g = self.get_selected_archive_group()
        if not g:
            return
        batch_set_numbers = self.get_sale_batch_set_numbers(g["date"], g["name"])
        groups = [(sn, g["date"], g["name"]) for sn in batch_set_numbers] if batch_set_numbers else [(g["set_number"], g["date"], g["name"])]
        self.print_invoice_groups(groups)

    def build_suppliers_tab(self):
        tab = self.tabview.tab("الموردين")

        top_bar = ctk.CTkFrame(tab, fg_color="transparent")
        top_bar.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(top_bar, text="👥 كشف حسابات الموردين", font=ctk.CTkFont(family="Cairo", size=17, weight="bold"), text_color="#d4af37").pack(side="right", padx=10)
        ctk.CTkButton(top_bar, text="➕ إضافة مورد", font=("Cairo", 15, "bold"), fg_color="#1e8449", hover_color="#145a32", width=140, height=38, command=self.add_supplier_dialog).pack(side="left", padx=10)

        self.suppliers_table_frame = ttk.Frame(tab)
        self.suppliers_table_frame.pack(fill="both", expand=True, padx=15, pady=10)
        self.suppliers_tree = None

        self.refresh_suppliers_table()

    def add_supplier_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("إضافة مورد جديد")
        win.geometry("400x200")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="اسم المورد الجديد:", font=("Cairo", 16, "bold")).pack(pady=15)
        ent = ctk.CTkEntry(win, justify="right", width=280, height=38)
        ent.pack(pady=5)

        def save():
            name = ent.get().strip()
            if not name:
                messagebox.showerror("خطأ", "الرجاء إدخال اسم صحيح.", parent=win)
                return
            if not self.check_name_exists(name):
                self.categories["الموردين"].append(name)
                self.save_name_to_db(name, "الموردين")
            if hasattr(self, 'in_supplier'):
                self.in_supplier.configure(values=self.get_supplier_name_values())
            self.refresh_suppliers_table()
            win.destroy()
            messagebox.showinfo("تم", f"تمت إضافة المورد ({name}) بنجاح.")

        ctk.CTkButton(win, text="حفظ 💾", font=("Cairo", 16, "bold"), fg_color="#2ecc71", hover_color="#27ae60", height=40, command=save).pack(pady=15)

    def refresh_suppliers_table(self):
        if not hasattr(self, 'suppliers_table_frame') or not self.suppliers_table_frame:
            return
        for widget in self.suppliers_table_frame.winfo_children():
            widget.destroy()

        cols = ("الاسم", "مدين", "دائن", "الرصيد")
        self.suppliers_tree = self.create_standard_treeview(self.suppliers_table_frame, cols, height=18)
        self.suppliers_tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 14, "bold"))
        for c in cols:
            self.suppliers_tree.column(c, width=220, anchor="center")

        hidden_mustarja = set(self.get_all_mustarja_names())
        names = [n for n in self.get_supplier_name_values() if n not in hidden_mustarja]

        tot_madin = tot_daen = 0.0
        for name in names:
            madin, daen = self.get_supplier_totals(name)
            balance = round(daen - madin, 2)
            tot_madin += madin
            tot_daen += daen
            self.suppliers_tree.insert("", "end", values=(name, f"{madin:.2f}", f"{daen:.2f}", f"{balance:.2f}"))

        if names:
            self.suppliers_tree.insert("", "end", values=("الإجمالي العام", f"{tot_madin:.2f}", f"{tot_daen:.2f}", f"{round(tot_daen - tot_madin, 2):.2f}"), tags=("total_tag",))

    def get_supplier_totals(self, name):
        """مدين = إجمالي (صادر ذهب) القديم + إجمالي المبيعات المسجلة باسم المورد، دائن = إجمالي الوارد المسجل باسمه"""
        in_types = ["وارد ذهب (عيار 18)", "وارد فصوص وأحجار", "وارد الماس"]
        sale_types = ["مبيعات ذهب", "مبيعات ذهب مع الماس", "مبيعات فصوص وأحجار", "مبيعات الماس"]
        madin = daen = 0.0
        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"): continue
            if inv.get("الاسم") != name: continue
            if inv.get("النوع") == "صادر ذهب" or inv.get("النوع") in sale_types:
                madin += inv["الوزن"]
            elif inv.get("النوع") in in_types:
                daen += inv["الوزن"]
        return round(madin, 2), round(daen, 2)

    def edit_inout_record(self, tree):
        if not self.check_edit_permission():
            return
        sel = tree.selection()
        if not sel: return
        inv_id = sel[0]
        if inv_id in ["total_in", "total_out"]: return  
        self.open_edit_invoice_ui(int(inv_id))

    def edit_selected_inout_row(self):
        """تعديل حركة الوارد المحددة من الجدول"""
        if not self.check_edit_permission():
            return
        if not hasattr(self, 'tree_in') or not self.tree_in:
            return
        sel = self.tree_in.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد تعديلها أولاً.")
            return
        inv_id = sel[0]
        if inv_id in ("total_in", "total_out") or not str(inv_id).isdigit():
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للتعديل (قيمة إجمالية وليست عملية مستقلة).")
            return
        self.open_edit_invoice_ui(int(inv_id))

    def delete_selected_inout_row(self):
        """حذف حركة الوارد المحددة، مع حذف قيد (المسترجع) المرتبط بها إن وُجد حفاظاً على توازن القيود"""
        if not hasattr(self, 'tree_in') or not self.tree_in:
            return
        sel = self.tree_in.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد الحركة المراد حذفها أولاً.")
            return
        raw_id = sel[0]
        if raw_id in ("total_in", "total_out") or not str(raw_id).isdigit():
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للحذف (قيمة إجمالية وليست عملية مستقلة).")
            return
        inv_id = int(raw_id)
        inv = self.invoices.get(inv_id)
        if not inv:
            return

        # القيد المزدوج المرتبط بعملية استرجاع صندوق خياس (إن وُجد) يُحذف معها حتى لا يبقى قيد معلّق بلا أصل
        linked_ref = f"JE-{inv_id + 1}"
        linked_ids = [i["رقم الفاتورة"] for i in self.invoices.values()
                      if i.get("set_number") == linked_ref and (i.get("البيان") or "") == "مسترجع"
                      and str(i.get("النوع", "")).startswith("قيد يومي")]

        msg = f"هل أنت متأكد من حذف حركة الوارد رقم ({inv.get('set_number') or inv_id}) بوزن {inv['الوزن']:.2f} جم؟"
        if linked_ids:
            msg += f"\n\nملاحظة: سيتم أيضاً حذف قيد (المسترجع) المرتبط بها وعدده {len(linked_ids)} قيد، حفاظاً على توازن الحسابات."
        if not messagebox.askyesno("تأكيد الحذف", msg):
            return

        any_blocked = False
        for i in [inv_id] + linked_ids:
            if not self.delete_invoice_from_db(i):
                any_blocked = True
        if any_blocked:
            return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
        self.recalculate_all()
        messagebox.showinfo("تم الحذف", "تم حذف حركة الوارد وتحديث الأرصدة المرتبطة.")

    def preview_selected_inout_row(self):
        """يطبع/يعاين العملية المحددة بجدول الوارد فقط (وليس الكشف الشهري كاملاً)"""
        if not hasattr(self, 'tree_in') or not self.tree_in:
            return
        sel = self.tree_in.selection()
        if not sel:
            messagebox.showwarning("تنبيه", "الرجاء تحديد السطر المراد معاينته أولاً.")
            return
        inv_id = sel[0]
        if inv_id in ("total_in", "total_out") or not str(inv_id).isdigit():
            messagebox.showinfo("تنبيه", "هذا السطر غير قابل للمعاينة (قيمة إجمالية وليست عملية مستقلة).")
            return
        self.print_single_inout_operation(int(inv_id))

    # =====================================================================
    # ---------- البحث الموحّد عن فاتورة مع تحديد الشاشة التي تمت فيها ----------
    # =====================================================================
    SEARCH_SOURCES = ["المبيعات/الصادر", "الوارد/قبض", "القيود اليومية", "الرصيد الافتتاحي", "رقم التشغيل"]

    def find_invoice_records_by_source(self, source, query):
        """يرجع الحركات المطابقة لرقم البحث داخل الشاشة المحددة فقط.
        (أرقام الفواتير قد تتكرر بين الشاشات، لذا تحديد الشاشة ضروري لتفادي الالتباس)"""
        q = (query or "").strip()
        if not q:
            return []
        q_digit = int(q) if q.isdigit() else None
        results = []

        for inv in self.invoices.values():
            if inv.get("settled_status") not in ("ACTIVE", "SETTLED_INOUT"):
                continue
            t = inv.get("النوع", "")
            manual = (inv.get("رقم الفاتورة اليدوي", "") or "").strip()
            voucher = (inv.get("set_number", "") or "").strip()
            inv_id = inv.get("رقم الفاتورة", 0)
            match = False

            if source == "المبيعات/الصادر":
                if t in self.SALE_TYPES or t == "خياس طقوم" or t == "صادر ذهب":
                    match = (manual == q) or (q_digit is not None and inv_id == q_digit)
            elif source == "الوارد/قبض":
                if t.startswith("وارد"):
                    match = (voucher == q) or (q_digit is not None and inv_id == q_digit)
            elif source == "القيود اليومية":
                if t in ("قيد يومي مدين", "قيد يومي دائن"):
                    match = (voucher == q) or (voucher == f"JE-{q}") or (q_digit is not None and inv_id == q_digit)
            elif source == "الرصيد الافتتاحي":
                if inv.get("trees_count") == 1.0 and inv.get("البيان") == "قيد افتتاحي":
                    match = (q_digit is not None and inv_id == q_digit) or (manual == q) or (voucher == q)
            elif source == "رقم التشغيل":
                match = (voucher == q)

            if match:
                results.append(inv)

        results.sort(key=lambda x: (x.get("التاريخ", ""), x.get("رقم الفاتورة", 0)))
        return results

    def search_invoice_window(self):
        query = self.entry_search_inv.get().strip()
        source = self.combo_search_source.get().strip() if hasattr(self, 'combo_search_source') else "المبيعات/الصادر"
        if not query:
            messagebox.showwarning("تنبيه", "الرجاء إدخال رقم الفاتورة في خانة البحث العلوية أولاً.")
            return
        if source not in self.SEARCH_SOURCES:
            source = "المبيعات/الصادر"

        records = self.find_invoice_records_by_source(source, query)
        if not records:
            messagebox.showinfo("لا توجد نتائج",
                                f"لم يتم العثور على أي حركة بالرقم ({query}) داخل شاشة ({source}).\n\n"
                                "تأكد من اختيار الشاشة الصحيحة، فأرقام الفواتير قد تتكرر بين الشاشات.")
            return

        win = ctk.CTkToplevel(self)
        win.title(f"نتائج البحث: {source} - {query}")
        win.geometry("1080x600")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text=f"🔎 نتائج البحث عن الرقم ({query}) في شاشة ({source})",
                     font=("Cairo", 18, "bold"), text_color="#d4af37").pack(pady=(14, 4))
        ctk.CTkLabel(win, text=f"عدد الحركات المطابقة: {len(records)}",
                     font=("Cairo", 13, "bold"), text_color="#1f77b4").pack(pady=(0, 8))

        t_frame = ttk.Frame(win)
        t_frame.pack(fill="both", expand=True, padx=18, pady=8)

        cols = ("رقم الحركة", "التاريخ", "الاسم", "النوع", "الوزن", "رقم التشغيل", "رقم الفاتورة", "البيان")
        tree = self.create_standard_treeview(t_frame, cols, height=12)
        tree.tag_configure("total_tag", foreground="#d4af37", font=("Cairo", 13, "bold"))
        for c in cols:
            w = 175 if c == "التاريخ" else 165 if c in ("الاسم", "النوع", "البيان") else 105
            tree.column(c, width=w, anchor="center")

        total_w = 0.0
        for inv in records:
            total_w = round(total_w + inv.get("الوزن", 0.0), 2)
            tree.insert("", "end", iid=str(inv["رقم الفاتورة"]), values=(
                inv["رقم الفاتورة"], inv.get("التاريخ", ""), inv.get("الاسم", ""), inv.get("النوع", ""),
                f"{inv.get('الوزن', 0.0):.2f}", inv.get("set_number", "") or "-",
                (inv.get("رقم الفاتورة اليدوي", "") or "-"), inv.get("البيان", "") or "-"
            ))
        tree.insert("", "end", iid="total_search", values=(
            "الإجمالي", "-", "-", "-", f"{total_w:.2f}", "-", "-", "-"), tags=("total_tag",))

        def get_sel_id():
            sel = tree.selection()
            if not sel or sel[0] == "total_search":
                messagebox.showwarning("تنبيه", "الرجاء تحديد حركة من الجدول أولاً.", parent=win)
                return None
            return int(sel[0])

        def open_record():
            rid = get_sel_id()
            if rid is not None:
                self.open_edit_invoice_ui(rid)

        def open_full_invoice():
            rid = get_sel_id()
            if rid is None:
                return
            inv = self.invoices.get(rid)
            if not inv:
                return
            t = inv.get("النوع", "")
            if t in self.SALE_TYPES or t == "خياس طقوم":
                key = ((inv.get("رقم الفاتورة اليدوي", "") or ""), inv.get("التاريخ", ""), inv.get("الاسم", ""))
                win.destroy()
                self.open_sale_invoice_editor(key)
            else:
                messagebox.showinfo("تنبيه", "تعديل الفاتورة كاملة متاح لفواتير المبيعات فقط.\nلباقي الشاشات استخدم (فتح الحركة).", parent=win)

        def preview_record():
            rid = get_sel_id()
            if rid is None:
                return
            inv = self.invoices.get(rid)
            if not inv:
                return
            if str(inv.get("النوع", "")).startswith("وارد"):
                self.print_single_inout_operation(rid)
            elif inv.get("set_number"):
                self.preview_invoice_groups([(inv["set_number"], inv["التاريخ"], inv["الاسم"])])
            else:
                messagebox.showinfo("تنبيه", "لا يوجد قالب طباعة مرتبط بهذه الحركة.", parent=win)

        btns = ctk.CTkFrame(win, fg_color="transparent")
        btns.pack(pady=10)
        ctk.CTkButton(btns, text="🔧 فتح الحركة (تعديل/حذف)", font=("Cairo", 14, "bold"), width=200, height=40,
                      fg_color="#b8860b", hover_color="#daa520", command=open_record).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="🧾 تعديل الفاتورة كاملة", font=("Cairo", 14, "bold"), width=190, height=40,
                      fg_color="#1e8449", hover_color="#145a32", command=open_full_invoice).pack(side="right", padx=6)
        ctk.CTkButton(btns, text="🖨️ معاينة الطباعة", font=("Cairo", 14, "bold"), width=170, height=40,
                      fg_color="#1f77b4", hover_color="#144d75", command=preview_record).pack(side="right", padx=6)

        tree.bind("<Double-1>", lambda e: open_record())

    def open_edit_invoice_ui(self, inv_id, is_archived=False, arch_meta=None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT invoice_id, date_time, name, op_type, weight, before_w, after_w, note, settled_status, trees_count, set_number, row_number, manual_no FROM invoices WHERE invoice_id = ?", (inv_id,))
            row = cursor.fetchone()

        if not row: return
        inv = {
            "رقم الفاتورة": row[0], "التاريخ": row[1], "الاسم": row[2], "النوع": row[3],
            "الوزن": row[4], "قبل": row[5], "بعد": row[6], "البيان": row[7], 
            "settled_status": row[8], "trees_count": row[9] if len(row)>9 and row[9] else 0.0,
            "set_number": row[10] if len(row) > 10 and row[10] else "",
            "row_number": row[11] if len(row) > 11 and row[11] else "",
            "رقم الفاتورة اليدوي": row[12] if len(row) > 12 and row[12] else ""
        }

        win = ctk.CTkToplevel(self)
        win.title(f"تعديل الفاتورة رقم: {inv_id}")
        win.geometry("500x480")
        win.attributes("-topmost", True)

        entries_edit = []

        entry_date = ctk.CTkEntry(win, font=("Cairo", 14), justify="center", width=300, height=35)
        entry_date.insert(0, inv["التاريخ"])
        entry_date.pack(pady=10)
        entries_edit.append(entry_date)

        entry_name = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
        entry_name.insert(0, inv["الاسم"])
        entry_name.pack(pady=10)
        if inv_id == 1000: entry_name.configure(state="disabled")
        else: entries_edit.append(entry_name)

        if inv["النوع"] == "خياس الاله/المكائن":
            if "الصب الداخلي" in inv["الاسم"]:
                entry_before = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
                entry_before.insert(0, str(inv["قبل"]))
                entry_before.pack(pady=8)
                entries_edit.append(entry_before)
                
                entry_after = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
                entry_after.insert(0, str(inv["بعد"]))
                entry_after.pack(pady=8)
                entries_edit.append(entry_after)
                
                entry_trees = ctk.CTkEntry(win, placeholder_text="عدد الشجر", font=("Cairo", 14), justify="right", width=300, height=35)
                entry_trees.insert(0, str(inv.get("trees_count", 0.0)))
                entry_trees.pack(pady=8)
                entries_edit.append(entry_trees)
            elif "التلميع النهائي" in inv["الاسم"]:
                entry_weight = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
                entry_weight.insert(0, str(inv["الوزن"]))
                entry_weight.pack(pady=8)
                entries_edit.append(entry_weight)
            else:
                entry_before = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
                entry_before.insert(0, str(inv["قبل"]))
                entry_before.pack(pady=8)
                entries_edit.append(entry_before)
                
                entry_after = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
                entry_after.insert(0, str(inv["بعد"]))
                entry_after.pack(pady=8)
                entries_edit.append(entry_after)
                
        elif inv["النوع"] == "وارد ذهب (عيار 18)":
            entry_before = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
            entry_before.insert(0, str(inv["قبل"]))
            entry_before.pack(pady=8)
            entries_edit.append(entry_before)
            
            entry_after = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
            entry_after.insert(0, str(inv["بعد"]))
            entry_after.pack(pady=8)
            entries_edit.append(entry_after)
        else:
            entry_weight = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
            entry_weight.insert(0, str(inv["الوزن"]))
            entry_weight.pack(pady=8)
            entries_edit.append(entry_weight)

        entry_note = ctk.CTkEntry(win, font=("Cairo", 14), justify="right", width=300, height=35)
        entry_note.insert(0, inv["البيان"])
        entry_note.pack(pady=8)
        entries_edit.append(entry_note)

        def save_changes():
            try:
                new_name = entry_name.get().strip()
                if inv["النوع"] == "خياس الاله/المكائن":
                    if "الصب الداخلي" in new_name:
                        b = round(float(entry_before.get()), 2)
                        a = round(float(entry_after.get()), 2)
                        t = round(float(entry_trees.get()), 2)
                        inv["قبل"] = b; inv["بعد"] = a; inv["الوزن"] = round(b - a, 2)
                        inv["trees_count"] = t
                    elif "التلميع النهائي" in new_name:
                        w = round(float(entry_weight.get()), 2)
                        inv["الوزن"] = w; inv["قبل"] = 0.0; inv["بعد"] = 0.0
                    else:
                        b = round(float(entry_before.get()), 2)
                        a = round(float(entry_after.get()), 2)
                        inv["قبل"] = b; inv["بعد"] = a; inv["الوزن"] = round(b - a, 2)
                elif inv["النوع"] == "وارد ذهب (عيار 18)":
                    raw_w = round(float(entry_before.get()), 2)
                    carat = round(float(entry_after.get()), 2)
                    inv["قبل"] = raw_w; inv["بعد"] = carat; inv["الوزن"] = round((raw_w * carat) / 18.0, 2)
                else:
                    new_w = round(float(entry_weight.get()), 2)
                    inv["الوزن"] = new_w

                inv["التاريخ"] = entry_date.get().strip()
                inv["الاسم"] = new_name
                inv["البيان"] = entry_note.get().strip()
                
                saved_ok = self.save_invoice_to_db(inv_id, inv)
                if not saved_ok:
                    return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل) — لا تحدّث أي حاجة ولا تقفل النافذة
                if inv_id in self.invoices: self.invoices[inv_id] = inv
                
                if is_archived or inv.get("settled_status") == "SETTLED" or inv.get("settled_status") == "SETTLED_INOUT":
                    self.sync_all_archives()
                    
                self.update_period_selector()
                self.recalculate_all()
                messagebox.showinfo("نجاح", "تم التحديث وإعادة حساب الخزينة والأرصدة بنجاح.")
                win.destroy()
            except ValueError:
                messagebox.showerror("خطأ", "تأكد من صحة الأرقام والتاريخ المدخل", parent=win)

        def delete_record():
            if messagebox.askyesno("تأكيد الحذف", "هل أنت متأكد من حذف هذه الحركة نهائياً؟ سيتم تحديث وتعديل جميع الأرصدة المرتبطة بها."):
                deleted_ok = self.delete_invoice_from_db(inv_id)
                if not deleted_ok:
                    return  # تم المنع (رسالة "غير مسموح" ظهرت بالفعل)
                
                if is_archived or inv.get("settled_status") == "SETTLED" or inv.get("settled_status") == "SETTLED_INOUT":
                    self.sync_all_archives()
                    
                self.update_period_selector()
                self.recalculate_all()
                messagebox.showinfo("نجاح", "تم الحذف بنجاح وتحديث الأرصدة المتأثرة.")
                win.destroy()

        # ربط التنقل بالأسهم وإنتر في نافذة التعديل
        for i, ent in enumerate(entries_edit):
            if i < len(entries_edit) - 1:
                ent.bind("<Return>", lambda e, next_w=entries_edit[i+1]: next_w.focus())
                ent.bind("<Down>", lambda e, next_w=entries_edit[i+1]: next_w.focus())
            else:
                ent.bind("<Return>", lambda e: save_changes())
            if i > 0:
                ent.bind("<Up>", lambda e, prev_w=entries_edit[i-1]: prev_w.focus())

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        btn_save_edit = ctk.CTkButton(btn_frame, text="حفظ التعديلات", font=("Cairo", 15, "bold"), height=40, fg_color="green", command=save_changes)
        btn_save_edit.pack(side="right", padx=10)
        ctk.CTkButton(btn_frame, text="حذف الحركة ❌", font=("Cairo", 15, "bold"), height=40, fg_color="#c0392b", hover_color="#922b21", command=delete_record).pack(side="left", padx=10)
        self.apply_edit_lock_to_button(btn_save_edit, win)

class SyncDownWindow(ctk.CTkToplevel):
    """شاشة تجهيز بيانات المصنع: ترفع ما لم يُرفع ثم تسحب نسخة السحابة.

    الترتيب مقصود: الرفع قبل السحب دائماً — لو عمل العميل أسبوعاً بلا إنترنت
    فحركاته المتراكمة تُرفع أولاً، وإلا طمستها نسخة السحابة الأقدم.
    """

    def __init__(self, master, db_path, api, tenant_id, business_name, cloud_only=None):
        super().__init__(master)
        # cloud_only: عند True تُمسح النسخة المحلية قبل السحب فتُعرض بيانات
        # السحابة وحدها. الافتراضي يتبع نوع النسخة (مدير = سحابي بحت).
        self.cloud_only = IS_ADMIN_BUILD if cloud_only is None else cloud_only
        self.db_path = db_path
        self.api = api
        self.tenant_id = tenant_id
        self.ok = False
        self.error = None

        self.title("تجهيز بيانات المصنع")
        apply_app_icon(self)
        self.geometry("480x260")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)   # لا يُغلق أثناء التجهيز

        ctk.CTkLabel(self, text="💎 جاديت", font=("Cairo", 26, "bold"),
                     text_color="#d4af37").pack(pady=(28, 2))
        ctk.CTkLabel(self, text=business_name or "", font=("Cairo", 15, "bold")).pack()

        self.lbl = ctk.CTkLabel(self, text="جارٍ الاتصال بالسحابة…",
                                font=("Cairo", 13), text_color="#d4af37",
                                wraplength=420, justify="center")
        self.lbl.pack(pady=(18, 8))

        self.bar = ctk.CTkProgressBar(self, width=380, height=10, progress_color="#d4af37")
        self.bar.set(0)
        self.bar.pack(pady=6)

        ctk.CTkLabel(self, text="لا تغلق البرنامج أثناء التجهيز",
                     font=("Cairo", 11), text_color="#7f858c").pack(pady=(10, 0))

        threading.Thread(target=self._work, daemon=True).start()

    def _ui(self, fn):
        """كل تحديث للواجهة يمر من هنا — استدعاء Tkinter من خيط آخر يُسقط البرنامج"""
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _progress(self, text, ratio=None):
        def apply():
            self.lbl.configure(text=text)
            if ratio is not None:
                self.bar.set(max(0.0, min(1.0, ratio)))
        self._ui(apply)

    def _work(self):
        try:
            # ═══════════════════════════════════════════════════════════════
            #  اتجاه المزامنة — قاعدة صارمة لا استثناء لها:
            #
            #  نسخة العميل (IS_ADMIN_BUILD = False):
            #      بياناتها المحلية هي مصدر الحقيقة. تُرفع للسحابة فقط،
            #      ولا يُسحب إليها شيء إطلاقاً. سحب السحابة إليها كان يطمس
            #      بياناته ببيانات جهاز المدير — وهي الحادثة التي وقعت.
            #
            #  نسخة المدير (IS_ADMIN_BUILD = True):
            #      مرآة للقراءة فقط: تمسح نسختها المؤقتة وتسحب من السحابة،
            #      ولا ترفع شيئاً أبداً.
            # ═══════════════════════════════════════════════════════════════
            if not IS_ADMIN_BUILD:
                self._progress("جارٍ رفع بياناتك للسحابة…", 0.15)
                install_sync_schema(self.db_path)
                uploader = CloudSync(db_path=self.db_path, api=self.api,
                                     tenant_id=self.tenant_id, app_version=APP_VERSION)
                pending = uploader.pending_count()
                if pending > 0:
                    uploader.flush(max_batches=500)
                self._progress("تم رفع بياناتك ✔", 1.0)
                self.error = None
                self.ok = True
                self._ui(self.destroy)
                return

            # نسخة المدير: نبدأ من قاعدة نظيفة دائماً، فما يُعرض هو أحدث نسخة
            # سحابية للعميل حصراً — لا بقايا من جلسة سابقة على هذا الجهاز
            if self.cloud_only:
                self._progress("جارٍ تجهيز نسخة سحابية نظيفة…", 0.03)
                reset_local_cache(self.db_path)

            install_sync_schema(self.db_path)

            # (١) رفع ما لم يُرفع بعد — يُتخطّى في نسخة المدير لأن قاعدتها
            # مُسحت للتو، فلا يوجد ما يُرفع، ورفع نسخة فارغة قد يطمس بيانات العميل
            uploader = CloudSync(db_path=self.db_path, api=self.api,
                                 tenant_id=self.tenant_id, app_version=APP_VERSION)
            pending = 0 if self.cloud_only else uploader.pending_count()
            if pending > 0:
                self._progress(f"جارٍ رفع {pending} حركة لم تُرفع بعد…", 0.08)
                uploader.flush(max_batches=300)

            # (٢) سحب نسخة السحابة ودمجها محلياً
            sync_down(self.db_path, self.api, self.tenant_id,
                      on_progress=lambda t, r: self._progress(t, r))
            self.ok = True

        except Exception as e:
            # فشل التجهيز لا يمنع العمل: البيانات المحلية سليمة والمزامنة تعيد المحاولة
            self.error = str(e)

        self._ui(self.destroy)


class LoginWindow(ctk.CTk):
    """شاشة الدخول الأولى: تظهر عند أول تشغيل فقط، أو لو حصل تسجيل خروج يدوي"""
    def __init__(self):
        super().__init__()
        self.title("تسجيل الدخول - نظام قسم التصنيع")
        apply_app_icon(self)
        self.geometry("440x400")
        self.resizable(False, False)
        self.eval('tk::PlaceWindow . center')

        ctk.CTkLabel(self, text="🔒 تسجيل الدخول", font=("Cairo", 24, "bold"), text_color="#d4af37").pack(pady=(35, 5))
        ctk.CTkLabel(self, text="نظام قسم التصنيع", font=("Cairo", 14)).pack(pady=(0, 20))

        self.ent_user = ctk.CTkEntry(self, placeholder_text="اسم المستخدم", font=("Cairo", 15), width=270, height=44, justify="center")
        self.ent_user.pack(pady=8)

        self.ent_pass = ctk.CTkEntry(self, placeholder_text="كلمة المرور", show="●", font=("Cairo", 15), width=270, height=44, justify="center")
        self.ent_pass.pack(pady=8)
        # Enter في اسم المستخدم ينقل لكلمة المرور، وفيها يسجّل الدخول مباشرة
        self.ent_user.bind("<Return>", lambda e: (self.ent_pass.focus_set(), "break")[1])
        self.ent_pass.bind("<Return>", lambda e: self.try_login())
        self.ent_user.focus_set()

        self.lbl_status = ctk.CTkLabel(self, text="", font=("Cairo", 13), text_color="#e74c3c")
        self.lbl_status.pack(pady=8)

        self.btn_login = ctk.CTkButton(self, text="دخول", font=("Cairo", 16, "bold"), width=220, height=46,
                                        fg_color="#d4af37", hover_color="#b8952e", text_color="black", command=self.try_login)
        self.btn_login.pack(pady=10)

        if not SUPABASE_AVAILABLE:
            ctk.CTkLabel(self, text="⚠️ مكتبة supabase غير مثبّتة — نفّذ: pip install supabase", font=("Cairo", 11), text_color="#e67e22").pack(pady=(15, 0))

    def try_login(self):
        username = self.ent_user.get().strip()
        password = self.ent_pass.get().strip()
        if not username or not password:
            self.lbl_status.configure(text="من فضلك أدخل اسم المستخدم وكلمة المرور")
            return

        self.btn_login.configure(state="disabled", text="جاري التحقق...")
        self.update_idletasks()

        # لوحة المدير غير متاحة في نسخة العميل — تُدار من لوحة الويب
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            self.btn_login.configure(state="normal", text="دخول")
            self.lbl_status.configure(text="هذه النسخة مخصصة للعملاء فقط")
            return

        if cloud_verify_sub_admin_login(username, password):
            self.destroy()
            panel = AdminPanel(restricted=True)
            panel.mainloop()
            return

        client_id, business_name, can_edit = cloud_verify_client_login(username, password)
        if client_id:
            # تجهيز بيانات المصنع من السحابة قبل فتح النظام
            if SYNC_AVAILABLE and CURRENT_SYNC_TOKEN:
                try:
                    db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")
                    api = _RpcBridge(get_supabase_public_client(), CURRENT_SYNC_TOKEN)
                    win = SyncDownWindow(self, db_path, api, client_id, business_name)
                    self.wait_window(win)
                    if win.error:
                        messagebox.showwarning("تنبيه المزامنة", sync_error_message(win.error))
                except Exception as e:
                    log_cloud_error("تعذّر تجهيز البيانات من السحابة", e)

            self.destroy()
            app = GoldSystemApp(client_id=client_id, client_name=business_name, supabase_client=get_supabase_public_client(), initial_can_edit=can_edit)
            app.mainloop()
        else:
            self.btn_login.configure(state="normal", text="دخول")
            self.lbl_status.configure(text="بيانات الدخول غير صحيحة، أو لا يوجد اتصال بالإنترنت")


class AdminPanel(ctk.CTk):
    """لوحة تحكم المدير: فتح حسابات جديدة للعملاء، وإمكانية الدخول لأي حساب عميل (انتحال شخصية).
    في الوضع المحدود (restricted=True، للمدير المساعد): انتحال شخصية العملاء فقط، بدون فتح حسابات جديدة أو التحكم بصلاحية التعديل."""
    def __init__(self, restricted=False):
        super().__init__()
        self.restricted = restricted
        self.title("لوحة تحكم المدير المساعد - انتحال شخصية العملاء" if restricted else "لوحة تحكم المدير - إدارة حسابات العملاء")
        apply_app_icon(self)
        self.geometry("1000x650")
        try:
            self.state('zoomed')
        except Exception:
            pass

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=15)
        ctk.CTkLabel(top, text="👤 حسابات العملاء", font=("Cairo", 20, "bold")).pack(side="right")
        if not self.restricted:
            ctk.CTkButton(top, text="➕ فتح حساب عميل جديد", font=("Cairo", 14, "bold"), height=42,
                          fg_color="#2ecc71", hover_color="#27ae60", command=self.open_add_client_dialog).pack(side="left", padx=5)
            ctk.CTkButton(top, text="➕ إضافة مدير مساعد", font=("Cairo", 14, "bold"), height=42,
                          fg_color="#1f77b4", command=self.open_add_sub_admin_dialog).pack(side="left", padx=5)
            ctk.CTkButton(top, text="📋 إدارة المدراء المساعدين", font=("Cairo", 14, "bold"), height=42,
                          fg_color="#555555", command=self.open_manage_sub_admins_dialog).pack(side="left", padx=5)
        ctk.CTkButton(top, text="🔄 تحديث القائمة", font=("Cairo", 14, "bold"), height=42,
                      fg_color="#555555", command=self.refresh_clients).pack(side="left", padx=5)

        self.list_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.refresh_clients()

    @staticmethod
    def format_cloud_time(value):
        """يحوّل وقت السحابة (UTC بصيغة ISO) إلى وقت محلي مقروء، مع عدد الدقائق منذ ذلك الوقت"""
        if not value:
            return None, None
        raw = str(value).replace("Z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            local = dt.astimezone()
            mins = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 60.0
            return local.strftime("%Y-%m-%d %H:%M"), mins
        except Exception:
            return str(value)[:16].replace("T", " "), None

    @staticmethod
    def humanize_since(minutes):
        if minutes is None:
            return ""
        if minutes < 2:
            return "الآن"
        if minutes < 60:
            return f"منذ {int(minutes)} دقيقة"
        if minutes < 1440:
            return f"منذ {int(minutes // 60)} ساعة"
        return f"منذ {int(minutes // 1440)} يوم"

    def refresh_clients(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        clients = cloud_list_clients()
        if not clients:
            ctk.CTkLabel(self.list_frame, text="لا يوجد عملاء مسجّلين حالياً، أو تعذر الاتصال بالسحابة", font=("Cairo", 14)).pack(pady=30)
            return
        for c in clients:
            row = ctk.CTkFrame(self.list_frame, fg_color="#2c3e50", corner_radius=10)
            row.pack(fill="x", pady=6, padx=5)
            status = "🟢 نشط" if c.get("is_active") else "🔴 موقوف"
            can_edit = bool(c.get("can_edit"))

            backup_txt, backup_mins = self.format_cloud_time(c.get("last_backup"))
            login_txt, _ = self.format_cloud_time(c.get("last_login"))
            seen_txt, seen_mins = self.format_cloud_time(c.get("last_seen"))

            # حالة الاتصال: العميل يرفع نبضة كل ١٠ ثواني، فالظهور خلال دقيقتين يعني أنه يعمل الآن
            activity_mins = seen_mins if seen_mins is not None else backup_mins
            if activity_mins is None:
                presence = "⚪ لم يدخل النظام بعد"
            elif activity_mins < 2:
                presence = "🟢 متصل الآن"
            else:
                presence = f"⚫ آخر ظهور: {self.humanize_since(activity_mins)}"

            backup_text = f"☁️ آخر نسخة سحابية: {backup_txt}" if backup_txt else "⚠️ لا توجد نسخة احتياطية على السحابة أبداً"
            login_text = f"🔑 آخر دخول: {login_txt}" if login_txt else "🔑 آخر دخول: غير مسجَّل"

            label_text = (f"{c.get('business_name','')}   —   ({c.get('username','')})   {status}\n"
                          f"{login_text}   |   {presence}\n{backup_text}")
            if not self.restricted:
                edit_status = "✏️ التعديل مفتوح" if can_edit else "🔒 التعديل مقفول"
                label_text += f"   |   {edit_status}"
            ctk.CTkLabel(row, text=label_text, font=("Cairo", 14, "bold"), justify="right").pack(side="right", padx=15, pady=10)
            ctk.CTkButton(row, text="فتح الحساب (دخول كالعميل) 🔑", font=("Cairo", 13, "bold"),
                          fg_color="#d4af37", hover_color="#b8952e", text_color="black",
                          command=lambda cid=c["client_id"], name=c["business_name"]: self.open_as_client(cid, name)
                          ).pack(side="left", padx=10, pady=8)
            if not self.restricted:
                toggle_text = "🔒 إغلاق التعديل" if can_edit else "🔓 فتح التعديل"
                toggle_color = "#8b0000" if can_edit else "#2ecc71"
                ctk.CTkButton(row, text=toggle_text, font=("Cairo", 13, "bold"), fg_color=toggle_color,
                              command=lambda cid=c["client_id"], new_val=(not can_edit): self.toggle_client_edit(cid, new_val)
                              ).pack(side="left", padx=10, pady=8)
                ctk.CTkButton(row, text="🗑️ حذف الحساب نهائياً", font=("Cairo", 13, "bold"), fg_color="#8b0000", hover_color="#a52a2a",
                              command=lambda cid=c["client_id"], name=c["business_name"]: self.delete_client(cid, name)
                              ).pack(side="left", padx=10, pady=8)

    def delete_client(self, client_id, business_name):
        if not messagebox.askyesno("⚠️ تأكيد حذف نهائي",
                f"هل أنت متأكد من حذف حساب '{business_name}' نهائياً؟\n\n"
                "سيتم حذف كل بياناته من السحابة (فواتير، أسماء، أرشيف، نسخة احتياطية) بشكل لا رجعة فيه،\n"
                "ولن يقدر يسجّل دخول تاني. البيانات المحلية على جهازه هو مش هتتأثر، لكن مش هيقدر يرفعها للسحابة تاني."):
            return
        if not messagebox.askyesno("تأكيد أخير", f"تأكيد أخير: حذف '{business_name}' نهائياً من كل شيء؟"):
            return
        ok, err = cloud_delete_client(client_id)
        if ok:
            messagebox.showinfo("تم الحذف", f"تم حذف حساب '{business_name}' نهائياً.")
            self.refresh_clients()
        else:
            messagebox.showerror("خطأ", f"تعذر الحذف: {err}")

    def toggle_client_edit(self, client_id, new_value):
        if cloud_set_client_can_edit(client_id, new_value):
            self.refresh_clients()
        else:
            messagebox.showerror("خطأ", "تعذر تغيير الصلاحية. تأكد من الاتصال بالإنترنت.")

    def open_manage_sub_admins_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("إدارة المدراء المساعدين")
        win.geometry("500x450")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="📋 المدراء المساعدون", font=("Cairo", 18, "bold")).pack(pady=15)
        list_frame = ctk.CTkScrollableFrame(win, label_text="")
        list_frame.pack(fill="both", expand=True, padx=15, pady=10)

        def refresh():
            for w in list_frame.winfo_children():
                w.destroy()
            admins = cloud_list_sub_admins()
            if not admins:
                ctk.CTkLabel(list_frame, text="لا يوجد مدراء مساعدون حالياً", font=("Cairo", 13)).pack(pady=20)
                return
            for a in admins:
                row = ctk.CTkFrame(list_frame, fg_color="#2c3e50", corner_radius=8)
                row.pack(fill="x", pady=4, padx=3)
                ctk.CTkLabel(row, text=a.get("username", ""), font=("Cairo", 14, "bold")).pack(side="right", padx=12, pady=10)
                ctk.CTkButton(row, text="🗑️ حذف", font=("Cairo", 12, "bold"), fg_color="#8b0000", hover_color="#a52a2a", width=80,
                              command=lambda aid=a["id"], uname=a["username"]: do_delete(aid, uname)).pack(side="left", padx=10, pady=6)

        def do_delete(admin_id, username):
            if not messagebox.askyesno("تأكيد الحذف", f"هل أنت متأكد من حذف حساب المدير المساعد '{username}'؟", parent=win):
                return
            ok, err = cloud_delete_sub_admin(admin_id)
            if ok:
                refresh()
            else:
                messagebox.showerror("خطأ", f"تعذر الحذف: {err}", parent=win)

        refresh()

    def open_add_sub_admin_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("إضافة مدير مساعد")
        win.geometry("380x320")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="اسم المستخدم:", font=("Cairo", 14, "bold")).pack(pady=(25, 5))
        ent_user = ctk.CTkEntry(win, width=250, height=40, justify="center")
        ent_user.pack()

        ctk.CTkLabel(win, text="كلمة المرور:", font=("Cairo", 14, "bold")).pack(pady=(18, 5))
        ent_pass = ctk.CTkEntry(win, width=250, height=40, justify="center")
        ent_pass.pack()

        ctk.CTkLabel(win, text="ملاحظة: هذا المستخدم هيقدر بس يدخل كأي عميل (انتحال شخصية)،\nمن غير ما يقدر يفتح حسابات جديدة أو يتحكم بصلاحية التعديل.",
                     font=("Cairo", 11), text_color="#aaaaaa", justify="center").pack(pady=12)

        lbl_msg = ctk.CTkLabel(win, text="", font=("Cairo", 12), text_color="#e74c3c")
        lbl_msg.pack(pady=5)

        def do_create():
            user = ent_user.get().strip()
            pw = ent_pass.get().strip()
            if not user or not pw:
                lbl_msg.configure(text="من فضلك املأ كل الحقول")
                return
            ok, err = cloud_create_sub_admin(user, pw)
            if ok:
                messagebox.showinfo("تم", f"تم إنشاء حساب المدير المساعد بنجاح.\nاسم المستخدم: {user}\nكلمة المرور: {pw}")
                win.destroy()
            else:
                lbl_msg.configure(text=f"فشل الإنشاء: {err}")

        ctk.CTkButton(win, text="إنشاء الحساب", font=("Cairo", 15, "bold"), fg_color="#1f77b4",
                      height=44, command=do_create).pack(pady=15)

    def open_add_client_dialog(self):
        win = ctk.CTkToplevel(self)
        win.title("فتح حساب عميل جديد")
        win.geometry("400x420")
        win.transient(self)
        win.grab_set()
        win.focus_force()

        ctk.CTkLabel(win, text="اسم المنشأة/العميل:", font=("Cairo", 14, "bold")).pack(pady=(25, 5))
        ent_name = ctk.CTkEntry(win, width=260, height=40, justify="center")
        ent_name.pack()

        ctk.CTkLabel(win, text="اسم المستخدم:", font=("Cairo", 14, "bold")).pack(pady=(18, 5))
        ent_user = ctk.CTkEntry(win, width=260, height=40, justify="center")
        ent_user.pack()

        ctk.CTkLabel(win, text="كلمة المرور:", font=("Cairo", 14, "bold")).pack(pady=(18, 5))
        ent_pass = ctk.CTkEntry(win, width=260, height=40, justify="center")
        ent_pass.pack()

        lbl_msg = ctk.CTkLabel(win, text="", font=("Cairo", 12), text_color="#e74c3c")
        lbl_msg.pack(pady=8)

        def do_create():
            name = ent_name.get().strip()
            user = ent_user.get().strip()
            pw = ent_pass.get().strip()
            if not name or not user or not pw:
                lbl_msg.configure(text="من فضلك املأ كل الحقول")
                return
            ok, result = cloud_create_client_account(name, user, pw)
            if ok:
                messagebox.showinfo("تم فتح الحساب", f"تم فتح حساب '{name}' بنجاح.\n\nاسم المستخدم: {user}\nكلمة المرور: {pw}\n\nسلّم بيانات الدخول دي للعميل.")
                win.destroy()
                self.refresh_clients()
            else:
                lbl_msg.configure(text=f"فشل الإنشاء: {result}")

        ctk.CTkButton(win, text="فتح الحساب", font=("Cairo", 15, "bold"), fg_color="#2ecc71",
                      hover_color="#27ae60", height=44, command=do_create).pack(pady=25)

    ADMIN_CLOUD_ONLY = True   # نسخة المدير لا تعتمد على بيانات الجهاز المحلية إطلاقاً

    def open_as_client(self, client_id, business_name):
        """انتحال شخصية العميل: يسحب بياناته من السحابة أولاً ثم يفتح نظامه كاملاً.

        بدون السحب كان المدير يرى قاعدة فارغة على جهازه هو، لأن بيانات العميل
        موجودة في السحابة لا على جهاز المدير. وبعد الفتح يبقى محرك المزامنة
        شغّالاً فتصل أي حركة يسجّلها العميل خلال ثوانٍ.

        ملاحظة أمان: هذه الشاشة تستخدم مفتاح الخدمة (secret key) الذي يتجاوز
        فحص رمز المزامنة في السحابة تلقائياً — لذلك لا تفشل هذه الدالة حتى لو
        تعذّرت قراءة الرمز نفسه؛ محاولة قراءته هنا للعرض والتوثيق فقط.
        """
        global CURRENT_SYNC_TOKEN

        sb_admin = get_supabase_admin_client()

        # الإصلاح الذاتي: يضمن وجود ربط صالح لهذا الحساب بغض النظر عن
        # كيف أو متى أُنشئ، بدل الاعتماد على سكربت ترحيل عمل مرة واحدة فقط
        CURRENT_SYNC_TOKEN = None
        try:
            res = sb_admin.rpc("ensure_tenant_link", {"p_client_id": client_id}).execute()
            rows = res.data or []
            if rows:
                CURRENT_SYNC_TOKEN = rows[0].get("out_sync_token")
        except Exception as e:
            log_cloud_error("تعذّر إصلاح ربط مزامنة العميل (سيتابع عبر مفتاح الخدمة)", e)

        self.withdraw()

        # تجهيز بيانات العميل على جهاز المدير قبل فتح النظام.
        # مفتاح الخدمة يعمل حتى بدون رمز مزامنة صريح، فنحاول السحب دائماً
        # طالما وحدات المزامنة متاحة — لا نمنعها فقط لغياب الرمز.
        if SYNC_AVAILABLE:
            try:
                db_path = os.path.join(DATA_DIR, f"client_data_{client_id}.db")

                # نسخة المدير سحابية بحتة: نبدأ من قاعدة نظيفة في كل مرة، فما
                # يُعرض هو أحدث نسخة سحابية للعميل حصراً — لا بقايا من جلسة
                # سابقة على جهاز المدير قد تُظهر أرقاماً قديمة أو محذوفة عند العميل.
                api = _RpcBridge(sb_admin, CURRENT_SYNC_TOKEN)
                prep = ctk.CTkToplevel(self)
                prep.withdraw()
                win = SyncDownWindow(prep, db_path, api, client_id, business_name)
                prep.wait_window(win)
                prep.destroy()
                if win.error:
                    messagebox.showwarning(
                        "تنبيه",
                        f"تعذّر سحب بيانات العميل من السحابة:\n{win.error}\n\n"
                        "سيُفتح النظام بما هو محفوظ على هذا الجهاز.")
            except Exception as e:
                log_cloud_error("تعذّر تجهيز بيانات العميل للمدير", e)

        app = GoldSystemApp(client_id=client_id, client_name=business_name,
                             supabase_client=sb_admin, is_admin_session=True)
        app.mainloop()

        CURRENT_SYNC_TOKEN = None
        self.deiconify()
        self.refresh_clients()


if __name__ == "__main__":
    # تسجيل الدخول مطلوب في كل مرة (لا يُحفظ تلقائياً)
    login = LoginWindow()
    login.mainloop()
# -*- coding: utf-8 -*-
"""
جاديت — المزامنة العكسية: سحب بيانات المصنع من السحابة إلى SQLite المحلية
==========================================================================

قواعد محاسبية صارمة يلتزم بها هذا الملف:

  ١) لا يُمسح شيء أبداً. السحب دمج (upsert) بمفتاح رقم الفاتورة، وليس
     استبدالاً للقاعدة. مسح القاعدة ثم إعادة تعبئتها يُفقد أي عمل لم يُرفع بعد.

  ٢) الرفع قبل السحب دائماً. لو عمل العميل أسبوعاً بلا إنترنت، فحركاته المتراكمة
     تُرفع أولاً ثم يُسحب المدموج — وإلا ضاع عمل الأسبوع.

  ٣) كل مصنع في ملف قاعدة بيانات مستقل باسم tenant_id، فلا تختلط بيانات
     مصنعين لو استُخدم نفس الجهاز لحسابين مختلفين.

  ٤) السحب لا يُعيد رفع ما سُحب: نرفع علم كتم مؤقت فتتوقف محفّزات صندوق
     الصادر، وإلا دخل النظام في حلقة رفع/سحب لا تنتهي.
"""

import os
import sqlite3
from datetime import datetime

PULL_PAGE_SIZE = 1000


# ==============================================================================
#  مسار قاعدة بيانات المصنع
# ==============================================================================

def tenant_db_path(data_dir, tenant_id):
    """لكل مصنع ملفه المستقل — يمنع اختلاط البيانات على الجهاز المشترك."""
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, f"client_data_{tenant_id}.db")


# ==============================================================================
#  كتم صندوق الصادر أثناء السحب
# ==============================================================================

def _set_suppress(con, on):
    con.execute(
        "INSERT INTO sync_state(key, value) VALUES('suppress_outbox', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("1" if on else "0",),
    )
    con.commit()


# ==============================================================================
#  السحب
# ==============================================================================

def sync_down(db_path, api, tenant_id, on_progress=None):
    """يسحب كل بيانات المصنع من السحابة ويدمجها في القاعدة المحلية.

    on_progress: دالة اختيارية (نص, نسبة 0..1) لتحديث شريط التقدّم.
    ترجع قاموساً بالإحصاءات.
    """
    def report(text, ratio=None):
        if on_progress:
            try:
                on_progress(text, ratio)
            except Exception:
                pass

    report("جارٍ قراءة بيانات المصنع من السحابة…", 0.02)

    summary = api.rpc("sync_cloud_summary", {"p_tenant": tenant_id, "p_token": None}) or []
    if isinstance(summary, list):
        summary = summary[0] if summary else {}
    total_rows = int(summary.get("total_rows") or 0)
    accounts_count = int(summary.get("accounts_count") or 0)

    con = sqlite3.connect(db_path, timeout=60)
    stats = {"transactions": 0, "accounts": 0, "settings": 0, "total_cloud": total_rows}

    try:
        _ensure_tables(con)
        # الكتم أولاً: ترحيل عمود الفترة يُجري UPDATE على كل الحركات، ولو جرى
        # قبل الكتم لأطلقت المحفّزات إعادة رفع القاعدة كاملة بلا داعٍ
        _set_suppress(con, True)
        _ensure_period_column(con)

        # ---------- الأسماء أولاً: الحركة قد تشير لاسم يجب أن يكون موجوداً ----------
        report(f"جارٍ سحب الحسابات ({accounts_count})…", 0.06)
        accounts = api.rpc("sync_pull_accounts", {"p_tenant": tenant_id, "p_token": None}) or []
        for a in accounts:
            name = (a.get("name") or "").strip()
            category = (a.get("category") or "").strip()
            if not name:
                continue
            con.execute(
                "INSERT OR IGNORE INTO names(name, category) VALUES(?, ?)", (name, category)
            )
            stats["accounts"] += 1
        con.commit()

        # ---------- إعدادات العميل: نسب الاسترجاع، أسماء الأعمدة، الترتيب… ----------
        # (سحابة لم تُحدَّث بعد لا تعرف الدالة: نكمل بالحركات كما كان)
        try:
            settings = api.rpc("sync_pull_settings", {"p_tenant": tenant_id, "p_token": None}) or []
        except Exception:
            settings = []
        for s in settings:
            key = (s.get("key") or "").strip()
            if not key or key == "invoice_counter":
                continue
            con.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, s.get("value") or ""))
        stats["settings"] = len(settings)
        con.commit()

        # ---------- الحركات على دفعات ----------
        after_seq = 0
        pulled = 0
        while True:
            # p_token يُحقن تلقائياً برمز مزامنة الجلسة عبر جسر الاستدعاء،
            # وبدونه ترفض السحابة السحب بخطأ 28000 لأن برنامج العميل يعمل
            # بمفتاح anon بلا جلسة Supabase Auth
            page = api.rpc("sync_pull_transactions", {
                "p_tenant": tenant_id,
                "p_after_seq": after_seq,
                "p_limit": PULL_PAGE_SIZE,
                "p_token": None,
            }) or []

            if not page:
                break

            rows = [(
                int(r["seq_no"]),
                # التاريخ كما هو على جهاز العميل حرفياً؛ وإلا (حركات قديمة أو من
                # الويب) يُحوَّل من السحابة لتوقيت هذا الجهاز
                r.get("local_date") or _sqlite_dt(r.get("txn_date")),
                r.get("account_name") or "",
                r.get("op_type") or "",
                float(r.get("weight") or 0),
                float(r.get("weight_before") or 0),
                float(r.get("weight_after") or 0),
                r.get("note") or "",
                r.get("status") or "ACTIVE",
                float(r.get("trees_count") or 0),
                r.get("set_number") or "",
                r.get("row_number") or "",
                r.get("manual_no") or "",
                # الفترة كما هي عند العميل — لا تُشتق من التاريخ، وإلا اختلفت
                # الفترات بين شاشة العميل وشاشة المدير
                r.get("period") or _sqlite_dt(r.get("txn_date"))[:7],
            ) for r in page]

            con.executemany("""
                INSERT INTO invoices
                    (invoice_id, date_time, name, op_type, weight, before_w, after_w,
                     note, settled_status, trees_count, set_number, row_number, manual_no, period)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(invoice_id) DO UPDATE SET
                    date_time      = excluded.date_time,
                    name           = excluded.name,
                    op_type        = excluded.op_type,
                    weight         = excluded.weight,
                    before_w       = excluded.before_w,
                    after_w        = excluded.after_w,
                    note           = excluded.note,
                    settled_status = excluded.settled_status,
                    trees_count    = excluded.trees_count,
                    set_number     = excluded.set_number,
                    row_number     = excluded.row_number,
                    manual_no      = excluded.manual_no,
                    period         = excluded.period
            """, rows)
            con.commit()

            pulled += len(page)
            stats["transactions"] = pulled
            after_seq = rows[-1][0]

            ratio = 0.10 + 0.85 * (pulled / total_rows if total_rows else 1)
            report(f"جارٍ سحب الحركات… {pulled} من {total_rows or pulled}", min(ratio, 0.95))

            if len(page) < PULL_PAGE_SIZE:
                break

        report("جارٍ ضبط الترقيم…", 0.97)
        _align_counter(con)

    finally:
        try:
            _set_suppress(con, False)
        finally:
            con.close()

    report("اكتمل تجهيز بيانات المصنع ✅", 1.0)
    return stats


def _ensure_period_column(con):
    """يضيف عمود الفترة للقاعدة المحلية إن غاب، ويملؤه من التواريخ.

    ضروري قبل السحب: بدونه يفشل الإدراج، أو تُشتق الفترة من التاريخ فتختلف
    شاشة المدير عن شاشة العميل.
    """
    cols = [c[1] for c in con.execute("PRAGMA table_info(invoices)")]
    if "period" not in cols:
        con.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")
    con.execute("UPDATE invoices SET period = substr(date_time,1,7) "
                "WHERE period IS NULL OR period = ''")
    con.commit()


def _ensure_tables(con):
    """ينشئ الجداول الأساسية لو كانت القاعدة جديدة تماماً على هذا الجهاز."""
    con.executescript("""
        CREATE TABLE IF NOT EXISTS names (
            name TEXT, category TEXT, UNIQUE(name, category)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        );
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id INTEGER PRIMARY KEY,
            date_time TEXT, name TEXT, op_type TEXT,
            weight REAL, before_w REAL, after_w REAL, note TEXT,
            settled_status TEXT DEFAULT 'ACTIVE',
            trees_count REAL DEFAULT 0,
            set_number TEXT DEFAULT '',
            row_number TEXT DEFAULT '',
            manual_no TEXT DEFAULT '',
            period TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
    """)
    con.commit()


def _align_counter(con):
    """يضبط عدّاد الفواتير بعد السحب.

    بدون هذا قد يبدأ البرنامج ترقيمه من رقم مستخدَم أصلاً في السحابة،
    فتصطدم الحركة الجديدة بحركة قائمة وتُفسد الدفاتر.
    """
    row = con.execute("SELECT COALESCE(MAX(invoice_id), 0) FROM invoices").fetchone()
    max_id = int(row[0] or 0)
    con.execute(
        "INSERT INTO settings(key, value) VALUES('invoice_counter', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(max_id),),
    )
    con.commit()
    return max_id


def _sqlite_dt(iso_text):
    """يحوّل تاريخ السحابة (ISO) لصيغة قاعدة العميل بتوقيت هذا الجهاز: YYYY-MM-DD HH:MM:SS

    برنامج العميل يرفع التاريخ بإزاحة توقيته المحلي (cloud_sync._to_iso)، والسحابة
    تخزّنه لحظةً زمنية وترجعه بتوقيت UTC (مثلاً 20:00+00:00 لحركة سُجّلت 23:00
    بتوقيت الرياض). قصّ الإزاحة بدل التحويل كان يعرض الوقت متأخراً ٣ ساعات،
    ويغيّر اليوم نفسه للحركات المسجّلة بعد منتصف الليل.
    """
    if not iso_text:
        return ""
    text = str(iso_text).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)   # إلى توقيت هذا الجهاز
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    # صيغة غير قياسية: نحتفظ بالسلوك القديم (قصّ الإزاحة والكسور)
    text = text.replace("T", " ")
    for cut in ("+", "Z", "."):
        idx = text.find(cut)
        if idx > 10:
            text = text[:idx]
    return text.strip()[:19]

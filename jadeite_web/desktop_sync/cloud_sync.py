# -*- coding: utf-8 -*-
"""
جاديت — محرك المزامنة السحابية الخلفي (Offline-First Background Sync Engine)
==============================================================================

يُضاف لبرنامج سطح المكتب (CustomTkinter + SQLite) ولا يغيّر شيئاً في واجهته.

⚠️ لا يوجد أي ملف جلسة على القرص. المحرك يعمل بجلسة المستخدم التي أنشأتها
   شاشة الدخول (SupabaseAPI)، وتنتهي بإغلاق البرنامج.

مبادئ التصميم:
  ١) العميل أولاً: كل الكتابة تبقى في SQLite المحلية. لو انقطع الإنترنت شهراً
     كاملاً يستمر البرنامج طبيعياً، وتُرفع كل الحركات المتراكمة عند عودته.
  ٢) لا يلمس الواجهة إطلاقاً: كل العمل في خيط خلفي daemon، ولا يستدعي أي دالة
     من Tkinter (استدعاء Tkinter من خيط آخر يُسقط البرنامج).
  ٣) صفر حزم خارجية: urllib فقط، فلا يكبر ملف exe ولا تتعطل المزامنة بتعارض إصدارات.
  ٤) لا يفقد حركة أبداً: محفّزات SQLite تسجّل كل إضافة/تعديل/حذف في صندوق صادر،
     ولا يُشطب السطر منه إلا بعد تأكيد وصوله للسحابة.
  ٥) idempotent: الرفع بمفتاح (tenant_id, invoice_id)، فإعادة رفع نفس الدفعة
     بعد انقطاع لا تُنشئ تكراراً.

الاستخدام (بعد شاشة الدخول):

    self.cloud_sync = CloudSync(
        db_path=session["db_path"],
        api=session["api"],
        tenant_id=session["tenant_id"],
        app_version="1.34.14",
        on_status=self._on_sync_status,
    )
    self.cloud_sync.start()
"""

import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone

try:
    # تحويل تاريخ السحابة لتوقيت الجهاز — مصدر واحد مع السحب الكامل
    from sync_down import _sqlite_dt
except ImportError:  # pragma: no cover — sync_down يُشحن دائماً مع هذا الملف
    def _sqlite_dt(iso_text):
        text = str(iso_text or "").replace("T", " ")
        return text[:19]

BATCH_SIZE = 200          # عدد الحركات في الدفعة الواحدة
IDLE_INTERVAL = 10        # ثواني بين دورات الفحص عند عدم وجود جديد
BUSY_INTERVAL = 1         # ثواني بين الدفعات عند وجود متراكم
HEARTBEAT_EVERY = 60      # ثواني بين نبضات الحضور
PULL_EVERY = 15           # ثواني بين عمليات سحب تعديلات الويب
MAX_BACKOFF = 300         # أقصى انتظار بعد فشل متكرر (٥ دقائق)


# ==============================================================================
#  ترحيل قاعدة البيانات المحلية: صندوق الصادر + المحفّزات
# ==============================================================================

def install_sync_schema(db_path):
    """يضيف بنية المزامنة لقاعدة المصنع المحلية.

    آمن وقابل لإعادة التشغيل: لا يعدّل أي عمود قائم ولا يمس أي بيانات.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    try:
        cur = con.cursor()

        cur.executescript("""
            CREATE TABLE IF NOT EXISTS names (
                name TEXT, category TEXT, UNIQUE(name, category)
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
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

            CREATE TABLE IF NOT EXISTS sync_outbox (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                entity     TEXT    NOT NULL,      -- invoice | name
                ref_id     TEXT    NOT NULL,
                action     TEXT    NOT NULL,      -- upsert | delete
                queued_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_outbox_entity ON sync_outbox(entity, ref_id);

            CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT);
        """)

        # قواعد قديمة بلا عمود الفترة: يُضاف فارغاً (الخادم يشتقّها من التاريخ عند
        # الرفع). بدونه يفشل أي إدراج يحمل الفترة.
        cols = [c[1] for c in cur.execute("PRAGMA table_info(invoices)")]
        if "period" not in cols:
            cur.execute("ALTER TABLE invoices ADD COLUMN period TEXT DEFAULT ''")

        # المحفّزات تُعاد دائماً لضمان وجود شرط الكتم
        # (بدونه يُعيد البرنامج رفع ما سحبه للتو، فيدخل في حلقة رفع/سحب لا تنتهي)
        cur.executescript("""
            DROP TRIGGER IF EXISTS trg_inv_sync_ins;
            DROP TRIGGER IF EXISTS trg_inv_sync_upd;
            DROP TRIGGER IF EXISTS trg_inv_sync_del;
            DROP TRIGGER IF EXISTS trg_name_sync_ins;
            DROP TRIGGER IF EXISTS trg_name_sync_del;

            CREATE TRIGGER trg_inv_sync_ins AFTER INSERT ON invoices
            WHEN COALESCE((SELECT value FROM sync_state WHERE key='suppress_outbox'), '0') = '0'
            BEGIN
                INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                VALUES('invoice', NEW.invoice_id, 'upsert', datetime('now'));
            END;

            CREATE TRIGGER trg_inv_sync_upd AFTER UPDATE ON invoices
            WHEN COALESCE((SELECT value FROM sync_state WHERE key='suppress_outbox'), '0') = '0'
            BEGIN
                INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                VALUES('invoice', NEW.invoice_id, 'upsert', datetime('now'));
            END;

            CREATE TRIGGER trg_inv_sync_del AFTER DELETE ON invoices
            WHEN COALESCE((SELECT value FROM sync_state WHERE key='suppress_outbox'), '0') = '0'
            BEGIN
                INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                VALUES('invoice', OLD.invoice_id, 'delete', datetime('now'));
            END;

            CREATE TRIGGER trg_name_sync_del AFTER DELETE ON names
            WHEN COALESCE((SELECT value FROM sync_state WHERE key='suppress_outbox'), '0') = '0'
            BEGIN
                INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                VALUES('name', OLD.name || '||' || OLD.category, 'delete', datetime('now'));
            END;

            CREATE TRIGGER trg_name_sync_ins AFTER INSERT ON names
            WHEN COALESCE((SELECT value FROM sync_state WHERE key='suppress_outbox'), '0') = '0'
            BEGIN
                INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                VALUES('name', NEW.name || '||' || NEW.category, 'upsert', datetime('now'));
            END;
        """)

        # أول تشغيل على جهاز فيه بيانات قديمة: نُدرجها كلها للرفع فلا يضيع تاريخ العميل
        if cur.execute("SELECT value FROM sync_state WHERE key='seeded'").fetchone() is None:
            cur.execute("""INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                           SELECT 'invoice', invoice_id, 'upsert', datetime('now') FROM invoices""")
            cur.execute("""INSERT INTO sync_outbox(entity, ref_id, action, queued_at)
                           SELECT 'name', name || '||' || category, 'upsert', datetime('now') FROM names""")
            cur.execute("INSERT INTO sync_state(key, value) VALUES('seeded', datetime('now'))")

        con.commit()
    finally:
        con.close()


# ==============================================================================
#  المحرك
# ==============================================================================

class CloudSync:
    """خيط خلفي يرفع حركات SQLite إلى Supabase ولا يوقف واجهة البرنامج أبداً."""

    def __init__(self, db_path, api, tenant_id, app_version="", on_status=None,
                 on_remote_change=None, pull_enabled=False):
        self.db_path = db_path
        self.api = api
        self.tenant_id = tenant_id
        self.app_version = app_version

        # ⚠️ السحب الدوري معطّل افتراضياً — قاعدة «اتجاه واحد» (RECOVERY_AR.md):
        # بيانات جهاز العميل هي مصدر الحقيقة ولا تكتب السحابة فوقها أبداً.
        # قبل هذا كان المحرك يسحب كل ١٥ ثانية ويكتب في قاعدة العميل رغم القاعدة،
        # ولا يوقفه إلا خطأ برمجي. يُفعَّل فقط صراحةً (pull_enabled=True).
        self.pull_enabled = pull_enabled

        # السحابة القديمة (قبل تحديث SQL) لا تعرف حالة MEMO — نتحوّل تلقائياً
        # لـ SETTLED (لا تُحتسب أيضاً) بدل ACTIVE التي كانت تُدخلها في الأرصدة
        self._memo_supported = True

        # ⚠️ تُستدعى من الخيط الخلفي — لا تلمس Tkinter داخلها مباشرة،
        #    مرّرها عبر root.after(0, ...) كما في دليل الدمج.
        self.on_status = on_status

        # تُستدعى بعد وصول تعديلات من الويب ليحدّث البرنامج شاشاته
        # ⚠️ تُستدعى من الخيط الخلفي — مرّرها عبر after(0, ...)
        self.on_remote_change = on_remote_change

        self.device_id = self._device_id()
        self._thread = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._backoff = 0
        self._pushed_total = 0
        self.last_error = None
        self.last_success_at = None

    # -------------------------------------------------------- معرّف الجهاز
    def _device_id(self):
        """معرّف ثابت للجهاز يُحفظ داخل قاعدة المصنع نفسها (لا ملف خارجي)."""
        try:
            con = sqlite3.connect(self.db_path, timeout=10)
            try:
                con.execute("CREATE TABLE IF NOT EXISTS sync_state (key TEXT PRIMARY KEY, value TEXT)")
                row = con.execute("SELECT value FROM sync_state WHERE key='device_id'").fetchone()
                if row and row[0]:
                    return row[0]
                new_id = str(uuid.uuid4())
                con.execute("INSERT OR REPLACE INTO sync_state(key, value) VALUES('device_id', ?)",
                            (new_id,))
                con.commit()
                return new_id
            finally:
                con.close()
        except Exception:
            return str(uuid.uuid4())

    # ----------------------------------------------------------- دورة الحياة
    def start(self):
        """يبدأ المزامنة في الخلفية. لا يرمي أي استثناء مهما حدث،
        لأن فشل المزامنة يجب ألا يمنع البرنامج من العمل محلياً."""
        try:
            install_sync_schema(self.db_path)
        except Exception as e:
            self.last_error = f"تعذّر تجهيز بنية المزامنة: {e}"
            self._notify()
            return False

        if not (self.api and self.tenant_id):
            self.last_error = "لا توجد جلسة سحابية"
            self._notify()
            return False

        if self._thread and self._thread.is_alive():
            return True

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="JadeiteCloudSync", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout=3):
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def sync_now(self):
        """يوقظ المحرك فوراً بدل انتظار الدورة التالية (بعد ترحيل مهم مثلاً)."""
        self._backoff = 0
        self._wake.set()

    def flush(self, max_batches=100):
        """رفع متزامن لكل المعلّق — تستخدمه شاشة الدخول قبل السحب،
        حتى لا تُطمس حركات العميل غير المرفوعة بنسخة السحابة."""
        pushed = 0
        for _ in range(max_batches):
            if not self._sync_cycle():
                break
            pushed += 1
        return pushed

    # -------------------------------------------------------------- الإحصاء
    def pending_count(self):
        try:
            con = sqlite3.connect(self.db_path, timeout=10)
            try:
                return con.execute("SELECT COUNT(*) FROM sync_outbox").fetchone()[0]
            finally:
                con.close()
        except Exception:
            return 0

    def status_text(self):
        pending = self.pending_count()
        if self.last_error:
            return f"⚠️ {self.last_error}"
        if pending > 0:
            return f"⏳ بانتظار الرفع: {pending} حركة"
        if self.last_success_at:
            return f"☁️ متزامن — آخر رفع {self.last_success_at.strftime('%H:%M:%S')}"
        return "☁️ المزامنة جاهزة"

    def _notify(self):
        if self.on_status:
            try:
                self.on_status(self.status_text())
            except Exception:
                pass

    # --------------------------------------------------------- الحلقة الخلفية
    def _run(self):
        last_heartbeat = 0.0
        last_pull = 0.0

        while not self._stop.is_set():
            try:
                worked = self._sync_cycle()

                now = time.time()

                # سحب تعديلات لوحة الويب — فقط لو فُعّل صراحةً، وبعد الرفع دائماً
                # فلا تُطمس حركة محلية لم تُرفع بعد بنسخة أقدم من السحابة
                if self.pull_enabled and now - last_pull >= PULL_EVERY:
                    last_pull = now
                    if self._pull_changes():
                        worked = True

                if now - last_heartbeat >= HEARTBEAT_EVERY:
                    self._heartbeat()
                    last_heartbeat = now

                self._backoff = 0
                self.last_error = None
                wait = BUSY_INTERVAL if worked else IDLE_INTERVAL

            except Exception as e:
                # أي خطأ (شبكة، صلاحية، خادم) لا يوقف الخيط — نتراجع تدريجياً ونعيد المحاولة
                self.last_error = self._friendly_error(e)
                self._backoff = min(MAX_BACKOFF, max(5, self._backoff * 2 or 5))
                wait = self._backoff

            self._notify()
            self._wake.wait(timeout=wait)
            self._wake.clear()

    def _sync_cycle(self):
        """دورة واحدة: يرفع دفعة واحدة على الأكثر. يرجع True لو كان هناك عمل."""
        did_names = self._sync_names()

        upserts, deletes, row_ids = self._read_batch()
        if not upserts and not deletes:
            return did_names

        if upserts:
            rows = self._load_invoices(upserts)
            if rows:
                self._push_rows(rows)
                self._pushed_total += len(rows)

        if deletes:
            self._rpc("sync_delete_transactions", {
                "p_tenant": self.tenant_id,
                "p_token": None,
                "p_seq_nos": deletes,
            })

        # لا نشطب من الصندوق إلا بعد نجاح الرفع فعلياً
        self._clear_outbox(row_ids)
        self.last_success_at = datetime.now()
        return True

    def _push_rows(self, rows):
        """يرفع دفعة حركات. لو رفضت السحابة حالة MEMO (قاعدة لم تُحدَّث بعد)
        يعيد المحاولة مرة واحدة بحالة SETTLED بدل إسقاط الدفعة كلها."""
        if not self._memo_supported:
            rows = [_downgrade_memo(r) for r in rows]
        payload = {
            "p_tenant": self.tenant_id,
            "p_token": None,
            "p_device": self.device_id,
            "p_rows": rows,
        }
        try:
            self._rpc("sync_push_transactions", payload)
        except Exception as e:
            text = str(e)
            has_memo = any(r.get("status") == "MEMO" for r in rows)
            if has_memo and "txn_status" in text and "MEMO" in text:
                self._memo_supported = False
                payload["p_rows"] = [_downgrade_memo(r) for r in rows]
                self._rpc("sync_push_transactions", payload)
            else:
                raise

    # ---------------------------------------------------------------- السحب
    def _get_state(self, key, default=None):
        try:
            con = sqlite3.connect(self.db_path, timeout=10)
            try:
                row = con.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
                return row[0] if row and row[0] else default
            finally:
                con.close()
        except Exception:
            return default

    def _set_state(self, key, value):
        con = sqlite3.connect(self.db_path, timeout=10)
        try:
            con.execute("INSERT INTO sync_state(key, value) VALUES(?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, str(value)))
            con.commit()
        finally:
            con.close()

    def _pending_seq_nos(self):
        """أرقام الحركات التي ما زالت في صندوق الصادر.

        هذه لم تصل السحابة بعد، فلا يصح أن تكتب نسخة السحابة الأقدم فوقها —
        وإلا ضاع تعديل العميل الذي أجراه للتو.
        """
        con = sqlite3.connect(self.db_path, timeout=10)
        try:
            rows = con.execute(
                "SELECT DISTINCT ref_id FROM sync_outbox WHERE entity='invoice'").fetchall()
        finally:
            con.close()
        out = set()
        for (ref,) in rows:
            try:
                out.add(int(ref))
            except (TypeError, ValueError):
                continue
        return out

    def _pull_changes(self):
        """يسحب تعديلات الويب ويطبّقها محلياً. يرجع True لو وصل جديد."""
        since = self._get_state("last_pull_at")

        result = self._rpc("sync_pull_changes", {
            "p_tenant": self.tenant_id,
            "p_since": since,
            "p_limit": 500,
            "p_token": None,
        })
        if isinstance(result, list):
            result = result[0] if result else None
        if not result:
            return False

        changed = result.get("changed") or []
        deleted = result.get("deleted") or []
        server_time = result.get("server_time")

        applied = 0
        if changed or deleted:
            pending = self._pending_seq_nos()
            con = sqlite3.connect(self.db_path, timeout=30)
            try:
                # كتم صندوق الصادر: ما نطبّقه الآن جاء من السحابة أصلاً،
                # ولو سُجّل في الصندوق لدخلنا في حلقة رفع/سحب لا تنتهي
                con.execute("INSERT INTO sync_state(key, value) VALUES('suppress_outbox','1') "
                            "ON CONFLICT(key) DO UPDATE SET value='1'")
                con.commit()

                rows = []
                for r in changed:
                    try:
                        seq = int(r.get("seq_no"))
                    except (TypeError, ValueError):
                        continue
                    if seq in pending:
                        continue      # تعديل محلي لم يُرفع بعد — له الأولوية
                    rows.append((
                        seq,
                        _sqlite_dt(r.get("txn_date")),
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
                        r.get("period") or str(r.get("txn_date") or "")[:7],
                    ))

                if rows:
                    con.executemany("""
                        INSERT INTO invoices
                            (invoice_id, date_time, name, op_type, weight, before_w, after_w,
                             note, settled_status, trees_count, set_number, row_number, manual_no, period)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(invoice_id) DO UPDATE SET
                            date_time=excluded.date_time, name=excluded.name,
                            op_type=excluded.op_type, weight=excluded.weight,
                            before_w=excluded.before_w, after_w=excluded.after_w,
                            note=excluded.note, settled_status=excluded.settled_status,
                            trees_count=excluded.trees_count, set_number=excluded.set_number,
                            row_number=excluded.row_number, manual_no=excluded.manual_no,
                            period=excluded.period
                    """, rows)
                    applied += len(rows)

                del_list = [int(d) for d in deleted
                            if str(d).lstrip("-").isdigit() and int(d) not in pending]
                if del_list:
                    con.executemany("DELETE FROM invoices WHERE invoice_id = ?",
                                    [(d,) for d in del_list])
                    applied += len(del_list)

                con.commit()
            finally:
                try:
                    con.execute("UPDATE sync_state SET value='0' WHERE key='suppress_outbox'")
                    con.commit()
                finally:
                    con.close()

        # نعتمد وقت الخادم لا وقت الجهاز: ساعة جهاز العميل قد تكون خاطئة
        # فيفوّت تغييرات أو يعيد سحب كل شيء بلا داعٍ
        if server_time:
            self._set_state("last_pull_at", server_time)

        if applied and self.on_remote_change:
            try:
                self.on_remote_change(applied)
            except Exception:
                pass

        return applied > 0

    def _sync_names(self):
        """يرفع الأسماء والأقسام قبل الحركات، حتى لا تصل حركة باسم غير مسجّل."""
        con = sqlite3.connect(self.db_path, timeout=20)
        try:
            rows = con.execute(
                "SELECT id, ref_id, action FROM sync_outbox WHERE entity='name' ORDER BY id LIMIT ?",
                (BATCH_SIZE,)).fetchall()
        finally:
            con.close()

        if not rows:
            return False

        added, removed, row_ids = [], [], []
        for rid, ref, action in rows:
            row_ids.append(rid)
            name, _, category = (ref or "").partition("||")
            if not name.strip():
                continue
            entry = {"name": name, "category": category}
            (removed if action == "delete" else added).append(entry)

        # نفس المعالجة للحسابات: اسم واحد بنفس القسم مرتين يُسبب 21000
        added = list({(a["name"], a["category"]): a for a in added}.values())
        removed = list({(a["name"], a["category"]): a for a in removed}.values())

        if added:
            self._rpc("sync_push_accounts", {
                "p_tenant": self.tenant_id,
                "p_token": None,
                "p_rows": added,
            })

        # الحذف يُرسَل بعد الإضافة: لو أُضيف اسم ثم حُذف في نفس الدفعة،
        # تكون النتيجة النهائية الحذف — مطابقةً لما عند العميل
        if removed:
            self._rpc("sync_delete_accounts", {
                "p_tenant": self.tenant_id,
                "p_token": None,
                "p_rows": removed,
            })

        self._clear_outbox(row_ids)
        return True

    def _read_batch(self):
        """يقرأ دفعة من الصندوق. آخر إجراء لكل سجل هو المعتمد:
        لو أُضيف ثم عُدّل ثم حُذف، فالنتيجة النهائية حذف — نرفع الحذف فقط.

        قاعدة حرجة: `row_ids` المُرجَعة تخص **فقط** السجلات التي ستُرفع فعلاً
        في هذه الدفعة. لو شطبنا من الصندوق أكثر مما رفعنا، تختفي حركات
        من قائمة الانتظار دون أن تصل السحابة — أي فقدان صامت للبيانات.
        """
        con = sqlite3.connect(self.db_path, timeout=20)
        try:
            rows = con.execute(
                "SELECT id, ref_id, action FROM sync_outbox "
                "WHERE entity='invoice' ORDER BY id LIMIT ?",
                (BATCH_SIZE * 3,)).fetchall()
        finally:
            con.close()

        final = {}       # ref_id -> آخر إجراء
        ref_rows = {}    # ref_id -> أرقام سطوره في الصندوق
        for rid, ref_id, action in rows:
            # عند اكتمال حجم الدفعة نترك بقية السجلات للدورة التالية بلا مساس
            if ref_id not in final and len(final) >= BATCH_SIZE:
                continue
            final[ref_id] = action
            ref_rows.setdefault(ref_id, []).append(rid)

        upserts, deletes, row_ids = [], [], []
        for ref_id, action in final.items():
            row_ids.extend(ref_rows[ref_id])
            try:
                seq = int(ref_id)
            except (TypeError, ValueError):
                # سطر تالف: يُشطب حتى لا يعلق الصندوق عليه إلى الأبد
                continue
            (deletes if action == "delete" else upserts).append(seq)

        return upserts, deletes, row_ids

    def _load_invoices(self, seq_nos):
        """يقرأ الحركات من SQLite ويحوّلها لصيغة السحابة."""
        if not seq_nos:
            return []
        con = sqlite3.connect(self.db_path, timeout=20)
        try:
            cols = [c[1] for c in con.execute("PRAGMA table_info(invoices)")]
            placeholders = ",".join("?" * len(seq_nos))
            # الفترة المحاسبية تُرفع كما هي؛ ولو غاب العمود (قاعدة قديمة)
            # تُشتق من التاريخ فتُطابق سلوك النظام السابق
            period_col = ", period" if "period" in cols else ", substr(date_time,1,7)"
            sql = f"""SELECT invoice_id, date_time, name, op_type, weight,
                             before_w, after_w, note, settled_status, trees_count,
                             set_number{', row_number' if 'row_number' in cols else ", ''"}
                             {', manual_no' if 'manual_no' in cols else ", ''"}
                             {period_col}
                        FROM invoices WHERE invoice_id IN ({placeholders})"""
            records = con.execute(sql, seq_nos).fetchall()
        finally:
            con.close()

        payload = [{
            "seq_no": r[0],
            "txn_date": _to_iso(r[1]),
            "account_name": r[2] or "",
            "op_type": r[3] or "",
            "weight": float(r[4] or 0),
            "weight_before": float(r[5] or 0),
            "weight_after": float(r[6] or 0),
            "note": r[7] or "",
            "status": _map_status(r[8]),
            "trees_count": float(r[9] or 0),
            "set_number": r[10] or "",
            "row_number": r[11] or "",
            "manual_no": r[12] or "",
            "period": (r[13] or "") if len(r) > 13 else "",
        } for r in records]

        # إزالة التكرار قبل الإرسال: صندوق الصادر قد يحمل نفس الحركة مرتين
        # (تعديل متتالٍ مثلاً)، والسحابة ترفض تعديل الصف نفسه مرتين في أمر
        # واحد بالخطأ 21000. نُبقي آخر نسخة لكل رقم تسلسل.
        deduped = {}
        for row in payload:
            deduped[row["seq_no"]] = row
        return list(deduped.values())

    def _clear_outbox(self, row_ids):
        if not row_ids:
            return
        con = sqlite3.connect(self.db_path, timeout=20)
        try:
            con.executemany("DELETE FROM sync_outbox WHERE id = ?", [(i,) for i in row_ids])
            con.commit()
        finally:
            con.close()

    def _heartbeat(self):
        self._rpc("sync_heartbeat", {
            "p_tenant": self.tenant_id,
            "p_token": None,
            "p_device": self.device_id,
            "p_name": os.environ.get("COMPUTERNAME", "") or os.environ.get("HOSTNAME", ""),
            "p_version": self.app_version,
            "p_pending": self.pending_count(),
            "p_pushed": self._pushed_total,
            "p_error": self.last_error,
        })

    def _rpc(self, function_name, payload):
        return self.api.rpc(function_name, payload)

    @staticmethod
    def _friendly_error(e):
        text = str(e)
        if "غير مصرّح" in text or "28000" in text:
            return "الجلسة غير مصرّح لها — سجّل الدخول من جديد"
        if "انتهت صلاحية الجلسة" in text or "401" in text:
            return "انتهت صلاحية الجلسة — أعد تشغيل البرنامج"
        if "الاتصال" in text or "الإنترنت" in text or "urlopen" in text:
            return "لا يوجد اتصال بالإنترنت — الحركات محفوظة محلياً"
        if "الخادم" in text or "HTTP 5" in text:
            return "الخادم غير متاح مؤقتاً"
        return text[:120]


# ==============================================================================
#  أدوات مساعدة
# ==============================================================================

def _to_iso(value):
    """يحوّل تاريخ SQLite لصيغة ISO.

    قواعد العملاء فيها صيغ تراكمت عبر النسخ، فنجرّبها بالترتيب ولا نخمّن أبداً:
    لو فشلت كلها نرجع النص كما هو ليرفضه الخادم بوضوح، بدل تسجيل تاريخ خاطئ
    في الدفاتر يفسد الفترة المحاسبية كلها.
    """
    if not value:
        return datetime.now(timezone.utc).isoformat()
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).astimezone().isoformat()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).astimezone().isoformat()
    except ValueError:
        return text


def _map_status(value):
    """حالات البرنامج تُنقل كما هي، وأي حالة غير معروفة تُعامل كنشطة.

    MEMO (السطور المعلوماتية: خياس البوليش/المركب/صافي الطقم) تُنقل بحالتها:
    كانت تُحوَّل إلى ACTIVE فتدخل خطأً في رصيد الخزينة والصناديق عند المدير.
    """
    text = (value or "ACTIVE").strip().upper()
    return text if text in ("ACTIVE", "SETTLED", "SETTLED_INOUT", "MEMO") else "ACTIVE"


def _downgrade_memo(row):
    """للسحابة القديمة فقط: MEMO → SETTLED (كلاهما لا يُحتسب في الأرصدة)."""
    if row.get("status") == "MEMO":
        row = dict(row)
        row["status"] = "SETTLED"
    return row

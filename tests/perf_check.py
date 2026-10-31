"""قياس الأداء مع آلاف الحسابات (اختياري — لا يعمل ضمن الاختبارات العادية).

    python tests/perf_check.py [عدد_الحسابات] [عدد_المستندات]

ينشئ قاعدة مؤقتة منفصلة، يرحّل مستندات حقيقية عبر نفس خدمات الترحيل، ثم يقيس
زمن شاشة الأرصدة (بحث/تصفية/ترتيب) وكشف الحساب وتحليل الحركة وفحص السلامة.
"""
import os
import random
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.db import Database  # noqa: E402
from server.services import accounts, auth, integrity, reports  # noqa: E402
from server.services import documents as docs  # noqa: E402


def main():
    n_acc = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    n_docs = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    tmp = tempfile.mkdtemp(prefix="jadeit-perf-")
    db = Database(os.path.join(tmp, "perf.db"))
    db.conn().execute("PRAGMA synchronous = OFF")  # للتسريع في القياس فقط
    admin = auth.setup_first_admin(db, {"username": "admin", "password": "secret123", "working_karat": 18})
    rnd = random.Random(7)
    t0 = time.perf_counter()
    ids = [accounts.create_account(db, admin, {"name": f"عميل رقم {i}", "wage_rate": str(rnd.randint(2, 9)),
                                                "client_token": f"perfacc{i:08d}"})["id"] for i in range(n_acc)]
    t1 = time.perf_counter()
    for k in range(n_docs):
        aid = rnd.choice(ids)
        if k % 3 == 2:
            docs.post_document(db, admin, {"doc_type": "receipt", "client_token": f"perfdoc{k:09d}", "account_id": aid,
                                           "doc_date": f"2026-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
                                           "material": "gold", "actual": f"{rnd.randint(1, 200)}.{rnd.randint(0, 9999):04d}",
                                           "karat": rnd.choice([18, 21, 22, 24])})
        else:
            lines = [{"run_no": f"{k}-{j}", "gold": f"{rnd.randint(0, 40)}.{rnd.randint(0, 9999):04d}",
                      "diamond": f"{rnd.randint(0, 3)}.{rnd.randint(0, 999):03d}"} for j in range(rnd.randint(1, 6))]
            docs.post_document(db, admin, {"doc_type": "sale", "client_token": f"perfdoc{k:09d}", "account_id": aid,
                                           "doc_date": f"2026-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}", "lines": lines})
    t2 = time.perf_counter()
    with db.read() as c:
        n_entries = c.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]
    print(f"إنشاء {n_acc} حساب: {t1 - t0:.1f} ث — ترحيل {n_docs} مستند ({n_entries} قيد): {t2 - t1:.1f} ث")

    def timed(label, fn, repeat=5):
        best = min((lambda: (time.perf_counter(), fn(), time.perf_counter()))()[::2] for _ in range(repeat))
        ms = (best[1] - best[0]) * 1000
        print(f"  {label}: {ms:.1f} ms")
        return ms

    timed("الأرصدة (الصفحة الأولى، ترتيب برقم الحساب)", lambda: reports.balances(db, {}))
    timed("الأرصدة: الحسابات المدينة بالذهب مرتبة بالرصيد", lambda: reports.balances(db, {"filter": "debit", "material": "gold", "sort": "gold", "dir": "desc"}))
    timed("الأرصدة: بحث بالاسم", lambda: reports.balances(db, {"q": "عميل رقم 12"}))
    busiest = ids[0]
    timed("كشف حساب ذهب لسنة كاملة", lambda: reports.statement(db, {"account_id": busiest, "material": "gold", "date_from": "2026-01-01", "date_to": "2026-12-31"}))
    timed("تحليل حركة العميل", lambda: reports.analysis(db, {"account_id": busiest}))
    timed("فحص سلامة كامل", lambda: integrity.run_check(db, admin), repeat=1)
    res = integrity.run_check(db, admin)
    print("  نتيجة الفحص:", "سليم" if res["ok"] else res["issues"][:3])
    db.close_all()
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

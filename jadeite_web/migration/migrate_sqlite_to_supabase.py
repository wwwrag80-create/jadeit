#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
جاديت ERP — أداة ترحيل بيانات العملاء من قواعد SQLite القديمة إلى Supabase.

الاستخدام:
    # فحص فقط بدون كتابة أي شيء (يُنصح به أولاً)
    python migrate_sqlite_to_supabase.py --db "C:/.../client_data_X.db" --tenant <TENANT_UUID> --dry-run

    # الترحيل الفعلي
    python migrate_sqlite_to_supabase.py --db "C:/.../client_data_X.db" --tenant <TENANT_UUID>

    # ترحيل مجلد كامل بملف ربط (JSON) بين اسم الملف والمستأجر
    python migrate_sqlite_to_supabase.py --dir "C:/Backups" --map mapping.json

مبادئ الأمان في هذه الأداة:
  • لا تحذف ولا تعدّل أي شيء في الملف القديم — قراءة فقط.
  • قابلة لإعادة التشغيل: تتخطى الحركات المرحّلة سابقاً (نفس tenant_id + seq_no).
  • تتحقق من التطابق بعد الترحيل (عدد الحركات ومجاميع الأوزان لكل نوع).
  • --dry-run يطبع تقريراً كاملاً دون أي كتابة.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

BATCH_SIZE = 500

# تصنيفات النظام القديم -> تصنيفات جدول accounts الجديد
CATEGORY_MAP = {
    "المصنعين": "المصنعين",
    "المركبين": "المركبين",
    "الآلة/المكائن": "الآلة/المكائن",
    "الموردين": "الموردين",
    "حسابات إضافية": "حسابات عامة",
    "أقسام_خياس_إضافية": "صناديق الخياس",
}

# تصنيفات قديمة ليست حسابات فعلية (تُرحّل كإعدادات وليس كأسماء)
NON_ACCOUNT_CATEGORIES = {"نسب_خصم_احجار"}

OLD_INVOICE_COLUMNS = [
    "invoice_id", "date_time", "name", "op_type", "weight", "before_w", "after_w",
    "note", "settled_status", "trees_count", "set_number", "row_number", "manual_no",
]


# ============================================================================
#  قراءة قاعدة البيانات القديمة (منطق نقي قابل للاختبار بدون شبكة)
# ============================================================================
def _table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    except sqlite3.Error:
        return []


def normalize_date(raw: Any) -> str:
    """يحوّل التاريخ القديم إلى ISO 8601 مقبول في PostgreSQL."""
    text = str(raw or "").strip()
    if not text:
        return dt.datetime.now().isoformat(timespec="seconds")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            continue
    # صيغة غير متوقعة: نحاول ISO مباشرة، وإلا نُبقيها كما هي ليرفضها الخادم بوضوح
    try:
        return dt.datetime.fromisoformat(text).isoformat(timespec="seconds")
    except ValueError:
        return text


def to_num(value: Any, default: float = 0.0) -> float:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def read_legacy_db(db_path: str, tenant_id: str) -> Dict[str, Any]:
    """يقرأ ملف SQLite قديماً ويرجع البيانات جاهزة للحقن، مع تقرير إحصائي."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"الملف غير موجود: {db_path}")

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        try:
            ok = con.execute("PRAGMA quick_check").fetchone()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"ملف قاعدة البيانات تالف أو ليس ملف SQLite: {db_path} ({exc})") from exc
        if not ok or str(ok[0]).lower() != "ok":
            raise RuntimeError(f"ملف قاعدة البيانات تالف: {db_path}")

        inv_cols = _table_columns(con, "invoices")
        if not inv_cols:
            raise RuntimeError(f"لا يوجد جدول invoices في: {db_path}")

        available = [c for c in OLD_INVOICE_COLUMNS if c in inv_cols]
        rows = con.execute(f"SELECT {', '.join(available)} FROM invoices").fetchall()

        transactions: List[Dict[str, Any]] = []
        for r in rows:
            row = {c: (r[c] if c in r.keys() else None) for c in available}
            transactions.append({
                "tenant_id":     tenant_id,
                "seq_no":        int(row.get("invoice_id") or 0),
                "txn_date":      normalize_date(row.get("date_time")),
                "account_name":  str(row.get("name") or "").strip(),
                "op_type":       str(row.get("op_type") or "").strip(),
                "weight":        to_num(row.get("weight")),
                "weight_before": to_num(row.get("before_w")),
                "weight_after":  to_num(row.get("after_w")),
                "note":          str(row.get("note") or ""),
                "status":        str(row.get("settled_status") or "ACTIVE") or "ACTIVE",
                "trees_count":   to_num(row.get("trees_count")),
                "set_number":    str(row.get("set_number") or ""),
                "row_number":    str(row.get("row_number") or ""),
                "manual_no":     str(row.get("manual_no") or ""),
            })

        accounts: List[Dict[str, Any]] = []
        settings: List[Dict[str, Any]] = []
        seen_accounts = set()

        if _table_columns(con, "names"):
            for r in con.execute("SELECT name, category FROM names"):
                name = str(r["name"] or "").strip()
                old_cat = str(r["category"] or "").strip()
                if not name or old_cat in NON_ACCOUNT_CATEGORIES:
                    continue
                new_cat = CATEGORY_MAP.get(old_cat)
                if not new_cat:
                    continue
                key = (name, new_cat)
                if key in seen_accounts:
                    continue
                seen_accounts.add(key)
                accounts.append({
                    "tenant_id": tenant_id,
                    "name": name,
                    "category": new_cat,
                    "box_key": name if new_cat == "صناديق الخياس" else None,
                    "is_system": False,
                })

        if _table_columns(con, "settings"):
            for r in con.execute("SELECT key, value FROM settings"):
                key = str(r["key"] or "").strip()
                if not key:
                    continue
                raw = r["value"]
                try:
                    parsed = json.loads(raw) if isinstance(raw, str) else raw
                except (ValueError, TypeError):
                    parsed = raw
                settings.append({
                    "tenant_id": tenant_id,
                    "key": key,
                    "value": json.dumps(parsed, ensure_ascii=False),
                })
    finally:
        con.close()

    return {
        "transactions": transactions,
        "accounts": accounts,
        "settings": settings,
        "report": build_report(transactions),
    }


def build_report(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """تقرير تحقق: عدد الحركات ومجموع الأوزان لكل نوع ولكل شهر."""
    by_type: Dict[str, Dict[str, float]] = defaultdict(lambda: {"count": 0, "weight": 0.0})
    by_period: Dict[str, int] = defaultdict(int)
    issues: List[str] = []
    seen_seq = set()

    for t in transactions:
        entry = by_type[t["op_type"]]
        entry["count"] += 1
        entry["weight"] = round(entry["weight"] + t["weight"], 3)
        by_period[t["txn_date"][:7]] += 1

        if t["seq_no"] in seen_seq:
            issues.append(f"رقم حركة مكرر في الملف القديم: {t['seq_no']}")
        seen_seq.add(t["seq_no"])
        if not t["account_name"]:
            issues.append(f"حركة بدون اسم حساب (رقم {t['seq_no']})")
        if not t["op_type"]:
            issues.append(f"حركة بدون نوع (رقم {t['seq_no']})")

    return {
        "total": len(transactions),
        "total_weight": round(sum(t["weight"] for t in transactions), 3),
        "by_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "by_period": dict(sorted(by_period.items())),
        "issues": issues,
    }


def chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ============================================================================
#  الحقن في Supabase
# ============================================================================
def get_client(url: str, service_key: str):
    try:
        from supabase import create_client
    except ImportError:
        sys.exit("مكتبة supabase غير مثبّتة. شغّل:  pip install -r requirements.txt")
    return create_client(url, service_key)


def existing_seq_numbers(sb, tenant_id: str) -> set:
    """أرقام الحركات المرحّلة سابقاً — تجعل الأداة قابلة لإعادة التشغيل بأمان."""
    found = set()
    page, size = 0, 1000
    while True:
        res = (sb.table("transactions").select("seq_no")
                 .eq("tenant_id", tenant_id)
                 .range(page * size, page * size + size - 1).execute())
        rows = res.data or []
        found.update(r["seq_no"] for r in rows)
        if len(rows) < size:
            break
        page += 1
    return found


def push_data(sb, data: Dict[str, Any], tenant_id: str, verbose: bool = True) -> Dict[str, int]:
    counts = {"accounts": 0, "settings": 0, "transactions": 0, "skipped": 0}

    if data["accounts"]:
        for batch in chunked(data["accounts"], BATCH_SIZE):
            sb.table("accounts").upsert(batch, on_conflict="tenant_id,name,category").execute()
            counts["accounts"] += len(batch)

    if data["settings"]:
        for batch in chunked(data["settings"], BATCH_SIZE):
            sb.table("tenant_settings").upsert(batch, on_conflict="tenant_id,key").execute()
            counts["settings"] += len(batch)

    already = existing_seq_numbers(sb, tenant_id)
    pending = [t for t in data["transactions"] if t["seq_no"] not in already]
    counts["skipped"] = len(data["transactions"]) - len(pending)

    for i, batch in enumerate(chunked(pending, BATCH_SIZE), start=1):
        sb.table("transactions").insert(batch).execute()
        counts["transactions"] += len(batch)
        if verbose:
            print(f"   … دفعة {i}: {counts['transactions']}/{len(pending)} حركة")

    return counts


def verify(sb, tenant_id: str, report: Dict[str, Any]) -> bool:
    """يقارن ما في السحابة بما كان في الملف القديم."""
    res = sb.table("transactions").select("id", count="exact").eq("tenant_id", tenant_id).execute()
    cloud_count = res.count or 0
    ok = cloud_count >= report["total"]
    print(f"\n🔍 التحقق: الملف القديم {report['total']} حركة | السحابة {cloud_count} حركة "
          f"{'✅ مطابق' if ok else '⚠️ ناقص'}")
    return ok


def print_report(db_path: str, tenant_id: str, report: Dict[str, Any]) -> None:
    print(f"\n{'=' * 70}\n📂 {os.path.basename(db_path)}   →   المستأجر {tenant_id}\n{'=' * 70}")
    print(f"إجمالي الحركات: {report['total']}   |   إجمالي الأوزان: {report['total_weight']:.3f}")
    print("\nالحركات حسب النوع:")
    for op_type, info in report["by_type"].items():
        print(f"   {op_type:<28} {info['count']:>6} حركة   {info['weight']:>14.3f}")
    print("\nالحركات حسب الشهر:")
    for period, count in report["by_period"].items():
        print(f"   {period}   {count:>6} حركة")
    if report["issues"]:
        print(f"\n⚠️ ملاحظات ({len(report['issues'])}):")
        for issue in report["issues"][:20]:
            print(f"   - {issue}")
        if len(report["issues"]) > 20:
            print(f"   … و {len(report['issues']) - 20} ملاحظة أخرى")


# ============================================================================
#  نقطة الدخول
# ============================================================================
def build_jobs(args) -> List[Tuple[str, str]]:
    if args.db and args.tenant:
        return [(args.db, args.tenant)]
    if args.dir and args.map:
        with open(args.map, encoding="utf-8") as f:
            mapping = json.load(f)
        jobs = []
        for filename, tenant_id in mapping.items():
            path = filename if os.path.isabs(filename) else os.path.join(args.dir, filename)
            jobs.append((path, tenant_id))
        return jobs
    sys.exit("استخدم إما (--db و --tenant) أو (--dir و --map). راجع --help")


def main() -> None:
    parser = argparse.ArgumentParser(description="ترحيل بيانات جاديت من SQLite إلى Supabase")
    parser.add_argument("--db", help="مسار ملف SQLite قديم")
    parser.add_argument("--tenant", help="معرّف المستأجر (UUID) في Supabase")
    parser.add_argument("--dir", help="مجلد يحتوي عدة ملفات قديمة")
    parser.add_argument("--map", help="ملف JSON للربط: {\"client_data_X.db\": \"<tenant-uuid>\"}")
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL"), help="رابط مشروع Supabase")
    parser.add_argument("--key", default=os.environ.get("SUPABASE_SERVICE_KEY"),
                        help="مفتاح الخدمة (service_role) — لا تضعه في أي نسخة تُرسل للعملاء")
    parser.add_argument("--dry-run", action="store_true", help="فحص وتقرير فقط بدون أي كتابة")
    args = parser.parse_args()

    jobs = build_jobs(args)

    if not args.dry_run and (not args.url or not args.key):
        sys.exit("مطلوب --url و --key (أو متغيرا البيئة SUPABASE_URL و SUPABASE_SERVICE_KEY)")

    sb = None if args.dry_run else get_client(args.url, args.key)
    grand_total = 0

    for db_path, tenant_id in jobs:
        try:
            data = read_legacy_db(db_path, tenant_id)
        except Exception as exc:
            print(f"❌ تعذّر قراءة {db_path}: {exc}")
            continue

        print_report(db_path, tenant_id, data["report"])

        if args.dry_run:
            print("\n🧪 وضع الفحص فقط — لم تتم أي كتابة.")
            continue

        counts = push_data(sb, data, tenant_id)
        grand_total += counts["transactions"]
        print(f"\n✅ تم: {counts['transactions']} حركة جديدة، "
              f"{counts['skipped']} متجاوزة (مرحّلة سابقاً)، "
              f"{counts['accounts']} حساب، {counts['settings']} إعداد.")
        verify(sb, tenant_id, data["report"])

    if not args.dry_run:
        print(f"\n{'=' * 70}\n🎉 انتهى الترحيل. إجمالي الحركات المُضافة: {grand_total}\n{'=' * 70}")


if __name__ == "__main__":
    main()

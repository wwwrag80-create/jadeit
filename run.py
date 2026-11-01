#!/usr/bin/env python3
"""تشغيل نظام جاديت لحسابات العملاء.

    python run.py                      ← يعمل على http://127.0.0.1:8080
    python run.py --port 9000          ← منفذ آخر
    python run.py --host 0.0.0.0       ← إتاحته لأجهزة الشبكة المحلية
    python run.py --db data/other.db   ← قاعدة بيانات أخرى

لا يحتاج أي مكتبات خارجية: بايثون 3.7 أو أحدث فقط (يعمل على ويندوز 7 و 10 و 11).
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from server.db import Database  # noqa: E402
from server.app import create_server  # noqa: E402
from server.services.backup import auto_backup  # noqa: E402


def main():
    if sys.version_info < (3, 7):
        sys.exit("Python 3.7+ is required / يتطلب النظام بايثون 3.7 أو أحدث")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # نافذة أوامر ويندوز قد لا تدعم الحروف العربية
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="جاديت — نظام حسابات العملاء")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default=os.path.join(ROOT, "data", "jadeit.db"))
    parser.add_argument("--open", action="store_true", help="فتح المتصفح تلقائياً")
    parser.add_argument("--no-backup", action="store_true", help="تخطي النسخة الاحتياطية التلقائية عند التشغيل")
    args = parser.parse_args()

    if os.path.exists(args.db) and not args.no_backup:
        path = auto_backup(_Probe(args.db))
        if path:
            print(f"نسخة احتياطية تلقائية: {path}")
    db = Database(args.db)
    server = create_server(db, args.host, args.port)
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    print(f"جاديت يعمل الآن على: {url}")
    print(f"قاعدة البيانات: {os.path.abspath(args.db)}")
    print("للإيقاف اضغط Ctrl+C")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف.")
    finally:
        server.server_close()


class _Probe:
    """كائن خفيف يحمل مسار القاعدة فقط لعمل النسخة الاحتياطية قبل فتحها."""

    def __init__(self, path):
        self.path = path


if __name__ == "__main__":
    main()

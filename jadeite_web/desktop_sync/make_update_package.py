# -*- coding: utf-8 -*-
"""
يصنع حزمة التحديث السريع (‎.jup) لبرنامج جاديت — نسخة العميل أو المدير أو كلتيهما.

الحزمة ملف zip صغير (أقل من ميجا) فيه:
  manifest.json : النوع (client/admin)، الإصدار، مستوى exe المطلوب (HOT_RUNTIME)، الملف الرئيسي،
                  بصمة SHA-256 لكل ملف، و«ما الجديد» من RELEASE_NOTES_AR.json
  ملفات البرنامج: الملف الرئيسي + gold_price.py + scale_reader.py + الشعار والأيقونة

برنامج exe (من 1.67.0) يثبّتها من زر «⬆️ تحديث» في ثوانٍ: بايثون والمكتبات والخطوط في exe نفسه،
فلا يلزم إلا ملفات البرنامج. حزمة العميل لا تحمل ملف المدير ولا أي مفتاح سري.

الاستخدام (من داخل مجلد desktop_sync):
    python make_update_package.py client        ← dist/Jadeite-Client-<الإصدار>.jup
    python make_update_package.py admin         ← dist/Jadeite-Admin-<الإصدار>.jup
    python make_update_package.py both
خيارات:  --out <مجلد>      --allow-no-notes (بلا «ما الجديد» لهذا الإصدار)
"""
import argparse
import ast
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

KINDS = {"client": ("rageh-CLIENT.py", "Jadeite-Client"), "admin": ("rageh-1-34-14-cloud.py", "Jadeite-Admin")}
EXTRA_FILES = ("gold_price.py", "scale_reader.py", "jadeite_logo.png", "jadeite.ico")
NOTES_FILE = "RELEASE_NOTES_AR.json"
SECRET_PATTERNS = (
    re.compile(rb"sb_secret_[A-Za-z0-9_-]{8,}"),
    re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]*c2VydmljZV9yb2xl[A-Za-z0-9_-]*\.[A-Za-z0-9_-]{10,}"),
)


class PackageError(Exception):
    pass


def _read(name):
    with open(os.path.join(HERE, name), "rb") as f:
        return f.read()


def source_value(text, name):
    m = re.search(rf'^{name}\s*=\s*"?([\w.]+)"?', text, re.M)
    if not m:
        raise PackageError(f"لم يُعثر على {name} في الملف الرئيسي")
    return m.group(1)


def release_notes(version, allow_missing=False, keep=12):
    """«ما الجديد» لهذا الإصدار وما قبله (الأحدث أولاً) — من RELEASE_NOTES_AR.json"""
    path = os.path.join(HERE, NOTES_FILE)
    notes = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            notes = json.load(f)
    if version not in notes and not allow_missing:
        raise PackageError(f"أضف «ما الجديد» للإصدار {version} في {NOTES_FILE} (أو --allow-no-notes)")
    vt = lambda v: tuple(int(x) for x in v.split("."))
    picked = sorted((v for v in notes if vt(v) <= vt(version)), key=vt, reverse=True)[:keep]
    return {v: notes[v] for v in picked}


def build_package(kind, out_dir=None, allow_missing_notes=False, regenerate_client=True):
    """يصنع الحزمة ويرجع مسارها. يتوقف بـPackageError عند أي خلل (لا حزمة ناقصة أبداً)."""
    if kind not in KINDS:
        raise PackageError(f"نوع غير معروف: {kind}")
    entry, prefix = KINDS[kind]
    if kind == "client" and regenerate_client:
        r = subprocess.run([sys.executable, "make_client_build.py"], cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            raise PackageError("تعذّر توليد نسخة العميل:\n" + (r.stdout + r.stderr)[-800:])
    text = _read(entry).decode("utf-8")
    version = source_value(text, "APP_VERSION")
    runtime = int(source_value(text, "HOT_RUNTIME"))
    if kind == "client":
        if not re.search(r"^IS_ADMIN_BUILD = False", text, re.M) or \
                not re.search(r'^SUPABASE_SECRET_KEY = ""', text, re.M):
            raise PackageError("rageh-CLIENT.py ليس نسخة عميل صحيحة (علم النوع أو المفتاح)")
    elif not re.search(r"^IS_ADMIN_BUILD = True", text, re.M):
        raise PackageError("rageh-1-34-14-cloud.py ليس مضبوطاً كنسخة مدير")
    names = [entry] + list(EXTRA_FILES)
    files, blobs = {}, {}
    for name in names:
        data = _read(name)
        for pat in SECRET_PATTERNS:
            if pat.search(data):
                raise PackageError(f"مفتاح سري داخل {name} — لا تُصنع الحزمة")
        if name.endswith(".py"):
            ast.parse(data.decode("utf-8"), name)
        files[name] = hashlib.sha256(data).hexdigest()
        blobs[name] = data
    manifest = {"format": "jadeite-update", "format_version": 1, "app": "Jadeite", "kind": kind,
                "version": version, "runtime": runtime, "entry": entry, "files": files,
                "notes": release_notes(version, allow_missing_notes),
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    out_dir = out_dir or os.path.join(HERE, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{prefix}-{version}.jup")
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for name in names:
            zf.writestr(name, blobs[name])
    os.replace(tmp, out)
    return out


def main():
    ap = argparse.ArgumentParser(description="حزمة التحديث السريع ‎.jup")
    ap.add_argument("target", choices=("client", "admin", "both"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--allow-no-notes", action="store_true")
    args = ap.parse_args()
    kinds = ("client", "admin") if args.target == "both" else (args.target,)
    try:
        for kind in kinds:
            path = build_package(kind, args.out, args.allow_no_notes)
            with zipfile.ZipFile(path) as zf:
                man = json.loads(zf.read("manifest.json"))
            print(f"✔ {os.path.relpath(path, HERE)}  ({os.path.getsize(path) // 1024} كيلوبايت) — "
                  f"الإصدار {man['version']}، {len(man['files'])} ملفات، مستوى exe {man['runtime']}")
    except PackageError as e:
        print(f"✘ {e}")
        sys.exit(1)
    if "client" in kinds:
        print("   حزمة العملاء: أرسلها لهم — زر «⬆️ تحديث» ← اختيار الحزمة ← تحديث الآن (ثوانٍ).")
    if "admin" in kinds:
        print("   ⚠️ حزمة المدير لك وحدك — لا تسلّمها لأي عميل.")


if __name__ == "__main__":
    main()

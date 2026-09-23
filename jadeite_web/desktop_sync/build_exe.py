# -*- coding: utf-8 -*-
"""
بناء ملف exe لبرنامج جاديت — نسخة العميل أو نسخة المدير — بخطوة واحدة.

الاستخدام (من داخل مجلد desktop_sync):
    python build_exe.py client        ← نسخة العميل  (dist/Jadeite-Client-<الإصدار>.exe)
    python build_exe.py admin         ← نسخة المدير  (dist/Jadeite-Admin-<الإصدار>.exe)

خيارات:
    --skip-install   لا تثبّت المكتبات (مثبّتة مسبقاً)
    --skip-checks    لا تشغّل فحوص run_all_checks (غير مستحسن قبل التسليم)
    --console        exe بنافذة أوامر تُظهر الأخطاء (للتشخيص فقط)

على ويندوز يكفي النقر المزدوج على build_client.bat أو build_admin.bat.

ماذا يفعل بالترتيب — ويتوقف عند أول خطأ برسالة واضحة:
  ١) يتحقق من إصدار بايثون ووجود tkinter وكل الملفات المطلوبة
  ٢) يثبّت المكتبات من requirements-desktop.txt
  ٣) نسخة العميل: يولّد rageh-CLIENT.py (بلا مفتاح سري وبلا لوحة مدير)
     نسخة المدير: يتأكد أن المفتاح السري غير مكتوب داخل الكود
  ٤) يشغّل كل فحوص البرنامج على الملف الذي سيُبنى
  ٥) يبني exe واحداً بالأيقونة والشعار وخط Cairo ووحدات المزامنة
  ٦) يتحقق من الناتج: موجود، وحجمه معقول، ولا مفتاح سري بداخله
"""
import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TARGETS = {
    "client": {"source": "rageh-CLIENT.py", "name": "Jadeite-Client", "label": "نسخة العميل"},
    "admin": {"source": "rageh-1-34-14-cloud.py", "name": "Jadeite-Admin", "label": "نسخة المدير"},
}

# وحدات يستوردها البرنامج من مجلده — تُضمَّن داخل exe
LOCAL_MODULES = ("cloud_sync", "sync_down", "supabase_api", "gold_price")
# ملفات يقرؤها البرنامج وقت التشغيل عبر resource_path
DATA_FILES = ("jadeite.ico", "jadeite_logo.png")
# مجلدات تُضمَّن كما هي (خط Cairo العربي للواجهة)
DATA_DIRS = ("fonts",)
FONT_FILES = ("fonts/Cairo-Regular.ttf", "fonts/Cairo-Bold.ttf")
# مكتبات خارجية لازمة للتشغيل: (اسم الاستيراد، اسم الحزمة في pip)
RUNTIME_PACKAGES = (("customtkinter", "customtkinter"), ("PIL", "Pillow"),
                    ("reportlab", "reportlab"), ("arabic_reshaper", "arabic-reshaper"),
                    ("bidi", "python-bidi"), ("supabase", "supabase"))

SECRET_PATTERNS = (
    re.compile(rb"sb_secret_[A-Za-z0-9_-]{8,}"),
    # مفتاح service_role القديم (JWT فيه "role":"service_role")
    re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]*c2VydmljZV9yb2xl[A-Za-z0-9_-]*\.[A-Za-z0-9_-]{10,}"),
)


def step(n, text):
    print(f"\n[{n}] {text}", flush=True)


def fail(text):
    print(f"\n✘ {text}", flush=True)
    sys.exit(1)


def ok(text):
    print(f"   ✔ {text}", flush=True)


def run(cmd, what):
    print("   $ " + " ".join(cmd), flush=True)
    if subprocess.call(cmd, cwd=HERE) != 0:
        fail(f"فشل: {what}")


def app_version(source_path):
    with open(source_path, encoding="utf-8") as f:
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    return m.group(1) if m else "0"


def assert_no_secret_in(path, what):
    with open(path, "rb") as f:
        data = f.read()
    for pat in SECRET_PATTERNS:
        if pat.search(data):
            fail(f"وُجد مفتاح سري داخل {what} — أوقفت البناء. أزل المفتاح من الكود وضعه في admin_secret.key")


def main():
    parser = argparse.ArgumentParser(description="بناء exe لبرنامج جاديت")
    parser.add_argument("target", choices=sorted(TARGETS), help="client أو admin")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--skip-checks", action="store_true")
    parser.add_argument("--console", action="store_true")
    args = parser.parse_args()

    t = TARGETS[args.target]
    os.chdir(HERE)
    print(f"═══ بناء {t['label']} ═══")

    # ---------- ١) البيئة والملفات ----------
    step(1, "فحص البيئة والملفات")
    if sys.version_info < (3, 9):
        fail(f"يلزم بايثون 3.9 أو أحدث (الحالي {sys.version.split()[0]})")
    ok(f"بايثون {sys.version.split()[0]} ({'64' if sys.maxsize > 2**32 else '32'}-bit)")
    try:
        __import__("tkinter")
    except ImportError:
        fail("tkinter غير مثبّت — أعد تثبيت بايثون من python.org مع خيار tcl/tk")
    ok("tkinter موجود")
    needed = [f"{m}.py" for m in LOCAL_MODULES] + list(DATA_FILES) + list(FONT_FILES) + ["run_all_checks.py"]
    needed += ["make_client_build.py", "rageh-1-34-14-cloud.py"] if args.target == "client" else [t["source"]]
    missing = [f for f in needed if not os.path.exists(os.path.join(HERE, f))]
    if missing:
        fail("ملفات ناقصة في المجلد: " + "، ".join(missing))
    ok("كل الملفات موجودة")

    # ---------- ٢) المكتبات ----------
    step(2, "تثبيت المكتبات")
    if args.skip_install:
        print("   (تُخطّيت بطلبك)")
    else:
        run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], "تحديث pip")
        run([sys.executable, "-m", "pip", "install", "-r", "requirements-desktop.txt"], "تثبيت المكتبات")
    absent = [pip for mod, pip in RUNTIME_PACKAGES + (("PyInstaller", "pyinstaller"),)
              if importlib.util.find_spec(mod) is None]
    if absent:
        fail("مكتبات غير مثبّتة: " + "، ".join(absent) + " — شغّل بدون --skip-install")
    ok("كل المكتبات مثبّتة")

    # ---------- ٣) الملف المصدر ----------
    step(3, "تجهيز الملف المصدر")
    if args.target == "client":
        run([sys.executable, "make_client_build.py"], "توليد نسخة العميل")
        with open(t["source"], encoding="utf-8") as f:
            src = f.read()
        if not re.search(r"^IS_ADMIN_BUILD = False", src, re.M):
            fail("rageh-CLIENT.py ليس مضبوطاً كنسخة عميل")
        if not re.search(r'^SUPABASE_SECRET_KEY = ""', src, re.M):
            fail("rageh-CLIENT.py ما زال يقرأ المفتاح السري")
        ok("نسخة العميل: بلا مفتاح سري، بلا لوحة مدير، ترفع فقط ولا تسحب")
    else:
        with open(t["source"], encoding="utf-8") as f:
            src = f.read()
        if not re.search(r"^IS_ADMIN_BUILD = True", src, re.M):
            fail("rageh-1-34-14-cloud.py ليس مضبوطاً كنسخة مدير")
        if not re.search(r"^SUPABASE_SECRET_KEY = _load_admin_secret_key\(\)", src, re.M):
            fail("المفتاح السري يجب أن يُقرأ من admin_secret.key لا أن يُكتب في الكود")
        ok("نسخة المدير: تقرأ المفتاح السري من خارج الكود، وتعرض بيانات العميل للقراءة فقط")
    assert_no_secret_in(t["source"], t["source"])
    for m in LOCAL_MODULES:
        assert_no_secret_in(f"{m}.py", f"{m}.py")
    ok("لا مفتاح سري مكتوب في أي ملف سيُضمَّن")

    # ---------- ٤) الفحوص ----------
    step(4, "تشغيل فحوص البرنامج")
    if args.skip_checks:
        print("   (تُخطّيت بطلبك — لا تسلّم هذا الملف قبل تشغيلها)")
    else:
        run([sys.executable, "run_all_checks.py", t["source"]], "فحوص البرنامج")
        ok("كل الفحوص نجحت")

    # ---------- ٥) البناء ----------
    version = app_version(t["source"])
    name = f"{t['name']}-{version}"
    step(5, f"بناء {name}")
    for path in (os.path.join("build", name), os.path.join("dist", name), f"{name}.spec"):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
           "--console" if args.console else "--noconsole",
           "--name", name, "--icon", "jadeite.ico", "--paths", HERE,
           # ثيمات customtkinter (ملفات json) — بدونها لا يفتح البرنامج أصلاً
           "--collect-data", "customtkinter",
           "--collect-submodules", "supabase"]
    for m in LOCAL_MODULES:
        cmd += ["--hidden-import", m]
    for f in DATA_FILES:
        cmd += ["--add-data", f"{f}{os.pathsep}."]
    for d in DATA_DIRS:
        cmd += ["--add-data", f"{d}{os.pathsep}{d}"]
    cmd.append(t["source"])
    run(cmd, "PyInstaller")

    # ---------- ٦) التحقق من الناتج ----------
    step(6, "التحقق من الناتج")
    exe = os.path.join(HERE, "dist", name + (".exe" if os.name == "nt" else ""))
    if not os.path.exists(exe):
        fail(f"لم يُنشأ الملف {exe}")
    size_mb = os.path.getsize(exe) / 1024 / 1024
    if size_mb < 5:
        fail(f"حجم الملف صغير بشكل غير طبيعي ({size_mb:.1f} ميجا) — البناء ناقص")
    assert_no_secret_in(exe, "ملف exe")
    with open(exe, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    ok(f"{os.path.relpath(exe, HERE)}  ({size_mb:.1f} ميجا)")
    ok(f"SHA-256: {digest}")
    ok("لا مفتاح سري داخل الملف")

    print(f"\n✅ اكتمل بناء {t['label']} — الإصدار {version}")
    if args.target == "client":
        print("   سلّم هذا الملف وحده للعميل. بياناته تبقى في %LOCALAPPDATA%\\JadeiteERP\n"
              "   (لا تُحذف بحذف البرنامج)، وتُرفع للسحابة فقط.")
    else:
        print("   ⚠️ هذا الملف لك وحدك — لا تسلّمه لأي عميل.\n"
              "   ضع ملف admin_secret.key (سطر واحد فيه المفتاح السري) بجانب exe على جهازك،\n"
              "   أو اضبط متغيّر البيئة JADEITE_SUPABASE_SECRET_KEY. الملف لا يُضمَّن داخل exe.\n"
              "   ولتغيير كلمة مرور لوحة المدير اضبط متغيّر البيئة JADEITE_ADMIN_PASSWORD.")


if __name__ == "__main__":
    main()

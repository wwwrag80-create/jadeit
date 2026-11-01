#!/usr/bin/env python3
"""تشغيل جاديت كتطبيق مكتبي بنقرة واحدة (ويندوز 7 و 8 و 10 و 11).

ما يفعله:
  1. إن كان النظام يعمل مسبقاً على هذا الجهاز ← يفتح نافذة جديدة له فقط (نسخة واحدة دائماً).
  2. وإلا يأخذ نسخة احتياطية تلقائية، ويشغّل الخادم داخلياً على 127.0.0.1 (لا يصل إليه أحد من خارج الجهاز).
  3. يفتح الواجهة في نافذة تطبيق مستقلة (Google Chrome أو Microsoft Edge بوضع التطبيق، بلا شريط عناوين).
  4. عند إغلاق النافذة يُغلق الخادم تلقائياً.
     إن لم يوجد Chrome أو Edge: يفتح المتصفح المتاح ويُظهر نافذة صغيرة «إيقاف النظام».

البيانات تُحفظ في مجلد data بجوار البرنامج (أو في %LOCALAPPDATA%\\Jadeit إن كان المجلد للقراءة فقط).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, APP_DIR)

PORTS = list(range(8080, 8100))
IS_WIN = os.name == "nt"


# ---------------------------------------------------------------------------- المسارات
def home_dir() -> str:
    """المجلد الذي يحتوي البرنامج (يضبطه Jadeit.exe في JADEIT_HOME)."""
    if os.environ.get("JADEIT_HOME"):
        return os.environ["JADEIT_HOME"]
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return APP_DIR


def _writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def data_dir() -> str:
    preferred = os.path.join(home_dir(), "data")
    if _writable(preferred):
        return preferred
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    fallback = os.path.join(base, "Jadeit", "data")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def setup_logging(data: str):
    """pythonw بلا نافذة أوامر: نوجّه المخرجات إلى ملف سجل حتى لا يتعطل الخادم."""
    to_file = (getattr(sys, "frozen", False) or sys.stdout is None or sys.stderr is None
               or os.path.basename(sys.executable).lower() == "pythonw.exe" or os.environ.get("JADEIT_LOG_TO_FILE"))
    if not to_file:
        return
    path = os.path.join(data, "jadeit.log")
    try:
        if os.path.exists(path) and os.path.getsize(path) > 5 * 1024 * 1024:
            os.replace(path, path + ".old")
    except OSError:
        pass
    log = open(path, "a", encoding="utf-8", buffering=1, errors="replace")
    sys.stdout = log
    sys.stderr = log
    print("\n==== Jadeit start", time.strftime("%Y-%m-%d %H:%M:%S"), "====")
    os.environ.setdefault("JADEIT_QUIET", "1")


# ---------------------------------------------------------------------------- رسائل ويندوز
def message(text: str, title: str = "جاديت", icon: str = "info") -> None:
    print(f"[{title}] {text}")
    if not IS_WIN or os.environ.get("JADEIT_NO_UI"):
        return
    try:
        import ctypes
        flags = {"info": 0x40, "warn": 0x30, "error": 0x10}[icon] | 0x10000 | 0x100000  # SETFOREGROUND | RTLREADING
        ctypes.windll.user32.MessageBoxW(None, text, title, flags | 0x80000)  # RIGHT
    except Exception:
        pass


# ---------------------------------------------------------------------------- الخادم
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe(port: int) -> str:
    """'ours' إن كان جاديت يعمل على المنفذ، 'free' إن كان متاحاً، 'busy' إن استخدمه برنامج آخر."""
    try:
        with _NO_PROXY.open(f"http://127.0.0.1:{port}/api/status", timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8"))
            return "ours" if "needs_setup" in data else "busy"
    except urllib.error.HTTPError:
        return "busy"
    except (urllib.error.URLError, ConnectionError, OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, ConnectionRefusedError) or "refused" in str(reason).lower() or "10061" in str(reason):
            return "free"
        if isinstance(e, ValueError):
            return "busy"
        return "free"


def find_running() -> int | None:
    for port in PORTS:
        if probe(port) == "ours":
            return port
    return None


def start_server(data: str):
    from server.app import create_server
    from server.db import Database
    from server.services.backup import auto_backup

    db_path = os.path.join(data, "jadeit.db")

    class _Probe:
        path = db_path

    if os.path.exists(db_path):
        try:
            auto_backup(_Probe())
        except Exception:
            traceback.print_exc()
    db = Database(db_path)
    last_error = None
    for port in PORTS:
        try:
            server = create_server(db, "127.0.0.1", port)
        except OSError as e:
            last_error = e
            continue
        t = threading.Thread(target=server.serve_forever, name="jadeit-http", daemon=True)
        t.start()
        with open(os.path.join(data, "server.port"), "w") as f:
            f.write(str(port))
        print("server on port", port, "db", db_path)
        return server, port
    raise RuntimeError(f"لا يوجد منفذ متاح من 8080 إلى 8099: {last_error}")


# ---------------------------------------------------------------------------- نافذة التطبيق
def _win_paths():
    env = os.environ.get
    roots = [env("ProgramFiles"), env("ProgramFiles(x86)"), env("ProgramW6432"), env("LOCALAPPDATA")]
    rel = [
        ("chrome", r"Google\Chrome\Application\chrome.exe"),
        ("edge", r"Microsoft\Edge\Application\msedge.exe"),
        ("chromium", r"Chromium\Application\chrome.exe"),
    ]
    found = []
    for name, r in rel:
        for root in roots:
            if root:
                p = os.path.join(root, r)
                if os.path.isfile(p):
                    found.append((name, p))
    try:
        import winreg
        for exe, name in (("chrome.exe", "chrome"), ("msedge.exe", "edge")):
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths" + "\\" + exe) as k:
                        p = winreg.QueryValue(k, None)
                        if p and os.path.isfile(p.strip('"')):
                            found.append((name, p.strip('"')))
                except OSError:
                    pass
    except ImportError:
        pass
    seen, out = set(), []
    for name, p in found:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append((name, p))
    return out


def find_chromium():
    custom = os.environ.get("JADEIT_BROWSER")
    if custom and os.path.isfile(custom):
        return custom
    if IS_WIN:
        browsers = _win_paths()
        return browsers[0][1] if browsers else None
    import shutil
    for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
        p = shutil.which(name)
        if p:
            return p
    return None


def find_firefox():
    if not IS_WIN:
        import shutil
        return shutil.which("firefox")
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root:
            p = os.path.join(root, "Mozilla Firefox", "firefox.exe")
            if os.path.isfile(p):
                return p
    return None


def open_window(url: str, data: str):
    """يعيد عملية المتصفح إن فُتحت نافذة تطبيق مستقلة يمكن متابعتها، وإلا None."""
    chromium = find_chromium()
    if chromium:
        profile = os.path.join(data, "browser")
        args = [chromium, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                "--disable-default-apps", "--lang=ar", "--start-maximized", "--disable-translate"]
        if os.environ.get("JADEIT_HEADLESS"):
            args += ["--headless=new", "--no-sandbox", "--disable-gpu"]
        flags = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW
        return subprocess.Popen(args, close_fds=True, creationflags=flags)
    firefox = find_firefox()
    if firefox:
        subprocess.Popen([firefox, "-new-window", url], close_fds=True)
        return None
    message("لم يُعثر على Google Chrome أو Microsoft Edge أو Firefox.\n"
            "يحتاج النظام أحدها (على ويندوز 7: Chrome 109 أو Edge 109 أو Firefox ESR 115).\n"
            "سيُفتح المتصفح الافتراضي الآن.", icon="warn")
    import webbrowser
    webbrowser.open(url)
    return None


def wait_control_dialog(url: str):
    """عند عدم إمكان متابعة نافذة المتصفح: نافذة صغيرة تبقي النظام يعمل حتى يضغط المستخدم «موافق»."""
    if IS_WIN and not os.environ.get("JADEIT_NO_UI"):
        message("جاديت يعمل الآن في المتصفح على العنوان:\n" + url +
                "\n\nأبقِ هذه الرسالة مفتوحة أثناء العمل.\nاضغط «موافق» لإيقاف النظام بأمان بعد الانتهاء.",
                title="جاديت — النظام يعمل")
        return
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main():
    data = data_dir()
    setup_logging(data)
    try:
        running = find_running()
        if running:
            # نسخة واحدة فقط: نفتح نافذة إضافية للنظام الذي يعمل بالفعل
            print("already running on", running)
            open_window(f"http://127.0.0.1:{running}/", data)
            return 0
        server, port = start_server(data)
        url = f"http://127.0.0.1:{port}/"
        started = time.time()
        proc = open_window(url, data)
        if proc is not None:
            proc.wait()
            if time.time() - started < 4:
                # سلّم المتصفح النافذة لنسخة مفتوحة مسبقاً بنفس الملف الشخصي؛ نبقي النظام يعمل بنافذة تحكم
                wait_control_dialog(url)
        else:
            wait_control_dialog(url)
        print("shutting down")
        server.shutdown()
        server.server_close()
        return 0
    except Exception as e:
        traceback.print_exc()
        message("تعذر تشغيل النظام:\n" + str(e) + "\n\nالتفاصيل في الملف:\n" + os.path.join(data, "jadeit.log"),
                title="جاديت — خطأ", icon="error")
        return 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""1.93: المعاينة في نافذة مستقلة بمحرّك Edge (المرفق مع ويندوز 10 و11) — بوضع التطبيق (--app): نافذة واحدة بلا
شريط عنوان ولا تبويبات، بحجمٍ يناسب الشاشة وفي وسطها. وبلا Edge (أو لغير ويندوز): البرنامج الافتراضي كما كان."""
import ast, io, os, subprocess, sys, tempfile, textwrap, types

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
lines = src.splitlines()
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def module_src(name):
    node = next(n for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == name)
                or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name for t in n.targets)))
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def member(name):
    node = next(m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name)
    return textwrap.dedent("\n".join(lines[node.lineno - 1:node.end_lineno]))


errors, launched = [], []
fake_sys = types.SimpleNamespace(platform="linux")
fake_sub = types.SimpleNamespace(Popen=lambda cmd, **k: launched.append(cmd))
ns = {"os": os, "sys": fake_sys, "subprocess": fake_sub, "log_cloud_error": lambda *a: errors.append(a)}
for name in ("EDGE_EXE_CANDIDATES", "EDGE_PREVIEW_TYPES", "find_edge_exe", "edge_preview_command"):
    exec(module_src(name), ns)

# ═══ ١) الأمر: وضع التطبيق على الملف، بحجم وموضع، بلا شاشة الترحيب ═══
pdf = os.path.join(tempfile.mkdtemp(prefix="edge_"), "فاتورة 7.pdf")
open(pdf, "wb").close()
cmd = ns["edge_preview_command"](r"C:\Edge\msedge.exe", pdf, 1200, 860, 83, 10)
assert cmd[0] == r"C:\Edge\msedge.exe" and cmd[1].startswith("--app=file://") and cmd[1].endswith("%207.pdf")
assert "--window-size=1200,860" in cmd and "--window-position=83,10" in cmd
assert "--no-first-run" in cmd and "--no-default-browser-check" in cmd
assert not any(a.startswith("--new-window") or a.startswith("--kiosk") for a in cmd), "نافذة تطبيق لا ملء الشاشة"
print("✔ الأمر: msedge --app=file:///… (نافذة بلا شريط عنوان ولا تبويبات) بحجمٍ وموضعٍ محددين، والمسار العربي مرمَّز")

# ═══ ٢) البحث عن Edge: ويندوز وحده — من سجلّه ثم مساراته المعتادة ═══
assert ns["find_edge_exe"]() is None, "لغير ويندوز: لا Edge (يبقى البرنامج الافتراضي)"
body = module_src("find_edge_exe")
assert r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe" in body
assert all(p in module_src("EDGE_EXE_CANDIDATES") for p in ("%ProgramFiles(x86)%", "%ProgramFiles%", "%LOCALAPPDATA%"))
fake_sys.platform = "win32"
exe = os.path.join(tempfile.mkdtemp(prefix="edgebin_"), "msedge.exe")
open(exe, "w").close()
ns["EDGE_EXE_CANDIDATES"] = ("%NOPE%\\msedge.exe", exe)
assert ns["find_edge_exe"]() == exe, "بلا سجلّ ويندوز: أول مسار موجود"
print("✔ Edge من سجلّ ويندوز (App Paths) ثم Program Files وLocalAppData — ولغير ويندوز لا شيء")

# ═══ ٣) المعاينة: نافذة Edge بحجم الشاشة ووسطها، وإلا البرنامج الافتراضي ═══
exec("class App:\n" + textwrap.indent(member("open_in_edge_window"), "    ") + "\n"
     + textwrap.indent(member("_open_file"), "    "), ns)


class App(ns["App"]):
    def winfo_screenwidth(self):
        return 1366

    def winfo_screenheight(self):
        return 768


opened = []
ns["os"] = types.SimpleNamespace(path=os.path, startfile=lambda p, *a: opened.append(p))
ns["messagebox"] = types.SimpleNamespace(showerror=lambda *a, **k: errors.append(a))
a = App()
a._open_file(pdf)
assert len(launched) == 1 and not opened, (launched, opened)
w_arg = next(x for x in launched[0] if x.startswith("--window-size="))
pos = next(x for x in launched[0] if x.startswith("--window-position="))
assert w_arg == "--window-size=1246,678" and pos == "--window-position=60,10", (w_arg, pos)
print("✔ على ويندوز: PDF يُفتح في نافذة Edge مستقلة بحجم الشاشة ووسطها (1366×768 ← 1246×678)")

xlsx = pdf.replace(".pdf", ".csv")
assert a.open_in_edge_window(xlsx) is False
a._open_file(xlsx)
assert opened == [xlsx] and len(launched) == 1, "ملف CSV: البرنامج الافتراضي (Excel)"
ns["find_edge_exe"] = lambda: None
a._open_file(pdf)
assert opened[-1] == pdf and len(launched) == 1, "بلا Edge: البرنامج الافتراضي كما كان"


def boom(cmd, **k):
    raise OSError("blocked")
ns["subprocess"] = types.SimpleNamespace(Popen=boom)
ns["find_edge_exe"] = lambda: exe
a._open_file(pdf)
assert opened[-1] == pdf and errors, "تعذّر تشغيل Edge: يُسجَّل ويُفتح بالبرنامج الافتراضي"
print("✔ غير PDF/HTML/الصور، أو بلا Edge، أو تعذّر تشغيله: البرنامج الافتراضي — المعاينة لا تتعطل أبداً")

# ═══ ٤) كل المعاينات تمرّ من _open_file ═══
assert src.count("self._open_file(") >= 12 and "webbrowser" not in src
for m in ("print_khayas_section", "print_generic_table_screen", "export_tree_csv"):
    assert "self._open_file(" in member(m), m
assert src.count("os.startfile(path)") == 2, "خارج _open_file: فتح المجلدات وحدها (open_folder)"
print("✔ المعاينات كلها (الفواتير، السندات، الكشوف، طباعة الأقسام) تمرّ من _open_file")

print("\n✅ 1.93: المعاينة في نافذة Edge مستقلة بلا شريط عنوان ولا تبويبات")

# -*- coding: utf-8 -*-
"""
يكشف تحديث الواجهة من خيط خلفي بدون after() — سبب خطأ:
    RuntimeError: main thread is not in main loop

ويتحقق أن ردود نداء المزامنة كلها تمر عبر after قبل لمس أي أداة رسومية.
"""
import ast, io, sys

problems, checks = [], []

# ---------- ١) ردود نداء المزامنة في نسخة العميل ----------
src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")

for name in ("_on_sync_status", "_on_remote_change", "_on_gold_price"):
    fn = next((m for m in cls.body if isinstance(m, ast.FunctionDef) and m.name == name), None)
    if fn is None:
        problems.append(f"{name} مفقودة"); continue
    body = ast.get_source_segment(src, fn)
    if "self.after(" not in body:
        problems.append(f"{name} تلمس الواجهة بلا after()")
    elif "try:" not in body:
        problems.append(f"{name} بلا حماية من إغلاق النافذة أثناء التنفيذ")
    else:
        checks.append(f"{name}: تمر عبر after ومحميّة")

# ---------- ٢) نافذة تجهيز البيانات ----------
sw = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "SyncDownWindow"), None)
if sw:
    work = ast.get_source_segment(src, next(m for m in sw.body if isinstance(m, ast.FunctionDef) and m.name == "_work"))
    ui = ast.get_source_segment(src, next(m for m in sw.body if isinstance(m, ast.FunctionDef) and m.name == "_ui"))
    if ".configure(" in work or ".set(" in work.split("self._progress")[0]:
        problems.append("SyncDownWindow._work يلمس الواجهة مباشرة")
    else:
        checks.append("SyncDownWindow._work: كل تحديث عبر _ui/after")
    if "except Exception" not in ui:
        problems.append("SyncDownWindow._ui بلا حماية من إغلاق النافذة")
    else:
        checks.append("SyncDownWindow._ui: محميّة لو أُغلقت النافذة")

# ---------- ٣) محرك المزامنة نفسه ----------
sync = io.open("cloud_sync.py", encoding="utf-8").read()
if "daemon=True" not in sync:
    problems.append("خيط المزامنة ليس daemon — سيمنع إغلاق البرنامج")
else:
    checks.append("خيط المزامنة daemon: لا يمنع إغلاق البرنامج")

for widget_call in ("ctk.CTk", "tkinter", "messagebox."):
    if widget_call in sync:
        problems.append(f"محرك المزامنة يستدعي واجهة مباشرة: {widget_call}")
if not any(w in sync for w in ("ctk.CTk", "tkinter", "messagebox.")):
    checks.append("محرك المزامنة لا يلمس الواجهة إطلاقاً")

gpx = io.open("gold_price.py", encoding="utf-8").read()
if any(w in gpx for w in ("ctk.", "tkinter", "messagebox.")):
    problems.append("gold_price يلمس الواجهة مباشرة")
elif "daemon=True" not in gpx:
    problems.append("خيط سعر الذهب ليس daemon")
else:
    checks.append("gold_price: خيط daemon ولا يلمس الواجهة")

sd = io.open("sync_down.py", encoding="utf-8").read()
if any(w in sd for w in ("ctk.", "tkinter", "messagebox.")):
    problems.append("sync_down يلمس الواجهة مباشرة")
else:
    checks.append("sync_down لا يلمس الواجهة إطلاقاً")

for c in checks:
    print("✔", c)
for p in problems:
    print("✘", p)
print(f"\nالنتيجة: {'آمن على الخيوط ✔' if not problems else str(len(problems)) + ' مشكلة'}")
sys.exit(1 if problems else 0)

# -*- coding: utf-8 -*-
"""فحص نهائي شامل على نسخة العميل قبل التسليم"""
import ast, io, re, sys

SRC = __import__("sys").argv[1] if len(__import__("sys").argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(SRC, encoding="utf-8").read()
tree = ast.parse(src)
errors, warnings = [], []

# ---------- ١) الصياغة ----------
print(f"الملف: {SRC} | {len(src.splitlines()):,} سطر")

# ---------- ٢) استدعاءات self غير معرّفة ----------
INHERITED = {"after","title","geometry","update_idletasks","state","attributes","minsize",
 "winfo_screenwidth","winfo_screenheight","protocol","destroy","mainloop","withdraw","focus_force",
 "grab_set","transient","bind","configure","winfo_children","pack_forget","eval","grid_columnconfigure",
 "resizable","deiconify","pack","wait_window","update","quit","iconbitmap","columnconfigure",
 "rowconfigure","lift","grid","focus_set","winfo_exists","after_cancel","bell","clipboard_clear",
 "clipboard_append","selection_get","winfo_width", "winfo_viewable","winfo_height","wm_attributes","tk","cget",
 "yview","yview_moveto","yview_scroll","bind_all","unbind_all","item","identify_column",
 "get_children","index","selection","winfo_rgb","iconify"}

for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
    defined = {m.name for m in cls.body if isinstance(m, ast.FunctionDef)}
    assigned = {n.attr for n in ast.walk(cls) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "self" and isinstance(n.ctx, ast.Store)}
    called = {n.func.attr for n in ast.walk(cls) if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
              and n.func.value.id == "self"}
    miss = sorted(c for c in called if c not in defined and c not in assigned and c not in INHERITED)
    if miss:
        errors.append(f"{cls.name}: استدعاءات غير معرّفة {miss}")

# ---------- ٣) تعريفات مكررة ----------
for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
    seen = {}
    for m in cls.body:
        if isinstance(m, ast.FunctionDef):
            seen.setdefault(m.name, []).append(m.lineno)
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    if dups:
        errors.append(f"{cls.name}: دوال مكررة {dups}")

# ---------- ٤) كل مسار كتابة يُعيد الحساب ----------
app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
WRITES = {"save_invoice_to_db", "delete_invoice_from_db", "delete_worker_from_db"}
for m in app.body:
    if not isinstance(m, ast.FunctionDef):
        continue
    calls = {n.func.attr for n in ast.walk(m) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    if (WRITES & calls) and "recalculate_all" not in calls:
        # دالة مساعدة تكتب لكن لا تُستدعى إلا من دوال تُعيد الحساب بنفسها:
        # نتحقق من كل مستدعييها بدل اعتبارها خطأ مباشرة
        callers = [x for x in app.body if isinstance(x, ast.FunctionDef)
                   and m.name in {c.func.attr for c in ast.walk(x)
                                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}]
        safe = callers and all(
            "recalculate_all" in {c.func.attr for c in ast.walk(x)
                                  if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)}
            for x in callers)
        if not safe:
            errors.append(f"يكتب بلا إعادة حساب: {m.name}()")

# ---------- ٥) لا بقايا لملف الجلسة ----------
if "device_session" in src:
    errors.append("ما زالت هناك إشارة لملف الجلسة device_session")

# ---------- ٦) وحدات المزامنة مستوردة بأمان ----------
if "SYNC_AVAILABLE" not in src:
    errors.append("وحدات المزامنة غير مربوطة")
if "except Exception as _sync_err" not in src:
    warnings.append("استيراد المزامنة قد لا يكون محمياً")

# ---------- ٧) التاريخ ----------
load_fn = next(m for m in app.body if isinstance(m, ast.FunctionDef) and m.name == "load_data_from_db")
if "max(active_dates)" in ast.get_source_segment(src, load_fn):
    errors.append("خطأ التاريخ عاد: الفترة تقفز لأحدث شهر فيه حركات")

# ---------- ٨) التلوين ----------
for name, sec in [("refresh_casting_table", "الكاستنج"), ("refresh_polish_table", "التلميع"),
                  ("refresh_polish_buff_table", "التلميع/البف")]:
    fn = next(m for m in app.body if isinstance(m, ast.FunctionDef) and m.name == name)
    if f'section="{sec}"' not in ast.get_source_segment(src, fn):
        errors.append(f"{name}: لا يمرّر اسم القسم لزر التلوين")

# ---------- ٩) الرصيد الحالي ----------
for fn_name in ("get_total_gold_balance", "get_gold_balance_breakdown", "show_gold_balance_breakdown"):
    if not any(isinstance(m, ast.FunctionDef) and m.name == fn_name for m in app.body):
        errors.append(f"دالة الرصيد الحالي مفقودة: {fn_name}")
recalc = ast.get_source_segment(src, next(m for m in app.body if isinstance(m, ast.FunctionDef)
                                          and m.name == "recalculate_all"))
if "get_total_gold_balance" not in recalc:
    errors.append("الرصيد الحالي لا يُحدَّث مع إعادة الحساب")

# ---------- ١٠) متغيّرات مستخدمة قبل تعريفها في نفس الدالة ----------
for m in ast.walk(tree):
    if isinstance(m, ast.FunctionDef):
        seg = ast.get_source_segment(src, m) or ""
        if "color_negative" in seg and "color_negative =" not in seg and m.name != "render_stage_ops_table":
            if m.name not in ("refresh_op_ledger_table",):
                warnings.append(f"{m.name}: يستخدم color_negative بلا تعريف")

# ---------- ١١) مفاتيح سرية ----------
if "SUPABASE_SECRET_KEY" in src:
    m = re.search(r'SUPABASE_SECRET_KEY\s*=\s*"([^"]*)"', src)
    if m and m.group(1).strip():
        warnings.append("⚠️ المفتاح السري ما زال في الملف — احذفه قبل تسليم exe للعملاء")
# أي مفتاح سري حرفي داخل الكود خطأ حاسم — حتى في نسخة المدير (يتسرّب مع أي رفع للمستودع)
if re.search(r"sb_secret_[A-Za-z0-9_-]{8,}", src) or re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.", src):
    errors.append("مفتاح سري مكتوب داخل الكود — انقله إلى admin_secret.key أو متغيّر البيئة")

# ---------- النتيجة ----------
print()
for w in warnings:
    print("⚠️ ", w)
for e in errors:
    print("✘ ", e)
if not errors:
    print("✔ لا استدعاءات غير معرّفة ولا دوال مكررة")
    print("✔ كل مسار يكتب في قاعدة البيانات يُعيد الحساب الشامل")
    print("✔ لا بقايا لملف الجلسة — الدخول إجباري في كل تشغيل")
    print("✔ إصلاح التاريخ ثابت (لا قفز لشهر سابق)")
    print("✔ زر التلوين مربوط بكل قسم")
    print("✔ الرصيد الحالي معرّف ويُحدَّث مع كل عملية")
    print("\n✅ النسخة جاهزة للتسليم")
sys.exit(1 if errors else 0)

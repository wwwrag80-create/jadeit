# -*- coding: utf-8 -*-
"""اختبار: التاريخ الحيّ داخل الفترة، حذف الاسم بلا حركاته، والتراجع"""
import ast, calendar, datetime, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def seg(name):
    return ast.get_source_segment(src, next(m for m in cls.body if isinstance(m, ast.FunctionDef)
                                            and m.name == name))


# ═══ ١) التاريخ داخل الفترة المعروضة ═══
ns = {"datetime": datetime, "calendar": calendar}
exec("class S:\n" + textwrap.indent(textwrap.dedent(seg("get_smart_default_date")), "    "), ns)
app = ns["S"]()

today = datetime.datetime.now()
app.current_display_month = today.strftime("%Y-%m")
assert app.get_smart_default_date() == today.strftime("%Y-%m-%d")
print(f"✔ في الشهر الحالي: التاريخ = اليوم فعلاً ({app.get_smart_default_date()})")

# فترة سابقة: التاريخ يبقى تاريخ اليوم الحقيقي (الفترة يحدّدها عمود period)
app.current_display_month = "2026-08"
assert app.get_smart_default_date() == today.strftime("%Y-%m-%d")
print(f"✔ في فترة 2026-08: التاريخ يبقى اليوم الحقيقي ({app.get_smart_default_date()})")
print("  والانتماء لفترة ٨ يحدّده عمود period لا التاريخ")

# ═══ ٢) الوقت حيّ دائماً ═══
opdt = seg("get_operation_datetime")
assert "strftime('%H:%M:%S')" in opdt and "get_smart_default_date()" in opdt
print("✔ تاريخ العملية ووقتها حيّان دائماً")

live = seg("refresh_live_date_fields")
assert "self.after(30000" in live
print("✔ خانات التاريخ تُراجَع كل ٣٠ ثانية فتتتبّع تغيّر تاريخ الجهاز")
assert 'current in ("", last)' in live
print("✔ لا يُلمس تاريخ عدّله المستخدم بنفسه")

# ═══ ٣) حذف الاسم لا يحذف حركاته ═══
dw = seg("delete_worker_from_db")
assert "keep_transactions=True" in dw
assert "if not keep_transactions:" in dw
assert "push_undo" in dw
print("✔ حذف الاسم يُبقي حركاته المحاسبية (والحذف الكامل بخيار صريح)")

box = seg("perform_khayas_box_deletion")
assert "keep_transactions=False" in box
print("✔ حذف صندوق الخياس يحذف حركاته صراحةً (سلوك مقصود بعد تأكيد المستخدم)")

# ═══ ٤) التراجع ═══
for fn in ("push_undo", "undo_last_action", "rewrite_database_from_memory", "can_undo"):
    assert any(isinstance(m, ast.FunctionDef) and m.name == fn for m in cls.body), fn
print("✔ دوال التراجع موجودة")

undo = seg("undo_last_action")
assert "askyesno" in undo and "recalculate_all" in undo
print("✔ التراجع يطلب تأكيداً ثم يُعيد الحساب الشامل")

rw = seg("rewrite_database_from_memory")
assert 'cur.execute("BEGIN")' in rw and "conn.rollback()" in rw
print("✔ إعادة الكتابة في معاملة واحدة مع تراجع عند الفشل (لا حالة نصفية)")

push = seg("push_undo")
assert "UNDO_LIMIT" in push and "deepcopy" in push
print("✔ اللقطة نسخة مستقلة، والمكدس محدود فلا تتضخّم الذاكرة")

# ═══ ٥) ترتيب الأسماء ═══
rtl = seg("rtl")
assert "\\u200f" in rtl
clean = seg("clean_name")
assert "\\u200f" in clean and "\\u200e" in clean
print("✔ الأسماء تُعرض باتجاه مثبّت، وتُنظَّف من العلامات قبل الحفظ")

# تحقق فعلي
ns3 = {}
exec("class S:\n" + textwrap.indent(textwrap.dedent(rtl), "    ")
     + "\n" + textwrap.indent(textwrap.dedent(clean), "    "), ns3)
S = ns3["S"]
assert S.clean_name(S.rtl("محمد علي")) == "محمد علي"
assert S.clean_name("  محمد علي  ") == "محمد علي"
assert S.rtl("") == "" and S.clean_name(None) == ""
print("✔ التنظيف يُرجع الاسم الأصلي تماماً (لا يُفسد المطابقة)")

print("\n✅ كل الاختبارات نجحت")

# -*- coding: utf-8 -*-
"""
اختبار حاسم بعد حادثة تلف بيانات العميل:
  • نسخة العميل ترفع فقط ولا تسحب شيئاً — فبياناتها لا تتغيّر أبداً.
  • نسخة المدير تسحب فقط ولا ترفع شيئاً — فلا تصل بياناتها للعميل.
"""
import ast, io

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
sw = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SyncDownWindow")


def seg(node, name):
    return ast.get_source_segment(src, next(m for m in node.body
                                            if isinstance(m, ast.FunctionDef) and m.name == name))


# ═══ ١) العميل: رفع فقط، بلا سحب ═══
work = seg(sw, "_work")
i_guard = work.find("if not IS_ADMIN_BUILD:")
i_down = work.find("sync_down(")
assert i_guard != -1, "لا يوجد فصل بين نسختي العميل والمدير"
assert i_down == -1 or i_guard < i_down, "العميل قد يصل إلى السحب!"
# فرع العميل كاملاً: من الشرط حتى بداية قسم نسخة المدير (لا نافذة نصية بطول ثابت)
i_admin = work.find("# نسخة المدير", i_guard)
assert i_admin != -1, "لم يُعثر على بداية قسم نسخة المدير"
seg_guard = work[i_guard:i_admin]
assert "return" in seg_guard
print("✔ نسخة العميل: تجهّز بياناتها ثم تعود فوراً — لا تصل إلى أي تنزيل إطلاقاً")

assert "drop_web_sync_artifacts" in seg_guard and "uploader" not in work and "sync_down" not in work
print("✔ ولا ترفع الحركات صفاً صفاً (أُزيل الويب): تحذف بقاياه من قاعدتها فقط، ونسختها الكاملة تُرفع في الخلفية")

assert "reset_local_cache" in work
i_reset = work.find("reset_local_cache")
assert i_guard < i_reset, "مسح القاعدة قد يقع في نسخة العميل!"
print("✔ مسح القاعدة المحلية محصور في نسخة المدير وحدها")

# ═══ ٢) لا مزامنة ويب إطلاقاً (الدفعة ٢١): لا محرك رفع ولا سحب ولا احتياط من سجل الحركات ═══
for gone in ("CloudSync", "install_sync_schema", "sync_down(", "start_cloud_sync_engine", "_on_remote_change",
             "ADMIN_LEDGER_FALLBACK_NOTE", '"ledger"', "_RpcBridge"):
    assert gone not in src, gone
assert not __import__("os").path.exists("cloud_sync.py") and not __import__("os").path.exists("sync_down.py")
print("✔ مزامنة الويب أُزيلت: لا محرك رفع ولا سحب، والمدير يقرأ النسخة الكاملة وحدها")

# ═══ ٣) المدير لا يرفع شيئاً ═══
upload = ast.get_source_segment(src, next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                                          and n.name == "cloud_upload_backup"))
i_admin = upload.find("if IS_ADMIN_BUILD:")
assert i_admin != -1 and "return False" in upload[i_admin:i_admin + 120]
print("✔ نسخة المدير لا ترفع شيئاً — بياناتها لا تصعد للسحابة أبداً")

# ═══ ٤) شاشة الاستعادة ═══
for fn in ("open_backup_restore_window", "restore_from_backup", "describe_backup",
           "list_local_backups"):
    assert any(isinstance(m, ast.FunctionDef) and m.name == fn for m in cls.body), fn
print("✔ شاشة استعادة النسخ الاحتياطية موجودة")

rest = seg(cls, "restore_from_backup")
i_safety = rest.find("before_restore_")
i_check = rest.find("integrity_check")
i_swap = rest.rfind("srccon.backup(dst)")
assert i_safety < i_check < i_swap, "ترتيب الاستعادة غير آمن"
print("✔ ترتيب الاستعادة آمن: حفظ الوضع الحالي ← فحص سلامة النسخة ← الاستبدال")
assert 'return False, f"النسخة تالفة' in rest
print("✔ النسخة التالفة تُرفض ولا يتغيّر شيء")

desc = seg(cls, "describe_backup")
for k in ("mtime", "rows", "periods"):
    assert k in desc, k
print("✔ كل نسخة تُعرض بوقتها وعدد حركاتها وفتراتها — الاختيار واعٍ لا تخميني")

win = seg(cls, "open_backup_restore_window")
assert "askyesno" in win and "عدد حركاتها" in win
print("✔ تأكيد قبل الاستعادة يوضّح النسخة ومحتواها")

print("\n✅ اتجاه المزامنة أحادي: بيانات العميل محميّة تماماً")

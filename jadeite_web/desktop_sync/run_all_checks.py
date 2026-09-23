# -*- coding: utf-8 -*-
"""فحص شامل قبل أي تسليم — شغّله بعد أي تعديل"""
import subprocess, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"

CHECKS = [
    ("الصياغة",            ["python3", "-c", f"import ast,io; ast.parse(io.open('{TARGET}',encoding='utf-8').read())"]),
    ("متغيّرات قبل تعريفها", ["python3", "check_unbound.py", TARGET]),
    ("أمان الخيوط",         ["python3", "check_thread_safety.py"]),
    ("الفحص البنيوي",       ["python3", "final_audit.py", TARGET]),
    ("استعادة بيانات العميل", ["python3", "test_client_upgrade.py"]),
    ("الرفع والسحب",        ["python3", "test_restore.py"]),
    ("الرصيد الحالي",       ["python3", "test_total_balance.py"]),
    ("الذهب عند القسم",     ["python3", "test_gold_at_section.py"]),
    ("سعر الذهب",           ["python3", "test_gold_price.py"]),
    ("مسار المدير الكامل",   ["python3", "test_admin_view.py"]),
    ("دورة صندوق الخياس",   ["python3", "test_box_lifecycle.py"]),
    ("إصلاح صلاحية المزامنة", ["python3", "test_sync_permission_fix.py"]),
    ("صافي الطقوم",         ["python3", "test_sales_net.py"]),
    ("محاسبة الدفعة ١٢",     ["python3", "test_v12_accounting.py"]),
    ("عزل السطور المعلوماتية", ["python3", "test_memo_status.py"]),
    ("ترحيل السطور القديمة", ["python3", "test_memo_migration.py"]),
    ("تطابق شريط الخزينة",   ["python3", "test_treasury_match.py"]),
    ("ربح/خسارة الطقم",     ["python3", "test_sets_profit.py"]),
    ("توافق التحديث",       ["python3", "test_upgrade_compat.py"]),
    ("صف الإجمالي الثابت",  ["python3", "test_sticky_totals.py"]),
    ("تعديل الصف والجلب",   ["python3", "test_row_edit_lookup.py"]),
    ("التحديث الكسول",      ["python3", "test_lazy_refresh.py"]),
    ("خياس المركب",         ["python3", "test_assembler_khayas.py"]),
    ("قواعد رقم التشغيل",   ["python3", "test_set_number_rules.py"]),
    ("تنقّل نوافذ التعديل", ["python3", "test_edit_navigation.py"]),
    ("التاريخ والتراجع",     ["python3", "test_live_date_undo.py"]),
    ("الفترة المحاسبية",     ["python3", "test_period_field.py"]),
    ("أمان حذف الاسم",      ["python3", "test_delete_name_safety.py"]),
    ("ترتيب الأسماء",       ["python3", "test_name_order.py"]),
    ("مطابقة المدير للعميل", ["python3", "test_admin_mirror.py"]),
    ("عزل الفترات",         ["python3", "test_period_isolation.py"]),
    ("خياس التلميع النهائي", ["python3", "test_final_polish_box.py"]),
    ("اتجاه المزامنة",      ["python3", "test_one_way_sync.py"]),
    ("ترحيل رصيد الفترة",   ["python3", "test_opening_balance.py"]),
    ("خياس كل فترة",        ["python3", "test_khayas_per_period.py"]),
    ("ختم فترة الإقفال",    ["python3", "test_closing_period_stamp.py"]),
    ("خياس فعلي لكل فترة",  ["python3", "test_live_khayas_rows.py"]),
    ("معادلة الخياس الفعلي", ["python3", "test_khayas_formula.py"]),
    ("قالب الطباعة",        ["python3", "test_print_template.py"]),
    ("الشريط الجانبي",      ["python3", "test_sidebar_ui.py"]),
    ("البناء الكسول",       ["python3", "test_lazy_screens.py"]),
    ("نظام التصميم",        ["python3", "test_design_system.py"]),
    ("تحسينات الواجهة",     ["python3", "test_ui_polish.py"]),
    ("إعادة استخدام الجداول", ["python3", "test_tree_reuse.py"]),
    ("الأداء والمزامنة",     ["python3", "test_perf_and_sync.py"]),
    ("بلا اهتزاز",          ["python3", "test_no_flicker.py"]),
]

failed = []
for name, cmd in CHECKS:
    r = subprocess.run(cmd, capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"{'✔' if ok else '✘'} {name}")
    if not ok:
        failed.append(name)
        print((r.stdout + r.stderr).strip()[-600:])

print()
if failed:
    print(f"✘ فشل: {'، '.join(failed)}")
    sys.exit(1)
print(f"✅ كل الفحوص نجحت — {TARGET} جاهز")

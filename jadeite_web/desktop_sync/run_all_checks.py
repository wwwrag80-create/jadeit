# -*- coding: utf-8 -*-
"""فحص شامل قبل أي تسليم — شغّله بعد أي تعديل"""
import subprocess, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"

PY = sys.executable or "python3"

CHECKS = [
    ("الصياغة",            [PY, "-c", f"import ast,io; ast.parse(io.open('{TARGET}',encoding='utf-8').read())"]),
    ("متغيّرات قبل تعريفها", [PY, "check_unbound.py", TARGET]),
    ("أمان الخيوط",         [PY, "check_thread_safety.py"]),
    ("الفحص البنيوي",       [PY, "final_audit.py", TARGET]),
    ("استعادة بيانات العميل", [PY, "test_client_upgrade.py"]),
    ("الرفع والسحب",        [PY, "test_restore.py"]),
    ("الاسترجاع بعد إعادة التثبيت", [PY, "test_reinstall_restore.py"]),
    ("المدير يطابق العميل",  [PY, "test_admin_parity.py"]),
    ("الرصيد الحالي",       [PY, "test_total_balance.py"]),
    ("الذهب عند القسم",     [PY, "test_gold_at_section.py"]),
    ("سعر الذهب",           [PY, "test_gold_price.py"]),
    ("مسار المدير الكامل",   [PY, "test_admin_view.py"]),
    ("دورة صندوق الخياس",   [PY, "test_box_lifecycle.py"]),
    ("إصلاح صلاحية المزامنة", [PY, "test_sync_permission_fix.py"]),
    ("صافي الطقوم",         [PY, "test_sales_net.py"]),
    ("محاسبة الدفعة ١٢",     [PY, "test_v12_accounting.py"]),
    ("عزل السطور المعلوماتية", [PY, "test_memo_status.py"]),
    ("ترحيل السطور القديمة", [PY, "test_memo_migration.py"]),
    ("تطابق شريط الخزينة",   [PY, "test_treasury_match.py"]),
    ("ربح/خسارة الطقم",     [PY, "test_sets_profit.py"]),
    ("توافق التحديث",       [PY, "test_upgrade_compat.py"]),
    ("صف الإجمالي الثابت",  [PY, "test_sticky_totals.py"]),
    ("تعديل الصف والجلب",   [PY, "test_row_edit_lookup.py"]),
    ("التحديث الكسول",      [PY, "test_lazy_refresh.py"]),
    ("خياس المركب",         [PY, "test_assembler_khayas.py"]),
    ("قواعد رقم التشغيل",   [PY, "test_set_number_rules.py"]),
    ("تنقّل نوافذ التعديل", [PY, "test_edit_navigation.py"]),
    ("التاريخ والتراجع",     [PY, "test_live_date_undo.py"]),
    ("الفترة المحاسبية",     [PY, "test_period_field.py"]),
    ("أمان حذف الاسم",      [PY, "test_delete_name_safety.py"]),
    ("ترتيب الأسماء",       [PY, "test_name_order.py"]),
    ("مطابقة المدير للعميل", [PY, "test_admin_mirror.py"]),
    ("عزل الفترات",         [PY, "test_period_isolation.py"]),
    ("خياس التلميع النهائي", [PY, "test_final_polish_box.py"]),
    ("اتجاه المزامنة",      [PY, "test_one_way_sync.py"]),
    ("محرك المزامنة فعلياً", [PY, "test_cloud_sync_engine.py"]),
    ("ترحيل رصيد الفترة",   [PY, "test_opening_balance.py"]),
    ("خياس كل فترة",        [PY, "test_khayas_per_period.py"]),
    ("ختم فترة الإقفال",    [PY, "test_closing_period_stamp.py"]),
    ("خياس فعلي لكل فترة",  [PY, "test_live_khayas_rows.py"]),
    ("دفتر الفترات الموحّد", [PY, "test_period_ledger.py"]),
    ("معادلة الخياس الفعلي", [PY, "test_khayas_formula.py"]),
    ("قالب الطباعة",        [PY, "test_print_template.py"]),
    ("الشريط الجانبي",      [PY, "test_sidebar_ui.py"]),
    ("البناء الكسول",       [PY, "test_lazy_screens.py"]),
    ("نظام التصميم",        [PY, "test_design_system.py"]),
    ("تحسينات الواجهة",     [PY, "test_ui_polish.py"]),
    ("إعادة استخدام الجداول", [PY, "test_tree_reuse.py"]),
    ("الأداء والمزامنة",     [PY, "test_perf_and_sync.py"]),
    ("بلا اهتزاز",          [PY, "test_no_flicker.py"]),
    ("شاشة الترحيب والدخول", [PY, "test_login_screen.py", TARGET]),
    ("الواجهات والمحاسبة ٣",  [PY, "test_screens_v3.py", TARGET]),
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

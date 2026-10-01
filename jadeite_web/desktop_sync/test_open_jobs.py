# -*- coding: utf-8 -*-
"""
الطقوم المفتوحة والذهب عند العمال (الدفعة ١٦) — من دوال البرنامج نفسها:

  • العمل المفتوح = صُرف له ذهب (صرف/ليز) ولم يُستلم منه شيء (قبض، المفنش، البوليش، السلك الراجع).
  • رقم التشغيل عملٌ واحد عند العامل عبر الفترات: صرف في أغسطس واستلام في سبتمبر = عمل مُغلق.
  • حركات الصف بلا رقم تأخذ رقم صفّها؛ والصف بلا رقم تشغيل عملٌ في فترته.
  • العمر من تاريخ أول صرف، والمتأخر من حدّ الأيام المختار، والأقدم أولاً.
  • الذهب عند العامل = ذهب/باقي في دفتره للفترة.
"""
import ast, datetime, io, sys, textwrap

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")


def node(name):
    return next(x for x in cls.body if (isinstance(x, ast.FunctionDef) and x.name == name)
                or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))


def member_src(name):
    x = node(name)
    deco = "".join("@" + ast.get_source_segment(src, d) + "\n" for d in getattr(x, "decorator_list", []))
    return textwrap.dedent(deco + ast.get_source_segment(src, x))


def body(name):
    return ast.get_source_segment(src, node(name))


PREFS = {}
ns = {"datetime": datetime, "load_ui_prefs": lambda: dict(PREFS)}
MEMBERS = ["_SET_DIGITS", "normalize_set_number", "WORKER_SECTIONS", "JOB_ISSUE_TYPES", "JOB_RECEIPT_TYPES",
           "DEFAULT_OVERDUE_DAYS", "overdue_days", "worker_jobs", "open_jobs", "gold_at_workers"]
exec("class Base:\n" + "\n".join(textwrap.indent(member_src(m), "    ") for m in MEMBERS), ns)


class App(ns["Base"]):
    def __init__(self):
        self.categories = {"المصنعين": ["سالم", "خالد"], "المركبين": ["مركب"]}
        self.invoices, self.n = {}, 0
        self.current_display_month = "2026-09"

    def inv_period(self, inv):
        return inv.get("period") or str(inv.get("التاريخ", ""))[:7]

    def invoices_by_name(self):
        out = {}
        for inv in self.invoices.values():
            out.setdefault(inv["الاسم"], []).append(inv)
        return out

    def calculate_single_ledger(self, name, sec, target_month=None):
        baqi = 0.0
        for inv in self.invoices.values():
            if inv["الاسم"] == name and self.inv_period(inv) == target_month and inv["settled_status"] == "ACTIVE":
                baqi += {"صرف ذهب": 1, "الليز": 1, "قبض ذهب": -1}.get(inv["النوع"], 0) * inv["الوزن"]
        return {"ذهب/باقي": round(baqi, 2)}

    def add(self, name, t, w, row="", set_no="", dt="2026-09-10 10:00:00", period=None, status="ACTIVE"):
        self.n += 1
        self.invoices[self.n] = {"رقم الفاتورة": self.n, "الاسم": name, "النوع": t, "الوزن": w, "row_number": row,
                                 "set_number": set_no, "التاريخ": dt, "period": period or dt[:7],
                                 "settled_status": status}


a = App()
# ١) سالم: رقم ٥٠١ صُرف في أغسطس واستُلم في سبتمبر برقمه ← مُغلق
a.add("سالم", "صرف ذهب", 100.0, "1", "٥٠١", dt="2026-08-28 09:00:00")
a.add("سالم", "قبض ذهب", 90.0, "4", "501", dt="2026-09-02 09:00:00")
# ٢) سالم: رقم ٥٠٢ صُرف ولم يُستلم ← مفتوح منذ ٢٠ يوماً (متأخر)
a.add("سالم", "صرف ذهب", 50.0, "2", "502", dt="2026-09-11 09:00:00")
a.add("سالم", "الليز", 1.5, "2", dt="2026-09-12 09:00:00")            # صفّه بلا رقم ← يأخذ ٥٠٢
# ٣) سالم: صف ٣ بلا رقم تشغيل، صُرف واستُلم منه بالمفنش ← مُغلق
a.add("سالم", "صرف ذهب", 30.0, "3", dt="2026-09-20 09:00:00")
a.add("سالم", "المفنش ٨ بالالف", 25.0, "3", dt="2026-09-25 09:00:00")
# ٤) خالد: صف ٧ بلا رقم، صُرف قبل يومين ← مفتوح غير متأخر
a.add("خالد", "صرف ذهب", 12.0, "7", dt="2026-09-29 09:00:00")
# ٥) مركب: رقم ٥٠١ نفسه عند المركّب ← عمل مستقل، استُلم منه سلك راجع فقط ← مُغلق
a.add("مركب", "صرف ذهب", 90.0, "1", "501", dt="2026-09-03 09:00:00")
a.add("مركب", "السلك الراجع", 5.0, "1", dt="2026-09-04 09:00:00")
# ٦) حركة مؤرشفة لا تدخل، ونوع آخر (عيار) لا يغيّر شيئاً
a.add("خالد", "صرف ذهب", 99.0, "9", dt="2026-08-01 09:00:00", status="SETTLED")
a.add("خالد", "العيار بعد الفحص", 750.0, "7", dt="2026-09-29 10:00:00")

jobs = a.worker_jobs()
assert jobs[("SET", "سالم", "501")]["issued"] == 100.0 and jobs[("SET", "سالم", "501")]["received"] == 90.0
assert jobs[("SET", "سالم", "502")]["issued"] == 51.5, "الليز على صف الرقم يدخل في عمله"
assert ("SET", "مركب", "501") in jobs and jobs[("SET", "مركب", "501")]["received"] == 5.0
assert ("ROW", "سالم", "2026-09", "3") in jobs and ("ROW", "خالد", "2026-09", "7") in jobs
assert not any(k[1] == "خالد" and k[-1] == "9" for k in jobs), "المؤرشف لا يدخل"
print("✔ الأعمال: رقم التشغيل عبر الفترات (أغسطس ← سبتمبر)، والصف بلا رقم في فترته، والمؤرشف لا يدخل")

today = datetime.date(2026, 10, 1)
op = a.open_jobs(today=today)
assert [(j["name"], j["set_number"] or j["row"]) for j in op] == [("سالم", "502"), ("خالد", "7")], op
s502, k7 = op
assert s502["age"] == 20 and s502["overdue"] and s502["issued"] == 51.5 and s502["first_issue"].startswith("2026-09-11")
assert k7["age"] == 2 and not k7["overdue"] and k7["row"] == "7"
print("✔ المفتوح وحده (بلا أي استلام)، بعمره من أول صرف (٢٠ و٢ يوم)، والمتأخر بحدّ ٧ أيام، والأقدم أولاً")

PREFS["overdue_days"] = 30
assert a.overdue_days() == 30 and not any(j["overdue"] for j in a.open_jobs(today=today))
PREFS["overdue_days"] = "عبث"
assert a.overdue_days() == 7
PREFS["overdue_days"] = 1
assert all(j["overdue"] for j in a.open_jobs(today=today))
PREFS.clear()
print("✔ حدّ التأخير يُختار ويُحفظ للجهاز (القيمة التالفة ترجع لـ ٧ أيام)")

w = {r["name"]: r for r in a.gold_at_workers(a.open_jobs(today=today), month="2026-09")}
assert w["سالم"]["open"] == 1 and w["سالم"]["overdue"] == 1 and w["سالم"]["oldest"] == 20
assert w["سالم"]["held"] == round(51.5 + 30.0 - 90.0, 2), w["سالم"]["held"]
assert w["خالد"]["open"] == 1 and w["خالد"]["open_gold"] == 12.0 and w["خالد"]["held"] == 12.0
assert w["مركب"]["open"] == 0 and w["مركب"]["held"] == 90.0
assert list(w)[0] == "سالم", "صاحب المتأخر أولاً"
print("✔ الذهب عند كل عامل = ذهب/باقي في دفتره، مع عدد مفتوحاته وأقدمها — وصاحب المتأخر أولاً")

assert a.open_jobs(today=today) and App().open_jobs(today=today) == []
win = body("open_open_jobs_report")
assert "self.open_jobs(overdue_days=limit)" in win and 'save_ui_pref("overdue_days"' in win
assert "self.open_set_number_trace(" in win and "self.print_generic_table_screen(" in win
assert "command=self.open_open_jobs_report" in body("build_inquiries_tab")
print("✔ النافذة من صناديق الخياس: ملخص العمال ثم الطقوم (المتأخر بالأحمر)، والنقر المزدوج يتتبّع الرقم، وطباعة")

print("\n✅ الطقوم المفتوحة والذهب عند العمال سليمان")

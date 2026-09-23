# -*- coding: utf-8 -*-
"""
اختبار قاعدتَي رقم التشغيل في المصنعين/المركبين:
  ١) لا يتكرّر في صف آخر ولا لعامل آخر.
  ٢) إدخاله وحده يُكمل العملية على نفس صفه (بلا كتابة رقم الصف).
"""
import ast, io, textwrap

src = io.open("rageh-1-34-14-cloud.py", encoding="utf-8").read()
cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
seg = lambda n: ast.get_source_segment(src, next(m for m in cls.body
                                                 if isinstance(m, ast.FunctionDef) and m.name == n))

# ═══ دالة البحث ═══
ns = {}
exec("class S:\n"
     "    @staticmethod\n    def inv_period(inv):\n"
     '        p = (inv.get("period") or "").strip()\n'
     '        return p if p else str(inv.get("التاريخ", ""))[:7]\n'
     "    @classmethod\n    def inv_in_period(cls, inv, month):\n"
     "        return True if not month else cls.inv_period(inv) == month\n"
     + textwrap.indent(textwrap.dedent(seg("find_row_by_set_number")), "    "), ns)
app = ns["S"]()
app.current_display_month = "2026-09"
app.categories = {"المصنعين": ["أحمد", "سالم"]}


def inv(i, name, op, w, row, setno):
    return {"رقم الفاتورة": i, "الاسم": name, "النوع": op, "الوزن": w,
            "row_number": row, "set_number": setno, "settled_status": "ACTIVE",
            "التاريخ": "2026-09-05 10:00", "period": "2026-09"}


app.invoices = {1: inv(1, "أحمد", "صرف ذهب", 10.0, "1", "1")}

owner, row = app.find_row_by_set_number("المصنعين", "1")
assert (owner, row) == ("أحمد", "1")
print("✔ رقم التشغيل (1) يُعرّف صف أحمد رقم (1)")

assert app.find_row_by_set_number("المصنعين", "99") == (None, None)
assert app.find_row_by_set_number("المصنعين", "") == (None, None)
print("✔ رقم غير مسجّل أو فارغ → لا صف")

app.invoices[9] = dict(inv(9, "أحمد", "صرف ذهب", 5.0, "7", "77"), settled_status="SETTLED")
assert app.find_row_by_set_number("المصنعين", "77") == (None, None)
print("✔ الحركات الملغاة لا تحجز رقم تشغيل")

app.invoices[10] = dict(inv(10, "أحمد", "صرف ذهب", 5.0, "8", "88"), period="2026-08")
assert app.find_row_by_set_number("المصنعين", "88") == (None, None)
print("✔ البحث داخل الفترة المعروضة وحدها")

# ═══ القواعد في الترحيل ═══
sub = seg("submit_unified_op")

assert "owner, owner_row = self.find_row_by_set_number(cat, set_typed)" in sub
print("\n✔ الترحيل يبحث عن صف رقم التشغيل قبل أي شيء")

assert "لا يمكن تسجيل نفس رقم التشغيل لعامل آخر" in sub
print("✔ عامل آخر بنفس رقم التشغيل → مرفوض")

assert 'مسجّل في الصف ({owner_row}) وليس ({row_typed})' in sub
print("✔ رقم صف مخالف لصف رقم التشغيل → مرفوض مع توضيح الصف الصحيح")

assert "row_entry.insert(0, owner_row)" in sub
print("✔ رقم التشغيل الموجود → يُملأ رقم الصف تلقائياً وتُضاف العملية لصفه")

assert "رقم التشغيل غير مسجّل من قبل، فلازم تكتب رقم الصف" in sub
print("✔ رقم تشغيل جديد → رقم الصف إلزامي لإنشاء صف جديد")

assert "dup_owner and dup_row != row_typed" in sub
print("✔ ولا يُقبل رقم تشغيل مستخدم في صف آخر")

# الترتيب: الفحص قبل نافذة التأكيد فلا يُسأل المستخدم ثم يُرفض
i_rule = sub.find("find_row_by_set_number")
i_confirm = sub.find('askyesno("تأكيد الترحيل"')
assert i_rule < i_confirm
print("✔ الفحص يسبق تأكيد الترحيل — لا يُسأل المستخدم ثم تُرفض عمليته")

print("\n✅ قاعدتا رقم التشغيل تعملان")

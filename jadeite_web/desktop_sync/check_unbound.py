# -*- coding: utf-8 -*-
"""
يكشف المتغيّرات المحلية المستخدمة قبل تعريفها داخل أي دالة.

هذا بالضبط نوع الخطأ الذي أسقط البرنامج عند الدخول (period_column):
لا يظهر عند فحص الصياغة لأنه خطأ وقت التشغيل لا وقت الترجمة.

يعمل بمرّتين: يجمع أماكن التعريف أولاً، ثم يفحص الاستخدامات —
مرّة واحدة لا تكفي لأن الاستخدام قد يسبق التعريف في ترتيب الملف.
"""
import ast, io, sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
tree = ast.parse(io.open(SRC, encoding="utf-8").read())
problems = []


def local_names(fn):
    """أسماء المعاملات والمتغيّرات المعرّفة بـ global/nonlocal (تُستثنى من الفحص)"""
    names = set()
    a = fn.args
    for arg in list(a.args) + list(a.kwonlyargs) + list(getattr(a, "posonlyargs", [])):
        names.add(arg.arg)
    if a.vararg: names.add(a.vararg.arg)
    if a.kwarg: names.add(a.kwarg.arg)
    for n in ast.walk(fn):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
    return names


def top_level_nodes(fn):
    """عقد جسم الدالة فقط، دون الغوص في الدوال الداخلية (لها نطاقها ووقت تنفيذها)"""
    out = []
    def walk(node, is_root=False):
        # الدوال الداخلية والاشتمالات لها نطاقها المستقل: متغيّراتها لا تخص الدالة الأم
        if not is_root and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                             ast.GeneratorExp, ast.ListComp, ast.SetComp,
                                             ast.DictComp)):
            return
        if not is_root:
            out.append(node)
        for child in ast.iter_child_nodes(node):
            walk(child)
    for stmt in fn.body:
        walk(stmt)
    return out


for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
    nodes = top_level_nodes(fn)
    skip = local_names(fn)

    # المرّة الأولى: أول سطر يُعرَّف فيه كل اسم
    first_def = {}
    for n in nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            first_def.setdefault(n.id, n.lineno)
        elif isinstance(n, (ast.For, ast.comprehension)):
            tgt = getattr(n, "target", None)
            for t in ast.walk(tgt) if tgt else []:
                if isinstance(t, ast.Name):
                    first_def.setdefault(t.id, getattr(t, "lineno", 0))
        elif isinstance(n, ast.ExceptHandler) and n.name:
            first_def.setdefault(n.name, n.lineno)

    # المرّة الثانية: أي قراءة تسبق أول تعريف
    for n in nodes:
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id in skip or n.id not in first_def:
                continue
            if n.lineno < first_def[n.id]:
                problems.append((fn.name, n.id, n.lineno, first_def[n.id]))

seen = set()
for fn, name, use_line, def_line in problems:
    key = (fn, name)
    if key in seen:
        continue
    seen.add(key)
    print(f"✘ {fn}(): المتغيّر '{name}' مستخدم في السطر {use_line} ويُعرَّف في {def_line}")

print(f"\nالنتيجة: {'لا مشاكل ✔' if not seen else str(len(seen)) + ' مشكلة'}")
sys.exit(1 if seen else 0)

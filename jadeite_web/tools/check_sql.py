# -*- coding: utf-8 -*-
"""فحص سلامة سكربت التثبيت: الترتيب، الاعتماديات، وإمكانية إعادة التشغيل بأمان"""
import re, io, os, sys

raw = io.open("supabase/INSTALL_ALL.sql", encoding="utf-8").read()
# نتجاهل التعليقات عند الفحص حتى لا تُحسب نصوصها كأوامر
sql_code = "\n".join(l for l in raw.split("\n") if not l.lstrip().startswith("--"))
errors = []

defs = [(m.start(), m.group(1)) for m in re.finditer(r"create or replace function public\.(\w+)", raw)]
first_def = {}
for pos, name in defs:
    first_def.setdefault(name, pos)

for name, pos in first_def.items():
    for m in re.finditer(r"public\.%s\s*\(" % re.escape(name), raw):
        # حذف توقيع قديم قبل إعادة التعريف ليس استدعاءً
        if raw[max(0, m.start() - 40):m.start()].rstrip().endswith("drop function if exists"):
            continue
        if m.start() < pos:
            errors.append(f"استدعاء قبل التعريف: public.{name}()")
            break

tables = {m.group(1): m.start() for m in re.finditer(r"create table if not exists public\.(\w+)", raw)}
for m in re.finditer(r"create policy (\w+) on public\.(\w+)", raw):
    name, t = m.group(1), m.group(2)
    if t not in tables:
        errors.append(f"سياسة على جدول غير معرّف: {t}")
    elif m.start() < tables[t]:
        errors.append(f"سياسة قبل إنشاء الجدول: {t}")
    if f"drop policy if exists {name}" not in raw:
        errors.append(f"سياسة بلا drop if exists: {name}")

if re.search(r"^\s*alter table .* force row level security", sql_code, re.M | re.I):
    errors.append("FORCE ROW LEVEL SECURITY مفعّلة — تسبب infinite recursion مع SECURITY DEFINER")
if re.search(r"^create table (?!if not exists)", sql_code, re.M):
    errors.append("create table بدون if not exists")
if re.search(r"^create type ", sql_code, re.M):
    errors.append("create type خارج do-block — يفشل عند إعادة التشغيل")
if "notify pgrst" not in sql_code:
    errors.append("ينقص notify pgrst 'reload schema'")

dart = ""
for root, _, fs in os.walk("lib"):
    for f in fs:
        if f.endswith(".dart"):
            dart += io.open(os.path.join(root, f), encoding="utf-8").read()
rpcs = set(re.findall(r"\.rpc\('(\w+)'", dart))
granted = set(re.findall(r"grant execute on function public\.(\w+)", raw))
for r in sorted(rpcs):
    if r not in first_def:
        errors.append(f"RPC غير معرّف في SQL: {r}")
    elif r not in granted:
        errors.append(f"RPC بلا grant: {r}")

print(f"دوال: {len(first_def)} | جداول: {len(tables)} | سياسات: {len(re.findall(r'create policy', raw))} | RPC مستخدمة: {len(rpcs)}")
if errors:
    for e in errors: print("✘", e)
    sys.exit(1)
for m in ["ترتيب التعريفات والاستدعاءات سليم", "الجداول قبل سياساتها",
          "لا وجود لـ FORCE RLS", "السكربت يمكن إعادة تشغيله بأمان", "كل RPC معرّف وممنوح"]:
    print("✔", m)

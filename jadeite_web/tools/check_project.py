# -*- coding: utf-8 -*-
"""فحص ثابت شامل لمشروع Flutter قبل التشغيل (يعمل بدون Flutter SDK)"""
import os, re, sys

BUILTIN_PROVIDERS = {"FutureProvider","StateNotifierProvider","StateProvider","Provider",
                     "StreamProvider","ChangeNotifierProvider","NotifierProvider","AsyncNotifierProvider"}
errors = []
dart_files = []
for root,_,fs in os.walk("lib"):
    for f in fs:
        if f.endswith(".dart"):
            dart_files.append(os.path.join(root,f))
src = {p: open(p,encoding="utf-8").read() for p in dart_files}

# ١) الاستيرادات النسبية
for p,s in src.items():
    for imp in re.findall(r"import\s+'([^']+)'", s):
        if imp.startswith(("package:","dart:")): continue
        if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(p), imp))):
            errors.append(f"import مفقود: {p} -> {imp}")

classes, providers = set(), set()
for p,s in src.items():
    classes |= set(re.findall(r"^(?:abstract\s+)?class\s+(\w+)", s, re.M))
    providers |= set(re.findall(r"^final\s+(\w+Provider)\s*=", s, re.M))

# ٢) providers
used = set()
for s in src.values():
    used |= set(re.findall(r"\b(\w+Provider)\b", s))
for u in sorted(used - providers - BUILTIN_PROVIDERS):
    errors.append(f"provider غير معرّف: {u}")

# ٣) دوال المستودعات — أي سطر بمسافتين ينتهي بـ ( ويسبقه اسم دالة
repo_src = src["lib/data/repositories/repositories.dart"]
repo_methods, cur = {}, None
for line in repo_src.split("\n"):
    m = re.match(r"class (\w+)", line)
    if m:
        cur = m.group(1); repo_methods[cur] = set()
    m = re.match(r"^  (?!//)(?!\})\S.*?\b(\w+)\s*\(", line)
    if m and cur:
        repo_methods[cur].add(m.group(1))

repo_of = {"authRepoProvider":"AuthRepository","tenantRepoProvider":"TenantRepository",
           "accountRepoProvider":"AccountRepository","txnRepoProvider":"TxnRepository",
           "ledgerRepoProvider":"LedgerRepository","journalRepoProvider":"JournalRepository",
           "closingRepoProvider":"ClosingRepository"}
for p,s in src.items():
    for prov, meth in re.findall(r"read\((\w+RepoProvider)\)\s*\.\s*(\w+)", s):
        cls = repo_of.get(prov)
        if cls and meth not in repo_methods.get(cls, set()):
            errors.append(f"دالة غير موجودة: {p} -> {cls}.{meth}()")

# ٤) الشاشات
shell = src["lib/features/home/shell_page.dart"]
for c in set(re.findall(r"const\s+(\w+Page)\(\)", shell)):
    if c not in classes:
        errors.append(f"شاشة غير معرّفة: {c}")
keys_defined = set(re.findall(r"\(key: '(\w+)', label:", src["lib/core/constants/op_types.dart"]))
keys_routed = set(re.findall(r"'(\w+)' => const \w+Page\(\)", shell))
if keys_defined - keys_routed:
    errors.append(f"شاشات في القائمة بلا توجيه: {sorted(keys_defined - keys_routed)}")

# ٥) توازن الأقواس
for p,s in src.items():
    b = re.sub(r"'(?:\\.|[^'\\])*'", "''", s)
    b = re.sub(r'"(?:\\.|[^"\\])*"', '""', b)
    b = re.sub(r"//.*", "", b)
    if b.count("{") != b.count("}"): errors.append(f"أقواس {{}} غير متوازنة: {p}")
    if b.count("(") != b.count(")"): errors.append(f"أقواس () غير متوازنة: {p}")

# ٦) كل RPC مستدعى من Dart له تعريف في SQL
sql = "".join(open(os.path.join("supabase",f),encoding="utf-8").read()
              for f in sorted(os.listdir("supabase")) if f.endswith(".sql"))
sql_funcs = set(re.findall(r"create or replace function public\.(\w+)", sql))
for p,s in src.items():
    for rpc in re.findall(r"\.rpc\('(\w+)'", s):
        if rpc not in sql_funcs:
            errors.append(f"RPC بلا تعريف SQL: {p} -> {rpc}()")

# ٧) كل دالة SQL مستدعاة من Dart لها grant
granted = set(re.findall(r"grant execute on function public\.(\w+)", sql))
for p,s in src.items():
    for rpc in set(re.findall(r"\.rpc\('(\w+)'", s)):
        if rpc in sql_funcs and rpc not in granted:
            errors.append(f"RPC بلا grant للمستخدمين: {rpc}()")

print(f"ملفات Dart: {len(dart_files)} | كلاسات: {len(classes)} | providers: {len(providers)} | دوال SQL: {len(sql_funcs)}")
if errors:
    for e in errors: print("✘", e)
    sys.exit(1)
for line in ["لا توجد استيرادات مفقودة","كل الـ providers معرّفة","كل دوال المستودعات موجودة",
             "كل الشاشات معرّفة وموجّهة","الأقواس متوازنة","كل RPC له تعريف SQL و grant"]:
    print("✔", line)

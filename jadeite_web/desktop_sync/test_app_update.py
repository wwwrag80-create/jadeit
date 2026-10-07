# -*- coding: utf-8 -*-
"""
زر «⬆️ تحديث» (الدفعة ٣٣): تحديث البرنامج كاملاً من الحزمة المرسلة.

  • الحزمة: حزمة المصدر jadeite_<الإصدار>.zip، أو ملف Jadeite-Client/Admin-<الإصدار>.exe الجاهز
    (أو zip فيه هذا الملف) — تُقرأ دون تنفيذ أي شيء منها، ويُعرض الإصدار الحالي ← الجديد.
  • لا نسخة أقدم، ولا ملف عميل على برنامج مدير (ولا العكس).
  • تشغيل من ملفات بايثون ← تُنسخ الملفات فوق القديمة (لا يُحذف شيء: المفتاح السري باقٍ) ثم يُعاد التشغيل.
  • نسخة exe ← يُبنى الجديد ببايثون الجهاز (build_exe.py بكل فحوصه)، أو يؤخذ الملف الجاهز، ثم يحلّ
    محلّ الحالي بعد إغلاقه بالاسم نفسه (اختصار سطح المكتب يبقى يعمل)، ويُحفظ القديم ‎.previous.
  • قبل أي تحديث نسخة احتياطية من البيانات، والبيانات في مجلدها لا يلمسها التحديث.
"""
import ast, io, os, re, shutil, subprocess, sys, tempfile, textwrap, zipfile

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
IS_ADMIN = bool(re.search(r"^IS_ADMIN_BUILD = True", src, re.M))


def module_src(name):
    n = next(x for x in tree.body if (isinstance(x, ast.FunctionDef) and x.name == name)
             or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))
    return ast.get_source_segment(src, n)


def body(name):
    n = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(src, n)


g = {"os": os, "re": re, "sys": sys, "shutil": shutil, "subprocess": subprocess, "zipfile": zipfile,
     "IS_ADMIN_BUILD": IS_ADMIN}
for name in ("UPDATE_SOURCE_NAME", "UPDATE_EXE_RE", "version_tuple", "app_build_kind", "inspect_update_package",
             "safe_extract_zip", "find_build_python", "write_swap_script", "plan_update", "apply_source_package"):
    exec(module_src(name), g)
kind = g["app_build_kind"]()
other = "client" if kind == "admin" else "admin"

tmp = tempfile.mkdtemp(prefix="jadeite_update_test_")
try:
    def make_zip(name, files):
        path = os.path.join(tmp, name)
        with zipfile.ZipFile(path, "w") as zf:
            for n, data in files.items():
                zf.writestr(n, data)
        return path

    # ═══ ١) قراءة الحزمة ═══
    assert g["version_tuple"]("1.66.0") == (1, 66, 0) > g["version_tuple"]("1.65.9") and g["version_tuple"]("x") == ()
    src_zip = make_zip("jadeite_9.9.9.zip", {
        "jadeite_web/desktop_sync/rageh-1-34-14-cloud.py": 'APP_VERSION = "9.9.9"\nIS_ADMIN_BUILD = True\n',
        "jadeite_web/desktop_sync/rageh-CLIENT.py": 'APP_VERSION = "9.9.9"\n',
        "jadeite_web/desktop_sync/build_exe.py": "# build\n",
        "jadeite_web/desktop_sync/fonts/a.ttf": b"\x00font",
        "jadeite_web/supabase/x.sql": "select 1;",
        "jadeite_web/desktop_sync/../../evil.txt": "خارج المجلد",
    })
    info = g["inspect_update_package"](src_zip)
    assert info["type"] == "source" and info["version"] == "9.9.9" and info["has_builder"]
    assert info["prefix"] == "jadeite_web/desktop_sync/"
    exe_zip = make_zip("exe.zip", {f"dist/Jadeite-{other.title()}-9.9.9.exe": b"x",
                                   f"dist/Jadeite-{kind.title()}-9.9.9.exe": b"y"})
    ez = g["inspect_update_package"](exe_zip)
    assert ez["type"] == "zip_exe" and ez["build"] == kind and ez["member"].endswith(f"{kind.title()}-9.9.9.exe")
    exe_file = os.path.join(tmp, f"Jadeite-{kind.title()}-9.9.9.exe")
    open(exe_file, "wb").write(b"MZ")
    ex = g["inspect_update_package"](exe_file)
    assert ex == {"type": "exe", "version": "9.9.9", "build": kind, "file": exe_file}
    bad = []
    for path in (os.path.join(tmp, "missing.zip"), make_zip("empty.zip", {"readme.txt": "x"})):
        try:
            g["inspect_update_package"](path)
        except ValueError as e:
            bad.append(str(e))
    renamed = os.path.join(tmp, "program.exe")
    open(renamed, "wb").write(b"MZ")
    notzip = os.path.join(tmp, "notes.zip")
    open(notzip, "w").write("not a zip")
    for path in (renamed, notzip):
        try:
            g["inspect_update_package"](path)
        except ValueError as e:
            bad.append(str(e))
    assert len(bad) == 4 and all(re.search(r"[\u0600-\u06FF]", m) for m in bad), bad
    print("✔ الحزمة تُقرأ دون تنفيذ شيء منها: المصدر (ورقم إصداره من الملف نفسه)، أو exe جاهز (من اسمه)، "
          "أو zip فيه exe — والملف الناقص أو الغريب برسالة عربية واضحة")

    # ═══ ٢) ماذا سيحدث ═══
    P = g["plan_update"]
    old = P(dict(info, version="1.0.0"), False, kind, "1.65.0")
    assert not old["ok"] and "أقدم" in old["text"]
    assert P(info, False, kind, "1.65.0")["mode"] == "copy"
    assert P(info, True, kind, "1.65.0")["mode"] == "build"
    assert not P(dict(info, has_builder=False), True, kind, "1.65.0")["ok"]
    assert P(ex, True, kind, "1.65.0")["mode"] == "swap" and "1.65.0" in P(ex, True, kind, "1.65.0")["text"]
    assert not P(ex, False, kind, "1.65.0")["ok"], "تشغيل من ملفات بايثون: ملف exe لا يُطبَّق هنا"
    assert not P(dict(ex, build=other), True, kind, "1.65.0")["ok"], "ملف المدير لا يُثبَّت على العميل (ولا العكس)"
    same = P(dict(info, version="1.65.0"), False, kind, "1.65.0")
    assert same["ok"] and "إعادة تثبيت" in same["text"]
    if kind == "admin":
        assert "نسخة العملاء" in P(info, True, kind, "1.65.0")["text"]
    print("✔ قبل التحديث يُعرض ما سيحدث: الإصدار الحالي ← الجديد؛ ولا نسخة أقدم، ولا ملف المدير على العميل")

    # ═══ ٣) نسخ الملفات (التشغيل من ملفات بايثون) ═══
    prog = os.path.join(tmp, "program", "desktop_sync")
    os.makedirs(prog)
    open(os.path.join(prog, "rageh-1-34-14-cloud.py"), "w").write('APP_VERSION = "1.65.0"\n')
    open(os.path.join(prog, "admin_secret.key"), "w").write("سري")
    n = g["apply_source_package"](info, prog)
    assert open(os.path.join(prog, "rageh-1-34-14-cloud.py")).read().startswith('APP_VERSION = "9.9.9"')
    assert open(os.path.join(prog, "admin_secret.key")).read() == "سري", "ملفاتك (المفتاح السري) تبقى"
    assert os.path.exists(os.path.join(prog, "fonts", "a.ttf")) and n == 4
    assert not os.path.exists(os.path.join(tmp, "evil.txt")) and not os.path.exists(os.path.join(tmp, "program", "evil.txt"))
    assert not os.path.exists(os.path.join(prog, "supabase")), "تُنسخ ملفات البرنامج وحدها"
    print("✔ التشغيل من ملفات بايثون: ملفات الإصدار الجديد فوق القديمة، وملفاتك (المفتاح السري) باقية، "
          "واسم ملف فيه «..» لا يخرج من مجلد البرنامج")

    # فك الحزمة كاملة للبناء: داخل مجلد التحديث وحده
    out = os.path.join(tmp, "work")
    with zipfile.ZipFile(src_zip) as zf:
        g["safe_extract_zip"](zf, out)
    assert os.path.exists(os.path.join(out, "jadeite_web", "supabase", "x.sql"))
    assert not os.path.exists(os.path.join(tmp, "evil.txt"))

    # ═══ ٤) استبدال exe بعد إغلاقه ═══
    folder = os.path.join(tmp, "مجلد التحديث")
    os.makedirs(folder)
    target = r"C:\Users\محمد\Desktop\Jadeite-Client-1.65.0.exe"
    script = g["write_swap_script"](folder, 4321, r"C:\Up\Jadeite-Client-9.9.9.exe", target,
                                    reveal=r"C:\it's\Jadeite-Client-9.9.9.exe")
    raw = open(script, "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf"), "UTF-8 بعلامة BOM: PowerShell يقرأ المسارات العربية"
    ps = raw.decode("utf-8-sig")
    assert "$old = 4321" in ps and "Get-Process -Id $old" in ps
    assert f"$target = '{target}'" in ps and "($target + '.previous')" in ps
    assert ps.index("Get-Process -Id $old") < ps.index("Copy-Item -LiteralPath $new -Destination $target")
    assert ps.index("Copy-Item -LiteralPath $new") < ps.index("Start-Process -FilePath $target")
    assert "'C:\\it''s\\Jadeite-Client-9.9.9.exe'" in ps, "علامة ' في المسار تُضاعف"
    assert "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path" in ps
    print("✔ نسخة exe: سكربت ينتظر إغلاق البرنامج، يحفظ القديم ‎.previous، يضع الجديد بالاسم نفسه "
          "(اختصار سطح المكتب يبقى يعمل) ثم يشغّله — والمسارات العربية سليمة")

    py = g["find_build_python"]()
    assert py is None or (isinstance(py, list) and os.path.exists(py[0]))
    print(f"✔ البحث عن بايثون صالح للبناء (٣٫١٠+ وفيه tkinter): {'وُجد' if py else 'غير موجود هنا'}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ═══ ٥) في البرنامج ═══
layout = body("create_layout")
i_upd = layout.index("self.btn_app_update = ctk.CTkButton(")
i_row = layout.index("tools_row = ctk.CTkFrame(tools_col")
i_theme = layout.index("self.btn_theme = ctk.CTkButton(tools_row")
i_search = layout.index("btn_search_all = ctk.CTkButton(\n            tools_row")
assert i_upd < i_row < i_theme < i_search
assert 'text="⬆️ تحديث"' in layout and "command=self.open_app_update" in layout
assert 'self.btn_app_update.pack(fill="x", pady=(0, 4))' in layout
print("✔ زر «⬆️ تحديث» أعلى الشريط فوق زرّي «فاتح» و«بحث» مباشرة وبعرضهما")

go = body("open_app_update")
assert go.index("self.perform_backup()") < go.index('if plan["mode"] == "copy":'), "نسخة احتياطية قبل أي تحديث"
assert "inspect_update_package(path)" in go and "plan_update(info, frozen, kind, APP_VERSION)" in go
assert "messagebox.askyesno" in go and 'state="disabled"' in go
build = body("_build_update")
assert '[vpy, "build_exe.py", k]' in build and '"--skip-install"' in build and "find_build_python()" in build
assert "threading.Thread(target=work" in build and "self.after(0" in build, "البناء في الخلفية والنافذة تتابع"
assert 'kinds = [kind] + (["client"] if kind == "admin" and var_clients.get() else [])' in go
swap = body("_swap_to_update")
assert '"-ExecutionPolicy", "Bypass"' in swap and "write_swap_script(work, os.getpid()" in swap
assert "self._exit_for_update()" in swap
ex = body("_exit_for_update")
assert "self.on_app_closing()" in ex and "os._exit(0)" in ex
assert not re.search(r"(rmtree|remove)\([^)]*(DATA_DIR|BACKUPS_DIR|APP_DATA_DIR\))", go + build + swap), \
    "التحديث لا يحذف شيئاً من مجلد البيانات"
print("✔ «تحديث الآن»: تأكيد، ثم نسخة احتياطية، ثم النسخ أو البناء (في الخلفية، سطراً سطراً) أو الاستبدال؛ "
      "والمدير يبني نسخة العملاء أيضاً لتوزيعها — والبيانات لا تُمسّ")

print("\n✅ زر التحديث: يحمّل الحزمة المرسلة ويحدّث البرنامج كاملاً إلى آخر إصدار")

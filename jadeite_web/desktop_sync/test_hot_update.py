# -*- coding: utf-8 -*-
"""
التحديث السريع بحزمة ‎.jup (الدفعة 1.67.0):

  • الحزمة: بيان (النوع، الإصدار، مستوى exe المطلوب، بصمة كل ملف، «ما الجديد») + ملفات البرنامج وحدها
    (أقل من ميجا). حزمة العميل بلا ملف المدير ولا مفتاح سري.
  • التثبيت في ثوانٍ: فكّ وتحقّق (البصمة، صياغة بايثون، أسماء آمنة) في مجلد مؤقت ثم المؤشّر — ملف تالف
    أو مُعدَّل يوقف كل شيء قبل أن يُلمس البرنامج. الإصدار السابق محفوظ للرجوع بضغطة.
  • exe يفتح الإصدار المثبَّت الأحدث بمكتباته هو؛ إن تعطّل قبل أن يفتح يُعلَّم معطوباً ويفتح الأساسي.
  • إعادة الفتح ببيئة نظيفة: متغيّرات PyInstaller الموروثة كانت تمنع exe الجديد من الفتح.
"""
import ast, builtins, hashlib, io, json, os, re, shutil, sys, tempfile, textwrap, types, zipfile

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
IS_ADMIN = bool(re.search(r"^IS_ADMIN_BUILD = True", src, re.M))
KIND = "admin" if IS_ADMIN else "client"
OTHER = "client" if IS_ADMIN else "admin"


def module_src(name):
    n = next(x for x in tree.body if (isinstance(x, ast.FunctionDef) and x.name == name)
             or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))
    return ast.get_source_segment(src, n)


def body(name):
    return ast.get_source_segment(src, next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name))


tmp = tempfile.mkdtemp(prefix="jadeite_hot_test_")
APPDATA = os.path.join(tmp, "LocalAppData", "JadeiteERP")
fake_sys = types.SimpleNamespace(frozen=True, path=[], modules={}, executable="Jadeite.exe")
g = {"os": os, "re": re, "json": json, "hashlib": hashlib, "zipfile": zipfile, "shutil": shutil,
     "datetime": __import__("datetime"), "sys": fake_sys, "IS_ADMIN_BUILD": IS_ADMIN, "APP_VERSION": "1.67.0",
     "admin_secret_dir": lambda: APPDATA}
for name in ("HOT_RUNTIME", "HOT_UPDATE_EXT", "HOT_LOCAL_MODULES", "JUP_FORMAT", "hot_update_root", "_hot_vt",
             "read_hot_pointer", "write_hot_pointer", "run_hot_update_if_newer", "clean_relaunch_env",
             "version_tuple", "app_build_kind", "_jup_safe_name", "read_jup_package", "jup_notes_since",
             "extract_jup_files", "install_hot_package", "rollback_hot_update", "embedded_runtime", "plan_update"):
    exec(module_src(name), g)
assert g["HOT_RUNTIME"] == 1 and g["HOT_UPDATE_EXT"] == ".jup"


def make_jup(version, entry_code, kind=KIND, runtime=1, extra=None, tamper=None, notes=None, entry=None):
    entry = entry or ("rageh-1-34-14-cloud.py" if kind == "admin" else "rageh-CLIENT.py")
    files = {entry: entry_code.encode("utf-8"), "gold_price.py": b"PRICE = 1\n"}
    files.update(extra or {})
    man = {"format": "jadeite-update", "format_version": 1, "kind": kind, "version": version, "runtime": runtime,
           "entry": entry, "files": {n: hashlib.sha256(d).hexdigest() for n, d in files.items()},
           "notes": notes if notes is not None else {version: [f"جديد {version}"], "1.66.2": ["قديم"]},
           "date": "2026-10-07 14:00"}
    path = os.path.join(tmp, f"{kind}-{version}-{len(os.listdir(tmp))}.jup")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(man, ensure_ascii=False))
        for n, d in files.items():
            zf.writestr(n, tamper.get(n, d) if tamper else d)
    return path


try:
    # ═══ ١) قراءة الحزمة وخطة التحديث ═══
    GOOD = "import builtins\nbuiltins._HOT_RAN = __file__\nimport sys as _s\n"
    p = make_jup("1.67.1", GOOD)
    info = g["read_jup_package"](p)
    assert info["type"] == "jup" and info["version"] == "1.67.1" and info["build"] == KIND and info["runtime"] == 1
    assert g["jup_notes_since"](info, "1.66.2") == [("1.67.1", ["جديد 1.67.1"])]
    assert [v for v, _ in g["jup_notes_since"](info, "1.60.0")] == ["1.67.1", "1.66.2"]
    P = g["plan_update"]
    assert P(info, True, KIND, "1.67.0", 1)["mode"] == "hot" and "ثوانٍ" in P(info, True, KIND, "1.67.0", 1)["text"]
    assert P(info, False, KIND, "1.67.0", 1)["mode"] == "jup_copy"
    assert not P(dict(info, runtime=2), True, KIND, "1.67.0", 1)["ok"], "حزمة تحتاج exe أحدث"
    assert "exe" in P(dict(info, runtime=2), True, KIND, "1.67.0", 1)["text"]
    assert not P(dict(info, build=OTHER), True, KIND, "1.67.0", 1)["ok"], "حزمة المدير لا تُثبَّت على العميل"
    assert not P(dict(info, version="1.66.0"), True, KIND, "1.67.0", 1)["ok"], "لا إصدار أقدم"
    errors = []
    for bad in (os.path.join(tmp, "x.jup"),):
        open(bad, "w").write("ليست zip")
        try:
            g["read_jup_package"](bad)
        except ValueError as e:
            errors.append(str(e))
    nomani = os.path.join(tmp, "nomani.jup")
    with zipfile.ZipFile(nomani, "w") as zf:
        zf.writestr("rageh-CLIENT.py", "x = 1")
    for path in (nomani, make_jup("1.67.1", GOOD, extra={"../evil.py": b"x=1"})):
        try:
            g["read_jup_package"](path)
        except ValueError as e:
            errors.append(str(e))
    assert len(errors) == 3 and all(re.search(r"[\u0600-\u06FF]", e) for e in errors), errors
    print("✔ حزمة ‎.jup تُقرأ دون تنفيذ شيء منها: الإصدار والنوع ومستوى exe المطلوب و«ما الجديد» منذ إصدارك؛ "
          "والملف التالف أو بلا بيان أو باسم «..» يُرفض برسالة عربية")
    print("✔ الخطة: exe ← تحديث سريع في ثوانٍ؛ ولا حزمة تحتاج exe أحدث، ولا حزمة المدير على العميل، ولا إصدار أقدم")

    # ═══ ٢) التثبيت: تحقق ثم مؤشّر، والإصدار السابق محفوظ ═══
    tampered = make_jup("1.67.1", GOOD, tamper={"gold_price.py": b"PRICE = 666  # \xd9\x85\xd8\xb9\xd8\xaf\xd9\x91\xd9\x84\n"})
    try:
        g["install_hot_package"](g["read_jup_package"](tampered), KIND)
        raise AssertionError("حزمة مُعدَّلة ثُبّتت!")
    except ValueError as e:
        assert "بصمته" in str(e)
    broken = make_jup("1.67.1", "def x(:\n")
    try:
        g["install_hot_package"](g["read_jup_package"](broken), KIND)
        raise AssertionError("ملف بايثون معطوب ثُبّت!")
    except ValueError as e:
        assert "لا يصلح للتشغيل" in str(e)
    assert g["read_hot_pointer"](KIND) is None, "لا مؤشّر بعد فشل التثبيت — البرنامج الحالي كما هو"
    steps = []
    g["install_hot_package"](info, KIND, progress=steps.append)
    cur = g["read_hot_pointer"](KIND)
    assert cur["version"] == "1.67.1" and os.path.isfile(cur["path"]) and cur["previous"] is None
    assert open(os.path.join(cur["folder"], "gold_price.py")).read() == "PRICE = 1\n" and steps
    info2 = g["read_jup_package"](make_jup("1.67.2", GOOD))
    g["install_hot_package"](info2, KIND)
    info3 = g["read_jup_package"](make_jup("1.67.3", GOOD))
    g["install_hot_package"](info3, KIND)
    cur = g["read_hot_pointer"](KIND)
    root = g["hot_update_root"](KIND)
    assert cur["version"] == "1.67.3" and cur["previous"]["version"] == "1.67.2"
    assert sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))) == ["1.67.2", "1.67.3"], \
        "الأقدم من السابق يُحذف"
    print("✔ التثبيت: ملف مُعدَّل (بصمته لا تطابق) أو بايثون معطوب يوقف كل شيء ولا يُكتب مؤشّر؛ والسليم يُثبَّت "
          "ويُحفظ الإصدار السابق وتُحذف الأقدم")

    # ═══ ٣) exe يفتح الإصدار المثبَّت الأحدث ═══
    run = g["run_hot_update_if_newer"]
    builtins._HOT_RAN = None
    try:
        run()
        raise AssertionError("لم يُشغَّل الإصدار المثبَّت")
    except SystemExit as e:
        assert e.code == 0
    assert builtins._HOT_RAN and builtins._HOT_RAN.endswith(os.path.join("1.67.3", os.path.basename(cur["path"])))
    assert fake_sys._jadeite_hot_running is True and fake_sys._jadeite_embedded == {"version": "1.67.0", "runtime": 1}
    assert fake_sys.path[0] == cur["folder"], "وحدات الإصدار المثبَّت (gold_price…) تُستورد من مجلده"
    fake_sys._jadeite_hot_running = False
    fake_sys.path.clear()
    print("✔ exe 1.67.0 يفتح الإصدار المثبَّت 1.67.3 من مجلده (ووحداته قبل وحدات exe)")

    for label, setup in (("أقدم من exe", lambda: g.update(APP_VERSION="1.68.0")),
                         ("يحتاج exe أحدث", lambda: g["write_hot_pointer"](dict(g["read_hot_pointer"](KIND), runtime=2), KIND)),
                         ("وضع آمن", lambda: os.environ.__setitem__("JADEITE_SAFE_MODE", "1")),
                         ("ليس exe", lambda: setattr(fake_sys, "frozen", False))):
        builtins._HOT_RAN = None
        setup()
        assert run() is False and builtins._HOT_RAN is None, label
        g["APP_VERSION"] = "1.67.0"
        g["write_hot_pointer"](dict(g["read_hot_pointer"](KIND), runtime=1), KIND)
        os.environ.pop("JADEITE_SAFE_MODE", None)
        fake_sys.frozen = True
    print("✔ ولا يُفتح إن كان أقدم من exe (exe جديد كامل يتقدّم)، أو يحتاج exe أحدث، أو في الوضع الآمن، أو بلا exe")

    # تعطّل قبل الفتح ← يُعلَّم معطوباً ويكمل البرنامج الأساسي
    boom = g["read_jup_package"](make_jup("1.67.4", "import gold_price\nimport jadeite_not_in_exe_module\n"))
    g["install_hot_package"](boom, KIND)
    fake_sys.modules["gold_price"] = "من الإصدار المعطوب"
    assert run() is False
    cur = json.load(open(os.path.join(root, "current.json"), encoding="utf-8"))
    assert cur["bad"] is True and "jadeite_not_in_exe_module" in cur["error"]
    assert fake_sys._jadeite_hot_running is False and fake_sys.path == [] and "gold_price" not in fake_sys.modules
    assert run() is False, "المعطوب لا يُعاد تجربته في كل فتح"
    print("✔ إصدار يتعطّل قبل أن يفتح (مكتبة لا يحملها exe) يُعلَّم معطوباً ويفتح البرنامج الأساسي — "
          "ولا يُعاد تجربته، وتُنظَّف وحداته")

    # تعطّل بعد أن بدأ ← خطأ عادي في البرنامج (لا يُعلَّم معطوباً)
    late = g["read_jup_package"](make_jup("1.67.5", "import builtins\nbuiltins._FAKE_SYS._jadeite_hot_started = True\n"
                                                    "raise RuntimeError('بعد الفتح')\n"))
    g["install_hot_package"](late, KIND)
    builtins._FAKE_SYS = fake_sys
    fake_sys._jadeite_hot_started = False
    try:
        run()
        raise AssertionError("الخطأ بعد الفتح ابتُلع")
    except RuntimeError:
        pass
    assert not json.load(open(os.path.join(root, "current.json"), encoding="utf-8")).get("bad")
    fake_sys._jadeite_hot_running = False
    fake_sys.path.clear()
    print("✔ وخطأ بعد أن فتح البرنامج يبقى خطأً عادياً (لا يُخفى ولا يُعلَّم الإصدار معطوباً)")

    # ═══ ٤) الرجوع للإصدار السابق ═══
    assert g["read_hot_pointer"](KIND)["previous"] is None, "الإصدار المعطوب (1.67.4) لا يُحفظ «سابقاً» يُرجع إليه"
    g["install_hot_package"](g["read_jup_package"](make_jup("1.67.6", GOOD)), KIND)
    g["install_hot_package"](g["read_jup_package"](make_jup("1.67.7", GOOD)), KIND)
    assert g["rollback_hot_update"](KIND) == "1.67.6"
    assert g["read_hot_pointer"](KIND)["version"] == "1.67.6"
    assert g["rollback_hot_update"](KIND) == "exe" and g["read_hot_pointer"](KIND) is None
    assert g["rollback_hot_update"](KIND) is None
    print("✔ «↩️ الإصدار السابق»: يعيد المثبَّت قبل آخر تحديث، ثم البرنامج الأساسي نفسه — ولا يرجع لإصدار معطوب")

    # ═══ ٥) بيئة إعادة الفتح ═══
    os.environ.update({"_PYI_ARCHIVE_FILE": "x.exe", "_PYI_APPLICATION_HOME_DIR": "C:\\Temp\\_MEI123",
                       "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": "C:\\Temp\\_MEI123"})
    env = g["clean_relaunch_env"]()
    for k in ("_PYI_ARCHIVE_FILE", "_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PROCESS_LEVEL", "_MEIPASS2"):
        os.environ.pop(k, None)
        assert k not in env
    assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1" and env.get("PATH") == os.environ.get("PATH")
    print("✔ إعادة الفتح ببيئة نظيفة: متغيّرات PyInstaller الموروثة (مجلد فكّ exe القديم) تُحذف — "
          "كانت تمنع exe الجديد من الفتح بعد التحديث")

    # ═══ ٦) صانع الحزمة من ملفات المستودع ═══
    sys.path.insert(0, os.path.dirname(os.path.abspath(TARGET)))
    import make_update_package as mup
    out_dir = os.path.join(tmp, "dist")
    for kind in ("client", "admin"):
        path = mup.build_package(kind, out_dir, allow_missing_notes=False, regenerate_client=False)
        with zipfile.ZipFile(path) as zf:
            man = json.loads(zf.read("manifest.json"))
            names = set(zf.namelist())
            for n, d in man["files"].items():
                assert hashlib.sha256(zf.read(n)).hexdigest() == d
            blob = b"".join(zf.read(n) for n in names)
        entry = mup.KINDS[kind][0]
        assert man["kind"] == kind and man["entry"] == entry and os.path.basename(path).startswith(mup.KINDS[kind][1])
        assert man["version"] in man["notes"] and man["runtime"] == g["HOT_RUNTIME"]
        assert not re.search(rb"sb_secret_[A-Za-z0-9_-]{8,}", blob), "لا مفتاح سري في الحزمة"
        if kind == "client":
            assert "rageh-1-34-14-cloud.py" not in names, "حزمة العميل بلا ملف المدير"
            assert b"IS_ADMIN_BUILD = False" in blob
        assert os.path.getsize(path) < 1_200_000
        info = g["read_jup_package"](path)
        assert info["build"] == kind and info["entry"] == entry
    print(f"✔ صانع الحزمة: حزمتا العميل والمدير (أقل من ١٫٢ ميجا)، بصمات صحيحة، «ما الجديد» للإصدار، "
          f"وحزمة العميل بلا ملف المدير ولا مفتاح سري")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# ═══ ٧) في البرنامج ═══
i_run = src.index("\nrun_hot_update_if_newer()\n")
assert src.index("IS_ADMIN_BUILD = ") < i_run < src.index("from gold_price import GoldPriceWatcher")
assert i_run < src.index("load_brand_fonts()\n") and i_run < src.index("class GoldSystemApp")
main = src[src.index('if __name__ == "__main__":'):]
assert main.index("sys._jadeite_hot_started = True") < main.index("LoginWindow()")
rp = module_src("resource_path")
assert '_jadeite_hot_running' in rp and "_MEIPASS" in rp
dlg = body("open_app_update")
assert '"*.jup *.exe *.zip"' in dlg and "jup_notes_since(info, APP_VERSION)" in dlg
assert "install_hot_package(info, kind" in dlg and "self._relaunch" in dlg and "rollback_hot_update(kind)" in dlg
fast = dlg[dlg.index("def fast_update"):dlg.index("def go():")]
assert "askyesno" not in fast and "self.perform_backup()" in fast and "progress.set" in dlg
assert 'env=clean_relaunch_env()' in body("_relaunch") and 'env=clean_relaunch_env()' in body("_swap_to_update")
build_src = io.open(os.path.join(os.path.dirname(os.path.abspath(TARGET)), "build_exe.py"), encoding="utf-8").read()
assert "make_update_package.build_package(args.target" in build_src
print("✔ البرنامج: يفتح الإصدار المثبَّت قبل أي وحدة أو خط؛ النافذة تقبل ‎.jup وتعرض «ما الجديد» وتثبّت بلا سؤال "
      "إضافي بشريط تقدّم ثم تفتح الجديد، وزر الرجوع؛ وبناء exe يصنع حزمة ‎.jup بجانبه")

print("\n✅ التحديث السريع: حزمة صغيرة، ثوانٍ، «ما الجديد»، تحقق كامل، ورجوع آمن")

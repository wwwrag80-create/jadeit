# -*- coding: utf-8 -*-
"""اختبار شاشة الترحيب المتحركة ولوحة الدخول ونظام التصميم الموحّد"""
import ast, io, os, re, sys

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
login = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LoginWindow")
methods = {m.name: m for m in login.body if isinstance(m, ast.FunctionDef)}
seg = lambda name: ast.get_source_segment(src, methods[name])

# ═══ ١) منطق الدخول لم يتغيّر، والواجهة تعطيه ما يحتاجه ═══
tl = seg("try_login")
for attr in ("self.ent_user", "self.ent_pass", "self.lbl_status"):
    assert attr in tl, attr
build = seg("_build_login_form")
for attr in ("self.ent_user =", "self.ent_pass =", "self.lbl_status =", "self.btn_login ="):
    assert attr in build, attr
assert "command=self.try_login" in build and 'self.ent_pass.bind("<Return>", lambda e: self.try_login())' in build
print("✔ حقول الدخول وزر (دخول) وEnter كلها تستدعي try_login")
assert "CTkFrame" not in build and "_card" not in build
print("✔ بلا لوحة ولا إطار: الشعار والحقول تطفو على المشهد مباشرة")
cl = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_CanvasLabel")
cls_src = ast.get_source_segment(src, cl)
assert "def configure(self, text=None, text_color=None" in cls_src
print("✔ رسالة الحالة وتنبيه Caps Lock نصوص مرسومة تقبل configure(text=…) كما تستدعيها try_login")

gen = io.open("make_client_build.py", encoding="utf-8").read()
m = re.search(r"old_admin = '''(.*?)'''", gen, re.S)
if TARGET == "rageh-1-34-14-cloud.py":
    assert m and src.count(m.group(1)) == 1
    print("✔ مولّد نسخة العميل ما زال يجد كتلة دخول المدير ليحذفها")
else:
    assert "AdminPanel()" not in tl and "هذه النسخة مخصصة للعملاء فقط" in tl
    print("✔ نسخة العميل: شاشة الدخول لا تفتح لوحة المدير")

# ═══ ٢) ترحيل متحرك بملء الشاشة لا يمنع الدخول أبداً ═══
init = seg("__init__")
assert '"-fullscreen", True' in init
print("✔ تفتح بملء الشاشة")
for part in ("_draw_background", "_init_waves", "_init_particles", "_init_logo", "_init_splash_texts"):
    assert f"self.{part}()" in init, part
assert init.index("self._draw_background()") < init.index("log_cloud_error")
print("✔ المشهد: خلفية متدرّجة + هالة + أمواج + ذرّات ذهب + شعار + «مرحباً بك»")
assert "مرحباً بك" in seg("_init_splash_texts")
assert "_ripples" in seg("_init_splash_texts") and "def _update_ripples" in src
print("✔ حلقات تموّج ذهبية تتّسع من الشعار")
tick = seg("_tick")
assert "except Exception" in tick and "self._show_login_now()" in tick
print("✔ أي خلل في الرسوم يُظهر لوحة الدخول مباشرة (لا يُحبس المستخدم في الترحيب)")
assert 'self.bind("<Key>", self._skip_splash' in init and '"<Button-1>", self._skip_splash' in init
print("✔ أي ضغطة أو نقرة تتخطّى الترحيب")
assert "self._SPLASH_S" in tick
print("✔ الترحيب ينتقل تلقائياً للدخول بعد مدته")
assert "after_cancel(self._anim_job)" in seg("destroy") and "self._alive = False" in seg("destroy")
print("✔ الحركة تتوقف عند إغلاق النافذة (لا أخطاء بعد الدخول)")
assert 'state="hidden"' in build and "_apply_part(items, 1.0)" in seg("_show_form")
assert '"state": "normal"' in seg("_apply_part")
assert "self._update_form(" in tick
print("✔ الحقول مخفية أثناء الترحيب، ثم تظهر صاعدةً جزءاً بعد جزء")
assert "self._shake()" in tl
print("✔ خطأ الدخول: اهتزاز خفيف للحقول ورسالة واضحة (بلا نوافذ)")

# ═══ ٢-ب) بعد نجاح الدخول: لا إغلاق ولا نوافذ ═══
assert "self._run_in_background(verify)" in tl and "threading.Thread" in seg("_run_in_background")
print("✔ التحقق عبر الإنترنت في الخلفية — الأمواج لا تتجمّد")
i_out, i_sync = tl.index("self._begin_outro("), tl.index("SyncDownWindow(")
i_wait, i_app = tl.index("self._wait_outro()"), tl.index("GoldSystemApp(")
assert i_out < i_sync < i_wait < i_app
assert "on_progress=self._outro_progress" in tl
print("✔ الأمواج تغمر الشاشة، ورفع البيانات يظهر تحت «أهلاً بك» (لا نافذة منبثقة)")
assert "intro=spec" in tl and "tk._default_root = None" in tl
assert tl.index("tk._default_root = None") < i_app
i_destroy_after = tl.find("self.destroy()", i_out)
assert i_destroy_after == -1 or tl.index("except Exception:", i_app - 60) < i_destroy_after
print("✔ شاشة الدخول لا تُغلق قبل النظام: النظام يُبنى خلف آخر إطار ثم يغلقها هو")
assert "_wave_lift" in seg("_update_outro") and "tag_lower" in seg("_begin_outro")
print("✔ التموّج: الأمواج ترتفع طبقة بعد طبقة حتى تغمر الشاشة والشعار ينزل للمنتصف")

sw = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SyncDownWindow")
sw_init = ast.get_source_segment(src, next(m for m in sw.body if isinstance(m, ast.FunctionDef)
                                            and m.name == "__init__"))
assert "on_progress=None" in sw_init and "self.withdraw()" in sw_init
print("✔ نافذة تجهيز البيانات تعمل بلا ظهور عند الدخول المتحرك")

app = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
aseg = lambda n: ast.get_source_segment(src, next(m for m in app.body
                                                  if isinstance(m, ast.FunctionDef) and m.name == n))
ainit = aseg("__init__")
assert "intro=None" in ainit and ainit.index("self.withdraw()") < ainit.index("self.create_layout()")
assert "self._intro_show()" in ainit and "self._intro_abort()" in ainit
print("✔ النظام يُبنى مخفياً، وأي خلل في الانتقال يُظهره مباشرة")
show = aseg("_intro_show")
assert '"-alpha", 0.0' in show and "self._intro_draw()" in show and "_intro_watchdog" in show
assert show.index("self._intro_draw()") < show.index("self.update()")
fade = aseg("_intro_fade")
assert "login.destroy()" in fade and "_startup_first_calc" in fade
print("✔ يظهر فوق شاشة الدخول بالإطار نفسه ثم يغلقها — والغطاء لا يبقى أبداً (مراقب زمني)")
first = aseg("_startup_first_calc")
assert "finally:" in first and first.index("finally:") < first.index("_intro_reveal")
print("✔ الأمواج تنحسر عن الرئيسية حتى لو فشل الحساب الأول")
fin = aseg("_intro_finish")
assert "_home_count_up" in fin and "_sidebar_shimmer" in fin
print("✔ بعد الانكشاف: أرقام الرئيسية تُعدّ من الصفر وأزرار الشريط تلمع بالتتابع")

# ═══ ٣) لا تُحفظ كلمة المرور أبداً ═══
save = seg("_save_username_pref")
assert '"username"' in save and "password" not in save.lower() and "ent_pass" not in save
print("✔ «تذكّر اسم المستخدم» يحفظ الاسم فقط — كلمة المرور لا تُحفظ")
assert "0x2" in seg("_check_caps_lock")
print("✔ تنبيه عند تفعيل Caps Lock")
assert 'show="" if hidden else "●"' in seg("_toggle_password")
print("✔ زر إظهار/إخفاء كلمة المرور")

# ═══ ٤) الحساب الفعلي للألوان: المزج بديل الشفافية ═══
ns = {}
exec("class L:\n" + "\n".join("    " + ln for ln in seg("_mix").splitlines()) + "\n"
     + "\n".join("    " + ln for ln in seg("_ease").splitlines()), ns)
L = ns["L"]
assert L._mix("#000000", "#ffffff", 0) == "#000000"
assert L._mix("#000000", "#ffffff", 1) == "#ffffff"
assert L._mix("#000000", "#ffffff", 0.5) == "#808080"
assert L._mix("#102030", "#102030", 0.3) == "#102030"
assert L._mix("#000000", "#ffffff", 7) == "#ffffff"          # خارج المدى يُقصّ
assert L._ease(0) == 0 and L._ease(1) == 1 and L._ease(0.5) > 0.5
print("✔ مزج الألوان والحركة الناعمة صحيحة حسابياً")

# ═══ ٥) نظام التصميم الموحّد ═══
assert "ctk.CTkButton = ThemedButton" in src and "ctk.CTkLabel = ThemedLabel" in src
print("✔ كل الأزرار والنصوص تتبع لوحة ألوان موحّدة تلقائياً")
lb = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "load_brand_fonts")
lbs = ast.get_source_segment(src, lb)
assert 'if not sys.platform.startswith("win")' in lbs
assert 'os.path.join("fonts"' in lbs
for f in ("Cairo-Regular.ttf", "Cairo-Bold.ttf", "OFL.txt"):
    assert os.path.exists(os.path.join("fonts", f)), f
print("✔ خط Cairo العربي مرفق (برخصته المفتوحة) ويُحمَّل على ويندوز")

bx = io.open("build_exe.py", encoding="utf-8").read()
assert re.search(r'DATA_DIRS\s*=\s*\(\s*"fonts"', bx) and 'f"{d}{os.pathsep}{d}"' in bx
print("✔ ملف البناء يضمّن مجلد الخطوط داخل exe")

print("\n✅ شاشة الترحيب والدخول جاهزة")

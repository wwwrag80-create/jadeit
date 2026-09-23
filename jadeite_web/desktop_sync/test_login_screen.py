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
build = seg("_build_login_card")
for attr in ("self.ent_user =", "self.ent_pass =", "self.lbl_status =", "self.btn_login ="):
    assert attr in build, attr
assert "command=self.try_login" in build and 'self.ent_pass.bind("<Return>", lambda e: self.try_login())' in build
print("✔ حقول الدخول وزر (دخول) وEnter كلها تستدعي try_login نفسها بلا تغيير")

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
assert 'state="hidden"' in build and 'state="normal"' in seg("_show_form")
print("✔ لوحة الدخول مخفية أثناء الترحيب وتظهر بعده")

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

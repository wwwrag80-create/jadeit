# دليل التشغيل الكامل — نظام جاديت السحابي

اتبع الخطوات بالترتيب. كل خطوة فيها **ماذا تفعل بالضبط**.

---

## الجزء الأول: إصلاح الأخطاء التي ظهرت عندك

ظهر عندك خطآن، وسببهما معروف:

| الخطأ الذي ظهر | السبب |
|---|---|
| `Could not find the table 'public.app_users' in the schema cache` | الجداول لم تُنشأ بعد، أو أُنشئت وذاكرة PostgREST لم تُحدَّث |
| `Database error querying schema` (500) | خدمة المصادقة في Supabase معطّلة — غالباً بسبب **محفّز (trigger) مضاف على `auth.users`** أو **صلاحيات ناقصة** بعد أوامر SQL سابقة |

> اكتشفت أيضاً خطأً في سكربتاتي أنا: كنت أستخدم `FORCE ROW LEVEL SECURITY`، وهي تُبطل مفعول دوال `SECURITY DEFINER` فتسبب **تكراراً لا نهائياً** عند قراءة `app_users`. أزلتها نهائياً في النسخة المرفقة.

---

## الجزء الثاني: خطوات التنفيذ في Supabase

### 🔹 الخطوة ١ — إصلاح خدمة المصادقة
1. افتح مشروعك في Supabase.
2. من القائمة اليمنى: **SQL Editor** ← **New query**.
3. افتح ملف `supabase/00_repair_auth.sql` وانسخ **كل** محتواه والصقه.
4. اضغط **Run**.
5. في نتيجة آخر استعلام يجب أن تكون قيمة `محفزات_متبقية` = **0**.

### 🔹 الخطوة ٢ — إعادة تشغيل المشروع
**Settings** ← **General** ← **Restart project** ← انتظر دقيقة.

> هذه الخطوة ضرورية: خدمة المصادقة تحتفظ باتصالات قديمة، وبدون إعادة التشغيل قد يستمر خطأ 500 رغم الإصلاح.

### 🔹 الخطوة ٣ — تثبيت قاعدة البيانات كاملة
1. **SQL Editor** ← **New query**.
2. الصق كل محتوى `supabase/INSTALL_ALL.sql`.
3. **Run**.
4. في النتيجة الأخيرة يجب أن ترى: `التثبيت اكتمل ✔`، وقبلها جدول بالدوال المتاحة لـ anon
   (المتوقع: دوال `sync_*` و`client_login_full` فقط — أي دالة أخرى تظهر بعلامة ⚠️ راجِعها).

> هذا الملف يجمع كل شيء بالترتيب الصحيح: الجداول ← سياسات الحماية ← الدوال ← التهيئة ← الموديولات. **لا تشغّل الملفات المرقّمة منفردة** — هذا الملف يغني عنها.

### 🔹 الخطوة ٤ — إنشاء مستخدم الدخول
1. **Authentication** ← **Users** ← **Add user** ← **Create new user**.
2. أدخل بريدك وكلمة مرور (٦ أحرف فأكثر).
3. ✅ **فعّل خيار `Auto Confirm User`** — هذا أهم شيء في هذه الخطوة. بدونه ستحصل على خطأ `Invalid login credentials` مهما كانت كلمة المرور صحيحة.
4. اضغط **Create user**.

### 🔹 الخطوة ٥ — ربط المستخدم كمدير + إنشاء أول مصنع
1. افتح `supabase/01_create_admin.sql`.
2. غيّر السطر: `v_admin_email text := 'admin@jadeite.com';` ← **ضع بريدك الذي أنشأته للتو**.
3. الصقه في SQL Editor ← **Run**.
4. يجب أن تظهر رسائل: `✅ تم ربط المدير` و`✅ تم إنشاء المصنع` وجدول فيه المدير والمصنع والحسابات.

### 🔹 الخطوة ٦ — نسخ مفاتيح الاتصال
**Settings** ← **API** ← انسخ:
- `Project URL`
- `anon` `public` key

> ⚠️ **لا تنسخ `service_role` أبداً ولا تضعه في التطبيق.** التطبيق يُسلَّم للعملاء، وهذا المفتاح يتخطى كل سياسات الحماية ويكشف بيانات كل عملائك.

---

## الجزء الثالث: تشغيل التطبيق

```bash
cd jadeite_web
flutter clean
flutter pub get
```

ثم شغّل (استبدل القيمتين بمفاتيحك):

```bash
flutter run -d chrome ^
  --dart-define=SUPABASE_URL=https://xxxxx.supabase.co ^
  --dart-define=SUPABASE_ANON_KEY=eyJhbGci...
```

> على Windows استخدم `^` كما بالأعلى. على Mac/Linux استخدم `\` بدلاً منها.

**فحص قبل التشغيل** (اختياري لكنه يوفّر وقتاً):

```bash
python3 tools/check_project.py
flutter analyze
```

---

## الجزء الرابع: البناء والنشر كبرنامج سطح مكتب

```bash
flutter build web --release ^
  --dart-define=SUPABASE_URL=https://xxxxx.supabase.co ^
  --dart-define=SUPABASE_ANON_KEY=eyJhbGci...
```

انشر مجلد `build/web` على أي استضافة **HTTPS** (Netlify / Vercel / Cloudflare Pages).
افتح الرابط في Chrome ← سيظهر زر **⬇️ تثبيت البرنامج على الجهاز** ← اضغطه فيصبح برنامجاً مستقلاً بلا شريط متصفح.

> التثبيت لا يعمل على `http://` ولا على `localhost` بشكل كامل — لا بد من HTTPS.

---

## إذا استمر خطأ 500 بعد كل ما سبق

هذا يعني تلفاً أعمق في مخطط `auth` بسبب أوامر سابقة. جرّب بالترتيب:

1. شغّل هذا للتشخيص وأرسل لي النتيجة:

```sql
select t.tgname, pg_get_triggerdef(t.oid)
  from pg_trigger t
  join pg_class c on c.oid = t.tgrelid
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname='auth' and c.relname='users' and not t.tgisinternal;

select rolname from pg_roles where rolname like 'supabase%';
select count(*) from auth.users;
```

2. إن لم يُحلّ: **أنشئ مشروع Supabase جديداً** وشغّل عليه الخطوات ١–٦ من البداية. المشروع الجديد يستغرق دقيقتين، وأسرع بكثير من مطاردة تلف في مخطط المصادقة.

---

## جدول الأخطاء الشائعة وحلولها

| الرسالة | الحل المباشر |
|---|---|
| `Could not find the table ... schema cache` | شغّل `INSTALL_ALL.sql` ثم `notify pgrst, 'reload schema';` |
| `Database error querying schema` (500) | `00_repair_auth.sql` + Restart project |
| `Invalid login credentials` | فعّل **Auto Confirm User** للمستخدم، أو صحّح كلمة المرور |
| `الحساب غير مربوط بالنظام` | شغّل `01_create_admin.sql` ببريدك |
| `infinite recursion detected in policy` | نسخة قديمة من `02_rls.sql` — استخدم `INSTALL_ALL.sql` المرفق |
| `row-level security` عند الحفظ | التعديل مقفول من المدير، أو تحاول الوصول لمصنع غير مصنعك |
| `Invalid API key` | راجع `--dart-define` — المفتاح ناقص أو خاطئ |

التطبيق الآن يترجم كل هذه الأخطاء تلقائياً إلى رسائل عربية تقول لك ماذا تفعل، بدل عرض النص الإنجليزي الخام.

---

# المعمارية الهجينة (تحديث)

```
   جهاز العميل                        السحابة                     جهازك أنت
┌──────────────────┐            ┌────────────────┐          ┌──────────────────┐
│  rageh.exe       │  RPC only  │   Supabase     │   Auth   │  لوحة الويب       │
│  CustomTkinter   │ ─────────► │  transactions  │ ◄──────  │  Flutter PWA     │
│  SQLite (محلي)   │  anon key  │  + RLS         │  + RLS   │  انتحال شخصية    │
│  خيط مزامنة صامت │            │  tenant_id     │ Realtime │  بث لحظي         │
└──────────────────┘            └────────────────┘          └──────────────────┘
     يعمل بدون إنترنت              مصدر التجميع              للمدير العام فقط
```

## خطوات التفعيل

### ١) في Supabase
شغّل `supabase/06_hybrid_sync.sql` بعد `INSTALL_ALL.sql`. سيطبع لك في النهاية
جدولاً فيه `tenant_id` و`sync_token` لكل عميل — احتفظ به.

ثم فعّل البث اللحظي: **Database ← Replication ← supabase_realtime** وتأكد أن
`transactions` و`tenant_devices` مفعّلان (السكربت يحاول تفعيلهما تلقائياً).

### ٢) في برنامج العملاء
اتبع `desktop_sync/INTEGRATION_AR.md` — ٣ أسطر في الكود، ثم ضع
`tenant_id` و`sync_token` في `device_session.json` على جهاز كل عميل.

### ٣) في لوحتك
سجّل الدخول كمدير ← ستجد أيقونة **☁️ متابعة المزامنة** في الشريط العلوي:
من متصل الآن، كم حركة عالقة عند كل عميل، آخر خطأ، وزر دخول مباشر على حسابه.

## ملاحظة أمنية أساسية

برنامج سطح المكتب يُوزَّع على العملاء، لذا يمكن استخراج مفتاح `anon` منه.
لهذا السبب صمّمت الطبقة بحيث:

- `anon` **ممنوع من قراءة أي جدول** (`revoke all ... from anon`)
- كل ما يستطيعه هو استدعاء دوال المزامنة، وكل دالة تتحقق من `sync_token` السرّي أولاً
- الرمز خاص بكل عميل، ويمكنك إبطاله بضغطة زر من لوحتك

النتيجة: من يستخرج المفتاح من ملف exe لا يستطيع قراءة أي شيء، ولا الكتابة إلا
لحساب العميل الذي يملك رمزه هو.

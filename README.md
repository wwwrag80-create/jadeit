# جاديت — نظام إدارة مصانع الذهب

كل المشروع داخل المجلد [`jadeite_web/`](jadeite_web/):

| الجزء | المكان |
|---|---|
| **تقرير المراجعة الشاملة والإصلاحات** — ابدأ منه | [`jadeite_web/REVIEW_AR.md`](jadeite_web/REVIEW_AR.md) |
| لوحة الويب (Flutter Web + PWA) | [`jadeite_web/lib/`](jadeite_web/lib/) — الدليل: [`README.md`](jadeite_web/README.md) |
| قاعدة البيانات (Supabase) | [`jadeite_web/supabase/`](jadeite_web/supabase/) — شغّل `INSTALL_ALL.sql` |
| برنامج سطح المكتب ومزامنته (Python) | [`jadeite_web/desktop_sync/`](jadeite_web/desktop_sync/) |
| أداة ترحيل البيانات القديمة | [`jadeite_web/migration/`](jadeite_web/migration/) |

الفحوص الآلية تعمل مع كل دفعة على GitHub: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

> ⚠️ لا ترفع أي مفتاح سري (`sb_secret_…` / `service_role`) إلى هذا المستودع — إنه **عام**.
> مفتاح نسخة المدير يوضع في `jadeite_web/desktop_sync/admin_secret.key` على جهازك فقط.

-- ============================================================================
--  اختبارات 23_cloud_accounts_only.sql — السحابة للحسابات والصلاحيات وحدها (آخر الاختبارات):
--    • النسخ الكاملة تُحذف، ورفع نسخة بعدها (برنامج عميل قديم) يُتجاهل بلا خطأ ولا صف.
--    • جدول روابط 1.94 ودالته يُحذفان إن وُجدا.
--    • لا يُمسّ: العملاء ورموز مزامنتهم، والدخول والفحص الدوري.
--    • آمن لإعادة التشغيل.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

create table if not exists public.db_backups (client_id uuid primary key, backup_data text, updated_at timestamptz);
insert into public.db_backups values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'FULL-COPY', now())
    on conflict (client_id) do update set backup_data = excluded.backup_data;
create table if not exists public.live_links (client_id uuid primary key, url text);
select set_config('jadeite.tenants_before', count(*)::text, false) from public.tenants \g /dev/null
select set_config('jadeite.clients_before', count(*)::text, false) from public.clients \g /dev/null

\i supabase/23_cloud_accounts_only.sql
\i supabase/23_cloud_accounts_only.sql

do $$
begin
    assert (select count(*) from public.db_backups) = 0, 'النسخ الكاملة حُذفت';
    insert into public.db_backups values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'OLD-CLIENT', now());
    assert (select count(*) from public.db_backups) = 0, 'رفع برنامج قديم يُتجاهل بلا خطأ';
    assert to_regclass('public.live_links') is null, 'جدول روابط 1.94 حُذف';
    assert (select count(*) from public.tenants) = current_setting('jadeite.tenants_before')::int, 'المصانع كما هي';
    assert (select count(*) from public.clients) = current_setting('jadeite.clients_before')::int, 'الحسابات كما هي';
    assert exists (select 1 from pg_proc where proname = 'client_access_check'), 'الفحص الدوري باقٍ';
    assert exists (select 1 from pg_proc where proname = 'client_login_v2'), 'الدخول باقٍ';
end $$;

select '✔ السحابة للحسابات والصلاحيات وحدها: النسخ حُذفت ولا تمتلئ، والحسابات والدخول كما هي' as النتيجة;

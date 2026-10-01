-- ============================================================================
--  اختبارات 17_backup_security.sql — النسخة الكاملة لا تُنزَّل بالمفتاح العام،
--  ولا تُرفع بالدالة الجديدة إلا برمز مزامنة العميل نفسه، والرفع القديم لا يتوقف
--  قبل المرحلة الثانية. دالتا النظام القديم تُحاكَيان هنا بالشكلين (uuid/نص).
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

select sync_token as b_token from public.tenants
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \gset

-- ---------------------------------------------------------------------------
--  ١) النظام القديم: دالتا الرفع والتنزيل SECURITY DEFINER ومعرّف uuid، متاحتان لـ anon
-- ---------------------------------------------------------------------------
drop function if exists public.upload_backup(uuid, text);
drop function if exists public.upload_backup(text, text);
drop function if exists public.download_backup(uuid);
drop table if exists public.db_backups;
create table if not exists public.db_backups (
    client_id   uuid primary key,
    backup_data text,
    updated_at  timestamptz default now()
);
grant all on public.db_backups to anon, authenticated;
create or replace function public.upload_backup(p_client_id uuid, p_backup_data text)
returns void language sql security definer set search_path = public as $$
    insert into public.db_backups (client_id, backup_data, updated_at) values (p_client_id, p_backup_data, now())
    on conflict (client_id) do update set backup_data = excluded.backup_data, updated_at = now();
$$;
create or replace function public.download_backup(p_client_id uuid)
returns table (out_backup_data text) language sql security definer set search_path = public as $$
    select backup_data from public.db_backups where client_id = p_client_id;
$$;
grant execute on function public.upload_backup(uuid, text) to anon, authenticated;
grant execute on function public.download_backup(uuid) to anon, authenticated;

\i supabase/17_backup_security.sql

do $$
begin
    assert not has_function_privilege('anon', 'public.download_backup(uuid)', 'execute'),
        'التنزيل ما زال متاحاً للمفتاح العام';
    assert not has_function_privilege('authenticated', 'public.download_backup(uuid)', 'execute'),
        'التنزيل متاح لأي مستخدم مسجّل';
    assert has_function_privilege('service_role', 'public.download_backup(uuid)', 'execute'),
        'مفتاح المدير (service_role) فقد التنزيل';
    assert has_function_privilege('anon', 'public.upload_backup_secure(uuid, uuid, text)', 'execute'),
        'برنامج العميل لا يستطيع الرفع الجديد';
    assert has_function_privilege('anon', 'public.upload_backup(uuid, text)', 'execute'),
        'المرحلة الأولى أوقفت الرفع القديم (عملاء ما قبل ١٫٥٠)';
    assert not has_table_privilege('anon', 'public.db_backups', 'select'),
        'جدول النسخ ما زال مقروءاً بالمفتاح العام';
    assert not has_table_privilege('anon', 'public.db_backups', 'insert'),
        'جدول النسخ ما زال قابلاً للكتابة بالمفتاح العام';
end $$;

-- رمز خاطئ يُرفض، والصحيح يحفظ بدالة الحفظ القديمة نفسها
begin;
set local role anon;
do $$
begin
    begin
        perform public.upload_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                            gen_random_uuid(), 'U1FMaXRl');
        raise exception 'رفعٌ برمز خاطئ قُبل';
    exception when sqlstate '28000' then
        null;
    end;
end $$;
select public.upload_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid, 'SkFERVoxCnh5eg==')
    \g /dev/null
commit;

do $$
begin
    assert (select backup_data from public.db_backups
             where client_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') = 'SkFERVoxCnh5eg==',
        'الرفع برمز صحيح لم يحفظ النسخة';
    assert (select count(*) from public.db_backups) = 1, 'الرفع المرفوض ترك أثراً';
end $$;

-- نسخة فارغة تُرفض حتى برمز صحيح
begin;
select set_config('jadeit.test_token', :'b_token', true) \g /dev/null
set local role anon;
do $$
begin
    begin
        perform public.upload_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                            current_setting('jadeit.test_token')::uuid, '');
        raise exception 'نسخة فارغة قُبلت';
    exception when sqlstate '22023' then
        null;
    end;
end $$;
commit;

-- ---------------------------------------------------------------------------
--  ٢) نظام قديم بمعرّف نصّي ودالة حفظ INVOKER: الجدول لا يُغلق (حتى لا يتوقف الرفع)
--     والرفع الجديد يعمل عبر الفرع النصّي
-- ---------------------------------------------------------------------------
drop function if exists public.upload_backup(uuid, text);
drop function if exists public.download_backup(uuid);
drop table if exists public.db_backups;
create table if not exists public.db_backups (
    client_id   text primary key,
    backup_data text,
    updated_at  timestamptz default now()
);
grant all on public.db_backups to anon, authenticated;
create or replace function public.upload_backup(p_client_id text, p_backup_data text)
returns void language sql security invoker set search_path = public as $$
    insert into public.db_backups (client_id, backup_data, updated_at) values (p_client_id, p_backup_data, now())
    on conflict (client_id) do update set backup_data = excluded.backup_data, updated_at = now();
$$;
grant execute on function public.upload_backup(text, text) to anon, authenticated;

\i supabase/17_backup_security.sql

do $$
begin
    assert has_table_privilege('anon', 'public.db_backups', 'insert'),
        'أُغلق الجدول مع دالة حفظ INVOKER فتوقف الرفع القديم';
end $$;

begin;
set local role anon;
select public.upload_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid, 'TkVX') \g /dev/null
commit;
do $$
begin
    assert (select backup_data from public.db_backups
             where client_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') = 'TkVX',
        'الرفع الجديد لم يعمل مع معرّف نصّي';
end $$;

-- تنظيف: محاكاة النظام القديم لا تبقى في قاعدة الاختبار
drop function if exists public.upload_backup(text, text);
drop table if exists public.db_backups;

select '✔ النسخة الكاملة: التنزيل للمدير وحده، والرفع الجديد برمز العميل، والقديم يعمل حتى المرحلة الثانية' as النتيجة;

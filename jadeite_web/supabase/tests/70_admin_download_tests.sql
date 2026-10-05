-- ============================================================================
--  اختبارات 20_admin_download.sql — برنامج المدير ينزّل نسخة العميل برمز مزامنته:
--    • الرمز الصحيح ينزّل النسخة، والخاطئ أو رمز عميل آخر يُرفض.
--    • المفتاح العام وحده (التنزيل القديم) يبقى مرفوضاً كما في 17.
--    • وقت آخر نسخة: '' إن لم تُرفع بعد، والوقت إن وُجدت.
--    • تقرير النسخ للمدير وحده، ويبيّن من له نسخة ومن ليس له.
--    • يعمل مع دالتي النظام القديم بمعرّف uuid أو نص.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

select sync_token as b_token from public.tenants where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \gset
select sync_token as a_token from public.tenants where id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' \gset

-- ---------------------------------------------------------------------------
--  ١) النظام القديم بمعرّف uuid (كما في اختبار 40)، ثم 17 ثم 20
-- ---------------------------------------------------------------------------
drop function if exists public.upload_backup(uuid, text);
drop function if exists public.upload_backup(text, text);
drop function if exists public.download_backup(uuid);
drop function if exists public.download_backup(text);
drop table if exists public.db_backups;
create table public.db_backups (client_id uuid primary key, backup_data text, updated_at timestamptz default now());
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
\i supabase/20_admin_download.sql
\i supabase/20_admin_download.sql

-- العميل b رفع نسخته برمزه
begin;
set local role anon;
select public.upload_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid, 'SkFERVgxCmZ1bGw=')
    \g /dev/null
commit;

-- ---------------------------------------------------------------------------
--  ٢) برنامج المدير (المفتاح العام + رمز العميل) ينزّل النسخة
-- ---------------------------------------------------------------------------
begin;
select set_config('jadeit.b_token', :'b_token', true) \g /dev/null
select set_config('jadeit.a_token', :'a_token', true) \g /dev/null
set local role anon;
do $$
declare
    v text;
begin
    select out_backup_data into v
      from public.download_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                         current_setting('jadeit.b_token')::uuid);
    assert v = 'SkFERVgxCmZ1bGw=', 'الرمز الصحيح لم ينزّل النسخة';

    -- رمز خاطئ
    begin
        perform * from public.download_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', gen_random_uuid());
        raise exception 'تنزيل برمز خاطئ قُبل';
    exception when sqlstate '28000' then null;
    end;

    -- رمز عميل آخر لا يفتح نسخة b
    begin
        perform * from public.download_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                                     current_setting('jadeit.a_token')::uuid);
        raise exception 'رمز عميل آخر فتح النسخة';
    exception when sqlstate '28000' then null;
    end;

    -- التنزيل القديم بالمفتاح العام وحده ما زال مرفوضاً
    begin
        perform * from public.download_backup('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
        raise exception 'التنزيل القديم بالمفتاح العام قُبل';
    exception when insufficient_privilege then null;
    end;

    -- وقت آخر نسخة: موجود لـ b، و'' لـ a (لم يرفع)
    assert coalesce(public.backup_stamp_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                               current_setting('jadeit.b_token')::uuid), '') <> '',
        'وقت نسخة b غير معروف';
    assert public.backup_stamp_secure('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                                      current_setting('jadeit.a_token')::uuid) = '',
        'عميل بلا نسخة لم يُرجع فراغاً';
    assert not exists (select 1 from public.download_backup_secure('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
                                                                   current_setting('jadeit.a_token')::uuid)),
        'عميل بلا نسخة أرجع شيئاً';
end $$;
commit;

-- ---------------------------------------------------------------------------
--  ٣) التقرير: للمدير وحده، ويبيّن من له نسخة
-- ---------------------------------------------------------------------------
do $$
declare
    v_name text := (select business_name from public.tenants where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
begin
    assert not has_function_privilege('anon', 'public.backup_status_report()', 'execute'),
        'التقرير متاح للمفتاح العام';
    assert has_function_privilege('anon', 'public.download_backup_secure(uuid, uuid)', 'execute'),
        'برنامج المدير لا يستطيع التنزيل برمز العميل';
    assert (select الحالة from public.backup_status_report() where العميل = v_name) like '✔%',
        'التقرير لا يرى نسخة b';
    assert (select آخر_نسخة_كاملة from public.backup_status_report() where العميل = v_name) is not null,
        'التقرير بلا وقت آخر نسخة';

    delete from public.db_backups;
    assert (select الحالة from public.backup_status_report() where العميل = v_name) like '⚠️%',
        'التقرير لا ينبّه على عميل بلا نسخة';
end $$;

-- ---------------------------------------------------------------------------
--  ٤) النظام القديم بمعرّف نصّي
-- ---------------------------------------------------------------------------
drop function if exists public.upload_backup(uuid, text);
drop function if exists public.download_backup(uuid);
drop table if exists public.db_backups;
create table public.db_backups (client_id text primary key, backup_data text, updated_at timestamptz default now());
insert into public.db_backups values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'VEVYVA==', now());
create or replace function public.download_backup(p_client_id text)
returns table (out_backup_data text) language sql security definer set search_path = public as $$
    select backup_data from public.db_backups where client_id = p_client_id;
$$;
revoke execute on function public.download_backup(text) from public, anon, authenticated;

begin;
select set_config('jadeit.b_token', :'b_token', true) \g /dev/null
set local role anon;
do $$
begin
    assert (select out_backup_data from public.download_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                current_setting('jadeit.b_token')::uuid)) = 'VEVYVA==', 'التنزيل لم يعمل مع معرّف نصّي';
    assert public.backup_stamp_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                      current_setting('jadeit.b_token')::uuid) <> '', 'الوقت لم يعمل مع معرّف نصّي';
end $$;
commit;

-- بلا دالة التنزيل القديمة: رسالة واضحة لا نسخة فارغة
drop function public.download_backup(text);
begin;
select set_config('jadeit.b_token', :'b_token', true) \g /dev/null
set local role anon;
do $$
begin
    begin
        perform * from public.download_backup_secure('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
                                                     current_setting('jadeit.b_token')::uuid);
        raise exception 'غياب دالة التنزيل لم يُبلَّغ';
    exception when sqlstate 'P0002' then null;
    end;
end $$;
commit;

-- تنظيف
drop table if exists public.db_backups;
\echo '   ✔ تنزيل المدير برمز العميل: الصحيح ينزّل، والخاطئ وعميل آخر والمفتاح العام وحده مرفوضة، والتقرير يبيّن من له نسخة'

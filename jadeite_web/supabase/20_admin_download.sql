-- ============================================================================
--  جاديت ERP — برنامج المدير ينزّل نسخة العميل برمز مزامنة العميل نفسه (الدفعة ٢٢)
--
--  المشكلة: منذ 17_backup_security.sql صار التنزيل (download_backup) لمفتاح المدير
--  وحده. فإن دخل برنامج المدير باسم العميل وكلمة مروره — بلا مفتاح المدير على الجهاز —
--  رُفض التنزيل، وكان احتياط «سجل حركات الويب» يُخفي ذلك. بعد إزالة الويب (الدفعة ٢١)
--  ظهر: «تعذّر تنزيل بيانات العميل من السحابة».
--
--  الحل — مثل الرفع تماماً (upload_backup_secure):
--    ١) download_backup_secure(العميل، رمز المزامنة): لا يعطي النسخة إلا لمن يحمل رمز
--       مزامنة العميل نفسه (يصل مع دخوله الصحيح باسمه وكلمة مروره) — أو مفتاح المدير.
--    ٢) backup_stamp_secure(العميل، رمز المزامنة): وقت آخر نسخة فقط (طلب خفيف)، فيعرف
--       برنامج المدير متى يرفع العميل نسخة أحدث فيعرضها تلقائياً.
--    ٣) backup_status_report(): تقرير للمدير — لكل عميل: هل له نسخة كاملة؟ ومتى آخر رفع؟
--
--  الأمان كما هو: المفتاح العام وحده (بلا رمز العميل) لا ينزّل شيئاً، ورمز عميل لا
--  يفتح نسخة عميل آخر. ولا يغيّر هذا الملف مكان الحفظ ولا شكله.
--
--  آمن لإعادة التشغيل، ولا يفشل في تثبيت جديد بلا دوال النظام القديم. شغّله بعد 17.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) التنزيل برمز مزامنة العميل
-- ----------------------------------------------------------------------------
create or replace function public.download_backup_secure(
    p_client_id  uuid,
    p_sync_token uuid
)
returns table (out_backup_data text)
language plpgsql security definer set search_path = public as $$
declare
    v_arg regtype;
begin
    -- رمز مزامنة العميل نفسه (أو مفتاح المدير) وإلا رُفض الطلب
    perform public.assert_sync_token(p_client_id, p_sync_token);

    -- التنزيل بدالة النظام القديم نفسها: معرّف العميل فيها uuid أو نص — يُقرأ من تعريفها
    select p.proargtypes[0]::regtype
      into v_arg
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'download_backup' and p.pronargs = 1
     order by p.oid
     limit 1;

    if v_arg is null then
        raise exception 'دالة تنزيل النسخة (download_backup) غير موجودة' using errcode = 'P0002';
    end if;

    return query execute format('select d.out_backup_data::text from public.download_backup($1::%s) d', v_arg)
        using p_client_id::text;
end $$;

revoke all on function public.download_backup_secure(uuid, uuid) from public;
grant execute on function public.download_backup_secure(uuid, uuid) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  ٢) وقت آخر نسخة — '' إن لم تُرفع نسخة بعد، وnull إن تعذّرت معرفته
-- ----------------------------------------------------------------------------
create or replace function public.backup_stamp_secure(
    p_client_id  uuid,
    p_sync_token uuid
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_stamp text;
begin
    perform public.assert_sync_token(p_client_id, p_sync_token);

    if to_regclass('public.db_backups') is null or not exists (
            select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'db_backups' and column_name = 'updated_at') then
        return null;
    end if;

    execute 'select max(updated_at)::text from public.db_backups where client_id::text = $1'
       into v_stamp
      using p_client_id::text;
    return coalesce(v_stamp, '');
end $$;

revoke all on function public.backup_stamp_secure(uuid, uuid) from public;
grant execute on function public.backup_stamp_secure(uuid, uuid) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  ٣) تقرير النسخ الكاملة لكل عميل (للمدير وحده — من SQL Editor أو بمفتاحه)
-- ----------------------------------------------------------------------------
create or replace function public.backup_status_report()
returns table (العميل text, آخر_نسخة_كاملة text, الحجم text, الحالة text)
language plpgsql security definer set search_path = public as $$
declare
    v_names text;
    v_time  text;
begin
    if to_regclass('public.clients') is not null then
        v_names := 'select client_id::text as id, business_name::text as name from public.clients';
    else
        v_names := 'select id::text as id, business_name::text as name from public.tenants';
    end if;

    if to_regclass('public.db_backups') is null then
        return query execute
            'select n.name, null::text, null::text, ''⚠️ جدول النسخ الكاملة db_backups غير موجود''::text
               from (' || v_names || ') n order by 1';
        return;
    end if;

    v_time := case when exists (select 1 from information_schema.columns
                                 where table_schema = 'public' and table_name = 'db_backups'
                                   and column_name = 'updated_at')
                   then 'to_char(max(b.updated_at) at time zone ''Asia/Riyadh'', ''YYYY-MM-DD HH24:MI'')'
                   else 'null::text' end;

    return query execute format(
        'select n.name,
                %s,
                pg_size_pretty(sum(pg_column_size(b.*))::bigint),
                case when count(b.*) = 0
                     then ''⚠️ لا نسخة كاملة — افتح برنامج العميل على جهازه وهو متصل بالإنترنت''
                     else ''✔ موجودة — برنامج المدير يفتحها'' end
           from (%s) n
           left join public.db_backups b on b.client_id::text = n.id
          group by n.id, n.name
          order by 1', v_time, v_names);
end $$;

revoke all on function public.backup_status_report() from public, anon, authenticated;
grant execute on function public.backup_status_report() to service_role;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  التقرير الآن: لكل عميل — هل وصلت نسخته الكاملة؟ ومتى آخر رفع (بتوقيت الرياض)؟
--  «لا نسخة» = برنامج العميل لم يرفع بعد: افتحه على جهازه متصلاً بالإنترنت دقيقة واحدة.
-- ----------------------------------------------------------------------------
select * from public.backup_status_report();

-- ============================================================================
--  جاديت ERP — حماية النسخة الكاملة على السحابة (جدول db_backups)
--
--  النسخة الكاملة = قاعدة SQLite لجهاز العميل كما هي، يرفعها برنامج العميل
--  ويفتحها برنامج المدير مرآةً حرفية. دالتا الرفع والتنزيل من النظام القديم
--  (upload_backup / download_backup) وليستا في هذا المستودع، وكانتا متاحتين
--  لـ anon — والمفتاح العام موجود داخل برنامج العميل:
--    • download_backup(معرّف): من يعرف معرّف عميل ينزّل قاعدته كاملة.
--    • upload_backup(معرّف، بيانات): يكتب فوق نسخة أي عميل بلا رمز.
--
--  بعد هذا الملف (المرحلة الأولى — آمنة الآن، لا توقف أي نسخة قديمة):
--    ١) upload_backup_secure(العميل، رمز المزامنة، البيانات): لا يقبل إلا رمز
--       مزامنة العميل نفسه (assert_sync_token)، ثم يحفظ بدالة الحفظ القديمة نفسها،
--       فلا يتغيّر مكان الحفظ ولا شكله. برنامج العميل ١٫٥٠ فما بعد يرفع بها،
--       ويرجع للدالة القديمة تلقائياً ما لم يُشغَّل هذا الملف.
--    ٢) download_backup للمدير وحده (مفتاح الخدمة service_role) — نسخة العميل
--       لا تنزّل من السحابة أبداً، ونسخة المدير تقرأ بمفتاحه.
--    ٣) جدول db_backups يُغلق أمام anon و authenticated إن كانت دالة الحفظ القديمة
--       SECURITY DEFINER (لا تحتاج صلاحية المتصل على الجدول)؛ وإلا يبقى كما هو
--       ويظهر في التقرير آخر الملف.
--
--  المرحلة الثانية (بعد تحديث كل العملاء إلى ١٫٥٠): انظر آخر الملف.
--
--  آمن لإعادة التشغيل، ولا يفشل في تثبيت جديد بلا دوال النظام القديم.
-- ============================================================================

create or replace function public.upload_backup_secure(
    p_client_id   uuid,
    p_sync_token  uuid,
    p_backup_data text
)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_arg regtype;
begin
    -- رمز مزامنة العميل نفسه وإلا رُفض الطلب (الرسالة نفسها مبهمة عمداً)
    perform public.assert_sync_token(p_client_id, p_sync_token);

    if p_backup_data is null or length(p_backup_data) = 0 then
        raise exception 'النسخة المرفوعة فارغة' using errcode = '22023';
    end if;

    -- الحفظ بدالة النظام القديم نفسها: معرّف العميل فيها uuid أو نص — يُقرأ من تعريفها
    select p.proargtypes[0]::regtype
      into v_arg
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'upload_backup' and p.pronargs = 2
     order by p.oid
     limit 1;

    if v_arg is null then
        raise exception 'دالة حفظ النسخة (upload_backup) غير موجودة' using errcode = '42883';
    elsif v_arg = 'uuid'::regtype then
        perform public.upload_backup(p_client_id, p_backup_data);
    else
        perform public.upload_backup(p_client_id::text, p_backup_data);
    end if;
end $$;

revoke all on function public.upload_backup_secure(uuid, uuid, text) from public;
grant execute on function public.upload_backup_secure(uuid, uuid, text) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  التنزيل للمدير وحده، والجدول مغلق متى أمكن دون كسر الرفع القديم
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_definer boolean;
begin
    for r in
        select p.oid::regprocedure as sig
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = 'download_backup'
    loop
        execute format('revoke execute on function %s from public, anon, authenticated', r.sig);
        if exists (select 1 from pg_roles where rolname = 'service_role') then
            execute format('grant execute on function %s to service_role', r.sig);
        end if;
    end loop;

    if to_regclass('public.db_backups') is not null then
        select bool_and(p.prosecdef)
          into v_definer
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public' and p.proname = 'upload_backup';

        if coalesce(v_definer, false) then
            revoke all on public.db_backups from anon, authenticated;
            alter table public.db_backups enable row level security;
        else
            raise notice 'دالة upload_backup ليست SECURITY DEFINER (أو غير موجودة): جدول db_backups '
                         'لم يُغلق حتى لا يتوقف رفع النسخ القديمة — راجع المرحلة الثانية';
        end if;
    end if;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  المرحلة الثانية — شغّلها يدوياً بعد تحديث كل العملاء إلى ١٫٥٠ فما بعد
--  (كلهم يرفعون عبر upload_backup_secure برمز المزامنة):
--
--  do $$
--  declare r record;
--  begin
--      for r in select p.oid::regprocedure as sig
--                 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
--                where n.nspname = 'public' and p.proname = 'upload_backup'
--      loop
--          execute format('revoke execute on function %s from public, anon, authenticated', r.sig);
--      end loop;
--      if to_regclass('public.db_backups') is not null then
--          revoke all on public.db_backups from anon, authenticated;
--          alter table public.db_backups enable row level security;
--      end if;
--  end $$;
--  notify pgrst, 'reload schema';
--
--  بعدها لا يرفع نسخةً كاملة إلا جهاز يحمل رمز مزامنة العميل نفسه.
-- ----------------------------------------------------------------------------

-- تقرير: من يستطيع الوصول للنسخ الكاملة الآن
select p.proname                                          as الدالة,
       pg_get_function_identity_arguments(p.oid)          as المعاملات,
       has_function_privilege('anon', p.oid, 'execute')   as متاحة_للمفتاح_العام,
       case when p.proname = 'download_backup' and has_function_privilege('anon', p.oid, 'execute')
                then '⚠️ التنزيل ما زال متاحاً للمفتاح العام'
            when p.proname = 'upload_backup' and has_function_privilege('anon', p.oid, 'execute')
                then 'ℹ️ الرفع القديم متاح حتى المرحلة الثانية (لعملاء ما قبل ١٫٥٠)'
            else '✔'
       end                                                as الحالة
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and p.proname in ('upload_backup', 'download_backup', 'upload_backup_secure')
 order by 1;

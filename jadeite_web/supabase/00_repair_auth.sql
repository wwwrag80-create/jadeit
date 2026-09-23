-- ============================================================================
--  جاديت ERP — إصلاح خدمة المصادقة (Auth)
--  شغّل هذا الملف أولاً إذا ظهر عند تسجيل الدخول:
--     AuthRetryableFetchException ... "Database error querying schema", 500
--
--  آمن ويمكن تشغيله أكثر من مرة. لا يحذف أي بيانات من جداولك.
--  Supabase → SQL Editor → New query → الصق → Run
-- ============================================================================

-- ----------------------------------------------------------------------------
--  الخطوة ١: تشخيص — ماذا يوجد الآن على جدول المستخدمين؟
--  (انظر النتيجة في الأسفل؛ إن ظهر أي trigger باسم غير معروف فهو غالباً السبب)
-- ----------------------------------------------------------------------------
select
    t.tgname                                   as trigger_name,
    pg_get_triggerdef(t.oid)                   as definition
  from pg_trigger t
  join pg_class c      on c.oid = t.tgrelid
  join pg_namespace n  on n.oid = c.relnamespace
 where n.nspname = 'auth'
   and c.relname = 'users'
   and not t.tgisinternal;

-- ----------------------------------------------------------------------------
--  الخطوة ٢: حذف أي محفّز (trigger) مخصّص على auth.users
--
--  السبب الأول لخطأ 500 هو محفّز مضاف يدوياً على auth.users يفشل عند التنفيذ
--  (مثل handle_new_user يشير لجدول غير موجود)، فيمنع تسجيل الدخول كلياً.
--  نظام جاديت لا يحتاج أي محفّز هنا — ربط المستخدم بالمستأجر يتم يدوياً
--  عبر جدول app_users، لذلك حذفها آمن تماماً.
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_dropped int := 0;
begin
    for r in
        select t.tgname
          from pg_trigger t
          join pg_class c     on c.oid = t.tgrelid
          join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'auth'
           and c.relname = 'users'
           and not t.tgisinternal
    loop
        execute format('drop trigger if exists %I on auth.users', r.tgname);
        v_dropped := v_dropped + 1;
        raise notice 'تم حذف المحفّز: %', r.tgname;
    end loop;

    if v_dropped = 0 then
        raise notice 'لا توجد محفّزات مخصّصة على auth.users (سليم)';
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  الخطوة ٣: إعادة صلاحيات خدمة المصادقة على مخططها
--
--  السبب الثاني لخطأ 500 هو فقدان صلاحيات الدور supabase_auth_admin
--  بعد تنفيذ أوامر revoke/grant عامة على قاعدة البيانات.
-- ----------------------------------------------------------------------------
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
        execute 'grant usage on schema auth to supabase_auth_admin';
        execute 'grant all privileges on all tables    in schema auth to supabase_auth_admin';
        execute 'grant all privileges on all sequences in schema auth to supabase_auth_admin';
        execute 'grant all privileges on all functions in schema auth to supabase_auth_admin';
        execute 'alter default privileges in schema auth grant all on tables    to supabase_auth_admin';
        execute 'alter default privileges in schema auth grant all on sequences to supabase_auth_admin';
        raise notice 'تمت إعادة صلاحيات supabase_auth_admin';
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  الخطوة ٤: التأكد من صلاحيات الوصول العامة للمخطط public
--  (بدونها ترجع كل طلبات التطبيق أخطاء صلاحيات)
-- ----------------------------------------------------------------------------
grant usage on schema public to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  الخطوة ٥: تحديث ذاكرة PostgREST
--  هذا ما يحل خطأ: Could not find the table 'public.app_users' in the schema cache
-- ----------------------------------------------------------------------------
notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  الخطوة ٦: تحقّق نهائي — يجب أن ترجع هذه الاستعلامات بدون أخطاء
-- ----------------------------------------------------------------------------
select count(*) as عدد_المستخدمين_في_المصادقة from auth.users;

select
    'تم الإصلاح — جرّب تسجيل الدخول الآن' as النتيجة,
    (select count(*) from pg_trigger t
       join pg_class c on c.oid = t.tgrelid
       join pg_namespace n on n.oid = c.relnamespace
      where n.nspname='auth' and c.relname='users' and not t.tgisinternal) as محفزات_متبقية;

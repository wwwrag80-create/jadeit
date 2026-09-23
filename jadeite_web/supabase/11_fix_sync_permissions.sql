-- ============================================================================
--  جاديت ERP — إصلاح خطأ المزامنة (28000: غير مصرّح بالمزامنة لهذا الحساب)
--
--  السبب الجذري:
--    كان ربط (clients.client_id ↔ tenants.id) يتم بسكربت ترحيل يعمل مرة واحدة
--    فقط. أي عميل أُضيف من لوحة الإدارة (سطح المكتب) بعد ذلك التاريخ لم يحصل
--    على صف tenants مطابق، فبقي بلا رمز مزامنة (sync_token = null)، فيرفض
--    assert_sync_token كل محاولة رفع من جهازه — ولنفس السبب تفشل محاولة
--    "انتحال الشخصية" من لوحة المدير، لأنها تقرأ نفس الرمز المفقود.
--
--  الحل: بدل الاعتماد على ترحيل لمرة واحدة، نجعل ربط الحساب بمزامنته
--  "ذاتي الإصلاح" — يُنفَّذ في كل مرة يُستخدم، لا مرة واحدة فقط:
--    ١) دخول العميل يضمن وجود الربط والرمز في نفس لحظة الدخول
--    ٢) انتحال شخصية المدير يضمن نفس الشيء قبل قراءة الرمز
--    ٣) مفتاح الخدمة (الذي تستخدمه شاشة المدير) يتجاوز فحص الرمز كلياً
--       كطبقة حماية إضافية، حتى لو تعذّر إصلاح الربط لأي سبب
--
--  شغّل هذا الملف بعد 10_maintenance.sql (وهو آمن لإعادة التشغيل)
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) is_service_role() — نُقلت إلى 02_rls.sql لأن has_tenant_access تعتمد عليها
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
--  ٢) الإصلاح الذاتي لربط الحساب بمزامنته
--
--  يُستدعى من: دخول العميل، وانتحال شخصية المدير — في كل مرة، لا لمرة واحدة.
--  لا يُنشئ بيانات وهمية: لو لم يكن الحساب موجوداً في tenants ولا في
--  clients القديم، يرجع بلا صفوف بهدوء.
-- ----------------------------------------------------------------------------
create or replace function public.ensure_tenant_link(p_client_id uuid)
returns table (
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean
)
language plpgsql security definer set search_path = public as $$
declare
    v_business text;
    v_can_edit boolean;
    v_active   boolean;
begin
    if p_client_id is null then
        return;
    end if;

    if exists (select 1 from public.tenants where id = p_client_id) then
        -- الصف موجود: نضمن فقط أن له رمز مزامنة صالحاً ومفعّلاً
        update public.tenants
           set sync_token   = coalesce(sync_token, gen_random_uuid()),
               sync_enabled = coalesce(sync_enabled, true)
         where id = p_client_id
           and (sync_token is null or sync_enabled is null);

    elsif to_regclass('public.clients') is not null then
        -- الصف غير موجود: ننشئه مطابقاً لحساب العميل القديم إن وُجد
        select c.business_name, c.can_edit, c.is_active
          into v_business, v_can_edit, v_active
          from public.clients c
         where c.client_id = p_client_id;

        if v_business is not null then
            insert into public.tenants (id, business_name, is_active, can_edit)
            values (p_client_id, v_business, coalesce(v_active, true), coalesce(v_can_edit, true))
            on conflict (id) do nothing;
        end if;
    end if;

    return query
        select t.business_name, coalesce(t.can_edit, true), t.sync_token, coalesce(t.sync_enabled, true)
          from public.tenants t
         where t.id = p_client_id;
end $$;

-- لا نمنحها لـ anon مباشرة (تمنع أي شخص من استكشاف بيانات حساب بمجرد تخمين
-- معرّفه)؛ العميل يصل إليها فقط بشكل غير مباشر عبر client_login_full أدناه،
-- والمدير يصل إليها مباشرة بمفتاح الخدمة.
--
-- ⚠️ كانت ممنوحة لـ authenticated، فكان أي مستخدم مسجّل (أي عميل) يستطيع قراءة
-- رمز مزامنة أي مصنع آخر بمعرّفه، ثم الكتابة في بياناته عبر دوال المزامنة.
revoke execute on function public.ensure_tenant_link(uuid) from public, anon, authenticated;
grant  execute on function public.ensure_tenant_link(uuid) to service_role;

-- ----------------------------------------------------------------------------
--  ٢-أ) سجل محاولات الدخول — يحدّ من تخمين كلمات المرور عبر client_login_full
--       (الدالة متاحة لـ anon لأن برنامج العميل يدخل بها قبل أي جلسة)
-- ----------------------------------------------------------------------------
create table if not exists public.login_attempts (
    id           bigserial primary key,
    username     text        not null,
    attempted_at timestamptz not null default now(),
    succeeded    boolean     not null default false
);

create index if not exists idx_login_attempts_user
    on public.login_attempts (lower(username), attempted_at desc);

alter table public.login_attempts enable row level security;
revoke all on public.login_attempts from anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٣) دخول العميل — الآن يستدعي الإصلاح الذاتي دائماً، لا الترحيل لمرة واحدة
--
--  إعادة الكتابة تفصل القراءة عن الكتابة الحسّاسة للأخطاء: التحقّق من بيانات
--  الدخول أولاً، ثم تحديث last_login في كتلة معزولة تتجاهل الأعمدة الناقصة
--  بهدوء، ثم الإرجاع في نهاية الدالة بلا أي معالج استثناءات حولها — فلا مجال
--  لأن يُبطل استثناء لاحق نتيجة تم إرجاعها مسبقاً.
-- ----------------------------------------------------------------------------
create or replace function public.client_login_full(
    p_username      text,
    p_password_hash text
)
returns table (
    out_client_id     uuid,
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean
)
language plpgsql security definer set search_path = public as $$
declare
    v_client_id uuid;
    v_business  text;
    v_can_edit  boolean;
    v_active    boolean;
    v_token     uuid;
    v_enabled   boolean;
    v_user      text := lower(btrim(coalesce(p_username, '')));
    v_fails     integer;
begin
    if to_regclass('public.clients') is null then
        return;   -- لا نظام عملاء قديم في هذه القاعدة
    end if;

    -- ١٠ محاولات فاشلة خلال ١٥ دقيقة توقف الاسم مؤقتاً. نرجع «بلا صفوف» (مثل
    -- كلمة مرور خاطئة) بدل رمي خطأ، حتى لا يلجأ البرنامج للدالة القديمة.
    select count(*) into v_fails
      from public.login_attempts
     where lower(username) = v_user
       and not succeeded
       and attempted_at > now() - interval '15 minutes';
    if v_fails >= 10 then
        return;
    end if;

    select c.client_id, c.business_name, c.can_edit, c.is_active
      into v_client_id, v_business, v_can_edit, v_active
      from public.clients c
     where lower(c.username) = v_user
       and c.password_hash = p_password_hash
     limit 1;

    if v_client_id is null or not coalesce(v_active, true) then
        insert into public.login_attempts (username, succeeded) values (v_user, false);
        return;   -- بيانات دخول خاطئة أو حساب موقوف: بلا صفوف
    end if;

    insert into public.login_attempts (username, succeeded) values (v_user, true);

    -- الإصلاح الذاتي: يضمن الربط والرمز بغض النظر عن كيف أو متى أُنشئ الحساب
    select e.out_sync_token, e.out_sync_enabled
      into v_token, v_enabled
      from public.ensure_tenant_link(v_client_id) e;

    -- تسجيل وقت الدخول، بمعزل تام عن مسار الإرجاع أدناه
    begin
        update public.clients
           set last_login = now(), last_seen = now()
         where client_id = v_client_id;
    exception when undefined_column then
        null;   -- نسخة قديمة من الجدول بلا هذين العمودين — لا يوقف الدخول
    end;

    return query
        select v_client_id, v_business, coalesce(v_can_edit, true), v_token, coalesce(v_enabled, true);
end $$;

grant execute on function public.client_login_full(text, text) to anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٤) فحص رمز المزامنة — مع تجاوز كامل لمفتاح الخدمة
--
--  مفتاح الخدمة تستخدمه شاشة "انتحال الشخصية" في لوحة المدير فقط (لا يُوزَّع
--  على العملاء إطلاقاً)، فتجاوزه هنا آمن ولا يفتح أي ثغرة للعملاء العاديين.
-- ----------------------------------------------------------------------------
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    -- (ج) مفتاح الخدمة (شاشة المدير) يتجاوز الفحص دائماً
    if public.is_service_role() then
        return;
    end if;

    -- (ب) جلسة مستخدم مسجّل الدخول عبر Supabase Auth وله صلاحية على هذا المصنع
    if auth.uid() is not null and public.has_tenant_access(p_tenant) then
        return;
    end if;

    -- (أ) رمز المزامنة السرّي — طريق أجهزة العملاء التي تستخدم تسجيل الدخول المخصّص
    if p_token is not null then
        select (sync_token = p_token and is_active and sync_enabled)
          into v_ok
          from public.tenants
         where id = p_tenant;

        if coalesce(v_ok, false) then
            return;
        end if;
    end if;

    raise exception 'غير مصرّح بالمزامنة لهذا الحساب' using errcode = '28000';
end $$;

-- ----------------------------------------------------------------------------
--  ٥) دالة تشخيص — شغّلها فوراً لمعرفة حالة أي عميل بدقة
-- ----------------------------------------------------------------------------
create or replace function public.diagnose_client_sync(p_username text)
returns table (
    الخطوة text,
    النتيجة text
)
language plpgsql security definer set search_path = public as $$
declare
    v_client_id uuid;
    v_has_clients boolean := to_regclass('public.clients') is not null;
begin
    return query select 'جدول clients موجود؟', case when v_has_clients then 'نعم' else 'لا — نظام Auth فقط' end;
    if not v_has_clients then
        return;
    end if;

    select c.client_id into v_client_id
      from public.clients c
     where lower(c.username) = lower(btrim(p_username));

    return query select 'الحساب موجود في clients؟',
        coalesce(v_client_id::text, 'لا — تحقق من اسم المستخدم');
    if v_client_id is null then
        return;
    end if;

    return query select 'الحساب مفعّل؟',
        (select case when is_active then 'نعم' else 'لا — موقوف' end from public.clients where client_id = v_client_id);

    return query select 'صف tenants مطابق موجود؟',
        case when exists (select 1 from public.tenants where id = v_client_id) then 'نعم' else 'لا (سيُنشأ تلقائياً عند أول دخول بعد هذا الإصلاح)' end;

    -- الرمز نفسه لا يُعرض أبداً — وجوده فقط
    return query select 'رمز المزامنة موجود؟',
        case when exists (select 1 from public.tenants
                           where id = v_client_id and sync_token is not null)
             then 'نعم' else 'لا' end;

    return query select 'المزامنة مفعّلة؟',
        coalesce((select case when sync_enabled then 'نعم' else 'لا — موقوفة يدوياً' end from public.tenants where id = v_client_id), 'لا يوجد صف بعد');

    return query select 'عدد الحركات في السحابة',
        (select count(*)::text from public.transactions where tenant_id = v_client_id);
end $$;

-- للتشخيص من SQL Editor أو بمفتاح الخدمة فقط — كانت تكشف بيانات أي عميل لأي مستخدم مسجّل
revoke execute on function public.diagnose_client_sync(text) from public, anon, authenticated;
grant  execute on function public.diagnose_client_sync(text) to service_role;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق فوري: كل عميل يجب أن يظهر الآن ومعه رمز مزامنة صالح
--  (هذا الاستعلام وحده لا يُصلح شيئاً — الإصلاح يحدث تلقائياً عند أول دخول
--   لكل عميل بعد تشغيل هذا الملف. لإصلاح الكل فوراً بلا انتظار دخولهم،
--   استخدم سطر الإصلاح الجماعي في نهاية هذا الملف)
-- ----------------------------------------------------------------------------
select t.business_name          as المصنع,
       t.id                     as tenant_id,
       (t.sync_token is not null) as له_رمز_مزامنة_الآن,
       t.sync_enabled           as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;

-- ----------------------------------------------------------------------------
--  إصلاح جماعي فوري لكل العملاء الحاليين (لا تنتظر دخولهم التالي)
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_fixed int := 0;
begin
    if to_regclass('public.clients') is not null then
        for r in select client_id from public.clients loop
            perform public.ensure_tenant_link(r.client_id);
            v_fixed := v_fixed + 1;
        end loop;
    end if;
    raise notice '✅ تم فحص وإصلاح ربط % حساب عميل', v_fixed;
end $$;

select 'تم الإصلاح الجماعي — الحالة النهائية:' as ملاحظة;
select t.business_name as المصنع, (t.sync_token is not null) as له_رمز_الآن
  from public.tenants t order by t.business_name;

-- ============================================================================
--  جاديت ERP — دخول العميل بدون أي ملف جلسة على القرص
--
--  الفكرة: عند تسجيل الدخول يرجع الخادم كل ما يحتاجه البرنامج (معرّف المصنع
--  ورمز المزامنة) في استجابة واحدة، ويحتفظ البرنامج بها في الذاكرة فقط.
--  بإغلاق البرنامج تختفي — لا يبقى أي سر على القرص.
--
--  شغّل هذا الملف بعد 06_hybrid_sync.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  دخول العميل: يرجع بيانات المصنع + رمز المزامنة دفعة واحدة
--
--  متوافق مع حسابات العملاء الحالية في جدول clients (لا يحتاج ترحيلهم لـ auth).
--  يعمل بالتحقق من بصمة كلمة المرور نفسها المستخدمة في verify_client_login.
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
begin
    return query
        select c.client_id, c.business_name, c.can_edit,
               t.sync_token, coalesce(t.sync_enabled, true)
          from public.clients c
          left join public.tenants t on t.id = c.client_id
         where lower(c.username) = lower(btrim(p_username))
           and c.password_hash = p_password_hash
           and c.is_active
         limit 1;

    -- تسجيل وقت الدخول ليظهر للمدير في لوحته
    update public.clients
       set last_login = now(), last_seen = now()
     where lower(username) = lower(btrim(p_username))
       and password_hash = p_password_hash;
exception when undefined_column or undefined_table then
    -- بيئة لا تحتوي جدول clients (تثبيت جديد يعتمد على auth فقط)
    return;
end $$;

grant execute on function public.client_login_full(text, text) to anon, authenticated;

-- ----------------------------------------------------------------------------
--  ضمان وجود صف tenants لكل عميل في clients
--  (العملاء القدامى أُنشئوا في clients قبل إضافة جدول tenants، فبدون هذا
--   لن يكون لهم رمز مزامنة ولن تُرفع بياناتهم)
-- ----------------------------------------------------------------------------
do $$
begin
    if to_regclass('public.clients') is not null then
        insert into public.tenants (id, business_name, is_active, can_edit)
        select c.client_id, c.business_name, c.is_active, c.can_edit
          from public.clients c
         where not exists (select 1 from public.tenants t where t.id = c.client_id)
        on conflict (id) do nothing;

        raise notice 'تمت مزامنة جدول tenants مع حسابات العملاء الحالية';
    end if;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: كل عميل يجب أن يظهر ومعه رمز مزامنة
-- ----------------------------------------------------------------------------
select t.business_name as المصنع,
       t.id            as tenant_id,
       (t.sync_token is not null) as له_رمز_مزامنة,
       t.sync_enabled  as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;

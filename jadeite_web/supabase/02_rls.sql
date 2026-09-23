-- ============================================================================
--  جاديت ERP — سياسات الأمان على مستوى الصف (RLS)
--  القاعدة: العميل لا يرى إلا بيانات مستأجره. المدير يرى ويعدّل كل شيء.
--  ملاحظة مهمة: دوال المساعدة SECURITY DEFINER حتى لا تدخل في تكرار لا نهائي
--  عند قراءة app_users من داخل سياسة على app_users نفسه.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  دوال المساعدة
-- ----------------------------------------------------------------------------
create or replace function public.current_tenant_id()
returns uuid
language sql stable security definer set search_path = public as $$
    select tenant_id from public.app_users where id = auth.uid();
$$;

create or replace function public.current_role_name()
returns text
language sql stable security definer set search_path = public as $$
    select role::text from public.app_users where id = auth.uid();
$$;

create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = public as $$
    select coalesce(
        (select role = 'admin' and is_active from public.app_users where id = auth.uid()),
        false
    );
$$;

-- هل الطلب الحالي بمفتاح الخدمة (service_role)؟
-- نقرأ الدور من مطالبات JWT التي يضبطها PostgREST — ثابتة طوال الطلب بخلاف
-- current_user الذي يتغيّر داخل دوال SECURITY DEFINER.
create or replace function public.is_service_role()
returns boolean
language plpgsql stable as $$
declare
    v_role text;
begin
    begin
        v_role := current_setting('request.jwt.claims', true)::json ->> 'role';
    exception when others then
        v_role := null;
    end;
    return coalesce(v_role, '') = 'service_role';
end $$;

-- هل يملك المستخدم الحالي صلاحية الوصول لهذا المستأجر؟
-- هذا الفحص هو خط الدفاع الوحيد داخل دوال SECURITY DEFINER (التي تتخطى RLS)،
-- لذلك يجب أن تستدعيه كل دالة تقرأ أو تكتب بيانات مستأجر.
create or replace function public.has_tenant_access(p_tenant uuid)
returns boolean
language sql stable security definer set search_path = public as $$
    select public.is_admin()
        or public.is_service_role()
        or (
            p_tenant is not null
            and p_tenant = public.current_tenant_id()
            and coalesce((select is_active from public.app_users where id = auth.uid()), false)
            and coalesce((select is_active from public.tenants where id = p_tenant), false)
        );
$$;

-- هل التعديل مسموح على هذا المستأجر؟ (المدير غير مقيّد)
create or replace function public.can_edit_tenant(p_tenant uuid)
returns boolean
language sql stable security definer set search_path = public as $$
    select public.is_admin()
        or coalesce((select can_edit from public.tenants where id = p_tenant), false);
$$;

grant execute on function public.current_tenant_id()      to authenticated;
grant execute on function public.current_role_name()      to authenticated;
grant execute on function public.is_admin()               to authenticated;
grant execute on function public.has_tenant_access(uuid)  to authenticated;
grant execute on function public.can_edit_tenant(uuid)    to authenticated;

-- ----------------------------------------------------------------------------
--  تفعيل RLS على كل الجداول
-- ----------------------------------------------------------------------------
alter table public.tenants         enable row level security;
alter table public.app_users       enable row level security;
alter table public.accounts        enable row level security;
alter table public.transactions    enable row level security;
alter table public.tenant_settings enable row level security;
alter table public.box_closings    enable row level security;
alter table public.audit_log       enable row level security;

-- ملاحظة مهمة: لا نستخدم FORCE ROW LEVEL SECURITY إطلاقاً.
-- سببها أن دوال المساعدة SECURITY DEFINER تعمل بصلاحية مالك الجدول، ومع FORCE
-- يصبح المالك نفسه خاضعاً للسياسات، فتقرأ السياسة app_users عبر دالة تقرأ app_users
-- => تكرار لا نهائي (infinite recursion) وتفشل كل الاستعلامات.

-- ----------------------------------------------------------------------------
--  tenants
-- ----------------------------------------------------------------------------
drop policy if exists tenants_select on public.tenants;
create policy tenants_select on public.tenants for select to authenticated
    using (public.is_admin() or id = public.current_tenant_id());

drop policy if exists tenants_admin_write on public.tenants;
create policy tenants_admin_write on public.tenants for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- العميل يُسمح له فقط بتحديث وقت ظهوره (بقية الأعمدة محمية بمُشغّل أدناه)
drop policy if exists tenants_self_touch on public.tenants;
create policy tenants_self_touch on public.tenants for update to authenticated
    using (id = public.current_tenant_id())
    with check (id = public.current_tenant_id());

-- يمنع العميل من رفع القيود عن نفسه (can_edit / is_active) حتى لو حاول تحديث الصف
create or replace function public.guard_tenant_self_update()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    if public.is_admin() then
        return new;
    end if;
    new.can_edit      := old.can_edit;
    new.is_active     := old.is_active;
    new.business_name := old.business_name;
    new.slug          := old.slug;
    return new;
end $$;

drop trigger if exists trg_tenant_guard on public.tenants;
create trigger trg_tenant_guard before update on public.tenants
    for each row execute function public.guard_tenant_self_update();

-- ----------------------------------------------------------------------------
--  app_users
-- ----------------------------------------------------------------------------
drop policy if exists app_users_select on public.app_users;
create policy app_users_select on public.app_users for select to authenticated
    -- (id = auth.uid()) أولاً عمداً: قراءة المستخدم لسجله لا تعتمد على أي دالة مساعدة،
    -- فيبقى تسجيل الدخول شغّالاً حتى لو حدث خلل في الدوال الأخرى.
    using (id = auth.uid() or public.is_admin() or tenant_id = public.current_tenant_id());

drop policy if exists app_users_admin_write on public.app_users;
create policy app_users_admin_write on public.app_users for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- ----------------------------------------------------------------------------
--  accounts
-- ----------------------------------------------------------------------------
drop policy if exists accounts_select on public.accounts;
create policy accounts_select on public.accounts for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists accounts_insert on public.accounts;
create policy accounts_insert on public.accounts for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

-- التعديل يخضع لقفل المدير
drop policy if exists accounts_update on public.accounts;
create policy accounts_update on public.accounts for update to authenticated
    using (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id))
    with check (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id));

-- الحذف يبقى متاحاً حتى مع قفل التعديل
drop policy if exists accounts_delete on public.accounts;
create policy accounts_delete on public.accounts for delete to authenticated
    using (public.has_tenant_access(tenant_id) and not is_system);

-- ----------------------------------------------------------------------------
--  transactions — الجدول الأهم
-- ----------------------------------------------------------------------------
drop policy if exists txn_select on public.transactions;
create policy txn_select on public.transactions for select to authenticated
    using (public.has_tenant_access(tenant_id));

-- تسجيل حركة جديدة مسموح دائماً (حتى مع قفل التعديل)
drop policy if exists txn_insert on public.transactions;
create policy txn_insert on public.transactions for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

-- تعديل حركة مسجّلة يتوقف عند قفل المدير
drop policy if exists txn_update on public.transactions;
create policy txn_update on public.transactions for update to authenticated
    using (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id))
    with check (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id));

-- الحذف مسموح دائماً — القفل يخص التعديل فقط
drop policy if exists txn_delete on public.transactions;
create policy txn_delete on public.transactions for delete to authenticated
    using (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  tenant_settings
-- ----------------------------------------------------------------------------
drop policy if exists settings_all on public.tenant_settings;
create policy settings_all on public.tenant_settings for all to authenticated
    using (public.has_tenant_access(tenant_id))
    with check (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  box_closings
-- ----------------------------------------------------------------------------
drop policy if exists closings_select on public.box_closings;
create policy closings_select on public.box_closings for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists closings_insert on public.box_closings;
create policy closings_insert on public.box_closings for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

drop policy if exists closings_delete on public.box_closings;
create policy closings_delete on public.box_closings for delete to authenticated
    using (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  audit_log — قراءة فقط، ولا يُحذف من التطبيق إطلاقاً
-- ----------------------------------------------------------------------------
drop policy if exists audit_select on public.audit_log;
create policy audit_select on public.audit_log for select to authenticated
    using (public.has_tenant_access(tenant_id));

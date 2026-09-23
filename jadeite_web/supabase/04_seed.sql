-- ============================================================================
--  جاديت ERP — تهيئة مستأجر جديد بحساباته الافتراضية
-- ============================================================================

create or replace function public.seed_tenant_defaults(p_tenant uuid)
returns void
language plpgsql security definer set search_path = public as $$
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير فقط';
    end if;

    -- حسابات النظام الأساسية
    insert into public.accounts(tenant_id, name, category, is_system, sort_order) values
        (p_tenant, 'المصنع',            'حسابات عامة',  true, 1),
        (p_tenant, 'حساب الخزينة',      'حسابات عامة',  true, 2),
        (p_tenant, 'حساب المبيعات',     'حسابات عامة',  true, 3),
        (p_tenant, 'حساب الخسائر',      'حسابات عامة',  true, 4)
    on conflict do nothing;

    -- صناديق الخياس وحسابات المسترجع المرتبطة بها
    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select p_tenant, k.box_name, 'صناديق الخياس', k.box_name, true, 10
      from public.khayas_boxes() k
    on conflict do nothing;

    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select p_tenant, k.mustarja_name, 'الموردين', k.box_name, true, 20
      from public.khayas_boxes() k
    on conflict do nothing;

    -- الإعدادات الافتراضية
    insert into public.tenant_settings(tenant_id, key, value) values
        (p_tenant, 'stones_discount_pct', '30'::jsonb),
        (p_tenant, 'home_screen_order',   '[]'::jsonb)
    on conflict do nothing;
end $$;

grant execute on function public.seed_tenant_defaults(uuid) to authenticated;

-- ----------------------------------------------------------------------------
--  إنشاء مستأجر جديد + ربط مستخدم به (يُنفَّذ من لوحة المدير)
-- ----------------------------------------------------------------------------
create or replace function public.admin_create_tenant(
    p_business_name text,
    p_user_id       uuid default null,
    p_full_name     text default null
) returns uuid
language plpgsql security definer set search_path = public as $$
declare
    v_tenant uuid;
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير فقط';
    end if;

    insert into public.tenants(business_name) values (p_business_name) returning id into v_tenant;
    perform public.seed_tenant_defaults(v_tenant);

    if p_user_id is not null then
        insert into public.app_users(id, tenant_id, role, full_name)
        values (p_user_id, v_tenant, 'owner', p_full_name)
        on conflict (id) do update set tenant_id = excluded.tenant_id, role = excluded.role;
    end if;

    return v_tenant;
end $$;

grant execute on function public.admin_create_tenant(text, uuid, text) to authenticated;

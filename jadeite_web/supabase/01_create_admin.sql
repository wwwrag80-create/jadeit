-- ============================================================================
--  جاديت ERP — إنشاء حساب المدير + أول مصنع (عميل)
--
--  قبل تشغيل هذا الملف:
--  ١) Supabase → Authentication → Users → Add user → Create new user
--     - أدخل بريدك وكلمة مرور
--     - ✅ فعّل خيار Auto Confirm User (مهم جداً، وإلا لن تستطيع الدخول)
--  ٢) عدّل البريد في السطر أدناه ثم شغّل الملف كاملاً.
-- ============================================================================

-- 👇👇 غيّر هذا البريد لبريدك الذي أنشأته في الخطوة ١ 👇👇
do $$
declare
    v_admin_email text := 'admin@jadeite.com';     -- ← ضع بريدك هنا
    v_factory     text := 'مصنع جاديت للتصنيع';    -- ← اسم أول مصنع (يمكن تغييره لاحقاً)
    v_uid         uuid;
    v_tenant      uuid;
begin
    -- ١) نبحث عن المستخدم في نظام المصادقة
    select id into v_uid from auth.users where lower(email) = lower(v_admin_email) limit 1;

    if v_uid is null then
        raise exception
            'لم يتم العثور على مستخدم بالبريد (%). أنشئه أولاً من Authentication → Users → Add user مع تفعيل Auto Confirm User.',
            v_admin_email;
    end if;

    -- ٢) ربطه كمدير عام (المدير هو الوحيد المسموح له أن يكون بلا مستأجر)
    insert into public.app_users (id, tenant_id, role, full_name, email, is_active)
    values (v_uid, null, 'admin', 'المدير العام', v_admin_email, true)
    on conflict (id) do update
        set role      = 'admin',
            tenant_id = null,
            is_active = true,
            email     = excluded.email;

    raise notice '✅ تم ربط المدير: %', v_admin_email;

    -- ٣) إنشاء أول مصنع بحساباته الافتراضية (إن لم يكن موجوداً)
    select id into v_tenant from public.tenants where business_name = v_factory limit 1;

    if v_tenant is null then
        insert into public.tenants (business_name, is_active, can_edit)
        values (v_factory, true, true)
        returning id into v_tenant;
        raise notice '✅ تم إنشاء المصنع: %  (المعرّف: %)', v_factory, v_tenant;
    else
        raise notice 'ℹ️ المصنع موجود مسبقاً: %', v_factory;
    end if;

    -- ٤) تهيئة الحسابات النظامية للمصنع (الخزينة، المبيعات، الخسائر، الصناديق، المسترجعات)
    --    نستدعي المنطق مباشرة لأن seed_tenant_defaults تشترط جلسة مدير فعلية
    insert into public.accounts(tenant_id, name, category, is_system, sort_order) values
        (v_tenant, 'المصنع',        'حسابات عامة', true, 1),
        (v_tenant, 'حساب الخزينة',  'حسابات عامة', true, 2),
        (v_tenant, 'حساب المبيعات', 'حسابات عامة', true, 3),
        (v_tenant, 'حساب الخسائر',  'حسابات عامة', true, 4)
    on conflict do nothing;

    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select v_tenant, k.box_name, 'صناديق الخياس', k.box_name, true, 10
      from public.khayas_boxes() k
    on conflict do nothing;

    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select v_tenant, k.mustarja_name, 'الموردين', k.box_name, true, 20
      from public.khayas_boxes() k
    on conflict do nothing;

    raise notice '✅ تمت تهيئة الحسابات النظامية للمصنع';
    raise notice '🎉 كل شيء جاهز — سجّل الدخول بالبريد: %', v_admin_email;
end $$;

-- ============================================================================
--  تحقّق: يجب أن يظهر المدير والمصنع وحساباته
-- ============================================================================
select 'المدير' as النوع, u.email as الاسم, u.role::text as الدور, '—' as القسم
  from public.app_users u where u.role = 'admin'
union all
select 'مصنع', t.business_name, case when t.can_edit then 'التعديل مفتوح' else 'التعديل مقفول' end, '—'
  from public.tenants t
union all
select 'حساب', a.name, '—', a.category::text
  from public.accounts a
 order by 1 desc, 4, 2;

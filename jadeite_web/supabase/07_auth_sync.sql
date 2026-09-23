-- ============================================================================
--  جاديت ERP — الدخول بحساب Supabase والمزامنة العكسية (Sync Down)
--
--  التغيير الجوهري: برنامج سطح المكتب لم يعد يحمل أي رمز سرّي في ملف.
--  العميل يسجّل دخوله ببريده وكلمة مروره، فيحصل على JWT، وكل استدعاءاته
--  بعد ذلك تمرّ بـ RLS العادية — وهذا أقوى أماناً من ملف الجلسة السابق.
--
--  شغّل هذا الملف بعد 06_hybrid_sync.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) توسيع فحص صلاحية المزامنة ليقبل مصدرين:
--     (أ) رمز مزامنة سرّي  — للتوافق مع الأجهزة القديمة
--     (ب) جلسة مستخدم مسجّل الدخول — الطريقة الجديدة المعتمدة
-- ----------------------------------------------------------------------------
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    -- (ب) الأولوية للجلسة المسجّلة: المستخدم الداخل فعلياً بحسابه
    if auth.uid() is not null and public.has_tenant_access(p_tenant) then
        return;
    end if;

    -- (أ) وإلا نقبل رمز المزامنة السرّي
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
--  ٢) بيانات جلسة المستخدم بعد تسجيل الدخول
--     يرجعها البرنامج فور نجاح الدخول ليعرف: أي مصنع، وهل التعديل مفتوح
-- ----------------------------------------------------------------------------
create or replace function public.my_session()
returns table (
    user_id       uuid,
    tenant_id     uuid,
    business_name text,
    user_role     text,
    can_edit      boolean,
    is_active     boolean,
    sync_enabled  boolean
)
language sql stable security definer set search_path = public as $$
    select
        u.id,
        u.tenant_id,
        coalesce(t.business_name, 'المدير العام'),
        u.role::text,
        coalesce(t.can_edit, true),
        (u.is_active and coalesce(t.is_active, true)),
        coalesce(t.sync_enabled, true)
      from public.app_users u
      left join public.tenants t on t.id = u.tenant_id
     where u.id = auth.uid();
$$;

-- ----------------------------------------------------------------------------
--  ٣) سحب الحركات من السحابة إلى الجهاز (Sync Down)
--     مقسّم على دفعات بترتيب الرقم المتسلسل، فيعمل مع أي حجم بيانات
--     ولا يقطع الاتصال ولا يستهلك ذاكرة الجهاز.
-- ----------------------------------------------------------------------------
create or replace function public.sync_pull_transactions(
    p_tenant    uuid,
    p_after_seq bigint default 0,
    p_limit     int    default 1000
)
returns table (
    seq_no        bigint,
    txn_date      timestamptz,
    account_name  text,
    op_type       text,
    weight        numeric,
    weight_before numeric,
    weight_after  numeric,
    note          text,
    status        text,
    trees_count   numeric,
    set_number    text,
    row_number    text,
    manual_no     text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٤) سحب شجرة الحسابات (الأسماء والأقسام)
-- ----------------------------------------------------------------------------
create or replace function public.sync_pull_accounts(p_tenant uuid)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select a.name, a.category::text
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by a.category, a.name;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) ملخّص ما في السحابة — يستخدمه البرنامج لعرض شريط التقدّم
-- ----------------------------------------------------------------------------
create or replace function public.sync_cloud_summary(p_tenant uuid)
returns table (total_rows bigint, max_seq bigint, accounts_count bigint, last_sync timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select
            (select count(*)          from public.transactions x where x.tenant_id = p_tenant),
            (select coalesce(max(x.seq_no), 0) from public.transactions x where x.tenant_id = p_tenant),
            (select count(*)          from public.accounts a where a.tenant_id = p_tenant),
            (select tn.last_sync_at   from public.tenants tn where tn.id = p_tenant);
end $$;

-- ----------------------------------------------------------------------------
--  ٦) الصلاحيات
--     دوال السحب للمستخدمين المسجّلين فقط — anon لا يستطيع قراءة أي شيء
-- ----------------------------------------------------------------------------
grant execute on function public.my_session()                            to authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int) to authenticated;
grant execute on function public.sync_pull_accounts(uuid)                to authenticated;
grant execute on function public.sync_cloud_summary(uuid)                to authenticated;

revoke execute on function public.sync_pull_transactions(uuid, bigint, int) from anon;
revoke execute on function public.sync_pull_accounts(uuid)                  from anon;
revoke execute on function public.sync_cloud_summary(uuid)                  from anon;

notify pgrst, 'reload schema';

-- ============================================================================
--  جاديت ERP — الإصلاح الجذري لخطأ 28000 عند سحب البيانات
--
--  السبب الحقيقي (بعد تتبّع الخطأ خطوة بخطوة):
--    دوال السحب الأربع (sync_cloud_summary / sync_pull_accounts /
--    sync_pull_transactions / sync_pull_changes) كانت تستدعي:
--        perform public.assert_sync_token(p_tenant, null);
--    أي تمرّر NULL كرمز مزامنة دائماً — فلا تنجح إلا لمستخدم مسجّل عبر
--    Supabase Auth (auth.uid() موجود) أو بمفتاح الخدمة.
--
--    لكن برنامج العميل يسجّل دخوله عبر جدول clients بمفتاح anon، فلا يوجد
--    auth.uid() إطلاقاً. النتيجة: كل محاولة سحب تفشل بـ 28000 مهما كان
--    رمز المزامنة صحيحاً — لأن الرمز لم يُمرَّر أصلاً.
--
--  الإصلاح: إضافة معامل p_token لكل دوال السحب وتمريره للفحص.
--  (المعامل اختياري وفي آخر القائمة، فالاستدعاءات القديمة تبقى صالحة)
--
--  شغّل هذا الملف بعد 11_fix_sync_permissions.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) ملخّص السحابة
-- ----------------------------------------------------------------------------
drop function if exists public.sync_cloud_summary(uuid);
drop function if exists public.sync_cloud_summary(uuid, uuid);

create or replace function public.sync_cloud_summary(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (total_rows bigint, max_seq bigint, accounts_count bigint, last_sync timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select
            (select count(*)          from public.transactions x where x.tenant_id = p_tenant),
            (select coalesce(max(x.seq_no), 0) from public.transactions x where x.tenant_id = p_tenant),
            (select count(*)          from public.accounts a where a.tenant_id = p_tenant),
            (select tn.last_sync_at   from public.tenants tn where tn.id = p_tenant);
end $$;

-- ----------------------------------------------------------------------------
--  ٢) سحب شجرة الحسابات
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_accounts(uuid);
drop function if exists public.sync_pull_accounts(uuid, uuid);

create or replace function public.sync_pull_accounts(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select a.name, a.category::text
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by a.category, a.name;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) سحب الحركات على دفعات
-- ----------------------------------------------------------------------------
-- تُحذف كل التوقيعات السابقة: تغيير نوع الإرجاع يرفضه
-- create or replace، فلا بد من الحذف أولاً
drop function if exists public.sync_pull_transactions(uuid, bigint, int);
drop function if exists public.sync_pull_transactions(uuid, bigint, int, uuid);

create or replace function public.sync_pull_transactions(
    p_tenant    uuid,
    p_after_seq bigint default 0,
    p_limit     int    default 1000,
    p_token     uuid   default null
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
    perform public.assert_sync_token(p_tenant, p_token);
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
--  ٤) السحب التفاضلي (تعديلات لوحة المدير تصل للعميل)
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_changes(uuid, timestamptz, int);
drop function if exists public.sync_pull_changes(uuid, timestamptz, int, uuid);

create or replace function public.sync_pull_changes(
    p_tenant uuid,
    p_since  timestamptz default null,
    p_limit  int default 500,
    p_token  uuid default null
)
returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
    v_now     timestamptz := now();
    v_full    boolean := false;
    v_changed jsonb;
    v_deleted jsonb;
    v_more    boolean := false;
    v_count   int;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_since is null or p_since < now() - interval '85 days' then
        v_full := true;
    end if;

    select coalesce(jsonb_agg(row_to_json(x)), '[]'::jsonb), count(*)
      into v_changed, v_count
      from (
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text as status, t.trees_count,
               t.set_number, t.row_number, t.manual_no,
               t.source, t.updated_at
          from public.transactions t
         where t.tenant_id = p_tenant
           and (v_full or t.updated_at > p_since)
         order by t.updated_at
         limit least(coalesce(p_limit, 500), 2000)
      ) x;

    v_more := (v_count >= least(coalesce(p_limit, 500), 2000));

    if v_full then
        v_deleted := '[]'::jsonb;
    else
        select coalesce(jsonb_agg(d.seq_no), '[]'::jsonb)
          into v_deleted
          from public.sync_deletions d
         where d.tenant_id = p_tenant
           and d.deleted_at > p_since;
    end if;

    return jsonb_build_object(
        'server_time', v_now,
        'full_resync', v_full,
        'has_more',    v_more,
        'changed',     v_changed,
        'deleted',     v_deleted
    );
end $$;

-- ----------------------------------------------------------------------------
--  ٥) الصلاحيات — anon يحتاجها لأن برنامج العميل يعمل بمفتاح anon
--     (الأمان محفوظ: كل دالة تتحقق من رمز المزامنة السرّي قبل أي قراءة)
-- ----------------------------------------------------------------------------
grant execute on function public.sync_cloud_summary(uuid, uuid)                    to anon, authenticated;
grant execute on function public.sync_pull_accounts(uuid, uuid)                    to anon, authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int, uuid)   to anon, authenticated;
grant execute on function public.sync_pull_changes(uuid, timestamptz, int, uuid)   to anon, authenticated;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: جرّب السحب برمز عميل حقيقي — يجب أن يرجع صفاً بلا خطأ 28000
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_rows bigint;
begin
    for r in select id, business_name, sync_token from public.tenants
              where sync_token is not null limit 3
    loop
        select total_rows into v_rows
          from public.sync_cloud_summary(r.id, r.sync_token);
        raise notice '✅ % — السحب يعمل، عدد الحركات: %', r.business_name, v_rows;
    end loop;
end $$;

select 'تم إصلاح دوال السحب — جرّب تسجيل الدخول الآن' as النتيجة;

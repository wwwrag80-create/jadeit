-- ============================================================================
--  جاديت ERP — طبقة المزامنة الهجينة (Hybrid Sync Layer)
--
--  المعمارية:
--    • العميل يعمل على SQLite محلياً (يشتغل بدون إنترنت)
--    • خيط خلفي في البرنامج يرفع الحركات إلى Supabase عبر دوال RPC فقط
--    • لوحة المدير (الويب) تقرأ من Supabase مباشرة عبر Supabase Auth + RLS
--
--  مبدأ الأمان الأساسي:
--    برنامج سطح المكتب يحمل مفتاح anon فقط (لأنه يُوزَّع على العملاء).
--    لذلك: anon **ممنوع** من الوصول المباشر لأي جدول، ولا يستطيع إلا استدعاء
--    دوال المزامنة أدناه، وكل دالة تتحقق من (tenant_id + sync_token) قبل الكتابة.
--    النتيجة: حتى لو فُكِّك ملف exe واستُخرج مفتاح anon، لن يصل حامله لبيانات
--    أي عميل آخر، ولن يقرأ شيئاً أصلاً — الدوال تكتب فقط.
--
--  شغّل هذا الملف بعد INSTALL_ALL.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) رمز المزامنة لكل عميل + بيانات جهازه
-- ----------------------------------------------------------------------------
alter table public.tenants
    add column if not exists sync_token   uuid not null default gen_random_uuid(),
    add column if not exists sync_enabled boolean not null default true,
    add column if not exists last_sync_at timestamptz;

comment on column public.tenants.sync_token is
    'رمز سرّي يُسلَّم لبرنامج العميل ويُخزَّن في device_session.json — يُبطل بتغييره فوراً';

create table if not exists public.tenant_devices (
    id            uuid primary key default gen_random_uuid(),
    tenant_id     uuid not null references public.tenants(id) on delete cascade,
    device_id     text not null,
    device_name   text default '',
    app_version   text default '',
    last_sync_at  timestamptz,
    pending_count int default 0,
    pushed_total  bigint default 0,
    last_error    text,
    created_at    timestamptz not null default now(),
    unique (tenant_id, device_id)
);

create index if not exists idx_devices_tenant on public.tenant_devices(tenant_id);

-- تتبّع مصدر كل حركة: هل جاءت من برنامج سطح المكتب أم أُدخلت من الويب
alter table public.transactions
    add column if not exists source      text not null default 'desktop',
    add column if not exists device_id   text default '',
    add column if not exists synced_at   timestamptz;

alter table public.accounts
    add column if not exists source text not null default 'desktop';

-- ----------------------------------------------------------------------------
--  ١-أ) حماية أعمدة المزامنة من العميل نفسه
--      سياسة tenants_self_touch تسمح للعميل بتحديث صفّه (لآخر ظهور)، فبدون هذا
--      يستطيع إعادة تفعيل مزامنة أوقفها المدير أو تغيير رمزها بنفسه.
-- ----------------------------------------------------------------------------
create or replace function public.guard_tenant_self_update()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    -- المدير، ومفتاح الخدمة، والجلسة المباشرة على القاعدة (SQL Editor — بلا JWT
    -- إطلاقاً، بخلاف طلبات PostgREST التي تحمل دوماً دور anon أو authenticated)
    if public.is_admin() or public.is_service_role()
       or coalesce(current_setting('request.jwt.claims', true), '') = '' then
        return new;
    end if;
    new.can_edit      := old.can_edit;
    new.is_active     := old.is_active;
    new.business_name := old.business_name;
    new.slug          := old.slug;
    new.sync_token    := old.sync_token;
    new.sync_enabled  := old.sync_enabled;
    new.last_sync_at  := old.last_sync_at;
    return new;
end $$;

-- ----------------------------------------------------------------------------
--  ١-ب) ترقيم حركات الويب عند مصانع سطح المكتب
--
--  برنامج سطح المكتب يرقّم حركاته محلياً (invoice_id) ويرفعها بالرقم نفسه،
--  والرفع upsert على (tenant_id, seq_no). لو أخذت حركة من الويب الرقم التالي
--  (max + 1) لاصطدمت بأول حركة جديدة يسجّلها العميل على جهازه، فيكتب الرفعُ
--  فوقها ويمحوها بصمت. الحل: حركات الويب لمصنع يعمل ببرنامج سطح المكتب
--  تأخذ أرقاماً من نطاق مستقل يبدأ من مليار، لا يصل إليه ترقيم الجهاز أبداً.
-- ----------------------------------------------------------------------------
create or replace function public.next_seq_no(p_tenant uuid)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
    c_web_base constant bigint := 1000000000;
    v_next    bigint;
    v_desktop boolean;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;

    -- القفل على مستوى المستأجر يمنع تكرار الأرقام عند التسجيل من جهازين معاً
    perform pg_advisory_xact_lock(hashtext(p_tenant::text));

    select coalesce(max(seq_no), 0) + 1 into v_next
      from public.transactions where tenant_id = p_tenant;

    v_desktop := exists (select 1 from public.tenant_devices d where d.tenant_id = p_tenant)
              or exists (select 1 from public.transactions x
                          where x.tenant_id = p_tenant and coalesce(x.device_id, '') <> '');

    if v_desktop then
        v_next := greatest(v_next, c_web_base);
    end if;
    return v_next;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) التحقق من رمز المزامنة — أساس أمان كل الدوال التالية
-- ----------------------------------------------------------------------------
-- القيمة الافتراضية مطابقة لتعريفه في 07/11: بدونها تفشل إعادة تشغيل التثبيت
-- بالخطأ «cannot remove parameter defaults from existing function»
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    select (sync_token = p_token and is_active and sync_enabled)
      into v_ok
      from public.tenants
     where id = p_tenant;

    if coalesce(v_ok, false) = false then
        -- رسالة واحدة مبهمة عمداً: لا نكشف إن كان المعرّف موجوداً أم لا
        raise exception 'رمز المزامنة غير صالح أو المزامنة موقوفة لهذا الحساب'
            using errcode = '28000';
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) رفع دفعة حركات من SQLite المحلية
--
--  الرفع idempotent بالكامل: المفتاح (tenant_id, seq_no) يقابل "رقم الفاتورة"
--  في قاعدة العميل، فإعادة رفع نفس الدفعة لا تُنشئ تكراراً بل تُحدّث فقط.
--  هذا ضروري لأن الشبكة قد تنقطع بعد الكتابة وقبل وصول الرد.
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_transactions(
    p_tenant  uuid,
    p_token   uuid,
    p_device  text,
    p_rows    jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.transactions (
        tenant_id, seq_no, txn_date, account_name, op_type,
        weight, weight_before, weight_after, note, status,
        trees_count, set_number, row_number, manual_no,
        source, device_id, synced_at
    )
    select
        p_tenant,
        (r ->> 'seq_no')::bigint,
        (r ->> 'txn_date')::timestamptz,
        coalesce(r ->> 'account_name', ''),
        coalesce(r ->> 'op_type', ''),
        coalesce((r ->> 'weight')::numeric, 0),
        coalesce((r ->> 'weight_before')::numeric, 0),
        coalesce((r ->> 'weight_after')::numeric, 0),
        coalesce(r ->> 'note', ''),
        coalesce((r ->> 'status')::public.txn_status, 'ACTIVE'),
        coalesce((r ->> 'trees_count')::numeric, 0),
        coalesce(r ->> 'set_number', ''),
        coalesce(r ->> 'row_number', ''),
        coalesce(r ->> 'manual_no', ''),
        'desktop',
        coalesce(p_device, ''),
        now()
      from jsonb_array_elements(p_rows) as r
     where (r ->> 'seq_no') is not null
       and (r ->> 'txn_date') is not null
    on conflict (tenant_id, seq_no) do update set
        txn_date      = excluded.txn_date,
        account_name  = excluded.account_name,
        op_type       = excluded.op_type,
        weight        = excluded.weight,
        weight_before = excluded.weight_before,
        weight_after  = excluded.weight_after,
        note          = excluded.note,
        status        = excluded.status,
        trees_count   = excluded.trees_count,
        set_number    = excluded.set_number,
        row_number    = excluded.row_number,
        manual_no     = excluded.manual_no,
        device_id     = excluded.device_id,
        synced_at     = now(),
        updated_at    = now();

    get diagnostics v_count = row_count;

    update public.tenants
       set last_sync_at = now(),
           last_seen    = now()
     where id = p_tenant;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) مزامنة الحذف
--
--  الحذف عند العميل حذف فعلي من SQLite، فنقابله هنا بحذف فعلي أيضاً حتى
--  تبقى نسخة السحابة مطابقة تماماً لما يراه العميل على شاشته.
-- ----------------------------------------------------------------------------
create or replace function public.sync_delete_transactions(
    p_tenant  uuid,
    p_token   uuid,
    p_seq_nos bigint[]
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_seq_nos is null or array_length(p_seq_nos, 1) is null then
        return 0;
    end if;

    delete from public.transactions
     where tenant_id = p_tenant
       and seq_no = any(p_seq_nos);

    get diagnostics v_count = row_count;

    update public.tenants set last_sync_at = now(), last_seen = now() where id = p_tenant;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) مزامنة شجرة الحسابات (الأسماء والأقسام)
--     الأقسام غير المعروفة تُحوَّل لـ (حسابات عامة) بدل رفض الدفعة كلها
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_accounts(
    p_tenant uuid,
    p_token  uuid,
    p_rows   jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.accounts (tenant_id, name, category, source)
    select
        p_tenant,
        r ->> 'name',
        case r ->> 'category'
            when 'المصنعين'      then 'المصنعين'
            when 'المركبين'      then 'المركبين'
            when 'الآلة/المكائن' then 'الآلة/المكائن'
            when 'الموردين'      then 'الموردين'
            when 'صناديق الخياس' then 'صناديق الخياس'
            else 'حسابات عامة'
        end::public.account_category,
        'desktop'
      from jsonb_array_elements(p_rows) as r
     where coalesce(btrim(r ->> 'name'), '') <> ''
    on conflict (tenant_id, name, category) do nothing;

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) نبضة الجهاز — تُظهر للمدير حالة كل عميل لحظياً
-- ----------------------------------------------------------------------------
create or replace function public.sync_heartbeat(
    p_tenant   uuid,
    p_token    uuid,
    p_device   text,
    p_name     text default '',
    p_version  text default '',
    p_pending  int  default 0,
    p_pushed   bigint default 0,
    p_error    text default null
)
returns void
language plpgsql security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);

    insert into public.tenant_devices
        (tenant_id, device_id, device_name, app_version, last_sync_at,
         pending_count, pushed_total, last_error)
    values
        (p_tenant, coalesce(p_device, 'unknown'), coalesce(p_name, ''), coalesce(p_version, ''),
         now(), coalesce(p_pending, 0), coalesce(p_pushed, 0), p_error)
    on conflict (tenant_id, device_id) do update set
        device_name   = excluded.device_name,
        app_version   = excluded.app_version,
        last_sync_at  = now(),
        pending_count = excluded.pending_count,
        pushed_total  = greatest(public.tenant_devices.pushed_total, excluded.pushed_total),
        last_error    = excluded.last_error;

    update public.tenants set last_seen = now() where id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  ٧) آخر رقم متسلسل موجود في السحابة — يستخدمه العميل لمعرفة من أين يكمل
-- ----------------------------------------------------------------------------
create or replace function public.sync_cloud_state(p_tenant uuid, p_token uuid)
returns table (max_seq bigint, total_rows bigint, last_sync timestamptz)
language plpgsql security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select coalesce(max(t.seq_no), 0), count(*),
               (select last_sync_at from public.tenants where id = p_tenant)
          from public.transactions t
         where t.tenant_id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  ٨) الصلاحيات — القاعدة الذهبية:
--     anon يستطيع استدعاء دوال المزامنة فقط، ولا يملك أي وصول مباشر للجداول
-- ----------------------------------------------------------------------------
revoke all on public.transactions    from anon;
revoke all on public.accounts        from anon;
revoke all on public.tenants         from anon;
revoke all on public.app_users       from anon;
revoke all on public.tenant_settings from anon;
revoke all on public.box_closings    from anon;
revoke all on public.audit_log       from anon;
revoke all on public.tenant_devices  from anon;

grant execute on function public.sync_push_transactions(uuid, uuid, text, jsonb) to anon, authenticated;
grant execute on function public.sync_delete_transactions(uuid, uuid, bigint[])  to anon, authenticated;
grant execute on function public.sync_push_accounts(uuid, uuid, jsonb)           to anon, authenticated;
grant execute on function public.sync_heartbeat(uuid, uuid, text, text, text, int, bigint, text) to anon, authenticated;
grant execute on function public.sync_cloud_state(uuid, uuid)                    to anon, authenticated;

-- assert_sync_token دالة داخلية — لا تُمنح لأحد
revoke all on function public.assert_sync_token(uuid, uuid) from public, anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٩) RLS لجدول الأجهزة (المدير يرى الكل، العميل يرى أجهزته)
-- ----------------------------------------------------------------------------
alter table public.tenant_devices enable row level security;

drop policy if exists devices_select on public.tenant_devices;
create policy devices_select on public.tenant_devices for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists devices_admin_write on public.tenant_devices;
create policy devices_admin_write on public.tenant_devices for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- ----------------------------------------------------------------------------
--  ١٠) لوحة المدير: نظرة شاملة على العملاء وحالة مزامنتهم
-- ----------------------------------------------------------------------------
create or replace function public.admin_sync_overview()
returns table (
    tenant_id      uuid,
    business_name  text,
    is_active      boolean,
    can_edit       boolean,
    sync_enabled   boolean,
    last_sync_at   timestamptz,
    is_online      boolean,
    devices        int,
    pending_count  int,
    txn_count      bigint,
    last_txn_at    timestamptz,
    last_error     text
)
language sql stable security definer set search_path = public as $$
    select
        t.id,
        t.business_name,
        t.is_active,
        t.can_edit,
        t.sync_enabled,
        t.last_sync_at,
        (t.last_seen is not null and t.last_seen > now() - interval '3 minutes'),
        (select count(*)::int from public.tenant_devices d where d.tenant_id = t.id),
        (select coalesce(sum(d.pending_count), 0)::int from public.tenant_devices d where d.tenant_id = t.id),
        (select count(*) from public.transactions x where x.tenant_id = t.id),
        (select max(x.txn_date) from public.transactions x where x.tenant_id = t.id),
        (select d.last_error from public.tenant_devices d
          where d.tenant_id = t.id and d.last_error is not null
          order by d.last_sync_at desc limit 1)
      from public.tenants t
     where public.is_admin()
     order by t.business_name;
$$;

grant execute on function public.admin_sync_overview() to authenticated;

-- ----------------------------------------------------------------------------
--  ١١) إعادة توليد رمز المزامنة (للمدير) — يُبطل الرمز القديم فوراً
-- ----------------------------------------------------------------------------
create or replace function public.admin_rotate_sync_token(p_tenant uuid)
returns uuid
language plpgsql security definer set search_path = public as $$
declare
    v_new uuid;
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير العام فقط';
    end if;
    v_new := gen_random_uuid();
    update public.tenants set sync_token = v_new where id = p_tenant;
    return v_new;
end $$;

grant execute on function public.admin_rotate_sync_token(uuid) to authenticated;

-- ----------------------------------------------------------------------------
--  ١٢) تفعيل البث اللحظي (Realtime) على جدول الحركات
--      حتى تتحدّث شاشات المدير لحظة وصول أي حركة من أي عميل
-- ----------------------------------------------------------------------------
do $$
begin
    if not exists (
        select 1 from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = 'public'
           and tablename = 'transactions')
    then
        alter publication supabase_realtime add table public.transactions;
    end if;

    if not exists (
        select 1 from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = 'public'
           and tablename = 'tenant_devices')
    then
        alter publication supabase_realtime add table public.tenant_devices;
    end if;
exception when others then
    raise notice 'تنبيه: فعّل Realtime يدوياً من Database → Replication (%).', sqlerrm;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  استخرج بيانات ربط برنامج العميل من هنا (انسخها في device_session.json)
-- ----------------------------------------------------------------------------
select
    t.business_name          as اسم_المصنع,
    t.id                     as tenant_id,
    t.sync_token             as sync_token,
    t.sync_enabled           as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;

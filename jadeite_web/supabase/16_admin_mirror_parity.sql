-- ============================================================================
--  جاديت ERP — برنامج المدير يعرض بيانات العميل كما تظهر على جهازه حرفياً
--
--  الاتجاه واحد دائماً: جهاز العميل ← السحابة ← برنامج المدير (قراءة فقط).
--  لا شيء في هذا الملف يكتب على جهاز العميل.
--
--  فرقان كانا يجعلان شاشة المدير تختلف عن شاشة العميل:
--
--  (١) ترتيب الأسماء: العميل يعرض العمال والموردين بترتيب إضافتهم، والسحابة
--      كانت ترجعهم مرتّبين أبجدياً (sync_pull_accounts: order by 2, 1) —
--      فتظهر جداول المصنعين والمركبين والقوائم عند المدير بترتيب آخر.
--      الحل: العميل يرفع ترتيب كل اسم (desktop_order)، والسحب يرجع به.
--
--  (٢) إعدادات العميل لم تكن تُرفع إطلاقاً: نسب استرجاع الخياس (تغيّر أرقام
--      شاشة ربح/خسارة الطقم)، أسماء الأعمدة المخصّصة، ترتيب الشاشات والأقسام،
--      وتلوين السالب. الحل: لقطة كاملة من إعدادات العميل تُرفع وتُسحب للمدير.
--
--  (٣) التاريخ: كان المدير يحوّل وقت كل حركة لتوقيت جهازه هو — فلو اختلف
--      ضبط التوقيت بين الجهازين اختلفت الساعة (وأحياناً اليوم). الحل: يُرفع
--      نص التاريخ كما هو على جهاز العميل (local_date) ويعرضه المدير حرفياً.
--
--  شغّل هذا الملف بعد 15_period_ledger.sql (أو شغّل INSTALL_ALL.sql كاملاً).
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) ترتيب الأسماء كما عند العميل
-- ----------------------------------------------------------------------------
alter table public.accounts
    add column if not exists desktop_order bigint;

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

    insert into public.accounts (tenant_id, name, category, category_raw, source, desktop_order)
    select
        p_tenant,
        r ->> 'name',
        -- العمود المُعدّد للتوافق مع لوحة الويب
        case r ->> 'category'
            when 'المصنعين'      then 'المصنعين'
            when 'المركبين'      then 'المركبين'
            when 'الآلة/المكائن' then 'الآلة/المكائن'
            when 'الموردين'      then 'الموردين'
            when 'صناديق الخياس' then 'صناديق الخياس'
            else 'حسابات عامة'
        end::public.account_category,
        -- والقسم الحقيقي حرفياً بلا تحويل — هذا ما يعتمده برنامج سطح المكتب
        coalesce(r ->> 'category', ''),
        'desktop',
        -- ترتيب الاسم على جهاز العميل (البرامج القديمة لا ترسله فيبقى كما هو)
        case when coalesce(r ->> 'sort_order', '') ~ '^\d{1,15}$'
             then (r ->> 'sort_order')::bigint end
      from (
             -- اسم واحد بنفس القسم مرتين في الدفعة يُسبب 21000
             select distinct on ((t.x ->> 'name'), (t.x ->> 'category')) t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where coalesce(btrim(t.x ->> 'name'), '') <> ''
              order by (t.x ->> 'name'), (t.x ->> 'category'), t.ord desc
           ) as d(r)
    on conflict (tenant_id, name, category) do update set
        category_raw  = excluded.category_raw,
        is_active     = true,
        desktop_order = coalesce(excluded.desktop_order, public.accounts.desktop_order);

    get diagnostics v_count = row_count;
    return v_count;
end $$;

create or replace function public.sync_pull_accounts(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select a.name,
               coalesce(nullif(a.category_raw, ''), a.category::text)
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         -- بترتيب العميل؛ وما لا ترتيب له (حسابات قديمة أو من الويب) بعده أبجدياً
         order by a.desktop_order nulls last, 2, 1;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) تاريخ الحركة كما هو على جهاز العميل
-- ----------------------------------------------------------------------------
alter table public.transactions
    add column if not exists local_date text;

-- تعديل التاريخ من الويب يُسقط النص القديم (وإلا عرض المدير تاريخاً لم يعد صحيحاً)
create or replace function public.clear_stale_local_date()
returns trigger language plpgsql as $$
begin
    if new.txn_date is distinct from old.txn_date
       and new.local_date is not distinct from old.local_date then
        new.local_date := null;
    end if;
    return new;
end $$;

drop trigger if exists trg_txn_local_date on public.transactions;
create trigger trg_txn_local_date before update on public.transactions
    for each row execute function public.clear_stale_local_date();

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
        period, source, device_id, synced_at, local_date
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
        -- الفترة كما أرسلها العميل، أو تُشتق من التاريخ لو غابت
        coalesce(nullif(r ->> 'period', ''), to_char((r ->> 'txn_date')::timestamptz, 'YYYY-MM')),
        'desktop',
        coalesce(p_device, ''),
        now(),
        -- نص التاريخ على جهاز العميل (البرامج القديمة لا ترسله)
        nullif(r ->> 'local_date', '')
      from (
             -- إزالة التكرار داخل الدفعة الواحدة (الخطأ 21000): آخر نسخة لكل رقم
             select distinct on ((t.x ->> 'seq_no')) t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where (t.x ->> 'seq_no') is not null
                and (t.x ->> 'txn_date') is not null
              order by (t.x ->> 'seq_no'), t.ord desc
           ) as d(r)
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
        period        = excluded.period,
        device_id     = excluded.device_id,
        local_date    = excluded.local_date,
        synced_at     = now(),
        updated_at    = now();

    get diagnostics v_count = row_count;

    update public.tenants
       set last_sync_at = now(), last_seen = now()
     where id = p_tenant;

    return v_count;
end $$;

-- عمود جديد في الناتج = تغيير نوع الإرجاع، فيلزم الحذف ثم الإنشاء
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
    manual_no     text,
    period        text,
    local_date    text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no,
               coalesce(nullif(t.period, ''), to_char(t.txn_date, 'YYYY-MM')),
               t.local_date
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٣) إعدادات العميل — لقطة كاملة، باتجاه واحد
--     تُحفظ في tenant_settings بمفتاح يبدأ بـ «desktop:» فلا تختلط بإعدادات الويب
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_settings(
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

    -- لقطة كاملة: إعداد حذفه العميل يُحذف هنا أيضاً
    delete from public.tenant_settings s
     where s.tenant_id = p_tenant
       and s.key like 'desktop:%'
       and not exists (select 1 from jsonb_array_elements(p_rows) r
                        where 'desktop:' || (r ->> 'key') = s.key);

    insert into public.tenant_settings (tenant_id, key, value, updated_at)
    select p_tenant, 'desktop:' || (r ->> 'key'), to_jsonb(coalesce(r ->> 'value', '')), now()
      from (
             select distinct on (t.x ->> 'key') t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where coalesce(btrim(t.x ->> 'key'), '') <> ''
              order by (t.x ->> 'key'), t.ord desc
           ) as d(r)
    on conflict (tenant_id, key) do update set
        value      = excluded.value,
        updated_at = now();

    get diagnostics v_count = row_count;
    return v_count;
end $$;

create or replace function public.sync_pull_settings(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (key text, value text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select substr(s.key, length('desktop:') + 1), s.value #>> '{}'
          from public.tenant_settings s
         where s.tenant_id = p_tenant
           and s.key like 'desktop:%'
         order by 1;
end $$;

-- دوال المزامنة محمية برمز المزامنة (assert_sync_token) — مثل بقية sync_*
revoke execute on function public.sync_push_settings(uuid, uuid, jsonb) from public;
revoke execute on function public.sync_pull_settings(uuid, uuid)        from public;
revoke execute on function public.sync_pull_transactions(uuid, bigint, int, uuid) from public;
revoke execute on function public.clear_stale_local_date()              from public, anon, authenticated;
grant execute on function public.sync_push_transactions(uuid, uuid, text, jsonb) to anon, authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int, uuid) to anon, authenticated;
grant execute on function public.sync_push_accounts(uuid, uuid, jsonb)  to anon, authenticated;
grant execute on function public.sync_pull_accounts(uuid, uuid)         to anon, authenticated;
grant execute on function public.sync_push_settings(uuid, uuid, jsonb)  to anon, authenticated;
grant execute on function public.sync_pull_settings(uuid, uuid)         to anon, authenticated;

notify pgrst, 'reload schema';

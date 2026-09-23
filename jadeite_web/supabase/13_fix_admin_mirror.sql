-- ============================================================================
--  جاديت ERP — إصلاح عدم تطابق بيانات المدير مع العميل
--
--  ثلاثة أسباب جذرية اكتُشفت عند تتبّع الفروقات:
--
--  (١) عمود الفترة (period) لم يكن يُرفع ولا يُسحَب إطلاقاً.
--      العميل يخزّن الفترة صراحةً، أما المدير فكان يشتقّها من تاريخ الحركة —
--      فحركة تاريخها ٧/٣٠ ومثبّتة في فترة ٨ تظهر عند المدير في فترة ٧.
--      وهذا سبب ظهور ٣ فترات عند المدير مقابل فترتين عند العميل.
--
--  (٢) أقسام الحسابات كانت تُسحق: كل قسم خارج القائمة الثابتة الستة يتحوّل
--      إلى (حسابات عامة). فصناديق الخياس المضافة وأقسام مراحل التصنيع
--      تفقد قسمها الحقيقي، فلا تظهر عند المدير أصلاً.
--
--  (٣) حذف الأسماء لم يكن يُزامَن: الاسم المحذوف عند العميل يبقى عند المدير.
--
--  شغّل هذا الملف بعد 12_fix_pull_token.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) عمود الفترة على الحركات
--
--  مهم: في المخطط الأصلي كان (period) عموداً **مُولَّداً** من التاريخ:
--      period text generated always as (to_char(txn_date,'YYYY-MM')) stored
--  والعمود المُولَّد لا يقبل الكتابة إطلاقاً، فيفشل الرفع بالخطأ:
--      column "period" can only be updated to DEFAULT
--  ولأن الفترة صارت قراراً محاسبياً مستقلاً عن التاريخ (العميل قد يعمل في
--  فترة ٨ ويسجّل بتاريخ ٩)، نحوّله إلى عمود عادي مع الاحتفاظ بقيمه الحالية.
-- ----------------------------------------------------------------------------
do $$
declare
    v_generated text;
begin
    select is_generated into v_generated
      from information_schema.columns
     where table_schema = 'public'
       and table_name  = 'transactions'
       and column_name = 'period';

    if v_generated is null then
        -- العمود غير موجود أصلاً
        alter table public.transactions add column period text default '';
        raise notice 'أُضيف عمود period';

    elsif v_generated = 'ALWAYS' then
        -- عمود مُولَّد: نفكّ التوليد فتبقى القيم المخزّنة كما هي ويصبح قابلاً للكتابة
        alter table public.transactions alter column period drop expression;
        raise notice 'حُوّل عمود period من مُولَّد إلى عادي (القيم محفوظة)';

    else
        raise notice 'عمود period عادي بالفعل — لا تغيير';
    end if;
end $$;

-- الحركات المرفوعة سابقاً: الفترة = شهر تاريخها (نفس اشتقاق النظام القديم)
update public.transactions
   set period = to_char(txn_date, 'YYYY-MM')
 where period is null or period = '';

-- ----------------------------------------------------------------------------
--  ٢) القسم الحقيقي للحساب كما هو عند العميل
--
--  نُبقي العمود القديم (category) للتوافق مع لوحة الويب، ونضيف عموداً نصياً
--  يحمل القسم حرفياً بلا أي تحويل — فلا تضيع الأقسام الديناميكية.
-- ----------------------------------------------------------------------------
alter table public.accounts
    add column if not exists category_raw text default '';

update public.accounts
   set category_raw = category::text
 where category_raw is null or category_raw = '';

-- ----------------------------------------------------------------------------
--  ٣) رفع الحركات مع فترتها
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
        period, source, device_id, synced_at
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
        now()
      from (
             -- إزالة التكرار داخل الدفعة الواحدة:
             -- ON CONFLICT DO UPDATE يرفض تعديل الصف نفسه مرتين في أمر واحد
             -- (الخطأ 21000)، ويحدث لو حملت الدفعة رقمَي تسلسل متطابقين.
             -- نُبقي آخر نسخة لكل رقم تسلسل.
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
        synced_at     = now(),
        updated_at    = now();

    get diagnostics v_count = row_count;

    update public.tenants
       set last_sync_at = now(), last_seen = now()
     where id = p_tenant;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) سحب الحركات مع فترتها
-- ----------------------------------------------------------------------------
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
    manual_no     text,
    period        text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no,
               coalesce(nullif(t.period, ''), to_char(t.txn_date, 'YYYY-MM'))
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٥) رفع الحسابات بأقسامها الحقيقية
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

    insert into public.accounts (tenant_id, name, category, category_raw, source)
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
        'desktop'
      from (
             -- نفس السبب: اسم واحد بنفس القسم مرتين في الدفعة يُسبب 21000
             select distinct on ((t.x ->> 'name'), (t.x ->> 'category')) t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where coalesce(btrim(t.x ->> 'name'), '') <> ''
              order by (t.x ->> 'name'), (t.x ->> 'category'), t.ord desc
           ) as d(r)
    on conflict (tenant_id, name, category) do update set
        category_raw = excluded.category_raw,
        is_active    = true;

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) سحب الحسابات بأقسامها الحقيقية
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
        select a.name,
               coalesce(nullif(a.category_raw, ''), a.category::text)
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by 2, 1;
end $$;

-- ----------------------------------------------------------------------------
--  ٧) مزامنة حذف الأسماء
--     بدونها يبقى الاسم المحذوف عند العميل ظاهراً عند المدير إلى الأبد
-- ----------------------------------------------------------------------------
create or replace function public.sync_delete_accounts(
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

    -- تعطيل لا حذف: يحفظ أثر الحساب في الحركات القديمة المرتبطة به
    update public.accounts a
       set is_active = false
      from jsonb_array_elements(p_rows) as r
     where a.tenant_id = p_tenant
       and a.name = (r ->> 'name')
       and coalesce(nullif(a.category_raw, ''), a.category::text) = coalesce(r ->> 'category', '');

    get diagnostics v_count = row_count;
    return v_count;
end $$;

grant execute on function public.sync_delete_accounts(uuid, uuid, jsonb) to anon, authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int, uuid) to anon, authenticated;
grant execute on function public.sync_pull_accounts(uuid, uuid) to anon, authenticated;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: الفترات والأقسام كما هي عند العميل
-- ----------------------------------------------------------------------------
select t.business_name as المصنع,
       x.period        as الفترة,
       count(*)        as الحركات
  from public.transactions x
  join public.tenants t on t.id = x.tenant_id
 group by t.business_name, x.period
 order by 1, 2;

select t.business_name as المصنع,
       coalesce(nullif(a.category_raw, ''), a.category::text) as القسم,
       count(*) as الحسابات
  from public.accounts a
  join public.tenants t on t.id = a.tenant_id
 where a.is_active
 group by 1, 2
 order by 1, 2;

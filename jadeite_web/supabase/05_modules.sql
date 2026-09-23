-- ============================================================================
--  جاديت ERP — دوال الموديولات المكمّلة
--  (القيود اليومية، إقفال الصناديق، أرشيف الفواتير والبحث، الخسائر والهالك)
--  شغّل هذا الملف بعد 03_functions.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) قيد يومي مزدوج: طرف مدين وطرف دائن بنفس الوزن ونفس المرجع
--     الترحيل داخل معاملة واحدة — إما يُسجَّل الطرفان معاً أو لا شيء إطلاقاً،
--     فلا يبقى قيد غير متوازن في الدفاتر أبداً.
-- ----------------------------------------------------------------------------
-- التوقيع القديم (بلا p_period) يُحذف أولاً حتى لا يلتبس الاستدعاء على PostgREST
drop function if exists public.post_journal_entry(uuid, timestamptz, text, text, numeric, text);

create or replace function public.post_journal_entry(
    p_tenant     uuid,
    p_date       timestamptz,
    p_from       text,          -- الحساب الدائن (خرج منه)
    p_to         text,          -- الحساب المدين (دخل إليه)
    p_weight     numeric,
    p_note       text default '',
    p_period     text default null   -- الفترة المحاسبية صراحةً (YYYY-MM)
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_ref     text;
    v_seq     bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;
    if p_weight is null or p_weight <= 0 then
        raise exception 'وزن القيد يجب أن يكون أكبر من صفر';
    end if;
    if p_from is null or p_to is null or btrim(p_from) = '' or btrim(p_to) = '' then
        raise exception 'الرجاء تحديد الحساب المدين والحساب الدائن';
    end if;
    if btrim(p_from) = btrim(p_to) then
        raise exception 'لا يصح أن يكون الطرف المدين هو نفسه الطرف الدائن';
    end if;
    if p_period is not null and btrim(p_period) <> '' and p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;

    v_seq := public.next_seq_no(p_tenant);
    v_ref := 'JE-' || v_seq::text;

    -- الطرف المدين (الحساب المستلم)
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, p_date, btrim(p_to), 'قيد يومي مدين', p_weight,
         coalesce(nullif(btrim(p_note), ''), 'قيد يومي'), v_ref,
         nullif(btrim(coalesce(p_period, '')), ''), auth.uid());

    -- الطرف الدائن (الحساب المصدر)
    v_seq := public.next_seq_no(p_tenant);
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, p_date, btrim(p_from), 'قيد يومي دائن', p_weight,
         coalesce(nullif(btrim(p_note), ''), 'قيد يومي'), v_ref,
         nullif(btrim(coalesce(p_period, '')), ''), auth.uid());

    return v_ref;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) حذف قيد يومي كامل بطرفيه — حذف طرف واحد يترك الدفاتر غير متوازنة
-- ----------------------------------------------------------------------------
create or replace function public.delete_journal_entry(p_tenant uuid, p_ref text)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    -- قيد الإقفال مرتبط بسجل في box_closings: حذفه من هنا يترك الصندوق
    -- «مُقفلاً» بلا قيد، فيُلغى فقط من شاشة الإقفال (reopen_khayas_box)
    if p_ref like 'CLOSE-%' then
        raise exception 'هذا قيد إقفال صندوق — ألغِه من شاشة إقفال الصناديق (زر التراجع)';
    end if;

    delete from public.transactions
     where tenant_id = p_tenant
       and set_number = p_ref
       and op_type in ('قيد يومي مدين', 'قيد يومي دائن');

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) القيود اليومية لفترة، مجمّعة في قيد واحد بطرفيه
-- ----------------------------------------------------------------------------
create or replace function public.journal_entries(p_tenant uuid, p_period text)
returns table (
    entry_ref   text,
    txn_date    timestamptz,
    debit_acc   text,
    credit_acc  text,
    weight      numeric,
    note        text,
    is_balanced boolean
)
language sql stable security definer set search_path = public as $$
    select
        t.set_number,
        min(t.txn_date),
        max(t.account_name) filter (where t.op_type = 'قيد يومي مدين'),
        max(t.account_name) filter (where t.op_type = 'قيد يومي دائن'),
        max(t.weight),
        max(t.note),
        -- القيد سليم فقط لو كان له طرفان بنفس الوزن
        (count(*) = 2
         and coalesce(sum(case when t.op_type = 'قيد يومي مدين' then t.weight else -t.weight end), 1) = 0)
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.period = p_period
       and t.op_type in ('قيد يومي مدين', 'قيد يومي دائن')
     group by t.set_number
     order by min(t.txn_date), t.set_number;
$$;

-- ----------------------------------------------------------------------------
--  ٤) إقفال صندوق خياس لفترة
--     الإقفال = ترحيل رصيد الصندوق لحساب الخسائر بقيد مزدوج + تسجيل الإقفال،
--     فلا يبقى الرصيد معلّقاً ولا يتكرر تحميله على الشهر التالي.
-- ----------------------------------------------------------------------------
create or replace function public.close_khayas_box(
    p_tenant uuid,
    p_box    text,
    p_period text
)
returns numeric
language plpgsql security definer set search_path = public as $$
declare
    v_khayas numeric;
    v_seq    bigint;
    v_ref    text;
    v_date   timestamptz;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    if p_period is null or p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;
    if not exists (select 1 from public.khayas_boxes() k where k.box_name = p_box) then
        raise exception 'صندوق غير معروف: %', p_box;
    end if;

    if exists (select 1 from public.box_closings
                where tenant_id = p_tenant and box_name = p_box and period = p_period) then
        raise exception 'صندوق (%) مُقفل مسبقاً لفترة (%)', p_box, p_period;
    end if;

    select khayas into v_khayas from public.box_period_totals(p_tenant, p_box, p_period);
    v_khayas := coalesce(v_khayas, 0);

    if v_khayas = 0 then
        raise exception 'لا يوجد رصيد خياس لإقفاله في صندوق (%) خلال (%)', p_box, p_period;
    end if;

    -- تاريخ الإقفال = آخر لحظة في الشهر المُقفل، حتى يبقى القيد داخل فترته
    v_date := (to_date(p_period || '-01', 'YYYY-MM-DD') + interval '1 month' - interval '1 second');

    v_seq := public.next_seq_no(p_tenant);
    v_ref := 'CLOSE-' || p_box || '-' || p_period;

    -- الرصيد الموجب (خياس/فاقد) يُحمَّل على حساب الخسائر، والسالب (فائض) يُرد منه
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, v_date, 'حساب الخسائر',
         case when v_khayas > 0 then 'قيد يومي مدين' else 'قيد يومي دائن' end,
         abs(v_khayas), 'إقفال صندوق ' || p_box || ' — ' || p_period, v_ref, p_period, auth.uid());

    v_seq := public.next_seq_no(p_tenant);
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, v_date, p_box,
         case when v_khayas > 0 then 'قيد يومي دائن' else 'قيد يومي مدين' end,
         abs(v_khayas), 'إقفال صندوق ' || p_box || ' — ' || p_period, v_ref, p_period, auth.uid());

    insert into public.box_closings (tenant_id, box_name, period, closed_khayas, closed_by)
    values (p_tenant, p_box, p_period, v_khayas, auth.uid());

    return v_khayas;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) التراجع عن إقفال صندوق (يحذف قيد الإقفال وسجلّه معاً)
-- ----------------------------------------------------------------------------
create or replace function public.reopen_khayas_box(
    p_tenant uuid,
    p_box    text,
    p_period text
)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ref text := 'CLOSE-' || p_box || '-' || p_period;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    delete from public.transactions
     where tenant_id = p_tenant and set_number = v_ref;

    delete from public.box_closings
     where tenant_id = p_tenant and box_name = p_box and period = p_period;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) حالة إقفال كل الصناديق لفترة
-- ----------------------------------------------------------------------------
create or replace function public.boxes_closing_status(p_tenant uuid, p_period text)
returns table (
    box_name      text,
    madin         numeric,
    daen          numeric,
    khayas        numeric,
    is_closed     boolean,
    closed_khayas numeric,
    closed_at     timestamptz
)
language sql stable security definer set search_path = public as $$
    select
        k.box_name,
        b.madin,
        b.daen,
        b.khayas,
        (c.id is not null),
        coalesce(c.closed_khayas, 0),
        c.closed_at
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b
      left join public.box_closings c
             on c.tenant_id = p_tenant and c.box_name = k.box_name and c.period = p_period
     where (select public.has_tenant_access(p_tenant))
     order by k.box_name;
$$;

-- ----------------------------------------------------------------------------
--  ٧) تفصيل الخسائر والهالك لفترة
--     يجمع: خياس كل صندوق + ذهب/صافي للمصنعين والمركبين
-- ----------------------------------------------------------------------------
create or replace function public.losses_breakdown(p_tenant uuid, p_period text)
returns table (
    source_kind  text,     -- 'صندوق' أو 'عامل'
    source_name  text,
    category     text,
    amount       numeric,
    is_closed    boolean
)
language sql stable security definer set search_path = public as $$
    -- خياس الصناديق
    select
        'صندوق'::text,
        k.box_name,
        'صناديق الخياس'::text,
        b.khayas,
        (c.id is not null)
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b
      left join public.box_closings c
             on c.tenant_id = p_tenant and c.box_name = k.box_name and c.period = p_period
     where b.khayas <> 0
       and (select public.has_tenant_access(p_tenant))

    union all

    -- الفاقد الفعلي لكل عامل في المصنعين والمركبين
    select
        'عامل'::text,
        a.name,
        a.category::text,
        coalesce((
            select sum(
                case
                    when a.category::text = 'المركبين'
                        then case t.op_type
                                when 'صرف ذهب' then t.weight
                                when 'قبض ذهب' then -t.weight
                                when 'الليز'   then t.weight
                                else 0 end
                    else case t.op_type
                                when 'صرف ذهب'          then t.weight
                                when 'قبض ذهب'          then -t.weight
                                when 'البوليش'          then -t.weight
                                when 'الليز'            then t.weight
                                when 'المفنش ٨ بالالف'  then -t.weight
                                when 'المفنش ٤ بالالف'  then -t.weight
                                else 0 end
                end)
              from public.transactions t
             where t.tenant_id = p_tenant
               and t.status in ('ACTIVE', 'SETTLED_INOUT')
               and t.period = p_period
               and t.account_name = a.name
        ), 0),
        false
      from public.accounts a
     where a.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and a.is_active
       and a.category::text in ('المصنعين', 'المركبين')
       and coalesce((
            select sum(case t.op_type when 'صرف ذهب' then t.weight else 0 end)
              from public.transactions t
             where t.tenant_id = p_tenant and t.status in ('ACTIVE', 'SETTLED_INOUT')
               and t.period = p_period and t.account_name = a.name
       ), 0) <> 0
     order by 3, 4 desc;
$$;

-- ----------------------------------------------------------------------------
--  ٨) أرشيف الفواتير: كل فاتورة مبيعات في صف واحد
-- ----------------------------------------------------------------------------
create or replace function public.invoice_archive(
    p_tenant uuid,
    p_period text default null,
    p_query  text default null
)
returns table (
    manual_no    text,
    txn_date     timestamptz,
    account_name text,
    gold         numeric,
    gems         numeric,
    stones_after numeric,
    diamond      numeric,
    khayas       numeric,
    lines_count  bigint,
    set_numbers  text
)
language sql stable security definer set search_path = public as $$
    select
        t.manual_no,
        min(t.txn_date),
        t.account_name,
        coalesce(sum(t.weight) filter (where t.op_type in ('مبيعات ذهب','مبيعات ذهب مع الماس')), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count <> 3), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count = 3), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات الماس'), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'خياس طقوم'), 0),
        count(distinct nullif(t.set_number, '')),
        string_agg(distinct nullif(t.set_number, ''), '، ')
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
       and (p_period is null or t.period = p_period)
       and (
            p_query is null or btrim(p_query) = ''
            or t.manual_no    ilike '%' || p_query || '%'
            or t.set_number   ilike '%' || p_query || '%'
            or t.account_name ilike '%' || p_query || '%'
       )
     group by t.manual_no, t.account_name, date_trunc('second', t.txn_date)
     order by min(t.txn_date) desc;
$$;

-- ----------------------------------------------------------------------------
--  ٩) البحث الموحّد مع تحديد الشاشة
--     أرقام الفواتير قد تتكرر بين الشاشات، لذا تحديد المصدر ضروري
--     p_source: المبيعات | الوارد | القيود | الافتتاحي | التشغيل | الكل
-- ----------------------------------------------------------------------------
create or replace function public.search_transactions(
    p_tenant uuid,
    p_source text,
    p_query  text
)
returns setof public.transactions
language sql stable security definer set search_path = public as $$
    select t.*
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and btrim(coalesce(p_query, '')) <> ''
       and case p_source
            when 'المبيعات' then
                (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
                and (t.manual_no = btrim(p_query) or t.seq_no::text = btrim(p_query))
            when 'الوارد' then
                t.op_type = any(public.inbound_types())
                and (t.set_number = btrim(p_query) or t.seq_no::text = btrim(p_query))
            when 'القيود' then
                t.op_type in ('قيد يومي مدين', 'قيد يومي دائن')
                and (t.set_number = btrim(p_query)
                     or t.set_number = 'JE-' || btrim(p_query)
                     or t.seq_no::text = btrim(p_query))
            when 'الافتتاحي' then
                t.trees_count = 1 and t.note = 'قيد افتتاحي'
                and t.seq_no::text = btrim(p_query)
            when 'التشغيل' then
                t.set_number = btrim(p_query)
            else
                t.seq_no::text = btrim(p_query)
                or t.manual_no = btrim(p_query)
                or t.set_number = btrim(p_query)
           end
     order by t.txn_date, t.seq_no;
$$;

-- ----------------------------------------------------------------------------
--  الصلاحيات
-- ----------------------------------------------------------------------------
grant execute on function public.post_journal_entry(uuid, timestamptz, text, text, numeric, text, text) to authenticated;
grant execute on function public.delete_journal_entry(uuid, text)          to authenticated;
grant execute on function public.journal_entries(uuid, text)               to authenticated;
grant execute on function public.close_khayas_box(uuid, text, text)        to authenticated;
grant execute on function public.reopen_khayas_box(uuid, text, text)       to authenticated;
grant execute on function public.boxes_closing_status(uuid, text)          to authenticated;
grant execute on function public.losses_breakdown(uuid, text)              to authenticated;
grant execute on function public.invoice_archive(uuid, text, text)         to authenticated;
grant execute on function public.search_transactions(uuid, text, text)     to authenticated;

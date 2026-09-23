-- ============================================================================
--  جاديت ERP — الدوال المحاسبية (RPC)
--  كل الحسابات تتم في قاعدة البيانات لضمان رقم واحد صحيح لكل الأجهزة
--
--  قاعدتان تلتزم بهما كل دالة هنا:
--   ١) كل دالة SECURITY DEFINER تتخطى RLS، فلا بد أن تتحقق بنفسها من
--      public.has_tenant_access(p_tenant) — وإلا قرأ أي عميل (بل أي زائر بمفتاح
--      anon) بيانات مصنع غيره بمجرد معرفة معرّفه.
--   ٢) الحركات المحتسبة في الأرصدة هي (ACTIVE, SETTLED_INOUT) — نفس فلتر برنامج
--      سطح المكتب حرفياً — فلا يختلف رقم المدير عن رقم العميل.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  أنواع الحركات — مصدر واحد للحقيقة يستخدمه SQL و Flutter
-- ----------------------------------------------------------------------------
create or replace function public.inbound_types() returns text[]
language sql immutable as $$
    select array['وارد ذهب (عيار 18)', 'وارد فصوص وأحجار', 'وارد الماس'];
$$;

create or replace function public.sale_types() returns text[]
language sql immutable as $$
    select array['مبيعات ذهب', 'مبيعات ذهب مع الماس', 'مبيعات فصوص وأحجار', 'مبيعات الماس'];
$$;

-- صناديق الخياس: (اسم الصندوق، نوع المدين، نوع الدائن، اسم المسترجع)
-- (يُعاد تعريفها في 15_period_ledger.sql بأسماء المسترجع كما يكتبها برنامج سطح المكتب)
create or replace function public.khayas_boxes()
returns table (box_name text, madin_type text, qabd_type text, mustarja_name text)
language sql immutable as $$
    values
        ('الكاستنج',      'صرف كاستنج',     'قبض كاستنج',      'مسترجع الكاستنج'),
        ('التلميع',       'صرف تلميع',      'قبض تلميع',       'مسترجع التلميع'),
        ('التلميع/البف',  'صرف تلميع بف',   'قبض تلميع بف',    'مسترجع التلميع/البف'),
        ('خياس الطقوم',   'خياس طقوم',      'قبض خياس طقوم',   'مسترجع خياس الطقوم');
$$;

-- ----------------------------------------------------------------------------
--  الرقم المتسلسل للحركة داخل كل مستأجر (آمن مع التزامن)
--  (يُعاد تعريفه في 06_hybrid_sync.sql ليحجز نطاقاً مستقلاً لحركات الويب
--   عند المصانع التي تعمل ببرنامج سطح المكتب)
-- ----------------------------------------------------------------------------
create or replace function public.next_seq_no(p_tenant uuid)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
    v_next bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;

    -- القفل على مستوى المستأجر يمنع تكرار الأرقام عند التسجيل من جهازين معاً
    perform pg_advisory_xact_lock(hashtext(p_tenant::text));
    select coalesce(max(seq_no), 0) + 1 into v_next
      from public.transactions where tenant_id = p_tenant;
    return v_next;
end $$;

-- ----------------------------------------------------------------------------
--  تسجيل حركة واحدة (يتكفّل بالرقم المتسلسل تلقائياً)
--
--  p_period: الفترة المحاسبية صراحةً (YYYY-MM). الفترة قرار محاسبي مستقل عن
--  التاريخ — تماماً كما في برنامج سطح المكتب — فلو غابت تُشتق من التاريخ.
--
--  التوقيع القديم (بلا p_period) يُحذف أولاً: بقاء النسختين معاً يجعل
--  PostgREST عاجزاً عن اختيار إحداهما (PGRST203).
-- ----------------------------------------------------------------------------
drop function if exists public.post_transaction(
    uuid, timestamptz, text, text, numeric, text, numeric, numeric, numeric, text, text, text);

create or replace function public.post_transaction(
    p_tenant        uuid,
    p_date          timestamptz,
    p_account       text,
    p_op_type       text,
    p_weight        numeric,
    p_note          text default '',
    p_before        numeric default 0,
    p_after         numeric default 0,
    p_trees         numeric default 0,
    p_set_number    text default '',
    p_row_number    text default '',
    p_manual_no     text default '',
    p_period        text default null
) returns bigint
language plpgsql security definer set search_path = public as $$
declare
    v_id bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;
    if coalesce(btrim(p_account), '') = '' or coalesce(btrim(p_op_type), '') = '' then
        raise exception 'الاسم ونوع الحركة مطلوبان';
    end if;
    if p_period is not null and btrim(p_period) <> '' and p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;

    insert into public.transactions(
        tenant_id, seq_no, txn_date, account_name, op_type, weight,
        weight_before, weight_after, note, trees_count,
        set_number, row_number, manual_no, period, created_by)
    values (
        p_tenant, public.next_seq_no(p_tenant), coalesce(p_date, now()),
        btrim(p_account), p_op_type, coalesce(p_weight, 0),
        coalesce(p_before, 0), coalesce(p_after, 0), coalesce(p_note, ''), coalesce(p_trees, 0),
        coalesce(p_set_number, ''), coalesce(p_row_number, ''), coalesce(p_manual_no, ''),
        nullif(btrim(coalesce(p_period, '')), ''), auth.uid())
    returning id into v_id;

    return v_id;
end $$;

-- ----------------------------------------------------------------------------
--  ترحيل عدة حركات دفعة واحدة — داخل معاملة واحدة: إما تُسجَّل كلها أو لا شيء.
--
--  p_rows: مصفوفة JSON، كل عنصر فيه مفاتيح أعمدة الحركة:
--    txn_date, account_name, op_type, weight, weight_before, weight_after,
--    note, trees_count, set_number, row_number, manual_no, period
--
--  p_replace_ids: (اختياري) أرقام حركات تُحذف في المعاملة نفسها قبل الإدراج —
--  هكذا يُعدَّل قيد مرحّل (فاتورة مثلاً) بلا أي لحظة تكون فيها الفاتورة ناقصة.
--  الاستبدال تعديلٌ، فيخضع لقفل التعديل من المدير.
-- ----------------------------------------------------------------------------
create or replace function public.post_transactions_batch(
    p_tenant      uuid,
    p_rows        jsonb,
    p_replace_ids bigint[] default null
) returns integer
language plpgsql security definer set search_path = public as $$
declare
    r          jsonb;
    v_count    integer := 0;
    v_deleted  integer := 0;
    v_expected integer := coalesce(array_length(p_replace_ids, 1), 0);
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'صيغة الحركات غير صحيحة';
    end if;

    if v_expected > 0 then
        if not public.can_edit_tenant(p_tenant) then
            raise exception 'التعديل مقفول من المدير — لا يمكن تعديل حركات مرحّلة';
        end if;

        delete from public.transactions
         where tenant_id = p_tenant
           and id = any(p_replace_ids);
        get diagnostics v_deleted = row_count;

        -- حُذف بعضها من جهاز آخر أثناء التعديل: نتوقف بدل إعادة كتابة نسخة قديمة
        if v_deleted <> v_expected then
            raise exception 'تغيّرت الحركات من جهاز آخر أثناء التعديل — أعد فتحها وحاول مجدداً';
        end if;
    end if;

    for r in select * from jsonb_array_elements(p_rows)
    loop
        if coalesce(btrim(r ->> 'account_name'), '') = ''
           or coalesce(btrim(r ->> 'op_type'), '') = '' then
            raise exception 'كل حركة تحتاج اسماً ونوعاً';
        end if;
        if coalesce(r ->> 'period', '') <> '' and (r ->> 'period') !~ '^\d{4}-\d{2}$' then
            raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', r ->> 'period';
        end if;

        insert into public.transactions(
            tenant_id, seq_no, txn_date, account_name, op_type, weight,
            weight_before, weight_after, note, trees_count,
            set_number, row_number, manual_no, period, created_by)
        values (
            p_tenant,
            public.next_seq_no(p_tenant),
            coalesce((r ->> 'txn_date')::timestamptz, now()),
            btrim(r ->> 'account_name'),
            r ->> 'op_type',
            coalesce((r ->> 'weight')::numeric, 0),
            coalesce((r ->> 'weight_before')::numeric, 0),
            coalesce((r ->> 'weight_after')::numeric, 0),
            coalesce(r ->> 'note', ''),
            coalesce((r ->> 'trees_count')::numeric, 0),
            coalesce(r ->> 'set_number', ''),
            coalesce(r ->> 'row_number', ''),
            coalesce(r ->> 'manual_no', ''),
            nullif(btrim(coalesce(r ->> 'period', '')), ''),
            auth.uid());
        v_count := v_count + 1;
    end loop;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  رصيد الخزينة (ذهب عيار ١٨) حتى نهاية فترة معيّنة
--  = الوارد + الرصيد الافتتاحي − المبيعات − الصادر − الخياس المقفل
--    ± صرف/قبض صناديق الخياس ± القيود اليومية على حساب الخزينة
--  (يُعاد تعريفها في 15_period_ledger.sql لتقرأ دفتر الفترات — فتخصم خياس
--   المصنعين والمركبين الفعلي وتطابق شريط الخزينة في البرنامج)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_balance(p_tenant uuid, p_until_period text default null)
returns numeric
language sql stable security definer set search_path = public as $$
    with t as (
        select op_type, weight, account_name
          from public.transactions
         where tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and status in ('ACTIVE', 'SETTLED_INOUT')
           and (p_until_period is null or period <= p_until_period)
    )
    select coalesce(sum(
        case
            when op_type in ('وارد ذهب (عيار 18)', 'رصيد افتتاحي')             then  weight
            when op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس',
                             'صادر ذهب', 'صرف خياس مقفل')                    then -weight
            when op_type in (select madin_type from public.khayas_boxes())    then -weight
            when op_type in (select qabd_type  from public.khayas_boxes())    then  weight
            when op_type = 'قيد يومي مدين'  and account_name = 'حساب الخزينة' then  weight
            when op_type = 'قيد يومي دائن'  and account_name = 'حساب الخزينة' then -weight
            else 0
        end), 0)
      from t;
$$;

-- ----------------------------------------------------------------------------
--  كشف حركة صندوق خياس لفترة (مدين/دائن/الخياس)
-- ----------------------------------------------------------------------------
create or replace function public.box_period_totals(p_tenant uuid, p_box text, p_period text)
returns table (madin numeric, daen numeric, khayas numeric)
language sql stable security definer set search_path = public as $$
    with cfg as (select * from public.khayas_boxes() where box_name = p_box),
    t as (
        select x.op_type, x.weight, x.account_name
          from public.transactions x
         where x.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and x.status in ('ACTIVE', 'SETTLED_INOUT')
           and x.period = p_period
    ),
    s as (
        select
            coalesce(sum(case when t.op_type = (select madin_type from cfg) then t.weight else 0 end), 0) as madin,
            coalesce(sum(case
                when t.op_type = (select qabd_type from cfg) then t.weight
                when t.op_type = any(public.inbound_types())
                     and t.account_name = (select mustarja_name from cfg) then t.weight
                else 0 end), 0) as daen
          from t
    )
    select s.madin, s.daen, s.madin - s.daen from s;
$$;

-- ----------------------------------------------------------------------------
--  كشف حركة عامل (مصنّع/مركّب) لفترة — مجمّع برقم الصف
--  الفاقد اللحظي للمصنعين = صرف − قبض − بوليش + ليز − مفنش٨ − مفنش٤
--  الفاقد اللحظي للمركبين = صرف − قبض + ليز
-- ----------------------------------------------------------------------------
create or replace function public.worker_ledger(p_tenant uuid, p_worker text, p_period text)
returns table (
    row_number text, set_number text, txn_date timestamptz,
    sarf numeric, qabd numeric, laiz numeric, polish numeric,
    mufanish8 numeric, mufanish4 numeric, wire_back numeric, carat numeric,
    note text, instant_loss numeric
)
language sql stable security definer set search_path = public as $$
    with g as (
        select
            t.row_number as rn,
            max(nullif(t.set_number, '')) as sn,
            min(t.txn_date) as dt,
            sum(case when t.op_type = 'صرف ذهب'            then t.weight else 0 end) as sarf,
            sum(case when t.op_type = 'قبض ذهب'            then t.weight else 0 end) as qabd,
            sum(case when t.op_type = 'الليز'              then t.weight else 0 end) as laiz,
            sum(case when t.op_type = 'البوليش'            then t.weight else 0 end) as polish,
            sum(case when t.op_type = 'المفنش ٨ بالالف'    then t.weight else 0 end) as m8,
            sum(case when t.op_type = 'المفنش ٤ بالالف'    then t.weight else 0 end) as m4,
            sum(case when t.op_type = 'السلك الراجع'       then t.weight else 0 end) as wire,
            max(case when t.op_type = 'العيار بعد الفحص'   then t.weight else 0 end) as carat,
            string_agg(distinct nullif(t.note, ''), ' | ') as note
          from public.transactions t
         where t.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and t.status in ('ACTIVE', 'SETTLED_INOUT')
           and t.account_name = p_worker and t.period = p_period
         group by t.row_number
    )
    select
        g.rn, coalesce(g.sn, ''), g.dt,
        g.sarf, g.qabd, g.laiz, g.polish, g.m8, g.m4, g.wire, g.carat,
        coalesce(g.note, ''),
        round(g.sarf - g.qabd - g.polish + g.laiz - g.m8 - g.m4, 3)
      from g
     order by nullif(regexp_replace(g.rn, '\D', '', 'g'), '')::numeric nulls last, g.rn, g.dt;
$$;

-- ----------------------------------------------------------------------------
--  فواتير المبيعات المرحّلة لفترة — كل فاتورة في صف واحد
-- ----------------------------------------------------------------------------
create or replace function public.sales_invoices(p_tenant uuid, p_period text)
returns table (
    manual_no text, txn_date timestamptz, account_name text,
    gold numeric, gems numeric, stones_after numeric, diamond numeric,
    khayas numeric, lines_count bigint
)
language sql stable security definer set search_path = public as $$
    select
        t.manual_no,
        t.txn_date,
        t.account_name,
        coalesce(sum(case when t.op_type in ('مبيعات ذهب','مبيعات ذهب مع الماس') then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count <> 3 then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count  = 3 then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات الماس' then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'خياس طقوم'    then t.weight else 0 end), 0),
        count(distinct nullif(t.set_number, ''))
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.period = p_period
       and (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
     group by t.manual_no, t.txn_date, t.account_name
     order by t.txn_date;
$$;

-- ----------------------------------------------------------------------------
--  إجمالي فواقد الورشة لفترة
-- ----------------------------------------------------------------------------
create or replace function public.workshop_losses(p_tenant uuid, p_period text)
returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce(sum(b.khayas), 0)
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b;
$$;

-- ----------------------------------------------------------------------------
--  رصيد حساب قبل فترة معيّنة (رصيد أول المدة في كشف الحساب)
--  p_debit_types: الأنواع التي تُعدّ مديناً على الحساب — تُمرَّر من التطبيق
--  حتى يبقى تعريف المدين/الدائن في مكان واحد مع شاشة الكشف نفسها.
-- ----------------------------------------------------------------------------
create or replace function public.account_opening_balance(
    p_tenant      uuid,
    p_account     text,
    p_period      text,
    p_debit_types text[]
) returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce(sum(case when t.op_type = any(p_debit_types) then t.weight else -t.weight end), 0)
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.account_name = p_account
       and t.period < p_period;
$$;

-- ----------------------------------------------------------------------------
--  تسجيل نشاط العميل (آخر دخول / آخر ظهور)
--  المدير المتصفّح لحساب عميل لا يُحسب حضوراً للعميل — وإلا ظهر العميل
--  «متصلاً الآن» في لوحة المتابعة وهو غير متصل أصلاً.
-- ----------------------------------------------------------------------------
create or replace function public.touch_activity(p_tenant uuid, p_is_login boolean default false)
returns void
language plpgsql security definer set search_path = public as $$
begin
    if not public.has_tenant_access(p_tenant) then
        return;
    end if;
    if public.is_admin() and public.current_tenant_id() is distinct from p_tenant then
        return;
    end if;
    update public.tenants
       set last_seen  = now(),
           last_login = case when p_is_login then now() else last_login end
     where id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  لوحة المدير: كل العملاء مع حالتهم
-- ----------------------------------------------------------------------------
create or replace function public.admin_tenants_overview()
returns table (
    id uuid, business_name text, is_active boolean, can_edit boolean,
    last_login timestamptz, last_seen timestamptz,
    is_online boolean, txn_count bigint, last_txn_at timestamptz
)
language sql stable security definer set search_path = public as $$
    select
        t.id, t.business_name, t.is_active, t.can_edit,
        t.last_login, t.last_seen,
        (t.last_seen is not null and t.last_seen > now() - interval '2 minutes'),
        (select count(*) from public.transactions x where x.tenant_id = t.id),
        (select max(x.created_at) from public.transactions x where x.tenant_id = t.id)
      from public.tenants t
     where public.is_admin()
     order by t.business_name;
$$;

grant execute on function public.inbound_types()                  to authenticated;
grant execute on function public.sale_types()                     to authenticated;
grant execute on function public.khayas_boxes()                   to authenticated;
grant execute on function public.next_seq_no(uuid)                to authenticated;
grant execute on function public.post_transaction(uuid, timestamptz, text, text, numeric, text, numeric, numeric, numeric, text, text, text, text) to authenticated;
grant execute on function public.post_transactions_batch(uuid, jsonb, bigint[]) to authenticated;
grant execute on function public.treasury_balance(uuid, text)     to authenticated;
grant execute on function public.box_period_totals(uuid, text, text) to authenticated;
grant execute on function public.worker_ledger(uuid, text, text)  to authenticated;
grant execute on function public.sales_invoices(uuid, text)       to authenticated;
grant execute on function public.workshop_losses(uuid, text)      to authenticated;
grant execute on function public.account_opening_balance(uuid, text, text, text[]) to authenticated;
grant execute on function public.touch_activity(uuid, boolean)    to authenticated;
grant execute on function public.admin_tenants_overview()         to authenticated;

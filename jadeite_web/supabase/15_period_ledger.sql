-- ============================================================================
--  جاديت ERP — دفتر الخزينة للفترات (مطابق لبرنامج سطح المكتب حرفياً)
--
--  لماذا:
--   كان رصيد الخزينة في الويب لا يخصم خياس المصنعين والمركبين الفعلي، ولا يعرف
--   صناديق الخياس المضافة من البرنامج، وأسماء المسترجع فيه تختلف عن أسماء
--   البرنامج — فيختلف رقم الويب عن رقم البرنامج للفترة نفسها.
--
--  القواعد (نفس get_treasury_ledger في البرنامج):
--   • كل حركة تنتمي لفترتها (عمود period) أياً كان تاريخها.
--   • رصيد بداية كل فترة = رصيد نهاية الفترة التي قبلها بالضبط.
--   • الخياس الفعلي للمصنعين والمركبين يُخصم في فترته سواء أُقفل أم لا:
--     الإقفال قيد بين «حساب الخسائر» والصندوق لا يمسّ الخزينة.
--
--  شغّل هذا الملف بعد 14_security_hardening.sql (أو شغّل INSTALL_ALL.sql كاملاً).
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) أسماء المسترجع كما يكتبها برنامج سطح المكتب
--     (الويب كان يستخدم «مسترجع الكاستنج»، والبرنامج «مسترجع كاستنج» — فكان
--      الذهب العائد من صندوق الكاستنج لا يُخصم من خياسه في الويب)
-- ----------------------------------------------------------------------------
create or replace function public.khayas_boxes()
returns table (box_name text, madin_type text, qabd_type text, mustarja_name text)
language sql immutable as $$
    values
        ('الكاستنج',      'صرف كاستنج',     'قبض كاستنج',      'مسترجع كاستنج'),
        ('التلميع',       'صرف تلميع',      'قبض تلميع',       'مسترجع التلميع/البف'),
        ('التلميع/البف',  'صرف تلميع بف',   'قبض تلميع بف',    'مسترجع البوليش'),
        ('خياس الطقوم',   'خياس طقوم',      'قبض خياس طقوم',   'مسترجع خياس الطقوم');
$$;

-- كل الأسماء التي تُعدّ مسترجعاً لصندوق: اسم البرنامج، ثم الاسم القديم في الويب
-- (لحركات سُجّلت من الويب قبل التوحيد). «مسترجع التلميع/البف» القديم للبف لا
-- يُقبل لأنه في البرنامج مسترجع صندوق التلميع — والبرنامج هو المرجع.
create or replace function public.box_mustarja_names(p_box text)
returns text[]
language sql immutable as $$
    select case p_box
        when 'الكاستنج'     then array['مسترجع كاستنج', 'مسترجع الكاستنج']
        when 'التلميع'      then array['مسترجع التلميع/البف', 'مسترجع التلميع']
        when 'التلميع/البف' then array['مسترجع البوليش']
        when 'خياس الطقوم'  then array['مسترجع خياس الطقوم']
        else array['مسترجع ' || p_box]
    end;
$$;

-- الصناديق الثابتة + الصناديق التي أضافها العميل من البرنامج (أقسام_خياس_إضافية)
create or replace function public.tenant_khayas_boxes(p_tenant uuid)
returns table (box_name text, madin_type text, qabd_type text, mustarja_names text[])
language sql stable security definer set search_path = public as $$
    select k.box_name, k.madin_type, k.qabd_type, public.box_mustarja_names(k.box_name)
      from public.khayas_boxes() k
     where (select public.has_tenant_access(p_tenant))
    union
    select a.name, 'صرف ' || a.name, 'قبض ' || a.name, array['مسترجع ' || a.name]
      from public.accounts a
     where a.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and a.category_raw = 'أقسام_خياس_إضافية'
       and a.name not in (select k2.box_name from public.khayas_boxes() k2);
$$;

-- ----------------------------------------------------------------------------
--  ٢) مجاميع صندوق خياس لفترة — يقبل كل أسماء المسترجع للصندوق
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
                     and t.account_name = any(public.box_mustarja_names(p_box)) then t.weight
                else 0 end), 0) as daen
          from t
    )
    select s.madin, s.daen, s.madin - s.daen from s;
$$;

-- ----------------------------------------------------------------------------
--  ٣) الخياس الفعلي لقسم (المصنعين/المركبين) في فترة
--     مطابق لـ calculate_single_ledger + get_actual_section_khayas في البرنامج:
--
--       لكل عامل:
--         المرجع ٧٥٠ = السلك الراجع × العيار بعد الفحص ÷ ٧٥٠ (إن وُجدا)
--         ذهب/باقي   = صرف − قبض − بوليش + ليز − مفنش٨ − مفنش٤   (المصنعين)
--                    = صرف − قبض + ليز                          (المركبين)
--         المسموح    = مفنش٨ × ٠٫٠٠٨ + مفنش٤ × ٠٫٠٠٤             (المصنعين)
--                    = قبض × ٠٫٠٠٨                              (المركبين)
--         الخياس     = المرجع − (ذهب/باقي − المسموح)
--       الخياس الفعلي للقسم = Σ ذهب/باقي − Σ المرجع − Σ الخياس الموجب فقط
--
--     الحركات ACTIVE فقط — مثل البرنامج (الإقفال القديم بالأرشفة يحوّلها SETTLED
--     ويسجّل «صرف خياس مقفل» بدلاً منها، فلا يُخصم الخياس مرتين).
-- ----------------------------------------------------------------------------
create or replace function public.section_actual_khayas(p_tenant uuid, p_section text, p_period text)
returns numeric
language sql stable security definer set search_path = public as $$
    with w as (
        select distinct a.name
          from public.accounts a
         where a.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and coalesce(nullif(a.category_raw, ''), a.category::text) = p_section
    ),
    g as (
        select w.name,
               coalesce(sum(t.weight) filter (where t.op_type = 'صرف ذهب'), 0)         as sarf,
               coalesce(sum(t.weight) filter (where t.op_type = 'قبض ذهب'), 0)         as qabd,
               coalesce(sum(t.weight) filter (where t.op_type = 'الليز'), 0)           as laiz,
               coalesce(sum(t.weight) filter (where t.op_type = 'البوليش'), 0)         as polish,
               coalesce(sum(t.weight) filter (where t.op_type = 'المفنش ٨ بالالف'), 0) as m8,
               coalesce(sum(t.weight) filter (where t.op_type = 'المفنش ٤ بالالف'), 0) as m4,
               coalesce(sum(t.weight) filter (where t.op_type = 'السلك الراجع'), 0)    as wire,
               -- البرنامج يأخذ آخر عيار مسجّل في الفترة (لا مجموعاً)
               coalesce((array_agg(t.weight order by t.seq_no desc)
                         filter (where t.op_type = 'العيار بعد الفحص'))[1], 0)       as carat
          from w
          left join public.transactions t
                 on t.tenant_id = p_tenant
                and t.account_name = w.name
                and t.status = 'ACTIVE'
                and t.period = p_period
         group by w.name
    ),
    l as (
        select case when g.wire > 0 and g.carat > 0
                    then round(g.wire * g.carat / 750.0, 2) else 0 end               as marja,
               case when p_section = 'المركبين'
                    then round(g.sarf - g.qabd + g.laiz, 2)
                    else round(g.sarf - g.qabd - g.polish + g.laiz - g.m8 - g.m4, 2)
               end                                                                   as baqi,
               case when p_section = 'المركبين'
                    then round(g.qabd * 0.008, 2)
                    else round(g.m8 * 0.008, 2) + round(g.m4 * 0.004, 2)
               end                                                                   as allowance
          from g
    ),
    k as (
        select l.baqi, l.marja,
               round(l.marja - round(l.baqi - l.allowance, 2), 2) as khayas
          from l
    )
    select coalesce(round(sum(k.baqi) - sum(k.marja)
                          - coalesce(sum(k.khayas) filter (where k.khayas > 0), 0), 2), 0)
      from k;
$$;

-- ----------------------------------------------------------------------------
--  ٤) دفتر الخزينة لكل الفترات — مصدر واحد للتقرير الشهري ورصيد الخزينة
--
--     البنود (بإشاراتها، مثل treasury_bucket في البرنامج):
--       opening  رصيد افتتاحي / قيد افتتاحي                         (+)
--       inbound  وارد ذهب                                            (+)
--       sales    مبيعات ذهب / صادر ذهب                               (−)
--       boxes    صرف صناديق الخياس (−) وقبضها والمسترجع منها (+)
--       closed   صرف خياس مقفل (إقفال الأرشفة القديم)                (−)
--       journal  قيد يومي على «حساب الخزينة» (مدين + / دائن −)
--       workers  الخياس الفعلي للمصنعين والمركبين                   (−)
--
--     p_include_period: فترة تُعرض حتى لو خلت من الحركات (الفترة المفتوحة حالياً)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_period_ledger(
    p_tenant         uuid,
    p_include_period text default null
)
returns table (
    period text, carry numeric, opening numeric, inbound numeric, sales numeric,
    boxes numeric, closed numeric, journal numeric, workers numeric,
    net numeric, closing numeric
)
language plpgsql stable security definer set search_path = public as $$
#variable_conflict use_column
declare
    v_sarf text[];
    v_qabd text[];
    v_must text[];
begin
    -- لا صلاحية = لا صفوف (لا رسالة خطأ تكشف وجود المصنع)
    if not public.has_tenant_access(p_tenant) then
        return;
    end if;

    select coalesce(array_agg(b.madin_type), '{}'), coalesce(array_agg(b.qabd_type), '{}')
      into v_sarf, v_qabd
      from public.tenant_khayas_boxes(p_tenant) b;
    select coalesce(array_agg(distinct m.name), '{}')
      into v_must
      from public.tenant_khayas_boxes(p_tenant) b
     cross join lateral unnest(b.mustarja_names) as m(name);

    return query
    with c as (
        select t.period as p,
               case
                   when t.op_type = 'رصيد افتتاحي' then 'opening'
                   when t.op_type = 'وارد ذهب (عيار 18)' then
                       case when t.trees_count = 1 and t.note = 'قيد افتتاحي' then 'opening'
                            when t.account_name = any(v_must) then 'boxes'
                            else 'inbound' end
                   when t.op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس', 'صادر ذهب') then 'sales'
                   when t.op_type = 'صرف خياس مقفل' then 'closed'
                   when t.op_type = any(v_sarf) then 'boxes'
                   when t.op_type = any(v_qabd) then 'boxes'
                   when t.account_name = 'حساب الخزينة'
                        and t.op_type in ('قيد يومي مدين', 'قيد يومي دائن') then 'journal'
               end as bucket,
               case
                   when t.op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس', 'صادر ذهب',
                                      'صرف خياس مقفل') then -t.weight
                   when t.op_type = 'وارد ذهب (عيار 18)' then t.weight
                   when t.op_type = any(v_sarf) then -t.weight
                   when t.op_type = 'قيد يومي دائن' then -t.weight
                   else t.weight
               end as amount
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.status in ('ACTIVE', 'SETTLED_INOUT')
           and coalesce(t.period, '') <> ''
    ),
    periods as (
        select distinct c.p from c
        union
        select p_include_period where coalesce(p_include_period, '') ~ '^\d{4}-\d{2}$'
    ),
    s as (
        select pr.p,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'opening'), 0), 2) as s_opening,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'inbound'), 0), 2) as s_inbound,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'sales'), 0), 2)   as s_sales,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'boxes'), 0), 2)   as s_boxes,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'closed'), 0), 2)  as s_closed,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'journal'), 0), 2) as s_journal,
               -round(public.section_actual_khayas(p_tenant, 'المصنعين', pr.p)
                      + public.section_actual_khayas(p_tenant, 'المركبين', pr.p), 2)  as s_workers
          from periods pr
          left join c on c.p = pr.p
         group by pr.p
    ),
    n as (
        select s.*,
               s.s_opening + s.s_inbound + s.s_sales + s.s_boxes
                 + s.s_closed + s.s_journal + s.s_workers as s_net
          from s
    )
    select n.p,
           coalesce(sum(n.s_net) over (order by n.p rows between unbounded preceding and 1 preceding), 0),
           n.s_opening, n.s_inbound, n.s_sales, n.s_boxes, n.s_closed, n.s_journal, n.s_workers,
           n.s_net,
           sum(n.s_net) over (order by n.p rows between unbounded preceding and current row)
      from n
     order by n.p;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) رصيد الخزينة حتى نهاية فترة = رصيد نهايتها في الدفتر نفسه
--     (فلا يختلف رقم «رصيد الخزينة» عن آخر عمود في التقرير الشهري)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_balance(p_tenant uuid, p_until_period text default null)
returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce((
        select l.closing
          from public.treasury_period_ledger(p_tenant, p_until_period) l
         where p_until_period is null or l.period <= p_until_period
         order by l.period desc
         limit 1), 0);
$$;

-- ----------------------------------------------------------------------------
--  ٦) الصلاحيات: للمستخدمين المسجّلين فقط (كل دالة تتحقق من المصنع داخلياً)
-- ----------------------------------------------------------------------------
revoke execute on function public.khayas_boxes()                             from public, anon;
revoke execute on function public.box_mustarja_names(text)                   from public, anon;
revoke execute on function public.tenant_khayas_boxes(uuid)                  from public, anon;
revoke execute on function public.box_period_totals(uuid, text, text)        from public, anon;
revoke execute on function public.section_actual_khayas(uuid, text, text)    from public, anon;
revoke execute on function public.treasury_period_ledger(uuid, text)         from public, anon;
revoke execute on function public.treasury_balance(uuid, text)               from public, anon;

grant execute on function public.khayas_boxes()                              to authenticated;
grant execute on function public.box_mustarja_names(text)                    to authenticated;
grant execute on function public.tenant_khayas_boxes(uuid)                   to authenticated;
grant execute on function public.box_period_totals(uuid, text, text)         to authenticated;
grant execute on function public.section_actual_khayas(uuid, text, text)     to authenticated;
grant execute on function public.treasury_period_ledger(uuid, text)          to authenticated;
grant execute on function public.treasury_balance(uuid, text)                to authenticated;

notify pgrst, 'reload schema';

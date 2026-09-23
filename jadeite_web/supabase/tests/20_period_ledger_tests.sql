-- ============================================================================
--  اختبارات دفتر الخزينة للفترات (15_period_ledger.sql)
--
--  نفس بيانات test_period_ledger.py في برنامج سطح المكتب حرفياً، والمتوقع
--  نفس الأرقام: نهاية فترة ٨ = 983، ونهاية فترة ٩ = 1018 — رقم واحد للويب
--  والبرنامج.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

insert into auth.users(id, email) values
    ('33333333-3333-3333-3333-333333333333', 'owner-c@test')
on conflict do nothing;
insert into public.tenants(id, business_name) values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'مصنع ج')
on conflict do nothing;
insert into public.app_users(id, tenant_id, role) values
    ('33333333-3333-3333-3333-333333333333', 'cccccccc-cccc-cccc-cccc-cccccccccccc', 'owner')
on conflict do nothing;

insert into public.accounts(tenant_id, name, category, category_raw) values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'عامل أ', 'المصنعين', 'المصنعين'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'مركب ب', 'المركبين', 'المركبين');

insert into public.transactions
    (tenant_id, seq_no, txn_date, account_name, op_type, weight, status, trees_count, note, period)
values
    -- ═══ فترة ٨ ═══
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  1, '2026-08-10', 'المصنع',        'وارد ذهب (عيار 18)', 1000, 'ACTIVE', 1, 'قيد افتتاحي', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  2, '2026-08-10', 'المصنع',        'وارد ذهب (عيار 18)',  200, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  3, '2026-08-10', 'عميل',          'مبيعات ذهب',          150, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  4, '2026-08-10', 'المصنع',        'صادر ذهب',             30, 'ACTIVE', 0, '', '2026-08'),
    -- تاريخها في شهر ٩ لكنها سُجّلت على فترة ٨ ← تنتمي لفترة ٨
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  5, '2026-09-02', 'عميل',          'مبيعات ذهب',           20, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  6, '2026-08-10', 'الكاستنج',      'صرف كاستنج',           40, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  7, '2026-08-10', 'الكاستنج',      'قبض كاستنج',           25, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  8, '2026-08-10', 'مسترجع كاستنج', 'وارد ذهب (عيار 18)',    5, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc',  9, '2026-08-10', 'عامل أ',        'صرف ذهب',             100, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 10, '2026-08-10', 'عامل أ',        'قبض ذهب',              90, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 11, '2026-08-10', 'حساب الخزينة',  'قيد يومي مدين',         3, 'ACTIVE', 0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 12, '2026-08-10', 'خياس الطقوم',   'خياس طقوم',             7, 'MEMO',   0, '', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 13, '2026-08-10', 'عميل',          'مبيعات ذهب',          999, 'SETTLED', 0, '', '2026-08'),
    -- ═══ فترة ٩ ═══
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 14, '2026-09-10', 'المصنع',        'وارد ذهب (عيار 18)',   50, 'ACTIVE', 0, '', '2026-09'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 15, '2026-09-10', 'عميل',          'مبيعات ذهب',           10, 'ACTIVE', 0, '', '2026-09'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 16, '2026-09-10', 'مركب ب',        'صرف ذهب',              30, 'ACTIVE', 0, '', '2026-09'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 17, '2026-09-10', 'مركب ب',        'قبض ذهب',              25, 'ACTIVE', 0, '', '2026-09');

-- ---------------------------------------------------------------------------
--  ١) الدفتر والترحيل — بصلاحية مالك المصنع (ج)
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"33333333-3333-3333-3333-333333333333","role":"authenticated"}', true) \g /dev/null
do $$
declare
    c   uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    r8  record;
    r9  record;
    r10 record;
    v   numeric;
begin
    select * into r8 from public.treasury_period_ledger(c) where period = '2026-08';
    select * into r9 from public.treasury_period_ledger(c) where period = '2026-09';

    assert r8.carry = 0 and r8.opening = 1000 and r8.inbound = 200 and r8.sales = -200
       and r8.boxes = -10 and r8.closed = 0 and r8.journal = 3 and r8.workers = -10,
        format('بنود فترة ٨ خاطئة: %s', row_to_json(r8));
    assert r8.closing = 983, format('نهاية فترة ٨ = %s (المتوقع 983 كما في البرنامج)', r8.closing);
    assert r9.carry = r8.closing, format('بداية فترة ٩ (%s) ≠ نهاية فترة ٨ (%s)', r9.carry, r8.closing);
    assert r9.workers = -5 and r9.closing = 1018,
        format('فترة ٩ خاطئة: %s (المتوقع نهاية 1018)', row_to_json(r9));

    -- رصيد الخزينة = نهاية الفترة في الدفتر نفسه
    assert public.treasury_balance(c, '2026-08') = 983, 'رصيد الخزينة لفترة ٨ ≠ الدفتر';
    assert public.treasury_balance(c, '2026-09') = 1018, 'رصيد الخزينة لفترة ٩ ≠ الدفتر';
    assert public.treasury_balance(c) = 1018, 'رصيد الخزينة الكلي ≠ نهاية آخر فترة';

    -- فترة مفتوحة بلا حركات: تبدأ وتنتهي برصيد سابقتها
    select * into r10 from public.treasury_period_ledger(c, '2026-10') where period = '2026-10';
    assert r10.carry = 1018 and r10.closing = 1018, 'الفترة الجديدة الفارغة لم تبدأ برصيد سابقتها';
    assert public.treasury_balance(c, '2026-10') = 1018, 'رصيد فترة جديدة فارغة ≠ نهاية سابقتها';

    -- الخياس الفعلي بمعادلة البرنامج
    assert public.section_actual_khayas(c, 'المصنعين', '2026-08') = 10, 'خياس المصنعين لفترة ٨';
    assert public.section_actual_khayas(c, 'المركبين', '2026-09') = 5, 'خياس المركبين لفترة ٩';

    -- المسترجع باسم البرنامج يُخصم من خياس الصندوق
    select khayas into v from public.box_period_totals(c, 'الكاستنج', '2026-08');
    assert v = 10, format('خياس الكاستنج = %s (المتوقع 40 − 25 − 5 = 10)', v);
end $$;
commit;

-- ---------------------------------------------------------------------------
--  ٢) الإقفال لا يغيّر الخزينة ولا رصيد افتتاح الفترة التالية
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"33333333-3333-3333-3333-333333333333","role":"authenticated"}', true) \g /dev/null
do $$
declare
    c uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
begin
    -- إقفال صندوق من الويب (قيد بين الصندوق وحساب الخسائر)
    assert public.close_khayas_box(c, 'الكاستنج', '2026-08') = 10, 'إقفال الكاستنج';
    -- وإقفال خياس المصنعين كما يسجّله البرنامج (_post_closing_entry)
    perform public.post_transactions_batch(c, jsonb_build_array(
        jsonb_build_object('account_name', 'حساب الخسائر', 'op_type', 'قيد يومي مدين', 'weight', 10,
                           'period', '2026-08', 'txn_date', '2026-08-31T23:59:00Z'),
        jsonb_build_object('account_name', 'صندوق خياس المصنعين', 'op_type', 'قيد يومي دائن', 'weight', 10,
                           'period', '2026-08', 'txn_date', '2026-08-31T23:59:00Z')));

    assert public.treasury_balance(c, '2026-08') = 983, 'الإقفال غيّر نهاية فترة ٨';
    assert (select carry from public.treasury_period_ledger(c) where period = '2026-09') = 983,
        'الإقفال غيّر رصيد افتتاح فترة ٩ (كان يرتفع بقيمة المُقفل)';
    assert public.treasury_balance(c, '2026-09') = 1018, 'الإقفال غيّر نهاية فترة ٩';
end $$;
rollback;

-- الإقفال القديم بالأرشفة (SETTLED + صرف خياس مقفل) يعطي الرصيد نفسه
begin;
update public.transactions set status = 'SETTLED'
 where tenant_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc' and account_name = 'عامل أ';
insert into public.transactions (tenant_id, seq_no, txn_date, account_name, op_type, weight, status, period)
values ('cccccccc-cccc-cccc-cccc-cccccccccccc', 90, '2026-08-31', 'الخياس الفعلي لقسم (المصنعين)',
        'صرف خياس مقفل', 10, 'ACTIVE', '2026-08');
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"33333333-3333-3333-3333-333333333333","role":"authenticated"}', true) \g /dev/null
do $$
declare r record;
begin
    select * into r from public.treasury_period_ledger('cccccccc-cccc-cccc-cccc-cccccccccccc')
     where period = '2026-08';
    assert r.workers = 0 and r.closed = -10 and r.closing = 983,
        format('الإقفال القديم خصم مرتين أو لم يخصم: %s', row_to_json(r));
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٣) أسماء المسترجع القديمة في الويب + الصناديق المضافة من البرنامج
-- ---------------------------------------------------------------------------
begin;
insert into public.accounts(tenant_id, name, category, category_raw) values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'الصب', 'حسابات عامة', 'أقسام_خياس_إضافية');
insert into public.transactions (tenant_id, seq_no, txn_date, account_name, op_type, weight, status, period)
values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 91, '2026-08-20', 'مسترجع الكاستنج', 'وارد ذهب (عيار 18)', 2, 'ACTIVE', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 92, '2026-08-20', 'الصب',           'صرف الصب',           6, 'ACTIVE', '2026-08'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 93, '2026-08-20', 'الصب',           'قبض الصب',           1, 'ACTIVE', '2026-08');
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"33333333-3333-3333-3333-333333333333","role":"authenticated"}', true) \g /dev/null
do $$
declare
    c uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    r record;
begin
    assert (select khayas from public.box_period_totals(c, 'الكاستنج', '2026-08')) = 8,
        'اسم المسترجع القديم في الويب لم يُخصم من الصندوق';
    select * into r from public.treasury_period_ledger(c) where period = '2026-08';
    -- الصناديق: −10 + 2 (مسترجع) − 6 + 1 (الصب) = −13 ، والوارد لم يتغيّر
    assert r.boxes = -13 and r.inbound = 200, format('صناديق فترة ٨: %s', row_to_json(r));
    assert r.closing = 980, format('نهاية فترة ٨ = %s (المتوقع 980)', r.closing);
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٤) معادلة الخياس الفعلي (المرجع ٧٥٠ والمسموح ٨ بالألف)
-- ---------------------------------------------------------------------------
begin;
insert into public.transactions (tenant_id, seq_no, txn_date, account_name, op_type, weight, status, period)
values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 94, '2026-07-10', 'عامل أ', 'صرف ذهب',          20, 'ACTIVE', '2026-07'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 95, '2026-07-10', 'عامل أ', 'قبض ذهب',           5, 'ACTIVE', '2026-07'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 96, '2026-07-10', 'عامل أ', 'المفنش ٨ بالالف',  10, 'ACTIVE', '2026-07'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 97, '2026-07-10', 'عامل أ', 'السلك الراجع',      3, 'ACTIVE', '2026-07'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 98, '2026-07-10', 'عامل أ', 'العيار بعد الفحص', 500, 'ACTIVE', '2026-07');
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"33333333-3333-3333-3333-333333333333","role":"authenticated"}', true) \g /dev/null
do $$
declare v numeric;
begin
    -- ذهب/باقي = 20 − 5 − 10 = 5 ، المرجع = 3 × 500 ÷ 750 = 2 ، الخياس = 2 − (5 − 0.08) = −2.92
    -- الفعلي = 5 − 2 − 0 (لا خياس موجب) = 3
    v := public.section_actual_khayas('cccccccc-cccc-cccc-cccc-cccccccccccc', 'المصنعين', '2026-07');
    assert v = 3, format('الخياس الفعلي = %s (المتوقع 3)', v);
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٥) العزل: مصنع آخر لا يرى الدفتر، والزائر لا يستدعيه
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}', true) \g /dev/null
do $$
declare c uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
begin
    assert (select count(*) from public.treasury_period_ledger(c)) = 0, 'تسريب: treasury_period_ledger';
    assert public.treasury_balance(c) = 0, 'تسريب: treasury_balance';
    assert public.section_actual_khayas(c, 'المصنعين', '2026-08') = 0, 'تسريب: section_actual_khayas';
    assert (select count(*) from public.tenant_khayas_boxes(c)) = 0, 'تسريب: tenant_khayas_boxes';
end $$;
rollback;

begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
do $$
begin
    perform * from public.treasury_period_ledger('cccccccc-cccc-cccc-cccc-cccccccccccc');
    raise exception 'FAIL: anon استدعى treasury_period_ledger';
exception when insufficient_privilege then null;
end $$;
rollback;

select '✅ دفتر الفترات مطابق لبرنامج سطح المكتب' as النتيجة;

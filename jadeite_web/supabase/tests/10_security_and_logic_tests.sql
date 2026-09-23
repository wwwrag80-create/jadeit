-- ============================================================================
--  اختبارات قاعدة البيانات: العزل بين المصانع + الصلاحيات + المنطق المحاسبي
--
--  تُشغَّل على قاعدة اختبار فقط بعد 00_supabase_stub.sql و INSTALL_ALL.sql:
--      bash supabase/tests/run_sql_tests.sh
--  أي فشل يوقف التشغيل برسالة واضحة (ON_ERROR_STOP).
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- ---------------------------------------------------------------------------
--  تجهيز: مصنعان (أ، ب) + مالك لكل منهما + مدير عام
-- ---------------------------------------------------------------------------
insert into auth.users(id, email) values
    ('11111111-1111-1111-1111-111111111111', 'owner-a@test'),
    ('22222222-2222-2222-2222-222222222222', 'owner-b@test'),
    ('99999999-9999-9999-9999-999999999999', 'admin@test')
on conflict do nothing;

insert into public.tenants(id, business_name) values
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'مصنع أ'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'مصنع ب')
on conflict do nothing;

insert into public.app_users(id, tenant_id, role) values
    ('11111111-1111-1111-1111-111111111111', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'owner'),
    ('22222222-2222-2222-2222-222222222222', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'owner'),
    ('99999999-9999-9999-9999-999999999999', null, 'admin')
on conflict do nothing;

-- مصنع ب يعمل ببرنامج سطح المكتب: جهاز مسجّل + حركات مرفوعة منه
insert into public.tenant_devices(tenant_id, device_id) values
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'pc-1')
on conflict do nothing;

insert into public.transactions
    (tenant_id, seq_no, txn_date, account_name, op_type, weight, status, trees_count, manual_no, period, device_id)
values
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 1, '2026-09-05', 'مورد سري', 'وارد ذهب (عيار 18)', 500, 'ACTIVE', 0, '', '2026-09', 'pc-1'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 2, '2026-09-06', 'عميل سري', 'مبيعات ذهب', 120, 'ACTIVE', 0, '77', '2026-09', 'pc-1'),
    -- سطر معلوماتي: لا يُحتسب أبداً
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 3, '2026-09-06', 'عميل سري', 'خياس طقوم', 9, 'MEMO', 7, '77', '2026-09', 'pc-1'),
    -- حالة قديمة يحتسبها برنامج سطح المكتب
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 4, '2026-09-07', 'المصنع', 'رصيد افتتاحي', 30, 'SETTLED_INOUT', 0, '', '2026-09', 'pc-1'),
    -- أُقفلت فترته وحلّ محلّه قيد الإقفال: لا يُحتسب
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 5, '2026-09-07', 'مورد سري', 'وارد ذهب (عيار 18)', 1000, 'SETTLED', 0, '', '2026-09', 'pc-1');

-- نظام الدخول القديم (clients) لاختبار حدّ محاولات الدخول
create table if not exists public.clients (
    client_id     uuid primary key,
    username      text,
    password_hash text,
    business_name text,
    can_edit      boolean default true,
    is_active     boolean default true,
    last_login    timestamptz,
    last_seen     timestamptz
);
insert into public.clients values
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'factory_b', 'correct-hash', 'مصنع ب', true, true, null, null)
on conflict do nothing;

-- ---------------------------------------------------------------------------
--  ١) عميل (أ) لا يقرأ ولا يكتب شيئاً من مصنع (ب) عبر أي دالة
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}', true) \g /dev/null

do $$
declare b uuid := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
begin
    assert public.treasury_balance(b) = 0, 'تسريب: treasury_balance يقرأ مصنعاً آخر';
    assert (select count(*) from public.search_transactions(b, 'الكل', '1')) = 0, 'تسريب: search_transactions';
    assert (select count(*) from public.invoice_archive(b)) = 0, 'تسريب: invoice_archive';
    assert (select count(*) from public.sales_invoices(b, '2026-09')) = 0, 'تسريب: sales_invoices';
    assert (select count(*) from public.journal_entries(b, '2026-09')) = 0, 'تسريب: journal_entries';
    assert (select count(*) from public.worker_ledger(b, 'مورد سري', '2026-09')) = 0, 'تسريب: worker_ledger';
    assert (select count(*) from public.boxes_closing_status(b, '2026-09')) = 0, 'تسريب: boxes_closing_status';
    assert (select count(*) from public.losses_breakdown(b, '2026-09')) = 0, 'تسريب: losses_breakdown';
    assert public.account_opening_balance(b, 'مورد سري', '2026-10', array['مبيعات ذهب']) = 0,
        'تسريب: account_opening_balance';
    assert (select count(*) from public.transactions where tenant_id = b) = 0, 'تسريب: RLS على transactions';

    begin
        perform public.post_transaction(b, now(), 'x', 'وارد ذهب (عيار 18)', 1);
        raise exception 'FAIL: عميل كتب حركة في مصنع غيره';
    exception when others then
        if sqlerrm like 'FAIL:%' then raise; end if;
    end;
end $$;
rollback;

-- الدوال الحسّاسة ممنوعة على العميل كلياً (رمز المزامنة لا يُكشف)
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}', true) \g /dev/null
do $$
begin
    begin
        perform * from public.ensure_tenant_link('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb');
        raise exception 'FAIL: ensure_tenant_link متاحة للعملاء (تكشف رمز المزامنة)';
    exception when insufficient_privilege then null;
    end;
    begin
        perform * from public.diagnose_client_sync('factory_b');
        raise exception 'FAIL: diagnose_client_sync متاحة للعملاء';
    exception when insufficient_privilege then null;
    end;
    begin
        perform * from public.run_maintenance();
        raise exception 'FAIL: run_maintenance متاحة للعملاء';
    exception when insufficient_privilege then null;
    end;
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٢) الزائر بمفتاح anon (بلا دخول) لا يستدعي إلا دوال المزامنة
-- ---------------------------------------------------------------------------
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
do $$
declare
    fn text;
begin
    foreach fn in array array[
        'select public.treasury_balance(''bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'')',
        'select * from public.search_transactions(''bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'', ''الكل'', ''1'')',
        'select * from public.invoice_archive(''bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'')',
        'select * from public.run_maintenance()',
        'select public.purge_audit_log(30)'
    ] loop
        begin
            execute fn;
            raise exception 'FAIL: anon نفّذ: %', fn;
        exception when insufficient_privilege then null;
        end;
    end loop;
end $$;

-- ورمز مزامنة خاطئ يُرفض
do $$
begin
    perform public.sync_push_transactions('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
        gen_random_uuid(), 'x', '[]'::jsonb);
    raise exception 'FAIL: رمز مزامنة خاطئ قُبل';
exception when others then
    if sqlerrm like 'FAIL:%' then raise; end if;
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٣) المنطق المحاسبي — بصلاحية مالك المصنع (ب)
-- ---------------------------------------------------------------------------
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}', true) \g /dev/null
do $$
declare
    b uuid := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
    v numeric;
    v_id bigint;
    v_seq bigint;
    v_period text;
    v_before int;
begin
    -- الخزينة = ٥٠٠ وارد − ١٢٠ مبيعات + ٣٠ رصيد افتتاحي (SETTLED_INOUT يُحتسب)
    --          والسطر المعلوماتي MEMO و SETTLED لا يُحتسبان
    v := public.treasury_balance(b);
    assert v = 410, format('رصيد الخزينة خاطئ: %s (المتوقع 410)', v);

    -- صندوق خياس الطقوم لا يرى السطر المعلوماتي
    select khayas into v from public.box_period_totals(b, 'خياس الطقوم', '2026-09');
    assert v = 0, format('السطر المعلوماتي دخل صندوق الخياس: %s', v);

    -- الفترة الصريحة تُحترم حتى لو اختلف شهر التاريخ (مثل برنامج سطح المكتب)
    v_id := public.post_transaction(b, '2026-09-02 10:00+03', 'مورد', 'وارد ذهب (عيار 18)', 5,
                                    p_period => '2026-08');
    select period, seq_no into v_period, v_seq from public.transactions where id = v_id;
    assert v_period = '2026-08', format('الفترة الصريحة تجاهلت: %s', v_period);

    -- مصنع يعمل ببرنامج سطح المكتب: حركات الويب في نطاق مستقل لا يصطدم بترقيم الجهاز
    assert v_seq >= 1000000000, format('رقم حركة الويب قد يصطدم بترقيم الجهاز: %s', v_seq);

    -- بلا فترة: تُشتق من التاريخ
    v_id := public.post_transaction(b, '2026-07-15 12:00+00', 'مورد', 'وارد الماس', 2);
    select period into v_period from public.transactions where id = v_id;
    assert v_period = '2026-07', format('اشتقاق الفترة من التاريخ خاطئ: %s', v_period);

    -- الدفعة ذرّية: سطر معيب يُلغي الدفعة كلها
    select count(*) into v_before from public.transactions where tenant_id = b;
    begin
        perform public.post_transactions_batch(b, jsonb_build_array(
            jsonb_build_object('account_name', 'عميل', 'op_type', 'مبيعات ذهب', 'weight', 3, 'period', '2026-09'),
            jsonb_build_object('account_name', '', 'op_type', 'مبيعات ذهب', 'weight', 4)
        ));
        raise exception 'FAIL: دفعة بسطر معيب قُبلت';
    exception when others then
        if sqlerrm like 'FAIL:%' then raise; end if;
    end;
    assert (select count(*) from public.transactions where tenant_id = b) = v_before,
        'الدفعة المعيبة سجّلت جزءاً منها';

    -- دفعة سليمة
    assert public.post_transactions_batch(b, jsonb_build_array(
        jsonb_build_object('account_name', 'عميل', 'op_type', 'مبيعات ذهب', 'weight', 3,
                           'manual_no', 'W1', 'period', '2026-09', 'txn_date', '2026-09-10T08:00:00Z'),
        jsonb_build_object('account_name', 'عميل', 'op_type', 'مبيعات الماس', 'weight', 1,
                           'manual_no', 'W1', 'period', '2026-09', 'txn_date', '2026-09-10T08:00:00Z')
    )) = 2, 'الدفعة السليمة لم تُسجَّل';
end $$;
commit;

-- قفل التعديل: الاستبدال (تعديل فاتورة) ممنوع، والتسجيل الجديد مسموح
update public.tenants set can_edit = false where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}', true) \g /dev/null
do $$
declare
    b uuid := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
    v_ids bigint[];
begin
    select array_agg(id) into v_ids from public.transactions where tenant_id = b and manual_no = 'W1';
    begin
        perform public.post_transactions_batch(b, jsonb_build_array(
            jsonb_build_object('account_name', 'عميل', 'op_type', 'مبيعات ذهب', 'weight', 9)), v_ids);
        raise exception 'FAIL: تعديل فاتورة مع قفل التعديل';
    exception when others then
        if sqlerrm like 'FAIL:%' then raise; end if;
    end;
    -- التسجيل الجديد مسموح رغم القفل (كما يوثّق النظام)
    perform public.post_transaction(b, now(), 'مورد', 'وارد الماس', 1, p_period => '2026-09');
end $$;
rollback;
update public.tenants set can_edit = true where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

-- الاستبدال بعد فتح القفل + رفض أرقام قديمة (حُذفت من جهاز آخر)
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}', true) \g /dev/null
do $$
declare
    b uuid := 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
    v_ids bigint[];
begin
    select array_agg(id) into v_ids from public.transactions where tenant_id = b and manual_no = 'W1';
    assert public.post_transactions_batch(b, jsonb_build_array(
        jsonb_build_object('account_name', 'عميل', 'op_type', 'مبيعات ذهب', 'weight', 7,
                           'manual_no', 'W1', 'period', '2026-09')), v_ids) = 1, 'الاستبدال فشل';
    assert (select sum(weight) from public.transactions where tenant_id = b and manual_no = 'W1') = 7,
        'الاستبدال لم يحذف السطور القديمة';
    begin
        perform public.post_transactions_batch(b, '[]'::jsonb, v_ids);  -- الأرقام حُذفت للتو
        raise exception 'FAIL: استبدال بأرقام غير موجودة قُبل';
    exception when others then
        if sqlerrm like 'FAIL:%' then raise; end if;
    end;

    -- قيد الإقفال لا يُحذف من شاشة القيود (يترك الصندوق مقفلاً بلا قيد)
    begin
        perform public.delete_journal_entry(b, 'CLOSE-الكاستنج-2026-09');
        raise exception 'FAIL: حذف قيد إقفال من شاشة القيود';
    exception when others then
        if sqlerrm like 'FAIL:%' then raise; end if;
    end;
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٤) العميل لا يرفع القيود عن نفسه (المزامنة/الرمز/القفل)
-- ---------------------------------------------------------------------------
update public.tenants set sync_enabled = false, can_edit = false
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated"}', true) \g /dev/null
update public.tenants
   set sync_enabled = true, can_edit = true, sync_token = gen_random_uuid()
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
commit;
do $$
begin
    assert (select not sync_enabled and not can_edit from public.tenants
             where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'),
        'العميل أعاد تفعيل المزامنة/التعديل بنفسه';
end $$;
update public.tenants set sync_enabled = true, can_edit = true
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

-- ---------------------------------------------------------------------------
--  ٥) المدير المتصفّح لحساب عميل لا يجعله «متصلاً الآن»
-- ---------------------------------------------------------------------------
update public.tenants set last_seen = null where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"99999999-9999-9999-9999-999999999999","role":"authenticated"}', true) \g /dev/null
select public.touch_activity('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', false);
-- والمدير يرى كل شيء
do $$
begin
    assert public.treasury_balance('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') > 0, 'المدير لا يرى رصيد العميل';
end $$;
commit;
do $$
begin
    assert (select last_seen is null from public.tenants where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'),
        'نبضة المدير سُجّلت كحضور للعميل';
end $$;

-- ---------------------------------------------------------------------------
--  ٦) المزامنة: السطر المعلوماتي MEMO يُرفع بحالته
-- ---------------------------------------------------------------------------
select sync_token as b_token from public.tenants
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \gset
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
select public.sync_push_transactions(
    'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
    :'b_token'::uuid,
    'pc-1',
    '[{"seq_no": 50, "txn_date": "2026-09-08T10:00:00+03:00", "account_name": "عميل",
       "op_type": "خياس طقوم", "weight": 2, "status": "MEMO", "trees_count": 9, "period": "2026-09"}]'::jsonb);
commit;
do $$
begin
    assert (select status::text from public.transactions
             where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 50) = 'MEMO',
        'حالة MEMO لم تُحفظ عند الرفع';
end $$;

-- ---------------------------------------------------------------------------
--  ٧) حدّ محاولات الدخول: بعد ١٠ محاولات فاشلة تُرفض حتى كلمة المرور الصحيحة مؤقتاً
-- ---------------------------------------------------------------------------
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
do $$
declare i int;
begin
    assert (select count(*) from public.client_login_full('factory_b', 'correct-hash')) = 1,
        'الدخول الصحيح فشل';
    for i in 1..10 loop
        perform * from public.client_login_full('factory_b', 'wrong-' || i);
    end loop;
    assert (select count(*) from public.client_login_full('factory_b', 'correct-hash')) = 0,
        'لا يوجد حدّ لمحاولات تخمين كلمة المرور';
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٨) سجل التدقيق المختصر: التعديل بلا تغيير حقيقي لا يُسجَّل
-- ---------------------------------------------------------------------------
do $$
declare
    v_before bigint;
begin
    select count(*) into v_before from public.audit_log;
    update public.transactions set weight = weight
     where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 1;
    assert (select count(*) from public.audit_log) = v_before, 'تعديل بلا تغيير سُجّل في التدقيق';

    update public.transactions set note = 'تعديل للاختبار'
     where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 1;
    assert (select after_data ? 'note' and not (after_data ? 'weight')
              from public.audit_log order by id desc limit 1),
        'سجل التدقيق لا يحفظ الفرق فقط';
end $$;

select '✅ كل اختبارات قاعدة البيانات نجحت' as النتيجة;

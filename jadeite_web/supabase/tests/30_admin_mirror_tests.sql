-- ============================================================================
--  اختبارات 16_admin_mirror_parity.sql — المدير يرى ما عند العميل حرفياً
--  (ترتيب الأسماء، الإعدادات، نص التاريخ) — باتجاه واحد وبرمز المزامنة
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

select sync_token as b_token from public.tenants
 where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \gset

-- ---------------------------------------------------------------------------
--  ١) جهاز العميل (anon + رمز المزامنة) يرفع الأسماء بترتيبها والإعدادات والتاريخ
-- ---------------------------------------------------------------------------
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
select public.sync_push_accounts('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid,
    '[{"name":"يوسف","category":"المصنعين","sort_order":3},
      {"name":"أحمد","category":"المصنعين","sort_order":7},
      {"name":"الصب","category":"أقسام_خياس_إضافية","sort_order":5},
      {"name":"محمد","category":"المصنعين","sort_order":9}]'::jsonb) \g /dev/null
select public.sync_push_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid,
    '[{"key":"recovery_pct_تلميع","value":"40"},
      {"key":"col_labels_workers","value":"{\"قبض\": \"استلام\"}"},
      {"key":"neg_color_المصنعين","value":"1"}]'::jsonb) \g /dev/null
select public.sync_push_transactions('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid, 'pc-1',
    '[{"seq_no": 60, "txn_date": "2026-08-31T23:30:00+03:00", "local_date": "2026-08-31 23:30:00",
       "account_name": "يوسف", "op_type": "صرف ذهب", "weight": 12.5, "period": "2026-08"}]'::jsonb) \g /dev/null
commit;

-- الترتيب والإعدادات والتاريخ كما يسحبها برنامج المدير
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
select public.sync_pull_accounts('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid) \g /dev/null
create temp table pulled_names on commit drop as
    select row_number() over () as pos, name, category
      from public.sync_pull_accounts('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid);
create temp table pulled_settings on commit drop as
    select * from public.sync_pull_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid);
create temp table pulled_txn on commit drop as
    select * from public.sync_pull_transactions('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 59, 10, :'b_token'::uuid);
do $$
begin
    assert (select array_agg(name order by pos) from pulled_names where category = 'المصنعين')
           = array['يوسف', 'أحمد', 'محمد'],
        format('ترتيب الأسماء ليس ترتيب العميل: %s',
               (select array_agg(name order by pos) from pulled_names where category = 'المصنعين'));
    assert (select min(pos) from pulled_names where name = 'يوسف')
         < (select min(pos) from pulled_names where name = 'الصب'),
        'الترتيب عبر الأقسام لا يتبع ترتيب العميل';
    assert (select pos from pulled_names where name = 'مورد سري') is null
        or (select pos from pulled_names where name = 'مورد سري')
         > (select max(pos) from pulled_names where name in ('يوسف', 'أحمد', 'محمد', 'الصب')),
        'الحسابات بلا ترتيب يجب أن تأتي بعد أسماء العميل';

    assert (select value from pulled_settings where key = 'recovery_pct_تلميع') = '40',
        'نسبة الاسترجاع لم تصل للمدير';
    assert (select value from pulled_settings where key = 'col_labels_workers') = '{"قبض": "استلام"}',
        'اسم العمود المخصّص لم يصل للمدير نصاً كما هو';

    assert (select local_date from pulled_txn where seq_no = 60) = '2026-08-31 23:30:00',
        'نص التاريخ كما عند العميل لم يُحفظ';
end $$;
commit;

-- ---------------------------------------------------------------------------
--  ٢) الإعدادات لقطة كاملة: ما حذفه العميل يُحذف، ولا تمس إعدادات الويب
-- ---------------------------------------------------------------------------
insert into public.tenant_settings(tenant_id, key, value)
values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'stones_discount_pct', '30'::jsonb)
on conflict do nothing;

begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
select public.sync_push_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', :'b_token'::uuid,
    '[{"key":"recovery_pct_تلميع","value":"55"}]'::jsonb) \g /dev/null
commit;
do $$
begin
    assert (select value #>> '{}' from public.tenant_settings
             where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and key = 'desktop:recovery_pct_تلميع') = '55',
        'تعديل الإعداد لم يصل';
    assert not exists (select 1 from public.tenant_settings
                        where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
                          and key in ('desktop:col_labels_workers', 'desktop:neg_color_المصنعين')),
        'إعداد حذفه العميل بقي عند المدير';
    assert exists (select 1 from public.tenant_settings
                    where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and key = 'stones_discount_pct'),
        'رفع إعدادات البرنامج حذف إعداداً من الويب';
end $$;

-- ---------------------------------------------------------------------------
--  ٣) تعديل التاريخ من الويب يُسقط نص التاريخ القديم
-- ---------------------------------------------------------------------------
update public.transactions set txn_date = '2026-09-01 08:00+03'
 where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 60;
update public.transactions set note = 'تعديل لا يمس التاريخ'
 where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 1;
do $$
begin
    assert (select local_date from public.transactions
             where tenant_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' and seq_no = 60) is null,
        'تعديل التاريخ من الويب أبقى نص التاريخ القديم فيعرض المدير تاريخاً خاطئاً';
end $$;

-- ---------------------------------------------------------------------------
--  ٤) الحماية: رمز خاطئ يُرفض، ومصنع آخر لا يقرأ إعدادات غيره
-- ---------------------------------------------------------------------------
begin;
set local role anon;
select set_config('request.jwt.claims', '{"role":"anon"}', true) \g /dev/null
do $$
begin
    perform public.sync_push_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', gen_random_uuid(),
                                      '[{"key":"x","value":"1"}]'::jsonb);
    raise exception 'FAIL: رمز مزامنة خاطئ رفع إعدادات';
exception when others then
    if sqlerrm like 'FAIL:%' then raise; end if;
end $$;
do $$
begin
    perform * from public.sync_pull_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null);
    raise exception 'FAIL: سحب الإعدادات بلا رمز';
exception when others then
    if sqlerrm like 'FAIL:%' then raise; end if;
end $$;
rollback;

begin;
set local role authenticated;
select set_config('request.jwt.claims', '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated"}', true) \g /dev/null
do $$
begin
    perform * from public.sync_pull_settings('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', null);
    raise exception 'FAIL: مصنع آخر قرأ إعدادات مصنع ب';
exception when others then
    if sqlerrm like 'FAIL:%' then raise; end if;
end $$;
rollback;

select '✅ المدير يرى ما عند العميل حرفياً — ترتيباً وإعدادات وتاريخاً' as النتيجة;

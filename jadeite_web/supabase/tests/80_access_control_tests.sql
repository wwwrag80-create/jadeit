-- ============================================================================
--  اختبارات 21_access_control.sql — مدة اشتراك المصنع وعدد أجهزته:
--    • الحساب الحالي مفتوح بلا حد وبلا حد أجهزة بعد تشغيل الملف (لا يتغيّر شيء).
--    • حد الأجهزة: الأقدم تسجيلاً مسموح، والزائد يُرفض ولا يُسجَّل، وإزالة جهاز تفتح مكانه،
--      وتخفيض الحد يوقف الأحدث تلقائياً.
--    • المدة: المنتهي يُرفض بسببه وبلا رمز مزامنة، والتجديد يعيده فوراً.
--    • الدخول القديم (≤ 1.67) يرفض المنتهي وذا حد الأجهزة.
--    • الفحص الدوري برمز الحساب نفسه فقط، ويكشف الإيقاف وإزالة الجهاز.
--    • كلمة المرور الخاطئة وحدّ المحاولات كما كانا، والجداول والدوال الداخلية محجوبة عن anon.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- جدول العملاء القديم موجود (أنشأه اختبار 10): الملف يضيف عموديه — ومرتين بلا خطأ
\i supabase/21_access_control.sql
\i supabase/21_access_control.sql

insert into public.tenants(id, business_name) values
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'مصنع ج')
on conflict do nothing;
insert into public.clients (client_id, username, password_hash, business_name, can_edit, is_active)
values ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'factory_c', 'hash-c', 'مصنع ج', true, true)
on conflict do nothing;

-- ---------------------------------------------------------------------------
--  ١) بعد التشغيل: كل الحسابات مفتوحة بلا حد — والجهاز يُسجَّل ليراه المدير
-- ---------------------------------------------------------------------------
do $$
declare r record;
begin
    assert (select count(*) from public.clients where access_until is not null or max_devices is not null) = 0,
        'الحسابات الحالية يجب أن تبقى مفتوحة بلا حد';

    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', 'جهاز المكتب', '1.68.0');
    assert r.out_status = 'ok' and r.out_client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc'
           and r.out_sync_token is not null and r.out_devices_used = 1, 'دخول أول جهاز';
    perform pg_sleep(0.01);
    select * into r from public.client_login_v2('FACTORY_C', 'hash-c', 'pc-B', 'لابتوب', '1.68.0');
    assert r.out_status = 'ok' and r.out_devices_used = 2, 'بلا حد: جهاز ثانٍ يدخل';
    perform pg_sleep(0.01);
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'ok' and r.out_devices_used = 2, 'الجهاز نفسه لا يُسجَّل مرتين';
    assert (select device_name from public.client_devices where device_id = 'pc-A') = 'جهاز المكتب',
        'اسم الجهاز لا يُمحى بدخول بلا اسم';
end $$;

-- ---------------------------------------------------------------------------
--  ٢) حد الأجهزة
-- ---------------------------------------------------------------------------
update public.clients set max_devices = 1 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
do $$
declare r record;
begin
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'ok', 'الحد ١: أقدم جهاز يبقى مسموحاً';

    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-B', null, null);
    assert r.out_status = 'device_limit' and r.out_client_id is null and r.out_sync_token is null
           and r.out_max_devices = 1 and r.out_devices_used = 2,
        'تخفيض الحد يوقف الجهاز الأحدث تلقائياً — بلا معرّف ولا رمز';

    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-NEW', null, null);
    assert r.out_status = 'device_limit', 'جهاز جديد يُرفض والأجهزة مكتملة';
    assert not exists (select 1 from public.client_devices where device_id = 'pc-NEW'),
        'الجهاز المرفوض لا يُسجَّل';

    -- المدير يزيل الجهاز القديم: الأحدث يصبح المسموح
    delete from public.client_devices where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc' and device_id = 'pc-A';
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-B', null, null);
    assert r.out_status = 'ok' and r.out_devices_used = 1, 'إزالة جهاز تفتح مكانه';
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'device_limit', 'الجهاز المُزال لا يعود والمكان مشغول';

    -- رفع الحد إلى ٢: يدخل
    update public.clients set max_devices = 2 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'ok' and r.out_devices_used = 2, 'رفع الحد يسمح بجهاز ثانٍ';

    -- برنامج لا يعرّف جهازه والحساب له حد
    select * into r from public.client_login_v2('factory_c', 'hash-c', null, null, null);
    assert r.out_status = 'update_required', 'بلا معرّف جهاز مع حد أجهزة: يُرفض';
    assert (select count(*) from public.client_login_full('factory_c', 'hash-c')) = 0,
        'الدخول القديم لا يتجاوز حد الأجهزة';

    begin
        update public.clients set max_devices = 0 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
        raise exception 'FAIL: قُبل حد أجهزة صفر';
    exception when check_violation then null;
    end;
end $$;

-- ---------------------------------------------------------------------------
--  ٣) مدة الاشتراك
-- ---------------------------------------------------------------------------
update public.clients set max_devices = null, access_until = now() - interval '1 minute'
 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
do $$
declare r record;
begin
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'expired' and r.out_sync_token is null and r.out_client_id is null
           and r.out_business_name = 'مصنع ج' and r.out_access_until < now(),
        'المنتهي يُرفض بسببه وتاريخه — بلا رمز مزامنة';
    assert (select count(*) from public.client_login_full('factory_c', 'hash-c')) = 0,
        'الدخول القديم يرفض المنتهي';

    -- كلمة مرور صحيحة لحساب منتهٍ لا تُحسب محاولة فاشلة (لا يُقفل الاسم بعد التجديد)
    assert (select count(*) from public.login_attempts
             where username = 'factory_c' and not succeeded) = 0, 'المنتهي ليس محاولة فاشلة';

    update public.clients set access_until = now() + interval '30 days'
     where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'ok' and r.out_sync_token is not null and r.out_access_until > now(), 'التجديد يعيده فوراً';
    assert (select count(*) from public.client_login_full('factory_c', 'hash-c')) = 1,
        'الدخول القديم يعمل للحساب المجدَّد بلا حد أجهزة';

    update public.clients set is_active = false where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', null, null);
    assert r.out_status = 'inactive', 'الحساب الموقوف يُبيَّن سببه';
    update public.clients set is_active = true where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
end $$;

-- ---------------------------------------------------------------------------
--  ٤) الفحص الدوري برمز الحساب
-- ---------------------------------------------------------------------------
select sync_token as c_token from public.tenants where id = 'cccccccc-cccc-cccc-cccc-cccccccccccc' \gset
select sync_token as b_token from public.tenants where id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb' \gset

begin;
select set_config('jadeit.c_token', :'c_token', true) \g /dev/null
select set_config('jadeit.b_token', :'b_token', true) \g /dev/null
set local role anon;
do $$
declare
    c   uuid := 'cccccccc-cccc-cccc-cccc-cccccccccccc';
    tok uuid := current_setting('jadeit.c_token')::uuid;
    r   record;
begin
    select * into r from public.client_access_check(c, tok, 'pc-A');
    assert r.out_status = 'ok' and r.out_can_edit and r.out_access_until > now(), 'الفحص الدوري: يعمل';

    select * into r from public.client_access_check(c, current_setting('jadeit.b_token')::uuid, 'pc-A');
    assert r.out_status = 'unauthorized' and r.out_access_until is null, 'رمز حساب آخر لا يكشف شيئاً';
    select * into r from public.client_access_check(c, null, 'pc-A');
    assert r.out_status = 'unauthorized', 'بلا رمز لا يكشف شيئاً';

    select * into r from public.client_access_check(c, tok, 'pc-UNKNOWN');
    assert r.out_status = 'device_removed', 'جهاز غير مسجّل (أزاله المدير) ← دخول جديد';

    -- الجداول والدوال الداخلية محجوبة عن anon
    begin
        perform * from public.client_devices;
        raise exception 'FAIL: anon قرأ سجل الأجهزة';
    exception when insufficient_privilege then null;
    end;
    begin
        perform * from public.client_access_gate(c, 'x', null, null, true);
        raise exception 'FAIL: anon استدعى البوابة الداخلية';
    exception when insufficient_privilege then null;
    end;
    begin
        perform * from public.client_password_check('factory_c', 'hash-c');
        raise exception 'FAIL: anon استدعى فحص كلمة المرور الداخلي';
    exception when insufficient_privilege then null;
    end;
    begin
        perform * from public.access_status_report();
        raise exception 'FAIL: anon قرأ تقرير الاشتراكات';
    exception when insufficient_privilege then null;
    end;
    -- العميل لا يمدّد اشتراكه بنفسه، ولا يقرأ بصمات كلمات المرور
    begin
        update public.clients set access_until = null, max_devices = null where client_id = c;
        raise exception 'FAIL: anon عدّل مدة اشتراكه بنفسه';
    exception when insufficient_privilege then null;
    end;
    begin
        perform password_hash from public.clients;
        raise exception 'FAIL: anon قرأ بصمات كلمات المرور';
    exception when insufficient_privilege then null;
    end;
    begin
        insert into public.clients (client_id, username, password_hash, business_name)
        values (gen_random_uuid(), 'intruder', 'x', 'x');
        raise exception 'FAIL: anon أنشأ حساباً';
    exception when insufficient_privilege then null;
    end;
end $$;
reset role;
do $$
begin
    assert not exists (select 1 from public.client_devices where device_id = 'pc-UNKNOWN'),
        'الفحص الدوري لا يسجّل أجهزة';
end $$;
rollback;

-- «آخر ظهور» يصل عبر الفحص الدوري
update public.clients set last_seen = now() - interval '1 hour'
 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
begin;
select set_config('jadeit.c_token', :'c_token', true) \g /dev/null
set local role anon;
select * from public.client_access_check('cccccccc-cccc-cccc-cccc-cccccccccccc',
                                         current_setting('jadeit.c_token')::uuid, 'pc-A') \g /dev/null
reset role;
do $$
begin
    assert (select last_seen from public.clients where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc')
           > now() - interval '1 minute', 'الفحص الدوري يسجّل آخر ظهور';
end $$;
rollback;

-- المدير يوقف الحساب أثناء العمل ← الفحص الدوري يكشفه، والتجديد يعيده
update public.clients set access_until = now() - interval '1 second'
 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
begin;
select set_config('jadeit.c_token', :'c_token', true) \g /dev/null
set local role anon;
do $$
declare r record;
begin
    select * into r from public.client_access_check('cccccccc-cccc-cccc-cccc-cccccccccccc',
                                                   current_setting('jadeit.c_token')::uuid, 'pc-A');
    assert r.out_status = 'expired', 'الفحص الدوري يكشف انتهاء المدة';
end $$;
rollback;
update public.clients set access_until = null where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';

-- ---------------------------------------------------------------------------
--  ٥) anon يدخل بالدالة الجديدة، وكلمة المرور الخاطئة وحد المحاولات كما كانا
-- ---------------------------------------------------------------------------
begin;
set local role anon;
do $$
declare r record;
begin
    select * into r from public.client_login_v2('factory_c', 'hash-c', 'pc-A', 'x', '1.68.0');
    assert r.out_status = 'ok', 'anon يدخل بالدالة الجديدة';
    assert (select count(*) from public.client_login_v2('factory_c', 'wrong', 'pc-A')) = 0,
        'كلمة مرور خاطئة: بلا صفوف';
    for i in 1..10 loop
        perform * from public.client_login_v2('factory_c', 'wrong-' || i, 'pc-A');
    end loop;
    assert (select count(*) from public.client_login_v2('factory_c', 'hash-c', 'pc-A')) = 0,
        'حد المحاولات يوقف الاسم حتى بكلمة المرور الصحيحة';
end $$;
rollback;

-- ---------------------------------------------------------------------------
--  ٦) تقرير المدير
-- ---------------------------------------------------------------------------
update public.clients set access_until = now() + interval '10 days', max_devices = 2
 where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc';
do $$
declare r record;
begin
    select * into r from public.access_status_report() where "المستخدم" = 'factory_c';
    assert r."الاشتراك" like '✔ حتى %' and r."الأيام_الباقية" = '10' and r."الأجهزة" = '2 من 2',
        format('تقرير الاشتراكات: %s / %s / %s', r."الاشتراك", r."الأيام_الباقية", r."الأجهزة");
    select * into r from public.access_status_report() where "المستخدم" = 'factory_b';
    assert r."الاشتراك" = '♾️ مفتوح بلا حد' and r."الأجهزة" = '0 من بلا حد', 'الحساب الآخر مفتوح بلا حد';
end $$;

select '✔ اختبارات مدة الاشتراك وحد الأجهزة نجحت' as النتيجة;

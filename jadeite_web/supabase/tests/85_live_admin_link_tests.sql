-- ============================================================================
--  اختبارات 24_live_admin_link.sql — رابط المدير في برنامج المدير وحده:
--    • جهاز المصنع برمز مزامنة حسابه يحفظ عنوانه ويأخذ بصمة مفتاح المدير (لا المفتاح).
--    • الرمز الخاطئ والحساب الموقوف والجهاز المُزال: لا شيء يُحفظ ولا بصمة.
--    • العنوان بصيغة https لاسم مضيف فقط؛ والبصمة ٦٤ حرفاً سداسياً (القاعدة ترفض غيرها).
--    • الأعمدة محجوبة عن المفتاح العام كبقية جدول العملاء، وآمن لإعادة التشغيل.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

\i supabase/24_live_admin_link.sql
\i supabase/24_live_admin_link.sql

insert into public.tenants(id, business_name) values
    ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'مصنع د')
on conflict do nothing;
insert into public.clients (client_id, username, password_hash, business_name, can_edit, is_active)
values ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'factory_d', 'hash-d', 'مصنع د', true, true)
on conflict do nothing;

do $$
declare
    r     record;
    tok   uuid;
    h     text := encode(sha256('admin-only-key'::bytea), 'hex');
    cid   uuid := 'dddddddd-dddd-dddd-dddd-dddddddddddd';
begin
    select * into r from public.client_login_v2('factory_d', 'hash-d', 'pc-D', 'جهاز المصنع', '1.96.0');
    assert r.out_status = 'ok', 'دخول جهاز المصنع';
    tok := r.out_sync_token;

    assert public.client_live_sync(cid, tok, 'pc-D', 'https://factory-pc.tail1a2b3.ts.net') is null,
        'قبل أن يُنشئ المدير المفتاح: لا بصمة';
    assert (select live_url from public.client_devices where client_id = cid and device_id = 'pc-D')
           = 'https://factory-pc.tail1a2b3.ts.net', 'عنوان الجهاز محفوظ ليجده المدير';

    update public.clients set live_key_hash = h where client_id = cid;
    assert public.client_live_sync(cid, tok, 'pc-D', null) = h, 'الجهاز يأخذ البصمة (لا المفتاح)';
    assert (select live_url from public.client_devices where client_id = cid and device_id = 'pc-D')
           = 'https://factory-pc.tail1a2b3.ts.net', 'بلا عنوان: العنوان السابق باقٍ';

    perform public.client_live_sync(cid, tok, 'pc-D', 'https://Live.Example.com');
    assert (select live_url from public.client_devices where client_id = cid and device_id = 'pc-D')
           = 'https://live.example.com', 'عنوان Cloudflare بحروفٍ صغيرة';
    perform public.client_live_sync(cid, tok, 'pc-D', 'http://evil.example.com/?k=x');
    perform public.client_live_sync(cid, tok, 'pc-D', 'https://x.com/path');
    assert (select live_url from public.client_devices where client_id = cid and device_id = 'pc-D')
           = 'https://live.example.com', 'عنوانٌ بغير الصيغة لا يُحفظ';

    assert public.client_live_sync(cid, gen_random_uuid(), 'pc-D', 'https://a.example.com') is null,
        'رمز مزامنة خاطئ: لا شيء';
    assert public.client_live_sync(cid, tok, 'pc-UNKNOWN', 'https://a.example.com') is null,
        'جهازٌ غير مسجّل: لا شيء';
    assert not exists (select 1 from public.client_devices where device_id = 'pc-UNKNOWN'),
        'ولا يُسجَّل جهازٌ جديد من هنا';

    update public.clients set is_active = false where client_id = cid;
    assert public.client_live_sync(cid, tok, 'pc-D', 'https://b.example.com') is null, 'الحساب الموقوف: لا بصمة';
    assert (select live_url from public.client_devices where client_id = cid and device_id = 'pc-D')
           = 'https://live.example.com', 'ولا يُحفظ عنوانه';
    update public.clients set is_active = true where client_id = cid;

    begin
        update public.clients set live_key_hash = 'not-a-hash' where client_id = cid;
        assert false, 'بصمةٌ بغير صيغتها مرفوضة';
    exception when check_violation then
        null;
    end;
end $$;

-- المفتاح العام لا يقرأ البصمة ولا العناوين (الجدولان للمدير وحده)
set role anon;
do $$
begin
    begin
        perform live_key_hash from public.clients limit 1;
        assert false, 'anon لا يقرأ جدول العملاء';
    exception when insufficient_privilege then
        null;
    end;
    begin
        perform live_url from public.client_devices limit 1;
        assert false, 'anon لا يقرأ أجهزة العملاء';
    exception when insufficient_privilege then
        null;
    end;
end $$;
reset role;

select '✔ رابط المدير: الجهاز يأخذ البصمة لا المفتاح ويحفظ عنوانه برمزه — والموقوف والمُزال والخاطئ لا شيء' as النتيجة;

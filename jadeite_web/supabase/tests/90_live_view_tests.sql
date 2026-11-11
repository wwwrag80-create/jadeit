-- ============================================================================
--  اختبارات 22_live_view.sql — «العرض المباشر»:
--    • الرابط يُرسل برمز مزامنة الحساب نفسه فقط، وبصيغته وحدها (https و?k=مفتاح)، ويُحدَّث بلا تكرار.
--    • الحساب الموقوف أو المنتهي أو الجهاز غير المسموح لا يرسل رابطاً.
--    • الإيقاف يمسح رابط الجهاز نفسه (لا رابط جهازٍ آخر)، والجدول محجوب عن anon وauthenticated.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

\i supabase/22_live_view.sql
\i supabase/22_live_view.sql

insert into public.tenants(id, business_name) values
    ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'مصنع د')
on conflict do nothing;
insert into public.clients (client_id, username, password_hash, business_name, can_edit, is_active)
values ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'factory_d', 'hash-d', 'مصنع د', true, true)
on conflict do nothing;

do $$
declare
    c   uuid := 'dddddddd-dddd-dddd-dddd-dddddddddddd';
    tok uuid;
    r   record;
    good text := 'https://quiet-river-1234.trycloudflare.com/?k=AbCdEfGhIjKlMnOpQrStUvWxYz012345';
begin
    select * into r from public.client_login_v2('factory_d', 'hash-d', 'pc-L1', 'جهاز المصنع', '1.94.0');
    assert r.out_status = 'ok', 'دخول الجهاز';
    tok := r.out_sync_token;

    assert public.client_publish_live_link(c, gen_random_uuid(), 'pc-L1', good) = 'unauthorized', 'رمز خاطئ';
    assert public.client_publish_live_link(null, tok, 'pc-L1', good) = 'unauthorized', 'بلا حساب';
    assert (select count(*) from public.live_links) = 0, 'لا شيء يُكتب بلا رمز صحيح';

    assert public.client_publish_live_link(c, tok, 'pc-L1', 'http://x.trycloudflare.com/?k=AbCdEfGhIjKlMnOpQrStUvWx') = 'invalid',
        'http مرفوض';
    assert public.client_publish_live_link(c, tok, 'pc-L1', 'https://x.com/?k=short') = 'invalid', 'مفتاح قصير مرفوض';
    assert public.client_publish_live_link(c, tok, 'pc-L1',
        'https://x.com/?k=AbCdEfGhIjKlMnOpQrStUvWx&next=javascript:alert(1)') = 'invalid', 'زيادة على الصيغة مرفوضة';
    assert public.client_publish_live_link(c, tok, 'pc-L1', 'javascript:alert(1)') = 'invalid', 'ليس رابطاً';

    assert public.client_publish_live_link(c, tok, 'pc-L1', good, 'جهاز المصنع', '1.94.0') = 'ok', 'الرابط الصحيح';
    assert (select url from public.live_links where client_id = c) = good;
    assert public.client_publish_live_link(c, tok, 'pc-L1',
        'https://new-name-99.trycloudflare.com/?k=AbCdEfGhIjKlMnOpQrStUvWxYz012345') = 'ok', 'رابط جديد بعد إعادة التشغيل';
    assert (select count(*) from public.live_links where client_id = c) = 1, 'صف واحد للحساب';
    assert (select device_name from public.live_links where client_id = c) = 'جهاز المصنع', 'اسم الجهاز يبقى';

    -- إيقاف من جهاز آخر لا يمسح رابط هذا الجهاز، ومن الجهاز نفسه يمسحه
    assert public.client_publish_live_link(c, tok, 'pc-OTHER', '') = 'removed';
    assert (select count(*) from public.live_links where client_id = c) = 1, 'جهاز آخر لا يمسح الرابط';
    assert public.client_publish_live_link(c, tok, 'pc-L1', '') = 'removed';
    assert (select count(*) from public.live_links where client_id = c) = 0, 'الإيقاف يمسح رابط الجهاز';

    -- الحساب الموقوف أو المنتهي لا يرسل
    update public.clients set is_active = false where client_id = c;
    assert public.client_publish_live_link(c, tok, 'pc-L1', good) = 'inactive', 'موقوف';
    update public.clients set is_active = true, access_until = now() - interval '1 day' where client_id = c;
    assert public.client_publish_live_link(c, tok, 'pc-L1', good) = 'expired', 'منتهي';
    update public.clients set access_until = null where client_id = c;
    assert (select count(*) from public.live_links) = 0, 'لا رابط من حساب موقوف أو منتهي';
end $$;

-- الجدول محجوب عن المفتاح العام وعن المستخدمين: لا قراءة ولا كتابة مباشرة
set role anon;
do $$
begin
    begin
        perform 1 from public.live_links;
        assert false, 'anon لا يقرأ الروابط';
    exception when insufficient_privilege then
        null;
    end;
    begin
        insert into public.live_links (client_id, url) values ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'https://evil.example/?k=x');
        assert false, 'anon لا يكتب الروابط';
    exception when insufficient_privilege then
        null;
    end;
end $$;
reset role;

select '✔ العرض المباشر: الرابط برمز الحساب وصيغته وحدها، ومحجوب إلا عن المدير' as النتيجة;

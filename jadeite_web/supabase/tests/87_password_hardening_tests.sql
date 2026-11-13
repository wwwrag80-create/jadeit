-- ============================================================================
--  اختبارات 25_password_hardening.sql — كلمات مرور الحسابات bcrypt في السحابة:
--    • البصمات الموجودة (SHA-256) تُحوَّل في مكانها، والجديدة تُحوَّل عند الحفظ؛
--    • الدخول بالبصمة نفسها التي يرسلها البرنامج يعمل كما كان، والخاطئة لا؛
--    • المخزَّن لا يفتح الحساب (لا دخول بالقيمة المخزّنة نفسها)؛
--    • القيمة القديمة غير السداسية (حسابات الاختبار) تبقى بالمقارنة القديمة؛ وآمن لإعادة التشغيل.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- حسابٌ «قديم» ببصمة SHA-256 قبل الحماية (المشغّل موقوف لمحاكاة ما قبل الملف)
insert into public.tenants(id, business_name) values
    ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'مصنع هـ')
on conflict do nothing;
do $$
begin
    if exists (select 1 from pg_trigger where tgname = 'clients_hash_password') then
        execute 'alter table public.clients disable trigger clients_hash_password';
    end if;
end $$;
insert into public.clients (client_id, username, password_hash, business_name, can_edit, is_active)
values ('eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee', 'factory_e', encode(sha256('kalimat-sir'::bytea), 'hex'),
        'مصنع هـ', true, true)
on conflict do nothing;

\i supabase/25_password_hardening.sql
\i supabase/25_password_hardening.sql

do $$
declare
    r      record;
    good   text := encode(sha256('kalimat-sir'::bytea), 'hex');
    stored text;
begin
    select password_hash into stored from public.clients where username = 'factory_e';
    assert stored like '$2_$%', 'البصمة القديمة حُوِّلت إلى bcrypt في مكانها';
    assert stored <> good, 'ولا تبقى البصمة نفسها مخزّنة';

    select * into r from public.client_login_v2('factory_e', good, 'pc-E', 'جهاز هـ', '1.97.0');
    assert r.out_status = 'ok', 'الدخول بما يرسله البرنامج كما كان';
    select * into r from public.client_login_v2('factory_e', encode(sha256('khata'::bytea), 'hex'), 'pc-E', 'جهاز هـ', '1.97.0');
    assert r.out_status is distinct from 'ok', 'كلمة مرور خاطئة: لا دخول';
    select * into r from public.client_login_v2('factory_e', stored, 'pc-E', 'جهاز هـ', '1.97.0');
    assert r.out_status is distinct from 'ok', 'القيمة المخزّنة نفسها لا تفتح الحساب';
    assert exists (select 1 from public.client_login_full('factory_e', good)), 'client_login_full كذلك';

    -- كلمة مرور جديدة يكتبها المدير (بصمة SHA-256) ← bcrypt عند الحفظ
    update public.clients set password_hash = encode(sha256('jadida'::bytea), 'hex') where username = 'factory_e';
    select password_hash into stored from public.clients where username = 'factory_e';
    assert stored like '$2_$%', 'كلمة المرور الجديدة تُحوَّل عند الحفظ';
    assert public.password_matches(stored, encode(sha256('jadida'::bytea), 'hex'))
           and not public.password_matches(stored, good), 'والقديمة لم تعد تفتح';

    -- القيمة غير السداسية (حسابات قديمة جداً/الاختبارات) بالمقارنة القديمة، والفارغ لا يطابق شيئاً
    assert public.password_matches('hash-d', 'hash-d') and not public.password_matches('hash-d', 'x');
    assert not public.password_matches(null, 'x') and not public.password_matches('x', '');
end $$;

-- المفتاح العام لا يستدعي دالة المقارنة ولا دالة التحقق
set role anon;
do $$
begin
    begin
        perform public.password_matches('a', 'a');
        assert false, 'anon لا يستدعي password_matches';
    exception when insufficient_privilege then
        null;
    end;
    begin
        perform * from public.client_password_check('factory_e', 'x');
        assert false, 'anon لا يستدعي client_password_check';
    exception when insufficient_privilege then
        null;
    end;
end $$;
reset role;

select '✔ كلمات المرور bcrypt: الموجود حُوِّل، والدخول كما كان، والمخزَّن لا يفتح الحساب' as النتيجة;

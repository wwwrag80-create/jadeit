-- ============================================================================
--  اختبارات 26_sub_admins.sql — المدراء الفرعيون:
--    • ما يرسله برنامج المدير (SHA-256) يُحفظ bcrypt، والموجود يُحوَّل في مكانه؛
--    • الدخول بالبصمة نفسها صح، والخاطئة والمخزّنة خطأ، والاسم بلا اعتبار لحالة الحروف والمسافات؛
--    • ١٠ محاولات فاشلة توقف الاسم مؤقتاً — حتى بالكلمة الصحيحة؛
--    • الجدول للمدير وحده، والدالة للمفتاح العام؛ وآمن لإعادة التشغيل.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- مديرٌ فرعي «قديم» بالبصمة قبل الملف (المشغّل موقوف لمحاكاة ما قبله)
alter table public.sub_admins disable trigger sub_admins_hash_password;
insert into public.sub_admins (username, password_hash) values ('Helper_One', encode(sha256('help-1'::bytea), 'hex'));
alter table public.sub_admins enable trigger sub_admins_hash_password;

\i supabase/26_sub_admins.sql
\i supabase/26_sub_admins.sql

do $$
declare
    good   text := encode(sha256('help-1'::bytea), 'hex');
    stored text;
    i      integer;
begin
    select password_hash into stored from public.sub_admins where username = 'Helper_One';
    assert stored like '$2_$%', 'الموجود حُوِّل إلى bcrypt في مكانه';
    assert public.verify_sub_admin_login('helper_one', good), 'الدخول بالبصمة نفسها (والاسم بلا اعتبار لحالة الحروف)';
    assert public.verify_sub_admin_login('  HELPER_ONE ', good), 'والمسافات حول الاسم';
    assert not public.verify_sub_admin_login('helper_one', encode(sha256('x'::bytea), 'hex')), 'كلمة خاطئة: لا';
    assert not public.verify_sub_admin_login('helper_one', stored), 'المخزَّن نفسه لا يفتح';
    assert not public.verify_sub_admin_login('nobody', good) and not public.verify_sub_admin_login('', good);

    -- الإنشاء من برنامج المدير (بصمة SHA-256) ← bcrypt
    insert into public.sub_admins (username, password_hash) values ('helper_two', encode(sha256('help-2'::bytea), 'hex'));
    select password_hash into stored from public.sub_admins where username = 'helper_two';
    assert stored like '$2_$%' and public.verify_sub_admin_login('helper_two', encode(sha256('help-2'::bytea), 'hex')),
        'الجديد bcrypt ويدخل';

    -- حدّ المحاولات: ١٠ فاشلة ← الصحيحة لا تفتح مؤقتاً
    for i in 1..10 loop
        perform public.verify_sub_admin_login('helper_two', 'wrong');
    end loop;
    assert not public.verify_sub_admin_login('helper_two', encode(sha256('help-2'::bytea), 'hex')),
        '١٠ محاولات فاشلة توقف الاسم ١٥ دقيقة';
    assert public.verify_sub_admin_login('helper_one', good), 'ولا يتأثر مديرٌ آخر';

    begin
        insert into public.sub_admins (username, password_hash) values ('HELPER_two', 'x');
        assert false, 'الاسم فريد بلا اعتبار لحالة الحروف';
    exception when unique_violation then
        null;
    end;
end $$;

set role anon;
do $$
begin
    assert public.verify_sub_admin_login('helper_one', encode(sha256('help-1'::bytea), 'hex')), 'المفتاح العام يستدعي الدخول';
    begin
        perform 1 from public.sub_admins limit 1;
        assert false, 'anon لا يقرأ جدول المدراء الفرعيين';
    exception when insufficient_privilege then
        null;
    end;
end $$;
reset role;

select '✔ المدراء الفرعيون: bcrypt، والدخول بحدّ محاولات، والجدول للمدير وحده' as النتيجة;

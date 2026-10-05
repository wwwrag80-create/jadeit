-- ============================================================================
--  اختبارات 18_storage_diet.sql — حمية المساحة:
--    • جدول النسخ الكاملة يبقى فيه آخر نسخة لكل عميل فقط (الأحدث بوقت الرفع)،
--      ولا يمسّ عميلاً عنده نسخة واحدة، ولا يفشل بلا الجدول القديم.
--    • الصيانة الشاملة تشمل ذلك، والدوال للمدير وحده (لا للمفتاح العام).
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- بلا جدول النسخ القديم: لا شيء يُحذف ولا خطأ
drop table if exists public.db_backups cascade;
do $$ begin
    assert public.prune_backup_history() = 0, 'بلا جدول النسخ يجب أن يرجع ٠';
end $$;

-- دالة رفع قديمة تحفظ كل رفعة صفاً جديداً (بلا مفتاح أساسي) — يتراكم التاريخ
create table public.db_backups (
    client_id   uuid,
    backup_data text,
    updated_at  timestamptz
);
insert into public.db_backups values
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'A-1', now() - interval '3 hours'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'A-3', now() - interval '1 minute'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'A-2', now() - interval '1 hour'),
    ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'B-1', now() - interval '2 days'),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'C-old', null),
    ('cccccccc-cccc-cccc-cccc-cccccccccccc', 'C-new', now());

do $$
declare v_removed int;
begin
    v_removed := public.prune_backup_history();
    assert v_removed = 3, format('يجب حذف ٣ نسخ قديمة، حُذف %s', v_removed);
    assert (select count(*) from public.db_backups) = 3, 'نسخة واحدة لكل عميل';
    assert (select backup_data from public.db_backups
             where client_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa') = 'A-3', 'تبقى الأحدث للعميل أ';
    assert (select backup_data from public.db_backups
             where client_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') = 'B-1', 'العميل بنسخة واحدة لا يُمس';
    assert (select backup_data from public.db_backups
             where client_id = 'cccccccc-cccc-cccc-cccc-cccccccccccc') = 'C-new', 'الوقت الفارغ يُعدّ الأقدم';
    assert public.prune_backup_history() = 0, 'التشغيل الثاني لا يحذف شيئاً';
end $$;

-- الصيانة الشاملة تشمل النسخ الكاملة
insert into public.db_backups values ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'B-2', now());
do $$
declare v_backups int;
begin
    select removed into v_backups from public.run_maintenance() where task = 'النسخ الكاملة القديمة';
    assert v_backups = 1, format('الصيانة يجب أن تحذف نسخة ب القديمة، حذفت %s', v_backups);
    assert (select backup_data from public.db_backups
             where client_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb') = 'B-2';
end $$;

-- جدول بلا عمود الوقت: الأحدث كتابةً
drop table public.db_backups;
create table public.db_backups (client_id uuid, backup_data text);
insert into public.db_backups values
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'first'),
    ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'last');
do $$ begin
    assert public.prune_backup_history() = 1;
    assert (select backup_data from public.db_backups) = 'last', 'بلا وقت تبقى آخر نسخة كُتبت';
end $$;

-- الصلاحيات: الحذف والصيانة للمدير وحده
do $$ begin
    assert not has_function_privilege('anon', 'public.prune_backup_history()', 'execute'), 'المفتاح العام يحذف النسخ';
    assert not has_function_privilege('authenticated', 'public.prune_backup_history()', 'execute');
    assert has_function_privilege('service_role', 'public.prune_backup_history()', 'execute');
    assert not has_function_privilege('anon', 'public.run_maintenance()', 'execute');
end $$;

drop table public.db_backups;
\echo '   ✔ حمية المساحة: آخر نسخة كاملة لكل عميل فقط، والصيانة تشملها، والدوال للمدير وحده'

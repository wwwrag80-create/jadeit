-- ============================================================================
--  اختبارات 19_remove_web.sql — إزالة الويب وحركاته (آخر الاختبارات: يمسح جداول الويب):
--    • حركات الويب وسجل تدقيقها وما يتبعها تُحذف كلها.
--    • الإدراج بعدها (نسخة عميل قديمة ما زالت ترفع) يُتجاهل بلا خطأ ولا صف يُخزَّن.
--    • لا يُمسّ: النسخ الكاملة التي يقرؤها المدير، والعملاء ورموز مزامنتهم.
--    • آمن لإعادة التشغيل.
-- ============================================================================
\set ON_ERROR_STOP 1
set client_min_messages = warning;

-- نسخة كاملة لعميل (يقرؤها برنامج المدير) — يجب أن تبقى
create table if not exists public.db_backups (client_id uuid primary key, backup_data text, updated_at timestamptz);
insert into public.db_backups values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'FULL-COPY', now())
    on conflict (client_id) do update set backup_data = excluded.backup_data;

-- حركات ويب موجودة قبل الإزالة (مع سجل تدقيقها من المحفّز)
insert into public.transactions (tenant_id, seq_no, txn_date, account_name, op_type, weight)
values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 900001, now(), 'عامل', 'صرف ذهب', 10),
       ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 900002, now(), 'عامل', 'قبض ذهب', 9);

select set_config('jadeite.tenants_before', count(*)::text, false) from public.tenants \g /dev/null
do $$ begin
    assert (select count(*) from public.transactions) >= 2, 'لا حركات قبل الإزالة';
end $$;

\i supabase/19_remove_web.sql
\i supabase/19_remove_web.sql

do $$
begin
    assert (select count(*) from public.transactions) = 0, 'الحركات لم تُحذف';
    assert (select count(*) from public.audit_log) = 0, 'سجل التدقيق لم يُحذف';
    assert (select count(*) from public.accounts) = 0, 'دليل الحسابات لم يُحذف';
    assert (select backup_data from public.db_backups
             where client_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa') = 'FULL-COPY', 'النسخة الكاملة مُسّت!';
end $$;

do $$ begin
    assert (select count(*) from public.tenants) = current_setting('jadeite.tenants_before')::int, 'العملاء مُسّوا!';
end $$;

-- نسخة عميل قديمة ما زالت ترفع: يُتجاهل بلا خطأ
insert into public.transactions (tenant_id, seq_no, txn_date, account_name, op_type, weight)
values ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 900003, now(), 'عامل', 'صرف ذهب', 1);
do $$ begin
    assert (select count(*) from public.transactions) = 0, 'إدراج بعد الإزالة خُزّن';
    assert (select count(*) from public.audit_log) = 0, 'سجل التدقيق كُتب بعد الإزالة';
end $$;

drop table public.db_backups;
\echo '   ✔ إزالة الويب: حُذفت حركاته وتوابعها، والرفع القديم يُتجاهل، والنسخ الكاملة والعملاء كما هم'

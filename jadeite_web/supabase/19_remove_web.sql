-- ============================================================================
--  جاديت ERP — إزالة الويب وحركاته من السحابة (الدفعة ٢١)
--
--  لماذا: برنامج المدير يعرض كل بيانات العميل من نسخته الكاملة (db_backups)،
--  والويب غير مستخدم. أما «حركات الويب» — رفع كل حركة صفاً صفاً إلى جدول
--  transactions مع سجل تدقيقها — فكانت أكبر ما يملأ المساحة المجانية
--  (نحو ١٢–١٥ ميجا لكل ٢٠٬٠٠٠ حركة، مقابل ٠٫٤ ميجا للنسخة الكاملة نفسها).
--
--  ما يفعله هذا الملف:
--    ١) يحذف حركات الويب وكل ما يتبعها: الحركات، سجل التدقيق، سجل الحذف،
--       دليل الحسابات، إقفالات الصناديق، إعدادات الويب، وأجهزة المزامنة.
--       بـ TRUNCATE: تعود المساحة فوراً.
--    ٢) يمنع امتلاءها من جديد: أي إدراج فيها (من نسخة عميل قديمة لم تُحدَّث بعد)
--       يُتجاهل بهدوء — فلا خطأ عند العميل ولا صف يُخزَّن.
--
--  لا يمسّ: النسخ الكاملة (db_backups) التي يقرؤها برنامج المدير، ولا العملاء
--  وحساباتهم ورموز مزامنتهم (tenants / clients)، ولا دخول العملاء.
--
--  ⚠️ الحذف نهائي — لكنه لا يُفقد شيئاً: كل حركة موجودة على جهاز العميل وفي نسخته
--  الكاملة على السحابة. شغّله بعد 18_storage_diet.sql.
--  لا يدخل في INSTALL_ALL.sql: يُشغَّل وحده مرة واحدة على مشروعك.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) منع الامتلاء من جديد: الإدراج في جداول الويب يُتجاهل
-- ----------------------------------------------------------------------------
create or replace function public.ignore_web_writes()
returns trigger
language plpgsql as $$
begin
    return null;        -- لا يُخزَّن الصف، ولا يظهر خطأ لنسخة عميل قديمة ما زالت ترفع
end $$;

do $$
declare
    t text;
begin
    foreach t in array array['transactions', 'accounts', 'audit_log', 'sync_deletions', 'box_closings',
                             'tenant_settings', 'tenant_devices']
    loop
        if to_regclass('public.' || t) is not null then
            execute format('drop trigger if exists trg_web_removed on public.%I', t);
            execute format('create trigger trg_web_removed before insert on public.%I '
                           'for each row execute function public.ignore_web_writes()', t);
        end if;
    end loop;

    -- سجل تدقيق الحركات لم يعد له ما يسجّله
    if to_regclass('public.transactions') is not null then
        drop trigger if exists trg_txn_audit on public.transactions;
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) حذف حركات الويب (TRUNCATE يعيد المساحة فوراً)
-- ----------------------------------------------------------------------------
do $$
declare
    v_tables text;
begin
    select string_agg(format('public.%I', t), ', ')
      into v_tables
      from unnest(array['audit_log', 'sync_deletions', 'transactions', 'accounts', 'box_closings',
                        'tenant_settings', 'tenant_devices']) as t
     where to_regclass('public.' || t) is not null;

    if v_tables is null then
        return;
    end if;

    begin
        execute 'truncate table ' || v_tables || ' restart identity';
    exception when others then
        -- جدول آخر يشير إليها بمفتاح أجنبي: حذف صفاً صفاً بدل TRUNCATE
        raise notice 'TRUNCATE تعذّر (%): حذف بالأمر delete', sqlerrm;
        execute 'delete from public.audit_log';
        if to_regclass('public.sync_deletions') is not null then execute 'delete from public.sync_deletions'; end if;
        execute 'delete from public.transactions';
        if to_regclass('public.box_closings') is not null then execute 'delete from public.box_closings'; end if;
        if to_regclass('public.accounts') is not null then execute 'delete from public.accounts'; end if;
        if to_regclass('public.tenant_settings') is not null then execute 'delete from public.tenant_settings'; end if;
        if to_regclass('public.tenant_devices') is not null then execute 'delete from public.tenant_devices'; end if;
    end;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  التقرير: حجم القاعدة بعد الإزالة، وأكبر الجداول
-- ----------------------------------------------------------------------------
select pg_size_pretty(pg_database_size(current_database()))                          as حجم_القاعدة_كلها,
       round(100.0 * pg_database_size(current_database()) / (500 * 1024 * 1024), 1)  as النسبة_من_500_ميجا;

select c.relname                                    as الجدول,
       pg_size_pretty(pg_total_relation_size(c.oid)) as الحجم,
       coalesce(s.n_live_tup, 0)                     as الصفوف
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_stat_user_tables s on s.relid = c.oid
 where n.nspname = 'public' and c.relkind = 'r'
 order by pg_total_relation_size(c.oid) desc
 limit 10;

-- ----------------------------------------------------------------------------
--  للتراجع (إن أردت الويب مستقبلاً): احذف المحفّزات trg_web_removed من الجداول أعلاه
--  وأعد تشغيل 10_maintenance.sql (يعيد محفّز سجل التدقيق).
-- ----------------------------------------------------------------------------

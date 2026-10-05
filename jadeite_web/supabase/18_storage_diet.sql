-- ============================================================================
--  جاديت ERP — حمية المساحة السحابية (الدفعة ٢٠)
--
--  الهدف: أن تبقى قاعدة Supabase المجانية خفيفة، دون أن يتغيّر شيء مما يراه
--  برنامج المدير (النسخة الكاملة لكل عميل تبقى كما هي — آخر نسخة كاملة دائماً).
--
--  ما يفعله هذا الملف:
--    ١) prune_backup_history(): يُبقي في db_backups آخر نسخة كاملة لكل عميل فقط
--       (إن كانت دالة الرفع القديمة تحفظ كل رفعة صفاً جديداً تتراكم النسخ بلا فائدة:
--        المدير يقرأ الأحدث دائماً، والعميل لا يسترجع من السحابة أبداً).
--    ٢) run_maintenance(): الصيانة الشاملة صارت تشمل ذلك أيضاً.
--    ٣) جدولة الصيانة أسبوعياً تلقائياً (pg_cron) بدل تشغيلها يدوياً:
--       كل جمعة ٣ فجراً — تنظيف + VACUUM يعيد المساحة المحرّرة للاستعمال.
--    ٤) تقرير المساحة في آخر الملف: حجم القاعدة وكل جدول.
--
--  ومع برنامج العميل ١٫٥٥ (لا يحتاج هذا الملف ليعمل): النسخة الكاملة تُرفع بلا فهارس
--  ومضغوطة بـ xz (أخف ~٦٠–٨٠٪)، ولا تُرفع إلا إن تغيّرت البيانات فعلاً.
--
--  آمن لإعادة التشغيل، ولا يفشل في تثبيت جديد بلا جدول النسخ القديم ولا بلا pg_cron.
--  شغّله بعد 17_backup_security.sql.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) آخر نسخة كاملة لكل عميل فقط
-- ----------------------------------------------------------------------------
create or replace function public.prune_backup_history()
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count   integer := 0;
    v_order   text;
begin
    if to_regclass('public.db_backups') is null or not exists (
            select 1 from information_schema.columns
             where table_schema = 'public' and table_name = 'db_backups' and column_name = 'client_id') then
        return 0;
    end if;

    -- الأحدث بوقت الرفع إن وُجد العمود، وإلا بآخر ما كُتب في الجدول
    v_order := case when exists (select 1 from information_schema.columns
                                  where table_schema = 'public' and table_name = 'db_backups'
                                    and column_name = 'updated_at')
                    then 'updated_at desc nulls last, ctid desc'
                    else 'ctid desc' end;

    execute format(
        'with ranked as (
             select ctid as row_ref, row_number() over (partition by client_id order by %s) as rn
               from public.db_backups)
         delete from public.db_backups b
          using ranked r
          where b.ctid = r.row_ref and r.rn > 1', v_order);
    get diagnostics v_count = row_count;
    return v_count;
end $$;

revoke execute on function public.prune_backup_history() from public, anon, authenticated;
grant  execute on function public.prune_backup_history() to service_role;

-- ----------------------------------------------------------------------------
--  ٢) الصيانة الشاملة (تحلّ محل نسخة 10_maintenance.sql وتزيد عليها النسخ الكاملة)
--     الحذف يحرّر المساحة للاستعمال من جديد بعد VACUUM (الجدولة أدناه تشغّله)،
--     فلا يكبر حجم القاعدة مرة أخرى بما حُذف.
-- ----------------------------------------------------------------------------
create or replace function public.run_maintenance()
returns table (task text, removed integer)
language plpgsql security definer set search_path = public as $$
begin
    return query select 'سجل التدقيق'::text, public.purge_audit_log(180);
    return query select 'سجل الحذف'::text,  public.purge_sync_deletions();
    return query select 'النسخ الكاملة القديمة'::text, public.prune_backup_history();

    -- محاولات الدخول (تُنشأ في 11_fix_sync_permissions.sql) — أقدم من ٣٠ يوماً
    if to_regclass('public.login_attempts') is not null then
        return query execute
            'with d as (delete from public.login_attempts
                         where attempted_at < now() - interval ''30 days'' returning 1)
             select ''محاولات الدخول''::text, count(*)::int from d';
    end if;

    analyze public.audit_log;
    analyze public.sync_deletions;
    analyze public.transactions;
end $$;

revoke execute on function public.run_maintenance() from public, anon, authenticated;
grant  execute on function public.run_maintenance() to service_role;

-- ----------------------------------------------------------------------------
--  ٣) جدولة أسبوعية تلقائية (pg_cron متاح في Supabase المجاني)
--     إن لم يكن مفعّلاً: Database → Extensions → pg_cron → Enable، ثم أعد تشغيل الملف
--     (أو شغّل select * from public.run_maintenance(); يدوياً مرة في الشهر).
-- ----------------------------------------------------------------------------
do $$
declare
    v_tables text := 'public.audit_log, public.transactions, public.sync_deletions';
begin
    if not exists (select 1 from pg_extension where extname = 'pg_cron') then
        begin
            create extension if not exists pg_cron;
        exception when others then
            raise notice 'pg_cron غير متاح هنا (%): فعّله من Database → Extensions ثم أعد تشغيل هذا الملف', sqlerrm;
            return;
        end;
    end if;

    if to_regclass('public.db_backups') is not null then
        v_tables := 'public.db_backups, ' || v_tables;
    end if;

    -- بالاسم: إعادة تشغيل الملف تحدّث الجدولة نفسها ولا تكرّرها
    perform cron.schedule('jadeite-weekly-maintenance', '0 3 * * 5', 'select public.run_maintenance()');
    perform cron.schedule('jadeite-weekly-vacuum', '30 3 * * 5', 'vacuum (analyze) ' || v_tables);
exception when others then
    raise notice 'تعذّرت جدولة الصيانة التلقائية (%): شغّل select * from public.run_maintenance(); يدوياً', sqlerrm;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تنظيف فوري الآن + تقرير المساحة
-- ----------------------------------------------------------------------------
select * from public.run_maintenance();

select pg_size_pretty(pg_database_size(current_database()))                          as حجم_القاعدة_كلها,
       round(100.0 * pg_database_size(current_database()) / (500 * 1024 * 1024), 1)  as النسبة_من_500_ميجا;

select c.relname                                    as الجدول,
       pg_size_pretty(pg_total_relation_size(c.oid)) as الحجم_مع_الفهارس,
       coalesce(s.n_live_tup, 0)                     as الصفوف,
       coalesce(s.n_dead_tup, 0)                     as صفوف_ميتة_تنتظر_التنظيف
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_stat_user_tables s on s.relid = c.oid
 where n.nspname = 'public' and c.relkind = 'r'
 order by pg_total_relation_size(c.oid) desc
 limit 12;

-- ----------------------------------------------------------------------------
--  مرة واحدة بعد تحديث العملاء إلى ١٫٥٥ (اختياري — يعيد المساحة المحجوزة فوراً):
--  النسخ الجديدة أصغر بكثير، لكن الجدول يبقى محجوزاً بحجمه القديم حتى يُضغط.
--  شغّل هذا السطر **وحده** في استعلام جديد (لا يعمل داخل ملف فيه أوامر أخرى):
--
--      vacuum full public.db_backups;
--
--  يقفل جدول النسخ ثوانيَ معدودة فقط (لا يمس الحركات ولا يوقف البرامج).
-- ----------------------------------------------------------------------------

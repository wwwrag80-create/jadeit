-- ============================================================================
--  جاديت ERP — تحصين الصلاحيات (يُشغَّل آخر شيء، ضمن INSTALL_ALL.sql)
--
--  المشكلة التي يحلّها:
--    PostgreSQL يمنح تنفيذ أي دالة جديدة لـ PUBLIC تلقائياً، وSupabase يمنحها
--    أيضاً لـ anon صراحةً. ومفتاح anon علني بطبيعته (داخل تطبيق الويب وبرنامج
--    العميل). النتيجة قبل هذا الملف: أي شخص على الإنترنت كان يستطيع استدعاء
--    دوال الحسابات والبحث مباشرةً بمفتاح anon، ودوال SECURITY DEFINER تتخطى RLS.
--
--  القاعدة بعد هذا الملف:
--    • anon لا يستدعي إلا دوال المزامنة ودخول العميل (وكلها تتحقق من رمز سرّي).
--    • كل دوال الويب للمستخدمين المسجّلين فقط، وكل واحدة منها تتحقق داخلياً
--      من has_tenant_access — فالعميل لا يصل لمصنع غيره حتى لو عرف معرّفه.
--
--  آمن لإعادة التشغيل، ولا يمس أي دالة قديمة خارج نظام جاديت (مثل
--  verify_client_login أو upload_backup) — تلك تظهر في تقرير المراجعة أدناه.
-- ============================================================================

do $$
declare
    -- دوال تطبيق الويب والدوال الداخلية: لا يستدعيها anon إطلاقاً
    v_web_only text[] := array[
        'current_tenant_id', 'current_role_name', 'is_admin', 'is_service_role',
        'has_tenant_access', 'can_edit_tenant',
        'inbound_types', 'sale_types', 'khayas_boxes',
        'next_seq_no', 'post_transaction', 'post_transactions_batch',
        'treasury_balance', 'box_period_totals', 'worker_ledger', 'sales_invoices',
        'workshop_losses', 'account_opening_balance', 'touch_activity',
        'admin_tenants_overview', 'seed_tenant_defaults', 'admin_create_tenant',
        'post_journal_entry', 'delete_journal_entry', 'journal_entries',
        'close_khayas_box', 'reopen_khayas_box', 'boxes_closing_status',
        'losses_breakdown', 'invoice_archive', 'search_transactions',
        'admin_sync_overview', 'admin_rotate_sync_token', 'my_session',
        'storage_report', 'storage_summary',
        'box_mustarja_names', 'tenant_khayas_boxes', 'section_actual_khayas',
        'treasury_period_ledger',
        -- الصيانة والتشخيص والربط: للمدير عبر SQL Editor أو مفتاح الخدمة فقط
        'purge_audit_log', 'run_maintenance', 'purge_sync_deletions',
        'ensure_tenant_link', 'diagnose_client_sync', 'assert_sync_token',
        -- دوال المحفّزات (لا تحتاج صلاحية تنفيذ أصلاً)
        'touch_updated_at', 'fill_txn_period', 'log_txn_audit', 'write_audit',
        'guard_tenant_self_update', 'log_txn_deletion', 'mark_web_source'
    ];
    r record;
begin
    for r in
        select p.oid::regprocedure as sig
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace
         where n.nspname = 'public'
           and p.proname = any(v_web_only)
    loop
        execute format('revoke execute on function %s from public, anon', r.sig);
    end loop;
end $$;

-- دوال لا يستدعيها إلا المدير عبر SQL Editor أو مفتاح الخدمة — تُسحب من
-- authenticated أيضاً (سحبها من PUBLIC أعلاه لا يكفي لأن Supabase يمنحها صراحةً)
revoke execute on function public.purge_audit_log(int)      from authenticated;
revoke execute on function public.run_maintenance()         from authenticated;
revoke execute on function public.purge_sync_deletions()    from authenticated;
revoke execute on function public.ensure_tenant_link(uuid)  from authenticated;
revoke execute on function public.diagnose_client_sync(text) from authenticated;
revoke execute on function public.assert_sync_token(uuid, uuid) from authenticated;

-- الجداول: لا وصول مباشر لـ anon لأي جدول من جداول النظام
revoke all on public.transactions    from anon;
revoke all on public.accounts        from anon;
revoke all on public.tenants         from anon;
revoke all on public.app_users       from anon;
revoke all on public.tenant_settings from anon;
revoke all on public.box_closings    from anon;
revoke all on public.audit_log       from anon;
revoke all on public.tenant_devices  from anon;
revoke all on public.sync_deletions  from anon;
revoke all on public.login_attempts  from anon, authenticated;

-- سجل التدقيق يكتبه المحفّز فقط — المستخدم يقرأ سجلّ مصنعه (RLS) ولا يعدّله
revoke insert, update, delete on public.audit_log from authenticated;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تقرير المراجعة: كل دالة ما زال anon يستطيع تنفيذها
--
--  المتوقع: دوال المزامنة (sync_*) و client_login_full فقط، وهي محمية برمز.
--  أي دالة أخرى تظهر هنا (غالباً من النظام القديم: verify_client_login،
--  check_client_can_edit، upload_backup، download_backup، verify_sub_admin_login)
--  راجِع تعريفها: هل تتحقق من كلمة مرور أو رمز قبل أن تُرجع بيانات عميل؟
-- ----------------------------------------------------------------------------
select p.proname                                  as الدالة,
       pg_get_function_identity_arguments(p.oid)  as المعاملات,
       case when p.prosecdef then 'SECURITY DEFINER' else 'INVOKER' end as النوع,
       case when p.proname like 'sync\_%' or p.proname = 'client_login_full'
            then '✔ متوقعة (محمية برمز المزامنة/كلمة المرور)'
            else '⚠️ راجعها — متاحة لأي زائر بمفتاح anon'
       end                                        as الحالة
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
 where n.nspname = 'public'
   and has_function_privilege('anon', p.oid, 'execute')
   -- دوال الإضافات (pgcrypto وغيرها) ليست من النظام — تُستبعد من التقرير
   and not exists (select 1 from pg_depend d
                    where d.classid = 'pg_proc'::regclass and d.objid = p.oid and d.deptype = 'e')
 order by 4 desc, 1;

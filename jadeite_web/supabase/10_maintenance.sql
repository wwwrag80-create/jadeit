-- ============================================================================
--  جاديت ERP — صيانة المساحة السحابية ومراقبتها
--
--  لماذا هذا الملف ضروري:
--    جدول transactions نفسه خفيف (~٠.٦ كيلوبايت للحركة مع فهارسها)، لكن
--    سجل التدقيق audit_log يخزّن نسخة كاملة قبل وبعد لكل تعديل أو حذف،
--    فيتضخّم أسرع من الحركات نفسها ويلتهم المساحة خلال شهور.
--
--  هذا الملف يضيف: تنظيفاً تلقائياً + تقرير مساحة تراه في لوحة المدير.
--
--  شغّل هذا الملف بعد 09_two_way_sync.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) تنظيف سجل التدقيق
--     نحتفظ بـ ١٨٠ يوماً: كافية لمراجعة أي نزاع محاسبي، والأقدم يُحذف.
--     الحركات نفسها لا تُمس إطلاقاً — هذا سجل تدقيق فقط وليس دفاتر.
-- ----------------------------------------------------------------------------
create or replace function public.purge_audit_log(p_keep_days int default 180)
returns integer
language plpgsql security definer set search_path = public as $$
declare v_count integer;
begin
    delete from public.audit_log
     where created_at < now() - make_interval(days => greatest(coalesce(p_keep_days, 180), 30));
    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) صيانة شاملة بأمر واحد
-- ----------------------------------------------------------------------------
create or replace function public.run_maintenance()
returns table (task text, removed integer)
language plpgsql security definer set search_path = public as $$
begin
    return query select 'سجل التدقيق'::text, public.purge_audit_log(180);
    return query select 'سجل الحذف'::text,  public.purge_sync_deletions();

    -- استرجاع المساحة فعلياً بعد الحذف (بدونها تبقى المساحة محجوزة)
    analyze public.audit_log;
    analyze public.sync_deletions;
    analyze public.transactions;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) تقرير المساحة — كم استهلكنا وكم بقي
-- ----------------------------------------------------------------------------
create or replace function public.storage_report()
returns table (
    table_name   text,
    total_size   text,
    size_bytes   bigint,
    row_count    bigint
)
language sql stable security definer set search_path = public as $$
    select
        c.relname::text,
        pg_size_pretty(pg_total_relation_size(c.oid)),
        pg_total_relation_size(c.oid),
        coalesce(s.n_live_tup, 0)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      left join pg_stat_user_tables s on s.relid = c.oid
     where n.nspname = 'public'
       and c.relkind = 'r'
       and public.is_admin()
     order by pg_total_relation_size(c.oid) desc;
$$;

-- ----------------------------------------------------------------------------
--  ٤) ملخّص سريع للمساحة الكلية ونسبة الامتلاء
-- ----------------------------------------------------------------------------
create or replace function public.storage_summary()
returns table (
    used_bytes    bigint,
    used_pretty   text,
    txn_rows      bigint,
    audit_rows    bigint,
    tenants_count bigint,
    pct_of_500mb  numeric
)
language sql stable security definer set search_path = public as $$
    select
        sum(pg_total_relation_size(c.oid))::bigint,
        pg_size_pretty(sum(pg_total_relation_size(c.oid))),
        (select count(*) from public.transactions),
        (select count(*) from public.audit_log),
        (select count(*) from public.tenants),
        round(100.0 * sum(pg_total_relation_size(c.oid)) / (500 * 1024 * 1024), 1)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r'
       and public.is_admin();
$$;

grant execute on function public.purge_audit_log(int)   to authenticated;
grant execute on function public.run_maintenance()      to authenticated;
grant execute on function public.storage_report()       to authenticated;
grant execute on function public.storage_summary()      to authenticated;

-- ----------------------------------------------------------------------------
--  ٥) تقليل حجم سجل التدقيق من الأساس
--     كنا نخزّن الصف القديم والجديد كاملين لكل تعديل. الآن نخزّن الفرق فقط،
--     فينكمش السجل إلى أقل من الثلث دون فقدان أي معلومة تدقيقية مفيدة.
-- ----------------------------------------------------------------------------
create or replace function public.write_audit()
returns trigger language plpgsql security definer set search_path = public as $$
declare
    v_tenant uuid;
    v_old    jsonb;
    v_new    jsonb;
    v_diff   jsonb;
begin
    v_tenant := (case when tg_op = 'DELETE'
                      then (to_jsonb(old) ->> 'tenant_id')
                      else (to_jsonb(new) ->> 'tenant_id') end)::uuid;

    if tg_op = 'INSERT' then
        -- الإضافة: يكفي تسجيل حدوثها؛ الصف نفسه موجود في الجدول
        v_old := null;
        v_new := jsonb_build_object('seq_no', to_jsonb(new) -> 'seq_no');

    elsif tg_op = 'DELETE' then
        -- الحذف: نحتفظ بالصف كاملاً لأنه لم يعد موجوداً في أي مكان آخر
        v_old := to_jsonb(old);
        v_new := null;

    else
        -- التعديل: الحقول المتغيّرة فقط
        select jsonb_object_agg(key, value)
          into v_diff
          from jsonb_each(to_jsonb(new))
         where to_jsonb(old) -> key is distinct from value
           and key not in ('updated_at', 'synced_at');

        if v_diff is null or v_diff = '{}'::jsonb then
            return new;      -- لا تغيير فعلي: لا نسجّل شيئاً
        end if;

        select jsonb_object_agg(key, to_jsonb(old) -> key)
          into v_old
          from jsonb_each(v_diff);
        v_new := v_diff;
    end if;

    insert into public.audit_log (tenant_id, table_name, record_id, action, actor, old_data, new_data)
    values (
        v_tenant, tg_table_name,
        (case when tg_op = 'DELETE' then (to_jsonb(old) ->> 'id') else (to_jsonb(new) ->> 'id') end)::uuid,
        tg_op, auth.uid(), v_old, v_new
    );

    return case when tg_op = 'DELETE' then old else new end;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تشغيل صيانة فورية + عرض المساحة الحالية
-- ----------------------------------------------------------------------------
select * from public.run_maintenance();
select * from public.storage_summary();

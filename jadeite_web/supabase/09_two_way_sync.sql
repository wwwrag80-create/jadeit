-- ============================================================================
--  جاديت ERP — المزامنة ثنائية الاتجاه (تعديلات المدير من الويب تصل للعميل)
--
--  المشكلة التي يحلّها هذا الملف:
--    كانت المزامنة باتجاه واحد (من جهاز العميل إلى السحابة). فلو عدّل المدير
--    حركة من لوحة الويب، لن يراها العميل في برنامجه لأن جهازه لا يسأل السحابة
--    عن الجديد إطلاقاً — وأسوأ من ذلك، أول رفع من جهازه كان سيعيد كتابة
--    القيمة القديمة فوق تعديل المدير.
--
--  الحل: سجلّ تغييرات + دالة سحب تفاضلية، والعميل يسأل السحابة كل ١٥ ثانية:
--    «ما الذي تغيّر منذ آخر مرة؟» فيطبّقه محلياً.
--
--  شغّل هذا الملف بعد 08_client_login.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) سجلّ الحذف
--     الحركة المحذوفة تختفي من الجدول، فلا وسيلة للعميل ليعرف أنها حُذفت.
--     نسجّل رقمها هنا ليطبّق الحذف على نسخته المحلية.
-- ----------------------------------------------------------------------------
create table if not exists public.sync_deletions (
    id         bigserial primary key,
    tenant_id  uuid not null references public.tenants(id) on delete cascade,
    seq_no     bigint not null,
    deleted_at timestamptz not null default now(),
    deleted_by uuid
);

create index if not exists idx_sync_del_tenant
    on public.sync_deletions(tenant_id, deleted_at);

alter table public.sync_deletions enable row level security;

drop policy if exists sync_del_select on public.sync_deletions;
create policy sync_del_select on public.sync_deletions for select to authenticated
    using (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  ٢) محفّز يسجّل كل حذف تلقائياً — أياً كان مصدره (ويب أو جهاز عميل آخر)
-- ----------------------------------------------------------------------------
create or replace function public.log_txn_deletion()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.sync_deletions (tenant_id, seq_no, deleted_by)
    values (old.tenant_id, old.seq_no, auth.uid());
    return old;
end $$;

drop trigger if exists trg_txn_log_delete on public.transactions;
create trigger trg_txn_log_delete
    after delete on public.transactions
    for each row execute function public.log_txn_deletion();

-- ----------------------------------------------------------------------------
--  ٣) تنظيف السجلّ القديم (بعد ٩٠ يوماً)
--     أي جهاز غاب أكثر من ٩٠ يوماً يجب أن يُعيد السحب الكامل بدل الاعتماد
--     على سجل ناقص — وهذا ما تفرضه الدالة أدناه بإرجاع علم full_resync.
-- ----------------------------------------------------------------------------
create or replace function public.purge_sync_deletions()
returns integer language plpgsql security definer set search_path = public as $$
declare v_count integer;
begin
    delete from public.sync_deletions where deleted_at < now() - interval '90 days';
    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) السحب التفاضلي: ما الذي تغيّر منذ لحظة معيّنة؟
--
--  يرجع الحركات المعدّلة/المضافة والمحذوفة معاً في استجابة واحدة،
--  مع الطابع الزمني للخادم ليستخدمه العميل في الطلب التالي
--  (نعتمد وقت الخادم لا وقت الجهاز، لأن ساعة جهاز العميل قد تكون خاطئة
--   فيفوّت تغييرات أو يعيد سحب كل شيء بلا داعٍ).
-- ----------------------------------------------------------------------------
create or replace function public.sync_pull_changes(
    p_tenant uuid,
    p_since  timestamptz default null,
    p_limit  int default 500
)
returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
    v_now         timestamptz := now();
    v_full        boolean := false;
    v_changed     jsonb;
    v_deleted     jsonb;
    v_more        boolean := false;
    v_count       int;
begin
    perform public.assert_sync_token(p_tenant, null);

    -- غياب طويل أو أول تشغيل: نطلب سحباً كاملاً بدل سجل ناقص
    if p_since is null or p_since < now() - interval '85 days' then
        v_full := true;
    end if;

    select coalesce(jsonb_agg(row_to_json(x)), '[]'::jsonb), count(*)
      into v_changed, v_count
      from (
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text as status, t.trees_count,
               t.set_number, t.row_number, t.manual_no,
               t.source, t.updated_at
          from public.transactions t
         where t.tenant_id = p_tenant
           and (v_full or t.updated_at > p_since)
         order by t.updated_at
         limit least(coalesce(p_limit, 500), 2000)
      ) x;

    v_more := (v_count >= least(coalesce(p_limit, 500), 2000));

    if v_full then
        v_deleted := '[]'::jsonb;
    else
        select coalesce(jsonb_agg(d.seq_no), '[]'::jsonb)
          into v_deleted
          from public.sync_deletions d
         where d.tenant_id = p_tenant
           and d.deleted_at > p_since;
    end if;

    return jsonb_build_object(
        'server_time', v_now,
        'full_resync', v_full,
        'has_more',    v_more,
        'changed',     v_changed,
        'deleted',     v_deleted
    );
end $$;

grant execute on function public.sync_pull_changes(uuid, timestamptz, int) to anon, authenticated;
grant execute on function public.purge_sync_deletions() to authenticated;

-- ----------------------------------------------------------------------------
--  ٥) وسم مصدر التعديل
--     كل كتابة من لوحة الويب تُوسم بـ 'web' لتمييزها عن حركات جهاز العميل،
--     فيظهر للطرفين من أين جاء التعديل عند المراجعة.
-- ----------------------------------------------------------------------------
create or replace function public.mark_web_source()
returns trigger language plpgsql as $$
begin
    -- الكتابة القادمة من مستخدم مسجّل الدخول عبر الويب فقط (لا من دوال المزامنة)
    if auth.uid() is not null and coalesce(new.device_id, '') = '' then
        new.source := 'web';
    end if;
    return new;
end $$;

drop trigger if exists trg_txn_mark_web on public.transactions;
create trigger trg_txn_mark_web
    before insert or update on public.transactions
    for each row execute function public.mark_web_source();

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق
-- ----------------------------------------------------------------------------
select 'المزامنة ثنائية الاتجاه جاهزة ✔' as الحالة,
       (select count(*) from public.sync_deletions) as سجلات_الحذف;

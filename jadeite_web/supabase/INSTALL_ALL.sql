-- ============================================================================
--  جاديت ERP — ملف التثبيت الكامل (شغّله مرة واحدة)
--  Supabase → SQL Editor → New query → الصق كل المحتوى → Run
--
--  يشمل: الجداول + سياسات الحماية + دوال الحسابات + التهيئة + الموديولات
--         + طبقة المزامنة الهجينة مع برامج سطح المكتب
--
--  آمن ويمكن إعادة تشغيله أكثر من مرة (idempotent) بدون فقدان بيانات.
--
--  ⚠️ إن ظهر خطأ 500 "Database error querying schema" عند الدخول،
--     شغّل أولاً الملف: 00_repair_auth.sql
--
--  ⚙️ هذا الملف مُولَّد آلياً من الملفات المرقّمة (tools/build_install_all.py)
--     — عدّل الملف المرقّم لا هذا الملف.
-- ============================================================================

set client_min_messages = warning;


-- ############################################################################
-- ##  المصدر: 01_schema.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — مخطط قاعدة البيانات السحابية (Supabase / PostgreSQL)
--  نظام متعدد المستأجرين (Multi-Tenancy): كل مصنع = tenant واحد
--  شغّل الملفات بالترتيب: 01_schema → 02_rls → 03_functions → 04_seed
-- ============================================================================

create extension if not exists "pgcrypto";

-- ============================================================================
--  ١) المستأجرون (المصانع/العملاء)
-- ============================================================================
create table if not exists public.tenants (
    id              uuid primary key default gen_random_uuid(),
    business_name   text        not null,
    slug            text        unique,
    cr_number       text,
    vat_number      text,
    city            text,
    phone           text,
    logo_url        text,

    is_active       boolean     not null default true,
    -- قفل التعديل: يمنع تعديل الحركات المسجّلة فقط، ويبقى التسجيل والحذف متاحين
    can_edit        boolean     not null default true,

    last_login      timestamptz,
    last_seen       timestamptz,

    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

comment on column public.tenants.can_edit is
    'قفل التعديل من المدير: false يمنع تعديل الحركات المسجّلة فقط — التسجيل والحذف يبقيان متاحين';

-- ============================================================================
--  ٢) المستخدمون (مربوطون بـ auth.users)
-- ============================================================================
do $$ begin
    create type public.user_role as enum ('admin', 'owner', 'accountant', 'viewer');
exception when duplicate_object then null; end $$;

create table if not exists public.app_users (
    id          uuid primary key references auth.users(id) on delete cascade,
    tenant_id   uuid references public.tenants(id) on delete cascade,
    role        public.user_role not null default 'owner',
    full_name   text,
    email       text,
    is_active   boolean not null default true,
    created_at  timestamptz not null default now(),

    -- المدير العام فقط هو من يجوز أن يكون بلا مستأجر
    constraint app_users_tenant_required
        check (role = 'admin' or tenant_id is not null)
);

create index if not exists idx_app_users_tenant on public.app_users(tenant_id);

-- ============================================================================
--  ٣) شجرة الحسابات (العمال، الموردين، الصناديق، الحسابات العامة)
-- ============================================================================
do $$ begin
    create type public.account_category as enum (
        'المصنعين',
        'المركبين',
        'الآلة/المكائن',
        'الموردين',
        'صناديق الخياس',
        'حسابات عامة'
    );
exception when duplicate_object then null; end $$;

create table if not exists public.accounts (
    id          uuid primary key default gen_random_uuid(),
    tenant_id   uuid not null references public.tenants(id) on delete cascade,
    name        text not null,
    category    public.account_category not null,
    -- للصناديق فقط: اسم حساب المسترجع المرتبط، ونوعا حركة المدين/الدائن
    box_key     text,
    is_system   boolean not null default false,
    is_active   boolean not null default true,
    sort_order  int     not null default 0,
    created_at  timestamptz not null default now(),

    unique (tenant_id, name, category)
);

create index if not exists idx_accounts_tenant     on public.accounts(tenant_id);
create index if not exists idx_accounts_tenant_cat on public.accounts(tenant_id, category);

-- ============================================================================
--  ٤) الحركات — دفتر الأستاذ الموحّد لكل النظام
--     كل شيء حركة: وارد، مبيعات، عمليات تصنيع، خياس، قيود يومية، قيود افتتاحية
-- ============================================================================
--  ACTIVE / SETTLED_INOUT: حركات تُحتسب في الأرصدة (نفس فلتر برنامج سطح المكتب)
--  SETTLED: حركات قسم أُقفلت فترته وحلّ محلّها قيد الإقفال — لا تُحتسب
--  MEMO: سطور معلوماتية (خياس البوليش/المركب/صافي الطقم) — لا تُحتسب أبداً
do $$ begin
    create type public.txn_status as enum ('ACTIVE', 'SETTLED', 'SETTLED_INOUT', 'MEMO');
exception when duplicate_object then null; end $$;

-- القواعد القديمة أُنشئ فيها النوع بلا MEMO، فكان البرنامج يرفع السطور المعلوماتية
-- كـ ACTIVE فتدخل خطأً في رصيد الخزينة والصناديق عند المدير
alter type public.txn_status add value if not exists 'MEMO';

create table if not exists public.transactions (
    id              bigserial primary key,
    tenant_id       uuid not null references public.tenants(id) on delete cascade,

    -- رقم متسلسل داخل كل مستأجر (يقابل "رقم الفاتورة" في النظام القديم)
    seq_no          bigint not null,

    txn_date        timestamptz not null,
    -- شهر الحركة المحاسبي (YYYY-MM) — عمود عادي يُملأ تلقائياً من التاريخ بمحفّز
    -- (trg_txn_period أدناه) إن لم يُرسَل صراحةً. لا يصح أن يكون عموداً مُولَّداً:
    -- to_char على timestamptz ليست immutable فيرفضها PostgreSQL، وبرنامج سطح
    -- المكتب يرسل الفترة صراحةً لأنها قرار محاسبي قد يختلف عن شهر التاريخ.
    period          text,

    account_name    text not null,               -- الاسم (عامل/مورد/صندوق/حساب)
    op_type         text not null,               -- النوع (صرف ذهب، وارد ذهب، مبيعات ذهب ...)

    weight          numeric(14,3) not null default 0,   -- الوزن المعتمد محاسبياً
    weight_before   numeric(14,3) not null default 0,   -- "قبل" (الوزن الخام قبل الخصم/قبل المكينة)
    weight_after    numeric(14,3) not null default 0,   -- "بعد" (العيار أو الوزن بعد المكينة)

    note            text not null default '',
    status          public.txn_status not null default 'ACTIVE',

    trees_count     numeric(12,3) not null default 0,   -- عدد الأشجار / علامات داخلية
    set_number      text not null default '',           -- رقم التشغيل / سند الوارد
    row_number      text not null default '',           -- رقم الصف داخل الفاتورة أو المرحلة
    manual_no       text not null default '',           -- رقم الفاتورة اليدوي (المبيعات)

    created_by      uuid references auth.users(id),
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    unique (tenant_id, seq_no)
);

create index if not exists idx_txn_tenant_period  on public.transactions(tenant_id, period);
create index if not exists idx_txn_tenant_type    on public.transactions(tenant_id, op_type);
create index if not exists idx_txn_tenant_account on public.transactions(tenant_id, account_name);
create index if not exists idx_txn_tenant_set     on public.transactions(tenant_id, set_number);
create index if not exists idx_txn_tenant_manual  on public.transactions(tenant_id, manual_no);
create index if not exists idx_txn_tenant_row     on public.transactions(tenant_id, period, row_number);
create index if not exists idx_txn_status         on public.transactions(tenant_id, status);

-- ============================================================================
--  ٥) الإعدادات لكل مستأجر (مفتاح/قيمة)
-- ============================================================================
create table if not exists public.tenant_settings (
    tenant_id   uuid not null references public.tenants(id) on delete cascade,
    key         text not null,
    value       jsonb not null default '{}'::jsonb,
    updated_at  timestamptz not null default now(),
    primary key (tenant_id, key)
);

-- ============================================================================
--  ٦) إقفالات صناديق الخياس الشهرية
-- ============================================================================
create table if not exists public.box_closings (
    id           uuid primary key default gen_random_uuid(),
    tenant_id    uuid not null references public.tenants(id) on delete cascade,
    box_name     text not null,
    period       text not null,                 -- YYYY-MM
    closed_khayas numeric(14,3) not null default 0,
    closed_at    timestamptz not null default now(),
    closed_by    uuid references auth.users(id),
    unique (tenant_id, box_name, period)
);

-- ============================================================================
--  ٧) سجل التدقيق (من عدّل ماذا ومتى) — مهم لأن التعديل يمس أرصدة
-- ============================================================================
create table if not exists public.audit_log (
    id          bigserial primary key,
    tenant_id   uuid references public.tenants(id) on delete cascade,
    actor_id    uuid references auth.users(id),
    actor_label text,
    action      text not null,                  -- INSERT | UPDATE | DELETE
    table_name  text not null,
    record_id   text,
    before_data jsonb,
    after_data  jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists idx_audit_tenant on public.audit_log(tenant_id, created_at desc);

-- ============================================================================
--  ٨) تحديث updated_at تلقائياً
-- ============================================================================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end $$;

drop trigger if exists trg_tenants_touch on public.tenants;
create trigger trg_tenants_touch before update on public.tenants
    for each row execute function public.touch_updated_at();

drop trigger if exists trg_txn_touch on public.transactions;
create trigger trg_txn_touch before update on public.transactions
    for each row execute function public.touch_updated_at();

-- الفترة تُشتق من التاريخ فقط عندما لا تُرسل صراحةً — بدونها تُسجَّل حركات
-- الويب بفترة فارغة فتختفي من كل الشاشات والأرصدة المبنية على الفترة.
create or replace function public.fill_txn_period()
returns trigger language plpgsql as $$
begin
    if new.period is null or btrim(new.period) = '' then
        new.period := to_char(new.txn_date, 'YYYY-MM');
    end if;
    return new;
end $$;

drop trigger if exists trg_txn_period on public.transactions;
create trigger trg_txn_period before insert or update on public.transactions
    for each row execute function public.fill_txn_period();

-- ============================================================================
--  ٩) تسجيل التدقيق على الحركات
-- ============================================================================
create or replace function public.log_txn_audit()
returns trigger language plpgsql security definer set search_path = public as $$
declare
    v_tenant uuid;
begin
    v_tenant := coalesce(new.tenant_id, old.tenant_id);
    insert into public.audit_log(tenant_id, actor_id, action, table_name, record_id, before_data, after_data)
    values (
        v_tenant,
        auth.uid(),
        tg_op,
        'transactions',
        coalesce(new.id, old.id)::text,
        case when tg_op in ('UPDATE','DELETE') then to_jsonb(old) end,
        case when tg_op in ('UPDATE','INSERT') then to_jsonb(new) end
    );
    return coalesce(new, old);
end $$;

drop trigger if exists trg_txn_audit on public.transactions;
create trigger trg_txn_audit after insert or update or delete on public.transactions
    for each row execute function public.log_txn_audit();


-- ############################################################################
-- ##  المصدر: 02_rls.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — سياسات الأمان على مستوى الصف (RLS)
--  القاعدة: العميل لا يرى إلا بيانات مستأجره. المدير يرى ويعدّل كل شيء.
--  ملاحظة مهمة: دوال المساعدة SECURITY DEFINER حتى لا تدخل في تكرار لا نهائي
--  عند قراءة app_users من داخل سياسة على app_users نفسه.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  دوال المساعدة
-- ----------------------------------------------------------------------------
create or replace function public.current_tenant_id()
returns uuid
language sql stable security definer set search_path = public as $$
    select tenant_id from public.app_users where id = auth.uid();
$$;

create or replace function public.current_role_name()
returns text
language sql stable security definer set search_path = public as $$
    select role::text from public.app_users where id = auth.uid();
$$;

create or replace function public.is_admin()
returns boolean
language sql stable security definer set search_path = public as $$
    select coalesce(
        (select role = 'admin' and is_active from public.app_users where id = auth.uid()),
        false
    );
$$;

-- هل الطلب الحالي بمفتاح الخدمة (service_role)؟
-- نقرأ الدور من مطالبات JWT التي يضبطها PostgREST — ثابتة طوال الطلب بخلاف
-- current_user الذي يتغيّر داخل دوال SECURITY DEFINER.
create or replace function public.is_service_role()
returns boolean
language plpgsql stable as $$
declare
    v_role text;
begin
    begin
        v_role := current_setting('request.jwt.claims', true)::json ->> 'role';
    exception when others then
        v_role := null;
    end;
    return coalesce(v_role, '') = 'service_role';
end $$;

-- هل يملك المستخدم الحالي صلاحية الوصول لهذا المستأجر؟
-- هذا الفحص هو خط الدفاع الوحيد داخل دوال SECURITY DEFINER (التي تتخطى RLS)،
-- لذلك يجب أن تستدعيه كل دالة تقرأ أو تكتب بيانات مستأجر.
create or replace function public.has_tenant_access(p_tenant uuid)
returns boolean
language sql stable security definer set search_path = public as $$
    select public.is_admin()
        or public.is_service_role()
        or (
            p_tenant is not null
            and p_tenant = public.current_tenant_id()
            and coalesce((select is_active from public.app_users where id = auth.uid()), false)
            and coalesce((select is_active from public.tenants where id = p_tenant), false)
        );
$$;

-- هل التعديل مسموح على هذا المستأجر؟ (المدير غير مقيّد)
create or replace function public.can_edit_tenant(p_tenant uuid)
returns boolean
language sql stable security definer set search_path = public as $$
    select public.is_admin()
        or coalesce((select can_edit from public.tenants where id = p_tenant), false);
$$;

grant execute on function public.current_tenant_id()      to authenticated;
grant execute on function public.current_role_name()      to authenticated;
grant execute on function public.is_admin()               to authenticated;
grant execute on function public.has_tenant_access(uuid)  to authenticated;
grant execute on function public.can_edit_tenant(uuid)    to authenticated;

-- ----------------------------------------------------------------------------
--  تفعيل RLS على كل الجداول
-- ----------------------------------------------------------------------------
alter table public.tenants         enable row level security;
alter table public.app_users       enable row level security;
alter table public.accounts        enable row level security;
alter table public.transactions    enable row level security;
alter table public.tenant_settings enable row level security;
alter table public.box_closings    enable row level security;
alter table public.audit_log       enable row level security;

-- ملاحظة مهمة: لا نستخدم FORCE ROW LEVEL SECURITY إطلاقاً.
-- سببها أن دوال المساعدة SECURITY DEFINER تعمل بصلاحية مالك الجدول، ومع FORCE
-- يصبح المالك نفسه خاضعاً للسياسات، فتقرأ السياسة app_users عبر دالة تقرأ app_users
-- => تكرار لا نهائي (infinite recursion) وتفشل كل الاستعلامات.

-- ----------------------------------------------------------------------------
--  tenants
-- ----------------------------------------------------------------------------
drop policy if exists tenants_select on public.tenants;
create policy tenants_select on public.tenants for select to authenticated
    using (public.is_admin() or id = public.current_tenant_id());

drop policy if exists tenants_admin_write on public.tenants;
create policy tenants_admin_write on public.tenants for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- العميل يُسمح له فقط بتحديث وقت ظهوره (بقية الأعمدة محمية بمُشغّل أدناه)
drop policy if exists tenants_self_touch on public.tenants;
create policy tenants_self_touch on public.tenants for update to authenticated
    using (id = public.current_tenant_id())
    with check (id = public.current_tenant_id());

-- يمنع العميل من رفع القيود عن نفسه (can_edit / is_active) حتى لو حاول تحديث الصف
create or replace function public.guard_tenant_self_update()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    if public.is_admin() then
        return new;
    end if;
    new.can_edit      := old.can_edit;
    new.is_active     := old.is_active;
    new.business_name := old.business_name;
    new.slug          := old.slug;
    return new;
end $$;

drop trigger if exists trg_tenant_guard on public.tenants;
create trigger trg_tenant_guard before update on public.tenants
    for each row execute function public.guard_tenant_self_update();

-- ----------------------------------------------------------------------------
--  app_users
-- ----------------------------------------------------------------------------
drop policy if exists app_users_select on public.app_users;
create policy app_users_select on public.app_users for select to authenticated
    -- (id = auth.uid()) أولاً عمداً: قراءة المستخدم لسجله لا تعتمد على أي دالة مساعدة،
    -- فيبقى تسجيل الدخول شغّالاً حتى لو حدث خلل في الدوال الأخرى.
    using (id = auth.uid() or public.is_admin() or tenant_id = public.current_tenant_id());

drop policy if exists app_users_admin_write on public.app_users;
create policy app_users_admin_write on public.app_users for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- ----------------------------------------------------------------------------
--  accounts
-- ----------------------------------------------------------------------------
drop policy if exists accounts_select on public.accounts;
create policy accounts_select on public.accounts for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists accounts_insert on public.accounts;
create policy accounts_insert on public.accounts for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

-- التعديل يخضع لقفل المدير
drop policy if exists accounts_update on public.accounts;
create policy accounts_update on public.accounts for update to authenticated
    using (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id))
    with check (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id));

-- الحذف يبقى متاحاً حتى مع قفل التعديل
drop policy if exists accounts_delete on public.accounts;
create policy accounts_delete on public.accounts for delete to authenticated
    using (public.has_tenant_access(tenant_id) and not is_system);

-- ----------------------------------------------------------------------------
--  transactions — الجدول الأهم
-- ----------------------------------------------------------------------------
drop policy if exists txn_select on public.transactions;
create policy txn_select on public.transactions for select to authenticated
    using (public.has_tenant_access(tenant_id));

-- تسجيل حركة جديدة مسموح دائماً (حتى مع قفل التعديل)
drop policy if exists txn_insert on public.transactions;
create policy txn_insert on public.transactions for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

-- تعديل حركة مسجّلة يتوقف عند قفل المدير
drop policy if exists txn_update on public.transactions;
create policy txn_update on public.transactions for update to authenticated
    using (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id))
    with check (public.has_tenant_access(tenant_id) and public.can_edit_tenant(tenant_id));

-- الحذف مسموح دائماً — القفل يخص التعديل فقط
drop policy if exists txn_delete on public.transactions;
create policy txn_delete on public.transactions for delete to authenticated
    using (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  tenant_settings
-- ----------------------------------------------------------------------------
drop policy if exists settings_all on public.tenant_settings;
create policy settings_all on public.tenant_settings for all to authenticated
    using (public.has_tenant_access(tenant_id))
    with check (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  box_closings
-- ----------------------------------------------------------------------------
drop policy if exists closings_select on public.box_closings;
create policy closings_select on public.box_closings for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists closings_insert on public.box_closings;
create policy closings_insert on public.box_closings for insert to authenticated
    with check (public.has_tenant_access(tenant_id));

drop policy if exists closings_delete on public.box_closings;
create policy closings_delete on public.box_closings for delete to authenticated
    using (public.has_tenant_access(tenant_id));

-- ----------------------------------------------------------------------------
--  audit_log — قراءة فقط، ولا يُحذف من التطبيق إطلاقاً
-- ----------------------------------------------------------------------------
drop policy if exists audit_select on public.audit_log;
create policy audit_select on public.audit_log for select to authenticated
    using (public.has_tenant_access(tenant_id));


-- ############################################################################
-- ##  المصدر: 03_functions.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — الدوال المحاسبية (RPC)
--  كل الحسابات تتم في قاعدة البيانات لضمان رقم واحد صحيح لكل الأجهزة
--
--  قاعدتان تلتزم بهما كل دالة هنا:
--   ١) كل دالة SECURITY DEFINER تتخطى RLS، فلا بد أن تتحقق بنفسها من
--      public.has_tenant_access(p_tenant) — وإلا قرأ أي عميل (بل أي زائر بمفتاح
--      anon) بيانات مصنع غيره بمجرد معرفة معرّفه.
--   ٢) الحركات المحتسبة في الأرصدة هي (ACTIVE, SETTLED_INOUT) — نفس فلتر برنامج
--      سطح المكتب حرفياً — فلا يختلف رقم المدير عن رقم العميل.
-- ============================================================================

-- ----------------------------------------------------------------------------
--  أنواع الحركات — مصدر واحد للحقيقة يستخدمه SQL و Flutter
-- ----------------------------------------------------------------------------
create or replace function public.inbound_types() returns text[]
language sql immutable as $$
    select array['وارد ذهب (عيار 18)', 'وارد فصوص وأحجار', 'وارد الماس'];
$$;

create or replace function public.sale_types() returns text[]
language sql immutable as $$
    select array['مبيعات ذهب', 'مبيعات ذهب مع الماس', 'مبيعات فصوص وأحجار', 'مبيعات الماس'];
$$;

-- صناديق الخياس: (اسم الصندوق، نوع المدين، نوع الدائن، اسم المسترجع)
-- (يُعاد تعريفها في 15_period_ledger.sql بأسماء المسترجع كما يكتبها برنامج سطح المكتب)
create or replace function public.khayas_boxes()
returns table (box_name text, madin_type text, qabd_type text, mustarja_name text)
language sql immutable as $$
    values
        ('الكاستنج',      'صرف كاستنج',     'قبض كاستنج',      'مسترجع الكاستنج'),
        ('التلميع',       'صرف تلميع',      'قبض تلميع',       'مسترجع التلميع'),
        ('التلميع/البف',  'صرف تلميع بف',   'قبض تلميع بف',    'مسترجع التلميع/البف'),
        ('خياس الطقوم',   'خياس طقوم',      'قبض خياس طقوم',   'مسترجع خياس الطقوم');
$$;

-- ----------------------------------------------------------------------------
--  الرقم المتسلسل للحركة داخل كل مستأجر (آمن مع التزامن)
--  (يُعاد تعريفه في 06_hybrid_sync.sql ليحجز نطاقاً مستقلاً لحركات الويب
--   عند المصانع التي تعمل ببرنامج سطح المكتب)
-- ----------------------------------------------------------------------------
create or replace function public.next_seq_no(p_tenant uuid)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
    v_next bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;

    -- القفل على مستوى المستأجر يمنع تكرار الأرقام عند التسجيل من جهازين معاً
    perform pg_advisory_xact_lock(hashtext(p_tenant::text));
    select coalesce(max(seq_no), 0) + 1 into v_next
      from public.transactions where tenant_id = p_tenant;
    return v_next;
end $$;

-- ----------------------------------------------------------------------------
--  تسجيل حركة واحدة (يتكفّل بالرقم المتسلسل تلقائياً)
--
--  p_period: الفترة المحاسبية صراحةً (YYYY-MM). الفترة قرار محاسبي مستقل عن
--  التاريخ — تماماً كما في برنامج سطح المكتب — فلو غابت تُشتق من التاريخ.
--
--  التوقيع القديم (بلا p_period) يُحذف أولاً: بقاء النسختين معاً يجعل
--  PostgREST عاجزاً عن اختيار إحداهما (PGRST203).
-- ----------------------------------------------------------------------------
drop function if exists public.post_transaction(
    uuid, timestamptz, text, text, numeric, text, numeric, numeric, numeric, text, text, text);

create or replace function public.post_transaction(
    p_tenant        uuid,
    p_date          timestamptz,
    p_account       text,
    p_op_type       text,
    p_weight        numeric,
    p_note          text default '',
    p_before        numeric default 0,
    p_after         numeric default 0,
    p_trees         numeric default 0,
    p_set_number    text default '',
    p_row_number    text default '',
    p_manual_no     text default '',
    p_period        text default null
) returns bigint
language plpgsql security definer set search_path = public as $$
declare
    v_id bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;
    if coalesce(btrim(p_account), '') = '' or coalesce(btrim(p_op_type), '') = '' then
        raise exception 'الاسم ونوع الحركة مطلوبان';
    end if;
    if p_period is not null and btrim(p_period) <> '' and p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;

    insert into public.transactions(
        tenant_id, seq_no, txn_date, account_name, op_type, weight,
        weight_before, weight_after, note, trees_count,
        set_number, row_number, manual_no, period, created_by)
    values (
        p_tenant, public.next_seq_no(p_tenant), coalesce(p_date, now()),
        btrim(p_account), p_op_type, coalesce(p_weight, 0),
        coalesce(p_before, 0), coalesce(p_after, 0), coalesce(p_note, ''), coalesce(p_trees, 0),
        coalesce(p_set_number, ''), coalesce(p_row_number, ''), coalesce(p_manual_no, ''),
        nullif(btrim(coalesce(p_period, '')), ''), auth.uid())
    returning id into v_id;

    return v_id;
end $$;

-- ----------------------------------------------------------------------------
--  ترحيل عدة حركات دفعة واحدة — داخل معاملة واحدة: إما تُسجَّل كلها أو لا شيء.
--
--  p_rows: مصفوفة JSON، كل عنصر فيه مفاتيح أعمدة الحركة:
--    txn_date, account_name, op_type, weight, weight_before, weight_after,
--    note, trees_count, set_number, row_number, manual_no, period
--
--  p_replace_ids: (اختياري) أرقام حركات تُحذف في المعاملة نفسها قبل الإدراج —
--  هكذا يُعدَّل قيد مرحّل (فاتورة مثلاً) بلا أي لحظة تكون فيها الفاتورة ناقصة.
--  الاستبدال تعديلٌ، فيخضع لقفل التعديل من المدير.
-- ----------------------------------------------------------------------------
create or replace function public.post_transactions_batch(
    p_tenant      uuid,
    p_rows        jsonb,
    p_replace_ids bigint[] default null
) returns integer
language plpgsql security definer set search_path = public as $$
declare
    r          jsonb;
    v_count    integer := 0;
    v_deleted  integer := 0;
    v_expected integer := coalesce(array_length(p_replace_ids, 1), 0);
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;
    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        raise exception 'صيغة الحركات غير صحيحة';
    end if;

    if v_expected > 0 then
        if not public.can_edit_tenant(p_tenant) then
            raise exception 'التعديل مقفول من المدير — لا يمكن تعديل حركات مرحّلة';
        end if;

        delete from public.transactions
         where tenant_id = p_tenant
           and id = any(p_replace_ids);
        get diagnostics v_deleted = row_count;

        -- حُذف بعضها من جهاز آخر أثناء التعديل: نتوقف بدل إعادة كتابة نسخة قديمة
        if v_deleted <> v_expected then
            raise exception 'تغيّرت الحركات من جهاز آخر أثناء التعديل — أعد فتحها وحاول مجدداً';
        end if;
    end if;

    for r in select * from jsonb_array_elements(p_rows)
    loop
        if coalesce(btrim(r ->> 'account_name'), '') = ''
           or coalesce(btrim(r ->> 'op_type'), '') = '' then
            raise exception 'كل حركة تحتاج اسماً ونوعاً';
        end if;
        if coalesce(r ->> 'period', '') <> '' and (r ->> 'period') !~ '^\d{4}-\d{2}$' then
            raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', r ->> 'period';
        end if;

        insert into public.transactions(
            tenant_id, seq_no, txn_date, account_name, op_type, weight,
            weight_before, weight_after, note, trees_count,
            set_number, row_number, manual_no, period, created_by)
        values (
            p_tenant,
            public.next_seq_no(p_tenant),
            coalesce((r ->> 'txn_date')::timestamptz, now()),
            btrim(r ->> 'account_name'),
            r ->> 'op_type',
            coalesce((r ->> 'weight')::numeric, 0),
            coalesce((r ->> 'weight_before')::numeric, 0),
            coalesce((r ->> 'weight_after')::numeric, 0),
            coalesce(r ->> 'note', ''),
            coalesce((r ->> 'trees_count')::numeric, 0),
            coalesce(r ->> 'set_number', ''),
            coalesce(r ->> 'row_number', ''),
            coalesce(r ->> 'manual_no', ''),
            nullif(btrim(coalesce(r ->> 'period', '')), ''),
            auth.uid());
        v_count := v_count + 1;
    end loop;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  رصيد الخزينة (ذهب عيار ١٨) حتى نهاية فترة معيّنة
--  = الوارد + الرصيد الافتتاحي − المبيعات − الصادر − الخياس المقفل
--    ± صرف/قبض صناديق الخياس ± القيود اليومية على حساب الخزينة
--  (يُعاد تعريفها في 15_period_ledger.sql لتقرأ دفتر الفترات — فتخصم خياس
--   المصنعين والمركبين الفعلي وتطابق شريط الخزينة في البرنامج)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_balance(p_tenant uuid, p_until_period text default null)
returns numeric
language sql stable security definer set search_path = public as $$
    with t as (
        select op_type, weight, account_name
          from public.transactions
         where tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and status in ('ACTIVE', 'SETTLED_INOUT')
           and (p_until_period is null or period <= p_until_period)
    )
    select coalesce(sum(
        case
            when op_type in ('وارد ذهب (عيار 18)', 'رصيد افتتاحي')             then  weight
            when op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس',
                             'صادر ذهب', 'صرف خياس مقفل')                    then -weight
            when op_type in (select madin_type from public.khayas_boxes())    then -weight
            when op_type in (select qabd_type  from public.khayas_boxes())    then  weight
            when op_type = 'قيد يومي مدين'  and account_name = 'حساب الخزينة' then  weight
            when op_type = 'قيد يومي دائن'  and account_name = 'حساب الخزينة' then -weight
            else 0
        end), 0)
      from t;
$$;

-- ----------------------------------------------------------------------------
--  كشف حركة صندوق خياس لفترة (مدين/دائن/الخياس)
-- ----------------------------------------------------------------------------
create or replace function public.box_period_totals(p_tenant uuid, p_box text, p_period text)
returns table (madin numeric, daen numeric, khayas numeric)
language sql stable security definer set search_path = public as $$
    with cfg as (select * from public.khayas_boxes() where box_name = p_box),
    t as (
        select x.op_type, x.weight, x.account_name
          from public.transactions x
         where x.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and x.status in ('ACTIVE', 'SETTLED_INOUT')
           and x.period = p_period
    ),
    s as (
        select
            coalesce(sum(case when t.op_type = (select madin_type from cfg) then t.weight else 0 end), 0) as madin,
            coalesce(sum(case
                when t.op_type = (select qabd_type from cfg) then t.weight
                when t.op_type = any(public.inbound_types())
                     and t.account_name = (select mustarja_name from cfg) then t.weight
                else 0 end), 0) as daen
          from t
    )
    select s.madin, s.daen, s.madin - s.daen from s;
$$;

-- ----------------------------------------------------------------------------
--  كشف حركة عامل (مصنّع/مركّب) لفترة — مجمّع برقم الصف
--  الفاقد اللحظي للمصنعين = صرف − قبض − بوليش + ليز − مفنش٨ − مفنش٤
--  الفاقد اللحظي للمركبين = صرف − قبض + ليز
-- ----------------------------------------------------------------------------
create or replace function public.worker_ledger(p_tenant uuid, p_worker text, p_period text)
returns table (
    row_number text, set_number text, txn_date timestamptz,
    sarf numeric, qabd numeric, laiz numeric, polish numeric,
    mufanish8 numeric, mufanish4 numeric, wire_back numeric, carat numeric,
    note text, instant_loss numeric
)
language sql stable security definer set search_path = public as $$
    with g as (
        select
            t.row_number as rn,
            max(nullif(t.set_number, '')) as sn,
            min(t.txn_date) as dt,
            sum(case when t.op_type = 'صرف ذهب'            then t.weight else 0 end) as sarf,
            sum(case when t.op_type = 'قبض ذهب'            then t.weight else 0 end) as qabd,
            sum(case when t.op_type = 'الليز'              then t.weight else 0 end) as laiz,
            sum(case when t.op_type = 'البوليش'            then t.weight else 0 end) as polish,
            sum(case when t.op_type = 'المفنش ٨ بالالف'    then t.weight else 0 end) as m8,
            sum(case when t.op_type = 'المفنش ٤ بالالف'    then t.weight else 0 end) as m4,
            sum(case when t.op_type = 'السلك الراجع'       then t.weight else 0 end) as wire,
            max(case when t.op_type = 'العيار بعد الفحص'   then t.weight else 0 end) as carat,
            string_agg(distinct nullif(t.note, ''), ' | ') as note
          from public.transactions t
         where t.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and t.status in ('ACTIVE', 'SETTLED_INOUT')
           and t.account_name = p_worker and t.period = p_period
         group by t.row_number
    )
    select
        g.rn, coalesce(g.sn, ''), g.dt,
        g.sarf, g.qabd, g.laiz, g.polish, g.m8, g.m4, g.wire, g.carat,
        coalesce(g.note, ''),
        round(g.sarf - g.qabd - g.polish + g.laiz - g.m8 - g.m4, 3)
      from g
     order by nullif(regexp_replace(g.rn, '\D', '', 'g'), '')::numeric nulls last, g.rn, g.dt;
$$;

-- ----------------------------------------------------------------------------
--  فواتير المبيعات المرحّلة لفترة — كل فاتورة في صف واحد
-- ----------------------------------------------------------------------------
create or replace function public.sales_invoices(p_tenant uuid, p_period text)
returns table (
    manual_no text, txn_date timestamptz, account_name text,
    gold numeric, gems numeric, stones_after numeric, diamond numeric,
    khayas numeric, lines_count bigint
)
language sql stable security definer set search_path = public as $$
    select
        t.manual_no,
        t.txn_date,
        t.account_name,
        coalesce(sum(case when t.op_type in ('مبيعات ذهب','مبيعات ذهب مع الماس') then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count <> 3 then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count  = 3 then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'مبيعات الماس' then t.weight else 0 end), 0),
        coalesce(sum(case when t.op_type = 'خياس طقوم'    then t.weight else 0 end), 0),
        count(distinct nullif(t.set_number, ''))
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.period = p_period
       and (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
     group by t.manual_no, t.txn_date, t.account_name
     order by t.txn_date;
$$;

-- ----------------------------------------------------------------------------
--  إجمالي فواقد الورشة لفترة
-- ----------------------------------------------------------------------------
create or replace function public.workshop_losses(p_tenant uuid, p_period text)
returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce(sum(b.khayas), 0)
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b;
$$;

-- ----------------------------------------------------------------------------
--  رصيد حساب قبل فترة معيّنة (رصيد أول المدة في كشف الحساب)
--  p_debit_types: الأنواع التي تُعدّ مديناً على الحساب — تُمرَّر من التطبيق
--  حتى يبقى تعريف المدين/الدائن في مكان واحد مع شاشة الكشف نفسها.
-- ----------------------------------------------------------------------------
create or replace function public.account_opening_balance(
    p_tenant      uuid,
    p_account     text,
    p_period      text,
    p_debit_types text[]
) returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce(sum(case when t.op_type = any(p_debit_types) then t.weight else -t.weight end), 0)
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.account_name = p_account
       and t.period < p_period;
$$;

-- ----------------------------------------------------------------------------
--  تسجيل نشاط العميل (آخر دخول / آخر ظهور)
--  المدير المتصفّح لحساب عميل لا يُحسب حضوراً للعميل — وإلا ظهر العميل
--  «متصلاً الآن» في لوحة المتابعة وهو غير متصل أصلاً.
-- ----------------------------------------------------------------------------
create or replace function public.touch_activity(p_tenant uuid, p_is_login boolean default false)
returns void
language plpgsql security definer set search_path = public as $$
begin
    if not public.has_tenant_access(p_tenant) then
        return;
    end if;
    if public.is_admin() and public.current_tenant_id() is distinct from p_tenant then
        return;
    end if;
    update public.tenants
       set last_seen  = now(),
           last_login = case when p_is_login then now() else last_login end
     where id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  لوحة المدير: كل العملاء مع حالتهم
-- ----------------------------------------------------------------------------
create or replace function public.admin_tenants_overview()
returns table (
    id uuid, business_name text, is_active boolean, can_edit boolean,
    last_login timestamptz, last_seen timestamptz,
    is_online boolean, txn_count bigint, last_txn_at timestamptz
)
language sql stable security definer set search_path = public as $$
    select
        t.id, t.business_name, t.is_active, t.can_edit,
        t.last_login, t.last_seen,
        (t.last_seen is not null and t.last_seen > now() - interval '2 minutes'),
        (select count(*) from public.transactions x where x.tenant_id = t.id),
        (select max(x.created_at) from public.transactions x where x.tenant_id = t.id)
      from public.tenants t
     where public.is_admin()
     order by t.business_name;
$$;

grant execute on function public.inbound_types()                  to authenticated;
grant execute on function public.sale_types()                     to authenticated;
grant execute on function public.khayas_boxes()                   to authenticated;
grant execute on function public.next_seq_no(uuid)                to authenticated;
grant execute on function public.post_transaction(uuid, timestamptz, text, text, numeric, text, numeric, numeric, numeric, text, text, text, text) to authenticated;
grant execute on function public.post_transactions_batch(uuid, jsonb, bigint[]) to authenticated;
grant execute on function public.treasury_balance(uuid, text)     to authenticated;
grant execute on function public.box_period_totals(uuid, text, text) to authenticated;
grant execute on function public.worker_ledger(uuid, text, text)  to authenticated;
grant execute on function public.sales_invoices(uuid, text)       to authenticated;
grant execute on function public.workshop_losses(uuid, text)      to authenticated;
grant execute on function public.account_opening_balance(uuid, text, text, text[]) to authenticated;
grant execute on function public.touch_activity(uuid, boolean)    to authenticated;
grant execute on function public.admin_tenants_overview()         to authenticated;


-- ############################################################################
-- ##  المصدر: 04_seed.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — تهيئة مستأجر جديد بحساباته الافتراضية
-- ============================================================================

create or replace function public.seed_tenant_defaults(p_tenant uuid)
returns void
language plpgsql security definer set search_path = public as $$
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير فقط';
    end if;

    -- حسابات النظام الأساسية
    insert into public.accounts(tenant_id, name, category, is_system, sort_order) values
        (p_tenant, 'المصنع',            'حسابات عامة',  true, 1),
        (p_tenant, 'حساب الخزينة',      'حسابات عامة',  true, 2),
        (p_tenant, 'حساب المبيعات',     'حسابات عامة',  true, 3),
        (p_tenant, 'حساب الخسائر',      'حسابات عامة',  true, 4)
    on conflict do nothing;

    -- صناديق الخياس وحسابات المسترجع المرتبطة بها
    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select p_tenant, k.box_name, 'صناديق الخياس', k.box_name, true, 10
      from public.khayas_boxes() k
    on conflict do nothing;

    insert into public.accounts(tenant_id, name, category, box_key, is_system, sort_order)
    select p_tenant, k.mustarja_name, 'الموردين', k.box_name, true, 20
      from public.khayas_boxes() k
    on conflict do nothing;

    -- الإعدادات الافتراضية
    insert into public.tenant_settings(tenant_id, key, value) values
        (p_tenant, 'stones_discount_pct', '30'::jsonb),
        (p_tenant, 'home_screen_order',   '[]'::jsonb)
    on conflict do nothing;
end $$;

grant execute on function public.seed_tenant_defaults(uuid) to authenticated;

-- ----------------------------------------------------------------------------
--  إنشاء مستأجر جديد + ربط مستخدم به (يُنفَّذ من لوحة المدير)
-- ----------------------------------------------------------------------------
create or replace function public.admin_create_tenant(
    p_business_name text,
    p_user_id       uuid default null,
    p_full_name     text default null
) returns uuid
language plpgsql security definer set search_path = public as $$
declare
    v_tenant uuid;
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير فقط';
    end if;

    insert into public.tenants(business_name) values (p_business_name) returning id into v_tenant;
    perform public.seed_tenant_defaults(v_tenant);

    if p_user_id is not null then
        insert into public.app_users(id, tenant_id, role, full_name)
        values (p_user_id, v_tenant, 'owner', p_full_name)
        on conflict (id) do update set tenant_id = excluded.tenant_id, role = excluded.role;
    end if;

    return v_tenant;
end $$;

grant execute on function public.admin_create_tenant(text, uuid, text) to authenticated;


-- ############################################################################
-- ##  المصدر: 05_modules.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — دوال الموديولات المكمّلة
--  (القيود اليومية، إقفال الصناديق، أرشيف الفواتير والبحث، الخسائر والهالك)
--  شغّل هذا الملف بعد 03_functions.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) قيد يومي مزدوج: طرف مدين وطرف دائن بنفس الوزن ونفس المرجع
--     الترحيل داخل معاملة واحدة — إما يُسجَّل الطرفان معاً أو لا شيء إطلاقاً،
--     فلا يبقى قيد غير متوازن في الدفاتر أبداً.
-- ----------------------------------------------------------------------------
-- التوقيع القديم (بلا p_period) يُحذف أولاً حتى لا يلتبس الاستدعاء على PostgREST
drop function if exists public.post_journal_entry(uuid, timestamptz, text, text, numeric, text);

create or replace function public.post_journal_entry(
    p_tenant     uuid,
    p_date       timestamptz,
    p_from       text,          -- الحساب الدائن (خرج منه)
    p_to         text,          -- الحساب المدين (دخل إليه)
    p_weight     numeric,
    p_note       text default '',
    p_period     text default null   -- الفترة المحاسبية صراحةً (YYYY-MM)
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_ref     text;
    v_seq     bigint;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;
    if p_weight is null or p_weight <= 0 then
        raise exception 'وزن القيد يجب أن يكون أكبر من صفر';
    end if;
    if p_from is null or p_to is null or btrim(p_from) = '' or btrim(p_to) = '' then
        raise exception 'الرجاء تحديد الحساب المدين والحساب الدائن';
    end if;
    if btrim(p_from) = btrim(p_to) then
        raise exception 'لا يصح أن يكون الطرف المدين هو نفسه الطرف الدائن';
    end if;
    if p_period is not null and btrim(p_period) <> '' and p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;

    v_seq := public.next_seq_no(p_tenant);
    v_ref := 'JE-' || v_seq::text;

    -- الطرف المدين (الحساب المستلم)
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, p_date, btrim(p_to), 'قيد يومي مدين', p_weight,
         coalesce(nullif(btrim(p_note), ''), 'قيد يومي'), v_ref,
         nullif(btrim(coalesce(p_period, '')), ''), auth.uid());

    -- الطرف الدائن (الحساب المصدر)
    v_seq := public.next_seq_no(p_tenant);
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, p_date, btrim(p_from), 'قيد يومي دائن', p_weight,
         coalesce(nullif(btrim(p_note), ''), 'قيد يومي'), v_ref,
         nullif(btrim(coalesce(p_period, '')), ''), auth.uid());

    return v_ref;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) حذف قيد يومي كامل بطرفيه — حذف طرف واحد يترك الدفاتر غير متوازنة
-- ----------------------------------------------------------------------------
create or replace function public.delete_journal_entry(p_tenant uuid, p_ref text)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    -- قيد الإقفال مرتبط بسجل في box_closings: حذفه من هنا يترك الصندوق
    -- «مُقفلاً» بلا قيد، فيُلغى فقط من شاشة الإقفال (reopen_khayas_box)
    if p_ref like 'CLOSE-%' then
        raise exception 'هذا قيد إقفال صندوق — ألغِه من شاشة إقفال الصناديق (زر التراجع)';
    end if;

    delete from public.transactions
     where tenant_id = p_tenant
       and set_number = p_ref
       and op_type in ('قيد يومي مدين', 'قيد يومي دائن');

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) القيود اليومية لفترة، مجمّعة في قيد واحد بطرفيه
-- ----------------------------------------------------------------------------
create or replace function public.journal_entries(p_tenant uuid, p_period text)
returns table (
    entry_ref   text,
    txn_date    timestamptz,
    debit_acc   text,
    credit_acc  text,
    weight      numeric,
    note        text,
    is_balanced boolean
)
language sql stable security definer set search_path = public as $$
    select
        t.set_number,
        min(t.txn_date),
        max(t.account_name) filter (where t.op_type = 'قيد يومي مدين'),
        max(t.account_name) filter (where t.op_type = 'قيد يومي دائن'),
        max(t.weight),
        max(t.note),
        -- القيد سليم فقط لو كان له طرفان بنفس الوزن
        (count(*) = 2
         and coalesce(sum(case when t.op_type = 'قيد يومي مدين' then t.weight else -t.weight end), 1) = 0)
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and t.period = p_period
       and t.op_type in ('قيد يومي مدين', 'قيد يومي دائن')
     group by t.set_number
     order by min(t.txn_date), t.set_number;
$$;

-- ----------------------------------------------------------------------------
--  ٤) إقفال صندوق خياس لفترة
--     الإقفال = ترحيل رصيد الصندوق لحساب الخسائر بقيد مزدوج + تسجيل الإقفال،
--     فلا يبقى الرصيد معلّقاً ولا يتكرر تحميله على الشهر التالي.
-- ----------------------------------------------------------------------------
create or replace function public.close_khayas_box(
    p_tenant uuid,
    p_box    text,
    p_period text
)
returns numeric
language plpgsql security definer set search_path = public as $$
declare
    v_khayas numeric;
    v_seq    bigint;
    v_ref    text;
    v_date   timestamptz;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    if p_period is null or p_period !~ '^\d{4}-\d{2}$' then
        raise exception 'صيغة الفترة غير صحيحة (المتوقع YYYY-MM): %', p_period;
    end if;
    if not exists (select 1 from public.khayas_boxes() k where k.box_name = p_box) then
        raise exception 'صندوق غير معروف: %', p_box;
    end if;

    if exists (select 1 from public.box_closings
                where tenant_id = p_tenant and box_name = p_box and period = p_period) then
        raise exception 'صندوق (%) مُقفل مسبقاً لفترة (%)', p_box, p_period;
    end if;

    select khayas into v_khayas from public.box_period_totals(p_tenant, p_box, p_period);
    v_khayas := coalesce(v_khayas, 0);

    if v_khayas = 0 then
        raise exception 'لا يوجد رصيد خياس لإقفاله في صندوق (%) خلال (%)', p_box, p_period;
    end if;

    -- تاريخ الإقفال = آخر لحظة في الشهر المُقفل، حتى يبقى القيد داخل فترته
    v_date := (to_date(p_period || '-01', 'YYYY-MM-DD') + interval '1 month' - interval '1 second');

    v_seq := public.next_seq_no(p_tenant);
    v_ref := 'CLOSE-' || p_box || '-' || p_period;

    -- الرصيد الموجب (خياس/فاقد) يُحمَّل على حساب الخسائر، والسالب (فائض) يُرد منه
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, v_date, 'حساب الخسائر',
         case when v_khayas > 0 then 'قيد يومي مدين' else 'قيد يومي دائن' end,
         abs(v_khayas), 'إقفال صندوق ' || p_box || ' — ' || p_period, v_ref, p_period, auth.uid());

    v_seq := public.next_seq_no(p_tenant);
    insert into public.transactions
        (tenant_id, seq_no, txn_date, account_name, op_type, weight, note, set_number, period, created_by)
    values
        (p_tenant, v_seq, v_date, p_box,
         case when v_khayas > 0 then 'قيد يومي دائن' else 'قيد يومي مدين' end,
         abs(v_khayas), 'إقفال صندوق ' || p_box || ' — ' || p_period, v_ref, p_period, auth.uid());

    insert into public.box_closings (tenant_id, box_name, period, closed_khayas, closed_by)
    values (p_tenant, p_box, p_period, v_khayas, auth.uid());

    return v_khayas;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) التراجع عن إقفال صندوق (يحذف قيد الإقفال وسجلّه معاً)
-- ----------------------------------------------------------------------------
create or replace function public.reopen_khayas_box(
    p_tenant uuid,
    p_box    text,
    p_period text
)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ref text := 'CLOSE-' || p_box || '-' || p_period;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'غير مصرّح بالوصول لهذا الحساب';
    end if;

    delete from public.transactions
     where tenant_id = p_tenant and set_number = v_ref;

    delete from public.box_closings
     where tenant_id = p_tenant and box_name = p_box and period = p_period;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) حالة إقفال كل الصناديق لفترة
-- ----------------------------------------------------------------------------
create or replace function public.boxes_closing_status(p_tenant uuid, p_period text)
returns table (
    box_name      text,
    madin         numeric,
    daen          numeric,
    khayas        numeric,
    is_closed     boolean,
    closed_khayas numeric,
    closed_at     timestamptz
)
language sql stable security definer set search_path = public as $$
    select
        k.box_name,
        b.madin,
        b.daen,
        b.khayas,
        (c.id is not null),
        coalesce(c.closed_khayas, 0),
        c.closed_at
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b
      left join public.box_closings c
             on c.tenant_id = p_tenant and c.box_name = k.box_name and c.period = p_period
     where (select public.has_tenant_access(p_tenant))
     order by k.box_name;
$$;

-- ----------------------------------------------------------------------------
--  ٧) تفصيل الخسائر والهالك لفترة
--     يجمع: خياس كل صندوق + ذهب/صافي للمصنعين والمركبين
-- ----------------------------------------------------------------------------
create or replace function public.losses_breakdown(p_tenant uuid, p_period text)
returns table (
    source_kind  text,     -- 'صندوق' أو 'عامل'
    source_name  text,
    category     text,
    amount       numeric,
    is_closed    boolean
)
language sql stable security definer set search_path = public as $$
    -- خياس الصناديق
    select
        'صندوق'::text,
        k.box_name,
        'صناديق الخياس'::text,
        b.khayas,
        (c.id is not null)
      from public.khayas_boxes() k
     cross join lateral public.box_period_totals(p_tenant, k.box_name, p_period) b
      left join public.box_closings c
             on c.tenant_id = p_tenant and c.box_name = k.box_name and c.period = p_period
     where b.khayas <> 0
       and (select public.has_tenant_access(p_tenant))

    union all

    -- الفاقد الفعلي لكل عامل في المصنعين والمركبين
    select
        'عامل'::text,
        a.name,
        a.category::text,
        coalesce((
            select sum(
                case
                    when a.category::text = 'المركبين'
                        then case t.op_type
                                when 'صرف ذهب' then t.weight
                                when 'قبض ذهب' then -t.weight
                                when 'الليز'   then t.weight
                                else 0 end
                    else case t.op_type
                                when 'صرف ذهب'          then t.weight
                                when 'قبض ذهب'          then -t.weight
                                when 'البوليش'          then -t.weight
                                when 'الليز'            then t.weight
                                when 'المفنش ٨ بالالف'  then -t.weight
                                when 'المفنش ٤ بالالف'  then -t.weight
                                else 0 end
                end)
              from public.transactions t
             where t.tenant_id = p_tenant
               and t.status in ('ACTIVE', 'SETTLED_INOUT')
               and t.period = p_period
               and t.account_name = a.name
        ), 0),
        false
      from public.accounts a
     where a.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and a.is_active
       and a.category::text in ('المصنعين', 'المركبين')
       and coalesce((
            select sum(case t.op_type when 'صرف ذهب' then t.weight else 0 end)
              from public.transactions t
             where t.tenant_id = p_tenant and t.status in ('ACTIVE', 'SETTLED_INOUT')
               and t.period = p_period and t.account_name = a.name
       ), 0) <> 0
     order by 3, 4 desc;
$$;

-- ----------------------------------------------------------------------------
--  ٨) أرشيف الفواتير: كل فاتورة مبيعات في صف واحد
-- ----------------------------------------------------------------------------
create or replace function public.invoice_archive(
    p_tenant uuid,
    p_period text default null,
    p_query  text default null
)
returns table (
    manual_no    text,
    txn_date     timestamptz,
    account_name text,
    gold         numeric,
    gems         numeric,
    stones_after numeric,
    diamond      numeric,
    khayas       numeric,
    lines_count  bigint,
    set_numbers  text
)
language sql stable security definer set search_path = public as $$
    select
        t.manual_no,
        min(t.txn_date),
        t.account_name,
        coalesce(sum(t.weight) filter (where t.op_type in ('مبيعات ذهب','مبيعات ذهب مع الماس')), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count <> 3), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات فصوص وأحجار' and t.trees_count = 3), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'مبيعات الماس'), 0),
        coalesce(sum(t.weight) filter (where t.op_type = 'خياس طقوم'), 0),
        count(distinct nullif(t.set_number, '')),
        string_agg(distinct nullif(t.set_number, ''), '، ')
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
       and (p_period is null or t.period = p_period)
       and (
            p_query is null or btrim(p_query) = ''
            or t.manual_no    ilike '%' || p_query || '%'
            or t.set_number   ilike '%' || p_query || '%'
            or t.account_name ilike '%' || p_query || '%'
       )
     group by t.manual_no, t.account_name, date_trunc('second', t.txn_date)
     order by min(t.txn_date) desc;
$$;

-- ----------------------------------------------------------------------------
--  ٩) البحث الموحّد مع تحديد الشاشة
--     أرقام الفواتير قد تتكرر بين الشاشات، لذا تحديد المصدر ضروري
--     p_source: المبيعات | الوارد | القيود | الافتتاحي | التشغيل | الكل
-- ----------------------------------------------------------------------------
create or replace function public.search_transactions(
    p_tenant uuid,
    p_source text,
    p_query  text
)
returns setof public.transactions
language sql stable security definer set search_path = public as $$
    select t.*
      from public.transactions t
     where t.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and t.status in ('ACTIVE', 'SETTLED_INOUT')
       and btrim(coalesce(p_query, '')) <> ''
       and case p_source
            when 'المبيعات' then
                (t.op_type = any(public.sale_types()) or t.op_type = 'خياس طقوم')
                and (t.manual_no = btrim(p_query) or t.seq_no::text = btrim(p_query))
            when 'الوارد' then
                t.op_type = any(public.inbound_types())
                and (t.set_number = btrim(p_query) or t.seq_no::text = btrim(p_query))
            when 'القيود' then
                t.op_type in ('قيد يومي مدين', 'قيد يومي دائن')
                and (t.set_number = btrim(p_query)
                     or t.set_number = 'JE-' || btrim(p_query)
                     or t.seq_no::text = btrim(p_query))
            when 'الافتتاحي' then
                t.trees_count = 1 and t.note = 'قيد افتتاحي'
                and t.seq_no::text = btrim(p_query)
            when 'التشغيل' then
                t.set_number = btrim(p_query)
            else
                t.seq_no::text = btrim(p_query)
                or t.manual_no = btrim(p_query)
                or t.set_number = btrim(p_query)
           end
     order by t.txn_date, t.seq_no;
$$;

-- ----------------------------------------------------------------------------
--  الصلاحيات
-- ----------------------------------------------------------------------------
grant execute on function public.post_journal_entry(uuid, timestamptz, text, text, numeric, text, text) to authenticated;
grant execute on function public.delete_journal_entry(uuid, text)          to authenticated;
grant execute on function public.journal_entries(uuid, text)               to authenticated;
grant execute on function public.close_khayas_box(uuid, text, text)        to authenticated;
grant execute on function public.reopen_khayas_box(uuid, text, text)       to authenticated;
grant execute on function public.boxes_closing_status(uuid, text)          to authenticated;
grant execute on function public.losses_breakdown(uuid, text)              to authenticated;
grant execute on function public.invoice_archive(uuid, text, text)         to authenticated;
grant execute on function public.search_transactions(uuid, text, text)     to authenticated;


-- ############################################################################
-- ##  المصدر: 06_hybrid_sync.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — طبقة المزامنة الهجينة (Hybrid Sync Layer)
--
--  المعمارية:
--    • العميل يعمل على SQLite محلياً (يشتغل بدون إنترنت)
--    • خيط خلفي في البرنامج يرفع الحركات إلى Supabase عبر دوال RPC فقط
--    • لوحة المدير (الويب) تقرأ من Supabase مباشرة عبر Supabase Auth + RLS
--
--  مبدأ الأمان الأساسي:
--    برنامج سطح المكتب يحمل مفتاح anon فقط (لأنه يُوزَّع على العملاء).
--    لذلك: anon **ممنوع** من الوصول المباشر لأي جدول، ولا يستطيع إلا استدعاء
--    دوال المزامنة أدناه، وكل دالة تتحقق من (tenant_id + sync_token) قبل الكتابة.
--    النتيجة: حتى لو فُكِّك ملف exe واستُخرج مفتاح anon، لن يصل حامله لبيانات
--    أي عميل آخر، ولن يقرأ شيئاً أصلاً — الدوال تكتب فقط.
--
--  شغّل هذا الملف بعد INSTALL_ALL.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) رمز المزامنة لكل عميل + بيانات جهازه
-- ----------------------------------------------------------------------------
alter table public.tenants
    add column if not exists sync_token   uuid not null default gen_random_uuid(),
    add column if not exists sync_enabled boolean not null default true,
    add column if not exists last_sync_at timestamptz;

comment on column public.tenants.sync_token is
    'رمز سرّي يُسلَّم لبرنامج العميل ويُخزَّن في device_session.json — يُبطل بتغييره فوراً';

create table if not exists public.tenant_devices (
    id            uuid primary key default gen_random_uuid(),
    tenant_id     uuid not null references public.tenants(id) on delete cascade,
    device_id     text not null,
    device_name   text default '',
    app_version   text default '',
    last_sync_at  timestamptz,
    pending_count int default 0,
    pushed_total  bigint default 0,
    last_error    text,
    created_at    timestamptz not null default now(),
    unique (tenant_id, device_id)
);

create index if not exists idx_devices_tenant on public.tenant_devices(tenant_id);

-- تتبّع مصدر كل حركة: هل جاءت من برنامج سطح المكتب أم أُدخلت من الويب
alter table public.transactions
    add column if not exists source      text not null default 'desktop',
    add column if not exists device_id   text default '',
    add column if not exists synced_at   timestamptz;

alter table public.accounts
    add column if not exists source text not null default 'desktop';

-- ----------------------------------------------------------------------------
--  ١-أ) حماية أعمدة المزامنة من العميل نفسه
--      سياسة tenants_self_touch تسمح للعميل بتحديث صفّه (لآخر ظهور)، فبدون هذا
--      يستطيع إعادة تفعيل مزامنة أوقفها المدير أو تغيير رمزها بنفسه.
-- ----------------------------------------------------------------------------
create or replace function public.guard_tenant_self_update()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    -- المدير، ومفتاح الخدمة، والجلسة المباشرة على القاعدة (SQL Editor — بلا JWT
    -- إطلاقاً، بخلاف طلبات PostgREST التي تحمل دوماً دور anon أو authenticated)
    if public.is_admin() or public.is_service_role()
       or coalesce(current_setting('request.jwt.claims', true), '') = '' then
        return new;
    end if;
    new.can_edit      := old.can_edit;
    new.is_active     := old.is_active;
    new.business_name := old.business_name;
    new.slug          := old.slug;
    new.sync_token    := old.sync_token;
    new.sync_enabled  := old.sync_enabled;
    new.last_sync_at  := old.last_sync_at;
    return new;
end $$;

-- ----------------------------------------------------------------------------
--  ١-ب) ترقيم حركات الويب عند مصانع سطح المكتب
--
--  برنامج سطح المكتب يرقّم حركاته محلياً (invoice_id) ويرفعها بالرقم نفسه،
--  والرفع upsert على (tenant_id, seq_no). لو أخذت حركة من الويب الرقم التالي
--  (max + 1) لاصطدمت بأول حركة جديدة يسجّلها العميل على جهازه، فيكتب الرفعُ
--  فوقها ويمحوها بصمت. الحل: حركات الويب لمصنع يعمل ببرنامج سطح المكتب
--  تأخذ أرقاماً من نطاق مستقل يبدأ من مليار، لا يصل إليه ترقيم الجهاز أبداً.
-- ----------------------------------------------------------------------------
create or replace function public.next_seq_no(p_tenant uuid)
returns bigint
language plpgsql security definer set search_path = public as $$
declare
    c_web_base constant bigint := 1000000000;
    v_next    bigint;
    v_desktop boolean;
begin
    if not public.has_tenant_access(p_tenant) then
        raise exception 'ليس لديك صلاحية على هذا الحساب';
    end if;

    -- القفل على مستوى المستأجر يمنع تكرار الأرقام عند التسجيل من جهازين معاً
    perform pg_advisory_xact_lock(hashtext(p_tenant::text));

    select coalesce(max(seq_no), 0) + 1 into v_next
      from public.transactions where tenant_id = p_tenant;

    v_desktop := exists (select 1 from public.tenant_devices d where d.tenant_id = p_tenant)
              or exists (select 1 from public.transactions x
                          where x.tenant_id = p_tenant and coalesce(x.device_id, '') <> '');

    if v_desktop then
        v_next := greatest(v_next, c_web_base);
    end if;
    return v_next;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) التحقق من رمز المزامنة — أساس أمان كل الدوال التالية
-- ----------------------------------------------------------------------------
-- القيمة الافتراضية مطابقة لتعريفه في 07/11: بدونها تفشل إعادة تشغيل التثبيت
-- بالخطأ «cannot remove parameter defaults from existing function»
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    select (sync_token = p_token and is_active and sync_enabled)
      into v_ok
      from public.tenants
     where id = p_tenant;

    if coalesce(v_ok, false) = false then
        -- رسالة واحدة مبهمة عمداً: لا نكشف إن كان المعرّف موجوداً أم لا
        raise exception 'رمز المزامنة غير صالح أو المزامنة موقوفة لهذا الحساب'
            using errcode = '28000';
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) رفع دفعة حركات من SQLite المحلية
--
--  الرفع idempotent بالكامل: المفتاح (tenant_id, seq_no) يقابل "رقم الفاتورة"
--  في قاعدة العميل، فإعادة رفع نفس الدفعة لا تُنشئ تكراراً بل تُحدّث فقط.
--  هذا ضروري لأن الشبكة قد تنقطع بعد الكتابة وقبل وصول الرد.
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_transactions(
    p_tenant  uuid,
    p_token   uuid,
    p_device  text,
    p_rows    jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.transactions (
        tenant_id, seq_no, txn_date, account_name, op_type,
        weight, weight_before, weight_after, note, status,
        trees_count, set_number, row_number, manual_no,
        source, device_id, synced_at
    )
    select
        p_tenant,
        (r ->> 'seq_no')::bigint,
        (r ->> 'txn_date')::timestamptz,
        coalesce(r ->> 'account_name', ''),
        coalesce(r ->> 'op_type', ''),
        coalesce((r ->> 'weight')::numeric, 0),
        coalesce((r ->> 'weight_before')::numeric, 0),
        coalesce((r ->> 'weight_after')::numeric, 0),
        coalesce(r ->> 'note', ''),
        coalesce((r ->> 'status')::public.txn_status, 'ACTIVE'),
        coalesce((r ->> 'trees_count')::numeric, 0),
        coalesce(r ->> 'set_number', ''),
        coalesce(r ->> 'row_number', ''),
        coalesce(r ->> 'manual_no', ''),
        'desktop',
        coalesce(p_device, ''),
        now()
      from jsonb_array_elements(p_rows) as r
     where (r ->> 'seq_no') is not null
       and (r ->> 'txn_date') is not null
    on conflict (tenant_id, seq_no) do update set
        txn_date      = excluded.txn_date,
        account_name  = excluded.account_name,
        op_type       = excluded.op_type,
        weight        = excluded.weight,
        weight_before = excluded.weight_before,
        weight_after  = excluded.weight_after,
        note          = excluded.note,
        status        = excluded.status,
        trees_count   = excluded.trees_count,
        set_number    = excluded.set_number,
        row_number    = excluded.row_number,
        manual_no     = excluded.manual_no,
        device_id     = excluded.device_id,
        synced_at     = now(),
        updated_at    = now();

    get diagnostics v_count = row_count;

    update public.tenants
       set last_sync_at = now(),
           last_seen    = now()
     where id = p_tenant;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) مزامنة الحذف
--
--  الحذف عند العميل حذف فعلي من SQLite، فنقابله هنا بحذف فعلي أيضاً حتى
--  تبقى نسخة السحابة مطابقة تماماً لما يراه العميل على شاشته.
-- ----------------------------------------------------------------------------
create or replace function public.sync_delete_transactions(
    p_tenant  uuid,
    p_token   uuid,
    p_seq_nos bigint[]
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_seq_nos is null or array_length(p_seq_nos, 1) is null then
        return 0;
    end if;

    delete from public.transactions
     where tenant_id = p_tenant
       and seq_no = any(p_seq_nos);

    get diagnostics v_count = row_count;

    update public.tenants set last_sync_at = now(), last_seen = now() where id = p_tenant;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) مزامنة شجرة الحسابات (الأسماء والأقسام)
--     الأقسام غير المعروفة تُحوَّل لـ (حسابات عامة) بدل رفض الدفعة كلها
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_accounts(
    p_tenant uuid,
    p_token  uuid,
    p_rows   jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.accounts (tenant_id, name, category, source)
    select
        p_tenant,
        r ->> 'name',
        case r ->> 'category'
            when 'المصنعين'      then 'المصنعين'
            when 'المركبين'      then 'المركبين'
            when 'الآلة/المكائن' then 'الآلة/المكائن'
            when 'الموردين'      then 'الموردين'
            when 'صناديق الخياس' then 'صناديق الخياس'
            else 'حسابات عامة'
        end::public.account_category,
        'desktop'
      from jsonb_array_elements(p_rows) as r
     where coalesce(btrim(r ->> 'name'), '') <> ''
    on conflict (tenant_id, name, category) do nothing;

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) نبضة الجهاز — تُظهر للمدير حالة كل عميل لحظياً
-- ----------------------------------------------------------------------------
create or replace function public.sync_heartbeat(
    p_tenant   uuid,
    p_token    uuid,
    p_device   text,
    p_name     text default '',
    p_version  text default '',
    p_pending  int  default 0,
    p_pushed   bigint default 0,
    p_error    text default null
)
returns void
language plpgsql security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);

    insert into public.tenant_devices
        (tenant_id, device_id, device_name, app_version, last_sync_at,
         pending_count, pushed_total, last_error)
    values
        (p_tenant, coalesce(p_device, 'unknown'), coalesce(p_name, ''), coalesce(p_version, ''),
         now(), coalesce(p_pending, 0), coalesce(p_pushed, 0), p_error)
    on conflict (tenant_id, device_id) do update set
        device_name   = excluded.device_name,
        app_version   = excluded.app_version,
        last_sync_at  = now(),
        pending_count = excluded.pending_count,
        pushed_total  = greatest(public.tenant_devices.pushed_total, excluded.pushed_total),
        last_error    = excluded.last_error;

    update public.tenants set last_seen = now() where id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  ٧) آخر رقم متسلسل موجود في السحابة — يستخدمه العميل لمعرفة من أين يكمل
-- ----------------------------------------------------------------------------
create or replace function public.sync_cloud_state(p_tenant uuid, p_token uuid)
returns table (max_seq bigint, total_rows bigint, last_sync timestamptz)
language plpgsql security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select coalesce(max(t.seq_no), 0), count(*),
               (select last_sync_at from public.tenants where id = p_tenant)
          from public.transactions t
         where t.tenant_id = p_tenant;
end $$;

-- ----------------------------------------------------------------------------
--  ٨) الصلاحيات — القاعدة الذهبية:
--     anon يستطيع استدعاء دوال المزامنة فقط، ولا يملك أي وصول مباشر للجداول
-- ----------------------------------------------------------------------------
revoke all on public.transactions    from anon;
revoke all on public.accounts        from anon;
revoke all on public.tenants         from anon;
revoke all on public.app_users       from anon;
revoke all on public.tenant_settings from anon;
revoke all on public.box_closings    from anon;
revoke all on public.audit_log       from anon;
revoke all on public.tenant_devices  from anon;

grant execute on function public.sync_push_transactions(uuid, uuid, text, jsonb) to anon, authenticated;
grant execute on function public.sync_delete_transactions(uuid, uuid, bigint[])  to anon, authenticated;
grant execute on function public.sync_push_accounts(uuid, uuid, jsonb)           to anon, authenticated;
grant execute on function public.sync_heartbeat(uuid, uuid, text, text, text, int, bigint, text) to anon, authenticated;
grant execute on function public.sync_cloud_state(uuid, uuid)                    to anon, authenticated;

-- assert_sync_token دالة داخلية — لا تُمنح لأحد
revoke all on function public.assert_sync_token(uuid, uuid) from public, anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٩) RLS لجدول الأجهزة (المدير يرى الكل، العميل يرى أجهزته)
-- ----------------------------------------------------------------------------
alter table public.tenant_devices enable row level security;

drop policy if exists devices_select on public.tenant_devices;
create policy devices_select on public.tenant_devices for select to authenticated
    using (public.has_tenant_access(tenant_id));

drop policy if exists devices_admin_write on public.tenant_devices;
create policy devices_admin_write on public.tenant_devices for all to authenticated
    using (public.is_admin()) with check (public.is_admin());

-- ----------------------------------------------------------------------------
--  ١٠) لوحة المدير: نظرة شاملة على العملاء وحالة مزامنتهم
-- ----------------------------------------------------------------------------
create or replace function public.admin_sync_overview()
returns table (
    tenant_id      uuid,
    business_name  text,
    is_active      boolean,
    can_edit       boolean,
    sync_enabled   boolean,
    last_sync_at   timestamptz,
    is_online      boolean,
    devices        int,
    pending_count  int,
    txn_count      bigint,
    last_txn_at    timestamptz,
    last_error     text
)
language sql stable security definer set search_path = public as $$
    select
        t.id,
        t.business_name,
        t.is_active,
        t.can_edit,
        t.sync_enabled,
        t.last_sync_at,
        (t.last_seen is not null and t.last_seen > now() - interval '3 minutes'),
        (select count(*)::int from public.tenant_devices d where d.tenant_id = t.id),
        (select coalesce(sum(d.pending_count), 0)::int from public.tenant_devices d where d.tenant_id = t.id),
        (select count(*) from public.transactions x where x.tenant_id = t.id),
        (select max(x.txn_date) from public.transactions x where x.tenant_id = t.id),
        (select d.last_error from public.tenant_devices d
          where d.tenant_id = t.id and d.last_error is not null
          order by d.last_sync_at desc limit 1)
      from public.tenants t
     where public.is_admin()
     order by t.business_name;
$$;

grant execute on function public.admin_sync_overview() to authenticated;

-- ----------------------------------------------------------------------------
--  ١١) إعادة توليد رمز المزامنة (للمدير) — يُبطل الرمز القديم فوراً
-- ----------------------------------------------------------------------------
create or replace function public.admin_rotate_sync_token(p_tenant uuid)
returns uuid
language plpgsql security definer set search_path = public as $$
declare
    v_new uuid;
begin
    if not public.is_admin() then
        raise exception 'هذه العملية للمدير العام فقط';
    end if;
    v_new := gen_random_uuid();
    update public.tenants set sync_token = v_new where id = p_tenant;
    return v_new;
end $$;

grant execute on function public.admin_rotate_sync_token(uuid) to authenticated;

-- ----------------------------------------------------------------------------
--  ١٢) تفعيل البث اللحظي (Realtime) على جدول الحركات
--      حتى تتحدّث شاشات المدير لحظة وصول أي حركة من أي عميل
-- ----------------------------------------------------------------------------
do $$
begin
    if not exists (
        select 1 from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = 'public'
           and tablename = 'transactions')
    then
        alter publication supabase_realtime add table public.transactions;
    end if;

    if not exists (
        select 1 from pg_publication_tables
         where pubname = 'supabase_realtime'
           and schemaname = 'public'
           and tablename = 'tenant_devices')
    then
        alter publication supabase_realtime add table public.tenant_devices;
    end if;
exception when others then
    raise notice 'تنبيه: فعّل Realtime يدوياً من Database → Replication (%).', sqlerrm;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  استخرج بيانات ربط برنامج العميل من هنا (انسخها في device_session.json)
-- ----------------------------------------------------------------------------
select
    t.business_name          as اسم_المصنع,
    t.id                     as tenant_id,
    t.sync_token             as sync_token,
    t.sync_enabled           as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;


-- ############################################################################
-- ##  المصدر: 07_auth_sync.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — الدخول بحساب Supabase والمزامنة العكسية (Sync Down)
--
--  التغيير الجوهري: برنامج سطح المكتب لم يعد يحمل أي رمز سرّي في ملف.
--  العميل يسجّل دخوله ببريده وكلمة مروره، فيحصل على JWT، وكل استدعاءاته
--  بعد ذلك تمرّ بـ RLS العادية — وهذا أقوى أماناً من ملف الجلسة السابق.
--
--  شغّل هذا الملف بعد 06_hybrid_sync.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) توسيع فحص صلاحية المزامنة ليقبل مصدرين:
--     (أ) رمز مزامنة سرّي  — للتوافق مع الأجهزة القديمة
--     (ب) جلسة مستخدم مسجّل الدخول — الطريقة الجديدة المعتمدة
-- ----------------------------------------------------------------------------
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    -- (ب) الأولوية للجلسة المسجّلة: المستخدم الداخل فعلياً بحسابه
    if auth.uid() is not null and public.has_tenant_access(p_tenant) then
        return;
    end if;

    -- (أ) وإلا نقبل رمز المزامنة السرّي
    if p_token is not null then
        select (sync_token = p_token and is_active and sync_enabled)
          into v_ok
          from public.tenants
         where id = p_tenant;

        if coalesce(v_ok, false) then
            return;
        end if;
    end if;

    raise exception 'غير مصرّح بالمزامنة لهذا الحساب' using errcode = '28000';
end $$;

-- ----------------------------------------------------------------------------
--  ٢) بيانات جلسة المستخدم بعد تسجيل الدخول
--     يرجعها البرنامج فور نجاح الدخول ليعرف: أي مصنع، وهل التعديل مفتوح
-- ----------------------------------------------------------------------------
create or replace function public.my_session()
returns table (
    user_id       uuid,
    tenant_id     uuid,
    business_name text,
    user_role     text,
    can_edit      boolean,
    is_active     boolean,
    sync_enabled  boolean
)
language sql stable security definer set search_path = public as $$
    select
        u.id,
        u.tenant_id,
        coalesce(t.business_name, 'المدير العام'),
        u.role::text,
        coalesce(t.can_edit, true),
        (u.is_active and coalesce(t.is_active, true)),
        coalesce(t.sync_enabled, true)
      from public.app_users u
      left join public.tenants t on t.id = u.tenant_id
     where u.id = auth.uid();
$$;

-- ----------------------------------------------------------------------------
--  ٣) سحب الحركات من السحابة إلى الجهاز (Sync Down)
--     مقسّم على دفعات بترتيب الرقم المتسلسل، فيعمل مع أي حجم بيانات
--     ولا يقطع الاتصال ولا يستهلك ذاكرة الجهاز.
-- ----------------------------------------------------------------------------
create or replace function public.sync_pull_transactions(
    p_tenant    uuid,
    p_after_seq bigint default 0,
    p_limit     int    default 1000
)
returns table (
    seq_no        bigint,
    txn_date      timestamptz,
    account_name  text,
    op_type       text,
    weight        numeric,
    weight_before numeric,
    weight_after  numeric,
    note          text,
    status        text,
    trees_count   numeric,
    set_number    text,
    row_number    text,
    manual_no     text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٤) سحب شجرة الحسابات (الأسماء والأقسام)
-- ----------------------------------------------------------------------------
create or replace function public.sync_pull_accounts(p_tenant uuid)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select a.name, a.category::text
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by a.category, a.name;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) ملخّص ما في السحابة — يستخدمه البرنامج لعرض شريط التقدّم
-- ----------------------------------------------------------------------------
create or replace function public.sync_cloud_summary(p_tenant uuid)
returns table (total_rows bigint, max_seq bigint, accounts_count bigint, last_sync timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, null);

    return query
        select
            (select count(*)          from public.transactions x where x.tenant_id = p_tenant),
            (select coalesce(max(x.seq_no), 0) from public.transactions x where x.tenant_id = p_tenant),
            (select count(*)          from public.accounts a where a.tenant_id = p_tenant),
            (select tn.last_sync_at   from public.tenants tn where tn.id = p_tenant);
end $$;

-- ----------------------------------------------------------------------------
--  ٦) الصلاحيات
--     دوال السحب للمستخدمين المسجّلين فقط — anon لا يستطيع قراءة أي شيء
-- ----------------------------------------------------------------------------
grant execute on function public.my_session()                            to authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int) to authenticated;
grant execute on function public.sync_pull_accounts(uuid)                to authenticated;
grant execute on function public.sync_cloud_summary(uuid)                to authenticated;

revoke execute on function public.sync_pull_transactions(uuid, bigint, int) from anon;
revoke execute on function public.sync_pull_accounts(uuid)                  from anon;
revoke execute on function public.sync_cloud_summary(uuid)                  from anon;

notify pgrst, 'reload schema';


-- ############################################################################
-- ##  المصدر: 08_client_login.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — دخول العميل بدون أي ملف جلسة على القرص
--
--  الفكرة: عند تسجيل الدخول يرجع الخادم كل ما يحتاجه البرنامج (معرّف المصنع
--  ورمز المزامنة) في استجابة واحدة، ويحتفظ البرنامج بها في الذاكرة فقط.
--  بإغلاق البرنامج تختفي — لا يبقى أي سر على القرص.
--
--  شغّل هذا الملف بعد 06_hybrid_sync.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  دخول العميل: يرجع بيانات المصنع + رمز المزامنة دفعة واحدة
--
--  متوافق مع حسابات العملاء الحالية في جدول clients (لا يحتاج ترحيلهم لـ auth).
--  يعمل بالتحقق من بصمة كلمة المرور نفسها المستخدمة في verify_client_login.
-- ----------------------------------------------------------------------------
create or replace function public.client_login_full(
    p_username      text,
    p_password_hash text
)
returns table (
    out_client_id     uuid,
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean
)
language plpgsql security definer set search_path = public as $$
begin
    return query
        select c.client_id, c.business_name, c.can_edit,
               t.sync_token, coalesce(t.sync_enabled, true)
          from public.clients c
          left join public.tenants t on t.id = c.client_id
         where lower(c.username) = lower(btrim(p_username))
           and c.password_hash = p_password_hash
           and c.is_active
         limit 1;

    -- تسجيل وقت الدخول ليظهر للمدير في لوحته
    update public.clients
       set last_login = now(), last_seen = now()
     where lower(username) = lower(btrim(p_username))
       and password_hash = p_password_hash;
exception when undefined_column or undefined_table then
    -- بيئة لا تحتوي جدول clients (تثبيت جديد يعتمد على auth فقط)
    return;
end $$;

grant execute on function public.client_login_full(text, text) to anon, authenticated;

-- ----------------------------------------------------------------------------
--  ضمان وجود صف tenants لكل عميل في clients
--  (العملاء القدامى أُنشئوا في clients قبل إضافة جدول tenants، فبدون هذا
--   لن يكون لهم رمز مزامنة ولن تُرفع بياناتهم)
-- ----------------------------------------------------------------------------
do $$
begin
    if to_regclass('public.clients') is not null then
        insert into public.tenants (id, business_name, is_active, can_edit)
        select c.client_id, c.business_name, c.is_active, c.can_edit
          from public.clients c
         where not exists (select 1 from public.tenants t where t.id = c.client_id)
        on conflict (id) do nothing;

        raise notice 'تمت مزامنة جدول tenants مع حسابات العملاء الحالية';
    end if;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: كل عميل يجب أن يظهر ومعه رمز مزامنة
-- ----------------------------------------------------------------------------
select t.business_name as المصنع,
       t.id            as tenant_id,
       (t.sync_token is not null) as له_رمز_مزامنة,
       t.sync_enabled  as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;


-- ############################################################################
-- ##  المصدر: 09_two_way_sync.sql
-- ############################################################################

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
-- التنظيف للمدير فقط (من SQL Editor أو بمفتاح الخدمة) — لا يُمنح للعملاء ولا لـ anon
revoke execute on function public.purge_sync_deletions() from public, anon, authenticated;
grant  execute on function public.purge_sync_deletions() to service_role;

-- سجل الحذف لا يُقرأ إلا عبر sync_pull_changes — لا وصول مباشر لـ anon
revoke all on public.sync_deletions from anon;

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


-- ############################################################################
-- ##  المصدر: 10_maintenance.sql
-- ############################################################################

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

    -- محاولات الدخول (تُنشأ في 11_fix_sync_permissions.sql) — أقدم من ٣٠ يوماً
    if to_regclass('public.login_attempts') is not null then
        return query execute
            'with d as (delete from public.login_attempts
                         where attempted_at < now() - interval ''30 days'' returning 1)
             select ''محاولات الدخول''::text, count(*)::int from d';
    end if;

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

-- الحذف والصيانة للمدير فقط (SQL Editor أو مفتاح الخدمة): دوال SECURITY DEFINER
-- بلا فحص داخلي، ولو بقيت متاحة لكان أي زائر بمفتاح anon يستطيع تشغيلها.
revoke execute on function public.purge_audit_log(int) from public, anon, authenticated;
revoke execute on function public.run_maintenance()    from public, anon, authenticated;
grant  execute on function public.purge_audit_log(int) to service_role;
grant  execute on function public.run_maintenance()    to service_role;

-- التقارير مفلترة داخلياً بـ is_admin()، فتبقى للمستخدمين المسجّلين فقط
revoke execute on function public.storage_report()  from public, anon;
revoke execute on function public.storage_summary() from public, anon;
grant  execute on function public.storage_report()  to authenticated;
grant  execute on function public.storage_summary() to authenticated;

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

        -- رقم الحركة للسياق فقط (لتعرف شاشة السجل أي حركة عُدّلت)
        if to_jsonb(new) ? 'seq_no' and not (v_new ? 'seq_no') then
            v_new := v_new || jsonb_build_object('seq_no', to_jsonb(new) -> 'seq_no');
        end if;
    end if;

    -- أسماء الأعمدة مطابقة لجدول audit_log في 01_schema.sql، ورقم السجل نصّي
    -- لأن id في transactions رقم (bigint) وليس uuid
    insert into public.audit_log (tenant_id, actor_id, action, table_name, record_id, before_data, after_data)
    values (
        v_tenant, auth.uid(), tg_op, tg_table_name,
        case when tg_op = 'DELETE' then to_jsonb(old) ->> 'id' else to_jsonb(new) ->> 'id' end,
        v_old, v_new
    );

    return case when tg_op = 'DELETE' then old else new end;
end $$;

-- تفعيل التدقيق المختصر فعلياً على الحركات (كان المحفّز ما زال على النسخة الكاملة)
-- أهم أثر: رفع برنامج سطح المكتب يعيد كتابة الصفوف دون تغيير حقيقي، فكانت كل
-- دورة رفع تضيف نسختين كاملتين لكل صف في السجل.
drop trigger if exists trg_txn_audit on public.transactions;
create trigger trg_txn_audit after insert or update or delete on public.transactions
    for each row execute function public.write_audit();

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تشغيل صيانة فورية + عرض المساحة الحالية
-- ----------------------------------------------------------------------------
select * from public.run_maintenance();
select * from public.storage_summary();


-- ############################################################################
-- ##  المصدر: 11_fix_sync_permissions.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — إصلاح خطأ المزامنة (28000: غير مصرّح بالمزامنة لهذا الحساب)
--
--  السبب الجذري:
--    كان ربط (clients.client_id ↔ tenants.id) يتم بسكربت ترحيل يعمل مرة واحدة
--    فقط. أي عميل أُضيف من لوحة الإدارة (سطح المكتب) بعد ذلك التاريخ لم يحصل
--    على صف tenants مطابق، فبقي بلا رمز مزامنة (sync_token = null)، فيرفض
--    assert_sync_token كل محاولة رفع من جهازه — ولنفس السبب تفشل محاولة
--    "انتحال الشخصية" من لوحة المدير، لأنها تقرأ نفس الرمز المفقود.
--
--  الحل: بدل الاعتماد على ترحيل لمرة واحدة، نجعل ربط الحساب بمزامنته
--  "ذاتي الإصلاح" — يُنفَّذ في كل مرة يُستخدم، لا مرة واحدة فقط:
--    ١) دخول العميل يضمن وجود الربط والرمز في نفس لحظة الدخول
--    ٢) انتحال شخصية المدير يضمن نفس الشيء قبل قراءة الرمز
--    ٣) مفتاح الخدمة (الذي تستخدمه شاشة المدير) يتجاوز فحص الرمز كلياً
--       كطبقة حماية إضافية، حتى لو تعذّر إصلاح الربط لأي سبب
--
--  شغّل هذا الملف بعد 10_maintenance.sql (وهو آمن لإعادة التشغيل)
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) is_service_role() — نُقلت إلى 02_rls.sql لأن has_tenant_access تعتمد عليها
-- ----------------------------------------------------------------------------

-- ----------------------------------------------------------------------------
--  ٢) الإصلاح الذاتي لربط الحساب بمزامنته
--
--  يُستدعى من: دخول العميل، وانتحال شخصية المدير — في كل مرة، لا لمرة واحدة.
--  لا يُنشئ بيانات وهمية: لو لم يكن الحساب موجوداً في tenants ولا في
--  clients القديم، يرجع بلا صفوف بهدوء.
-- ----------------------------------------------------------------------------
create or replace function public.ensure_tenant_link(p_client_id uuid)
returns table (
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean
)
language plpgsql security definer set search_path = public as $$
declare
    v_business text;
    v_can_edit boolean;
    v_active   boolean;
begin
    if p_client_id is null then
        return;
    end if;

    if exists (select 1 from public.tenants where id = p_client_id) then
        -- الصف موجود: نضمن فقط أن له رمز مزامنة صالحاً ومفعّلاً
        update public.tenants
           set sync_token   = coalesce(sync_token, gen_random_uuid()),
               sync_enabled = coalesce(sync_enabled, true)
         where id = p_client_id
           and (sync_token is null or sync_enabled is null);

    elsif to_regclass('public.clients') is not null then
        -- الصف غير موجود: ننشئه مطابقاً لحساب العميل القديم إن وُجد
        select c.business_name, c.can_edit, c.is_active
          into v_business, v_can_edit, v_active
          from public.clients c
         where c.client_id = p_client_id;

        if v_business is not null then
            insert into public.tenants (id, business_name, is_active, can_edit)
            values (p_client_id, v_business, coalesce(v_active, true), coalesce(v_can_edit, true))
            on conflict (id) do nothing;
        end if;
    end if;

    return query
        select t.business_name, coalesce(t.can_edit, true), t.sync_token, coalesce(t.sync_enabled, true)
          from public.tenants t
         where t.id = p_client_id;
end $$;

-- لا نمنحها لـ anon مباشرة (تمنع أي شخص من استكشاف بيانات حساب بمجرد تخمين
-- معرّفه)؛ العميل يصل إليها فقط بشكل غير مباشر عبر client_login_full أدناه،
-- والمدير يصل إليها مباشرة بمفتاح الخدمة.
--
-- ⚠️ كانت ممنوحة لـ authenticated، فكان أي مستخدم مسجّل (أي عميل) يستطيع قراءة
-- رمز مزامنة أي مصنع آخر بمعرّفه، ثم الكتابة في بياناته عبر دوال المزامنة.
revoke execute on function public.ensure_tenant_link(uuid) from public, anon, authenticated;
grant  execute on function public.ensure_tenant_link(uuid) to service_role;

-- ----------------------------------------------------------------------------
--  ٢-أ) سجل محاولات الدخول — يحدّ من تخمين كلمات المرور عبر client_login_full
--       (الدالة متاحة لـ anon لأن برنامج العميل يدخل بها قبل أي جلسة)
-- ----------------------------------------------------------------------------
create table if not exists public.login_attempts (
    id           bigserial primary key,
    username     text        not null,
    attempted_at timestamptz not null default now(),
    succeeded    boolean     not null default false
);

create index if not exists idx_login_attempts_user
    on public.login_attempts (lower(username), attempted_at desc);

alter table public.login_attempts enable row level security;
revoke all on public.login_attempts from anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٣) دخول العميل — الآن يستدعي الإصلاح الذاتي دائماً، لا الترحيل لمرة واحدة
--
--  إعادة الكتابة تفصل القراءة عن الكتابة الحسّاسة للأخطاء: التحقّق من بيانات
--  الدخول أولاً، ثم تحديث last_login في كتلة معزولة تتجاهل الأعمدة الناقصة
--  بهدوء، ثم الإرجاع في نهاية الدالة بلا أي معالج استثناءات حولها — فلا مجال
--  لأن يُبطل استثناء لاحق نتيجة تم إرجاعها مسبقاً.
-- ----------------------------------------------------------------------------
create or replace function public.client_login_full(
    p_username      text,
    p_password_hash text
)
returns table (
    out_client_id     uuid,
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean
)
language plpgsql security definer set search_path = public as $$
declare
    v_client_id uuid;
    v_business  text;
    v_can_edit  boolean;
    v_active    boolean;
    v_token     uuid;
    v_enabled   boolean;
    v_user      text := lower(btrim(coalesce(p_username, '')));
    v_fails     integer;
begin
    if to_regclass('public.clients') is null then
        return;   -- لا نظام عملاء قديم في هذه القاعدة
    end if;

    -- ١٠ محاولات فاشلة خلال ١٥ دقيقة توقف الاسم مؤقتاً. نرجع «بلا صفوف» (مثل
    -- كلمة مرور خاطئة) بدل رمي خطأ، حتى لا يلجأ البرنامج للدالة القديمة.
    select count(*) into v_fails
      from public.login_attempts
     where lower(username) = v_user
       and not succeeded
       and attempted_at > now() - interval '15 minutes';
    if v_fails >= 10 then
        return;
    end if;

    select c.client_id, c.business_name, c.can_edit, c.is_active
      into v_client_id, v_business, v_can_edit, v_active
      from public.clients c
     where lower(c.username) = v_user
       and c.password_hash = p_password_hash
     limit 1;

    if v_client_id is null or not coalesce(v_active, true) then
        insert into public.login_attempts (username, succeeded) values (v_user, false);
        return;   -- بيانات دخول خاطئة أو حساب موقوف: بلا صفوف
    end if;

    insert into public.login_attempts (username, succeeded) values (v_user, true);

    -- الإصلاح الذاتي: يضمن الربط والرمز بغض النظر عن كيف أو متى أُنشئ الحساب
    select e.out_sync_token, e.out_sync_enabled
      into v_token, v_enabled
      from public.ensure_tenant_link(v_client_id) e;

    -- تسجيل وقت الدخول، بمعزل تام عن مسار الإرجاع أدناه
    begin
        update public.clients
           set last_login = now(), last_seen = now()
         where client_id = v_client_id;
    exception when undefined_column then
        null;   -- نسخة قديمة من الجدول بلا هذين العمودين — لا يوقف الدخول
    end;

    return query
        select v_client_id, v_business, coalesce(v_can_edit, true), v_token, coalesce(v_enabled, true);
end $$;

grant execute on function public.client_login_full(text, text) to anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٤) فحص رمز المزامنة — مع تجاوز كامل لمفتاح الخدمة
--
--  مفتاح الخدمة تستخدمه شاشة "انتحال الشخصية" في لوحة المدير فقط (لا يُوزَّع
--  على العملاء إطلاقاً)، فتجاوزه هنا آمن ولا يفتح أي ثغرة للعملاء العاديين.
-- ----------------------------------------------------------------------------
create or replace function public.assert_sync_token(p_tenant uuid, p_token uuid default null)
returns void
language plpgsql security definer set search_path = public as $$
declare
    v_ok boolean;
begin
    -- (ج) مفتاح الخدمة (شاشة المدير) يتجاوز الفحص دائماً
    if public.is_service_role() then
        return;
    end if;

    -- (ب) جلسة مستخدم مسجّل الدخول عبر Supabase Auth وله صلاحية على هذا المصنع
    if auth.uid() is not null and public.has_tenant_access(p_tenant) then
        return;
    end if;

    -- (أ) رمز المزامنة السرّي — طريق أجهزة العملاء التي تستخدم تسجيل الدخول المخصّص
    if p_token is not null then
        select (sync_token = p_token and is_active and sync_enabled)
          into v_ok
          from public.tenants
         where id = p_tenant;

        if coalesce(v_ok, false) then
            return;
        end if;
    end if;

    raise exception 'غير مصرّح بالمزامنة لهذا الحساب' using errcode = '28000';
end $$;

-- ----------------------------------------------------------------------------
--  ٥) دالة تشخيص — شغّلها فوراً لمعرفة حالة أي عميل بدقة
-- ----------------------------------------------------------------------------
create or replace function public.diagnose_client_sync(p_username text)
returns table (
    الخطوة text,
    النتيجة text
)
language plpgsql security definer set search_path = public as $$
declare
    v_client_id uuid;
    v_has_clients boolean := to_regclass('public.clients') is not null;
begin
    return query select 'جدول clients موجود؟', case when v_has_clients then 'نعم' else 'لا — نظام Auth فقط' end;
    if not v_has_clients then
        return;
    end if;

    select c.client_id into v_client_id
      from public.clients c
     where lower(c.username) = lower(btrim(p_username));

    return query select 'الحساب موجود في clients؟',
        coalesce(v_client_id::text, 'لا — تحقق من اسم المستخدم');
    if v_client_id is null then
        return;
    end if;

    return query select 'الحساب مفعّل؟',
        (select case when is_active then 'نعم' else 'لا — موقوف' end from public.clients where client_id = v_client_id);

    return query select 'صف tenants مطابق موجود؟',
        case when exists (select 1 from public.tenants where id = v_client_id) then 'نعم' else 'لا (سيُنشأ تلقائياً عند أول دخول بعد هذا الإصلاح)' end;

    -- الرمز نفسه لا يُعرض أبداً — وجوده فقط
    return query select 'رمز المزامنة موجود؟',
        case when exists (select 1 from public.tenants
                           where id = v_client_id and sync_token is not null)
             then 'نعم' else 'لا' end;

    return query select 'المزامنة مفعّلة؟',
        coalesce((select case when sync_enabled then 'نعم' else 'لا — موقوفة يدوياً' end from public.tenants where id = v_client_id), 'لا يوجد صف بعد');

    return query select 'عدد الحركات في السحابة',
        (select count(*)::text from public.transactions where tenant_id = v_client_id);
end $$;

-- للتشخيص من SQL Editor أو بمفتاح الخدمة فقط — كانت تكشف بيانات أي عميل لأي مستخدم مسجّل
revoke execute on function public.diagnose_client_sync(text) from public, anon, authenticated;
grant  execute on function public.diagnose_client_sync(text) to service_role;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق فوري: كل عميل يجب أن يظهر الآن ومعه رمز مزامنة صالح
--  (هذا الاستعلام وحده لا يُصلح شيئاً — الإصلاح يحدث تلقائياً عند أول دخول
--   لكل عميل بعد تشغيل هذا الملف. لإصلاح الكل فوراً بلا انتظار دخولهم،
--   استخدم سطر الإصلاح الجماعي في نهاية هذا الملف)
-- ----------------------------------------------------------------------------
select t.business_name          as المصنع,
       t.id                     as tenant_id,
       (t.sync_token is not null) as له_رمز_مزامنة_الآن,
       t.sync_enabled           as المزامنة_مفعّلة
  from public.tenants t
 order by t.business_name;

-- ----------------------------------------------------------------------------
--  إصلاح جماعي فوري لكل العملاء الحاليين (لا تنتظر دخولهم التالي)
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_fixed int := 0;
begin
    if to_regclass('public.clients') is not null then
        for r in select client_id from public.clients loop
            perform public.ensure_tenant_link(r.client_id);
            v_fixed := v_fixed + 1;
        end loop;
    end if;
    raise notice '✅ تم فحص وإصلاح ربط % حساب عميل', v_fixed;
end $$;

select 'تم الإصلاح الجماعي — الحالة النهائية:' as ملاحظة;
select t.business_name as المصنع, (t.sync_token is not null) as له_رمز_الآن
  from public.tenants t order by t.business_name;


-- ############################################################################
-- ##  المصدر: 12_fix_pull_token.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — الإصلاح الجذري لخطأ 28000 عند سحب البيانات
--
--  السبب الحقيقي (بعد تتبّع الخطأ خطوة بخطوة):
--    دوال السحب الأربع (sync_cloud_summary / sync_pull_accounts /
--    sync_pull_transactions / sync_pull_changes) كانت تستدعي:
--        perform public.assert_sync_token(p_tenant, null);
--    أي تمرّر NULL كرمز مزامنة دائماً — فلا تنجح إلا لمستخدم مسجّل عبر
--    Supabase Auth (auth.uid() موجود) أو بمفتاح الخدمة.
--
--    لكن برنامج العميل يسجّل دخوله عبر جدول clients بمفتاح anon، فلا يوجد
--    auth.uid() إطلاقاً. النتيجة: كل محاولة سحب تفشل بـ 28000 مهما كان
--    رمز المزامنة صحيحاً — لأن الرمز لم يُمرَّر أصلاً.
--
--  الإصلاح: إضافة معامل p_token لكل دوال السحب وتمريره للفحص.
--  (المعامل اختياري وفي آخر القائمة، فالاستدعاءات القديمة تبقى صالحة)
--
--  شغّل هذا الملف بعد 11_fix_sync_permissions.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) ملخّص السحابة
-- ----------------------------------------------------------------------------
drop function if exists public.sync_cloud_summary(uuid);
drop function if exists public.sync_cloud_summary(uuid, uuid);

create or replace function public.sync_cloud_summary(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (total_rows bigint, max_seq bigint, accounts_count bigint, last_sync timestamptz)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select
            (select count(*)          from public.transactions x where x.tenant_id = p_tenant),
            (select coalesce(max(x.seq_no), 0) from public.transactions x where x.tenant_id = p_tenant),
            (select count(*)          from public.accounts a where a.tenant_id = p_tenant),
            (select tn.last_sync_at   from public.tenants tn where tn.id = p_tenant);
end $$;

-- ----------------------------------------------------------------------------
--  ٢) سحب شجرة الحسابات
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_accounts(uuid);
drop function if exists public.sync_pull_accounts(uuid, uuid);

create or replace function public.sync_pull_accounts(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select a.name, a.category::text
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by a.category, a.name;
end $$;

-- ----------------------------------------------------------------------------
--  ٣) سحب الحركات على دفعات
-- ----------------------------------------------------------------------------
-- تُحذف كل التوقيعات السابقة: تغيير نوع الإرجاع يرفضه
-- create or replace، فلا بد من الحذف أولاً
drop function if exists public.sync_pull_transactions(uuid, bigint, int);
drop function if exists public.sync_pull_transactions(uuid, bigint, int, uuid);

create or replace function public.sync_pull_transactions(
    p_tenant    uuid,
    p_after_seq bigint default 0,
    p_limit     int    default 1000,
    p_token     uuid   default null
)
returns table (
    seq_no        bigint,
    txn_date      timestamptz,
    account_name  text,
    op_type       text,
    weight        numeric,
    weight_before numeric,
    weight_after  numeric,
    note          text,
    status        text,
    trees_count   numeric,
    set_number    text,
    row_number    text,
    manual_no     text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٤) السحب التفاضلي (تعديلات لوحة المدير تصل للعميل)
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_changes(uuid, timestamptz, int);
drop function if exists public.sync_pull_changes(uuid, timestamptz, int, uuid);

create or replace function public.sync_pull_changes(
    p_tenant uuid,
    p_since  timestamptz default null,
    p_limit  int default 500,
    p_token  uuid default null
)
returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
    v_now     timestamptz := now();
    v_full    boolean := false;
    v_changed jsonb;
    v_deleted jsonb;
    v_more    boolean := false;
    v_count   int;
begin
    perform public.assert_sync_token(p_tenant, p_token);

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

-- ----------------------------------------------------------------------------
--  ٥) الصلاحيات — anon يحتاجها لأن برنامج العميل يعمل بمفتاح anon
--     (الأمان محفوظ: كل دالة تتحقق من رمز المزامنة السرّي قبل أي قراءة)
-- ----------------------------------------------------------------------------
grant execute on function public.sync_cloud_summary(uuid, uuid)                    to anon, authenticated;
grant execute on function public.sync_pull_accounts(uuid, uuid)                    to anon, authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int, uuid)   to anon, authenticated;
grant execute on function public.sync_pull_changes(uuid, timestamptz, int, uuid)   to anon, authenticated;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: جرّب السحب برمز عميل حقيقي — يجب أن يرجع صفاً بلا خطأ 28000
-- ----------------------------------------------------------------------------
do $$
declare
    r record;
    v_rows bigint;
begin
    for r in select id, business_name, sync_token from public.tenants
              where sync_token is not null limit 3
    loop
        select total_rows into v_rows
          from public.sync_cloud_summary(r.id, r.sync_token);
        raise notice '✅ % — السحب يعمل، عدد الحركات: %', r.business_name, v_rows;
    end loop;
end $$;

select 'تم إصلاح دوال السحب — جرّب تسجيل الدخول الآن' as النتيجة;


-- ############################################################################
-- ##  المصدر: 13_fix_admin_mirror.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — إصلاح عدم تطابق بيانات المدير مع العميل
--
--  ثلاثة أسباب جذرية اكتُشفت عند تتبّع الفروقات:
--
--  (١) عمود الفترة (period) لم يكن يُرفع ولا يُسحَب إطلاقاً.
--      العميل يخزّن الفترة صراحةً، أما المدير فكان يشتقّها من تاريخ الحركة —
--      فحركة تاريخها ٧/٣٠ ومثبّتة في فترة ٨ تظهر عند المدير في فترة ٧.
--      وهذا سبب ظهور ٣ فترات عند المدير مقابل فترتين عند العميل.
--
--  (٢) أقسام الحسابات كانت تُسحق: كل قسم خارج القائمة الثابتة الستة يتحوّل
--      إلى (حسابات عامة). فصناديق الخياس المضافة وأقسام مراحل التصنيع
--      تفقد قسمها الحقيقي، فلا تظهر عند المدير أصلاً.
--
--  (٣) حذف الأسماء لم يكن يُزامَن: الاسم المحذوف عند العميل يبقى عند المدير.
--
--  شغّل هذا الملف بعد 12_fix_pull_token.sql
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) عمود الفترة على الحركات
--
--  مهم: في المخطط الأصلي كان (period) عموداً **مُولَّداً** من التاريخ:
--      period text generated always as (to_char(txn_date,'YYYY-MM')) stored
--  والعمود المُولَّد لا يقبل الكتابة إطلاقاً، فيفشل الرفع بالخطأ:
--      column "period" can only be updated to DEFAULT
--  ولأن الفترة صارت قراراً محاسبياً مستقلاً عن التاريخ (العميل قد يعمل في
--  فترة ٨ ويسجّل بتاريخ ٩)، نحوّله إلى عمود عادي مع الاحتفاظ بقيمه الحالية.
-- ----------------------------------------------------------------------------
do $$
declare
    v_generated text;
begin
    select is_generated into v_generated
      from information_schema.columns
     where table_schema = 'public'
       and table_name  = 'transactions'
       and column_name = 'period';

    if v_generated is null then
        -- العمود غير موجود أصلاً
        alter table public.transactions add column period text default '';
        raise notice 'أُضيف عمود period';

    elsif v_generated = 'ALWAYS' then
        -- عمود مُولَّد: نفكّ التوليد فتبقى القيم المخزّنة كما هي ويصبح قابلاً للكتابة
        alter table public.transactions alter column period drop expression;
        raise notice 'حُوّل عمود period من مُولَّد إلى عادي (القيم محفوظة)';

    else
        raise notice 'عمود period عادي بالفعل — لا تغيير';
    end if;
end $$;

-- الحركات المرفوعة سابقاً: الفترة = شهر تاريخها (نفس اشتقاق النظام القديم)
update public.transactions
   set period = to_char(txn_date, 'YYYY-MM')
 where period is null or period = '';

-- ----------------------------------------------------------------------------
--  ٢) القسم الحقيقي للحساب كما هو عند العميل
--
--  نُبقي العمود القديم (category) للتوافق مع لوحة الويب، ونضيف عموداً نصياً
--  يحمل القسم حرفياً بلا أي تحويل — فلا تضيع الأقسام الديناميكية.
-- ----------------------------------------------------------------------------
alter table public.accounts
    add column if not exists category_raw text default '';

update public.accounts
   set category_raw = category::text
 where category_raw is null or category_raw = '';

-- ----------------------------------------------------------------------------
--  ٣) رفع الحركات مع فترتها
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_transactions(
    p_tenant  uuid,
    p_token   uuid,
    p_device  text,
    p_rows    jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.transactions (
        tenant_id, seq_no, txn_date, account_name, op_type,
        weight, weight_before, weight_after, note, status,
        trees_count, set_number, row_number, manual_no,
        period, source, device_id, synced_at
    )
    select
        p_tenant,
        (r ->> 'seq_no')::bigint,
        (r ->> 'txn_date')::timestamptz,
        coalesce(r ->> 'account_name', ''),
        coalesce(r ->> 'op_type', ''),
        coalesce((r ->> 'weight')::numeric, 0),
        coalesce((r ->> 'weight_before')::numeric, 0),
        coalesce((r ->> 'weight_after')::numeric, 0),
        coalesce(r ->> 'note', ''),
        coalesce((r ->> 'status')::public.txn_status, 'ACTIVE'),
        coalesce((r ->> 'trees_count')::numeric, 0),
        coalesce(r ->> 'set_number', ''),
        coalesce(r ->> 'row_number', ''),
        coalesce(r ->> 'manual_no', ''),
        -- الفترة كما أرسلها العميل، أو تُشتق من التاريخ لو غابت
        coalesce(nullif(r ->> 'period', ''), to_char((r ->> 'txn_date')::timestamptz, 'YYYY-MM')),
        'desktop',
        coalesce(p_device, ''),
        now()
      from (
             -- إزالة التكرار داخل الدفعة الواحدة:
             -- ON CONFLICT DO UPDATE يرفض تعديل الصف نفسه مرتين في أمر واحد
             -- (الخطأ 21000)، ويحدث لو حملت الدفعة رقمَي تسلسل متطابقين.
             -- نُبقي آخر نسخة لكل رقم تسلسل.
             select distinct on ((t.x ->> 'seq_no')) t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where (t.x ->> 'seq_no') is not null
                and (t.x ->> 'txn_date') is not null
              order by (t.x ->> 'seq_no'), t.ord desc
           ) as d(r)
    on conflict (tenant_id, seq_no) do update set
        txn_date      = excluded.txn_date,
        account_name  = excluded.account_name,
        op_type       = excluded.op_type,
        weight        = excluded.weight,
        weight_before = excluded.weight_before,
        weight_after  = excluded.weight_after,
        note          = excluded.note,
        status        = excluded.status,
        trees_count   = excluded.trees_count,
        set_number    = excluded.set_number,
        row_number    = excluded.row_number,
        manual_no     = excluded.manual_no,
        period        = excluded.period,
        device_id     = excluded.device_id,
        synced_at     = now(),
        updated_at    = now();

    get diagnostics v_count = row_count;

    update public.tenants
       set last_sync_at = now(), last_seen = now()
     where id = p_tenant;

    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) سحب الحركات مع فترتها
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_transactions(uuid, bigint, int);
drop function if exists public.sync_pull_transactions(uuid, bigint, int, uuid);

create or replace function public.sync_pull_transactions(
    p_tenant    uuid,
    p_after_seq bigint default 0,
    p_limit     int    default 1000,
    p_token     uuid   default null
)
returns table (
    seq_no        bigint,
    txn_date      timestamptz,
    account_name  text,
    op_type       text,
    weight        numeric,
    weight_before numeric,
    weight_after  numeric,
    note          text,
    status        text,
    trees_count   numeric,
    set_number    text,
    row_number    text,
    manual_no     text,
    period        text
)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select t.seq_no, t.txn_date, t.account_name, t.op_type,
               t.weight, t.weight_before, t.weight_after, t.note,
               t.status::text, t.trees_count, t.set_number, t.row_number, t.manual_no,
               coalesce(nullif(t.period, ''), to_char(t.txn_date, 'YYYY-MM'))
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.seq_no > coalesce(p_after_seq, 0)
         order by t.seq_no
         limit least(coalesce(p_limit, 1000), 5000);
end $$;

-- ----------------------------------------------------------------------------
--  ٥) رفع الحسابات بأقسامها الحقيقية
-- ----------------------------------------------------------------------------
create or replace function public.sync_push_accounts(
    p_tenant uuid,
    p_token  uuid,
    p_rows   jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    insert into public.accounts (tenant_id, name, category, category_raw, source)
    select
        p_tenant,
        r ->> 'name',
        -- العمود المُعدّد للتوافق مع لوحة الويب
        case r ->> 'category'
            when 'المصنعين'      then 'المصنعين'
            when 'المركبين'      then 'المركبين'
            when 'الآلة/المكائن' then 'الآلة/المكائن'
            when 'الموردين'      then 'الموردين'
            when 'صناديق الخياس' then 'صناديق الخياس'
            else 'حسابات عامة'
        end::public.account_category,
        -- والقسم الحقيقي حرفياً بلا تحويل — هذا ما يعتمده برنامج سطح المكتب
        coalesce(r ->> 'category', ''),
        'desktop'
      from (
             -- نفس السبب: اسم واحد بنفس القسم مرتين في الدفعة يُسبب 21000
             select distinct on ((t.x ->> 'name'), (t.x ->> 'category')) t.x
               from jsonb_array_elements(p_rows) with ordinality as t(x, ord)
              where coalesce(btrim(t.x ->> 'name'), '') <> ''
              order by (t.x ->> 'name'), (t.x ->> 'category'), t.ord desc
           ) as d(r)
    on conflict (tenant_id, name, category) do update set
        category_raw = excluded.category_raw,
        is_active    = true;

    get diagnostics v_count = row_count;
    return v_count;
end $$;

-- ----------------------------------------------------------------------------
--  ٦) سحب الحسابات بأقسامها الحقيقية
-- ----------------------------------------------------------------------------
drop function if exists public.sync_pull_accounts(uuid);
drop function if exists public.sync_pull_accounts(uuid, uuid);

create or replace function public.sync_pull_accounts(
    p_tenant uuid,
    p_token  uuid default null
)
returns table (name text, category text)
language plpgsql stable security definer set search_path = public as $$
begin
    perform public.assert_sync_token(p_tenant, p_token);
    return query
        select a.name,
               coalesce(nullif(a.category_raw, ''), a.category::text)
          from public.accounts a
         where a.tenant_id = p_tenant and a.is_active
         order by 2, 1;
end $$;

-- ----------------------------------------------------------------------------
--  ٧) مزامنة حذف الأسماء
--     بدونها يبقى الاسم المحذوف عند العميل ظاهراً عند المدير إلى الأبد
-- ----------------------------------------------------------------------------
create or replace function public.sync_delete_accounts(
    p_tenant uuid,
    p_token  uuid,
    p_rows   jsonb
)
returns integer
language plpgsql security definer set search_path = public as $$
declare
    v_count integer := 0;
begin
    perform public.assert_sync_token(p_tenant, p_token);

    if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
        return 0;
    end if;

    -- تعطيل لا حذف: يحفظ أثر الحساب في الحركات القديمة المرتبطة به
    update public.accounts a
       set is_active = false
      from jsonb_array_elements(p_rows) as r
     where a.tenant_id = p_tenant
       and a.name = (r ->> 'name')
       and coalesce(nullif(a.category_raw, ''), a.category::text) = coalesce(r ->> 'category', '');

    get diagnostics v_count = row_count;
    return v_count;
end $$;

grant execute on function public.sync_delete_accounts(uuid, uuid, jsonb) to anon, authenticated;
grant execute on function public.sync_pull_transactions(uuid, bigint, int, uuid) to anon, authenticated;
grant execute on function public.sync_pull_accounts(uuid, uuid) to anon, authenticated;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  تحقّق: الفترات والأقسام كما هي عند العميل
-- ----------------------------------------------------------------------------
select t.business_name as المصنع,
       x.period        as الفترة,
       count(*)        as الحركات
  from public.transactions x
  join public.tenants t on t.id = x.tenant_id
 group by t.business_name, x.period
 order by 1, 2;

select t.business_name as المصنع,
       coalesce(nullif(a.category_raw, ''), a.category::text) as القسم,
       count(*) as الحسابات
  from public.accounts a
  join public.tenants t on t.id = a.tenant_id
 where a.is_active
 group by 1, 2
 order by 1, 2;


-- ############################################################################
-- ##  المصدر: 14_security_hardening.sql
-- ############################################################################

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


-- ############################################################################
-- ##  المصدر: 15_period_ledger.sql
-- ############################################################################

-- ============================================================================
--  جاديت ERP — دفتر الخزينة للفترات (مطابق لبرنامج سطح المكتب حرفياً)
--
--  لماذا:
--   كان رصيد الخزينة في الويب لا يخصم خياس المصنعين والمركبين الفعلي، ولا يعرف
--   صناديق الخياس المضافة من البرنامج، وأسماء المسترجع فيه تختلف عن أسماء
--   البرنامج — فيختلف رقم الويب عن رقم البرنامج للفترة نفسها.
--
--  القواعد (نفس get_treasury_ledger في البرنامج):
--   • كل حركة تنتمي لفترتها (عمود period) أياً كان تاريخها.
--   • رصيد بداية كل فترة = رصيد نهاية الفترة التي قبلها بالضبط.
--   • الخياس الفعلي للمصنعين والمركبين يُخصم في فترته سواء أُقفل أم لا:
--     الإقفال قيد بين «حساب الخسائر» والصندوق لا يمسّ الخزينة.
--
--  شغّل هذا الملف بعد 14_security_hardening.sql (أو شغّل INSTALL_ALL.sql كاملاً).
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) أسماء المسترجع كما يكتبها برنامج سطح المكتب
--     (الويب كان يستخدم «مسترجع الكاستنج»، والبرنامج «مسترجع كاستنج» — فكان
--      الذهب العائد من صندوق الكاستنج لا يُخصم من خياسه في الويب)
-- ----------------------------------------------------------------------------
create or replace function public.khayas_boxes()
returns table (box_name text, madin_type text, qabd_type text, mustarja_name text)
language sql immutable as $$
    values
        ('الكاستنج',      'صرف كاستنج',     'قبض كاستنج',      'مسترجع كاستنج'),
        ('التلميع',       'صرف تلميع',      'قبض تلميع',       'مسترجع التلميع/البف'),
        ('التلميع/البف',  'صرف تلميع بف',   'قبض تلميع بف',    'مسترجع البوليش'),
        ('خياس الطقوم',   'خياس طقوم',      'قبض خياس طقوم',   'مسترجع خياس الطقوم');
$$;

-- كل الأسماء التي تُعدّ مسترجعاً لصندوق: اسم البرنامج، ثم الاسم القديم في الويب
-- (لحركات سُجّلت من الويب قبل التوحيد). «مسترجع التلميع/البف» القديم للبف لا
-- يُقبل لأنه في البرنامج مسترجع صندوق التلميع — والبرنامج هو المرجع.
create or replace function public.box_mustarja_names(p_box text)
returns text[]
language sql immutable as $$
    select case p_box
        when 'الكاستنج'     then array['مسترجع كاستنج', 'مسترجع الكاستنج']
        when 'التلميع'      then array['مسترجع التلميع/البف', 'مسترجع التلميع']
        when 'التلميع/البف' then array['مسترجع البوليش']
        when 'خياس الطقوم'  then array['مسترجع خياس الطقوم']
        else array['مسترجع ' || p_box]
    end;
$$;

-- الصناديق الثابتة + الصناديق التي أضافها العميل من البرنامج (أقسام_خياس_إضافية)
create or replace function public.tenant_khayas_boxes(p_tenant uuid)
returns table (box_name text, madin_type text, qabd_type text, mustarja_names text[])
language sql stable security definer set search_path = public as $$
    select k.box_name, k.madin_type, k.qabd_type, public.box_mustarja_names(k.box_name)
      from public.khayas_boxes() k
     where (select public.has_tenant_access(p_tenant))
    union
    select a.name, 'صرف ' || a.name, 'قبض ' || a.name, array['مسترجع ' || a.name]
      from public.accounts a
     where a.tenant_id = p_tenant
       and (select public.has_tenant_access(p_tenant))
       and a.category_raw = 'أقسام_خياس_إضافية'
       and a.name not in (select k2.box_name from public.khayas_boxes() k2);
$$;

-- ----------------------------------------------------------------------------
--  ٢) مجاميع صندوق خياس لفترة — يقبل كل أسماء المسترجع للصندوق
-- ----------------------------------------------------------------------------
create or replace function public.box_period_totals(p_tenant uuid, p_box text, p_period text)
returns table (madin numeric, daen numeric, khayas numeric)
language sql stable security definer set search_path = public as $$
    with cfg as (select * from public.khayas_boxes() where box_name = p_box),
    t as (
        select x.op_type, x.weight, x.account_name
          from public.transactions x
         where x.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and x.status in ('ACTIVE', 'SETTLED_INOUT')
           and x.period = p_period
    ),
    s as (
        select
            coalesce(sum(case when t.op_type = (select madin_type from cfg) then t.weight else 0 end), 0) as madin,
            coalesce(sum(case
                when t.op_type = (select qabd_type from cfg) then t.weight
                when t.op_type = any(public.inbound_types())
                     and t.account_name = any(public.box_mustarja_names(p_box)) then t.weight
                else 0 end), 0) as daen
          from t
    )
    select s.madin, s.daen, s.madin - s.daen from s;
$$;

-- ----------------------------------------------------------------------------
--  ٣) الخياس الفعلي لقسم (المصنعين/المركبين) في فترة
--     مطابق لـ calculate_single_ledger + get_actual_section_khayas في البرنامج:
--
--       لكل عامل:
--         المرجع ٧٥٠ = السلك الراجع × العيار بعد الفحص ÷ ٧٥٠ (إن وُجدا)
--         ذهب/باقي   = صرف − قبض − بوليش + ليز − مفنش٨ − مفنش٤   (المصنعين)
--                    = صرف − قبض + ليز                          (المركبين)
--         المسموح    = مفنش٨ × ٠٫٠٠٨ + مفنش٤ × ٠٫٠٠٤             (المصنعين)
--                    = قبض × ٠٫٠٠٨                              (المركبين)
--         الخياس     = المرجع − (ذهب/باقي − المسموح)
--       الخياس الفعلي للقسم = Σ ذهب/باقي − Σ المرجع − Σ الخياس الموجب فقط
--
--     الحركات ACTIVE فقط — مثل البرنامج (الإقفال القديم بالأرشفة يحوّلها SETTLED
--     ويسجّل «صرف خياس مقفل» بدلاً منها، فلا يُخصم الخياس مرتين).
-- ----------------------------------------------------------------------------
create or replace function public.section_actual_khayas(p_tenant uuid, p_section text, p_period text)
returns numeric
language sql stable security definer set search_path = public as $$
    with w as (
        select distinct a.name
          from public.accounts a
         where a.tenant_id = p_tenant
           and (select public.has_tenant_access(p_tenant))
           and coalesce(nullif(a.category_raw, ''), a.category::text) = p_section
    ),
    g as (
        select w.name,
               coalesce(sum(t.weight) filter (where t.op_type = 'صرف ذهب'), 0)         as sarf,
               coalesce(sum(t.weight) filter (where t.op_type = 'قبض ذهب'), 0)         as qabd,
               coalesce(sum(t.weight) filter (where t.op_type = 'الليز'), 0)           as laiz,
               coalesce(sum(t.weight) filter (where t.op_type = 'البوليش'), 0)         as polish,
               coalesce(sum(t.weight) filter (where t.op_type = 'المفنش ٨ بالالف'), 0) as m8,
               coalesce(sum(t.weight) filter (where t.op_type = 'المفنش ٤ بالالف'), 0) as m4,
               coalesce(sum(t.weight) filter (where t.op_type = 'السلك الراجع'), 0)    as wire,
               -- البرنامج يأخذ آخر عيار مسجّل في الفترة (لا مجموعاً)
               coalesce((array_agg(t.weight order by t.seq_no desc)
                         filter (where t.op_type = 'العيار بعد الفحص'))[1], 0)       as carat
          from w
          left join public.transactions t
                 on t.tenant_id = p_tenant
                and t.account_name = w.name
                and t.status = 'ACTIVE'
                and t.period = p_period
         group by w.name
    ),
    l as (
        select case when g.wire > 0 and g.carat > 0
                    then round(g.wire * g.carat / 750.0, 2) else 0 end               as marja,
               case when p_section = 'المركبين'
                    then round(g.sarf - g.qabd + g.laiz, 2)
                    else round(g.sarf - g.qabd - g.polish + g.laiz - g.m8 - g.m4, 2)
               end                                                                   as baqi,
               case when p_section = 'المركبين'
                    then round(g.qabd * 0.008, 2)
                    else round(g.m8 * 0.008, 2) + round(g.m4 * 0.004, 2)
               end                                                                   as allowance
          from g
    ),
    k as (
        select l.baqi, l.marja,
               round(l.marja - round(l.baqi - l.allowance, 2), 2) as khayas
          from l
    )
    select coalesce(round(sum(k.baqi) - sum(k.marja)
                          - coalesce(sum(k.khayas) filter (where k.khayas > 0), 0), 2), 0)
      from k;
$$;

-- ----------------------------------------------------------------------------
--  ٤) دفتر الخزينة لكل الفترات — مصدر واحد للتقرير الشهري ورصيد الخزينة
--
--     البنود (بإشاراتها، مثل treasury_bucket في البرنامج):
--       opening  رصيد افتتاحي / قيد افتتاحي                         (+)
--       inbound  وارد ذهب                                            (+)
--       sales    مبيعات ذهب / صادر ذهب                               (−)
--       boxes    صرف صناديق الخياس (−) وقبضها والمسترجع منها (+)
--       closed   صرف خياس مقفل (إقفال الأرشفة القديم)                (−)
--       journal  قيد يومي على «حساب الخزينة» (مدين + / دائن −)
--       workers  الخياس الفعلي للمصنعين والمركبين                   (−)
--
--     p_include_period: فترة تُعرض حتى لو خلت من الحركات (الفترة المفتوحة حالياً)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_period_ledger(
    p_tenant         uuid,
    p_include_period text default null
)
returns table (
    period text, carry numeric, opening numeric, inbound numeric, sales numeric,
    boxes numeric, closed numeric, journal numeric, workers numeric,
    net numeric, closing numeric
)
language plpgsql stable security definer set search_path = public as $$
#variable_conflict use_column
declare
    v_sarf text[];
    v_qabd text[];
    v_must text[];
begin
    -- لا صلاحية = لا صفوف (لا رسالة خطأ تكشف وجود المصنع)
    if not public.has_tenant_access(p_tenant) then
        return;
    end if;

    select coalesce(array_agg(b.madin_type), '{}'), coalesce(array_agg(b.qabd_type), '{}')
      into v_sarf, v_qabd
      from public.tenant_khayas_boxes(p_tenant) b;
    select coalesce(array_agg(distinct m.name), '{}')
      into v_must
      from public.tenant_khayas_boxes(p_tenant) b
     cross join lateral unnest(b.mustarja_names) as m(name);

    return query
    with c as (
        select t.period as p,
               case
                   when t.op_type = 'رصيد افتتاحي' then 'opening'
                   when t.op_type = 'وارد ذهب (عيار 18)' then
                       case when t.trees_count = 1 and t.note = 'قيد افتتاحي' then 'opening'
                            when t.account_name = any(v_must) then 'boxes'
                            else 'inbound' end
                   when t.op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس', 'صادر ذهب') then 'sales'
                   when t.op_type = 'صرف خياس مقفل' then 'closed'
                   when t.op_type = any(v_sarf) then 'boxes'
                   when t.op_type = any(v_qabd) then 'boxes'
                   when t.account_name = 'حساب الخزينة'
                        and t.op_type in ('قيد يومي مدين', 'قيد يومي دائن') then 'journal'
               end as bucket,
               case
                   when t.op_type in ('مبيعات ذهب', 'مبيعات ذهب مع الماس', 'صادر ذهب',
                                      'صرف خياس مقفل') then -t.weight
                   when t.op_type = 'وارد ذهب (عيار 18)' then t.weight
                   when t.op_type = any(v_sarf) then -t.weight
                   when t.op_type = 'قيد يومي دائن' then -t.weight
                   else t.weight
               end as amount
          from public.transactions t
         where t.tenant_id = p_tenant
           and t.status in ('ACTIVE', 'SETTLED_INOUT')
           and coalesce(t.period, '') <> ''
    ),
    periods as (
        select distinct c.p from c
        union
        select p_include_period where coalesce(p_include_period, '') ~ '^\d{4}-\d{2}$'
    ),
    s as (
        select pr.p,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'opening'), 0), 2) as s_opening,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'inbound'), 0), 2) as s_inbound,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'sales'), 0), 2)   as s_sales,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'boxes'), 0), 2)   as s_boxes,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'closed'), 0), 2)  as s_closed,
               round(coalesce(sum(c.amount) filter (where c.bucket = 'journal'), 0), 2) as s_journal,
               -round(public.section_actual_khayas(p_tenant, 'المصنعين', pr.p)
                      + public.section_actual_khayas(p_tenant, 'المركبين', pr.p), 2)  as s_workers
          from periods pr
          left join c on c.p = pr.p
         group by pr.p
    ),
    n as (
        select s.*,
               s.s_opening + s.s_inbound + s.s_sales + s.s_boxes
                 + s.s_closed + s.s_journal + s.s_workers as s_net
          from s
    )
    select n.p,
           coalesce(sum(n.s_net) over (order by n.p rows between unbounded preceding and 1 preceding), 0),
           n.s_opening, n.s_inbound, n.s_sales, n.s_boxes, n.s_closed, n.s_journal, n.s_workers,
           n.s_net,
           sum(n.s_net) over (order by n.p rows between unbounded preceding and current row)
      from n
     order by n.p;
end $$;

-- ----------------------------------------------------------------------------
--  ٥) رصيد الخزينة حتى نهاية فترة = رصيد نهايتها في الدفتر نفسه
--     (فلا يختلف رقم «رصيد الخزينة» عن آخر عمود في التقرير الشهري)
-- ----------------------------------------------------------------------------
create or replace function public.treasury_balance(p_tenant uuid, p_until_period text default null)
returns numeric
language sql stable security definer set search_path = public as $$
    select coalesce((
        select l.closing
          from public.treasury_period_ledger(p_tenant, p_until_period) l
         where p_until_period is null or l.period <= p_until_period
         order by l.period desc
         limit 1), 0);
$$;

-- ----------------------------------------------------------------------------
--  ٦) الصلاحيات: للمستخدمين المسجّلين فقط (كل دالة تتحقق من المصنع داخلياً)
-- ----------------------------------------------------------------------------
revoke execute on function public.khayas_boxes()                             from public, anon;
revoke execute on function public.box_mustarja_names(text)                   from public, anon;
revoke execute on function public.tenant_khayas_boxes(uuid)                  from public, anon;
revoke execute on function public.box_period_totals(uuid, text, text)        from public, anon;
revoke execute on function public.section_actual_khayas(uuid, text, text)    from public, anon;
revoke execute on function public.treasury_period_ledger(uuid, text)         from public, anon;
revoke execute on function public.treasury_balance(uuid, text)               from public, anon;

grant execute on function public.khayas_boxes()                              to authenticated;
grant execute on function public.box_mustarja_names(text)                    to authenticated;
grant execute on function public.tenant_khayas_boxes(uuid)                   to authenticated;
grant execute on function public.box_period_totals(uuid, text, text)         to authenticated;
grant execute on function public.section_actual_khayas(uuid, text, text)     to authenticated;
grant execute on function public.treasury_period_ledger(uuid, text)          to authenticated;
grant execute on function public.treasury_balance(uuid, text)                to authenticated;

notify pgrst, 'reload schema';


notify pgrst, 'reload schema';
select 'التثبيت اكتمل ✔' as الحالة;

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
do $$ begin
    create type public.txn_status as enum ('ACTIVE', 'SETTLED', 'SETTLED_INOUT');
exception when duplicate_object then null; end $$;

create table if not exists public.transactions (
    id              bigserial primary key,
    tenant_id       uuid not null references public.tenants(id) on delete cascade,

    -- رقم متسلسل داخل كل مستأجر (يقابل "رقم الفاتورة" في النظام القديم)
    seq_no          bigint not null,

    txn_date        timestamptz not null,
    -- شهر الحركة المحاسبي (YYYY-MM) — مُولَّد تلقائياً لعزل الفترات وتسريع الاستعلام
    period          text generated always as (to_char(txn_date, 'YYYY-MM')) stored,

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

-- ============================================================================
--  جاديت ERP — مدة اشتراك كل مصنع + عدد الأجهزة المسموح لكل حساب (الإصدار 1.68.0)
--
--  ما يضيفه:
--    ١) لكل حساب عميل (جدول clients):
--       • access_until : آخر لحظة يعمل فيها الحساب. فارغ = مفتوح بلا حد.
--                        بعدها لا يدخل البرنامج حتى يجدّده المدير.
--       • max_devices  : عدد الأجهزة المسموح أن يعمل عليها الحساب. فارغ = بلا حد.
--    ٢) سجل الأجهزة (client_devices): كل جهاز دخل الحساب — يراه المدير ويزيله.
--       الأجهزة المسموحة هي أقدمها تسجيلاً بقدر العدد المسموح: إن خفّض المدير العدد
--       توقّف الأحدث تلقائياً، وإزالة جهاز تفتح مكانه لجهاز آخر.
--    ٣) client_login_v2: دخول برنامج العميل 1.68.0 فما بعد — يتحقق من كلمة المرور ثم
--       من مدة الاشتراك ومن الجهاز، ويرجع السبب بوضوح (منتهي / الأجهزة مكتملة / موقوف).
--    ٤) client_access_check: فحص دوري خفيف أثناء العمل (برمز مزامنة العميل نفسه):
--       إن انتهت المدة أو أُزيل الجهاز يتوقّف البرنامج فوراً، ويعود حين يجدّد المدير.
--    ٥) client_login_full (الدخول القديم ≤ 1.67): يرفض الحساب المنتهي، والحساب الذي له حدّ
--       أجهزة (البرنامج القديم لا يعرّف جهازه) — فلا يُتجاوز الحد ببرنامج قديم.
--    ٦) access_status_report(): تقرير للمدير — لكل مصنع: الاشتراك، والأيام الباقية، والأجهزة.
--    ٧) حماية جدول العملاء: كان المفتاح العام (داخل برنامج العميل) يقرأ الجدول ويعدّله
--       مباشرة — أي أن العميل يستطيع تمديد اشتراكه أو رفع حدّ أجهزته بنفسه، ويقرأ بصمات
--       كلمات مرور كل الحسابات (والدخول يتم بالبصمة). الآن: المدير وحده (مفتاحه) يقرأ
--       ويعدّل، وبرنامج العميل يمر بالدوال أعلاه فقط. «آخر ظهور» يصل عبر الفحص الدوري.
--
--  الحسابات الحالية تبقى كما هي: مفتوحة بلا حد وبلا حد أجهزة، حتى يحدّد المدير غير ذلك
--  من لوحة المدير ← «⚙️ الاشتراك والأجهزة».
--
--  آمن لإعادة التشغيل. شغّله بعد الملفات السابقة (أو ضمن INSTALL_ALL.sql).
-- ============================================================================

-- ----------------------------------------------------------------------------
--  ١) عمودا المدة وعدد الأجهزة (جدول العملاء من النظام القديم — إن وُجد)
-- ----------------------------------------------------------------------------
do $$
begin
    if to_regclass('public.clients') is not null then
        execute 'alter table public.clients add column if not exists access_until timestamptz';
        execute 'alter table public.clients add column if not exists max_devices integer';
        if not exists (select 1 from pg_constraint
                        where conname = 'clients_max_devices_range'
                          and conrelid = 'public.clients'::regclass) then
            execute 'alter table public.clients add constraint clients_max_devices_range
                     check (max_devices is null or max_devices between 1 and 1000)';
        end if;
        execute $c$comment on column public.clients.access_until is
            'آخر لحظة يعمل فيها الحساب — فارغ: مفتوح بلا حد'$c$;
        execute $c$comment on column public.clients.max_devices is
            'عدد الأجهزة المسموح — فارغ: بلا حد'$c$;
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  ٢) سجل أجهزة كل حساب
-- ----------------------------------------------------------------------------
create table if not exists public.client_devices (
    client_id   uuid        not null,
    device_id   text        not null,
    device_name text,
    app_version text,
    first_seen  timestamptz not null default now(),
    last_seen   timestamptz not null default now(),
    primary key (client_id, device_id)
);

comment on table public.client_devices is
    'الأجهزة التي دخلت كل حساب عميل — المسموحة أقدمها تسجيلاً بقدر clients.max_devices';

-- لا يقرؤه ولا يكتبه إلا المدير (مفتاح الخدمة) ودوال الدخول أدناه
alter table public.client_devices enable row level security;
revoke all on public.client_devices from public, anon, authenticated;
grant  all on public.client_devices to service_role;

-- ----------------------------------------------------------------------------
--  ٣) التحقق من اسم المستخدم وكلمة المرور (داخلية — مع حدّ محاولات التخمين)
--     ترجع صفاً واحداً للحساب إن صحّت كلمة المرور، وإلا لا شيء (وتُسجَّل المحاولة الفاشلة)
-- ----------------------------------------------------------------------------
create or replace function public.client_password_check(
    p_username      text,
    p_password_hash text
)
returns table (
    out_client_id     uuid,
    out_business_name text,
    out_can_edit      boolean,
    out_is_active     boolean
)
language plpgsql security definer set search_path = public as $$
declare
    v_user  text := lower(btrim(coalesce(p_username, '')));
    v_fails integer;
    v_id    uuid;
    v_name  text;
    v_edit  boolean;
    v_act   boolean;
begin
    if to_regclass('public.clients') is null then
        return;   -- لا نظام عملاء قديم في هذه القاعدة
    end if;

    -- ١٠ محاولات فاشلة خلال ١٥ دقيقة توقف الاسم مؤقتاً — حتى مع كلمة المرور الصحيحة
    select count(*) into v_fails
      from public.login_attempts
     where lower(username) = v_user
       and not succeeded
       and attempted_at > now() - interval '15 minutes';
    if v_fails >= 10 then
        return;
    end if;

    select c.client_id, c.business_name, c.can_edit, c.is_active
      into v_id, v_name, v_edit, v_act
      from public.clients c
     where lower(c.username) = v_user
       and c.password_hash = p_password_hash
     limit 1;

    if v_id is null then
        insert into public.login_attempts (username, succeeded) values (v_user, false);
        return;
    end if;

    return query select v_id, v_name, coalesce(v_edit, true), coalesce(v_act, true);
end $$;

revoke execute on function public.client_password_check(text, text) from public, anon, authenticated;
grant  execute on function public.client_password_check(text, text) to service_role;

-- ----------------------------------------------------------------------------
--  ٤) البوابة: حالة الحساب على هذا الجهاز (داخلية)
--
--  out_status:
--    ok              يعمل
--    inactive        الحساب موقوف (is_active = false)
--    expired         انتهت مدة الاشتراك (access_until مضى)
--    device_limit    الأجهزة المسموحة مكتملة بأجهزة أقدم
--    device_removed  (الفحص الدوري) أزال المدير هذا الجهاز — يلزم دخول جديد
--    update_required برنامج لا يعرّف جهازه والحساب له حدّ أجهزة
--    unknown         لا حساب بهذا المعرّف
--
--  p_register: الدخول يسجّل الجهاز الجديد إن كان له مكان؛ الفحص الدوري لا يسجّل.
-- ----------------------------------------------------------------------------
create or replace function public.client_access_gate(
    p_client_id   uuid,
    p_device_id   text,
    p_device_name text,
    p_app_version text,
    p_register    boolean
)
returns table (
    out_status       text,
    out_access_until timestamptz,
    out_max_devices  integer,
    out_devices_used integer
)
language plpgsql security definer set search_path = public as $$
declare
    v_active boolean;
    v_until  timestamptz;
    v_max    integer;
    v_found  boolean;
    v_dev    text := left(nullif(btrim(coalesce(p_device_id, '')), ''), 128);
    v_name   text := left(nullif(btrim(coalesce(p_device_name, '')), ''), 120);
    v_ver    text := left(nullif(btrim(coalesce(p_app_version, '')), ''), 32);
    v_first  timestamptz;
    v_rank   integer;
    v_used   integer;
    v_status text;
begin
    if to_regclass('public.clients') is null or p_client_id is null then
        return query select 'unknown'::text, null::timestamptz, null::integer, 0;
        return;
    end if;

    begin
        select c.is_active, c.access_until, c.max_devices, true
          into v_active, v_until, v_max, v_found
          from public.clients c
         where c.client_id = p_client_id;
    exception when undefined_column then
        -- جدول عملاء أُنشئ بعد تشغيل هذا الملف (بلا العمودين): مفتوح بلا حد حتى يُعاد تشغيله
        select c.is_active, null::timestamptz, null::integer, true
          into v_active, v_until, v_max, v_found
          from public.clients c
         where c.client_id = p_client_id;
    end;

    if not coalesce(v_found, false) then
        return query select 'unknown'::text, null::timestamptz, null::integer, 0;
        return;
    end if;

    if v_max is not null and v_max <= 0 then
        v_max := null;
    end if;

    -- دخولان متزامنان لحساب واحد لا يتجاوزان الحد معاً
    perform pg_advisory_xact_lock(hashtext('jadeite_client_devices:' || p_client_id::text));

    if not coalesce(v_active, true) then
        v_status := 'inactive';
    elsif v_until is not null and now() >= v_until then
        v_status := 'expired';
    elsif v_dev is null then
        v_status := case when v_max is null then 'ok' else 'update_required' end;
    else
        select d.first_seen into v_first
          from public.client_devices d
         where d.client_id = p_client_id and d.device_id = v_dev;

        if found then
            select count(*) into v_rank
              from public.client_devices d
             where d.client_id = p_client_id
               and (d.first_seen, d.device_id) <= (v_first, v_dev);
            if v_max is not null and v_rank > v_max then
                v_status := 'device_limit';
            else
                v_status := 'ok';
                update public.client_devices
                   set last_seen   = now(),
                       device_name = coalesce(v_name, device_name),
                       app_version = coalesce(v_ver, app_version)
                 where client_id = p_client_id and device_id = v_dev;
            end if;
        elsif not coalesce(p_register, false) then
            v_status := 'device_removed';
        else
            select count(*) into v_used from public.client_devices d where d.client_id = p_client_id;
            if v_max is not null and v_used >= v_max then
                v_status := 'device_limit';
            else
                v_status := 'ok';
                insert into public.client_devices (client_id, device_id, device_name, app_version)
                values (p_client_id, v_dev, v_name, v_ver)
                on conflict (client_id, device_id) do update set last_seen = now();
            end if;
        end if;
    end if;

    select count(*) into v_used from public.client_devices d where d.client_id = p_client_id;
    return query select v_status, v_until, v_max, v_used;
end $$;

revoke execute on function public.client_access_gate(uuid, text, text, text, boolean) from public, anon, authenticated;
grant  execute on function public.client_access_gate(uuid, text, text, text, boolean) to service_role;

-- ----------------------------------------------------------------------------
--  ٥) دخول برنامج العميل (1.68.0 فما بعد): كلمة المرور ← المدة ← الجهاز
--     كلمة مرور خاطئة: بلا صفوف (كما كان). صحيحة: صف واحد فيه السبب في out_status،
--     ورمز المزامنة لا يُعطى إلا إن كان «ok».
-- ----------------------------------------------------------------------------
create or replace function public.client_login_v2(
    p_username      text,
    p_password_hash text,
    p_device_id     text default null,
    p_device_name   text default null,
    p_app_version   text default null
)
returns table (
    out_client_id     uuid,
    out_business_name text,
    out_can_edit      boolean,
    out_sync_token    uuid,
    out_sync_enabled  boolean,
    out_status        text,
    out_access_until  timestamptz,
    out_max_devices   integer,
    out_devices_used  integer
)
language plpgsql security definer set search_path = public as $$
declare
    v_user   text := lower(btrim(coalesce(p_username, '')));
    v_id     uuid;
    v_name   text;
    v_edit   boolean;
    v_status text;
    v_until  timestamptz;
    v_max    integer;
    v_used   integer;
    v_token  uuid;
    v_on     boolean;
begin
    select a.out_client_id, a.out_business_name, a.out_can_edit
      into v_id, v_name, v_edit
      from public.client_password_check(p_username, p_password_hash) a;
    if v_id is null then
        return;   -- بيانات دخول خاطئة (أو محاولات كثيرة): بلا صفوف
    end if;

    select g.out_status, g.out_access_until, g.out_max_devices, g.out_devices_used
      into v_status, v_until, v_max, v_used
      from public.client_access_gate(v_id, p_device_id, p_device_name, p_app_version, true) g;

    if v_status <> 'ok' then
        -- كلمة المرور صحيحة لكن الحساب لا يعمل الآن: السبب فقط، بلا معرّف ولا رمز
        return query select null::uuid, v_name, false, null::uuid, false, v_status, v_until, v_max, v_used;
        return;
    end if;

    insert into public.login_attempts (username, succeeded) values (v_user, true);

    select e.out_sync_token, e.out_sync_enabled
      into v_token, v_on
      from public.ensure_tenant_link(v_id) e;

    begin
        update public.clients
           set last_login = now(), last_seen = now()
         where client_id = v_id;
    exception when undefined_column then
        null;   -- نسخة قديمة من الجدول بلا هذين العمودين — لا يوقف الدخول
    end;

    return query select v_id, v_name, v_edit, v_token, coalesce(v_on, true), v_status, v_until, v_max, v_used;
end $$;

revoke all on function public.client_login_v2(text, text, text, text, text) from public;
grant execute on function public.client_login_v2(text, text, text, text, text) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  ٦) الدخول القديم (برامج ≤ 1.67 تستدعيه): نفسه، مع رفض الحساب المنتهي والحساب
--     الذي له حدّ أجهزة — البرنامج القديم لا يعرّف جهازه فلا يُتجاوز الحد به
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
    v_user   text := lower(btrim(coalesce(p_username, '')));
    v_id     uuid;
    v_name   text;
    v_edit   boolean;
    v_status text;
    v_token  uuid;
    v_on     boolean;
begin
    select a.out_client_id, a.out_business_name, a.out_can_edit
      into v_id, v_name, v_edit
      from public.client_password_check(p_username, p_password_hash) a;
    if v_id is null then
        return;
    end if;

    select g.out_status into v_status
      from public.client_access_gate(v_id, null, null, null, false) g;
    if v_status <> 'ok' then
        return;   -- موقوف / منتهي / له حدّ أجهزة: البرنامج القديم يعرضها «بيانات غير صحيحة»
    end if;

    insert into public.login_attempts (username, succeeded) values (v_user, true);

    select e.out_sync_token, e.out_sync_enabled
      into v_token, v_on
      from public.ensure_tenant_link(v_id) e;

    begin
        update public.clients
           set last_login = now(), last_seen = now()
         where client_id = v_id;
    exception when undefined_column then
        null;
    end;

    return query select v_id, v_name, v_edit, v_token, coalesce(v_on, true);
end $$;

grant execute on function public.client_login_full(text, text) to anon, authenticated;

-- ----------------------------------------------------------------------------
--  ٧) الفحص الدوري أثناء العمل (كل ٣٠ ثانية): برمز مزامنة الحساب نفسه فقط.
--     يرجع الحالة وصلاحية التعديل ونهاية المدة معاً (طلب واحد خفيف).
-- ----------------------------------------------------------------------------
create or replace function public.client_access_check(
    p_client_id  uuid,
    p_sync_token uuid,
    p_device_id  text default null
)
returns table (
    out_status       text,
    out_can_edit     boolean,
    out_access_until timestamptz,
    out_max_devices  integer,
    out_devices_used integer
)
language plpgsql security definer set search_path = public as $$
declare
    v_edit boolean;
begin
    if p_client_id is null or p_sync_token is null or not exists (
            select 1 from public.tenants t where t.id = p_client_id and t.sync_token = p_sync_token) then
        return query select 'unauthorized'::text, null::boolean, null::timestamptz, null::integer, null::integer;
        return;
    end if;

    if to_regclass('public.clients') is not null then
        select coalesce(c.can_edit, true) into v_edit from public.clients c where c.client_id = p_client_id;
        -- «آخر ظهور» للوحة المدير (كان البرنامج يكتبه في الجدول مباشرة بالمفتاح العام)
        begin
            update public.clients set last_seen = now() where client_id = p_client_id;
        exception when undefined_column then
            null;
        end;
    end if;

    return query
        select g.out_status, coalesce(v_edit, true), g.out_access_until, g.out_max_devices, g.out_devices_used
          from public.client_access_gate(p_client_id, p_device_id, null, null, false) g;
end $$;

revoke all on function public.client_access_check(uuid, uuid, text) from public;
grant execute on function public.client_access_check(uuid, uuid, text) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  ٨) تقرير الاشتراكات والأجهزة (للمدير وحده — SQL Editor أو مفتاحه)
-- ----------------------------------------------------------------------------
create or replace function public.access_status_report()
returns table (المصنع text, المستخدم text, الاشتراك text, الأيام_الباقية text, الأجهزة text)
language plpgsql security definer set search_path = public as $$
begin
    if to_regclass('public.clients') is null then
        return;
    end if;
    return query
        select c.business_name::text,
               c.username::text,
               case when not coalesce(c.is_active, true) then '⛔ موقوف'
                    when c.access_until is null then '♾️ مفتوح بلا حد'
                    when c.access_until <= now() then '⛔ منتهي منذ '
                         || to_char(c.access_until at time zone 'Asia/Riyadh', 'YYYY-MM-DD')
                    else '✔ حتى ' || to_char(c.access_until at time zone 'Asia/Riyadh', 'YYYY-MM-DD')
               end,
               case when c.access_until is null then '—'
                    when c.access_until <= now() then '0'
                    else ceil(extract(epoch from c.access_until - now()) / 86400)::int::text
               end,
               (select count(*) from public.client_devices d where d.client_id = c.client_id)::text
               || ' من ' || coalesce(c.max_devices::text, 'بلا حد')
          from public.clients c
         order by 1;
end $$;

revoke all on function public.access_status_report() from public, anon, authenticated;
grant execute on function public.access_status_report() to service_role;

-- ----------------------------------------------------------------------------
--  ٩) جدول العملاء للمدير وحده: لا قراءة ولا كتابة بالمفتاح العام
--     (الدخول والفحص الدوري دوال SECURITY DEFINER أعلاه — لا تحتاج صلاحية على الجدول)
-- ----------------------------------------------------------------------------
do $$
begin
    if to_regclass('public.clients') is not null then
        execute 'revoke all on public.clients from anon, authenticated';
        execute 'grant all on public.clients to service_role';
    end if;
end $$;

notify pgrst, 'reload schema';

-- ----------------------------------------------------------------------------
--  التقرير الآن: الحسابات الحالية كلها «مفتوح بلا حد» حتى تحدّد غير ذلك من لوحة المدير
-- ----------------------------------------------------------------------------
select * from public.access_status_report();

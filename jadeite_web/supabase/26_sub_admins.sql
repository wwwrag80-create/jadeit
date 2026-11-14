-- ============================================================================
--  جاديت ERP — المدراء الفرعيون (الإصدار 1.98)
--
--  المدير الفرعي يدخل برنامج المدير بصلاحيةٍ محدودة (فتح حسابات العملاء وحده). جدوله ودالة دخوله كانا في قاعدة
--  Supabase وحدها لا في ملفات المشروع — فلم يكن معروفاً كيف تُحفظ كلمات مرورهم ولا كيف يُتحقق منها. الآن هنا:
--    ١) sub_admins: الاسم (فريد بلا اعتبار لحالة الحروف) وكلمة المرور bcrypt — للمدير وحده (مفتاح الخدمة).
--    ٢) مشغّل: بصمة SHA-256 التي يرسلها برنامج المدير عند الإنشاء تُحفظ bcrypt (كحسابات العملاء — 25).
--    ٣) تحويل الموجود في مكانه — فلا يغيّر أحدٌ كلمة مروره.
--    ٤) verify_sub_admin_login(الاسم، البصمة) ← صح/خطأ: بحدّ محاولات (١٠ خلال ١٥ دقيقة)، والمخزَّن لا يفتح.
--
--  يحتاج 25_password_hardening.sql قبله (password_matches). آمن لإعادة التشغيل. ضمن INSTALL_ALL.sql.
-- ============================================================================

create extension if not exists "pgcrypto";

do $$
begin
    if to_regprocedure('public.password_matches(text,text)') is null then
        raise exception 'شغّل 25_password_hardening.sql أولاً (password_matches)';
    end if;
end $$;

create table if not exists public.sub_admins (
    id            uuid primary key default gen_random_uuid(),
    username      text not null,
    password_hash text not null,
    created_at    timestamptz not null default now()
);
alter table public.sub_admins add column if not exists created_at timestamptz not null default now();

-- الاسم فريد بلا اعتبار لحالة الحروف (إن كانت فيه أسماء مكررة قديمة يبقى الجدول كما هو — تُرى في لوحة المدير)
do $$
begin
    if not exists (select 1 from pg_indexes where schemaname = 'public' and indexname = 'sub_admins_username_lower') then
        begin
            execute 'create unique index sub_admins_username_lower on public.sub_admins (lower(btrim(username)))';
        exception when unique_violation then
            raise notice 'أسماء مدراء فرعيين مكررة — الفهرس الفريد لم يُنشأ';
        end;
    end if;
end $$;

comment on table public.sub_admins is
    'المدراء الفرعيون (برنامج المدير بصلاحية فتح حسابات العملاء وحدها) — كلمة المرور bcrypt، للمدير وحده';

alter table public.sub_admins enable row level security;
revoke all on public.sub_admins from public, anon, authenticated;
grant all on public.sub_admins to service_role;

-- ----------------------------------------------------------------------------
--  ٢) و٣) bcrypt عند الحفظ، وتحويل الموجود
-- ----------------------------------------------------------------------------
create or replace function public.sub_admins_hash_password()
returns trigger
language plpgsql set search_path = public, extensions as $$
begin
    if new.password_hash ~ '^[0-9a-f]{64}$' then
        new.password_hash := crypt(new.password_hash, gen_salt('bf', 8));
    end if;
    return new;
end $$;

revoke all on function public.sub_admins_hash_password() from public, anon, authenticated;

drop trigger if exists sub_admins_hash_password on public.sub_admins;
create trigger sub_admins_hash_password before insert or update of password_hash on public.sub_admins
    for each row execute function public.sub_admins_hash_password();

update public.sub_admins set password_hash = password_hash where password_hash ~ '^[0-9a-f]{64}$';

-- ----------------------------------------------------------------------------
--  ٤) دخول المدير الفرعي: صح أو خطأ — بحدّ محاولات التخمين
-- ----------------------------------------------------------------------------
drop function if exists public.verify_sub_admin_login(text, text);
create function public.verify_sub_admin_login(p_username text, p_password_hash text)
returns boolean
language plpgsql security definer set search_path = public as $$
declare
    v_user   text := lower(btrim(coalesce(p_username, '')));
    v_key    text;
    v_fails  integer;
    v_stored text;
begin
    if v_user = '' then
        return false;
    end if;
    v_key := 'subadmin:' || v_user;           -- في سجل المحاولات نفسه، منفصلاً عن أسماء العملاء
    if to_regclass('public.login_attempts') is not null then
        select count(*) into v_fails
          from public.login_attempts
         where lower(username) = v_key
           and not succeeded
           and attempted_at > now() - interval '15 minutes';
        if v_fails >= 10 then
            return false;
        end if;
    end if;

    select s.password_hash into v_stored
      from public.sub_admins s
     where lower(btrim(s.username)) = v_user
     limit 1;

    if v_stored is null or not public.password_matches(v_stored, p_password_hash) then
        if to_regclass('public.login_attempts') is not null then
            insert into public.login_attempts (username, succeeded) values (v_key, false);
        end if;
        return false;
    end if;
    if to_regclass('public.login_attempts') is not null then
        insert into public.login_attempts (username, succeeded) values (v_key, true);
    end if;
    return true;
end $$;

revoke all on function public.verify_sub_admin_login(text, text) from public;
grant execute on function public.verify_sub_admin_login(text, text) to anon, authenticated, service_role;

-- ============================================================================
--  محاكاة بيئة Supabase داخل PostgreSQL عادي — للاختبار المحلي و CI فقط.
--  لا تشغّل هذا الملف على مشروع Supabase حقيقي.
--
--  يُنشئ: الأدوار (anon/authenticated/service_role)، مخطط auth بجدول users
--  ودالة auth.uid()، ونشرة supabase_realtime، والصلاحيات الافتراضية نفسها
--  التي يضبطها Supabase على مخطط public.
-- ============================================================================
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin bypassrls;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
        create role supabase_auth_admin nologin;
    end if;
end $$;

create schema if not exists auth;
grant usage on schema auth to anon, authenticated, service_role;

create table if not exists auth.users (
    id    uuid primary key default gen_random_uuid(),
    email text
);

-- مطابقة لتعريف Supabase: المعرّف يأتي من مطالبات JWT التي يضبطها PostgREST
create or replace function auth.uid() returns uuid
language sql stable as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.sub', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
    )::uuid
$$;

create or replace function auth.role() returns text
language sql stable as $$
    select coalesce(
        nullif(current_setting('request.jwt.claim.role', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
    )::text
$$;

grant execute on function auth.uid()  to anon, authenticated, service_role;
grant execute on function auth.role() to anon, authenticated, service_role;

do $$
begin
    if not exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
        create publication supabase_realtime;
    end if;
end $$;

-- الصلاحيات الافتراضية في Supabase: كل جدول/دالة جديدة في public متاحة
-- للأدوار الثلاثة، والحماية الفعلية تأتي من RLS ومن revoke الصريح.
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables    to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;

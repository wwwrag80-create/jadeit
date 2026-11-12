-- ============================================================================
--  جاديت ERP — رابط المدير المباشر يظهر في برنامج المدير وحده (الإصدار 1.96.0)
--
--  الرابط = عنوان جهاز المصنع (في وسيط الرابط: Tailscale أو Cloudflare) + مفتاحٌ سري.
--    • المفتاح يُنشئه برنامج المدير ويبقى على جهاز المدير وحده — لا يصل جهاز المصنع ولا السحابة أبداً.
--    • جهاز المصنع يأخذ «بصمة» المفتاح فقط (SHA-256) ليتحقق بها ممن يفتح الرابط: البصمة لا تُعيد
--      المفتاح، فلا يستطيع أحدٌ على جهاز المصنع معرفة الرابط ولا تكوينه.
--    • جهاز المصنع يرسل عنوانه (بلا مفتاح — لا يفتح شيئاً وحده) ليجده برنامج المدير.
--  فهذه «صلاحيةٌ» من صلاحيات الحساب: لا بيانات، ولا نسخ، ولا الرابط نفسه.
--
--  ما يضيفه:
--    ١) clients.live_key_hash    : بصمة مفتاح المدير لكل حساب (يكتبها المدير بمفتاحه).
--    ٢) client_devices.live_url  : عنوان كل جهاز في وسيط الرابط ووقت تحديثه.
--    ٣) client_live_sync(…)      : برنامج العميل برمز مزامنته — يحفظ عنوان جهازه ويأخذ البصمة،
--                                  للحساب الفعّال والجهاز المسموح وحدهما.
--    ٤) (1.96.1) client_devices.live_state: حال الرابط على جهاز المصنع كما يفحصه هو — يراه المدير
--       في «🩺 فحص» فيعرف أين توقف الضبط دون أن يكون عند الجهاز. والنسخة الخماسية من الدالة ترسله.
--
--  آمن لإعادة التشغيل. ضمن INSTALL_ALL.sql — أو شغّله وحده بعد 21_access_control.sql.
-- ============================================================================

do $$
begin
    if to_regclass('public.clients') is not null then
        execute 'alter table public.clients add column if not exists live_key_hash text';
        if not exists (select 1 from pg_constraint
                        where conname = 'clients_live_key_hash_format'
                          and conrelid = 'public.clients'::regclass) then
            execute $c$alter table public.clients add constraint clients_live_key_hash_format
                     check (live_key_hash is null or live_key_hash ~ '^[0-9a-f]{64}$')$c$;
        end if;
        execute $c$comment on column public.clients.live_key_hash is
            'بصمة SHA-256 لمفتاح رابط المدير المباشر — المفتاح نفسه على جهاز المدير وحده'$c$;
    end if;
end $$;

alter table public.client_devices add column if not exists live_url      text;
alter table public.client_devices add column if not exists live_url_at   timestamptz;
alter table public.client_devices add column if not exists live_state    text;
alter table public.client_devices add column if not exists live_state_at timestamptz;

comment on column public.client_devices.live_url is
    'عنوان الجهاز في وسيط الرابط المباشر (بلا مفتاح) — يكوّن منه برنامج المدير الرابط';
comment on column public.client_devices.live_state is
    'حال الرابط على جهاز المصنع (يعمل؟ Tailscale؟ وصل المفتاح؟) — يراه المدير في فحص الرابط (1.96.1)';

-- ----------------------------------------------------------------------------
--  برنامج العميل: يحفظ عنوان جهازه (إن أرسله) ويأخذ بصمة مفتاح المدير
--  لا شيء إلا برمز مزامنة الحساب نفسه، وللحساب الفعّال والجهاز المسموح.
-- ----------------------------------------------------------------------------
create or replace function public.client_live_sync(
    p_client_id  uuid,
    p_sync_token uuid,
    p_device_id  text,
    p_url        text default null
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_dev    text := left(nullif(btrim(coalesce(p_device_id, '')), ''), 128);
    v_url    text := lower(nullif(btrim(coalesce(p_url, '')), ''));
    v_status text;
    v_hash   text;
begin
    if p_client_id is null or p_sync_token is null or v_dev is null or not exists (
            select 1 from public.tenants t where t.id = p_client_id and t.sync_token = p_sync_token) then
        return null;
    end if;
    select g.out_status into v_status
      from public.client_access_gate(p_client_id, v_dev, null, null, false) g;
    if v_status is distinct from 'ok' then
        return null;
    end if;
    if v_url is not null and v_url ~ '^https://[a-z0-9]([a-z0-9.-]{2,251}[a-z0-9])?$' then
        update public.client_devices
           set live_url = v_url, live_url_at = now()
         where client_id = p_client_id and device_id = v_dev
           and live_url is distinct from v_url;
    end if;
    select c.live_key_hash into v_hash from public.clients c where c.client_id = p_client_id;
    return v_hash;
end $$;

revoke all on function public.client_live_sync(uuid, uuid, text, text) from public;
grant execute on function public.client_live_sync(uuid, uuid, text, text) to anon, authenticated, service_role;

-- ----------------------------------------------------------------------------
--  (1.96.1) الدالة نفسها ومعها حال الرابط على الجهاز (p_state) — الرباعية أعلاه تبقى للإصدار 1.96.0
-- ----------------------------------------------------------------------------
create or replace function public.client_live_sync(
    p_client_id  uuid,
    p_sync_token uuid,
    p_device_id  text,
    p_url        text,
    p_state      text
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_dev    text := left(nullif(btrim(coalesce(p_device_id, '')), ''), 128);
    v_hash   text;
begin
    v_hash := public.client_live_sync(p_client_id, p_sync_token, p_device_id, p_url);
    if v_dev is not null and exists (
            select 1 from public.tenants t where t.id = p_client_id and t.sync_token = p_sync_token) then
        update public.client_devices
           set live_state = left(nullif(btrim(coalesce(p_state, '')), ''), 300), live_state_at = now()
         where client_id = p_client_id and device_id = v_dev;
    end if;
    return v_hash;
end $$;

revoke all on function public.client_live_sync(uuid, uuid, text, text, text) from public;
grant execute on function public.client_live_sync(uuid, uuid, text, text, text) to anon, authenticated, service_role;

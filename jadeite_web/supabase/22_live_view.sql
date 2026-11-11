-- ============================================================================
--  جاديت ERP — «العرض المباشر»: رابط المدير الخاص إلى جهاز العميل (الإصدار 1.94.0)
--
--  برنامج العميل يشغّل على جهازه خادماً للقراءة فقط (شاشات مراحل التصنيع وصناديق الخياس
--  والمبيعات والوارد وصناديق المصنع والخسائر، بالفترة المختارة) ونفقاً آمناً (https)، ويرسل
--  رابطه — وفيه مفتاحه السري — إلى هنا برمز مزامنته. والمدير يقرؤه بمفتاح المدير وحده من لوحته
--  («🌐 العرض المباشر») فيفتح شاشات الجهاز مباشرة.
--
--  ما يضيفه:
--    ١) live_links: آخر رابط لكل حساب (والجهاز الذي أرسله ووقته). محجوب عن anon وauthenticated:
--       لا يُقرأ إلا بمفتاح المدير، ولا يُكتب إلا من الدالة أدناه.
--    ٢) client_publish_live_link: برنامج العميل يرسل الرابط (أو يمسحه عند إيقاف العرض) برمز مزامنة
--       حسابه — والحساب الموقوف أو المنتهي أو الجهاز غير المسموح لا يرسل شيئاً، والرابط بصيغته
--       المعروفة وحدها (https و?k=المفتاح).
--
--  آمن لإعادة التشغيل. شغّله مع تحديث البرامج إلى 1.94.0 (وهو ضمن INSTALL_ALL أيضاً).
-- ============================================================================

create table if not exists public.live_links (
    client_id   uuid primary key references public.tenants(id) on delete cascade,
    url         text        not null,
    device_id   text,
    device_name text,
    app_version text,
    updated_at  timestamptz not null default now()
);

alter table public.live_links enable row level security;
revoke all on public.live_links from public, anon, authenticated;
grant  all on public.live_links to service_role;

comment on table public.live_links is
    'العرض المباشر: رابط جهاز العميل للمدير (فيه مفتاح سري) — يُقرأ بمفتاح المدير وحده';

create or replace function public.client_publish_live_link(
    p_client_id   uuid,
    p_sync_token  uuid,
    p_device_id   text,
    p_url         text,
    p_device_name text default null,
    p_app_version text default null
)
returns text
language plpgsql security definer set search_path = public as $$
declare
    v_url    text := btrim(coalesce(p_url, ''));
    v_dev    text := left(nullif(btrim(coalesce(p_device_id, '')), ''), 128);
    v_status text;
begin
    if p_client_id is null or p_sync_token is null or not exists (
            select 1 from public.tenants t where t.id = p_client_id and t.sync_token = p_sync_token) then
        return 'unauthorized';
    end if;

    -- إيقاف العرض: يُمسح رابط هذا الجهاز (لا رابطُ جهازٍ آخر للحساب نفسه)
    if v_url = '' then
        delete from public.live_links l
         where l.client_id = p_client_id and (l.device_id is null or l.device_id is not distinct from v_dev);
        return 'removed';
    end if;

    -- الحساب الموقوف أو المنتهي أو الجهاز غير المسموح لا يرسل رابطاً
    select g.out_status into v_status
      from public.client_access_gate(p_client_id, v_dev, null, null, false) g;
    if coalesce(v_status, 'unknown') not in ('ok', 'unknown') then
        return v_status;
    end if;

    if length(v_url) > 300 or v_url !~ '^https://[A-Za-z0-9.-]+/\?k=[A-Za-z0-9_-]{24,100}$' then
        return 'invalid';
    end if;

    insert into public.live_links as l (client_id, url, device_id, device_name, app_version, updated_at)
    values (p_client_id, v_url, v_dev, left(nullif(btrim(coalesce(p_device_name, '')), ''), 120),
            left(nullif(btrim(coalesce(p_app_version, '')), ''), 32), now())
    on conflict (client_id) do update
        set url = excluded.url, device_id = excluded.device_id,
            device_name = coalesce(excluded.device_name, l.device_name),
            app_version = coalesce(excluded.app_version, l.app_version), updated_at = now();
    return 'ok';
end $$;

revoke all on function public.client_publish_live_link(uuid, uuid, text, text, text, text) from public;
grant execute on function public.client_publish_live_link(uuid, uuid, text, text, text, text)
    to anon, authenticated, service_role;

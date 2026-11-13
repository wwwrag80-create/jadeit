-- ============================================================================
--  جاديت ERP — حماية كلمات مرور الحسابات في السحابة (الإصدار 1.97)
--
--  كان clients.password_hash بصمة SHA-256 لكلمة المرور كما يرسلها البرنامج، بلا «ملح»:
--    • لو تسرّب الجدول تُكسر البصمات السهلة في دقائق (جداول جاهزة لكل كلمة شائعة)؛
--    • والبصمة المخزّنة نفسها تفتح الحساب (من يقرؤها يدخل بها).
--  الآن تُخزَّن bcrypt لتلك البصمة (pgcrypto: crypt + gen_salt('bf')) — بملحٍ لكل حساب وبطيئة عمداً:
--    • البرنامج كما هو (يرسل البصمة نفسها) — فلا يغيّر أحدٌ كلمة مروره ولا يتعطّل دخوله؛
--    • الموجود يُحوَّل هنا في مكانه، وأي حساب جديد أو كلمة مرور جديدة تُحوَّل تلقائياً عند الحفظ (مشغّل).
--
--  ما يضيفه:
--    ١) password_matches(المخزّن، المرسل): bcrypt، أو المقارنة القديمة لما لم يُحوَّل بعد.
--    ٢) مشغّل على clients: بصمة SHA-256 (٦٤ حرفاً سداسياً) تُحوَّل إلى bcrypt قبل الحفظ.
--    ٣) تحويل كل البصمات الموجودة.
--    ٤) client_password_check (التي تمرّ بها client_login_v2 وclient_login_full) تقارن بـ password_matches.
--
--  آمن لإعادة التشغيل. ضمن INSTALL_ALL.sql — أو شغّله وحده بعد 21_access_control.sql.
-- ============================================================================

create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
--  ١) المقارنة: bcrypt (‏$2a$…) أو القيمة القديمة كما هي
-- ----------------------------------------------------------------------------
create or replace function public.password_matches(p_stored text, p_given text)
returns boolean
language plpgsql stable security definer set search_path = public, extensions as $$
begin
    if p_stored is null or p_given is null or p_given = '' then
        return false;
    end if;
    if p_stored like '$2_$%' then
        return crypt(p_given, p_stored) = p_stored;
    end if;
    return p_stored = p_given;          -- لم يُحوَّل بعد (يُحوَّل عند تشغيل هذا الملف أو أول حفظ)
end $$;

revoke all on function public.password_matches(text, text) from public, anon, authenticated;
grant execute on function public.password_matches(text, text) to service_role;

-- ----------------------------------------------------------------------------
--  ٢) و٣) المشغّل والتحويل — إن وُجد جدول العملاء
-- ----------------------------------------------------------------------------
create or replace function public.clients_hash_password()
returns trigger
language plpgsql set search_path = public, extensions as $$
begin
    if new.password_hash ~ '^[0-9a-f]{64}$' then
        new.password_hash := crypt(new.password_hash, gen_salt('bf', 8));
    end if;
    return new;
end $$;

revoke all on function public.clients_hash_password() from public, anon, authenticated;

do $$
begin
    if to_regclass('public.clients') is not null then
        execute 'drop trigger if exists clients_hash_password on public.clients';
        execute 'create trigger clients_hash_password before insert or update of password_hash on public.clients '
                'for each row execute function public.clients_hash_password()';
        execute $u$update public.clients set password_hash = password_hash
                    where password_hash ~ '^[0-9a-f]{64}$'$u$;
    end if;
end $$;

-- ----------------------------------------------------------------------------
--  ٤) التحقق من اسم المستخدم وكلمة المرور (21_access_control.sql) — بالمقارنة الجديدة
--     الحساب يُقرأ باسمه أولاً ثم تُقارن كلمة مروره مرة واحدة (bcrypt بطيئة عمداً)
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
    v_user   text := lower(btrim(coalesce(p_username, '')));
    v_fails  integer;
    v_id     uuid;
    v_name   text;
    v_edit   boolean;
    v_act    boolean;
    v_stored text;
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

    select c.client_id, c.business_name, c.can_edit, c.is_active, c.password_hash
      into v_id, v_name, v_edit, v_act, v_stored
      from public.clients c
     where lower(c.username) = v_user
     limit 1;

    if v_id is null or not public.password_matches(v_stored, p_password_hash) then
        insert into public.login_attempts (username, succeeded) values (v_user, false);
        return;
    end if;

    return query select v_id, v_name, coalesce(v_edit, true), coalesce(v_act, true);
end $$;

revoke execute on function public.client_password_check(text, text) from public, anon, authenticated;
grant  execute on function public.client_password_check(text, text) to service_role;

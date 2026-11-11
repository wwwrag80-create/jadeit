-- ============================================================================
--  جاديت ERP — السحابة للحسابات والصلاحيات وحدها (الإصدار 1.95.0)
--
--  لماذا: برامج العملاء من 1.95 لا ترفع نسخة بياناتها إلى السحابة، وبرنامج المدير لا ينزّل
--  شيئاً منها — المدير يرى المصنع ويتحكم فيه مباشرةً عبر «العرض المباشر» (رابط جهاز المصنع
--  نفسه). والنسخ الكاملة (db_backups) كانت أكبر ما في السحابة ومعظم حركة الإنترنت فيها.
--
--  ما يفعله هذا الملف:
--    ١) يحذف النسخ الكاملة المخزّنة (db_backups) — بـ TRUNCATE فتعود المساحة فوراً.
--    ٢) يمنع امتلاءها من جديد: رفع نسخة من برنامج عميل قديم (1.94 فما قبل) لم يُحدَّث بعد
--       يُتجاهل بهدوء — لا خطأ عنده ولا صف يُخزَّن.
--    ٣) يحذف جدول روابط العرض المباشر ودالته (من 1.94) — الرابط صار ثابتاً بلا سحابة.
--
--  يبقى كما هو: العملاء وحساباتهم وكلمات مرورهم ورموز مزامنتهم وصلاحية التعديل والإيقاف
--  ومدة الاشتراك والأجهزة والمدراء الفرعيون (tenants / clients / client_devices / sub_admins)
--  ودوال الدخول والفحص الدوري.
--
--  ⚠️ الحذف نهائي: البيانات كلها على أجهزة المصانع نفسها — وانسخ احتياطياً من «العرض المباشر»
--  (⚙️ لوحة التحكم ← ⬇️ تنزيل النسخة) أو من البرنامج على الجهاز. شغّله بعد تحديث البرامج إلى 1.95.0.
--  لا يدخل في INSTALL_ALL.sql: يُشغَّل وحده مرة واحدة على مشروعك.
-- ============================================================================

-- ١) منع الامتلاء من جديد: أي إدراج أو تحديث في النسخ يُتجاهل
create or replace function public.ignore_backup_writes()
returns trigger
language plpgsql as $$
begin
    return null;        -- لا يُخزَّن الصف، ولا يظهر خطأ لنسخة عميل قديمة ما زالت ترفع
end $$;

do $$
begin
    if to_regclass('public.db_backups') is not null then
        drop trigger if exists trg_backups_removed on public.db_backups;
        create trigger trg_backups_removed before insert or update on public.db_backups
            for each row execute function public.ignore_backup_writes();
    end if;
end $$;

-- ٢) حذف النسخ المخزّنة (TRUNCATE يعيد المساحة فوراً)
do $$
begin
    if to_regclass('public.db_backups') is not null then
        begin
            truncate table public.db_backups;
        exception when others then
            delete from public.db_backups;
        end;
    end if;
end $$;

-- ٣) روابط العرض المباشر في السحابة (1.94) — لم تعد مستخدمة
drop function if exists public.client_publish_live_link(uuid, uuid, text, text, text, text);
drop table if exists public.live_links;

select 'السحابة الآن للحسابات والصلاحيات وحدها ✔' as الحالة;

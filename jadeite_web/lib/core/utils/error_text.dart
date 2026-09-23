/// يحوّل أخطاء Supabase الخام إلى رسائل عربية تقول للمستخدم **ماذا يفعل** بالضبط،
/// بدل عرض نص استثناء إنجليزي لا يفيده.
///
/// كل حالة هنا خطأ حقيقي واجهناه أثناء التشغيل، ومكتوب معها الحل المباشر.
class ErrorText {
  const ErrorText._();

  static String friendly(Object error) {
    final raw = error.toString();

    // ---------- جداول غير موجودة أو ذاكرة PostgREST قديمة ----------
    if (raw.contains('PGRST205') || raw.contains('schema cache')) {
      return 'قاعدة البيانات غير مهيّأة بعد.\n\n'
          'الحل: افتح Supabase ← SQL Editor وشغّل الملف INSTALL_ALL.sql، '
          'ثم شغّل السطر التالي لتحديث الذاكرة:\n'
          "notify pgrst, 'reload schema';";
    }

    // ---------- خطأ مخطط المصادقة (السبب: محفّز معطوب أو صلاحيات ناقصة) ----------
    if (raw.contains('Database error querying schema') ||
        raw.contains('AuthRetryableFetchException')) {
      return 'خدمة تسجيل الدخول في Supabase معطّلة حالياً.\n\n'
          'الحل: شغّل الملف 00_repair_auth.sql في SQL Editor، '
          'ثم أعد تشغيل المشروع من Settings ← General ← Restart project.';
    }

    // ---------- بيانات دخول خاطئة ----------
    if (raw.contains('invalid_credentials') || raw.contains('Invalid login credentials')) {
      return 'البريد الإلكتروني أو كلمة المرور غير صحيحة.\n\n'
          'تأكد أيضاً أن المستخدم مُفعّل: Authentication ← Users ← يجب أن يكون '
          'Auto Confirm مفعّلاً أو البريد مؤكَّداً.';
    }

    // ---------- المستخدم موجود في المصادقة لكن غير مربوط بجدول app_users ----------
    if (raw.contains('غير مربوط') || raw.contains('app_users') && raw.contains('null')) {
      return 'الحساب موجود لكنه غير مربوط بالنظام.\n\n'
          'الحل: شغّل الملف 01_create_admin.sql بعد وضع بريدك فيه.';
    }

    // ---------- البريد غير مؤكَّد ----------
    if (raw.contains('Email not confirmed') || raw.contains('email_not_confirmed')) {
      return 'البريد الإلكتروني غير مُفعّل.\n\n'
          'الحل: Authentication ← Users ← افتح المستخدم ← Confirm email.';
    }

    // ---------- منع بسبب سياسات الحماية أو قفل التعديل ----------
    if (raw.contains('row-level security') || raw.contains('violates row-level')) {
      return 'العملية مرفوضة: إما أن التعديل مقفول من المدير، '
          'أو أنك تحاول الوصول لحساب غير حسابك.';
    }

    // ---------- تكرار في البيانات ----------
    if (raw.contains('duplicate key')) {
      return 'هذا السجل مسجّل من قبل — راجع الأرقام المكررة.';
    }

    // ---------- مشاكل الشبكة ----------
    if (raw.contains('SocketException') ||
        raw.contains('Failed host lookup') ||
        raw.contains('ClientException') ||
        raw.contains('XMLHttpRequest')) {
      return 'لا يوجد اتصال بالخادم.\n\n'
          'تحقق من الإنترنت، ومن صحة SUPABASE_URL و SUPABASE_ANON_KEY.';
    }

    // ---------- مفاتيح ناقصة ----------
    if (raw.contains('Invalid API key') || raw.contains('JWT')) {
      return 'مفتاح الاتصال بـ Supabase غير صحيح.\n\n'
          'راجع قيم --dart-define=SUPABASE_URL و SUPABASE_ANON_KEY.';
    }

    // ---------- غير ذلك: نعرض النص الخام لأنه أفضل من رسالة عامة مبهمة ----------
    return raw.replaceFirst('Exception: ', '');
  }
}

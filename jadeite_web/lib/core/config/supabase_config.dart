import 'package:supabase_flutter/supabase_flutter.dart';

/// إعدادات الاتصال بـ Supabase.
///
/// لا تضع المفتاح السري (service_role) هنا إطلاقاً — هذا الملف يُرسل للمتصفح.
/// المفتاح العام (anon) آمن لأن الحماية الحقيقية في سياسات RLS.
///
/// تمرير القيم وقت البناء:
///   flutter build web --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_ANON_KEY=...
class SupabaseConfig {
  const SupabaseConfig._();

  // القيم الافتراضية للتشغيل المحلي فقط؛ في النشر تأتي من متغيرات البيئة
  // عبر --dart-define في build_web.sh، فلا تُعدَّل هنا عند التغيير.
  static const String url = String.fromEnvironment(
    'SUPABASE_URL',
    defaultValue: 'https://ttpqksvtnhoulghgovob.supabase.co',
  );

  static const String anonKey = String.fromEnvironment(
    'SUPABASE_ANON_KEY',
    defaultValue: 'sb_publishable_ymRG7rKUf-704V3j1bNwgg_b1IvlMlX',
  );

  /// كل كم ثانية يُرسل نبض الحضور (يظهر للمدير كـ "متصل الآن")
  static const Duration heartbeatInterval = Duration(seconds: 10);

  /// كل كم ثانية تُعاد قراءة صلاحية التعديل من السحابة
  static const Duration permissionPollInterval = Duration(seconds: 30);

  static bool get isConfigured => url.isNotEmpty && anonKey.isNotEmpty;
}

/// عميل Supabase المشترك — نقطة وصول واحدة لكل الطبقات
SupabaseClient get db => Supabase.instance.client;

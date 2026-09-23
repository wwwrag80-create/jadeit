import 'package:intl/intl.dart';

/// تنسيقات موحّدة للأوزان والتواريخ والفترات المحاسبية.
class Fmt {
  const Fmt._();

  static final NumberFormat _weight = NumberFormat('#,##0.00', 'en');
  static final NumberFormat _carat = NumberFormat('#,##0.0', 'en');
  // en_US مدمجة في intl دائماً؛ أما 'en' فتحتاج تهيئة بيانات اللغة أولاً
  // (initializeDateFormatting) وإلا رمت LocaleDataException قبل تحميل الترجمات.
  static final DateFormat _dateTime = DateFormat('yyyy-MM-dd HH:mm', 'en_US');
  static final DateFormat _date = DateFormat('yyyy-MM-dd', 'en_US');
  static final DateFormat _period = DateFormat('yyyy-MM', 'en_US');

  static String weight(num? value) => _weight.format(value ?? 0);
  static String carat(num? value) => _carat.format(value ?? 0);

  /// يعرض الشرطة بدل الصفر حتى لا تمتلئ الجداول بأصفار بلا معنى
  static String weightOrDash(num? value) =>
      (value == null || value == 0) ? '-' : _weight.format(value);

  static String dateTime(DateTime? value) => value == null ? '-' : _dateTime.format(value.toLocal());
  static String date(DateTime? value) => value == null ? '-' : _date.format(value.toLocal());
  static String period(DateTime value) => _period.format(value);

  static String periodOf(DateTime value) => _period.format(value);

  /// الفترة الحالية بصيغة YYYY-MM
  static String currentPeriod() => _period.format(DateTime.now());

  /// أول يوم في فترة معيّنة (يُستخدم كتاريخ افتراضي عند العمل في شهر سابق)
  static DateTime firstDayOfPeriod(String period) {
    final parts = period.split('-');
    return DateTime(int.parse(parts[0]), int.parse(parts[1]), 1);
  }

  /// تاريخ العملية الحقيقي: اليوم المختار بساعة التسجيل الفعلية.
  ///
  /// مثل برنامج سطح المكتب: التاريخ لا يُزوَّر ليدخل الفترة المعروضة، بل تُرسل
  /// الفترة المحاسبية صراحةً مع الحركة (عمود period) — فتظهر الحركة في الفترة
  /// التي سُجّلت فيها مهما كان شهر تاريخها.
  static DateTime operationDate(DateTime day, {DateTime? now}) {
    final t = now ?? DateTime.now();
    return DateTime(day.year, day.month, day.day, t.hour, t.minute, t.second);
  }

  /// هل الفترة بصيغة YYYY-MM صحيحة؟
  static bool isValidPeriod(String period) => RegExp(r'^\d{4}-\d{2}$').hasMatch(period);

  static String shiftPeriod(String period, int months) {
    final base = firstDayOfPeriod(period);
    return _period.format(DateTime(base.year, base.month + months, 1));
  }

  /// "منذ ٥ دقائق" — لعرض آخر ظهور في لوحة المدير
  static String since(DateTime? value) {
    if (value == null) return 'لم يدخل بعد';
    final minutes = DateTime.now().difference(value.toLocal()).inMinutes;
    if (minutes < 2) return 'الآن';
    if (minutes < 60) return 'منذ $minutes دقيقة';
    if (minutes < 1440) return 'منذ ${minutes ~/ 60} ساعة';
    return 'منذ ${minutes ~/ 1440} يوم';
  }

  /// ترتيب أرقام الصفوف تدريجياً: رقمياً أولاً، ثم نصياً، والفارغ في النهاية
  static int compareRowNumbers(String a, String b) {
    final numA = double.tryParse(a.trim());
    final numB = double.tryParse(b.trim());
    if (a.trim().isEmpty) return b.trim().isEmpty ? 0 : 1;
    if (b.trim().isEmpty) return -1;
    if (numA != null && numB != null) return numA.compareTo(numB);
    if (numA != null) return -1;
    if (numB != null) return 1;
    return a.compareTo(b);
  }
}

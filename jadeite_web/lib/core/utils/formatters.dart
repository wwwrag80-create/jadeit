import 'package:intl/intl.dart';

/// تنسيقات موحّدة للأوزان والتواريخ والفترات المحاسبية.
class Fmt {
  const Fmt._();

  static final NumberFormat _weight = NumberFormat('#,##0.00', 'en');
  static final NumberFormat _carat = NumberFormat('#,##0.0', 'en');
  static final DateFormat _dateTime = DateFormat('yyyy-MM-dd HH:mm', 'en');
  static final DateFormat _date = DateFormat('yyyy-MM-dd', 'en');
  static final DateFormat _period = DateFormat('yyyy-MM', 'en');

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

  /// تاريخ افتراضي ذكي: اليوم إن كنا في الشهر الحالي، وإلا أول الشهر المعروض
  static DateTime smartDefaultDate(String period) =>
      period == currentPeriod() ? DateTime.now() : firstDayOfPeriod(period);

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

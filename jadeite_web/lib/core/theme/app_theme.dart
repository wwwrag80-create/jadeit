import 'package:flutter/material.dart';

/// هوية جاديت البصرية: ذهبي على داكن، بخط Cairo واتجاه عربي.
class AppTheme {
  const AppTheme._();

  static const Color gold = Color(0xFFD4AF37);
  static const Color goldDim = Color(0xFFB8860B);
  static const Color blue = Color(0xFF1F77B4);
  static const Color blueDark = Color(0xFF144D75);
  static const Color danger = Color(0xFFC0392B);
  static const Color success = Color(0xFF2ECC71);
  static const Color warn = Color(0xFFE67E22);
  static const Color surfaceDark = Color(0xFF1B1F24);
  static const Color surfaceDarker = Color(0xFF13161A);

  static const String fontFamily = 'Cairo';

  static ThemeData dark() => _build(Brightness.dark);
  static ThemeData light() => _build(Brightness.light);

  static ThemeData _build(Brightness brightness) {
    final bool isDark = brightness == Brightness.dark;
    final ColorScheme scheme = ColorScheme.fromSeed(
      seedColor: gold,
      brightness: brightness,
    ).copyWith(primary: gold, secondary: blue, error: danger);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      fontFamily: fontFamily,
      scaffoldBackgroundColor: isDark ? surfaceDarker : const Color(0xFFF3F5F7),
      cardTheme: CardThemeData(
        color: isDark ? surfaceDark : Colors.white,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: BorderSide(color: isDark ? Colors.white10 : Colors.black12),
        ),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: isDark ? surfaceDark : Colors.white,
        foregroundColor: isDark ? Colors.white : Colors.black87,
        elevation: 0,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        isDense: true,
        filled: true,
        fillColor: isDark ? Colors.white10 : Colors.black.withValues(alpha: 0.04),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide.none,
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 44),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          textStyle: const TextStyle(fontFamily: fontFamily, fontWeight: FontWeight.bold),
        ),
      ),
      dataTableTheme: DataTableThemeData(
        headingRowColor: WidgetStatePropertyAll(
          isDark ? Colors.white.withValues(alpha: 0.06) : Colors.black.withValues(alpha: 0.04),
        ),
        headingTextStyle: const TextStyle(
          fontFamily: fontFamily,
          fontWeight: FontWeight.bold,
          color: gold,
        ),
        dividerThickness: 0.4,
      ),
      dividerTheme: const DividerThemeData(thickness: 0.4),
    );
  }

  /// لون الصف في جداول العمليات:
  /// أحمر إذا كان الدائن أكبر من المدين (أو الفاقد اللحظي سالباً)، وإلا اللون الافتراضي.
  static Color? rowColorFor(double khayas) =>
      khayas < 0 ? danger : null;
}

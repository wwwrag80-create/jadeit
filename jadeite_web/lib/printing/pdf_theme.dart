import 'package:flutter/services.dart' show rootBundle;
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

/// أساس موحّد لكل قوالب الطباعة: خط Cairo عربي واتجاه RTL كامل.
///
/// لا يُخزَّن أي ملف PDF على السحابة إطلاقاً — كل شيء يُولَّد في المتصفح لحظياً
/// عند الطلب ثم يُطبع أو يُحمَّل، فلا يستهلك مساحة التخزين.
class PdfTheme {
  const PdfTheme._();

  static pw.Font? _regular;
  static pw.Font? _bold;

  static const PdfColor gold = PdfColor.fromInt(0xFFB8860B);
  static const PdfColor ink = PdfColor.fromInt(0xFF1B1F24);
  static const PdfColor line = PdfColor.fromInt(0xFF9AA3AB);
  static const PdfColor headerBg = PdfColor.fromInt(0xFFF0EAD6);

  /// يحمّل خط Cairo مرة واحدة (مطلوب لعرض العربية بشكل صحيح في PDF)
  static Future<void> ensureFonts() async {
    if (_regular != null && _bold != null) return;
    _regular = pw.Font.ttf(await rootBundle.load('assets/fonts/Cairo-Regular.ttf'));
    _bold = pw.Font.ttf(await rootBundle.load('assets/fonts/Cairo-Bold.ttf'));
  }

  static pw.ThemeData theme() => pw.ThemeData.withFont(
        base: _regular!,
        bold: _bold!,
      );

  static pw.TextStyle text({double size = 9, bool bold = false, PdfColor? color}) =>
      pw.TextStyle(
        font: bold ? _bold : _regular,
        fontSize: size,
        color: color ?? ink,
        fontWeight: bold ? pw.FontWeight.bold : pw.FontWeight.normal,
      );

  /// كل النصوص العربية تمر من هنا لضمان الاتجاه الصحيح
  static pw.Widget rtl(String value, {double size = 9, bool bold = false, PdfColor? color}) =>
      pw.Directionality(
        textDirection: pw.TextDirection.rtl,
        child: pw.Text(value, style: text(size: size, bold: bold, color: color)),
      );

  static pw.Widget page({required List<pw.Widget> children}) => pw.Directionality(
        textDirection: pw.TextDirection.rtl,
        child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.stretch, children: children),
      );

  /// ترويسة موحّدة لكل المستندات
  static pw.Widget header({
    required String businessName,
    required String title,
    String? crNumber,
    String? vatNumber,
    String? city,
  }) =>
      pw.Container(
        padding: const pw.EdgeInsets.all(10),
        decoration: pw.BoxDecoration(
          border: pw.Border.all(color: line, width: 0.7),
          borderRadius: pw.BorderRadius.circular(6),
        ),
        child: pw.Row(
          mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
              pw.Text('JADEITE', style: text(size: 14, bold: true, color: gold)),
              pw.Text('Gold & Jewellery', style: text(size: 7)),
            ]),
            rtl(title, size: 13, bold: true, color: gold),
            pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.end, children: [
              rtl(businessName, size: 11, bold: true),
              if (city != null) rtl(city, size: 7),
              if (crNumber != null) rtl('س.ت: $crNumber', size: 7),
              if (vatNumber != null) rtl('الرقم الضريبي: $vatNumber', size: 7),
            ]),
          ],
        ),
      );

  static pw.Widget footer(pw.Context context) => pw.Directionality(
        textDirection: pw.TextDirection.rtl,
        child: pw.Padding(
          padding: const pw.EdgeInsets.only(top: 6),
          child: pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            children: [
              pw.Text('نظام جاديت', style: text(size: 7, color: line)),
              pw.Text('صفحة ${context.pageNumber} من ${context.pagesCount}',
                  style: text(size: 7, color: line)),
            ],
          ),
        ),
      );

  /// جدول عربي: الأعمدة تُعكس تلقائياً ليكون العمود الأول على اليمين
  static pw.Widget table({
    required List<String> columns,
    required List<List<String>> rows,
    List<String>? totalsRow,
    List<double>? columnWidths,
  }) {
    List<T> flip<T>(List<T> items) => items.reversed.toList();

    final widths = <int, pw.TableColumnWidth>{};
    if (columnWidths != null) {
      final flipped = flip(columnWidths);
      for (var i = 0; i < flipped.length; i++) {
        widths[i] = pw.FlexColumnWidth(flipped[i]);
      }
    }

    return pw.Table(
      border: pw.TableBorder.all(color: line, width: 0.4),
      columnWidths: widths,
      children: [
        pw.TableRow(
          decoration: const pw.BoxDecoration(color: headerBg),
          children: flip(columns)
              .map((c) => pw.Padding(
                    padding: const pw.EdgeInsets.symmetric(vertical: 4, horizontal: 3),
                    child: pw.Center(child: rtl(c, size: 8, bold: true)),
                  ))
              .toList(),
        ),
        ...rows.map((r) => pw.TableRow(
              children: flip(r)
                  .map((cell) => pw.Padding(
                        padding: const pw.EdgeInsets.symmetric(vertical: 3, horizontal: 3),
                        child: pw.Center(child: rtl(cell, size: 8)),
                      ))
                  .toList(),
            )),
        if (totalsRow != null)
          pw.TableRow(
            decoration: const pw.BoxDecoration(color: headerBg),
            children: flip(totalsRow)
                .map((cell) => pw.Padding(
                      padding: const pw.EdgeInsets.symmetric(vertical: 4, horizontal: 3),
                      child: pw.Center(child: rtl(cell, size: 8, bold: true)),
                    ))
                .toList(),
          ),
      ],
    );
  }
}

import 'package:flutter_test/flutter_test.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:jadeite_erp/printing/pdf_theme.dart';

/// يتحقق أن خطوط Cairo المضمّنة صالحة لتوليد PDF عربي — بدونها يفشل البناء
/// أو تخرج الفواتير مربعات فارغة بدل الحروف.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('توليد PDF عربي بخط Cairo وجدول معكوس الاتجاه', () async {
    await PdfTheme.ensureFonts();

    final doc = pw.Document();
    doc.addPage(
      pw.Page(
        theme: PdfTheme.theme(),
        textDirection: pw.TextDirection.rtl,
        build: (_) => PdfTheme.page(children: [
          PdfTheme.header(businessName: 'مصنع الاختبار', title: 'فاتورة مبيعات'),
          PdfTheme.table(
            columns: const ['رقم التشغيل', 'الذهب', 'الماس'],
            rows: const [
              ['S1', '10.00', '0.40'],
            ],
            totalsRow: const ['الإجمالي', '10.00', '0.40'],
            columnWidths: const [1, 1, 1],
          ),
        ]),
      ),
    );

    final bytes = await doc.save();
    expect(bytes.length, greaterThan(1000));
    // توقيع ملف PDF
    expect(String.fromCharCodes(bytes.take(4)), '%PDF');
  });
}

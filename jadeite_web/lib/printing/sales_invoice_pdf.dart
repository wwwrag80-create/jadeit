import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../core/utils/formatters.dart';
import '../data/models/models.dart';
import 'pdf_theme.dart';

/// توليد فواتير المبيعات لحظياً في المتصفح — بدون أي تخزين على السحابة.
class SalesInvoicePdf {
  const SalesInvoicePdf();

  /// قالب الفاتورة المجمّعة: كل رقم تشغيل في صف، مع عمود الخياس.
  Future<void> printSummary({
    required String businessName,
    required String customerName,
    required String invoiceNo,
    required DateTime date,
    required List<SaleLine> lines,
    String? crNumber,
    String? vatNumber,
    String? city,
  }) async {
    await PdfTheme.ensureFonts();

    final rows = <List<String>>[];
    double tGold = 0, tGems = 0, tStonesRaw = 0, tStonesAfter = 0, tDiamond = 0, tKhayas = 0;

    for (var i = 0; i < lines.length; i++) {
      final l = lines[i];
      tGold += l.gold;
      tGems += l.gems;
      tStonesRaw += l.stonesRaw;
      tStonesAfter += l.stonesAfterDiscount;
      tDiamond += l.diamond;
      tKhayas += l.khayas;

      rows.add([
        '${i + 1}',
        l.setNumber.isEmpty ? '-' : l.setNumber,
        Fmt.weightOrDash(l.gold),
        Fmt.weightOrDash(l.gems),
        Fmt.weightOrDash(l.stonesRaw),
        Fmt.weightOrDash(l.stonesAfterDiscount),
        Fmt.weightOrDash(l.diamond),
        Fmt.weightOrDash(l.khayas),
        Fmt.weightOrDash(l.standingWeight),
        Fmt.weightOrDash(l.boundWeight),
      ]);
    }

    final totalStanding = tGold + tGems + tStonesRaw + tDiamond;
    final totalBound = tGold + tGems + tStonesAfter + tDiamond;

    final doc = pw.Document();
    doc.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        theme: PdfTheme.theme(),
        margin: const pw.EdgeInsets.all(24),
        textDirection: pw.TextDirection.rtl,
        footer: PdfTheme.footer,
        build: (context) => [
          PdfTheme.header(
            businessName: businessName,
            title: 'فاتورة مبيعات',
            crNumber: crNumber,
            vatNumber: vatNumber,
            city: city,
          ),
          pw.SizedBox(height: 10),
          pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            children: [
              PdfTheme.rtl('التاريخ: ${Fmt.dateTime(date)}', size: 9),
              PdfTheme.rtl('العميل: $customerName', size: 10, bold: true),
              PdfTheme.rtl('رقم الفاتورة: $invoiceNo', size: 10, bold: true),
            ],
          ),
          pw.SizedBox(height: 10),
          PdfTheme.table(
            columns: const [
              '#', 'رقم التشغيل', 'الذهب', 'الفصوص', 'الأحجار',
              'الأحجار بعد الخصم', 'الماس', 'خياس', 'الوزن القائم', 'الوزن المقيد',
            ],
            columnWidths: const [0.45, 1.0, 0.85, 0.85, 0.85, 1.1, 0.85, 0.8, 0.95, 0.95],
            rows: rows,
            totalsRow: [
              'الإجمالي', '-',
              Fmt.weight(tGold), Fmt.weight(tGems), Fmt.weight(tStonesRaw),
              Fmt.weight(tStonesAfter), Fmt.weight(tDiamond), Fmt.weight(tKhayas),
              Fmt.weight(totalStanding), Fmt.weight(totalBound),
            ],
          ),
          pw.SizedBox(height: 24),
          pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceAround,
            children: [
              PdfTheme.rtl('توقيع المستلم: ..............................', size: 9),
              PdfTheme.rtl('توقيع المسؤول: ..............................', size: 9),
            ],
          ),
        ],
      ),
    );

    await Printing.layoutPdf(onLayout: (_) => doc.save(), name: 'فاتورة-$invoiceNo.pdf');
  }

  /// قالب رقم التشغيل: تفاصيل أوزان طقم واحد، وفيه خانة الخياس.
  Future<void> printSetTemplate({
    required String businessName,
    required String customerName,
    required String invoiceNo,
    required DateTime date,
    required SaleLine line,
    required double discountPct,
    String? crNumber,
    String? vatNumber,
  }) async {
    await PdfTheme.ensureFonts();

    final doc = pw.Document();
    doc.addPage(
      pw.Page(
        pageFormat: PdfPageFormat.a5.landscape,
        theme: PdfTheme.theme(),
        margin: const pw.EdgeInsets.all(18),
        textDirection: pw.TextDirection.rtl,
        build: (context) => PdfTheme.page(children: [
          PdfTheme.header(
            businessName: businessName,
            title: 'سند رقم تشغيل',
            crNumber: crNumber,
            vatNumber: vatNumber,
          ),
          pw.SizedBox(height: 8),
          pw.Row(
            mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
            children: [
              PdfTheme.rtl('التاريخ: ${Fmt.dateTime(date)}', size: 9),
              PdfTheme.rtl('العميل: $customerName', size: 10, bold: true),
              PdfTheme.rtl('رقم التشغيل: ${line.setNumber}', size: 11, bold: true),
              PdfTheme.rtl('رقم الفاتورة: $invoiceNo', size: 9),
            ],
          ),
          pw.SizedBox(height: 10),
          PdfTheme.table(
            columns: const ['البيان', 'القيمة'],
            columnWidths: const [2.0, 1.0],
            rows: [
              ['الذهب', Fmt.weight(line.gold)],
              ['الفصوص', Fmt.weight(line.gems)],
              ['الأحجار', Fmt.weight(line.stonesRaw)],
              ['الأحجار بعد الخصم (${discountPct.toStringAsFixed(0)}%)',
                Fmt.weight(line.stonesAfterDiscount)],
              ['الماس', Fmt.weight(line.diamond)],
              ['الخياس', Fmt.weight(line.khayas)],
            ],
            totalsRow: ['الوزن المقيد', Fmt.weight(line.boundWeight)],
          ),
          pw.SizedBox(height: 18),
          PdfTheme.rtl('توقيع المستلم: ..............................', size: 9),
        ]),
      ),
    );

    await Printing.layoutPdf(
      onLayout: (_) => doc.save(),
      name: 'تشغيل-${line.setNumber}.pdf',
    );
  }
}

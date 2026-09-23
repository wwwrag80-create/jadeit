import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:printing/printing.dart';

import '../core/utils/formatters.dart';
import 'pdf_theme.dart';

/// كشف حساب / تقرير عام — يُولَّد لحظياً ولا يُخزَّن.
class StatementPdf {
  const StatementPdf();

  Future<void> print({
    required String businessName,
    required String title,
    required String subtitle,
    required List<String> columns,
    required List<List<String>> rows,
    List<String>? totalsRow,
    List<double>? columnWidths,
  }) async {
    await PdfTheme.ensureFonts();

    final doc = pw.Document();
    doc.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        theme: PdfTheme.theme(),
        margin: const pw.EdgeInsets.all(24),
        textDirection: pw.TextDirection.rtl,
        footer: PdfTheme.footer,
        build: (context) => [
          PdfTheme.header(businessName: businessName, title: title),
          pw.SizedBox(height: 8),
          PdfTheme.rtl(subtitle, size: 10, bold: true),
          pw.SizedBox(height: 10),
          PdfTheme.table(
            columns: columns,
            rows: rows,
            totalsRow: totalsRow,
            columnWidths: columnWidths,
          ),
          pw.SizedBox(height: 10),
          PdfTheme.rtl('تاريخ الطباعة: ${Fmt.dateTime(DateTime.now())}', size: 8),
        ],
      ),
    );

    await Printing.layoutPdf(onLayout: (_) => doc.save(), name: '$title.pdf');
  }
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import 'sale_posting_service.dart';

/// نافذة تعديل فاتورة مبيعات مرحّلة: نفس خانات العمليات + جدول سطورها.
///
/// عند الحفظ تُحذف حركات الفاتورة القديمة وتُعاد كتابتها بالكامل — هذا يضمن
/// تطابق الحسابات مع الفاتورة بعد التعديل، ولا يترك أي حركة يتيمة في النظام.
class InvoiceEditorDialog extends ConsumerStatefulWidget {
  const InvoiceEditorDialog({
    super.key,
    required this.summary,
    required this.existing,
  });

  final SalesInvoiceSummary summary;
  final List<Txn> existing;

  @override
  ConsumerState<InvoiceEditorDialog> createState() => _InvoiceEditorDialogState();
}

class _InvoiceEditorDialogState extends ConsumerState<InvoiceEditorDialog> {
  static const _service = SalePostingService();

  late final List<SaleLine> _lines = _service.rebuildLines(widget.existing);
  late final TextEditingController _invoiceNo =
      TextEditingController(text: widget.summary.manualNo);

  final _rowNumber = TextEditingController();
  final _setNumber = TextEditingController();
  final _gold = TextEditingController();
  final _gems = TextEditingController();
  final _stones = TextEditingController();
  final _stonesAfter = TextEditingController();
  final _khayas = TextEditingController();
  final _diamond = TextEditingController();

  int? _editingIndex;
  bool _busy = false;

  @override
  void dispose() {
    for (final c in [
      _invoiceNo, _rowNumber, _setNumber, _gold, _gems,
      _stones, _stonesAfter, _khayas, _diamond,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  double _n(TextEditingController c) => double.tryParse(c.text.trim()) ?? 0;

  void _clear() {
    for (final c in [_rowNumber, _setNumber, _gold, _gems, _stones, _stonesAfter, _khayas, _diamond]) {
      c.clear();
    }
    setState(() => _editingIndex = null);
  }

  void _saveLine() {
    final line = SaleLine(
      rowNumber: _rowNumber.text.trim(),
      setNumber: _setNumber.text.trim(),
      gold: _n(_gold),
      gems: _n(_gems),
      stonesRaw: _n(_stones),
      stonesAfterDiscount: _n(_stonesAfter),
      diamond: _n(_diamond),
      khayas: _n(_khayas),
    );
    if (line.isEmpty) {
      AppSnack.warn(context, 'لا بد من قيمة واحدة على الأقل.');
      return;
    }
    final dup = _service.duplicateError(
        _lines, line.rowNumber, line.setNumber, skipIndex: _editingIndex);
    if (dup != null) {
      AppSnack.warn(context, dup);
      return;
    }
    setState(() {
      if (_editingIndex == null) {
        _lines.add(line);
      } else {
        _lines[_editingIndex!] = line;
      }
    });
    _clear();
  }

  void _load(int i) {
    final l = _lines[i];
    _rowNumber.text = l.rowNumber;
    _setNumber.text = l.setNumber;
    _gold.text = l.gold == 0 ? '' : '${l.gold}';
    _gems.text = l.gems == 0 ? '' : '${l.gems}';
    _stones.text = l.stonesRaw == 0 ? '' : '${l.stonesRaw}';
    _stonesAfter.text = l.stonesAfterDiscount == 0 ? '' : '${l.stonesAfterDiscount}';
    _diamond.text = l.diamond == 0 ? '' : '${l.diamond}';
    _khayas.text = l.khayas == 0 ? '' : '${l.khayas}';
    setState(() => _editingIndex = i);
  }

  Future<void> _save() async {
    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    if (_lines.isEmpty) {
      AppSnack.warn(context,
          'لا توجد سطور. لحذف الفاتورة بالكامل استخدم زر الحذف من جدول العمليات.');
      return;
    }
    final invoiceNo = _invoiceNo.text.trim();
    if (invoiceNo.isEmpty) {
      AppSnack.warn(context, 'رقم الفاتورة مطلوب.');
      return;
    }

    final ok = await confirmDialog(
      context,
      title: 'تأكيد الحفظ',
      message: 'سيتم إعادة تسجيل الفاتورة بـ ${_lines.length} سطر، '
          'وتحديث الخزينة وصندوق خياس الطقوم وكل الحسابات المرتبطة.',
    );
    if (!ok) return;

    // الفاتورة المعدّلة تبقى في فترتها الأصلية (لا في الفترة المعروضة الآن)
    final period = widget.existing
        .map((t) => t.period)
        .firstWhere((p) => p.isNotEmpty, orElse: () => ref.read(periodProvider));

    setState(() => _busy = true);
    try {
      // الحذف والإعادة في معاملة واحدة: لو فشل أي جزء تبقى الفاتورة الأصلية كما هي
      await ref.read(txnRepoProvider).replaceMany(
            tenantId,
            widget.existing.map((t) => t.id).toList(),
            _service.buildTransactions(
              lines: _lines,
              customerName: widget.summary.accountName,
              date: widget.summary.date,
              manualInvoiceNo: invoiceNo,
              period: period,
            ),
          );
      bumpDataRevision(ref);

      if (mounted) {
        Navigator.pop(context);
        AppSnack.success(context, 'تم حفظ تعديلات الفاتورة وتحديث كل الحسابات.');
      }
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Dialog(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1080, maxHeight: 720),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(children: [
                  const Text('✏️ تعديل فاتورة مبيعات مرحّلة',
                      style: TextStyle(
                          fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ]),
                const SizedBox(height: 10),
                Row(children: [
                  SizedBox(
                    width: 160,
                    child: TextField(
                      controller: _invoiceNo,
                      decoration: const InputDecoration(labelText: 'رقم الفاتورة'),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Text('العميل: ${widget.summary.accountName}',
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(width: 16),
                  Text('التاريخ: ${Fmt.dateTime(widget.summary.date)}',
                      style: const TextStyle(color: Colors.grey)),
                ]),
                const Divider(height: 24),
                Wrap(spacing: 8, runSpacing: 8, children: [
                  _f(_rowNumber, 'رقم الصف', 95),
                  _f(_setNumber, 'رقم التشغيل', 120),
                  _f(_gold, 'الذهب', 100),
                  _f(_gems, 'الفصوص', 100),
                  _f(_stones, 'الأحجار', 100),
                  _f(_stonesAfter, 'الأحجار بعد الخصم', 135),
                  _f(_khayas, 'خياس', 95),
                  _f(_diamond, 'الماس', 95),
                ]),
                const SizedBox(height: 10),
                Row(children: [
                  FilledButton.icon(
                    onPressed: _saveLine,
                    icon: Icon(_editingIndex == null ? Icons.add : Icons.save, size: 18),
                    label: Text(_editingIndex == null ? 'إضافة سطر' : 'حفظ السطر'),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(onPressed: _clear, child: const Text('تفريغ')),
                ]),
                const SizedBox(height: 12),
                Expanded(
                  child: SingleChildScrollView(
                    child: DataTable(
                      columnSpacing: 20,
                      columns: const [
                        DataColumn(label: Text('رقم الصف')),
                        DataColumn(label: Text('رقم التشغيل')),
                        DataColumn(label: Text('الذهب')),
                        DataColumn(label: Text('الفصوص')),
                        DataColumn(label: Text('الأحجار')),
                        DataColumn(label: Text('بعد الخصم')),
                        DataColumn(label: Text('الماس')),
                        DataColumn(label: Text('خياس')),
                        DataColumn(label: Text('')),
                      ],
                      rows: [
                        for (var i = 0; i < _lines.length; i++)
                          DataRow(cells: [
                            DataCell(Text(_lines[i].rowNumber.isEmpty ? '-' : _lines[i].rowNumber)),
                            DataCell(Text(_lines[i].setNumber.isEmpty ? '-' : _lines[i].setNumber)),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].gold))),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].gems))),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].stonesRaw))),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].stonesAfterDiscount))),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].diamond))),
                            DataCell(Text(Fmt.weightOrDash(_lines[i].khayas))),
                            DataCell(Row(children: [
                              IconButton(
                                icon: const Icon(Icons.edit, size: 17),
                                onPressed: () => _load(i),
                              ),
                              IconButton(
                                icon: const Icon(Icons.delete_outline,
                                    size: 17, color: AppTheme.danger),
                                onPressed: () => setState(() => _lines.removeAt(i)),
                              ),
                            ])),
                          ]),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                FilledButton.icon(
                  onPressed: _busy ? null : _save,
                  icon: const Icon(Icons.check),
                  label: Text(_busy ? 'جاري الحفظ…' : 'حفظ تعديلات الفاتورة'),
                ),
              ],
            ),
          ),
        ),
      );

  Widget _f(TextEditingController c, String label, double width) => SizedBox(
        width: width,
        child: TextField(
          controller: c,
          textAlign: TextAlign.center,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label),
        ),
      );
}

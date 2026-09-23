import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../printing/sales_invoice_pdf.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';
import 'sale_posting_service.dart';

/// تبويب إدخال فاتورة المبيعات: خانات العمليات + جدول السطور المعلّقة + الترحيل.
class SalesEntryTab extends ConsumerStatefulWidget {
  const SalesEntryTab({super.key});

  @override
  ConsumerState<SalesEntryTab> createState() => _SalesEntryTabState();
}

class _SalesEntryTabState extends ConsumerState<SalesEntryTab> {
  static const _service = SalePostingService();

  final _invoiceNo = TextEditingController();
  final _rowNumber = TextEditingController();
  final _setNumber = TextEditingController();
  final _gold = TextEditingController();
  final _gems = TextEditingController();
  final _stones = TextEditingController();
  final _stonesAfter = TextEditingController();
  final _khayas = TextEditingController();
  final _diamond = TextEditingController();

  final List<SaleLine> _pending = [];
  String? _customer;
  DateTime _date = DateTime.now();
  double _discountPct = 30;
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

  double _num(TextEditingController c) => double.tryParse(c.text.trim()) ?? 0;

  void _recalcStones() {
    final raw = _num(_stones);
    if (raw > 0) {
      _stonesAfter.text = _service.stonesAfterDiscount(raw, _discountPct).toStringAsFixed(2);
    }
  }

  void _clearLineFields() {
    for (final c in [_rowNumber, _setNumber, _gold, _gems, _stones, _stonesAfter, _khayas, _diamond]) {
      c.clear();
    }
    setState(() => _editingIndex = null);
  }

  void _addOrUpdateLine() {
    final line = SaleLine(
      rowNumber: _rowNumber.text.trim(),
      setNumber: _setNumber.text.trim(),
      gold: _num(_gold),
      gems: _num(_gems),
      stonesRaw: _num(_stones),
      stonesAfterDiscount: _num(_stonesAfter),
      diamond: _num(_diamond),
      khayas: _num(_khayas),
    );

    if (line.isEmpty) {
      AppSnack.warn(context, 'لا بد من قيمة واحدة على الأقل (ذهب/فصوص/أحجار/ماس/خياس).');
      return;
    }
    if (line.khayas < 0) {
      AppSnack.warn(context, 'لا يمكن إدخال خياس بالسالب.');
      return;
    }

    final dup = _service.duplicateError(
      _pending, line.rowNumber, line.setNumber, skipIndex: _editingIndex);
    if (dup != null) {
      AppSnack.warn(context, dup);
      return;
    }

    setState(() {
      if (_editingIndex == null) {
        _pending.add(line);
      } else {
        _pending[_editingIndex!] = line;
      }
    });
    _clearLineFields();
  }

  void _loadLineForEdit(int index) {
    final l = _pending[index];
    _rowNumber.text = l.rowNumber;
    _setNumber.text = l.setNumber;
    _gold.text = l.gold == 0 ? '' : '${l.gold}';
    _gems.text = l.gems == 0 ? '' : '${l.gems}';
    _stones.text = l.stonesRaw == 0 ? '' : '${l.stonesRaw}';
    _stonesAfter.text = l.stonesAfterDiscount == 0 ? '' : '${l.stonesAfterDiscount}';
    _diamond.text = l.diamond == 0 ? '' : '${l.diamond}';
    _khayas.text = l.khayas == 0 ? '' : '${l.khayas}';
    setState(() => _editingIndex = index);
  }

  Future<void> _commit() async {
    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    final invoiceNo = _invoiceNo.text.trim();
    if (invoiceNo.isEmpty) {
      AppSnack.warn(context, 'لازم تسجل رقم الفاتورة يدوياً قبل الاعتماد.');
      return;
    }
    if (_customer == null) {
      AppSnack.warn(context, 'الرجاء اختيار اسم العميل.');
      return;
    }
    if (_pending.isEmpty) {
      AppSnack.warn(context, 'لا توجد سطور لترحيلها.');
      return;
    }

    setState(() => _busy = true);
    try {
      final txns = _service.buildTransactions(
        lines: _pending,
        customerName: _customer!,
        date: Fmt.operationDate(_date),
        manualInvoiceNo: invoiceNo,
        period: ref.read(periodProvider),
      );
      // كل سطور الفاتورة في معاملة واحدة — لا فاتورة ناقصة لو انقطع الاتصال
      await ref.read(txnRepoProvider).postMany(tenantId, txns);
      bumpDataRevision(ref);

      if (mounted) {
        AppSnack.success(context, 'تم ترحيل الفاتورة وتحديث الخزينة وكل الحسابات.');
        setState(() {
          _pending.clear();
          _invoiceNo.clear();
        });
      }
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _preview() async {
    if (_pending.isEmpty) {
      AppSnack.warn(context, 'لا توجد سطور لمعاينتها.');
      return;
    }
    final tenant = ref.read(sessionProvider).activeTenant;
    await const SalesInvoicePdf().printSummary(
      businessName: tenant?.businessName ?? 'جاديت',
      customerName: _customer ?? '',
      invoiceNo: _invoiceNo.text.trim().isEmpty ? '—' : _invoiceNo.text.trim(),
      date: _date,
      lines: _pending,
      crNumber: tenant?.crNumber,
      vatNumber: tenant?.vatNumber,
      city: tenant?.city,
    );
  }

  @override
  Widget build(BuildContext context) {
    final accounts = ref.watch(accountsProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 150,
                        child: TextField(
                          controller: _invoiceNo,
                          decoration: const InputDecoration(labelText: 'رقم الفاتورة (يدوي)'),
                        ),
                      ),
                      SizedBox(
                        width: 220,
                        child: accounts.when(
                          loading: () => const LinearProgressIndicator(),
                          error: (e, _) => Text('$e'),
                          data: (list) {
                            final names = list
                                .where((a) =>
                                    a.category == 'الموردين' || a.category == 'حسابات عامة')
                                .map((a) => a.name)
                                .toList();
                            return DropdownButtonFormField<String>(
                              value: _customer,
                              isExpanded: true,
                              decoration: const InputDecoration(labelText: 'العميل'),
                              items: names
                                  .map((n) => DropdownMenuItem(value: n, child: Text(n)))
                                  .toList(),
                              onChanged: (v) => setState(() => _customer = v),
                            );
                          },
                        ),
                      ),
                      SizedBox(
                        width: 170,
                        child: InkWell(
                          onTap: () async {
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: _date,
                              firstDate: DateTime(2020),
                              lastDate: DateTime(2100),
                            );
                            if (picked != null) setState(() => _date = picked);
                          },
                          child: InputDecorator(
                            decoration: const InputDecoration(labelText: 'التاريخ'),
                            child: Text(Fmt.date(_date)),
                          ),
                        ),
                      ),
                      SizedBox(
                        width: 140,
                        child: TextFormField(
                          initialValue: '$_discountPct',
                          decoration: const InputDecoration(labelText: 'نسبة خصم الأحجار %'),
                          onChanged: (v) {
                            _discountPct = double.tryParse(v) ?? 30;
                            _recalcStones();
                          },
                        ),
                      ),
                    ],
                  ),
                  const Divider(height: 28),
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: [
                      _field(_rowNumber, 'رقم الصف', width: 100),
                      _field(_setNumber, 'رقم التشغيل', width: 130),
                      _field(_gold, 'الذهب'),
                      _field(_gems, 'الفصوص'),
                      _field(_stones, 'الأحجار', onChanged: (_) => setState(_recalcStones)),
                      _field(_stonesAfter, 'الأحجار بعد الخصم', width: 140),
                      _field(_khayas, 'خياس'),
                      _field(_diamond, 'الماس'),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      FilledButton.icon(
                        onPressed: _addOrUpdateLine,
                        icon: Icon(_editingIndex == null ? Icons.add : Icons.save, size: 18),
                        label: Text(_editingIndex == null ? 'إضافة سطر' : 'حفظ تعديل السطر'),
                      ),
                      const SizedBox(width: 10),
                      OutlinedButton.icon(
                        onPressed: _clearLineFields,
                        icon: const Icon(Icons.cleaning_services, size: 18),
                        label: const Text('تفريغ الخانات'),
                      ),
                      const Spacer(),
                      Text(
                        'الوزن القائم: ${Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.standingWeight))}'
                        '     |     المقيد: ${Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.boundWeight))}',
                        style: const TextStyle(color: AppTheme.gold, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
          DataTableCard(
            title: 'سطور الفاتورة الحالية',
            columns: const [
              'رقم الصف', 'رقم التشغيل', 'الذهب', 'الفصوص', 'الأحجار',
              'الأحجار بعد الخصم', 'الماس', 'خياس', '',
            ],
            rows: [
              for (var i = 0; i < _pending.length; i++)
                DataRow(cells: [
                  DataCell(Text(_pending[i].rowNumber.isEmpty ? '-' : _pending[i].rowNumber)),
                  DataCell(Text(_pending[i].setNumber.isEmpty ? '-' : _pending[i].setNumber)),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].gold))),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].gems))),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].stonesRaw))),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].stonesAfterDiscount))),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].diamond))),
                  DataCell(Text(Fmt.weightOrDash(_pending[i].khayas))),
                  DataCell(Row(children: [
                    IconButton(
                      icon: const Icon(Icons.edit, size: 18),
                      onPressed: () => _loadLineForEdit(i),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                      onPressed: () => setState(() => _pending.removeAt(i)),
                    ),
                  ])),
                ]),
            ],
            totalsRow: _pending.isEmpty
                ? null
                : [
                    'الإجمالي', '-',
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.gold)),
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.gems)),
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.stonesRaw)),
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.stonesAfterDiscount)),
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.diamond)),
                    Fmt.weight(_pending.fold<double>(0, (s, l) => s + l.khayas)),
                    '',
                  ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  // قفل التعديل يمنع تعديل المرحّل فقط — الترحيل الجديد مسموح دائماً
                  onPressed: _busy ? null : _commit,
                  icon: const Icon(Icons.check_circle_outline),
                  label: Text(_busy ? 'جاري الترحيل…' : 'اعتماد وترحيل الفاتورة'),
                ),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                onPressed: _preview,
                icon: const Icon(Icons.print_outlined),
                label: const Text('معاينة وطباعة'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _field(
    TextEditingController controller,
    String label, {
    double width = 110,
    ValueChanged<String>? onChanged,
  }) =>
      SizedBox(
        width: width,
        child: TextField(
          controller: controller,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          textAlign: TextAlign.center,
          onChanged: onChanged,
          decoration: InputDecoration(labelText: label),
        ),
      );
}

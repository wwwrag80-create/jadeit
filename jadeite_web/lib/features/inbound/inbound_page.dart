import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// حركات الوارد للفترة المعروضة
final inboundTxnsProvider = FutureProvider.autoDispose<List<Txn>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return const [];
  return ref.read(txnRepoProvider).byPeriod(tenantId, period, opTypes: OpTypes.inbound);
});

/// شاشة الوارد/قبض: تسجيل الوارد بالعيار مع تحويله تلقائياً لعيار ١٨.
class InboundPage extends ConsumerStatefulWidget {
  const InboundPage({super.key});

  @override
  ConsumerState<InboundPage> createState() => _InboundPageState();
}

class _InboundPageState extends ConsumerState<InboundPage> {
  final _voucher = TextEditingController();
  final _weight = TextEditingController();
  final _carat = TextEditingController();
  final _note = TextEditingController();

  String _type = OpTypes.inboundGold;
  String? _supplier;
  DateTime _date = DateTime.now();
  bool _busy = false;

  @override
  void dispose() {
    _voucher.dispose();
    _weight.dispose();
    _carat.dispose();
    _note.dispose();
    super.dispose();
  }

  /// الذهب يُخزَّن دائماً بمعادل عيار ١٨ حتى تبقى الخزينة بوحدة واحدة
  double get _finalWeight {
    final raw = double.tryParse(_weight.text.trim()) ?? 0;
    if (_type != OpTypes.inboundGold) return raw;
    final carat = double.tryParse(_carat.text.trim()) ?? 0;
    if (carat <= 0) return 0;
    return double.parse(((raw * carat) / 18.0).toStringAsFixed(2));
  }

  Future<void> _submit() async {
    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    final voucher = _voucher.text.trim();
    if (voucher.isEmpty) {
      AppSnack.warn(context, 'لازم تسجل رقم الفاتورة يدوياً قبل الترحيل.');
      return;
    }
    if (_supplier == null || _supplier!.isEmpty) {
      AppSnack.warn(context, 'الرجاء اختيار اسم المورد.');
      return;
    }
    final raw = double.tryParse(_weight.text.trim()) ?? 0;
    if (raw <= 0) {
      AppSnack.warn(context, 'الرجاء إدخال وزن صحيح أكبر من صفر.');
      return;
    }
    if (_type == OpTypes.inboundGold && (double.tryParse(_carat.text.trim()) ?? 0) <= 0) {
      AppSnack.warn(context, 'الرجاء إدخال العيار للذهب.');
      return;
    }

    setState(() => _busy = true);
    try {
      await ref.read(txnRepoProvider).post(
            tenantId,
            Txn.newEntry(
              date: Fmt.operationDate(_date),
              accountName: _supplier!,
              opType: _type,
              weight: _finalWeight,
              weightBefore: raw,
              weightAfter: _type == OpTypes.inboundGold
                  ? (double.tryParse(_carat.text.trim()) ?? 0)
                  : 0,
              // البيان يبقى فارغاً إلا لو سجّل المستخدم بياناً فعلياً
              note: _note.text.trim(),
              setNumber: voucher,
              // الحركة تُثبَّت في الفترة المعروضة مهما كان شهر تاريخها
              period: ref.read(periodProvider),
            ),
          );

      _weight.clear();
      _carat.clear();
      _note.clear();
      // رقم الفاتورة يبقى كما هو ليُكمل المستخدم أسطر نفس الفاتورة
      bumpDataRevision(ref);
      if (mounted) AppSnack.success(context, 'تم ترحيل حركة الوارد وتحديث الخزينة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(Txn txn) async {
    final ok = await confirmDialog(
      context,
      title: 'تأكيد الحذف',
      message: 'حذف حركة الوارد رقم (${txn.setNumber.isEmpty ? txn.seqNo : txn.setNumber}) '
          'بوزن ${Fmt.weight(txn.weight)} جم؟\nسيتم تحديث الخزينة تلقائياً.',
      confirmLabel: 'حذف',
      danger: true,
    );
    if (!ok) return;
    try {
      await ref.read(txnRepoProvider).delete(txn.id);
      bumpDataRevision(ref);
      if (mounted) AppSnack.success(context, 'تم الحذف وتحديث الأرصدة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final accounts = ref.watch(accountsProvider);
    final txns = ref.watch(inboundTxnsProvider);
    final canEdit = ref.watch(sessionProvider).canEdit;

    final suppliers = accounts.maybeWhen(
      data: (list) => [
        OpTypes.factoryAccount,
        ...list.where((a) => a.category == 'الموردين').map((a) => a.name),
        ...KhayasBox.all.map((b) => b.mustarjaName),
      ],
      orElse: () => <String>[OpTypes.factoryAccount],
    );

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text('📥 تسجيل وارد / قبض',
                      style: TextStyle(
                          fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      SizedBox(
                        width: 150,
                        child: TextField(
                          controller: _voucher,
                          decoration: const InputDecoration(labelText: 'رقم الفاتورة'),
                        ),
                      ),
                      SizedBox(
                        width: 170,
                        child: DropdownButtonFormField<String>(
                          value: _supplier,
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: 'الاسم'),
                          items: suppliers
                              .map((s) => DropdownMenuItem(value: s, child: Text(s)))
                              .toList(),
                          onChanged: (v) => setState(() => _supplier = v),
                        ),
                      ),
                      SizedBox(
                        width: 190,
                        child: DropdownButtonFormField<String>(
                          value: _type,
                          isExpanded: true,
                          decoration: const InputDecoration(labelText: 'النوع'),
                          items: OpTypes.inbound
                              .map((t) => DropdownMenuItem(value: t, child: Text(t)))
                              .toList(),
                          onChanged: (v) => setState(() => _type = v ?? OpTypes.inboundGold),
                        ),
                      ),
                      SizedBox(
                        width: 120,
                        child: TextField(
                          controller: _weight,
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setState(() {}),
                          decoration: const InputDecoration(labelText: 'الوزن'),
                        ),
                      ),
                      if (_type == OpTypes.inboundGold)
                        SizedBox(
                          width: 110,
                          child: TextField(
                            controller: _carat,
                            keyboardType: TextInputType.number,
                            onChanged: (_) => setState(() {}),
                            decoration: const InputDecoration(labelText: 'العيار'),
                          ),
                        ),
                      SizedBox(
                        width: 150,
                        child: InkWell(
                          onTap: () async {
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: _date,
                              firstDate: DateTime(2015),
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
                        width: 220,
                        child: TextField(
                          controller: _note,
                          decoration: const InputDecoration(labelText: 'البيان (اختياري)'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      if (_type == OpTypes.inboundGold)
                        Text('الوزن المعادل عيار ١٨: ${Fmt.weight(_finalWeight)} جم',
                            style: const TextStyle(
                                color: AppTheme.blue, fontWeight: FontWeight.bold)),
                      const Spacer(),
                      FilledButton.icon(
                        onPressed: _busy ? null : _submit,
                        icon: const Icon(Icons.save_outlined),
                        label: const Text('ترحيل الحركة'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          txns.when(
            loading: () => const Center(child: Padding(
                padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double total = 0;
              final rows = list.map((t) {
                total += t.weight;
                return DataRow(cells: [
                  DataCell(Text(t.setNumber.isEmpty ? '${t.seqNo}' : t.setNumber)),
                  DataCell(Text(Fmt.dateTime(t.date))),
                  DataCell(Text(t.accountName)),
                  DataCell(Text(t.opType.replaceFirst('وارد ', ''))),
                  DataCell(Text(Fmt.weightOrDash(t.weightBefore))),
                  DataCell(Text(t.weightAfter > 0 ? Fmt.carat(t.weightAfter) : '-')),
                  DataCell(Text(Fmt.weight(t.weight))),
                  DataCell(Text(t.note)),
                  DataCell(Row(children: [
                    IconButton(
                      tooltip: canEdit ? 'تعديل' : 'التعديل مقفول من المدير',
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      onPressed: canEdit
                          ? () => _showEditDialog(t)
                          : () => AppSnack.warn(context,
                              'التعديل مقفول من المدير — الحذف والتسجيل ما زالا متاحين.'),
                    ),
                    IconButton(
                      tooltip: 'حذف',
                      icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                      onPressed: () => _delete(t),
                    ),
                  ])),
                ]);
              }).toList();

              return DataTableCard(
                title: '📋 كشف حركة الوارد — ${ref.watch(periodProvider)}',
                columns: const [
                  'رقم الفاتورة', 'التاريخ', 'الاسم', 'النوع',
                  'الوزن الخام', 'العيار', 'وزن ١٨', 'البيان', 'إجراءات',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : ['الإجمالي', '-', '-', '-', '-', '-', Fmt.weight(total), '-', '-'],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _showEditDialog(Txn txn) async {
    final weight = TextEditingController(text: txn.weightBefore.toString());
    final carat = TextEditingController(text: txn.weightAfter.toString());
    final note = TextEditingController(text: txn.note);

    final saved = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('تعديل حركة الوارد #${txn.seqNo}'),
        content: SizedBox(
          width: 340,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: weight,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'الوزن الخام')),
            const SizedBox(height: 10),
            TextField(
                controller: carat,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'العيار')),
            const SizedBox(height: 10),
            TextField(controller: note, decoration: const InputDecoration(labelText: 'البيان')),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('حفظ')),
        ],
      ),
    );
    if (saved != true) return;

    final raw = double.tryParse(weight.text.trim()) ?? 0;
    final c = double.tryParse(carat.text.trim()) ?? 0;
    if (raw <= 0) {
      if (mounted) AppSnack.warn(context, 'الوزن غير صحيح.');
      return;
    }
    final finalW = txn.opType == OpTypes.inboundGold && c > 0
        ? double.parse(((raw * c) / 18.0).toStringAsFixed(2))
        : raw;

    try {
      await ref.read(txnRepoProvider).update(txn.id, {
        'weight': finalW,
        'weight_before': raw,
        'weight_after': c,
        'note': note.text.trim(),
      });
      bumpDataRevision(ref);
      if (mounted) AppSnack.success(context, 'تم التعديل وتحديث الأرصدة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    }
  }
}

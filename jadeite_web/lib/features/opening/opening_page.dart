import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// القيود الافتتاحية (كل الفترات — لأنها أساس الأرصدة وليست حركة شهرية)
final openingTxnsProvider = FutureProvider.autoDispose<List<Txn>>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  if (tenantId == null) return const [];
  return ref.read(txnRepoProvider).openingEntries(tenantId);
});

/// شاشة الرصيد الافتتاحي: تسجيل وتعديل وحذف القيود الافتتاحية.
class OpeningPage extends ConsumerStatefulWidget {
  const OpeningPage({super.key});

  @override
  ConsumerState<OpeningPage> createState() => _OpeningPageState();
}

class _OpeningPageState extends ConsumerState<OpeningPage> {
  final _weight = TextEditingController();
  final _carat = TextEditingController();
  String _type = OpTypes.inboundGold;
  String? _name;
  DateTime _date = DateTime.now();
  bool _busy = false;

  @override
  void dispose() {
    _weight.dispose();
    _carat.dispose();
    super.dispose();
  }

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
    final raw = double.tryParse(_weight.text.trim()) ?? 0;

    if (_name == null || _name!.isEmpty) {
      AppSnack.warn(context, 'الرجاء اختيار الاسم.');
      return;
    }
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
              date: _date,
              accountName: _name!,
              opType: _type,
              weight: _finalWeight,
              weightBefore: raw,
              weightAfter: _type == OpTypes.inboundGold
                  ? (double.tryParse(_carat.text.trim()) ?? 0)
                  : 0,
              note: OpTypes.openingNote,
              treesCount: OpTypes.openingMarker,
            ),
          );
      _weight.clear();
      _carat.clear();
      ref.invalidate(openingTxnsProvider);
      ref.invalidate(treasuryProvider);
      if (mounted) AppSnack.success(context, 'تم تسجيل القيد الافتتاحي وتحديث الخزينة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final accounts = ref.watch(accountsProvider);
    final entries = ref.watch(openingTxnsProvider);
    final canEdit = ref.watch(sessionProvider).canEdit;

    final names = accounts.maybeWhen(
      data: (list) => [
        OpTypes.factoryAccount,
        ...list.where((a) => a.category == 'الموردين').map((a) => a.name),
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
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const Text('⚖️ تسجيل رصيد افتتاحي',
                    style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                const SizedBox(height: 6),
                const Text(
                  'القيد الافتتاحي هو رصيدك قبل بدء التسجيل في النظام، ويدخل مباشرة في الخزينة.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 14),
                Wrap(spacing: 12, runSpacing: 12, children: [
                  SizedBox(
                    width: 190,
                    child: DropdownButtonFormField<String>(
                      value: _name,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'الاسم'),
                      items:
                          names.map((n) => DropdownMenuItem(value: n, child: Text(n))).toList(),
                      onChanged: (v) => setState(() => _name = v),
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
                ]),
                const SizedBox(height: 14),
                Row(children: [
                  if (_type == OpTypes.inboundGold)
                    Text('الوزن المعادل عيار ١٨: ${Fmt.weight(_finalWeight)} جم',
                        style:
                            const TextStyle(color: AppTheme.blue, fontWeight: FontWeight.bold)),
                  const Spacer(),
                  FilledButton.icon(
                    onPressed: _busy ? null : _submit,
                    icon: const Icon(Icons.save_outlined),
                    label: const Text('تسجيل القيد'),
                  ),
                ]),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          entries.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double totalGold = 0;
              final rows = list.map((t) {
                if (t.opType == OpTypes.inboundGold) totalGold += t.weight;
                return DataRow(cells: [
                  DataCell(Text('${t.seqNo}')),
                  DataCell(Text(Fmt.date(t.date))),
                  DataCell(Text(t.accountName)),
                  DataCell(Text(t.opType.replaceFirst('وارد ', ''))),
                  DataCell(Text(Fmt.weightOrDash(t.weightBefore))),
                  DataCell(Text(t.weightAfter > 0 ? Fmt.carat(t.weightAfter) : '-')),
                  DataCell(Text(Fmt.weight(t.weight))),
                  DataCell(Row(children: [
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 18),
                      tooltip: canEdit ? 'تعديل' : 'التعديل مقفول من المدير',
                      onPressed: canEdit
                          ? () => _edit(t)
                          : () => AppSnack.warn(context,
                              'التعديل مقفول من المدير — الحذف والتسجيل ما زالا متاحين.'),
                    ),
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                      tooltip: 'حذف',
                      onPressed: () => _delete(t),
                    ),
                  ])),
                ]);
              }).toList();

              return DataTableCard(
                title: 'القيود الافتتاحية المسجّلة',
                columns: const [
                  'رقم الحركة', 'التاريخ', 'الاسم', 'النوع', 'الوزن', 'العيار', 'وزن ١٨', 'إجراءات',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : ['-', '-', '-', 'إجمالي الذهب (عيار ١٨)', '-', '-', Fmt.weight(totalGold), '-'],
                emptyMessage: 'لا توجد قيود افتتاحية مسجّلة',
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _delete(Txn txn) async {
    final ok = await confirmDialog(
      context,
      title: 'حذف القيد الافتتاحي',
      message: 'حذف القيد رقم (${txn.seqNo}) — ${txn.accountName} '
          'بوزن ${Fmt.weight(txn.weight)} جم؟\nسيتم إعادة حساب الخزينة تلقائياً.',
      danger: true,
    );
    if (!ok) return;
    try {
      await ref.read(txnRepoProvider).delete(txn.id);
      ref.invalidate(openingTxnsProvider);
      ref.invalidate(treasuryProvider);
      if (mounted) AppSnack.success(context, 'تم الحذف وتحديث كل الأرصدة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    }
  }

  Future<void> _edit(Txn txn) async {
    final weight = TextEditingController(text: txn.weightBefore.toString());
    final carat = TextEditingController(text: txn.weightAfter.toString());

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('تعديل القيد الافتتاحي #${txn.seqNo}'),
        content: SizedBox(
          width: 320,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(
                controller: weight,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'الوزن')),
            const SizedBox(height: 10),
            TextField(
                controller: carat,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'العيار (للذهب)')),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('حفظ')),
        ],
      ),
    );
    if (ok != true) return;

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
      });
      ref.invalidate(openingTxnsProvider);
      ref.invalidate(treasuryProvider);
      if (mounted) AppSnack.success(context, 'تم التعديل وإعادة حساب كل الأرصدة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    }
  }
}

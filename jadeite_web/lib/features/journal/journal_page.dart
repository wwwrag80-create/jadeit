import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// القيود اليومية للفترة المعروضة، مجمّعة في قيد واحد بطرفيه
final journalEntriesProvider =
    FutureProvider.autoDispose<List<JournalEntry>>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return const [];
  return ref.read(ledgerRepoProvider).journalEntries(tenantId, period);
});

/// شاشة القيود اليومية: نقل وزن بين حسابين بقيد مزدوج متوازن.
class JournalPage extends ConsumerStatefulWidget {
  const JournalPage({super.key});

  @override
  ConsumerState<JournalPage> createState() => _JournalPageState();
}

class _JournalPageState extends ConsumerState<JournalPage> {
  final _weight = TextEditingController();
  final _note = TextEditingController();
  String? _from;
  String? _to;
  DateTime _date = DateTime.now();
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _date = Fmt.smartDefaultDate(ref.read(periodProvider));
  }

  @override
  void dispose() {
    _weight.dispose();
    _note.dispose();
    super.dispose();
  }

  /// كل الحسابات التي يصح أن تكون طرفاً في قيد يومي
  List<String> _accountOptions(List<Account> accounts) => [
        OpTypes.factoryAccount,
        OpTypes.treasuryAccount,
        OpTypes.salesAccount,
        OpTypes.lossesAccount,
        ...KhayasBox.all.map((b) => b.name),
        ...accounts.map((a) => a.name),
      ];

  Future<void> _submit() async {
    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    final weight = double.tryParse(_weight.text.trim()) ?? 0;
    if (_from == null || _to == null) {
      AppSnack.warn(context, 'الرجاء تحديد الحساب الدائن والحساب المدين.');
      return;
    }
    if (_from == _to) {
      AppSnack.warn(context, 'لا يصح أن يكون الطرف المدين هو نفسه الطرف الدائن.');
      return;
    }
    if (weight <= 0) {
      AppSnack.warn(context, 'الرجاء إدخال وزن أكبر من صفر.');
      return;
    }

    setState(() => _busy = true);
    try {
      final ref0 = await ref.read(journalRepoProvider).post(
            tenantId: tenantId,
            date: _date,
            fromAccount: _from!,
            toAccount: _to!,
            weight: weight,
            note: _note.text.trim(),
          );
      _weight.clear();
      _note.clear();
      ref.invalidate(journalEntriesProvider);
      ref.invalidate(treasuryProvider);
      if (mounted) AppSnack.success(context, 'تم ترحيل القيد ($ref0) بطرفيه.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _delete(JournalEntry entry) async {
    final ok = await confirmDialog(
      context,
      title: 'حذف القيد',
      message: 'حذف القيد (${entry.ref}) بوزن ${Fmt.weight(entry.weight)} جم؟\n\n'
          'سيتم حذف طرفي القيد معاً (المدين والدائن) حفاظاً على توازن الدفاتر، '
          'وإعادة حساب كل الأرصدة تلقائياً.',
      confirmLabel: 'حذف',
      danger: true,
    );
    if (!ok) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;
    try {
      final count = await ref.read(journalRepoProvider).delete(tenantId, entry.ref);
      ref.invalidate(journalEntriesProvider);
      ref.invalidate(treasuryProvider);
      if (mounted) AppSnack.success(context, 'تم حذف $count حركة وتحديث الأرصدة.');
    } catch (e) {
      if (mounted) AppSnack.error(context, '$e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final accounts = ref.watch(accountsProvider);
    final entries = ref.watch(journalEntriesProvider);
    final period = ref.watch(periodProvider);

    final options = accounts.maybeWhen(
      data: _accountOptions,
      orElse: () => <String>[OpTypes.factoryAccount, OpTypes.treasuryAccount],
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
                const Text('📒 تسجيل قيد يومي',
                    style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                const SizedBox(height: 6),
                const Text(
                  'القيد ينقل وزناً من حساب إلى حساب: يُخصم من الدائن ويُضاف للمدين. '
                  'الطرفان يُسجَّلان معاً دائماً، فلا يبقى قيد غير متوازن.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 14),
                Wrap(spacing: 12, runSpacing: 12, children: [
                  SizedBox(
                    width: 230,
                    child: DropdownButtonFormField<String>(
                      value: _from,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'من حساب (دائن — يُخصم منه)'),
                      items: options
                          .map((n) => DropdownMenuItem(value: n, child: Text(n)))
                          .toList(),
                      onChanged: (v) => setState(() => _from = v),
                    ),
                  ),
                  const Icon(Icons.arrow_back, color: AppTheme.gold),
                  SizedBox(
                    width: 230,
                    child: DropdownButtonFormField<String>(
                      value: _to,
                      isExpanded: true,
                      decoration: const InputDecoration(labelText: 'إلى حساب (مدين — يُضاف إليه)'),
                      items: options
                          .map((n) => DropdownMenuItem(value: n, child: Text(n)))
                          .toList(),
                      onChanged: (v) => setState(() => _to = v),
                    ),
                  ),
                  SizedBox(
                    width: 130,
                    child: TextField(
                      controller: _weight,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'الوزن'),
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
                    width: 260,
                    child: TextField(
                      controller: _note,
                      decoration: const InputDecoration(labelText: 'البيان'),
                    ),
                  ),
                ]),
                const SizedBox(height: 14),
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: FilledButton.icon(
                    onPressed: _busy ? null : _submit,
                    icon: const Icon(Icons.post_add_outlined),
                    label: const Text('ترحيل القيد'),
                  ),
                ),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          entries.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double total = 0;
              final rows = list.map((e) {
                total += e.weight;
                return DataRow(cells: [
                  DataCell(Row(children: [
                    if (!e.isBalanced)
                      const Padding(
                        padding: EdgeInsetsDirectional.only(end: 6),
                        child: Tooltip(
                          message: 'قيد غير متوازن — راجعه',
                          child: Icon(Icons.warning_amber_rounded,
                              size: 16, color: AppTheme.warn),
                        ),
                      ),
                    Text(e.ref),
                  ])),
                  DataCell(Text(Fmt.dateTime(e.date))),
                  DataCell(Text(e.debitAccount)),
                  DataCell(Text(e.creditAccount)),
                  DataCell(Text(Fmt.weight(e.weight))),
                  DataCell(Text(e.note)),
                  DataCell(IconButton(
                    tooltip: 'حذف القيد بطرفيه',
                    icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                    onPressed: () => _delete(e),
                  )),
                ]);
              }).toList();

              return DataTableCard(
                title: 'القيود اليومية — $period',
                columns: const [
                  'المرجع', 'التاريخ', 'مدين (إلى)', 'دائن (من)', 'الوزن', 'البيان', 'إجراءات',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : ['الإجمالي', '-', '-', '-', Fmt.weight(total), '-', '-'],
                emptyMessage: 'لا توجد قيود يومية في $period',
              );
            },
          ),
        ],
      ),
    );
  }
}

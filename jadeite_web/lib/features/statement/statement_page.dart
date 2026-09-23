import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../printing/statement_pdf.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

final statementAccountProvider = StateProvider<String?>((_) => null);

final statementRowsProvider = FutureProvider.autoDispose<List<Txn>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final account = ref.watch(statementAccountProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null || account == null) return const [];
  return ref.read(txnRepoProvider).byAccount(tenantId, account, period);
});

/// رصيد الحساب قبل الفترة المعروضة — يبدأ منه الرصيد المتحرك، فلا يبدأ كل شهر
/// من الصفر كأن الحساب بلا تاريخ
final statementOpeningProvider = FutureProvider.autoDispose<double>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final account = ref.watch(statementAccountProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null || account == null) return 0;
  return ref.read(ledgerRepoProvider).accountOpeningBalance(
        tenantId,
        account,
        period,
        StatementPage.debitTypes.toList(),
      );
});

/// كشف حساب أي طرف: مدين/دائن/رصيد متحرك، مع تصدير PDF عربي.
class StatementPage extends ConsumerWidget {
  const StatementPage({super.key});

  /// الأنواع التي تُعتبر مديناً على الحساب (خرج من الخزينة إليه)
  static const debitTypes = {
    OpTypes.issueGold,
    OpTypes.saleGold,
    OpTypes.saleGoldWithDiamond,
    OpTypes.saleGemsStones,
    OpTypes.saleDiamond,
    OpTypes.journalDebit,
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final accounts = ref.watch(accountsProvider);
    final account = ref.watch(statementAccountProvider);
    final rows = ref.watch(statementRowsProvider);
    final opening = ref.watch(statementOpeningProvider);
    final period = ref.watch(periodProvider);

    final names = accounts.maybeWhen(
      data: (list) => [
        OpTypes.factoryAccount,
        ...list.map((a) => a.name),
        ...KhayasBox.all.map((b) => b.name),
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
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                const Text('الحساب: ', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(width: 8),
                SizedBox(
                  width: 280,
                  child: DropdownButtonFormField<String>(
                    value: names.contains(account) ? account : null,
                    isExpanded: true,
                    decoration: const InputDecoration(isDense: true),
                    items:
                        names.map((n) => DropdownMenuItem(value: n, child: Text(n))).toList(),
                    onChanged: (v) =>
                        ref.read(statementAccountProvider.notifier).state = v,
                  ),
                ),
                const Spacer(),
                if (account != null)
                  OutlinedButton.icon(
                    onPressed: () => _print(context, ref, account, period),
                    icon: const Icon(Icons.print_outlined),
                    label: const Text('طباعة الكشف'),
                  ),
              ]),
            ),
          ),
          const SizedBox(height: 14),
          if (account == null)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(child: Text('اختر حساباً لعرض كشفه')),
            )
          else
            rows.when(
              loading: () => const Center(
                  child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
              error: (e, _) => Center(child: Text('$e')),
              data: (list) {
                final openingBalance = opening.valueOrNull ?? 0;
                double running = openingBalance, tDebit = 0, tCredit = 0;
                final dataRows = list.map((t) {
                  final isDebit = debitTypes.contains(t.opType);
                  final debit = isDebit ? t.weight : 0.0;
                  final credit = isDebit ? 0.0 : t.weight;
                  running += debit - credit;
                  tDebit += debit;
                  tCredit += credit;
                  return DataRow(cells: [
                    DataCell(Text('${t.seqNo}')),
                    DataCell(Text(Fmt.dateTime(t.date))),
                    DataCell(Text(t.opType)),
                    DataCell(Text(Fmt.weightOrDash(debit))),
                    DataCell(Text(Fmt.weightOrDash(credit))),
                    DataCell(Text(Fmt.weight(running))),
                    DataCell(Text(t.note)),
                  ]);
                }).toList();

                return DataTableCard(
                  title: 'كشف حساب: $account — $period',
                  columns: const [
                    'رقم الحركة', 'التاريخ', 'النوع', 'مدين', 'دائن', 'الرصيد', 'البيان',
                  ],
                  rows: [
                    if (openingBalance != 0 || dataRows.isNotEmpty)
                      DataRow(cells: [
                        const DataCell(Text('-')),
                        const DataCell(Text('-')),
                        const DataCell(Text('رصيد أول المدة')),
                        const DataCell(Text('-')),
                        const DataCell(Text('-')),
                        DataCell(Text(Fmt.weight(openingBalance))),
                        const DataCell(Text('مُرحَّل من الفترات السابقة')),
                      ]),
                    ...dataRows,
                  ],
                  totalsRow: dataRows.isEmpty
                      ? null
                      : [
                          'الإجمالي', '-', '-', Fmt.weight(tDebit), Fmt.weight(tCredit),
                          Fmt.weight(running), '-',
                        ],
                );
              },
            ),
        ],
      ),
    );
  }

  Future<void> _print(
      BuildContext context, WidgetRef ref, String account, String period) async {
    final List<Txn> list;
    final double openingBalance;
    try {
      list = await ref.read(statementRowsProvider.future);
      openingBalance = await ref.read(statementOpeningProvider.future);
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
      return;
    }
    if (list.isEmpty && openingBalance == 0) {
      if (context.mounted) AppSnack.warn(context, 'لا توجد حركات لطباعتها في هذه الفترة.');
      return;
    }
    final tenant = ref.read(sessionProvider).activeTenant;
    double running = openingBalance, tDebit = 0, tCredit = 0;
    final rows = <List<String>>[
      ['-', '-', 'رصيد أول المدة', '-', '-', Fmt.weight(openingBalance), 'مُرحَّل من الفترات السابقة'],
    ];

    for (final t in list) {
      final isDebit = debitTypes.contains(t.opType);
      final debit = isDebit ? t.weight : 0.0;
      final credit = isDebit ? 0.0 : t.weight;
      running += debit - credit;
      tDebit += debit;
      tCredit += credit;
      rows.add([
        '${t.seqNo}',
        Fmt.dateTime(t.date),
        t.opType,
        Fmt.weightOrDash(debit),
        Fmt.weightOrDash(credit),
        Fmt.weight(running),
        t.note,
      ]);
    }

    await const StatementPdf().print(
      businessName: tenant?.businessName ?? 'جاديت',
      title: 'كشف حساب — $account',
      subtitle: 'الفترة: $period',
      columns: const ['رقم الحركة', 'التاريخ', 'النوع', 'مدين', 'دائن', 'الرصيد', 'البيان'],
      rows: rows,
      totalsRow: [
        'الإجمالي', '-', '-', Fmt.weight(tDebit), Fmt.weight(tCredit), Fmt.weight(running), '-',
      ],
      columnWidths: const [1.0, 1.6, 1.8, 1.1, 1.1, 1.2, 2.2],
    );
  }
}

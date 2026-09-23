import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../printing/statement_pdf.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// إجماليات كل الصناديق للفترة المعروضة
final allBoxesTotalsProvider =
    FutureProvider.autoDispose<Map<String, ({double madin, double daen, double khayas})>>(
        (ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return {};

  final repo = ref.read(ledgerRepoProvider);
  final result = <String, ({double madin, double daen, double khayas})>{};
  for (final box in KhayasBox.all) {
    result[box.name] = await repo.boxTotals(tenantId, box.name, period);
  }
  return result;
});

/// التقرير الشهري: صورة كاملة عن الفترة في صفحة واحدة.
class ReportsPage extends ConsumerWidget {
  const ReportsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final period = ref.watch(periodProvider);
    final treasury = ref.watch(treasuryProvider);
    final losses = ref.watch(workshopLossesProvider);
    final invoices = ref.watch(salesInvoicesProvider);
    final boxes = ref.watch(allBoxesTotalsProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Text('📊 التقرير الشهري — $period',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.gold)),
            const Spacer(),
            OutlinedButton.icon(
              onPressed: () => _print(context, ref),
              icon: const Icon(Icons.print_outlined),
              label: const Text('طباعة التقرير'),
            ),
          ]),
          const SizedBox(height: 14),

          // ---------- مؤشرات عامة ----------
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Wrap(spacing: 34, runSpacing: 16, children: [
                _Kpi(
                  label: 'رصيد الخزينة',
                  value: treasury.maybeWhen(
                      data: (v) => '${Fmt.weight(v)} جم', orElse: () => '...'),
                  color: AppTheme.gold,
                ),
                _Kpi(
                  label: 'إجمالي فواقد الورشة',
                  value:
                      losses.maybeWhen(data: (v) => '${Fmt.weight(v)} جم', orElse: () => '...'),
                  color: AppTheme.warn,
                ),
                _Kpi(
                  label: 'عدد فواتير المبيعات',
                  value: invoices.maybeWhen(
                      data: (v) => '${v.length}', orElse: () => '...'),
                  color: AppTheme.blue,
                ),
                _Kpi(
                  label: 'إجمالي ذهب المبيعات',
                  value: invoices.maybeWhen(
                    data: (v) =>
                        '${Fmt.weight(v.fold<double>(0, (s, i) => s + i.gold))} جم',
                    orElse: () => '...',
                  ),
                  color: AppTheme.success,
                ),
              ]),
            ),
          ),
          const SizedBox(height: 16),

          // ---------- صناديق الخياس ----------
          boxes.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (map) {
              double tM = 0, tD = 0, tK = 0;
              final rows = KhayasBox.all.map((b) {
                final t = map[b.name] ?? (madin: 0.0, daen: 0.0, khayas: 0.0);
                tM += t.madin;
                tD += t.daen;
                tK += t.khayas;
                return DataRow(cells: [
                  DataCell(Text('${b.icon} ${b.name}')),
                  DataCell(Text(Fmt.weightOrDash(t.madin))),
                  DataCell(Text(Fmt.weightOrDash(t.daen))),
                  DataCell(Text(Fmt.weight(t.khayas))),
                ]);
              }).toList();

              return DataTableCard(
                title: 'صناديق الخياس خلال $period',
                columns: const ['الصندوق', 'مدين (صرف)', 'دائن (قبض/مسترجع)', 'الخياس'],
                rows: rows,
                totalsRow: [
                  'الإجمالي', Fmt.weight(tM), Fmt.weight(tD), Fmt.weight(tK),
                ],
              );
            },
          ),
          const SizedBox(height: 16),

          // ---------- فواتير المبيعات ----------
          invoices.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double gold = 0, gems = 0, stones = 0, diamond = 0, khayas = 0;
              final rows = list.map((inv) {
                gold += inv.gold;
                gems += inv.gems;
                stones += inv.stonesAfter;
                diamond += inv.diamond;
                khayas += inv.khayas;
                return DataRow(cells: [
                  DataCell(Text(inv.manualNo.isEmpty ? '-' : inv.manualNo)),
                  DataCell(Text(Fmt.date(inv.date))),
                  DataCell(Text(inv.accountName)),
                  DataCell(Text(Fmt.weightOrDash(inv.gold))),
                  DataCell(Text(Fmt.weightOrDash(inv.gems))),
                  DataCell(Text(Fmt.weightOrDash(inv.stonesAfter))),
                  DataCell(Text(Fmt.weightOrDash(inv.diamond))),
                  DataCell(Text(Fmt.weightOrDash(inv.khayas))),
                ]);
              }).toList();

              return DataTableCard(
                title: 'فواتير المبيعات خلال $period',
                columns: const [
                  'رقم الفاتورة', 'التاريخ', 'الاسم', 'الذهب', 'الفصوص',
                  'الأحجار بعد الخصم', 'الماس', 'خياس',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : [
                        'الإجمالي', '-', '-', Fmt.weight(gold), Fmt.weight(gems),
                        Fmt.weight(stones), Fmt.weight(diamond), Fmt.weight(khayas),
                      ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _print(BuildContext context, WidgetRef ref) async {
    final period = ref.read(periodProvider);
    final tenant = ref.read(sessionProvider).activeTenant;
    final boxes = await ref.read(allBoxesTotalsProvider.future);
    final treasury = await ref.read(treasuryProvider.future);
    final losses = await ref.read(workshopLossesProvider.future);

    final rows = KhayasBox.all
        .map((b) {
          final t = boxes[b.name] ?? (madin: 0.0, daen: 0.0, khayas: 0.0);
          return [b.name, Fmt.weight(t.madin), Fmt.weight(t.daen), Fmt.weight(t.khayas)];
        })
        .toList();

    try {
      await const StatementPdf().print(
        businessName: tenant?.businessName ?? 'جاديت',
        title: 'التقرير الشهري',
        subtitle: 'الفترة: $period   |   رصيد الخزينة: ${Fmt.weight(treasury)} جم   |   '
            'إجمالي الفواقد: ${Fmt.weight(losses)} جم',
        columns: const ['الصندوق', 'مدين', 'دائن', 'الخياس'],
        rows: rows,
        totalsRow: [
          'الإجمالي',
          Fmt.weight(boxes.values.fold<double>(0, (s, t) => s + t.madin)),
          Fmt.weight(boxes.values.fold<double>(0, (s, t) => s + t.daen)),
          Fmt.weight(boxes.values.fold<double>(0, (s, t) => s + t.khayas)),
        ],
      );
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({required this.label, required this.value, required this.color});
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 6),
        Text(value,
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}

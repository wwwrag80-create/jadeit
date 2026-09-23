import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

// ---------- حالة الأرشيف ----------
final archiveQueryProvider = StateProvider<String>((_) => '');
final archiveAllPeriodsProvider = StateProvider<bool>((_) => false);

final invoiceArchiveProvider =
    FutureProvider.autoDispose<List<ArchivedInvoice>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  final allPeriods = ref.watch(archiveAllPeriodsProvider);
  final query = ref.watch(archiveQueryProvider);
  if (tenantId == null) return const [];
  return ref.read(ledgerRepoProvider).invoiceArchive(
        tenantId,
        period: allPeriods ? null : period,
        query: query,
      );
});

// ---------- حالة البحث الموحّد ----------
final searchSourceProvider = StateProvider<String>((_) => SearchSource.sales);
final searchQueryProvider = StateProvider<String>((_) => '');

final unifiedSearchProvider = FutureProvider.autoDispose<List<Txn>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final source = ref.watch(searchSourceProvider);
  final query = ref.watch(searchQueryProvider);
  if (tenantId == null || query.trim().isEmpty) return const [];
  return ref.read(txnRepoProvider).search(
        tenantId: tenantId,
        source: source,
        query: query,
      );
});

/// أرشيف الفواتير + البحث الموحّد مع تحديد الشاشة.
class ArchivePage extends ConsumerWidget {
  const ArchivePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return const DefaultTabController(
      length: 2,
      child: Column(
        children: [
          Material(
            color: Colors.transparent,
            child: TabBar(
              tabs: [
                Tab(text: '🗄️  أرشيف الفواتير'),
                Tab(text: '🔎  البحث الموحّد'),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              children: [_ArchiveTab(), _SearchTab()],
            ),
          ),
        ],
      ),
    );
  }
}

// ============================================================================
//  تبويب الأرشيف
// ============================================================================
class _ArchiveTab extends ConsumerStatefulWidget {
  const _ArchiveTab();

  @override
  ConsumerState<_ArchiveTab> createState() => _ArchiveTabState();
}

class _ArchiveTabState extends ConsumerState<_ArchiveTab> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final invoices = ref.watch(invoiceArchiveProvider);
    final allPeriods = ref.watch(archiveAllPeriodsProvider);
    final period = ref.watch(periodProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Wrap(
                spacing: 12,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  SizedBox(
                    width: 300,
                    child: TextField(
                      controller: _controller,
                      decoration: const InputDecoration(
                        labelText: 'بحث برقم الفاتورة أو رقم التشغيل أو الاسم',
                        prefixIcon: Icon(Icons.search),
                      ),
                      onSubmitted: (v) =>
                          ref.read(archiveQueryProvider.notifier).state = v.trim(),
                    ),
                  ),
                  FilledButton(
                    onPressed: () => ref.read(archiveQueryProvider.notifier).state =
                        _controller.text.trim(),
                    child: const Text('بحث'),
                  ),
                  OutlinedButton(
                    onPressed: () {
                      _controller.clear();
                      ref.read(archiveQueryProvider.notifier).state = '';
                    },
                    child: const Text('مسح'),
                  ),
                  FilterChip(
                    label: Text(allPeriods ? 'كل الفترات' : 'الفترة الحالية ($period)'),
                    selected: allPeriods,
                    onSelected: (v) =>
                        ref.read(archiveAllPeriodsProvider.notifier).state = v,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 14),
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
                  DataCell(Text(Fmt.dateTime(inv.date))),
                  DataCell(Text(inv.accountName)),
                  DataCell(Text(Fmt.weightOrDash(inv.gold))),
                  DataCell(Text(Fmt.weightOrDash(inv.gems))),
                  DataCell(Text(Fmt.weightOrDash(inv.stonesAfter))),
                  DataCell(Text(Fmt.weightOrDash(inv.diamond))),
                  DataCell(Text(Fmt.weightOrDash(inv.khayas))),
                  DataCell(Text('${inv.linesCount}')),
                  DataCell(
                    SizedBox(
                      width: 150,
                      child: Text(inv.setNumbers,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontSize: 11, color: Colors.grey)),
                    ),
                  ),
                ]);
              }).toList();

              return DataTableCard(
                title: allPeriods
                    ? 'أرشيف الفواتير — كل الفترات (${list.length} فاتورة)'
                    : 'أرشيف الفواتير — $period (${list.length} فاتورة)',
                columns: const [
                  'رقم الفاتورة', 'التاريخ', 'الاسم', 'الذهب', 'الفصوص',
                  'الأحجار بعد الخصم', 'الماس', 'خياس', 'الأسطر', 'أرقام التشغيل',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : [
                        'الإجمالي', '-', '-', Fmt.weight(gold), Fmt.weight(gems),
                        Fmt.weight(stones), Fmt.weight(diamond), Fmt.weight(khayas), '-', '-',
                      ],
                emptyMessage: 'لا توجد فواتير مطابقة',
              );
            },
          ),
        ],
      ),
    );
  }
}

// ============================================================================
//  تبويب البحث الموحّد
// ============================================================================
class _SearchTab extends ConsumerStatefulWidget {
  const _SearchTab();

  @override
  ConsumerState<_SearchTab> createState() => _SearchTabState();
}

class _SearchTabState extends ConsumerState<_SearchTab> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _run() => ref.read(searchQueryProvider.notifier).state = _controller.text.trim();

  @override
  Widget build(BuildContext context) {
    final source = ref.watch(searchSourceProvider);
    final results = ref.watch(unifiedSearchProvider);
    final query = ref.watch(searchQueryProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const Text(
                  'أرقام الفواتير قد تتشابه بين الشاشات، لذلك حدّد الشاشة التي تمت فيها الفاتورة '
                  'ثم اكتب رقمها.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    SizedBox(
                      width: 200,
                      child: DropdownButtonFormField<String>(
                        value: source,
                        isExpanded: true,
                        decoration: const InputDecoration(labelText: 'الشاشة'),
                        items: SearchSource.options
                            .map((o) =>
                                DropdownMenuItem(value: o.key, child: Text(o.label)))
                            .toList(),
                        onChanged: (v) => ref.read(searchSourceProvider.notifier).state =
                            v ?? SearchSource.sales,
                      ),
                    ),
                    SizedBox(
                      width: 220,
                      child: TextField(
                        controller: _controller,
                        decoration: const InputDecoration(
                          labelText: 'الرقم',
                          prefixIcon: Icon(Icons.numbers),
                        ),
                        onSubmitted: (_) => _run(),
                      ),
                    ),
                    FilledButton.icon(
                      onPressed: _run,
                      icon: const Icon(Icons.search),
                      label: const Text('بحث'),
                    ),
                  ],
                ),
              ]),
            ),
          ),
          const SizedBox(height: 14),
          if (query.trim().isEmpty)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(child: Text('اكتب رقماً وحدّد الشاشة لبدء البحث')),
            )
          else
            results.when(
              loading: () => const Center(
                  child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
              error: (e, _) => Center(child: Text('$e')),
              data: (list) {
                if (list.isEmpty) {
                  return Card(
                    child: Padding(
                      padding: const EdgeInsets.all(30),
                      child: Center(
                        child: Text(
                          'لم يتم العثور على أي حركة بالرقم ($query) داخل شاشة '
                          '(${SearchSource.labelOf(source)}).\n'
                          'تأكد من اختيار الشاشة الصحيحة.',
                          textAlign: TextAlign.center,
                          style: const TextStyle(color: Colors.grey),
                        ),
                      ),
                    ),
                  );
                }

                double total = 0;
                final rows = list.map((t) {
                  total += t.weight;
                  return DataRow(cells: [
                    DataCell(Text('${t.seqNo}')),
                    DataCell(Text(Fmt.dateTime(t.date))),
                    DataCell(Text(t.accountName)),
                    DataCell(Text(t.opType)),
                    DataCell(Text(Fmt.weight(t.weight))),
                    DataCell(Text(t.setNumber.isEmpty ? '-' : t.setNumber)),
                    DataCell(Text(t.manualNo.isEmpty ? '-' : t.manualNo)),
                    DataCell(Text(t.note)),
                    DataCell(IconButton(
                      tooltip: 'حذف الحركة',
                      icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                      onPressed: () => _delete(t),
                    )),
                  ]);
                }).toList();

                return DataTableCard(
                  title: 'نتائج البحث في ${SearchSource.labelOf(source)} '
                      '— ${list.length} حركة',
                  columns: const [
                    'رقم الحركة', 'التاريخ', 'الاسم', 'النوع', 'الوزن',
                    'رقم التشغيل', 'رقم الفاتورة', 'البيان', 'إجراءات',
                  ],
                  rows: rows,
                  totalsRow: [
                    'الإجمالي', '-', '-', '-', Fmt.weight(total), '-', '-', '-', '-',
                  ],
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
      title: 'حذف الحركة',
      message: 'حذف الحركة رقم (${txn.seqNo}) — ${txn.opType} '
          'بوزن ${Fmt.weight(txn.weight)} جم؟\nسيتم تحديث كل الأرصدة تلقائياً.',
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
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../printing/sales_invoice_pdf.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';
import 'invoice_editor_dialog.dart';
import 'sale_posting_service.dart';

/// تبويب العمليات: كل فاتورة مرحّلة في صف واحد، مع التعديل والحذف والطباعة.
class SalesOpsTab extends ConsumerWidget {
  const SalesOpsTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final invoicesAsync = ref.watch(salesInvoicesProvider);
    final period = ref.watch(periodProvider);

    return invoicesAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(child: Text('تعذّر التحميل:\n$e', textAlign: TextAlign.center)),
      data: (invoices) {
        double tGold = 0, tGems = 0, tStones = 0, tDiamond = 0, tKhayas = 0;
        for (final inv in invoices) {
          tGold += inv.gold;
          tGems += inv.gems;
          tStones += inv.stonesAfter;
          tDiamond += inv.diamond;
          tKhayas += inv.khayas;
        }

        return SingleChildScrollView(
          padding: const EdgeInsets.all(18),
          child: DataTableCard(
            title: 'الفواتير المرحّلة — الفترة $period',
            columns: const [
              'رقم الفاتورة', 'التاريخ', 'العميل', 'الذهب', 'الفصوص',
              'الأحجار بعد الخصم', 'الماس', 'خياس', 'عدد الأسطر', '',
            ],
            rows: invoices
                .map((inv) => DataRow(cells: [
                      DataCell(Text(inv.manualNo.isEmpty ? '-' : inv.manualNo)),
                      DataCell(Text(Fmt.dateTime(inv.date))),
                      DataCell(Text(inv.accountName)),
                      DataCell(Text(Fmt.weightOrDash(inv.gold))),
                      DataCell(Text(Fmt.weightOrDash(inv.gems))),
                      DataCell(Text(Fmt.weightOrDash(inv.stonesAfter))),
                      DataCell(Text(Fmt.weightOrDash(inv.diamond))),
                      DataCell(Text(Fmt.weightOrDash(inv.khayas))),
                      DataCell(Text('${inv.linesCount}')),
                      DataCell(Row(children: [
                        IconButton(
                          tooltip: 'تعديل الفاتورة',
                          icon: const Icon(Icons.edit, size: 18),
                          onPressed: () => _edit(context, ref, inv),
                        ),
                        IconButton(
                          tooltip: 'طباعة',
                          icon: const Icon(Icons.print_outlined, size: 18),
                          onPressed: () => _print(context, ref, inv),
                        ),
                        IconButton(
                          tooltip: 'حذف الفاتورة',
                          icon: const Icon(Icons.delete_outline,
                              size: 18, color: AppTheme.danger),
                          onPressed: () => _delete(context, ref, inv),
                        ),
                      ])),
                    ]))
                .toList(),
            totalsRow: invoices.isEmpty
                ? null
                : [
                    'إجمالي الشهر', '-', '-',
                    Fmt.weight(tGold), Fmt.weight(tGems), Fmt.weight(tStones),
                    Fmt.weight(tDiamond), Fmt.weight(tKhayas), '${invoices.length}', '',
                  ],
          ),
        );
      },
    );
  }

  Future<List<Txn>> _invoiceTxns(WidgetRef ref, SalesInvoiceSummary inv) async {
    final tenantId = ref.read(activeTenantIdProvider)!;
    final all = await ref.read(txnRepoProvider).byPeriod(
          tenantId,
          Fmt.periodOf(inv.date),
          opTypes: [...OpTypes.sales, OpTypes.setsKhayas],
        );
    return all
        .where((t) =>
            t.manualNo == inv.manualNo &&
            t.accountName == inv.accountName &&
            t.date.isAtSameMomentAs(inv.date))
        .toList();
  }

  Future<void> _edit(BuildContext context, WidgetRef ref, SalesInvoiceSummary inv) async {
    if (ref.read(sessionProvider).isEditLocked) {
      AppSnack.warn(context,
          'التعديل مقفول من المدير. يمكنك الحذف، ولتعديل فاتورة اطلب فتح التعديل.');
      return;
    }
    final txns = await _invoiceTxns(ref, inv);
    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (_) => InvoiceEditorDialog(summary: inv, existing: txns),
    );
  }

  Future<void> _print(BuildContext context, WidgetRef ref, SalesInvoiceSummary inv) async {
    final txns = await _invoiceTxns(ref, inv);
    final tenant = ref.read(sessionProvider).activeTenant;
    final lines = const SalePostingRebuilder().rebuild(txns);
    await const SalesInvoicePdf().printSummary(
      businessName: tenant?.businessName ?? 'جاديت',
      customerName: inv.accountName,
      invoiceNo: inv.manualNo,
      date: inv.date,
      lines: lines,
      crNumber: tenant?.crNumber,
      vatNumber: tenant?.vatNumber,
      city: tenant?.city,
    );
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, SalesInvoiceSummary inv) async {
    final txns = await _invoiceTxns(ref, inv);
    if (!context.mounted) return;

    final ok = await confirmDialog(
      context,
      title: 'حذف الفاتورة',
      message: 'سيتم حذف فاتورة رقم (${inv.manualNo}) للعميل ${inv.accountName} '
          'بكل سطورها وخياسها (${txns.length} حركة).\n\n'
          'سيتم تحديث الخزينة وصندوق خياس الطقوم وكل الحسابات تلقائياً.',
      confirmLabel: 'حذف',
      danger: true,
    );
    if (!ok) return;

    try {
      await ref.read(txnRepoProvider).deleteMany(txns.map((t) => t.id).toList());
      ref
        ..invalidate(salesInvoicesProvider)
        ..invalidate(treasuryProvider)
        ..invalidate(workshopLossesProvider);
      if (context.mounted) AppSnack.success(context, 'تم حذف الفاتورة وتحديث كل الأرصدة.');
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}

/// غلاف صغير لإعادة بناء السطور من الحركات المسجّلة
class SalePostingRebuilder {
  const SalePostingRebuilder();
  List<SaleLine> rebuild(List<Txn> txns) =>
      const SalePostingService().rebuildLines(txns);
}

import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

/// بطاقة جدول موحّدة لكل الشاشات: عنوان + أزرار + جدول + سطر إجماليات.
class DataTableCard extends StatelessWidget {
  const DataTableCard({
    super.key,
    required this.title,
    required this.columns,
    required this.rows,
    this.totalsRow,
    this.actions = const [],
    this.emptyMessage = 'لا توجد بيانات في هذه الفترة',
  });

  final String title;
  final List<String> columns;
  final List<DataRow> rows;
  final List<String>? totalsRow;
  final List<Widget> actions;
  final String emptyMessage;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Text(title,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                const Spacer(),
                ...actions,
              ],
            ),
            const SizedBox(height: 10),
            if (rows.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 34),
                child: Center(
                  child: Text(emptyMessage, style: const TextStyle(color: Colors.grey)),
                ),
              )
            else
              // التمرير العرضي: يجعل كل الأعمدة قابلة للقراءة على الجوال بلا تكبير
              Scrollbar(
                thumbVisibility: true,
                child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.only(bottom: 8),
                child: DataTable(
                  columnSpacing: 26,
                  headingRowHeight: 42,
                  dataRowMinHeight: 38,
                  dataRowMaxHeight: 46,
                  columns: columns.map((c) => DataColumn(label: Text(c))).toList(),
                  rows: [
                    ...rows,
                    if (totalsRow != null)
                      DataRow(
                        color: WidgetStatePropertyAll(AppTheme.gold.withValues(alpha: 0.10)),
                        cells: totalsRow!
                            .map((c) => DataCell(Text(
                                  c,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.bold, color: AppTheme.gold),
                                )))
                            .toList(),
                      ),
                  ],
                ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

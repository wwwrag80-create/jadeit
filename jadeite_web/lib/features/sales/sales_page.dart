import 'package:flutter/material.dart';

import 'sales_entry_tab.dart';
import 'sales_ops_tab.dart';

/// شاشة المبيعات/الصادر بتبويبين: (المبيعات) للإدخال و(العمليات) للفواتير المرحّلة.
class SalesPage extends StatelessWidget {
  const SalesPage({super.key});

  @override
  Widget build(BuildContext context) => DefaultTabController(
        length: 2,
        child: Column(
          children: [
            const Material(
              child: TabBar(
                tabs: [
                  Tab(text: '🧾  المبيعات', height: 46),
                  Tab(text: '📚  العمليات', height: 46),
                ],
              ),
            ),
            const Expanded(
              child: TabBarView(
                children: [SalesEntryTab(), SalesOpsTab()],
              ),
            ),
          ],
        ),
      );
}

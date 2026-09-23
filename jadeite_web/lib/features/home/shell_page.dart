import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../state/providers.dart';
import '../../state/realtime_controller.dart';
import '../../widgets/period_selector.dart';
import '../../widgets/status_bar.dart';
import '../accounts/accounts_page.dart';
import '../archive/archive_page.dart';
import '../closing/closing_page.dart';
import '../journal/journal_page.dart';
import '../losses/losses_page.dart';
import '../boxes/boxes_page.dart';
import '../inbound/inbound_page.dart';
import '../manufacturing/manufacturing_page.dart';
import '../opening/opening_page.dart';
import '../reports/reports_page.dart';
import '../sales/sales_page.dart';
import '../statement/statement_page.dart';

/// الهيكل الرئيسي لواجهة العميل: شريط علوي + قائمة شاشات جانبية + محتوى.
class ShellPage extends ConsumerStatefulWidget {
  const ShellPage({super.key});

  @override
  ConsumerState<ShellPage> createState() => _ShellPageState();
}

class _ShellPageState extends ConsumerState<ShellPage> {
  String _screen = 'sales';

  @override
  void initState() {
    super.initState();
    // تشغيل قناة البث اللحظي: أي حركة ترفعها برامج العملاء تظهر هنا فوراً،
    // والقناة تتبدّل تلقائياً عند انتقال المدير لعميل آخر.
    WidgetsBinding.instance.addPostFrameCallback((_) => ref.read(realtimeProvider));
  }

  Widget _bodyFor(String key) => switch (key) {
        'sales' => const SalesPage(),
        'inbound' => const InboundPage(),
        'manufacturing' => const ManufacturingPage(),
        'boxes' => const BoxesPage(),
        'accounts' => const AccountsPage(),
        'statement' => const StatementPage(),
        'journal' => const JournalPage(),
        'archive' => const ArchivePage(),
        'closing' => const ClosingPage(),
        'losses' => const LossesPage(),
        'opening' => const OpeningPage(),
        'reports' => const ReportsPage(),
        _ => const SalesPage(),
      };

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final treasury = ref.watch(treasuryProvider);
    final width = MediaQuery.sizeOf(context).width;
    final isWide = width >= 1100;     // القائمة الجانبية ثابتة
    final isPhone = width < 700;      // تخطيط الجوال المضغوط

    final tenantName = session.activeTenant?.businessName ?? 'جاديت';
    final treasuryText = treasury.maybeWhen(
      data: (v) => 'الخزينة: ${Fmt.weight(v)} جم',
      orElse: () => 'الخزينة: …',
    );

    return Scaffold(
      appBar: AppBar(
        titleSpacing: isPhone ? 4 : 16,
        // على الجوال: اسم المصنع والرصيد فوق بعض حتى لا يفيض الشريط
        title: isPhone
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(tenantName,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                  Text(treasuryText,
                      style: const TextStyle(
                          color: AppTheme.gold, fontWeight: FontWeight.bold, fontSize: 11)),
                ],
              )
            : Row(
                children: [
                  const Text('💎', style: TextStyle(fontSize: 20)),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(tenantName,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                  ),
                  const SizedBox(width: 20),
                  Text(treasuryText,
                      style: const TextStyle(
                          color: AppTheme.gold, fontWeight: FontWeight.bold)),
                ],
              ),
        actions: isPhone
            // على الجوال نكتفي بمختار الفترة، وحالة الاتصال تنزل للوحة الجانبية
            ? const [PeriodSelector(), SizedBox(width: 4)]
            : const [PeriodSelector(), SizedBox(width: 12), StatusBar(), SizedBox(width: 12)],
      ),
      body: Column(
        children: [
          if (session.isImpersonating) const _ImpersonationBanner(),
          Expanded(
            child: Row(
              children: [
                if (isWide)
                  _SideNav(
                    current: _screen,
                    onSelect: (key) => setState(() => _screen = key),
                  ),
                Expanded(child: _bodyFor(_screen)),
              ],
            ),
          ),
        ],
      ),
      drawer: isWide
          ? null
          : Drawer(
              child: SafeArea(
                child: _SideNav(
                  current: _screen,
                  onSelect: (key) {
                    setState(() => _screen = key);
                    Navigator.pop(context);
                  },
                ),
              ),
            ),
    );
  }
}

/// شريط تنبيه واضح يمنع المدير من نسيان أنه يعمل داخل حساب عميل.
class _ImpersonationBanner extends ConsumerWidget {
  const _ImpersonationBanner();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tenant = ref.watch(sessionProvider).activeTenant;
    final isPhone = MediaQuery.sizeOf(context).width < 700;
    final deviceSync = ref.watch(activeTenantSyncProvider);

    // يوضّح للمدير هل سيصل تعديله لجهاز العميل الآن أم عند فتحه البرنامج
    final syncNote = deviceSync.maybeWhen(
      data: (row) {
        if (row == null) return '';
        return row.isOnline
            ? '🟢 جهاز العميل متصل — تعديلك يصله خلال ثوانٍ'
            : '⚫ جهاز العميل غير متصل — تعديلك يصله عند فتحه البرنامج';
      },
      orElse: () => '',
    );

    // شريط ثابت يوضّح دائماً أي عميل معروض — على الجوال نختصر النص
    // ونجعل زر الرجوع كبيراً بما يكفي للمس بإصبع واحد.
    return Material(
      color: AppTheme.warn,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: isPhone ? 8 : 16, vertical: 6),
          child: Row(
            children: [
              const Icon(Icons.visibility, color: Colors.black87, size: 18),
              const SizedBox(width: 6),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      isPhone
                          ? 'تعرض: ${tenant?.businessName ?? ''}'
                          : 'أنت داخل حساب العميل «${tenant?.businessName ?? ''}» كمدير — أي تعديل هنا يؤثر على بياناته الفعلية.',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: Colors.black87,
                          fontWeight: FontWeight.bold,
                          fontSize: isPhone ? 12 : 14),
                    ),
                    if (syncNote.isNotEmpty)
                      Text(syncNote,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: Colors.black.withValues(alpha: 0.65),
                              fontSize: isPhone ? 10 : 12)),
                  ],
                ),
              ),
              const SizedBox(width: 4),
              isPhone
                  ? IconButton(
                      tooltip: 'رجوع للوحة الإدارة',
                      constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
                      onPressed: () => ref.read(sessionProvider.notifier).exitTenant(),
                      icon: const Icon(Icons.logout, color: Colors.black87),
                    )
                  : TextButton.icon(
                      onPressed: () => ref.read(sessionProvider.notifier).exitTenant(),
                      icon: const Icon(Icons.arrow_back, size: 18, color: Colors.black87),
                      label: const Text('رجوع للوحة الإدارة',
                          style: TextStyle(color: Colors.black87)),
                    ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SideNav extends StatelessWidget {
  const _SideNav({required this.current, required this.onSelect});

  final String current;
  final ValueChanged<String> onSelect;

  @override
  Widget build(BuildContext context) => Container(
        width: 230,
        color: Theme.of(context).cardTheme.color,
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 12),
          children: [
            for (final s in AppScreens.all)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                child: Material(
                  color: current == s.key
                      ? AppTheme.gold.withValues(alpha: 0.16)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  child: ListTile(
                    dense: true,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    leading: Text(s.icon, style: const TextStyle(fontSize: 18)),
                    title: Text(
                      s.label,
                      style: TextStyle(
                        fontWeight: current == s.key ? FontWeight.bold : FontWeight.normal,
                        color: current == s.key ? AppTheme.gold : null,
                      ),
                    ),
                    onTap: () => onSelect(s.key),
                  ),
                ),
              ),
          ],
        ),
      );
}

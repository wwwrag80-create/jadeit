import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'features/admin/admin_dashboard_page.dart';
import 'features/auth/login_page.dart';
import 'features/home/shell_page.dart';
import 'state/providers.dart';
import 'state/session_controller.dart';

class JadeiteApp extends ConsumerWidget {
  const JadeiteApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);

    return MaterialApp(
      title: 'جاديت — نظام إدارة مصانع الذهب',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.dark,

      // الاتجاه العربي على مستوى التطبيق كله
      locale: const Locale('ar', 'SA'),
      supportedLocales: const [Locale('ar', 'SA'), Locale('en', 'US')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      builder: (context, child) => Directionality(
        textDirection: TextDirection.rtl,
        child: child ?? const SizedBox.shrink(),
      ),

      home: _rootFor(session),
    );
  }

  Widget _rootFor(SessionState session) {
    if (session.loading && !session.isSignedIn) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!session.isSignedIn) {
      return const LoginPage();
    }
    if (session.hasNoTenant) {
      return const _BlockedPage(
        icon: Icons.link_off,
        message: 'تم الدخول، لكن حسابك غير مربوط بأي مصنع بعد.\n'
            'تواصل مع الإدارة لربط حسابك.',
      );
    }
    if (session.isTenantSuspended) {
      return const _BlockedPage(
        icon: Icons.block,
        message: 'حساب المصنع موقوف حالياً من الإدارة.\n'
            'بياناتك محفوظة كما هي — تواصل مع الإدارة لإعادة التفعيل.',
      );
    }
    // المدير بلا مستأجر مُختار => لوحة الإدارة.
    // بمجرد اختياره عميلاً يتغيّر activeTenantId فينتقل تلقائياً لواجهة العميل.
    if (session.isAdmin && session.activeTenantId == null) {
      return const AdminDashboardPage();
    }
    return const ShellPage();
  }
}

/// شاشة بديلة عندما لا يصح فتح النظام (حساب غير مربوط أو موقوف)
class _BlockedPage extends ConsumerWidget {
  const _BlockedPage({required this.icon, required this.message});

  final IconData icon;
  final String message;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 56, color: AppTheme.warn),
                const SizedBox(height: 16),
                Text(message, textAlign: TextAlign.center, style: const TextStyle(fontSize: 16)),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: () => ref.read(sessionProvider.notifier).signOut(),
                  icon: const Icon(Icons.logout),
                  label: const Text('تسجيل الخروج'),
                ),
              ],
            ),
          ),
        ),
      );
}

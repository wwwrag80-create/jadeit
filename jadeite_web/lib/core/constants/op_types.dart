/// أنواع الحركات وصناديق الخياس — مصدر واحد للحقيقة، مطابق لدوال SQL.
class OpTypes {
  const OpTypes._();

  // ---------- الوارد ----------
  static const String inboundGold = 'وارد ذهب (عيار 18)';
  static const String inboundGems = 'وارد فصوص وأحجار';
  static const String inboundDiamond = 'وارد الماس';
  static const List<String> inbound = [inboundGold, inboundGems, inboundDiamond];

  // ---------- المبيعات ----------
  static const String saleGold = 'مبيعات ذهب';
  static const String saleGoldWithDiamond = 'مبيعات ذهب مع الماس';
  static const String saleGemsStones = 'مبيعات فصوص وأحجار';
  static const String saleDiamond = 'مبيعات الماس';
  static const List<String> sales = [
    saleGold,
    saleGoldWithDiamond,
    saleGemsStones,
    saleDiamond,
  ];

  /// علامة داخلية تميّز "الأحجار بعد الخصم" عن "الفصوص" في نفس النوع
  static const double stonesDiscountMarker = 3.0;

  /// علامة داخلية للقيود الافتتاحية
  static const double openingMarker = 1.0;
  static const String openingNote = 'قيد افتتاحي';

  // ---------- عمليات المصنعين والمركبين ----------
  static const String issueGold = 'صرف ذهب';
  static const String receiveGold = 'قبض ذهب';
  static const String laiz = 'الليز';
  static const String polish = 'البوليش';
  static const String mufanish8 = 'المفنش ٨ بالالف';
  static const String mufanish4 = 'المفنش ٤ بالالف';
  static const String wireBack = 'السلك الراجع';
  static const String caratAfterCheck = 'العيار بعد الفحص';

  static const List<String> manufacturerOps = [
    issueGold,
    receiveGold,
    mufanish8,
    mufanish4,
    polish,
    laiz,
    wireBack,
    caratAfterCheck,
  ];

  static const List<String> assemblerOps = [
    issueGold,
    receiveGold,
    laiz,
    wireBack,
    caratAfterCheck,
  ];

  // ---------- خياس الطقوم ----------
  static const String setsKhayas = 'خياس طقوم';

  // ---------- القيود اليومية ----------
  static const String journalDebit = 'قيد يومي مدين';
  static const String journalCredit = 'قيد يومي دائن';

  // ---------- حالات الحركة ----------
  /// الحالات التي تُحتسب في الأرصدة — نفس فلتر برنامج سطح المكتب حرفياً
  /// (SETTLED: قسم أُقفلت فترته، MEMO: سطر معلوماتي — كلاهما لا يُحتسب)
  static const List<String> countedStatuses = ['ACTIVE', 'SETTLED_INOUT'];

  // ---------- الحسابات النظامية ----------
  static const String factoryAccount = 'المصنع';
  static const String treasuryAccount = 'حساب الخزينة';
  static const String salesAccount = 'حساب المبيعات';
  static const String lossesAccount = 'حساب الخسائر';
}

/// مصادر البحث الموحّد — الشاشة التي تمت فيها الفاتورة.
/// ضروري لأن أرقام الفواتير قد تتشابه بين الشاشات.
class SearchSource {
  const SearchSource._();

  static const String sales = 'المبيعات';
  static const String inbound = 'الوارد';
  static const String journal = 'القيود';
  static const String opening = 'الافتتاحي';
  static const String setNumber = 'التشغيل';
  static const String all = 'الكل';

  static const List<({String key, String label})> options = [
    (key: sales, label: 'المبيعات/الصادر'),
    (key: inbound, label: 'الوارد/قبض'),
    (key: journal, label: 'القيود اليومية'),
    (key: opening, label: 'الرصيد الافتتاحي'),
    (key: setNumber, label: 'رقم التشغيل'),
    (key: all, label: 'كل الشاشات'),
  ];

  static String labelOf(String key) =>
      options.firstWhere((o) => o.key == key, orElse: () => options.last).label;
}

/// تعريف صندوق خياس: نوع المدين، نوع الدائن، وحساب المسترجع المرتبط.
///
/// أسماء المسترجع هي ما يكتبه برنامج سطح المكتب حرفياً (get_stage_config) —
/// وإلا لم يُخصم الذهب العائد من خياس صندوقه عند مزامنة الحركات بين الطرفين.
/// (قاعدة البيانات تقبل الأسماء القديمة أيضاً: box_mustarja_names)
class KhayasBox {
  const KhayasBox({
    required this.name,
    required this.madinType,
    required this.qabdType,
    required this.mustarjaName,
    required this.icon,
  });

  final String name;
  final String madinType;
  final String qabdType;
  final String mustarjaName;
  final String icon;

  static const List<KhayasBox> all = [
    KhayasBox(
      name: 'الكاستنج',
      madinType: 'صرف كاستنج',
      qabdType: 'قبض كاستنج',
      mustarjaName: 'مسترجع كاستنج',
      icon: '🏗️',
    ),
    KhayasBox(
      name: 'التلميع',
      madinType: 'صرف تلميع',
      qabdType: 'قبض تلميع',
      mustarjaName: 'مسترجع التلميع/البف',
      icon: '✨',
    ),
    KhayasBox(
      name: 'التلميع/البف',
      madinType: 'صرف تلميع بف',
      qabdType: 'قبض تلميع بف',
      mustarjaName: 'مسترجع البوليش',
      icon: '🪄',
    ),
    KhayasBox(
      name: 'خياس الطقوم',
      madinType: OpTypes.setsKhayas,
      qabdType: 'قبض خياس طقوم',
      mustarjaName: 'مسترجع خياس الطقوم',
      icon: '💍',
    ),
  ];

  static KhayasBox? byName(String name) {
    for (final box in all) {
      if (box.name == name) return box;
    }
    return null;
  }

  static List<String> get madinTypes => all.map((b) => b.madinType).toList();
  static List<String> get qabdTypes => all.map((b) => b.qabdType).toList();
}

/// شاشات النظام (تُستخدم في الواجهة الرئيسية وفي التوجيه)
class AppScreens {
  const AppScreens._();

  static const List<({String key, String label, String icon})> all = [
    (key: 'sales', label: 'المبيعات/الصادر', icon: '🧾'),
    (key: 'inbound', label: 'الوارد/قبض', icon: '📥'),
    (key: 'manufacturing', label: 'مراحل التصنيع', icon: '🏭'),
    (key: 'boxes', label: 'صناديق الخياس', icon: '📦'),
    (key: 'accounts', label: 'الحسابات', icon: '🗂️'),
    (key: 'statement', label: 'كشف حساب', icon: '📄'),
    (key: 'journal', label: 'القيود اليومية', icon: '📒'),
    (key: 'archive', label: 'أرشيف الفواتير', icon: '🗄️'),
    (key: 'closing', label: 'إقفال الصناديق', icon: '🔐'),
    (key: 'losses', label: 'الخسائر والهالك', icon: '⚠️'),
    (key: 'opening', label: 'الرصيد الافتتاحي', icon: '⚖️'),
    (key: 'reports', label: 'التقرير الشهري', icon: '📊'),
    (key: 'audit', label: 'سجل التعديلات', icon: '🕵️'),
  ];

  /// شاشات تظهر للمدير فقط (أثناء تصفّح حساب عميل)
  static const Set<String> adminOnly = {'audit'};
}

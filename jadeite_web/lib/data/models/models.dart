import '../../core/constants/op_types.dart';

/// مستأجر (مصنع/عميل)
class Tenant {
  const Tenant({
    required this.id,
    required this.businessName,
    required this.isActive,
    required this.canEdit,
    this.lastLogin,
    this.lastSeen,
    this.isOnline = false,
    this.txnCount = 0,
    this.crNumber,
    this.vatNumber,
    this.city,
  });

  final String id;
  final String businessName;
  final bool isActive;
  final bool canEdit;
  final DateTime? lastLogin;
  final DateTime? lastSeen;
  final bool isOnline;
  final int txnCount;
  final String? crNumber;
  final String? vatNumber;
  final String? city;

  factory Tenant.fromMap(Map<String, dynamic> m) => Tenant(
        id: m['id'] as String,
        businessName: (m['business_name'] ?? '') as String,
        isActive: (m['is_active'] ?? true) as bool,
        canEdit: (m['can_edit'] ?? true) as bool,
        lastLogin: _date(m['last_login']),
        lastSeen: _date(m['last_seen']),
        isOnline: (m['is_online'] ?? false) as bool,
        txnCount: ((m['txn_count'] ?? 0) as num).toInt(),
        crNumber: m['cr_number'] as String?,
        vatNumber: m['vat_number'] as String?,
        city: m['city'] as String?,
      );
}

/// المستخدم الحالي
class AppUser {
  const AppUser({
    required this.id,
    required this.role,
    this.tenantId,
    this.fullName,
  });

  final String id;
  final String role;
  final String? tenantId;
  final String? fullName;

  bool get isAdmin => role == 'admin';

  factory AppUser.fromMap(Map<String, dynamic> m) => AppUser(
        id: m['id'] as String,
        role: (m['role'] ?? 'owner') as String,
        tenantId: m['tenant_id'] as String?,
        fullName: m['full_name'] as String?,
      );
}

/// حساب في شجرة الحسابات
class Account {
  const Account({
    required this.id,
    required this.name,
    required this.category,
    this.boxKey,
    this.isSystem = false,
  });

  final String id;
  final String name;
  final String category;
  final String? boxKey;
  final bool isSystem;

  factory Account.fromMap(Map<String, dynamic> m) => Account(
        id: m['id'] as String,
        name: (m['name'] ?? '') as String,
        category: (m['category'] ?? '') as String,
        boxKey: m['box_key'] as String?,
        isSystem: (m['is_system'] ?? false) as bool,
      );
}

/// حركة واحدة في دفتر الأستاذ
class Txn {
  const Txn({
    required this.id,
    required this.seqNo,
    required this.date,
    required this.accountName,
    required this.opType,
    required this.weight,
    this.weightBefore = 0,
    this.weightAfter = 0,
    this.note = '',
    this.status = 'ACTIVE',
    this.treesCount = 0,
    this.setNumber = '',
    this.rowNumber = '',
    this.manualNo = '',
  });

  final int id;
  final int seqNo;
  final DateTime date;
  final String accountName;
  final String opType;
  final double weight;
  final double weightBefore;
  final double weightAfter;
  final String note;
  final String status;
  final double treesCount;
  final String setNumber;
  final String rowNumber;
  final String manualNo;

  String get period =>
      '${date.year.toString().padLeft(4, '0')}-${date.month.toString().padLeft(2, '0')}';

  bool get isOpening =>
      treesCount == OpTypes.openingMarker && note == OpTypes.openingNote;

  bool get isStonesAfterDiscount =>
      opType == OpTypes.saleGemsStones && treesCount == OpTypes.stonesDiscountMarker;

  factory Txn.fromMap(Map<String, dynamic> m) => Txn(
        id: ((m['id'] ?? 0) as num).toInt(),
        seqNo: ((m['seq_no'] ?? 0) as num).toInt(),
        date: _date(m['txn_date']) ?? DateTime.now(),
        accountName: (m['account_name'] ?? '') as String,
        opType: (m['op_type'] ?? '') as String,
        weight: _num(m['weight']),
        weightBefore: _num(m['weight_before']),
        weightAfter: _num(m['weight_after']),
        note: (m['note'] ?? '') as String,
        status: (m['status'] ?? 'ACTIVE') as String,
        treesCount: _num(m['trees_count']),
        setNumber: (m['set_number'] ?? '') as String,
        rowNumber: (m['row_number'] ?? '') as String,
        manualNo: (m['manual_no'] ?? '') as String,
      );

  /// حركة جديدة لم تُرحَّل بعد — الرقم المتسلسل تمنحه قاعدة البيانات عند الترحيل
  factory Txn.newEntry({
    required DateTime date,
    required String accountName,
    required String opType,
    required double weight,
    double weightBefore = 0,
    double weightAfter = 0,
    String note = '',
    double treesCount = 0,
    String setNumber = '',
    String rowNumber = '',
    String manualNo = '',
  }) =>
      Txn(
        id: 0,
        seqNo: 0,
        date: date,
        accountName: accountName,
        opType: opType,
        weight: weight,
        weightBefore: weightBefore,
        weightAfter: weightAfter,
        note: note,
        treesCount: treesCount,
        setNumber: setNumber,
        rowNumber: rowNumber,
        manualNo: manualNo,
      );

  Map<String, dynamic> toInsertMap(String tenantId) => {
        'tenant_id': tenantId,
        'txn_date': date.toIso8601String(),
        'account_name': accountName,
        'op_type': opType,
        'weight': weight,
        'weight_before': weightBefore,
        'weight_after': weightAfter,
        'note': note,
        'status': status,
        'trees_count': treesCount,
        'set_number': setNumber,
        'row_number': rowNumber,
        'manual_no': manualNo,
      };
}

/// سطر فاتورة مبيعات (قبل الترحيل أو أثناء التعديل)
class SaleLine {
  SaleLine({
    this.rowNumber = '',
    this.setNumber = '',
    this.gold = 0,
    this.gems = 0,
    this.stonesRaw = 0,
    this.stonesAfterDiscount = 0,
    this.diamond = 0,
    this.khayas = 0,
  });

  String rowNumber;
  String setNumber;
  double gold;
  double gems;
  double stonesRaw;
  double stonesAfterDiscount;
  double diamond;

  /// خياس الطقم: لا يدخل ضمن أوزان الطقم، بل يُرحّل لصندوق خياس الطقوم
  double khayas;

  bool get isEmpty =>
      gold <= 0 && gems <= 0 && stonesAfterDiscount <= 0 && diamond <= 0 && khayas <= 0;

  /// الوزن القائم = الذهب + الفصوص + الأحجار الخام + الماس
  double get standingWeight => gold + gems + stonesRaw + diamond;

  /// الوزن المقيد = الذهب + الفصوص + الأحجار بعد الخصم + الماس
  double get boundWeight => gold + gems + stonesAfterDiscount + diamond;

  SaleLine copy() => SaleLine(
        rowNumber: rowNumber,
        setNumber: setNumber,
        gold: gold,
        gems: gems,
        stonesRaw: stonesRaw,
        stonesAfterDiscount: stonesAfterDiscount,
        diamond: diamond,
        khayas: khayas,
      );
}

/// فاتورة مبيعات مرحّلة (صف واحد في تبويب العمليات)
class SalesInvoiceSummary {
  const SalesInvoiceSummary({
    required this.manualNo,
    required this.date,
    required this.accountName,
    required this.gold,
    required this.gems,
    required this.stonesAfter,
    required this.diamond,
    required this.khayas,
    required this.linesCount,
  });

  final String manualNo;
  final DateTime date;
  final String accountName;
  final double gold;
  final double gems;
  final double stonesAfter;
  final double diamond;
  final double khayas;
  final int linesCount;

  factory SalesInvoiceSummary.fromMap(Map<String, dynamic> m) => SalesInvoiceSummary(
        manualNo: (m['manual_no'] ?? '') as String,
        date: _date(m['txn_date']) ?? DateTime.now(),
        accountName: (m['account_name'] ?? '') as String,
        gold: _num(m['gold']),
        gems: _num(m['gems']),
        stonesAfter: _num(m['stones_after']),
        diamond: _num(m['diamond']),
        khayas: _num(m['khayas']),
        linesCount: ((m['lines_count'] ?? 0) as num).toInt(),
      );
}

/// صف في كشف حركة عامل (مصنّع/مركّب)
class WorkerLedgerRow {
  const WorkerLedgerRow({
    required this.rowNumber,
    required this.setNumber,
    required this.sarf,
    required this.qabd,
    required this.laiz,
    required this.polish,
    required this.mufanish8,
    required this.mufanish4,
    required this.wireBack,
    required this.carat,
    required this.note,
    required this.instantLoss,
  });

  final String rowNumber;
  final String setNumber;
  final double sarf;
  final double qabd;
  final double laiz;
  final double polish;
  final double mufanish8;
  final double mufanish4;
  final double wireBack;
  final double carat;
  final String note;
  final double instantLoss;

  factory WorkerLedgerRow.fromMap(Map<String, dynamic> m) => WorkerLedgerRow(
        rowNumber: (m['row_number'] ?? '') as String,
        setNumber: (m['set_number'] ?? '') as String,
        sarf: _num(m['sarf']),
        qabd: _num(m['qabd']),
        laiz: _num(m['laiz']),
        polish: _num(m['polish']),
        mufanish8: _num(m['mufanish8']),
        mufanish4: _num(m['mufanish4']),
        wireBack: _num(m['wire_back']),
        carat: _num(m['carat']),
        note: (m['note'] ?? '') as String,
        instantLoss: _num(m['instant_loss']),
      );
}

/// صف في شاشة عمليات صندوق (كاستنج/تلميع/بف)
class StageRow {
  StageRow({
    required this.rowNumber,
    required this.accountName,
    required this.madin,
    required this.daen,
    required this.note,
    required this.trees,
    required this.ids,
  });

  final String rowNumber;
  final String accountName;
  final double madin;
  final double daen;
  final String note;
  final double trees;
  final List<int> ids;

  /// الخياس = مدين − دائن
  double get khayas => double.parse((madin - daen).toStringAsFixed(3));

  /// خياس كل شجرة (للكاستنج فقط)
  double get khayasPerTree => trees > 0 ? khayas / trees : 0;

  /// يجمّع حركات القسم في صفوف حسب (رقم الصف + الاسم)، مرتّبة تدريجياً برقم الصف.
  /// الخياس لكل صف = مدين − دائن، والبيانات المتكررة تُدمج بدون تكرار.
  static List<StageRow> group(List<Txn> txns, String madinType, String qabdType) {
    final map = <String, _StageAgg>{};
    final order = <String>[];

    for (final t in txns) {
      final key = '${t.rowNumber}||${t.accountName}';
      final agg = map.putIfAbsent(key, () {
        order.add(key);
        return _StageAgg(t.rowNumber, t.accountName);
      });

      agg.ids.add(t.id);
      // الجمع (وليس الاستبدال) حتى لا تُهمل أي حركة مسجّلة بنفس رقم الصف
      if (t.opType == madinType) {
        agg.madin += t.weight;
      } else if (t.opType == qabdType) {
        agg.daen += t.weight;
      }
      if (t.treesCount > agg.trees) agg.trees = t.treesCount;
      final note = t.note.trim();
      if (note.isNotEmpty && !agg.notes.contains(note)) agg.notes.add(note);
    }

    final rows = order.map((k) {
      final a = map[k]!;
      return StageRow(
        rowNumber: a.rowNumber,
        accountName: a.accountName,
        madin: double.parse(a.madin.toStringAsFixed(3)),
        daen: double.parse(a.daen.toStringAsFixed(3)),
        note: a.notes.join(' | '),
        trees: a.trees,
        ids: a.ids,
      );
    }).toList();

    rows.sort((x, y) {
      final byRow = _compareRowNumbers(x.rowNumber, y.rowNumber);
      return byRow != 0 ? byRow : x.accountName.compareTo(y.accountName);
    });
    return rows;
  }
}

class _StageAgg {
  _StageAgg(this.rowNumber, this.accountName);
  final String rowNumber;
  final String accountName;
  double madin = 0;
  double daen = 0;
  double trees = 0;
  final List<int> ids = [];
  final List<String> notes = [];
}

/// ترتيب تدريجي لأرقام الصفوف: رقمياً أولاً، ثم نصياً، والفارغ في النهاية
int _compareRowNumbers(String a, String b) {
  final ta = a.trim();
  final tb = b.trim();
  if (ta.isEmpty) return tb.isEmpty ? 0 : 1;
  if (tb.isEmpty) return -1;
  final na = double.tryParse(ta);
  final nb = double.tryParse(tb);
  if (na != null && nb != null) return na.compareTo(nb);
  if (na != null) return -1;
  if (nb != null) return 1;
  return ta.compareTo(tb);
}

/// قيد يومي مزدوج (طرف مدين + طرف دائن بنفس المرجع)
class JournalEntry {
  const JournalEntry({
    required this.ref,
    required this.date,
    required this.debitAccount,
    required this.creditAccount,
    required this.weight,
    required this.note,
    required this.isBalanced,
  });

  final String ref;
  final DateTime date;
  final String debitAccount;
  final String creditAccount;
  final double weight;
  final String note;

  /// القيد سليم فقط لو كان له طرفان بنفس الوزن — غير المتوازن يُعرض بتحذير
  final bool isBalanced;

  factory JournalEntry.fromMap(Map<String, dynamic> m) => JournalEntry(
        ref: (m['entry_ref'] ?? '') as String,
        date: _date(m['txn_date']) ?? DateTime.now(),
        debitAccount: (m['debit_acc'] ?? '—') as String,
        creditAccount: (m['credit_acc'] ?? '—') as String,
        weight: _num(m['weight']),
        note: (m['note'] ?? '') as String,
        isBalanced: (m['is_balanced'] ?? false) as bool,
      );
}

/// حالة إقفال صندوق خياس لفترة
class BoxClosingStatus {
  const BoxClosingStatus({
    required this.boxName,
    required this.madin,
    required this.daen,
    required this.khayas,
    required this.isClosed,
    required this.closedKhayas,
    this.closedAt,
  });

  final String boxName;
  final double madin;
  final double daen;
  final double khayas;
  final bool isClosed;
  final double closedKhayas;
  final DateTime? closedAt;

  factory BoxClosingStatus.fromMap(Map<String, dynamic> m) => BoxClosingStatus(
        boxName: (m['box_name'] ?? '') as String,
        madin: _num(m['madin']),
        daen: _num(m['daen']),
        khayas: _num(m['khayas']),
        isClosed: (m['is_closed'] ?? false) as bool,
        closedKhayas: _num(m['closed_khayas']),
        closedAt: _date(m['closed_at']),
      );
}

/// سطر في تفصيل الخسائر والهالك
class LossRow {
  const LossRow({
    required this.sourceKind,
    required this.sourceName,
    required this.category,
    required this.amount,
    required this.isClosed,
  });

  final String sourceKind;   // صندوق | عامل
  final String sourceName;
  final String category;
  final double amount;
  final bool isClosed;

  /// الفاقد الموجب هالك فعلي، والسالب فائض لصالح الورشة
  bool get isWaste => amount > 0;

  factory LossRow.fromMap(Map<String, dynamic> m) => LossRow(
        sourceKind: (m['source_kind'] ?? '') as String,
        sourceName: (m['source_name'] ?? '') as String,
        category: (m['category'] ?? '') as String,
        amount: _num(m['amount']),
        isClosed: (m['is_closed'] ?? false) as bool,
      );
}

/// صف في أرشيف الفواتير
class ArchivedInvoice {
  const ArchivedInvoice({
    required this.manualNo,
    required this.date,
    required this.accountName,
    required this.gold,
    required this.gems,
    required this.stonesAfter,
    required this.diamond,
    required this.khayas,
    required this.linesCount,
    required this.setNumbers,
  });

  final String manualNo;
  final DateTime date;
  final String accountName;
  final double gold;
  final double gems;
  final double stonesAfter;
  final double diamond;
  final double khayas;
  final int linesCount;
  final String setNumbers;

  double get totalWeight =>
      double.parse((gold + gems + stonesAfter + diamond).toStringAsFixed(3));

  factory ArchivedInvoice.fromMap(Map<String, dynamic> m) => ArchivedInvoice(
        manualNo: (m['manual_no'] ?? '') as String,
        date: _date(m['txn_date']) ?? DateTime.now(),
        accountName: (m['account_name'] ?? '') as String,
        gold: _num(m['gold']),
        gems: _num(m['gems']),
        stonesAfter: _num(m['stones_after']),
        diamond: _num(m['diamond']),
        khayas: _num(m['khayas']),
        linesCount: ((m['lines_count'] ?? 0) as num).toInt(),
        setNumbers: (m['set_numbers'] ?? '') as String,
      );
}

/// حالة عميل واحد في لوحة المدير: مزامنته وأجهزته وحركاته
class SyncOverview {
  const SyncOverview({
    required this.tenantId,
    required this.businessName,
    required this.isActive,
    required this.canEdit,
    required this.syncEnabled,
    required this.isOnline,
    required this.devices,
    required this.pendingCount,
    required this.txnCount,
    this.lastSyncAt,
    this.lastTxnAt,
    this.lastError,
  });

  final String tenantId;
  final String businessName;
  final bool isActive;
  final bool canEdit;
  final bool syncEnabled;
  final bool isOnline;
  final int devices;
  final int pendingCount;
  final int txnCount;
  final DateTime? lastSyncAt;
  final DateTime? lastTxnAt;
  final String? lastError;

  /// المزامنة سليمة فقط لو لا يوجد متراكم ولا خطأ مسجّل
  bool get isHealthy => pendingCount == 0 && (lastError == null || lastError!.isEmpty);

  factory SyncOverview.fromMap(Map<String, dynamic> m) => SyncOverview(
        tenantId: (m['tenant_id'] ?? '') as String,
        businessName: (m['business_name'] ?? '') as String,
        isActive: (m['is_active'] ?? true) as bool,
        canEdit: (m['can_edit'] ?? true) as bool,
        syncEnabled: (m['sync_enabled'] ?? true) as bool,
        isOnline: (m['is_online'] ?? false) as bool,
        devices: ((m['devices'] ?? 0) as num).toInt(),
        pendingCount: ((m['pending_count'] ?? 0) as num).toInt(),
        txnCount: ((m['txn_count'] ?? 0) as num).toInt(),
        lastSyncAt: _date(m['last_sync_at']),
        lastTxnAt: _date(m['last_txn_at']),
        lastError: m['last_error'] as String?,
      );
}

double _num(dynamic v) => v == null ? 0.0 : (v as num).toDouble();

DateTime? _date(dynamic v) {
  if (v == null) return null;
  if (v is DateTime) return v;
  return DateTime.tryParse(v.toString());
}

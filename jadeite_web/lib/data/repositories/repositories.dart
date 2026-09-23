import 'package:supabase_flutter/supabase_flutter.dart';

import '../../core/config/supabase_config.dart';

import '../../core/constants/op_types.dart';
import '../models/models.dart';

SupabaseClient get _db => db;

/// خطأ يحمل رسالة عربية واضحة بدل رسالة PostgREST الخام.
class RepoException implements Exception {
  RepoException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// نص الخطأ الفعلي: رسالة PostgrestException وحدها (دوال SQL ترمي رسائل عربية
/// واضحة)، بدل النص الطويل «PostgrestException(message: …, code: …, …)».
String _errorText(Object error) {
  if (error is PostgrestException) return error.message;
  if (error is AuthException) return error.message;
  return error.toString();
}

Never _rethrowFriendly(Object error) {
  final text = _errorText(error);
  if (text.contains('row-level security') || text.contains('violates row-level')) {
    throw RepoException(
      'العملية مرفوضة: إما أن التعديل مقفول من المدير، أو أنك تحاول الوصول لحساب غير حسابك.',
    );
  }
  if (text.contains('duplicate key')) {
    throw RepoException('هذا السجل مسجّل من قبل — راجع الأرقام المكررة.');
  }
  if (text.contains('Failed host lookup') ||
      text.contains('SocketException') ||
      text.contains('XMLHttpRequest') ||
      text.contains('ClientException')) {
    throw RepoException('لا يوجد اتصال بالإنترنت. تحقق من الشبكة وحاول مجدداً.');
  }
  // رسائل دوال قاعدة البيانات عربية أصلاً — تُعرض كما هي
  if (RegExp(r'[\u0600-\u06FF]').hasMatch(text)) {
    throw RepoException(text);
  }
  throw RepoException('تعذّر تنفيذ العملية: $text');
}

// ============================================================================
//  الجلسة والمستخدم
// ============================================================================
class AuthRepository {
  Future<AppUser?> signIn(String email, String password) async {
    try {
      final res = await _db.auth.signInWithPassword(email: email, password: password);
      if (res.user == null) return null;
      return currentAppUser();
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> signOut() => _db.auth.signOut();

  /// أحداث الجلسة (خروج من تبويب آخر، انتهاء صلاحية الرمز…)
  Stream<AuthState> get authChanges => _db.auth.onAuthStateChange;

  Future<AppUser?> currentAppUser() async {
    final user = _db.auth.currentUser;
    if (user == null) return null;
    final row = await _db.from('app_users').select().eq('id', user.id).maybeSingle();
    if (row == null) return null;
    return AppUser.fromMap(row);
  }
}

// ============================================================================
//  المستأجرون + لوحة المدير
// ============================================================================
class TenantRepository {
  Future<Tenant?> byId(String tenantId) async {
    final row = await _db.from('tenants').select().eq('id', tenantId).maybeSingle();
    return row == null ? null : Tenant.fromMap(row);
  }

  /// لوحة المدير: كل العملاء مع حالة الاتصال وآخر دخول
  Future<List<Tenant>> adminOverview() async {
    final rows = await _db.rpc('admin_tenants_overview') as List<dynamic>;
    return rows.map((r) => Tenant.fromMap(Map<String, dynamic>.from(r as Map))).toList();
  }

  /// نظرة المدير الشاملة: حالة كل عميل ومزامنته وأجهزته
  Future<List<SyncOverview>> syncOverview() async {
    final rows = await _db.rpc('admin_sync_overview') as List<dynamic>;
    return rows
        .map((r) => SyncOverview.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  /// إعادة توليد رمز مزامنة العميل — يُبطل الرمز القديم على كل أجهزته فوراً
  Future<String> rotateSyncToken(String tenantId) async {
    try {
      final token = await _db.rpc('admin_rotate_sync_token', params: {'p_tenant': tenantId});
      return token as String;
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> setCanEdit(String tenantId, bool value) async {
    try {
      await _db.from('tenants').update({'can_edit': value}).eq('id', tenantId);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> setActive(String tenantId, bool value) async {
    try {
      await _db.from('tenants').update({'is_active': value}).eq('id', tenantId);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// حذف مستأجر — الجداول التابعة تُحذف تلقائياً بـ ON DELETE CASCADE
  Future<void> delete(String tenantId) async {
    try {
      await _db.from('tenants').delete().eq('id', tenantId);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<String> create(String businessName) async {
    try {
      final id = await _db.rpc('admin_create_tenant', params: {'p_business_name': businessName});
      return id as String;
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> touchActivity(String tenantId, {bool isLogin = false}) async {
    try {
      await _db.rpc('touch_activity', params: {'p_tenant': tenantId, 'p_is_login': isLogin});
    } catch (_) {
      // النبض ليس حرجاً — لا نُفشل الواجهة بسببه
    }
  }

  Future<bool> canEdit(String tenantId) async {
    final row = await _db.from('tenants').select('can_edit').eq('id', tenantId).maybeSingle();
    return (row?['can_edit'] ?? true) as bool;
  }
}

// ============================================================================
//  الحسابات
// ============================================================================
class AccountRepository {
  Future<List<Account>> list(String tenantId) async {
    final rows = await _db
        .from('accounts')
        .select()
        .eq('tenant_id', tenantId)
        .eq('is_active', true)
        .order('category')
        .order('sort_order')
        .order('name');
    return (rows as List).map((r) => Account.fromMap(Map<String, dynamic>.from(r))).toList();
  }

  Future<void> add(String tenantId, String name, String category) async {
    try {
      await _db.from('accounts').insert({
        'tenant_id': tenantId,
        'name': name.trim(),
        'category': category,
      });
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> remove(String accountId) async {
    try {
      await _db.from('accounts').delete().eq('id', accountId);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }
}

// ============================================================================
//  الحركات — قلب النظام
// ============================================================================
class TxnRepository {
  /// تسجيل حركة واحدة عبر RPC (يتكفّل بالرقم المتسلسل بأمان مع التزامن)
  Future<int> post(String tenantId, Txn txn) async {
    try {
      final id = await _db.rpc('post_transaction', params: {
        'p_tenant': tenantId,
        // لحظة زمنية كاملة بتوقيت UTC — تُعرض بتوقيت كل جهاز صحيحاً
        'p_date': txn.date.toUtc().toIso8601String(),
        'p_account': txn.accountName,
        'p_op_type': txn.opType,
        'p_weight': txn.weight,
        'p_note': txn.note,
        'p_before': txn.weightBefore,
        'p_after': txn.weightAfter,
        'p_trees': txn.treesCount,
        'p_set_number': txn.setNumber,
        'p_row_number': txn.rowNumber,
        'p_manual_no': txn.manualNo,
        'p_period': txn.period.isEmpty ? null : txn.period,
      });
      return (id as num).toInt();
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// تسجيل عدة حركات (فاتورة كاملة) داخل معاملة واحدة في قاعدة البيانات:
  /// إما تُسجَّل كلها أو لا شيء — فلا تبقى فاتورة ناقصة لو انقطع الاتصال.
  Future<void> postMany(String tenantId, List<Txn> txns) async {
    if (txns.isEmpty) return;
    try {
      await _db.rpc('post_transactions_batch', params: {
        'p_tenant': tenantId,
        'p_rows': txns.map((t) => t.toRpcRow()).toList(),
      });
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// استبدال حركات مرحّلة بأخرى (تعديل فاتورة) في معاملة واحدة:
  /// الحذف والإدراج معاً، فلا توجد لحظة تكون فيها الفاتورة محذوفة دون بديل.
  /// يخضع لقفل التعديل من المدير (يُفرض في قاعدة البيانات).
  Future<void> replaceMany(String tenantId, List<int> oldIds, List<Txn> txns) async {
    try {
      await _db.rpc('post_transactions_batch', params: {
        'p_tenant': tenantId,
        'p_rows': txns.map((t) => t.toRpcRow()).toList(),
        'p_replace_ids': oldIds,
      });
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> update(int id, Map<String, dynamic> changes) async {
    try {
      await _db.from('transactions').update(changes).eq('id', id);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// الحذف مسموح دائماً حتى مع قفل التعديل (سياسة RLS تسمح بذلك)
  Future<void> delete(int id) async {
    try {
      await _db.from('transactions').delete().eq('id', id);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<void> deleteMany(List<int> ids) async {
    if (ids.isEmpty) return;
    try {
      await _db.from('transactions').delete().inFilter('id', ids);
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  Future<List<Txn>> byPeriod(String tenantId, String period, {List<String>? opTypes}) async {
    var query = _db
        .from('transactions')
        .select()
        .eq('tenant_id', tenantId)
        .eq('period', period)
        .inFilter('status', OpTypes.countedStatuses);
    if (opTypes != null && opTypes.isNotEmpty) {
      query = query.inFilter('op_type', opTypes);
    }
    final rows = await query.order('txn_date').order('seq_no');
    return (rows as List).map((r) => Txn.fromMap(Map<String, dynamic>.from(r))).toList();
  }

  Future<List<Txn>> byAccount(String tenantId, String accountName, String period) async {
    final rows = await _db
        .from('transactions')
        .select()
        .eq('tenant_id', tenantId)
        .eq('account_name', accountName)
        .eq('period', period)
        .inFilter('status', OpTypes.countedStatuses)
        .order('txn_date');
    return (rows as List).map((r) => Txn.fromMap(Map<String, dynamic>.from(r))).toList();
  }

  /// القيود الافتتاحية لكل الفترات — أساس الأرصدة وليست حركة شهرية
  Future<List<Txn>> openingEntries(String tenantId) async {
    final rows = await _db
        .from('transactions')
        .select()
        .eq('tenant_id', tenantId)
        .inFilter('status', OpTypes.countedStatuses)
        .eq('trees_count', OpTypes.openingMarker)
        .eq('note', OpTypes.openingNote)
        .order('txn_date');
    return (rows as List).map((r) => Txn.fromMap(Map<String, dynamic>.from(r))).toList();
  }

  Future<List<Txn>> bySetNumber(String tenantId, String setNumber) async {
    final rows = await _db
        .from('transactions')
        .select()
        .eq('tenant_id', tenantId)
        .eq('set_number', setNumber)
        .inFilter('status', OpTypes.countedStatuses)
        .order('seq_no');
    return (rows as List).map((r) => Txn.fromMap(Map<String, dynamic>.from(r))).toList();
  }

  /// البحث الموحّد مع تحديد الشاشة — أرقام الفواتير قد تتكرر بين الشاشات،
  /// فتحديد المصدر يمنع الالتباس. المنطق في قاعدة البيانات ليكون واحداً لكل العملاء.
  Future<List<Txn>> search({
    required String tenantId,
    required String source,
    required String query,
  }) async {
    if (query.trim().isEmpty) return const [];
    try {
      final rows = await _db.rpc('search_transactions', params: {
        'p_tenant': tenantId,
        'p_source': source,
        'p_query': query.trim(),
      }) as List<dynamic>;
      return rows
          .map((r) => Txn.fromMap(Map<String, dynamic>.from(r as Map)))
          .toList();
    } catch (e) {
      _rethrowFriendly(e);
    }
  }
}

// ============================================================================
//  القيود اليومية — قيد مزدوج متوازن دائماً
// ============================================================================
class JournalRepository {
  /// يُرحّل الطرفين معاً داخل معاملة واحدة في قاعدة البيانات،
  /// فلا يمكن أن يبقى قيد بطرف واحد يخلّ بتوازن الدفاتر.
  Future<String> post({
    required String tenantId,
    required DateTime date,
    required String fromAccount,
    required String toAccount,
    required double weight,
    required String period,
    String note = '',
  }) async {
    try {
      final ref = await _db.rpc('post_journal_entry', params: {
        'p_tenant': tenantId,
        'p_date': date.toUtc().toIso8601String(),
        'p_from': fromAccount,
        'p_to': toAccount,
        'p_weight': weight,
        'p_note': note,
        'p_period': period,
      });
      return ref as String;
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// حذف القيد بطرفيه — حذف طرف واحد يترك الدفاتر غير متوازنة
  Future<int> delete(String tenantId, String entryRef) async {
    try {
      final count = await _db.rpc('delete_journal_entry', params: {
        'p_tenant': tenantId,
        'p_ref': entryRef,
      });
      return (count as num).toInt();
    } catch (e) {
      _rethrowFriendly(e);
    }
  }
}

// ============================================================================
//  إقفال صناديق الخياس
// ============================================================================
class ClosingRepository {
  /// يرحّل رصيد الصندوق لحساب الخسائر بقيد مزدوج ويسجّل الإقفال
  Future<double> closeBox(String tenantId, String boxName, String period) async {
    try {
      final value = await _db.rpc('close_khayas_box', params: {
        'p_tenant': tenantId,
        'p_box': boxName,
        'p_period': period,
      });
      return (value as num?)?.toDouble() ?? 0;
    } catch (e) {
      _rethrowFriendly(e);
    }
  }

  /// التراجع عن الإقفال: يحذف قيد الإقفال وسجلّه معاً
  Future<void> reopenBox(String tenantId, String boxName, String period) async {
    try {
      await _db.rpc('reopen_khayas_box', params: {
        'p_tenant': tenantId,
        'p_box': boxName,
        'p_period': period,
      });
    } catch (e) {
      _rethrowFriendly(e);
    }
  }
}

// ============================================================================
//  الحسابات المشتقّة (تُحسب في قاعدة البيانات لضمان رقم واحد لكل الأجهزة)
// ============================================================================
class LedgerRepository {
  Future<double> treasuryBalance(String tenantId, {String? untilPeriod}) async {
    final value = await _db.rpc('treasury_balance', params: {
      'p_tenant': tenantId,
      'p_until_period': untilPeriod,
    });
    return (value as num?)?.toDouble() ?? 0;
  }

  Future<({double madin, double daen, double khayas})> boxTotals(
      String tenantId, String boxName, String period) async {
    final rows = await _db.rpc('box_period_totals', params: {
      'p_tenant': tenantId,
      'p_box': boxName,
      'p_period': period,
    }) as List<dynamic>;
    if (rows.isEmpty) return (madin: 0.0, daen: 0.0, khayas: 0.0);
    final m = Map<String, dynamic>.from(rows.first as Map);
    return (
      madin: (m['madin'] as num?)?.toDouble() ?? 0,
      daen: (m['daen'] as num?)?.toDouble() ?? 0,
      khayas: (m['khayas'] as num?)?.toDouble() ?? 0,
    );
  }

  Future<List<WorkerLedgerRow>> workerLedger(
      String tenantId, String worker, String period) async {
    final rows = await _db.rpc('worker_ledger', params: {
      'p_tenant': tenantId,
      'p_worker': worker,
      'p_period': period,
    }) as List<dynamic>;
    return rows
        .map((r) => WorkerLedgerRow.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  Future<List<SalesInvoiceSummary>> salesInvoices(String tenantId, String period) async {
    final rows = await _db.rpc('sales_invoices', params: {
      'p_tenant': tenantId,
      'p_period': period,
    }) as List<dynamic>;
    return rows
        .map((r) => SalesInvoiceSummary.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  /// القيود اليومية لفترة، مجمّعة في قيد واحد بطرفيه
  Future<List<JournalEntry>> journalEntries(String tenantId, String period) async {
    final rows = await _db.rpc('journal_entries', params: {
      'p_tenant': tenantId,
      'p_period': period,
    }) as List<dynamic>;
    return rows
        .map((r) => JournalEntry.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  /// حالة إقفال كل الصناديق لفترة
  Future<List<BoxClosingStatus>> boxesClosingStatus(String tenantId, String period) async {
    final rows = await _db.rpc('boxes_closing_status', params: {
      'p_tenant': tenantId,
      'p_period': period,
    }) as List<dynamic>;
    return rows
        .map((r) => BoxClosingStatus.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  /// تفصيل الخسائر والهالك لفترة (صناديق + عمال)
  Future<List<LossRow>> lossesBreakdown(String tenantId, String period) async {
    final rows = await _db.rpc('losses_breakdown', params: {
      'p_tenant': tenantId,
      'p_period': period,
    }) as List<dynamic>;
    return rows.map((r) => LossRow.fromMap(Map<String, dynamic>.from(r as Map))).toList();
  }

  /// أرشيف الفواتير — فترة اختيارية وبحث نصي اختياري
  Future<List<ArchivedInvoice>> invoiceArchive(
    String tenantId, {
    String? period,
    String? query,
  }) async {
    final rows = await _db.rpc('invoice_archive', params: {
      'p_tenant': tenantId,
      'p_period': period,
      'p_query': query,
    }) as List<dynamic>;
    return rows
        .map((r) => ArchivedInvoice.fromMap(Map<String, dynamic>.from(r as Map)))
        .toList();
  }

  /// رصيد الحساب قبل الفترة (رصيد أول المدة) — يبدأ منه الرصيد المتحرك في الكشف
  Future<double> accountOpeningBalance(
    String tenantId,
    String account,
    String period,
    List<String> debitTypes,
  ) async {
    final value = await _db.rpc('account_opening_balance', params: {
      'p_tenant': tenantId,
      'p_account': account,
      'p_period': period,
      'p_debit_types': debitTypes,
    });
    return (value as num?)?.toDouble() ?? 0;
  }

  Future<double> workshopLosses(String tenantId, String period) async {
    final value = await _db.rpc('workshop_losses', params: {
      'p_tenant': tenantId,
      'p_period': period,
    });
    return (value as num?)?.toDouble() ?? 0;
  }
}

// ============================================================================
//  سجل التدقيق — قراءة فقط (يكتبه محفّز قاعدة البيانات)
// ============================================================================
class AuditRepository {
  /// آخر التغييرات على حركات المستأجر، الأحدث أولاً
  Future<List<AuditEntry>> latest(String tenantId, {int limit = 300, String? action}) async {
    var query = _db
        .from('audit_log')
        .select('id, action, created_at, actor_id, before_data, after_data')
        .eq('tenant_id', tenantId)
        .eq('table_name', 'transactions');
    if (action != null) query = query.eq('action', action);
    final rows = await query.order('id', ascending: false).limit(limit);
    return (rows as List).map((r) => AuditEntry.fromMap(Map<String, dynamic>.from(r))).toList();
  }
}

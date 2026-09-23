import 'package:flutter_test/flutter_test.dart';
import 'package:jadeite_erp/core/utils/formatters.dart';
import 'package:jadeite_erp/data/models/models.dart';

void main() {
  group('Txn', () {
    test('يقرأ الفترة والأرقام حتى لو وصلت نصاً', () {
      final t = Txn.fromMap({
        'id': 5,
        'seq_no': 1000000001,
        'txn_date': '2026-09-01T21:30:00+00:00',
        'account_name': 'مورد',
        'op_type': 'وارد ذهب (عيار 18)',
        'weight': '12.500',
        'period': '2026-09',
      });
      expect(t.weight, 12.5);
      expect(t.period, '2026-09');
      expect(t.seqNo, 1000000001);
      expect(t.date.isUtc, isTrue);
    });

    test('صف الدفعة يرسل التاريخ لحظةً بتوقيت UTC والفترة صراحةً', () {
      final local = DateTime(2026, 9, 1, 0, 30);
      final row = Txn.newEntry(
        date: local,
        accountName: 'مورد',
        opType: 'وارد الماس',
        weight: 1,
        period: '2026-08',
      ).toRpcRow();

      expect(row['period'], '2026-08');
      expect((row['txn_date'] as String).endsWith('Z'), isTrue);
      expect(DateTime.parse(row['txn_date'] as String).isAtSameMomentAs(local), isTrue);
    });

    test('بلا فترة: لا يُرسل المفتاح فتُشتق في قاعدة البيانات', () {
      final row = Txn.newEntry(
        date: DateTime(2026, 9, 1),
        accountName: 'x',
        opType: 'y',
        weight: 1,
      ).toRpcRow();
      expect(row.containsKey('period'), isFalse);
    });
  });

  group('StageRow.group', () {
    Txn t(int id, String row, String name, String type, double w, {double trees = 0}) => Txn(
          id: id,
          seqNo: id,
          date: DateTime(2026, 9, 1),
          accountName: name,
          opType: type,
          weight: w,
          rowNumber: row,
          treesCount: trees,
        );

    test('يجمع (لا يستبدل) الحركات بنفس الصف والاسم ويرتّب تدريجياً', () {
      final rows = StageRow.group([
        t(1, '10', 'أحمد', 'صرف كاستنج', 100, trees: 4),
        t(2, '2', 'أحمد', 'صرف كاستنج', 50),
        t(3, '10', 'أحمد', 'قبض كاستنج', 97),
        t(4, '10', 'أحمد', 'صرف كاستنج', 5),
        t(5, '', 'سالم', 'صرف كاستنج', 1),
      ], 'صرف كاستنج', 'قبض كاستنج');

      expect(rows.map((r) => r.rowNumber), ['2', '10', ''],
          reason: 'رقمياً لا نصياً، والفارغ في النهاية');
      final r10 = rows[1];
      expect(r10.madin, 105);
      expect(r10.daen, 97);
      expect(r10.khayas, 8);
      expect(r10.trees, 4);
      expect(r10.khayasPerTree, 2);
      expect(r10.ids, [1, 3, 4]);
    });
  });

  group('AuditEntry', () {
    test('التعديل يُلخَّص بالحقول المتغيّرة ورقم الحركة من السياق', () {
      final e = AuditEntry.fromMap({
        'id': 1,
        'action': 'UPDATE',
        'created_at': '2026-09-01T10:00:00+00:00',
        'actor_id': 'u-1',
        'before_data': {'weight': 10},
        'after_data': {'weight': 12, 'seq_no': 44},
      });
      expect(e.seqNo, '44');
      expect(e.summary, 'الوزن: 10 ← 12');
      expect(e.fromDesktop, isFalse);
    });

    test('الحذف يعرض الحركة المحذوفة، وحركات المزامنة بلا مستخدم', () {
      final e = AuditEntry.fromMap({
        'id': 2,
        'action': 'DELETE',
        'created_at': '2026-09-01T10:00:00+00:00',
        'before_data': {'seq_no': 7, 'account_name': 'مورد', 'op_type': 'وارد الماس', 'weight': 3},
      });
      expect(e.seqNo, '7');
      expect(e.summary, contains('مورد'));
      expect(e.fromDesktop, isTrue);
    });
  });

  group('Fmt', () {
    test('تنقّل الفترات عبر السنوات', () {
      expect(Fmt.shiftPeriod('2026-01', -1), '2025-12');
      expect(Fmt.shiftPeriod('2026-12', 1), '2027-01');
    });

    test('صحة صيغة الفترة', () {
      expect(Fmt.isValidPeriod('2026-09'), isTrue);
      expect(Fmt.isValidPeriod('2026-9'), isFalse);
      expect(Fmt.isValidPeriod(''), isFalse);
    });

    test('تاريخ العملية: اليوم المختار بساعة التسجيل الفعلية', () {
      final d = Fmt.operationDate(DateTime(2026, 8, 15), now: DateTime(2026, 9, 1, 13, 5, 9));
      expect(d, DateTime(2026, 8, 15, 13, 5, 9));
    });

    test('ترتيب أرقام الصفوف', () {
      final list = ['10', 'ب', '', '2', 'أ', '1.5']..sort(Fmt.compareRowNumbers);
      expect(list, ['1.5', '2', '10', 'أ', 'ب', '']);
    });
  });
}

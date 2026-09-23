import 'package:flutter_test/flutter_test.dart';
import 'package:jadeite_erp/core/constants/op_types.dart';
import 'package:jadeite_erp/data/models/models.dart';
import 'package:jadeite_erp/features/sales/sale_posting_service.dart';

void main() {
  const service = SalePostingService();
  final date = DateTime(2026, 9, 10, 14, 30);

  group('buildTransactions', () {
    test('ذهب مع ماس يُسجَّل بنوع خاص، والأحجار بعد الخصم بعلامتها', () {
      final txns = service.buildTransactions(
        lines: [
          SaleLine(
            rowNumber: '1',
            setNumber: 'S1',
            gold: 10,
            stonesRaw: 5,
            stonesAfterDiscount: 1.5,
            diamond: 0.4,
          ),
        ],
        customerName: 'عميل',
        date: date,
        manualInvoiceNo: '77',
        period: '2026-08',
      );

      expect(txns.map((t) => t.opType), [
        OpTypes.saleGoldWithDiamond,
        OpTypes.saleGemsStones,
        OpTypes.saleDiamond,
      ]);
      final stones = txns[1];
      expect(stones.weight, 1.5);
      expect(stones.weightBefore, 5, reason: 'الخام يُحفظ للطباعة فقط');
      expect(stones.treesCount, OpTypes.stonesDiscountMarker);
      expect(txns.every((t) => t.period == '2026-08'), isTrue,
          reason: 'الفترة الصريحة تنتقل لكل سطور الفاتورة');
      expect(txns.every((t) => t.manualNo == '77' && t.setNumber == 'S1'), isTrue);
    });

    test('الخياس يُرحَّل سطراً مستقلاً لصندوق خياس الطقوم ولا يدخل وزن الطقم', () {
      final line = SaleLine(setNumber: 'S2', gold: 8, khayas: 0.3);
      final txns = service.buildTransactions(
        lines: [line],
        customerName: 'عميل',
        date: date,
        manualInvoiceNo: '78',
      );
      expect(txns.map((t) => t.opType), [OpTypes.saleGold, OpTypes.setsKhayas]);
      expect(line.boundWeight, 8);
    });

    test('القيم الصفرية لا تُنشئ حركات', () {
      final txns = service.buildTransactions(
        lines: [SaleLine(gold: 0, gems: 2)],
        customerName: 'عميل',
        date: date,
        manualInvoiceNo: '1',
      );
      expect(txns, hasLength(1));
      expect(txns.single.opType, OpTypes.saleGemsStones);
    });
  });

  test('إعادة بناء السطور من الحركات تعطي الفاتورة نفسها', () {
    final original = [
      SaleLine(rowNumber: '1', setNumber: 'A', gold: 10, gems: 1, stonesRaw: 4,
          stonesAfterDiscount: 1.2, diamond: 0.5, khayas: 0.2),
      SaleLine(rowNumber: '2', setNumber: 'B', gold: 7),
    ];
    final txns = service.buildTransactions(
      lines: original,
      customerName: 'عميل',
      date: date,
      manualInvoiceNo: '9',
    );
    // الأرقام المتسلسلة تمنحها قاعدة البيانات بالترتيب
    final stored = [
      for (var i = 0; i < txns.length; i++)
        Txn(
          id: i + 1,
          seqNo: i + 1,
          date: txns[i].date,
          accountName: txns[i].accountName,
          opType: txns[i].opType,
          weight: txns[i].weight,
          weightBefore: txns[i].weightBefore,
          treesCount: txns[i].treesCount,
          setNumber: txns[i].setNumber,
          rowNumber: txns[i].rowNumber,
          manualNo: txns[i].manualNo,
        ),
    ];

    final rebuilt = service.rebuildLines(stored);
    expect(rebuilt, hasLength(2));
    expect(rebuilt[0].gold, 10);
    expect(rebuilt[0].gems, 1);
    expect(rebuilt[0].stonesRaw, 4);
    expect(rebuilt[0].stonesAfterDiscount, 1.2);
    expect(rebuilt[0].diamond, 0.5);
    expect(rebuilt[0].khayas, 0.2);
    expect(rebuilt[1].setNumber, 'B');
    expect(rebuilt[1].gold, 7);
  });

  test('منع تكرار رقم الصف أو رقم التشغيل داخل الفاتورة الواحدة', () {
    final lines = [SaleLine(rowNumber: '1', setNumber: 'A')];
    expect(service.duplicateError(lines, '1', 'X'), isNotNull);
    expect(service.duplicateError(lines, '2', 'A'), isNotNull);
    expect(service.duplicateError(lines, '2', 'B'), isNull);
    expect(service.duplicateError(lines, '1', 'A', skipIndex: 0), isNull,
        reason: 'تعديل السطر نفسه ليس تكراراً');
  });

  test('الأحجار بعد الخصم = الخام × النسبة', () {
    expect(service.stonesAfterDiscount(10, 30), 3);
    expect(service.stonesAfterDiscount(1.234, 30), 0.37);
  });
}

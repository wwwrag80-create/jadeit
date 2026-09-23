import '../../core/constants/op_types.dart';
import '../../data/models/models.dart';

/// منطق محاسبي نقي لتحويل سطور فاتورة المبيعات إلى حركات دفتر الأستاذ.
///
/// مصدر واحد للحقيقة يستخدمه الترحيل الجديد وتعديل الفاتورة المرحّلة معاً،
/// فيستحيل أن تختلف المعالجة المحاسبية بينهما.
///
/// قواعد ثابتة:
///  • "الأحجار" الخام لا تُعتمد كمبيعات إطلاقاً — المعتمد هو "الأحجار بعد الخصم"،
///    والخام يُحفظ في weight_before لغرض الطباعة فقط.
///  • الذهب المصاحب للماس يُسجَّل بنوع خاص ليُحتسب ضمن لوحة الألماس.
///  • خياس الطقم لا يدخل ضمن أوزان الطقم المباعة، بل يُرحّل لصندوق (خياس الطقوم)
///    فيُخصم من الخزينة ويظهر ضمن فواقد الورشة.
class SalePostingService {
  const SalePostingService();

  List<Txn> buildTransactions({
    required List<SaleLine> lines,
    required String customerName,
    required DateTime date,
    required String manualInvoiceNo,
  }) {
    final result = <Txn>[];

    for (final line in lines) {
      final goldType = (line.gold > 0 && line.diamond > 0)
          ? OpTypes.saleGoldWithDiamond
          : OpTypes.saleGold;

      final items = <({double value, String type, double marker, double rawRef})>[
        (value: line.gold, type: goldType, marker: 0, rawRef: 0),
        (value: line.gems, type: OpTypes.saleGemsStones, marker: 0, rawRef: 0),
        (
          value: line.stonesAfterDiscount,
          type: OpTypes.saleGemsStones,
          marker: OpTypes.stonesDiscountMarker,
          rawRef: line.stonesRaw,
        ),
        (value: line.diamond, type: OpTypes.saleDiamond, marker: 0, rawRef: 0),
      ];

      for (final item in items) {
        if (item.value <= 0) continue;
        result.add(Txn(
          id: 0,
          seqNo: 0,
          date: date,
          accountName: customerName,
          opType: item.type,
          weight: item.value,
          weightBefore: item.rawRef,
          note: 'مبيعات',
          treesCount: item.marker,
          setNumber: line.setNumber,
          rowNumber: line.rowNumber,
          manualNo: manualInvoiceNo,
        ));
      }

      if (line.khayas > 0) {
        result.add(Txn(
          id: 0,
          seqNo: 0,
          date: date,
          accountName: customerName,
          opType: OpTypes.setsKhayas,
          weight: line.khayas,
          note: 'خياس طقم',
          setNumber: line.setNumber,
          rowNumber: line.rowNumber,
          manualNo: manualInvoiceNo,
        ));
      }
    }

    return result;
  }

  /// إعادة بناء سطور الفاتورة من حركاتها المسجّلة (لفتحها في نافذة التعديل).
  List<SaleLine> rebuildLines(List<Txn> txns) {
    final map = <String, SaleLine>{};
    final order = <String>[];

    final sorted = [...txns]..sort((a, b) => a.seqNo.compareTo(b.seqNo));
    for (final t in sorted) {
      final key = t.setNumber;
      final line = map.putIfAbsent(key, () {
        order.add(key);
        return SaleLine(setNumber: key, rowNumber: t.rowNumber);
      });
      if (line.rowNumber.isEmpty && t.rowNumber.isNotEmpty) {
        line.rowNumber = t.rowNumber;
      }

      switch (t.opType) {
        case OpTypes.saleGold:
        case OpTypes.saleGoldWithDiamond:
          line.gold += t.weight;
        case OpTypes.saleGemsStones:
          if (t.treesCount == OpTypes.stonesDiscountMarker) {
            line.stonesRaw += t.weightBefore;
            line.stonesAfterDiscount += t.weight;
          } else {
            line.gems += t.weight;
          }
        case OpTypes.saleDiamond:
          line.diamond += t.weight;
        case OpTypes.setsKhayas:
          line.khayas += t.weight;
      }
    }

    return order.map((k) => map[k]!).toList();
  }

  /// يمنع تكرار رقم الصف أو رقم التشغيل داخل الفاتورة الواحدة فقط.
  /// بعد الترحيل تبدأ فاتورة جديدة، فيجوز استخدام رقم الصف ١ من جديد.
  String? duplicateError(
    List<SaleLine> lines,
    String rowNumber,
    String setNumber, {
    int? skipIndex,
  }) {
    for (var i = 0; i < lines.length; i++) {
      if (skipIndex != null && i == skipIndex) continue;
      if (rowNumber.isNotEmpty && lines[i].rowNumber == rowNumber) {
        return 'رقم الصف ($rowNumber) مسجّل بالفعل في سطر آخر من هذه الفاتورة.';
      }
      if (setNumber.isNotEmpty && lines[i].setNumber == setNumber) {
        return 'رقم التشغيل ($setNumber) مسجّل بالفعل في سطر آخر من هذه الفاتورة.\n'
            'كل رقم تشغيل يُطبع كفاتورة مستقلة، وتكراره يدمج السطرين في قالب واحد.';
      }
    }
    return null;
  }

  /// حساب الأحجار بعد الخصم من نسبة الخصم المعتمدة للمصنع
  double stonesAfterDiscount(double rawStones, double discountPct) =>
      double.parse((rawStones * (discountPct / 100)).toStringAsFixed(3));
}

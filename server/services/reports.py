"""الأرصدة، ملخص الحساب، كشف الحساب، تحليل حركة العميل.

كل الأرقام تُستخرج من دفتر الحركات (ledger_entries) أو من أسطر المستندات
المرحّلة نفسها — لا توجد أرقام مكتوبة يدوياً في أي مكان.
"""
from __future__ import annotations

from .. import fixed as F
from ..errors import NotFound, ValidationError
from .common import DOC_TYPES, MATERIALS, clean_line, name_key, optional_date


def direction_of(value_e4: int) -> str:
    return "debit" if value_e4 > 0 else ("credit" if value_e4 < 0 else "zero")


def _bal(value_e4: int, material: str) -> dict:
    dp = F.MATERIAL_DP[material]
    return {"value": F.fmt(abs(value_e4), dp), "signed": F.fmt(value_e4, dp), "e4": value_e4,
            "direction": direction_of(value_e4)}


def _account_status(values: list) -> str:
    nz = [v for v in values if v != 0]
    if not nz:
        return "settled"
    if all(v > 0 for v in nz):
        return "debit"
    if all(v < 0 for v in nz):
        return "credit"
    return "mixed"


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# ============================================================================
#  شاشة الأرصدة
# ============================================================================
_BAL_SQL = """
SELECT a.id, a.account_no, a.name, a.phone, a.is_active,
       COALESCE(g.net, 0) AS gold, COALESCE(g.karats, 0) AS gold_karats,
       COALESCE(d.net, 0) AS diamond, COALESCE(w.net, 0) AS wage
FROM accounts a
LEFT JOIN (SELECT account_id, SUM(debit_e4 - credit_e4) AS net,
                  SUM(CASE WHEN debit_e4 <> credit_e4 THEN 1 ELSE 0 END) AS karats
           FROM account_balances WHERE material = 'gold' GROUP BY account_id) g ON g.account_id = a.id
LEFT JOIN (SELECT account_id, SUM(debit_e4 - credit_e4) AS net
           FROM account_balances WHERE material = 'diamond' GROUP BY account_id) d ON d.account_id = a.id
LEFT JOIN (SELECT account_id, SUM(debit_e4 - credit_e4) AS net
           FROM account_balances WHERE material = 'wage' GROUP BY account_id) w ON w.account_id = a.id
"""

SORTS = {
    "name": "b.name COLLATE NOCASE",
    "account_no": "CAST(b.account_no AS INTEGER)",
    "gold": "b.gold",
    "diamond": "b.diamond",
    "wage": "b.wage",
}


def balances(db, params: dict) -> dict:
    q = clean_line(params.get("q"), 100)
    material = params.get("material") or "any"
    if material not in ("any", "gold", "diamond", "wage"):
        material = "any"
    flt = params.get("filter") or "all"  # all | nonzero | debit | credit | zero
    sort = params.get("sort") if params.get("sort") in SORTS else "account_no"
    direction = "DESC" if str(params.get("dir")).lower() == "desc" else "ASC"
    page = max(1, int(params.get("page") or 1))
    size = min(max(10, int(params.get("size") or 100)), 500)

    where, args = [], []
    if q:
        where.append("(b.name_key LIKE ? ESCAPE '\\' OR b.account_no LIKE ? ESCAPE '\\' OR b.phone LIKE ? ESCAPE '\\')")
        args += [_like(name_key(q)), _like(q) if not q.isdigit() else q + "%", _like(F.normalize_digits(q))]
    cols = ["b.gold", "b.diamond", "b.wage"] if material == "any" else [f"b.{material}"]
    if flt == "nonzero":
        where.append("(" + " OR ".join(f"{c} <> 0" for c in cols) + ")")
    elif flt == "debit":
        where.append("(" + " OR ".join(f"{c} > 0" for c in cols) + ")")
    elif flt == "credit":
        where.append("(" + " OR ".join(f"{c} < 0" for c in cols) + ")")
    elif flt == "zero":
        where.append("(" + " AND ".join(f"{c} = 0" for c in cols) + ")")
    if params.get("active") == "1":
        where.append("b.is_active = 1")

    base = f"SELECT b.* FROM ({_BAL_SQL.replace('a.is_active', 'a.is_active, a.name_key')}) b"
    if where:
        base += " WHERE " + " AND ".join(where)
    order = f" ORDER BY {SORTS[sort]} {direction}, CAST(b.account_no AS INTEGER) ASC"
    with db.read() as c:
        totals_row = c.execute(
            f"""SELECT COUNT(*) n,
                   SUM(CASE WHEN gold > 0 THEN gold ELSE 0 END) gd, SUM(CASE WHEN gold < 0 THEN -gold ELSE 0 END) gc,
                   SUM(CASE WHEN diamond > 0 THEN diamond ELSE 0 END) dd,
                   SUM(CASE WHEN diamond < 0 THEN -diamond ELSE 0 END) dc,
                   SUM(CASE WHEN wage > 0 THEN wage ELSE 0 END) wd, SUM(CASE WHEN wage < 0 THEN -wage ELSE 0 END) wc
                FROM ({base})""", args).fetchone()
        rows = c.execute(base + order + " LIMIT ? OFFSET ?", args + [size, (page - 1) * size]).fetchall()
    items = []
    for r in rows:
        items.append({
            "id": r["id"], "account_no": r["account_no"], "name": r["name"], "phone": r["phone"],
            "is_active": bool(r["is_active"]),
            "gold": _bal(r["gold"], "gold"), "diamond": _bal(r["diamond"], "diamond"),
            "wage": _bal(r["wage"], "wage"),
            "gold_mixed_karats": (r["gold_karats"] or 0) > 1,
            "status": _account_status([r["gold"], r["diamond"], r["wage"]]),
        })
    t = totals_row
    totals = {
        "count": t["n"] or 0,
        "gold": {"debit": F.fmt(t["gd"] or 0, 4), "credit": F.fmt(t["gc"] or 0, 4)},
        "diamond": {"debit": F.fmt(t["dd"] or 0, 3), "credit": F.fmt(t["dc"] or 0, 3)},
        "wage": {"debit": F.fmt(t["wd"] or 0, 2), "credit": F.fmt(t["wc"] or 0, 2)},
    }
    return {"items": items, "totals": totals, "page": page, "size": size,
            "pages": max(1, -(-(t["n"] or 0) // size))}


# ============================================================================
#  ملخص حساب واحد (اللوحة التفصيلية)
# ============================================================================
def account_summary(db, account_id: int) -> dict:
    with db.read() as c:
        acc = c.execute("SELECT * FROM accounts WHERE id = ?", (int(account_id),)).fetchone()
        if acc is None:
            raise NotFound("الحساب غير موجود")
        rows = c.execute("SELECT * FROM account_balances WHERE account_id = ?", (acc["id"],)).fetchall()
        docs = c.execute(
            """SELECT doc_type, COUNT(*) n FROM documents WHERE account_id = ? AND status = 'posted'
               GROUP BY doc_type""", (acc["id"],)).fetchall()
        recent = c.execute(
            """SELECT id, doc_no, doc_type, doc_date, status, description FROM documents WHERE account_id = ?
               ORDER BY doc_date DESC, posting_order DESC LIMIT 12""", (acc["id"],)).fetchall()
        last = c.execute("SELECT MAX(entry_date) FROM ledger_entries WHERE account_id = ?",
                         (acc["id"],)).fetchone()[0]
        opening = c.execute(
            """SELECT id, doc_no, doc_date FROM documents WHERE account_id = ? AND doc_type = 'opening'
               AND status = 'posted'""", (acc["id"],)).fetchone()
    sections = {}
    for m in MATERIALS:
        dr = sum(r["debit_e4"] for r in rows if r["material"] == m)
        cr = sum(r["credit_e4"] for r in rows if r["material"] == m)
        dp = F.MATERIAL_DP[m]
        sections[m] = {"debit": F.fmt(dr, dp), "credit": F.fmt(cr, dp), "balance": _bal(dr - cr, m)}
    by_karat = [
        {"karat": r["ref_karat"], "balance": _bal(r["debit_e4"] - r["credit_e4"], "gold"), "entries": r["entries"]}
        for r in sorted(rows, key=lambda r: r["ref_karat"]) if r["material"] == "gold" and r["entries"] > 0
    ]
    sections["gold"]["by_karat"] = by_karat
    sections["gold"]["mixed_karats"] = len([k for k in by_karat if k["balance"]["e4"] != 0]) > 1
    return {
        "account": {
            "id": acc["id"], "account_no": acc["account_no"], "name": acc["name"], "phone": acc["phone"],
            "notes": acc["notes"], "wage_rate": F.fmt_rate(acc["wage_rate_e4"]), "is_active": bool(acc["is_active"]),
            "created_at": acc["created_at"], "version": acc["version"],
        },
        "sections": sections,
        "status": _account_status([sections[m]["balance"]["e4"] for m in MATERIALS]),
        "doc_counts": {r["doc_type"]: r["n"] for r in docs},
        "recent": [dict(dict(r), type_label=DOC_TYPES[r["doc_type"]]) for r in recent],
        "last_movement": last,
        "opening": dict(opening) if opening else None,
    }


# ============================================================================
#  كشف الحساب
# ============================================================================
_ENTRY_SQL = """
SELECT l.*, d.doc_no, d.doc_type, d.status, d.description AS doc_description, d.notes AS doc_notes,
       d.posting_order, d.exception_reason, d.is_unlinked_return,
       o.doc_no AS original_doc_no,
       v.actual_e4 AS v_actual, v.actual_karat AS v_karat, v.working_karat AS v_wk,
       ol.description AS ol_description, ol.note AS ol_note, ol.actual_e4 AS ol_actual,
       ol.actual_karat AS ol_karat,
       tl.gold_e4 AS tl_gold, tl.rate_e4 AS tl_rate
FROM ledger_entries l
JOIN documents d ON d.id = l.doc_id
LEFT JOIN documents o ON o.id = d.original_doc_id
LEFT JOIN voucher_details v ON v.doc_id = d.id
LEFT JOIN opening_lines ol ON d.doc_type = 'opening' AND ol.id = l.source_line_id
LEFT JOIN trade_lines tl ON d.doc_type IN ('sale', 'return') AND tl.id = l.source_line_id
"""
_ORDER = """ ORDER BY l.entry_date, CASE WHEN d.doc_type = 'opening' THEN 0 ELSE 1 END,
             d.posting_order, l.is_reversal, l.line_no, l.id"""

KIND_LABEL = {"sale": "مبيعات", "return": "مرتجع مبيعات", "receipt": "قبض", "payment": "صرف",
              "opening": "رصيد افتتاحي"}


def _entry_text(r, material) -> str:
    t = r["doc_type"]
    if t == "opening":
        base = r["ol_description"] or r["doc_description"] or "رصيد افتتاحي"
        if material == "gold" and r["ol_karat"]:
            base += f" — الوزن الفعلي {F.fmt(r['ol_actual'], 4)} جم عيار {r['ol_karat']}"
        return base
    if t in ("receipt", "payment"):
        base = r["doc_description"] or KIND_LABEL[t]
        if material == "gold" and r["v_karat"]:
            base += f" — الوزن الفعلي {F.fmt(r['v_actual'], 4)} جم عيار {r['v_karat']}، مكافئ بعيار {r['v_wk']}"
        return base
    if t == "sale":
        base = r["doc_description"] or "فاتورة مبيعات"
        if material == "wage" and r["tl_gold"] is not None:
            base += f" — {F.fmt(r['tl_gold'], 4)} جم × {F.fmt_rate(r['tl_rate'])}"
        return base
    if t == "return":
        if r["original_doc_no"]:
            base = r["doc_description"] or f"مرتجع من الفاتورة {r['original_doc_no']}"
        else:
            base = (r["doc_description"] or "مرتجع غير مرتبط بفاتورة") + f" (استثناء: {r['exception_reason']})"
        if material == "wage" and r["tl_gold"] is not None:
            base += f" — أجر مسترد بأجر الفاتورة {F.fmt_rate(r['tl_rate'])}"
        return base
    return r["doc_description"] or ""


def statement(db, params: dict) -> dict:
    try:
        account_id = int(params.get("account_id"))
    except (TypeError, ValueError):
        raise ValidationError("اختر العميل")
    material = params.get("material")
    if material not in MATERIALS:
        raise ValidationError("اختر نوع الكشف (ذهب / ألماس / أجور)")
    date_from = optional_date(params.get("date_from"), "من تاريخ")
    date_to = optional_date(params.get("date_to"), "إلى تاريخ")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("تاريخ البداية بعد تاريخ النهاية")
    dp = F.MATERIAL_DP[material]
    with db.read() as c:
        acc = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if acc is None:
            raise NotFound("الحساب غير موجود")
        opening = 0
        if date_from:
            opening = c.execute(
                """SELECT COALESCE(SUM(debit_e4 - credit_e4), 0) FROM ledger_entries
                   WHERE account_id = ? AND material = ? AND entry_date < ?""",
                (account_id, material, date_from)).fetchone()[0]
        where = ["l.account_id = ?", "l.material = ?"]
        args = [account_id, material]
        if date_from:
            where.append("l.entry_date >= ?")
            args.append(date_from)
        if date_to:
            where.append("l.entry_date <= ?")
            args.append(date_to)
        rows = c.execute(_ENTRY_SQL + " WHERE " + " AND ".join(where) + _ORDER, args).fetchall()
        total_now = c.execute(
            """SELECT COALESCE(SUM(debit_e4 - credit_e4), 0) FROM ledger_entries
               WHERE account_id = ? AND material = ?""", (account_id, material)).fetchone()[0]
    running = opening
    tdr = tcr = 0
    out_rows = []
    karats = set()
    for r in rows:
        running += r["debit_e4"] - r["credit_e4"]
        tdr += r["debit_e4"]
        tcr += r["credit_e4"]
        if r["ref_karat"]:
            karats.add(r["ref_karat"])
        kind = KIND_LABEL[r["doc_type"]]
        text = _entry_text(r, material)
        if r["is_reversal"]:
            kind = "إلغاء " + kind
            text = f"قيد عكسي لإلغاء المستند {r['doc_no']}"
        notes = r["doc_notes"] or ""
        if r["doc_type"] == "opening" and r["ol_note"]:
            notes = r["ol_note"]
        out_rows.append({
            "date": r["entry_date"], "doc_id": r["doc_id"], "doc_no": r["doc_no"], "doc_type": r["doc_type"],
            "kind": kind, "text": text, "run_no": r["run_no"],
            "debit": F.fmt(r["debit_e4"], dp) if r["debit_e4"] else "",
            "credit": F.fmt(r["credit_e4"], dp) if r["credit_e4"] else "",
            "balance": _bal(running, material), "notes": notes, "ref_karat": r["ref_karat"],
            "is_reversal": bool(r["is_reversal"]), "cancelled": r["status"] == "cancelled",
        })
    return {
        "account": {"id": acc["id"], "account_no": acc["account_no"], "name": acc["name"],
                    "wage_rate": F.fmt_rate(acc["wage_rate_e4"])},
        "material": material,
        "date_from": date_from, "date_to": date_to,
        "opening": _bal(opening, material),
        "rows": out_rows,
        "totals": {"debit": F.fmt(tdr, dp), "credit": F.fmt(tcr, dp), "count": len(out_rows)},
        "closing": _bal(running, material),
        "account_balance_all_time": _bal(total_now, material),
        "ref_karats": sorted(karats),
        "mixed_karats": len(karats) > 1,
    }


# ============================================================================
#  تحليل حركة العميل
# ============================================================================
def analysis(db, params: dict) -> dict:
    try:
        account_id = int(params.get("account_id"))
    except (TypeError, ValueError):
        raise ValidationError("اختر العميل")
    date_from = optional_date(params.get("date_from"), "من تاريخ")
    date_to = optional_date(params.get("date_to"), "إلى تاريخ")
    if date_from and date_to and date_from > date_to:
        raise ValidationError("تاريخ البداية بعد تاريخ النهاية")
    period_sql, period_args = "", []
    if date_from:
        period_sql += " AND d.doc_date >= ?"
        period_args.append(date_from)
    if date_to:
        period_sql += " AND d.doc_date <= ?"
        period_args.append(date_to)

    with db.read() as c:
        acc = c.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if acc is None:
            raise NotFound("الحساب غير موجود")
        trade = c.execute(
            f"""SELECT d.id doc_id, d.doc_no, d.doc_type, d.doc_date, d.description, d.is_unlinked_return,
                       d.exception_reason, d.original_doc_id, o.doc_no AS original_doc_no, o.doc_date AS original_date,
                       tl.run_no, tl.gold_e4, tl.diamond_e4, tl.rate_e4, tl.wage_e4, tl.line_no
                FROM trade_lines tl JOIN documents d ON d.id = tl.doc_id
                LEFT JOIN documents o ON o.id = d.original_doc_id
                WHERE d.account_id = ? AND d.status = 'posted' {period_sql}
                ORDER BY d.doc_date, d.posting_order, tl.line_no""",
            [account_id] + period_args).fetchall()
        vouchers = c.execute(
            f"""SELECT d.id doc_id, d.doc_no, d.doc_type, d.doc_date, d.description, d.notes,
                       v.material, v.actual_e4, v.actual_karat, v.working_karat, v.equivalent_e4
                FROM voucher_details v JOIN documents d ON d.id = v.doc_id
                WHERE d.account_id = ? AND d.status = 'posted' {period_sql}
                ORDER BY d.doc_date, d.posting_order""",
            [account_id] + period_args).fetchall()
        cancelled = c.execute(
            f"""SELECT COUNT(*) FROM documents d WHERE d.account_id = ? AND d.status = 'cancelled'
                AND d.doc_type <> 'opening' {period_sql}""", [account_id] + period_args).fetchone()[0]
        bal_rows = c.execute(
            """SELECT material, SUM(debit_e4 - credit_e4) b FROM ledger_entries WHERE account_id = ?
               GROUP BY material""", (account_id,)).fetchall()
        end_args = [account_id]
        end_sql = ""
        if date_to:
            end_sql = " AND entry_date <= ?"
            end_args.append(date_to)
        end_rows = c.execute(
            f"""SELECT material, SUM(debit_e4 - credit_e4) b FROM ledger_entries WHERE account_id = ? {end_sql}
                GROUP BY material""", end_args).fetchall()

    sales, returns = [], []
    s_tot = {"gold": 0, "diamond": 0, "wage": 0}
    r_tot = {"gold": 0, "diamond": 0, "wage": 0}
    net = {}  # مفتاح التجميع: الفاتورة الأصلية أو المرتجع غير المرتبط

    def net_row(key, doc_no, doc_date, kind):
        if key not in net:
            net[key] = {"key": key, "doc_no": doc_no, "doc_date": doc_date, "kind": kind,
                        "sold": {"gold": 0, "diamond": 0, "wage": 0},
                        "returned": {"gold": 0, "diamond": 0, "wage": 0}}
        return net[key]

    for r in trade:
        vals = {"gold": r["gold_e4"], "diamond": r["diamond_e4"], "wage": r["wage_e4"]}
        if r["doc_type"] == "sale":
            sales.append({
                "date": r["doc_date"], "doc_id": r["doc_id"], "doc_no": r["doc_no"], "run_no": r["run_no"],
                "gold": F.fmt(r["gold_e4"], 4), "diamond": F.fmt(r["diamond_e4"], 3),
                "rate": F.fmt_rate(r["rate_e4"]), "wage": F.fmt(r["wage_e4"], 2),
            })
            for k in s_tot:
                s_tot[k] += vals[k]
            row = net_row(f"s{r['doc_id']}", r["doc_no"], r["doc_date"], "invoice")
            for k in vals:
                row["sold"][k] += vals[k]
        else:
            returns.append({
                "date": r["doc_date"], "doc_id": r["doc_id"], "doc_no": r["doc_no"],
                "original_doc_no": r["original_doc_no"] or "", "run_no": r["run_no"],
                "gold": F.fmt(r["gold_e4"], 4), "diamond": F.fmt(r["diamond_e4"], 3),
                "wage": F.fmt(r["wage_e4"], 2),
                "text": r["description"] or (f"مرتجع من {r['original_doc_no']}" if r["original_doc_no"]
                                             else "مرتجع غير مرتبط"),
                "unlinked": bool(r["is_unlinked_return"]), "exception_reason": r["exception_reason"],
            })
            for k in r_tot:
                r_tot[k] += vals[k]
            if r["original_doc_id"]:
                row = net_row(f"s{r['original_doc_id']}", r["original_doc_no"], r["original_date"], "invoice")
            else:
                row = net_row(f"u{r['doc_id']}", r["doc_no"], r["doc_date"], "unlinked")
            for k in vals:
                row["returned"][k] += vals[k]

    dps = {"gold": 4, "diamond": 3, "wage": 2}

    def fmt3(d):
        return {k: F.fmt(v, dps[k]) for k, v in d.items()}

    net_rows = []
    for row in sorted(net.values(), key=lambda x: (x["kind"] != "invoice", x["doc_date"], x["doc_no"])):
        n = {k: row["sold"][k] - row["returned"][k] for k in dps}
        net_rows.append({
            "doc_no": row["doc_no"], "doc_date": row["doc_date"], "kind": row["kind"],
            "sold": fmt3(row["sold"]), "returned": fmt3(row["returned"]),
            "net": {k: _bal(n[k], k) for k in dps},
            "invoice_outside_period": row["kind"] == "invoice" and row["sold"]["gold"] == 0
            and row["sold"]["diamond"] == 0 and row["sold"]["wage"] == 0,
        })

    pays = []
    p_tot = {m: {"in": 0, "out": 0} for m in MATERIALS}
    for v in vouchers:
        dp = F.MATERIAL_DP[v["material"]]
        pays.append({
            "date": v["doc_date"], "doc_id": v["doc_id"], "doc_no": v["doc_no"],
            "kind": "قبض" if v["doc_type"] == "receipt" else "صرف", "doc_type": v["doc_type"],
            "material": v["material"], "actual": F.fmt(v["actual_e4"], dp),
            "karat": v["actual_karat"], "working_karat": v["working_karat"],
            "equivalent": F.fmt(v["equivalent_e4"], dp) if v["material"] == "gold" else "",
            "text": v["description"],
        })
        p_tot[v["material"]]["in" if v["doc_type"] == "receipt" else "out"] += v["equivalent_e4"]

    current = {m: 0 for m in MATERIALS}
    for r in bal_rows:
        current[r["material"]] = r["b"] or 0
    at_end = {m: 0 for m in MATERIALS}
    for r in end_rows:
        at_end[r["material"]] = r["b"] or 0

    net_tot = {k: s_tot[k] - r_tot[k] for k in dps}
    return {
        "account": {"id": acc["id"], "account_no": acc["account_no"], "name": acc["name"],
                    "wage_rate": F.fmt_rate(acc["wage_rate_e4"])},
        "date_from": date_from, "date_to": date_to,
        "sales": {"rows": sales, "totals": fmt3(s_tot), "count": len(sales)},
        "returns": {"rows": returns, "totals": fmt3(r_tot), "count": len(returns),
                    "unlinked_count": len([r for r in returns if r["unlinked"]])},
        "net": {"rows": net_rows, "totals": {k: _bal(net_tot[k], k) for k in dps}},
        "payments": {
            "rows": pays,
            "totals": {m: {"in": F.fmt(p_tot[m]["in"], F.MATERIAL_DP[m]),
                           "out": F.fmt(p_tot[m]["out"], F.MATERIAL_DP[m]),
                           "net": F.fmt(p_tot[m]["in"] - p_tot[m]["out"], F.MATERIAL_DP[m])}
                       for m in MATERIALS},
            "count": len(pays),
        },
        "balances": {m: _bal(current[m], m) for m in MATERIALS},
        "balances_at_end": {m: _bal(at_end[m], m) for m in MATERIALS},
        "cancelled_count": cancelled,
    }

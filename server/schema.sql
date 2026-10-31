-- ============================================================================
--  جاديت — نظام حسابات العملاء (ذهب / ألماس / أجور)
--  مخطط قاعدة البيانات (SQLite)
--
--  قواعد عامة:
--   • كل الكميات أعداد صحيحة بمقياس 10,000 (لاحقة _e4) — لا أرقام عشرية ثنائية.
--   • المصدر الوحيد للأرصدة هو جدول ledger_entries (دفتر الحركات المحاسبية).
--   • قيود الدفتر لا تُعدَّل (UPDATE ممنوع بمشغّل)، وسجل التدقيق لا يُعدَّل ولا يُحذف.
--   • المستند لا يُحفظ إلا مع كل أسطره وقيوده داخل معاملة واحدة.
-- ============================================================================

-- ---------------------------------------------------------------- المستخدمون
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    username        TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    full_name       TEXT    NOT NULL,
    password_hash   TEXT    NOT NULL,              -- scrypt + ملح عشوائي (لا نص واضح)
    is_admin        INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    permissions     TEXT    NOT NULL DEFAULT '[]', -- JSON: قائمة الصلاحيات
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT    PRIMARY KEY,                -- SHA-256 للرمز (الرمز نفسه لا يُخزَّن)
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);

-- ---------------------------------------------------------------- الإعدادات
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    updated_by  INTEGER REFERENCES users(id)
);

-- سجل تغييرات عيار العمل المعتمد (لا يُحذف)
CREATE TABLE IF NOT EXISTS karat_history (
    id              INTEGER PRIMARY KEY,
    karat           INTEGER NOT NULL CHECK (karat IN (18, 21, 22, 24)),
    previous_karat  INTEGER CHECK (previous_karat IN (18, 21, 22, 24)),
    reason          TEXT    NOT NULL,
    changed_at      TEXT    NOT NULL,
    changed_by      INTEGER REFERENCES users(id)
);

-- عدادات الترقيم الفريد (الحسابات، كل نوع مستند، ترتيب الترحيل)
CREATE TABLE IF NOT EXISTS sequences (
    name        TEXT    PRIMARY KEY,
    last_value  INTEGER NOT NULL
);

-- ---------------------------------------------------------------- الحسابات
CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY,
    account_no      TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    name_key        TEXT    NOT NULL UNIQUE,   -- الاسم بعد التوحيد لمنع التكرار
    phone           TEXT    NOT NULL DEFAULT '',
    notes           TEXT    NOT NULL DEFAULT '',
    wage_rate_e4    INTEGER NOT NULL CHECK (wage_rate_e4 >= 0),  -- الأجر الافتراضي لكل جرام
    is_active       INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    client_token    TEXT    UNIQUE,            -- يمنع إنشاء الحساب مرتين عند تكرار الضغط
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL,
    created_by      INTEGER REFERENCES users(id),
    updated_at      TEXT    NOT NULL,
    updated_by      INTEGER REFERENCES users(id)
);

-- ---------------------------------------------------------------- المستندات
--  sale     = فاتورة مبيعات          return  = مرتجع مبيعات
--  receipt  = سند قبض                payment = سند صرف
--  opening  = رصيد افتتاحي
CREATE TABLE IF NOT EXISTS documents (
    id                  INTEGER PRIMARY KEY,
    doc_type            TEXT    NOT NULL CHECK (doc_type IN ('sale', 'return', 'receipt', 'payment', 'opening')),
    seq                 INTEGER NOT NULL,
    doc_no              TEXT    NOT NULL UNIQUE,
    posting_order       INTEGER NOT NULL UNIQUE,   -- ترتيب ثابت للعرض داخل اليوم الواحد
    account_id          INTEGER NOT NULL REFERENCES accounts(id),
    doc_date            TEXT    NOT NULL CHECK (doc_date GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    working_karat       INTEGER NOT NULL CHECK (working_karat IN (18, 21, 22, 24)),  -- لقطة وقت الترحيل
    original_doc_id     INTEGER REFERENCES documents(id),  -- المرتجع: الفاتورة الأصلية
    is_unlinked_return  INTEGER NOT NULL DEFAULT 0 CHECK (is_unlinked_return IN (0, 1)),
    exception_reason    TEXT    NOT NULL DEFAULT '',       -- سبب المرتجع غير المرتبط
    description         TEXT    NOT NULL DEFAULT '',       -- البيان
    notes               TEXT    NOT NULL DEFAULT '',
    status              TEXT    NOT NULL DEFAULT 'posted' CHECK (status IN ('posted', 'cancelled')),
    client_token        TEXT    NOT NULL UNIQUE,           -- مفتاح منع الترحيل المكرر
    version             INTEGER NOT NULL DEFAULT 1,
    posted_at           TEXT    NOT NULL,
    posted_by           INTEGER NOT NULL REFERENCES users(id),
    updated_at          TEXT,
    updated_by          INTEGER REFERENCES users(id),
    cancelled_at        TEXT,
    cancelled_by        INTEGER REFERENCES users(id),
    cancel_reason       TEXT    NOT NULL DEFAULT '',
    UNIQUE (doc_type, seq),
    CHECK (doc_type = 'return' OR (original_doc_id IS NULL AND is_unlinked_return = 0)),
    CHECK (doc_type <> 'return' OR (original_doc_id IS NOT NULL) <> (is_unlinked_return = 1)),
    CHECK (is_unlinked_return = 0 OR length(trim(exception_reason)) > 0),
    CHECK (status = 'posted' OR length(trim(cancel_reason)) > 0)
);
CREATE INDEX IF NOT EXISTS ix_documents_account  ON documents(account_id, doc_date);
CREATE INDEX IF NOT EXISTS ix_documents_date     ON documents(doc_date);
CREATE INDEX IF NOT EXISTS ix_documents_original ON documents(original_doc_id);
-- رصيد افتتاحي واحد فعّال لكل حساب (التعديل يتم على المستند نفسه بصلاحية)
CREATE UNIQUE INDEX IF NOT EXISTS ux_opening_per_account
    ON documents(account_id) WHERE doc_type = 'opening' AND status = 'posted';

-- أسطر المبيعات والمرتجعات
CREATE TABLE IF NOT EXISTS trade_lines (
    id                  INTEGER PRIMARY KEY,
    doc_id              INTEGER NOT NULL REFERENCES documents(id),
    line_no             INTEGER NOT NULL,
    run_no              TEXT    NOT NULL DEFAULT '',     -- رقم التشغيل كما أدخله المستخدم (نص)
    gold_e4             INTEGER NOT NULL CHECK (gold_e4 >= 0),
    diamond_e4          INTEGER NOT NULL CHECK (diamond_e4 >= 0),
    rate_e4             INTEGER NOT NULL CHECK (rate_e4 >= 0),   -- الأجر المعتمد لكل جرام (لقطة)
    wage_e4             INTEGER NOT NULL CHECK (wage_e4 >= 0),   -- = round(gold × rate, 2)
    rate_overridden     INTEGER NOT NULL DEFAULT 0 CHECK (rate_overridden IN (0, 1)),
    original_line_id    INTEGER REFERENCES trade_lines(id),      -- سطر البيع الأصلي (للمرتجع)
    CHECK (gold_e4 > 0 OR diamond_e4 > 0),
    UNIQUE (doc_id, line_no)
);
CREATE INDEX IF NOT EXISTS ix_trade_lines_doc  ON trade_lines(doc_id);
CREATE INDEX IF NOT EXISTS ix_trade_lines_run  ON trade_lines(run_no);
CREATE INDEX IF NOT EXISTS ix_trade_lines_orig ON trade_lines(original_line_id);

-- تفاصيل سندات القبض والصرف (سطر واحد لكل سند)
CREATE TABLE IF NOT EXISTS voucher_details (
    doc_id          INTEGER PRIMARY KEY REFERENCES documents(id),
    material        TEXT    NOT NULL CHECK (material IN ('gold', 'diamond', 'wage')),
    actual_e4       INTEGER NOT NULL CHECK (actual_e4 > 0),       -- الوزن الفعلي / المبلغ
    actual_karat    INTEGER CHECK (actual_karat IN (18, 21, 22, 24)),
    working_karat   INTEGER CHECK (working_karat IN (18, 21, 22, 24)),
    equivalent_e4   INTEGER NOT NULL CHECK (equivalent_e4 > 0),   -- الوزن المكافئ (= الفعلي لغير الذهب)
    CHECK ((material = 'gold') = (actual_karat IS NOT NULL AND working_karat IS NOT NULL)),
    CHECK (material = 'gold' OR equivalent_e4 = actual_e4)
);

-- أسطر الرصيد الافتتاحي (ذهب / ألماس / أجور — كلٌّ بسطر مستقل واتجاه مستقل)
CREATE TABLE IF NOT EXISTS opening_lines (
    id              INTEGER PRIMARY KEY,
    doc_id          INTEGER NOT NULL REFERENCES documents(id),
    line_no         INTEGER NOT NULL,
    material        TEXT    NOT NULL CHECK (material IN ('gold', 'diamond', 'wage')),
    direction       TEXT    NOT NULL CHECK (direction IN ('debit', 'credit')),
    actual_e4       INTEGER NOT NULL CHECK (actual_e4 > 0),
    actual_karat    INTEGER CHECK (actual_karat IN (18, 21, 22, 24)),
    working_karat   INTEGER CHECK (working_karat IN (18, 21, 22, 24)),
    equivalent_e4   INTEGER NOT NULL CHECK (equivalent_e4 > 0),
    description     TEXT    NOT NULL DEFAULT '',
    note            TEXT    NOT NULL DEFAULT '',
    CHECK ((material = 'gold') = (actual_karat IS NOT NULL AND working_karat IS NOT NULL)),
    CHECK (material = 'gold' OR equivalent_e4 = actual_e4),
    UNIQUE (doc_id, line_no)
);
CREATE INDEX IF NOT EXISTS ix_opening_lines_doc ON opening_lines(doc_id);

-- ---------------------------------------------------------------- دفتر الحركات
--  مدين  = يزيد مستحقات الحساب (على العميل)
--  دائن  = يخفض مستحقات الحساب (للعميل)
--  الرصيد = مجموع المدين − مجموع الدائن  (موجب: مدين، سالب: دائن)
CREATE TABLE IF NOT EXISTS ledger_entries (
    id              INTEGER PRIMARY KEY,
    doc_id          INTEGER NOT NULL REFERENCES documents(id),
    account_id      INTEGER NOT NULL REFERENCES accounts(id),
    entry_date      TEXT    NOT NULL,
    material        TEXT    NOT NULL CHECK (material IN ('gold', 'diamond', 'wage')),
    debit_e4        INTEGER NOT NULL DEFAULT 0 CHECK (debit_e4 >= 0),
    credit_e4       INTEGER NOT NULL DEFAULT 0 CHECK (credit_e4 >= 0),
    ref_karat       INTEGER CHECK (ref_karat IN (18, 21, 22, 24)),  -- عيار العمل الذي يُعبّر به وزن الذهب
    line_no         INTEGER NOT NULL DEFAULT 0,
    source_line_id  INTEGER,
    run_no          TEXT    NOT NULL DEFAULT '',
    is_reversal     INTEGER NOT NULL DEFAULT 0 CHECK (is_reversal IN (0, 1)),
    created_at      TEXT    NOT NULL,
    CHECK ((debit_e4 > 0 AND credit_e4 = 0) OR (credit_e4 > 0 AND debit_e4 = 0)),
    CHECK ((material = 'gold') = (ref_karat IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS ix_ledger_account ON ledger_entries(account_id, material, entry_date);
CREATE INDEX IF NOT EXISTS ix_ledger_doc     ON ledger_entries(doc_id);

-- القيود غير قابلة للتعديل: أي تصحيح يتم بإعادة توليد قيود المستند أو بقيد عكسي
CREATE TRIGGER IF NOT EXISTS trg_ledger_no_update
BEFORE UPDATE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'ledger entries are immutable');
END;

-- ---------------------------------------------------------------- الأرصدة المحفوظة
--  ملخص محسوب من الدفتر لتسريع شاشة الأرصدة مع آلاف الحسابات.
--  يُحدَّث بمشغّلات داخل نفس معاملة القيد، فيستحيل أن يختلف عن الدفتر؛
--  وفحص السلامة يعيد حسابه من الدفتر ويقارن.
CREATE TABLE IF NOT EXISTS account_balances (
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    material    TEXT    NOT NULL CHECK (material IN ('gold', 'diamond', 'wage')),
    ref_karat   INTEGER NOT NULL DEFAULT 0,      -- عيار العمل للذهب، و0 لغيره
    debit_e4    INTEGER NOT NULL DEFAULT 0,
    credit_e4   INTEGER NOT NULL DEFAULT 0,
    entries     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, material, ref_karat)
);

CREATE TRIGGER IF NOT EXISTS trg_balances_on_insert
AFTER INSERT ON ledger_entries
BEGIN
    INSERT INTO account_balances(account_id, material, ref_karat, debit_e4, credit_e4, entries)
    VALUES (NEW.account_id, NEW.material, COALESCE(NEW.ref_karat, 0), NEW.debit_e4, NEW.credit_e4, 1)
    ON CONFLICT(account_id, material, ref_karat) DO UPDATE SET
        debit_e4  = debit_e4  + excluded.debit_e4,
        credit_e4 = credit_e4 + excluded.credit_e4,
        entries   = entries + 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_balances_on_delete
AFTER DELETE ON ledger_entries
BEGIN
    UPDATE account_balances SET
        debit_e4  = debit_e4  - OLD.debit_e4,
        credit_e4 = credit_e4 - OLD.credit_e4,
        entries   = entries - 1
    WHERE account_id = OLD.account_id AND material = OLD.material AND ref_karat = COALESCE(OLD.ref_karat, 0);
END;

-- القيد يجب أن يخص حساب المستند نفسه وتاريخه
CREATE TRIGGER IF NOT EXISTS trg_ledger_matches_document
BEFORE INSERT ON ledger_entries
WHEN NEW.account_id <> (SELECT account_id FROM documents WHERE id = NEW.doc_id)
  OR NEW.entry_date <> (SELECT doc_date FROM documents WHERE id = NEW.doc_id)
BEGIN
    SELECT RAISE(ABORT, 'ledger entry does not match its document');
END;

-- ---------------------------------------------------------------- سجل التدقيق
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY,
    at          TEXT    NOT NULL,
    user_id     INTEGER REFERENCES users(id),
    action      TEXT    NOT NULL,
    entity      TEXT    NOT NULL,
    entity_id   INTEGER,
    ref         TEXT    NOT NULL DEFAULT '',
    reason      TEXT    NOT NULL DEFAULT '',
    before_json TEXT,
    after_json  TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_log(entity, entity_id);

CREATE TRIGGER IF NOT EXISTS trg_audit_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_audit_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit log is append-only');
END;

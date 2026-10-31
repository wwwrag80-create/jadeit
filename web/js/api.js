// طبقة الاتصال بالخادم: JSON + ترويسة الحماية + رسائل أخطاء عربية موحّدة.

export class ApiError extends Error {
  constructor(status, payload) {
    const err = (payload && payload.error) || {};
    super(err.message || "تعذر الاتصال بالخادم");
    this.status = status;
    this.code = err.code || "network";
    this.details = err.details || null;
  }
}

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

async function request(method, path, body, { raw = false, timeout = 30000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeout);
  const headers = { "X-Requested-With": "jadeit" };
  let payload;
  if (raw) {
    payload = body;
    headers["Content-Type"] = "application/octet-stream";
  } else if (body !== undefined) {
    payload = JSON.stringify(body);
    headers["Content-Type"] = "application/json";
  }
  let resp;
  try {
    resp = await fetch(path, { method, headers, body: payload, credentials: "same-origin", signal: ctrl.signal });
  } catch (e) {
    throw new ApiError(0, { error: { code: "network", message: "انقطع الاتصال بالخادم. تحقق من تشغيل النظام ثم أعد المحاولة — لن يُكرَّر أي مستند عند إعادة المحاولة." } });
  } finally {
    clearTimeout(timer);
  }
  const ctype = resp.headers.get("Content-Type") || "";
  if (!ctype.includes("json")) {
    if (!resp.ok) throw new ApiError(resp.status, null);
    return resp;
  }
  const data = await resp.json();
  if (!resp.ok) {
    const err = new ApiError(resp.status, data);
    if (resp.status === 401 && !path.startsWith("/api/login")) onUnauthorized(err);
    throw err;
  }
  return data;
}

function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== "") p.set(k, v);
  }
  const s = p.toString();
  return s ? "?" + s : "";
}

export const api = {
  get: (path, params) => request("GET", path + qs(params)),
  post: (path, body) => request("POST", path, body ?? {}),
  put: (path, body) => request("PUT", path, body ?? {}),
  upload: (path, blob) => request("POST", path, blob, { raw: true, timeout: 300000 }),
  download: async (path) => {
    const resp = await request("GET", path);
    return resp;
  },
};

/**
 * إرسال مستند مع إعادة المحاولة التلقائية عند انقطاع الشبكة فقط.
 * مفتاح العملية (client_token) ثابت، لذلك إعادة الإرسال لا تكرر الترحيل أبداً.
 */
export async function postWithRetry(path, body, tries = 3) {
  let last;
  for (let i = 0; i < tries; i++) {
    try {
      return await api.post(path, body);
    } catch (e) {
      last = e;
      if (e.code !== "network") throw e;
      await new Promise((r) => setTimeout(r, 800 * (i + 1)));
    }
  }
  throw last;
}

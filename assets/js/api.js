/**
 * 立米AI Ryu兵衛 - バックエンドAPI通信モジュール
 *
 * 使い方:
 *   const jobs = await RyubeeAPI.fetchJobs();
 *   const token = await RyubeeAPI.authLogin(email, password);
 */

// ── 環境切り替え ─────────────────────────────────────────────
// ローカル開発: http://localhost:8000
// 本番Render:   https://ryubee-api-new.onrender.com
const API_BASE = (() => {
  const host = location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return "http://localhost:8000";
  }
  return "https://ryubee-api-v2.onrender.com";
})();

// ── 共通フェッチラッパー ──────────────────────────────────────
async function apiFetch(path, options = {}) {
  const token = localStorage.getItem("ryubee_token");
  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  // FormData の場合は Content-Type を削除（ブラウザに自動設定させる）
  if (options.body instanceof FormData) {
    delete headers["Content-Type"];
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    // トークン期限切れ → 強制ログアウト
    localStorage.removeItem("ryubee_token");
    localStorage.removeItem("ryubee_user");
    window.location.href = "login.html";
    throw new Error("セッションが切れました。再ログインしてください。");
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const err = await res.json();
      msg = err.detail || JSON.stringify(err);
    } catch (_) { }
    throw new Error(msg);
  }

  // 204 No Content
  if (res.status === 204) return null;

  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────
const RyubeeAPI = {
  baseUrl: API_BASE,

  getToken() {
    return localStorage.getItem("ryubee_token");
  },

  getHeaders() {
    const token = this.getToken();
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };
  },

  async authLogin(email, password) {
    const data = await apiFetch("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem("ryubee_token", data.token);
    localStorage.setItem("ryubee_user", JSON.stringify(data.user));
    return data;
  },

  async authRegister(companyName, email, password, name = "") {
    const data = await apiFetch("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ company_name: companyName, email, password, name }),
    });
    localStorage.setItem("ryubee_token", data.token);
    localStorage.setItem("ryubee_user", JSON.stringify(data.user));
    return data;
  },

  async authMe() {
    return apiFetch("/v1/auth/me");
  },

  authLogout() {
    localStorage.removeItem("ryubee_token");
    localStorage.removeItem("ryubee_user");
    window.location.href = "login.html";
  },

  isAdmin() {
    const userStr = localStorage.getItem("ryubee_user");
    if (!userStr) return false;
    try {
      return JSON.parse(userStr).role === "admin";
    } catch { return false; }
  },

  /** ログイン済みかチェック。未ログインなら login.html へ飛ばす */
  requireAuth() {
    const token = localStorage.getItem("ryubee_token");
    if (!token) {
      window.location.href = "login.html";
      return false;
    }
    return true;
  },

  /** 管理者権限チェック。非管理者なら pipeline.html へ飛ばす */
  requireAdmin() {
    if (!this.requireAuth()) return false;
    if (!this.isAdmin()) {
      alert("管理者権限がありません。");
      window.location.href = "pipeline.html";
      return false;
    }
    return true;
  },

  /** 現在のユーザー情報を取得（localStorageキャッシュ） */
  currentUser() {
    try {
      return JSON.parse(localStorage.getItem("ryubee_user") || "null");
    } catch {
      return null;
    }
  },

  // ── Jobs ────────────────────────────────────────────────────

  async fetchJobs({ status = null, q = null } = {}) {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    const qs = params.toString();
    return apiFetch(`/v1/jobs${qs ? "?" + qs : ""}`);
  },

  async fetchJob(jobId) {
    return apiFetch(`/v1/jobs/${jobId}`);
  },

  async createJob(body) {
    return apiFetch("/v1/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateJob(jobId, body) {
    return apiFetch(`/v1/jobs/${jobId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async deleteJob(jobId) {
    return apiFetch(`/v1/jobs/${jobId}`, { method: "DELETE" });
  },

  // ── Settings ─────────────────────────────────────────────────

  async fetchSettings() {
    return apiFetch("/v1/settings");
  },

  async saveSettings(body) {
    return apiFetch("/v1/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  // ── Admin ────────────────────────────────────────────────────

  async fetchAdminSummary() {
    return apiFetch("/v1/admin/summary");
  },

  async fetchSalesChart(days = 7) {
    return apiFetch(`/v1/admin/sales-chart?days=${days}`);
  },

  async fetchStaffRanking() {
    return apiFetch("/v1/admin/staff-ranking");
  },

  // ── Volume Estimate (AI) ──────────────────────────────────────

  async estimateVolume(formData) {
    return apiFetch("/v1/volume-estimate", {
      method: "POST",
      body: formData,
      headers: {}, // Content-Type は自動（FormData）
    });
  },

  // ── Invoices (請求書) ──────────────────────────────────────

  async fetchInvoices({ month = null, status = null, customer_id = null } = {}) {
    const params = new URLSearchParams();
    if (month) params.set("month", month);
    if (status) params.set("status", status);
    if (customer_id) params.set("customer_id", customer_id);
    const qs = params.toString();
    return apiFetch(`/v1/invoices${qs ? "?" + qs : ""}`);
  },

  async fetchInvoice(invoiceId) {
    return apiFetch(`/v1/invoices/${invoiceId}`);
  },

  async downloadInvoicePdf(invoiceId) {
    const token = this.getToken();
    if (!token) throw new Error("認証が必要です");
    return fetch(`${this.baseUrl}/v1/invoices/${invoiceId}/pdf`, {
      method: "GET",
      headers: { "Authorization": `Bearer ${token}` }
    }).then(async res => {
      if (!res.ok) throw new Error(await res.text());
      return res.blob();
    }).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Invoice_${invoiceId.slice(0, 6)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  },

  async sendInvoiceEmail(invoiceId, body = { subject: "【ご請求書】送付のご案内", body: "いつも大変お世話になっております。\\n添付の通り、ご請求書を送付いたします。\\nご確認のほどよろしくお願い申し上げます。" }) {
    return apiFetch(`/v1/invoices/${invoiceId}/send`, {
      method: "POST",
      body: JSON.stringify(body)
    });
  },

  async createInvoice(body) {
    return apiFetch("/v1/invoices", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateInvoice(invoiceId, body) {
    return apiFetch(`/v1/invoices/${invoiceId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async updateInvoiceFull(invoiceId, body) {
    return apiFetch(`/v1/invoices/${invoiceId}/full`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async generateMonthlyInvoices(month, dueDate = null) {
    return apiFetch("/v1/invoices/generate-monthly", {
      method: "POST",
      body: JSON.stringify({ month, due_date: dueDate }),
    });
  },

  async generateSubscriptionsCustom(body) {
    return apiFetch("/v1/invoices/generate-subscriptions-custom", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async createOcrInvoice(formData) {
    return apiFetch("/v1/invoices/ocr-create", {
      method: "POST",
      body: formData,
    });
  },

  async fetchUnpaidAlerts() {
    return apiFetch("/v1/invoices/unpaid-alerts");
  },

  // ── Payments (入金・消し込み) ────────────────────────────────

  async fetchPayments() {
    return apiFetch("/v1/payments");
  },

  async registerPayment(body) {
    return apiFetch("/v1/payments", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async deletePayment(paymentId) {
    return apiFetch(`/v1/payments/${paymentId}`, { method: "DELETE" });
  },

  // ── Pipeline (営業パイプライン) ──────────────────────────────

  async fetchPipeline() {
    return apiFetch("/v1/jobs/pipeline");
  },

  async updateJobStage(jobId, pipelineStage) {
    return apiFetch(`/v1/jobs/${jobId}`, {
      method: "PUT",
      body: JSON.stringify({ pipeline_stage: pipelineStage }),
    });
  },

  // ── Daily Reports (ドライバー日報・集計) ───────────────────

  async fetchDailyReports(month = "") {
    let url = "/v1/daily_reports";
    if (month) url += `?month=${month}`;
    return apiFetch(url);
  },

  async createDailyReport(body) {
    return apiFetch("/v1/daily_reports", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async deleteDailyReport(reportId) {
    return apiFetch(`/v1/daily_reports/${reportId}`, { method: "DELETE" });
  },

  // ── Customers (顧客管理) ────────────────────────────────────

  async fetchCustomers(search = null) {
    let url = "/v1/customers?limit=2000";
    if (search) url += `&search=${encodeURIComponent(search)}`;
    const res = await apiFetch(url);
    // 後方互換: 配列 or {items} どちらでも対応
    return Array.isArray(res) ? res : (res.items || []);
  },

  async createCustomer(body) {
    return apiFetch("/v1/customers", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateCustomer(customerId, body) {
    return apiFetch(`/v1/customers/${customerId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async deleteCustomer(customerId) {
    return apiFetch(`/v1/customers/${customerId}`, { method: "DELETE" });
  },

  async fetchCustomerHistory(customerId) {
    return apiFetch(`/v1/customers/${customerId}/history`);
  },

  async addCustomerHistory(customerId, text, eventType) {
    return apiFetch(`/v1/customers/${customerId}/history`, {
      method: "POST",
      body: JSON.stringify({ event_type: eventType, description: text }),
    });
  },

  // ── Manifests (マニフェスト) ─────────────────────────────────

  async fetchManifests({ waste_category = null, status = null } = {}) {
    const params = new URLSearchParams();
    if (waste_category) params.set("waste_category", waste_category);
    if (status) params.set("status", status);
    const qs = params.toString();
    return apiFetch(`/v1/manifests${qs ? "?" + qs : ""}`);
  },

  async createManifest(body) {
    return apiFetch("/v1/manifests", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  async updateManifest(manifestId, body) {
    return apiFetch(`/v1/manifests/${manifestId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  async fetchManifestsOverdue() {
    return apiFetch("/v1/manifests/overdue");
  },

  // ── Estimate → Invoice (見積→請求変換) ───────────────────────

  async createInvoiceFromEstimate(jobId) {
    return apiFetch(`/v1/invoices/from-estimate/${jobId}`, {
      method: "POST",
    });
  },

  async createInvoiceAndCollectCash(jobId) {
    return apiFetch(`/v1/invoices/cash-collection/${jobId}`, {
      method: "POST",
    });
  },

  // ── Job Comments (コメント) ──────────────────────────────────

  async fetchComments(jobId) {
    return apiFetch(`/v1/jobs/${jobId}/comments`);
  },

  async postComment(jobId, content) {
    return apiFetch(`/v1/jobs/${jobId}/comments`, {
      method: "POST",
      body: JSON.stringify({ content }),
    });
  },

  // ── Bank (銀行入金取込) ─────────────────────────────────────

  async uploadBankCSV(file) {
    const formData = new FormData();
    formData.append("file", file);
    const token = localStorage.getItem("token");
    const resp = await fetch(`${BASE}/v1/bank/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  },

  async bankAutoMatch() {
    return apiFetch("/v1/bank/auto-match", { method: "POST" });
  },

  async fetchUnmatchedTransactions() {
    return apiFetch("/v1/bank/unmatched");
  },

  async fetchBankTransactions() {
    return apiFetch("/v1/bank/transactions");
  },

  // ── freee連携 ───────────────────────────────────────────────

  async freeeAuthUrl() {
    return apiFetch("/v1/freee/auth-url");
  },

  async freeeCallback(code) {
    return apiFetch(`/v1/freee/callback?code=${code}`, { method: "POST" });
  },

  async freeeStatus() {
    return apiFetch("/v1/freee/status");
  },

  async freeSyncInvoice(invoiceId) {
    return apiFetch(`/v1/freee/sync-invoice/${invoiceId}`, { method: "POST" });
  },
  // ── Settings (会社設定・メール) ──────────────────────────────
  async fetchSettings() {
    return apiFetch("/v1/settings");
  },
  async updateSettings(body) {
    return apiFetch("/v1/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },

  // ── Item Templates (品目雛形) ────────────────────────────
  async fetchTemplates() {
    return apiFetch("/v1/templates");
  },
  async createTemplate(body) {
    return apiFetch("/v1/templates", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  async updateTemplate(id, body) {
    return apiFetch(`/v1/templates/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  async deleteTemplate(id) {
    return apiFetch(`/v1/templates/${id}`, {
      method: "DELETE",
    });
  },

  // ── Automated Reminders (未入金メール) ─────────────────
  async sendUnpaidReminders() {
    return apiFetch("/v1/invoices/send-reminders", { method: "POST" });
  },

  // ── Vehicles (車両管理) ──────────────────────────────────
  async fetchVehicles() {
    return apiFetch("/v1/vehicles");
  },
  async createVehicle(body) {
    return apiFetch("/v1/vehicles", { method: "POST", body: JSON.stringify(body) });
  },
  async updateVehicle(id, body) {
    return apiFetch(`/v1/vehicles/${id}`, { method: "PUT", body: JSON.stringify(body) });
  },
  async deleteVehicle(id) {
    return apiFetch(`/v1/vehicles/${id}`, { method: "DELETE" });
  },

  // ── Permits (許可証管理) ─────────────────────────────────
  async fetchPermits() {
    return apiFetch("/v1/permits");
  },
  async createPermit(body) {
    return apiFetch("/v1/permits", { method: "POST", body: JSON.stringify(body) });
  },
  async updatePermit(id, body) {
    return apiFetch(`/v1/permits/${id}`, { method: "PUT", body: JSON.stringify(body) });
  },
  async deletePermit(id) {
    return apiFetch(`/v1/permits/${id}`, { method: "DELETE" });
  },

  // ── Waste Contracts (産廃3社契約) ────────────────────────
  async fetchWasteContracts() {
    return apiFetch("/v1/waste-contracts");
  },
  async createWasteContract(body) {
    return apiFetch("/v1/waste-contracts", { method: "POST", body: JSON.stringify(body) });
  },
  async updateWasteContract(id, body) {
    return apiFetch(`/v1/waste-contracts/${id}`, { method: "PUT", body: JSON.stringify(body) });
  },
  async deleteWasteContract(id) {
    return apiFetch(`/v1/waste-contracts/${id}`, { method: "DELETE" });
  },

  // ── Company Data Alerts (更新期限アラート) ───────────────
  async fetchCompanyDataAlerts() {
    return apiFetch("/v1/company-data/alerts");
  },

  // ── Vehicle Records (車両履歴: 修理/事故/車検) ──────────
  async fetchVehicleRecords(vehicleId) {
    return apiFetch(`/v1/vehicles/${vehicleId}/records`);
  },
  async createVehicleRecord(vehicleId, formData) {
    const token = localStorage.getItem("ryubee_token");
    const res = await fetch(`${API_BASE}/v1/vehicles/${vehicleId}/records`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,  // FormData (not JSON)
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async deleteVehicleRecord(vehicleId, recordId) {
    return apiFetch(`/v1/vehicles/${vehicleId}/records/${recordId}`, { method: "DELETE" });
  },

  // ── Training Materials (研修資料) ────────────────────────
  async fetchTrainingMaterials() {
    return apiFetch("/v1/training-materials");
  },
  async createTrainingMaterial(formData) {
    const token = localStorage.getItem("ryubee_token");
    const res = await fetch(`${API_BASE}/v1/training-materials`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
  async deleteTrainingMaterial(id) {
    return apiFetch(`/v1/training-materials/${id}`, { method: "DELETE" });
  },

  // ── 繰越処理 ──────────────────────────────────────────
  async carryoverInvoices(sourceMonth, targetMonth) {
    return apiFetch("/v1/invoices/carryover", {
      method: "POST",
      body: JSON.stringify({ source_month: sourceMonth, target_month: targetMonth }),
    });
  },

  // ── 口座振替 ──────────────────────────────────────────
  async previewAutoDebit(month) {
    return apiFetch(`/v1/auto-debit/preview?month=${month}`);
  },
  async generateAutoDebitCsv(invoiceIds, debitDate, opts = {}) {
    const token = localStorage.getItem("ryubee_token");
    const res = await fetch(`${API_BASE}/v1/auto-debit/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify({ invoice_ids: invoiceIds, debit_date: debitDate, ...opts }),
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText);
    }
    // CSVレスポンスの場合はBlobとしてダウンロード
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("text/csv")) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `auto_debit_${debitDate}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      return { generated: parseInt(res.headers.get("x-generated-count") || "0"), skipped: parseInt(res.headers.get("x-skipped-count") || "0") };
    }
    return res.json();
  },
  async importAutoDebitResult(file) {
    const token = localStorage.getItem("ryubee_token");
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/v1/auto-debit/import-result`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }
};

// グローバルに公開
window.RyubeeAPI = RyubeeAPI;

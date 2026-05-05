/**
 * Atlantic Highlands API Client
 */

// In browser: use relative URLs so Next.js rewrites proxy to backend (avoids mixed content)
// Server-side: use full URL
const API_BASE = typeof window !== "undefined" ? "" : (process.env.NEXT_PUBLIC_API_URL || "");

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ah_token");
}

/** Public helper: returns Authorization header dict for direct fetch() calls. */
export function getAuthToken(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ─── Auth ─────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  must_change_password?: boolean;
}

export async function changePassword(newPassword: string) {
  return request<{ detail: string }>("/api/auth/change-password", {
    method: "POST", body: JSON.stringify({ new_password: newPassword }),
  });
}

export async function login(email: string, password: string) {
  const data = await request<{ access_token: string; pending_approval?: boolean }>("/api/auth/login", {
    method: "POST", body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("ah_token", data.access_token);
  return data;
}

export async function getMe(): Promise<User> { return request<User>("/api/auth/me"); }
export function logout() { localStorage.removeItem("ah_token"); }

// ─── Projects ─────────────────────────────────────────────────────────

export interface Project {
  id: string; name: string; description: string | null;
  entity_type: string | null; document_count: number; created_at: string;
}

export async function getProjects(): Promise<Project[]> { return request<Project[]>("/api/projects/"); }
export async function createProject(name: string, description?: string, entity_type?: string): Promise<Project> {
  return request<Project>("/api/projects/", { method: "POST", body: JSON.stringify({ name, description, entity_type }) });
}
export async function deleteProject(projectId: string) { return request(`/api/projects/${projectId}`, { method: "DELETE" }); }

// ─── Documents ────────────────────────────────────────────────────────

export interface Document {
  id: string; project_id: string; filename: string; original_filename: string;
  s3_key: string; file_size: number; content_type: string | null;
  doc_type: string | null; category: string | null; department: string | null;
  fiscal_year: string | null; status: string; notes: string | null; created_at: string;
}

export async function getDocuments(params?: { project_id?: string; category?: string; doc_type?: string }): Promise<Document[]> {
  // Fetch all pages — paginated to fit Amplify Lambda response limits
  const PAGE_SIZE = 200;
  const baseQuery = new URLSearchParams();
  if (params?.project_id) baseQuery.set("project_id", params.project_id);
  if (params?.category) baseQuery.set("category", params.category);
  if (params?.doc_type) baseQuery.set("doc_type", params.doc_type);

  // Get total count first
  const countRes = await request<{ count: number }>(
    `/api/documents/count${baseQuery.toString() ? `?${baseQuery}` : ""}`
  );
  const total = countRes.count;

  // Fetch all pages in parallel
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const pagePromises: Promise<Document[]>[] = [];
  for (let i = 0; i < pageCount; i++) {
    const q = new URLSearchParams(baseQuery);
    q.set("limit", String(PAGE_SIZE));
    q.set("offset", String(i * PAGE_SIZE));
    pagePromises.push(request<Document[]>(`/api/documents/?${q}`));
  }
  const pages = await Promise.all(pagePromises);
  return pages.flat();
}

/**
 * Upload a single file directly to S3 via presigned URL (bypasses Amplify proxy size limits).
 */
export async function uploadDocument(
  file: File,
  projectId: string,
  metadata?: { doc_type?: string; category?: string; fiscal_year?: string }
): Promise<Document> {
  // 1. Get presigned URL from backend
  const presigned = await request<{ upload_url: string; s3_key: string; document_id: string }>(
    "/api/documents/presigned-upload",
    {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        project_id: projectId,
        file_size: file.size,
        doc_type: metadata?.doc_type,
        category: metadata?.category,
        fiscal_year: metadata?.fiscal_year,
      }),
    }
  );

  // 2. Upload directly to S3 (no proxy involved)
  const uploadRes = await fetch(presigned.upload_url, {
    method: "PUT",
    body: file,
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
  });
  if (!uploadRes.ok) {
    throw new Error(`S3 upload failed: ${uploadRes.status} ${uploadRes.statusText}`);
  }

  // 3. Confirm upload — backend records the doc in DB
  return request<Document>("/api/documents/confirm-upload", {
    method: "POST",
    body: JSON.stringify({
      document_id: presigned.document_id,
      s3_key: presigned.s3_key,
      filename: file.name,
      file_size: file.size,
      content_type: file.type || "application/octet-stream",
      project_id: projectId,
      doc_type: metadata?.doc_type,
      category: metadata?.category,
      fiscal_year: metadata?.fiscal_year,
    }),
  });
}

/**
 * Upload multiple files via presigned URLs.
 * Throws if any file fails — caller can inspect `error.results` for per-file status.
 */
export async function uploadMultipleDocuments(
  files: File[],
  projectId: string,
  category?: string
): Promise<{ uploaded: number; files: { filename: string; status: string }[] }> {
  const results = await Promise.allSettled(
    files.map((f) => uploadDocument(f, projectId, { category }))
  );
  const fileResults = results.map((r, i) => ({
    filename: files[i].name,
    status: r.status === "fulfilled" ? "uploaded" : `error: ${(r.reason as Error).message}`,
  }));
  const uploaded = results.filter((r) => r.status === "fulfilled").length;
  const failed = files.length - uploaded;

  if (failed > 0) {
    const failedNames = fileResults.filter((f) => f.status.startsWith("error")).map((f) => `${f.filename}: ${f.status}`).join("; ");
    const err = new Error(`${failed} of ${files.length} uploads failed. ${failedNames}`);
    (err as any).results = fileResults;
    (err as any).uploaded = uploaded;
    throw err;
  }
  return { uploaded, files: fileResults };
}

export async function getDocument(documentId: string): Promise<Document> {
  return request<Document>(`/api/documents/${documentId}`);
}

export async function getDocumentViewUrl(documentId: string): Promise<{ url: string }> {
  const result = await request<{ url: string }>(`/api/documents/${documentId}/view-url`);
  // If URL is relative (local storage), prepend the API base
  if (result.url && result.url.startsWith("/")) {
    result.url = `${API_BASE}${result.url}`;
  }
  return result;
}

export async function updateDocument(documentId: string, update: Partial<Document>) {
  return request<Document>(`/api/documents/${documentId}`, { method: "PATCH", body: JSON.stringify(update) });
}

export async function deleteDocument(documentId: string) {
  return request(`/api/documents/${documentId}`, { method: "DELETE" });
}

// ─── Financial Analysis ───────────────────────────────────────────────

export interface FinancialStatement {
  id: string; document_id: string; entity_name: string; entity_type: string;
  statement_type: string; fiscal_year: string;
  total_revenue: number | null; total_expenditures: number | null;
  surplus_deficit: number | null; fund_balance: number | null;
  total_debt: number | null; status: string; created_at: string;
}

export interface LineItem {
  id: string; section: string | null; subsection: string | null;
  line_name: string; amount: number | null; prior_year_amount: number | null;
  budget_amount: number | null; variance: number | null;
}

export interface FinancialAnalysisResult {
  id: string; name: string; entity_type: string; analysis_type: string;
  fiscal_years: string[]; results: Record<string, any>;
  summary: string | null; created_at: string;
}

export async function getStatements(params?: { entity_type?: string; fiscal_year?: string }): Promise<FinancialStatement[]> {
  const query = new URLSearchParams();
  if (params?.entity_type) query.set("entity_type", params.entity_type);
  if (params?.fiscal_year) query.set("fiscal_year", params.fiscal_year);
  const qs = query.toString();
  return request<FinancialStatement[]>(`/api/financial/statements${qs ? `?${qs}` : ""}`);
}

export async function getStatement(statementId: string): Promise<FinancialStatement> {
  return request<FinancialStatement>(`/api/financial/statements/${statementId}`);
}

export async function getStatementLineItems(statementId: string): Promise<LineItem[]> {
  return request<LineItem[]>(`/api/financial/statements/${statementId}/line-items`);
}

export async function getStatementRawExtraction(statementId: string): Promise<Record<string, any>> {
  return request<Record<string, any>>(`/api/financial/statements/${statementId}/raw`);
}

// ─── Drill-down + anomalies (Phase 2) ─────────────────────────────────

export interface AnomalyFlag {
  code: string;
  severity: "info" | "warn" | "high";
  message: string;
  line_id?: string;
  value?: number;
}

export interface DrillResults {
  revenue?: any;
  expenditure?: any;
  debt?: any;
  fund_balance?: any;
  synthesis?: any;
}

export interface DrillResponse {
  statement_id: string;
  status: string;
  accounting_basis: string | null;
  fiscal_calendar: string | null;
  reconcile_status: string | null;
  reconcile_details: Record<string, any>;
  anomaly_flags: AnomalyFlag[];
  drill_results: DrillResults;
}

export async function runDrill(statementId: string, sync = false) {
  const qs = sync ? "?sync=true" : "";
  return request<{
    statement_id: string;
    mode: "background" | "sync";
    status?: string;
    synthesis_ok?: boolean;
    success_count?: number;
    error_count?: number;
    duration_s?: number;
    drill_results?: any;
  }>(`/api/financial/statements/${statementId}/drill${qs}`, { method: "POST" });
}

export async function drillAll(params?: { entity_type?: string; fiscal_year?: string; redrill?: boolean; concurrency?: number }) {
  const qs = new URLSearchParams();
  if (params?.entity_type) qs.set("entity_type", params.entity_type);
  if (params?.fiscal_year) qs.set("fiscal_year", params.fiscal_year);
  if (params?.redrill) qs.set("redrill", "true");
  if (params?.concurrency != null) qs.set("concurrency", String(params.concurrency));
  return request<{ queued: number; concurrency: number; statement_ids: string[] }>(
    `/api/financial/drill-all${qs.toString() ? `?${qs}` : ""}`,
    { method: "POST" },
  );
}

export async function getFinancialDiagnostics() {
  return request<{
    llm_keys: { anthropic_api_key_set: boolean; gemini_api_key_set: boolean };
    statements: { by_status: Record<string, number>; by_accounting_basis: Record<string, number>; by_entity_type: Record<string, number>; total: number };
    extraction_issues: { extracted_with_no_line_items: any[]; extracted_with_no_line_items_count: number };
    drill_issues: { drills_with_errors_count: number; drills_with_errors_sample: any[] };
    next_steps_hint: string;
  }>("/api/financial/diagnostics");
}

export async function getDrillResults(statementId: string): Promise<DrillResponse> {
  return request<DrillResponse>(`/api/financial/statements/${statementId}/drill`);
}

export async function getStatementAnomalies(statementId: string): Promise<{ statement_id: string; anomaly_flags: AnomalyFlag[] }> {
  return request(`/api/financial/statements/${statementId}/anomalies`);
}

// ─── Contracts + Vendors (Phase 3) ────────────────────────────────────

export interface VendorSummary {
  id: string; name: string; category: string | null;
  contract_count: number; payment_total: number; created_at: string;
}

export interface ContractRow {
  id: string; vendor_id: string; vendor_name: string;
  entity_type: string; title: string; amount: number | null;
  fiscal_year: string | null; contract_type: string | null;
  awarded_date: string | null;
  authorizing_resolution: string | null;
  status: string;
}

export async function listVendors(params?: { q?: string; category?: string }): Promise<VendorSummary[]> {
  const qs = new URLSearchParams();
  if (params?.q) qs.set("q", params.q);
  if (params?.category) qs.set("category", params.category);
  return request<VendorSummary[]>(`/api/contracts/vendors${qs.toString() ? `?${qs}` : ""}`);
}

export async function listContracts(params?: { entity_type?: string; fiscal_year?: string; vendor?: string; min_amount?: number }): Promise<ContractRow[]> {
  const qs = new URLSearchParams();
  if (params?.entity_type) qs.set("entity_type", params.entity_type);
  if (params?.fiscal_year) qs.set("fiscal_year", params.fiscal_year);
  if (params?.vendor) qs.set("vendor", params.vendor);
  if (params?.min_amount != null) qs.set("min_amount", String(params.min_amount));
  return request<ContractRow[]>(`/api/contracts/contracts${qs.toString() ? `?${qs}` : ""}`);
}

export async function extractFinancialData(documentId: string, entityType: string, statementType: string) {
  return request<{ statement_id: string; status: string }>("/api/financial/extract", {
    method: "POST", body: JSON.stringify({ document_id: documentId, entity_type: entityType, statement_type: statementType }),
  });
}

export async function createAnalysis(name: string, entityType: string, analysisType: string, statementIds: string[]): Promise<FinancialAnalysisResult> {
  return request<FinancialAnalysisResult>("/api/financial/analyze", {
    method: "POST", body: JSON.stringify({ name, entity_type: entityType, analysis_type: analysisType, statement_ids: statementIds }),
  });
}

export async function getAnalyses(entityType?: string): Promise<FinancialAnalysisResult[]> {
  const qs = entityType ? `?entity_type=${entityType}` : "";
  return request<FinancialAnalysisResult[]>(`/api/financial/analyses${qs}`);
}

// ─── Processing ───────────────────────────────────────────────────────

export interface ProcessingStats {
  total: number; processed: number; processing: number; uploaded: number; errors: number;
}

export async function processDocuments(params?: { document_ids?: string[]; project_id?: string }) {
  return request<{ detail: string; count: number }>("/api/processing/run", { method: "POST", body: JSON.stringify(params || {}) });
}

export async function processSingleDocument(documentId: string) {
  return request<{ detail: string }>(`/api/processing/single/${documentId}`, { method: "POST" });
}

export async function getProcessingStats(projectId?: string): Promise<ProcessingStats> {
  const qs = projectId ? `?project_id=${projectId}` : "";
  return request<ProcessingStats>(`/api/processing/stats${qs}`);
}

// ─── Search ───────────────────────────────────────────────────────────

export interface SearchResult {
  id: string; filename: string; doc_type: string | null; category: string | null;
  fiscal_year: string | null; department: string | null;
  status: string; score: number; snippet: string | null;
  /** "phrase" = matched a quoted phrase, "fts" = ranked match, "filename" = ILIKE fallback. */
  match_type: "phrase" | "fts" | "filename";
}

export async function searchDocuments(
  query: string,
  params?: { project_id?: string; category?: string; doc_type?: string; fiscal_year?: string; department?: string },
): Promise<SearchResult[]> {
  return request<SearchResult[]>("/api/search/", {
    method: "POST", body: JSON.stringify({ query, ...params }),
  });
}

export interface SearchFacets {
  doc_types: Record<string, number>;
  categories: Record<string, number>;
  fiscal_years: Record<string, number>;  // already deduped + 4-digit-sanitized server-side
  departments: Record<string, number>;   // already case-insensitive deduped server-side
}

export async function getSearchFacets(projectId?: string): Promise<SearchFacets> {
  const qs = projectId ? `?project_id=${projectId}` : "";
  return request<SearchFacets>(`/api/search/facets${qs}`);
}

// ─── Scraper ──────────────────────────────────────────────────────────

export interface SiteStats {
  status: "pending" | "running" | "done" | "error";
  documents_found: number;
  documents_uploaded: number;
  documents_skipped: number;
  errors: number;
  started_at: string | null;
  completed_at: string | null;
}

export interface ScraperStatus {
  running: boolean; current_site: string | null;
  documents_found: number; documents_uploaded: number; documents_skipped: number;
  errors: string[]; started_at: string | null; completed_at: string | null;
  per_site?: Record<string, SiteStats>;
  sites_planned?: string[];
  sites_completed?: string[];
}

export async function startScraper(sites?: string[], projectId?: string, dryRun?: boolean) {
  return request<{ detail: string; status?: ScraperStatus }>("/api/scraper/run", { method: "POST", body: JSON.stringify({ sites, project_id: projectId, dry_run: dryRun }) });
}

export async function getScraperStatus(): Promise<ScraperStatus> {
  return request<ScraperStatus>("/api/scraper/status");
}

// ─── Web Search ───────────────────────────────────────────────────────

export interface WebSearchResult {
  title: string;
  url: string;
  snippet: string;
}

export async function webSearch(query: string, maxResults: number = 5) {
  return request<{ results: WebSearchResult[]; query: string }>("/api/websearch/", {
    method: "POST",
    body: JSON.stringify({ query, max_results: maxResults }),
  });
}

// ─── Chat History ─────────────────────────────────────────────────────

export async function getChatHistory(sessionId: string) {
  return request<{ session_id: string; messages: { role: string; content: string; timestamp: string }[] }>(
    `/api/chat/history?session_id=${sessionId}`
  );
}

export async function getChatSessions() {
  return request<{ session_id: string; scope_type: string; message_count: number; last_activity: string; last_query: string }[]>(
    "/api/chat/sessions"
  );
}

// ─── Reports ──────────────────────────────────────────────────────────

export async function generateReport(reportType: string, entityType?: string, customPrompt?: string) {
  return fetch(`${API_BASE}/api/reports/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_type: reportType, entity_type: entityType, custom_prompt: customPrompt }),
  });
}

// ─── Calendar Events ──────────────────────────────────────────────────

export interface CalendarEvent {
  id: string; date: string; title: string; time: string | null;
  location: string | null; description: string | null; source: string;
}

export async function getCalendarEvents(year?: number, month?: number): Promise<CalendarEvent[]> {
  const params = new URLSearchParams();
  if (year) params.set("year", String(year));
  if (month) params.set("month", String(month));
  const qs = params.toString();
  return request<CalendarEvent[]>(`/api/calendar/events${qs ? `?${qs}` : ""}`);
}

// ─── Admin ────────────────────────────────────────────────────────────

export interface AdminStats {
  total_users: number; total_projects: number; total_documents: number; total_statements: number;
  pending_users: number;
}

export interface Invite {
  id: string; token: string; email: string | null; is_used: boolean;
  used_by: string | null; expires_at: string; created_at: string;
}

export interface AdminUser extends User {
  created_at: string;
}

export async function getAdminStats(): Promise<AdminStats> { return request<AdminStats>("/api/admin/stats"); }
export async function getAdminUsers() { return request<AdminUser[]>("/api/admin/users"); }
export async function approveUser(userId: string) { return request(`/api/admin/users/${userId}/approve`, { method: "PATCH" }); }
export async function toggleUserActive(userId: string) { return request(`/api/admin/users/${userId}/toggle-active`, { method: "PATCH" }); }
export async function toggleUserAdmin(userId: string) { return request(`/api/admin/users/${userId}/toggle-admin`, { method: "PATCH" }); }
export async function deleteUser(userId: string) { return request(`/api/admin/users/${userId}`, { method: "DELETE" }); }
export async function createInvite(email?: string, expiresHours: number = 72) {
  return request<{ token: string; invite_url: string; email: string | null; expires_at: string }>("/api/admin/invites", {
    method: "POST", body: JSON.stringify({ email: email || null, expires_hours: expiresHours }),
  });
}
export async function getInvites() { return request<Invite[]>("/api/admin/invites"); }
export async function deleteInvite(inviteId: string) { return request(`/api/admin/invites/${inviteId}`, { method: "DELETE" }); }

/**
 * Atlantic Highlands API Client
 * Centralized API service for all backend interactions.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ah_token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData (browser sets it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

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
}

export async function login(email: string, password: string) {
  const data = await request<{ access_token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("ah_token", data.access_token);
  return data;
}

export async function register(email: string, username: string, password: string, full_name?: string) {
  const data = await request<{ access_token: string }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, username, password, full_name }),
  });
  localStorage.setItem("ah_token", data.access_token);
  return data;
}

export async function getMe(): Promise<User> {
  return request<User>("/api/auth/me");
}

export function logout() {
  localStorage.removeItem("ah_token");
}

// ─── Projects ─────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  description: string | null;
  entity_type: string | null;
  document_count: number;
  created_at: string;
}

export async function getProjects(): Promise<Project[]> {
  return request<Project[]>("/api/projects/");
}

export async function createProject(name: string, description?: string, entity_type?: string): Promise<Project> {
  return request<Project>("/api/projects/", {
    method: "POST",
    body: JSON.stringify({ name, description, entity_type }),
  });
}

export async function deleteProject(projectId: string) {
  return request(`/api/projects/${projectId}`, { method: "DELETE" });
}

// ─── Documents ────────────────────────────────────────────────────────

export interface Document {
  id: string;
  project_id: string;
  filename: string;
  original_filename: string;
  s3_key: string;
  file_size: number;
  content_type: string | null;
  doc_type: string | null;
  category: string | null;
  department: string | null;
  fiscal_year: string | null;
  status: string;
  notes: string | null;
  created_at: string;
}

export async function getDocuments(params?: {
  project_id?: string;
  category?: string;
  doc_type?: string;
}): Promise<Document[]> {
  const query = new URLSearchParams();
  if (params?.project_id) query.set("project_id", params.project_id);
  if (params?.category) query.set("category", params.category);
  if (params?.doc_type) query.set("doc_type", params.doc_type);
  const qs = query.toString();
  return request<Document[]>(`/api/documents/${qs ? `?${qs}` : ""}`);
}

export async function uploadDocument(
  file: File,
  projectId: string,
  metadata?: { doc_type?: string; category?: string; fiscal_year?: string }
): Promise<Document> {
  const form = new FormData();
  form.append("file", file);
  form.append("project_id", projectId);
  if (metadata?.doc_type) form.append("doc_type", metadata.doc_type);
  if (metadata?.category) form.append("category", metadata.category);
  if (metadata?.fiscal_year) form.append("fiscal_year", metadata.fiscal_year);

  return request<Document>("/api/documents/upload", { method: "POST", body: form });
}

export async function uploadMultipleDocuments(
  files: File[],
  projectId: string,
  category?: string
) {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  form.append("project_id", projectId);
  if (category) form.append("category", category);

  return request<{ uploaded: number; files: { filename: string; status: string }[] }>(
    "/api/documents/upload-multiple",
    { method: "POST", body: form }
  );
}

export async function getDocumentViewUrl(documentId: string): Promise<{ url: string }> {
  return request<{ url: string }>(`/api/documents/${documentId}/view-url`);
}

export async function updateDocument(documentId: string, update: Partial<Document>) {
  return request<Document>(`/api/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify(update),
  });
}

export async function deleteDocument(documentId: string) {
  return request(`/api/documents/${documentId}`, { method: "DELETE" });
}

// ─── Financial Analysis ───────────────────────────────────────────────

export interface FinancialStatement {
  id: string;
  document_id: string;
  entity_name: string;
  entity_type: string;
  statement_type: string;
  fiscal_year: string;
  total_revenue: number | null;
  total_expenditures: number | null;
  surplus_deficit: number | null;
  fund_balance: number | null;
  total_debt: number | null;
  status: string;
  created_at: string;
}

export interface LineItem {
  id: string;
  section: string | null;
  subsection: string | null;
  line_name: string;
  amount: number | null;
  prior_year_amount: number | null;
  budget_amount: number | null;
  variance: number | null;
}

export interface FinancialAnalysisResult {
  id: string;
  name: string;
  entity_type: string;
  analysis_type: string;
  fiscal_years: string[];
  results: Record<string, unknown>;
  summary: string | null;
  created_at: string;
}

export async function getStatements(params?: {
  entity_type?: string;
  fiscal_year?: string;
}): Promise<FinancialStatement[]> {
  const query = new URLSearchParams();
  if (params?.entity_type) query.set("entity_type", params.entity_type);
  if (params?.fiscal_year) query.set("fiscal_year", params.fiscal_year);
  const qs = query.toString();
  return request<FinancialStatement[]>(`/api/financial/statements${qs ? `?${qs}` : ""}`);
}

export async function getStatementLineItems(statementId: string): Promise<LineItem[]> {
  return request<LineItem[]>(`/api/financial/statements/${statementId}/line-items`);
}

export async function extractFinancialData(
  documentId: string,
  entityType: string,
  statementType: string
) {
  return request<{ statement_id: string; status: string }>("/api/financial/extract", {
    method: "POST",
    body: JSON.stringify({
      document_id: documentId,
      entity_type: entityType,
      statement_type: statementType,
    }),
  });
}

export async function createAnalysis(
  name: string,
  entityType: string,
  analysisType: string,
  statementIds: string[]
): Promise<FinancialAnalysisResult> {
  return request<FinancialAnalysisResult>("/api/financial/analyze", {
    method: "POST",
    body: JSON.stringify({
      name,
      entity_type: entityType,
      analysis_type: analysisType,
      statement_ids: statementIds,
    }),
  });
}

export async function getAnalyses(entityType?: string): Promise<FinancialAnalysisResult[]> {
  const qs = entityType ? `?entity_type=${entityType}` : "";
  return request<FinancialAnalysisResult[]>(`/api/financial/analyses${qs}`);
}

// ─── Admin ────────────────────────────────────────────────────────────

export interface AdminStats {
  total_users: number;
  total_projects: number;
  total_documents: number;
  total_statements: number;
}

export async function getAdminStats(): Promise<AdminStats> {
  return request<AdminStats>("/api/admin/stats");
}

export async function getAdminUsers() {
  return request<User[]>("/api/admin/users");
}

export async function toggleUserActive(userId: string) {
  return request(`/api/admin/users/${userId}/toggle-active`, { method: "PATCH" });
}

// ─── Scraper ──────────────────────────────────────────────────────────

export interface ScraperStatus {
  running: boolean;
  current_site: string | null;
  documents_found: number;
  documents_uploaded: number;
  documents_skipped: number;
  errors: string[];
  started_at: string | null;
  completed_at: string | null;
}

export async function startScraper(sites?: string[], projectId?: string, dryRun?: boolean) {
  return request<{ detail: string }>("/api/scraper/run", {
    method: "POST",
    body: JSON.stringify({ sites, project_id: projectId, dry_run: dryRun }),
  });
}

export async function getScraperStatus(): Promise<ScraperStatus> {
  return request<ScraperStatus>("/api/scraper/status");
}

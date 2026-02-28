/**
 * UROG Automation — Frontend API Client
 *
 * Thin wrapper around fetch() for every backend endpoint.
 * All methods return the parsed JSON body on success, or throw on failure.
 */

export class UrogAPI {
  /**
   * @param {string} baseUrl  Root URL of the FastAPI server.
   */
  constructor(baseUrl = "http://127.0.0.1:8000") {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
  }

  // ── Internals ────────────────────────────────────────────────

  async _request(method, path, { body, isFormData = false } = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = {};
    let fetchBody;

    if (isFormData) {
      fetchBody = body; // browser sets Content-Type + boundary
    } else if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      fetchBody = JSON.stringify(body);
    }

    const resp = await fetch(url, { method, headers, body: fetchBody });
    const json = await resp.json().catch(() => null);

    if (!resp.ok) {
      const detail = json?.detail || resp.statusText;
      throw new Error(`${resp.status}: ${detail}`);
    }
    return json;
  }

  // ── GET /health ──────────────────────────────────────────────

  checkHealth() {
    return this._request("GET", "/health");
  }

  // ── POST /api/webhook/ingest ─────────────────────────────────

  webhookIngest(sourceName, sourceType, data) {
    return this._request("POST", "/api/webhook/ingest", {
      body: { source_name: sourceName, source_type: sourceType, data },
    });
  }

  // ── POST /api/admin/upload-file ──────────────────────────────

  uploadFile(file, sourceName) {
    const fd = new FormData();
    fd.append("file", file);
    if (sourceName) fd.append("source_name", sourceName);
    return this._request("POST", "/api/admin/upload-file", {
      body: fd,
      isFormData: true,
    });
  }

  // ── POST /api/admin/trigger-worker ───────────────────────────

  triggerWorker() {
    return this._request("POST", "/api/admin/trigger-worker");
  }

  // ── POST /api/admin/generate-drafts ──────────────────────────

  generateDrafts(templateName, { role, limit, contextOverride } = {}) {
    const body = { template_name: templateName };
    if (role) body.role = role;
    if (limit) body.limit = limit;
    if (contextOverride) body.context_override = contextOverride;
    return this._request("POST", "/api/admin/generate-drafts", { body });
  }

  // ── POST /api/admin/dispatch ─────────────────────────────────

  dispatchDrafts(drafts) {
    return this._request("POST", "/api/admin/dispatch", {
      body: { drafts },
    });
  }

  // ── POST /api/admin/ingest-gsheets ───────────────────────────

  ingestGoogleSheet(spreadsheetId, sourceName) {
    const body = { spreadsheet_id: spreadsheetId };
    if (sourceName) body.source_name = sourceName;
    return this._request("POST", "/api/admin/ingest-gsheets", { body });
  }

  // ── POST /api/admin/create-opportunity ───────────────────────

  createOpportunity(title, professorEmail, { description, type, sheetHeaders } = {}) {
    const body = { title, professor_email: professorEmail };
    if (description) body.description = description;
    if (type) body.type = type;
    if (sheetHeaders) body.sheet_headers = sheetHeaders;
    return this._request("POST", "/api/admin/create-opportunity", { body });
  }
}

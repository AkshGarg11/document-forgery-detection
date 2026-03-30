/**
 * frontend/src/services/api.js
 * Centralized API client for the Document Forgery Detection backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";
const DOCTAMPER_ZERO_AREA_RATIO = 0.0005; // 0.05% => shows as 0.0% with one decimal

/**
 * Convert string to title case (capitalize first letter of each word)
 * @param {string} str
 * @returns {string}
 */
const toTitleCase = (str) => {
  return str
    .split(" ")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
};

/**
 * Extract user-friendly error message from API response
 * Handles blockchain revert reasons, API errors, and nested error objects
 * @param {Object} errorBody
 * @returns {string}
 */
const extractErrorMessage = (errorBody) => {
  if (!errorBody) return "Unknown error";
  if (typeof errorBody === "string") return errorBody;
  if (errorBody.data?.reason) return errorBody.data.reason;
  if (errorBody.reason) return errorBody.reason;
  if (errorBody.detail) return errorBody.detail;
  if (typeof errorBody.message === "string") {
    const msg = errorBody.message;
    if (msg.includes("revert ")) return msg.split("revert ")[1];
    return msg;
  }
  return "Unknown error";
};

const normalizeProbabilities = (probabilities) => {
  if (!probabilities || typeof probabilities !== "object") return {};
  const values = Object.values(probabilities)
    .map((v) => Number(v))
    .filter((v) => Number.isFinite(v));
  const looksPercentScale = values.length > 0 && Math.max(...values) > 1;

  return Object.fromEntries(
    Object.entries(probabilities).map(([k, v]) => {
      const n = Number(v);
      if (!Number.isFinite(n)) return [k, 0];
      const normalized = looksPercentScale ? n / 100 : n;
      return [k, Math.max(0, Math.min(1, normalized))];
    }),
  );
};

/**
 * Upload an image file for combined forgery detection.
 * Runs signature verification, copy-move, and DocTamper detection in parallel.
 * @param {File} file
 * @param {"save"|"find"} blockchainAction
 * @returns {Promise<{
 *  result: string,
 *  confidence: number,
 *  hash: string,
 *  final_verdict: string,
 *  risk_level: string,
 *  signature_detected: boolean,
 *  forgery_type: string,
 *  ...
 * }>}
 */
export async function analyzeDocument(file, blockchainAction = "save") {
  const formData = new FormData();
  formData.append("image", file);
  formData.append("blockchain_action", blockchainAction);

  const response = await fetch(`${BASE_URL}/combined-detection/predict`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    const cleanMsg = extractErrorMessage(errorBody);
    throw new Error(
      cleanMsg || `Request failed with status ${response.status}`,
    );
  }

  const payload = await response.json();

  let auditHistory = [];
  const fileHash = payload.hash || "";
  if (fileHash) {
    try {
      const historyResponse = await fetchAuditHistory(fileHash);
      auditHistory = historyResponse.history || [];
    } catch {
      auditHistory = [];
    }
  }

  // Normalize DocTamper output for UI consistency.
  const tamperedRatio = Number(payload.doctamper_tampered_pixels_ratio || 0);
  const hasVisibleTamperedArea = tamperedRatio > DOCTAMPER_ZERO_AREA_RATIO;
  const normalizedDoctamperForged =
    Boolean(payload.doctamper_is_forged) && hasVisibleTamperedArea;
  const normalizedDoctamperType =
    payload.doctamper_type === "skipped_no_text"
      ? "skipped_no_text"
      : hasVisibleTamperedArea
        ? payload.doctamper_type
        : "authentic";
  const doctamperSkipped = normalizedDoctamperType === "skipped_no_text";

  // Map combined detection results to frontend format
  const forgeryType = toTitleCase(payload.forgery_type.replace("_", " "));
  const riskLevelColor = {
    low: "#00DD00",
    medium: "#FF9900",
    high: "#FF0000",
  };
  const normalizedSignatureProbabilities = normalizeProbabilities(
    payload.signature_probabilities,
  );

  return {
    result: payload.final_verdict,
    confidence: Math.max(
      payload.signature_confidence,
      payload.forgery_confidence,
    ),
    hash: payload.hash || "N/A",
    cid: "N/A",
    tx_hash: payload.tx_hash ?? null,
    anchor_status: payload.anchor_status ?? null,
    anchor_error: payload.anchor_error ?? null,
    chain_exists: payload.chain_exists ?? null,
    chain_revoked: payload.chain_revoked ?? null,
    chain_timestamp: payload.chain_timestamp ?? null,
    chain_issuer: payload.chain_issuer ?? null,
    audit_history: auditHistory,
    // Combined verdict
    final_verdict: payload.final_verdict,
    risk_level: payload.risk_level,
    risk_color: riskLevelColor[payload.risk_level] || "#FF9900",
    // Signature verification results
    signature_detected: payload.signature_detected,
    signature_result: payload.signature_result,
    signature_confidence: payload.signature_confidence,
    signature_verdict: payload.signature_verdict,
    signature_probabilities: normalizedSignatureProbabilities,
    // Copy-move detection results
    forgery_type: payload.forgery_type,
    forgery_confidence: payload.forgery_confidence,
    is_forged: payload.is_forged,
    all_forgery_scores: payload.all_forgery_scores,
    // DocTamper localization results
    doctamper_type: normalizedDoctamperType,
    doctamper_confidence: payload.doctamper_confidence,
    doctamper_is_forged: normalizedDoctamperForged,
    doctamper_tampered_pixels_ratio: tamperedRatio,
    // Explanation and regions
    explanation: payload.reason,
    reasons: [
      `Signature Detected: ${payload.signature_detected ? "Yes" : "No"}`,
      payload.signature_detected
        ? `Signature Verdict: ${payload.signature_verdict} (${(payload.signature_confidence * 100).toFixed(1)}%)`
        : `Forgery Type: ${forgeryType} (${(payload.forgery_confidence * 100).toFixed(1)}%)`,
      `OCR Text Detection: ${payload.text_found ? "Text found" : "No text found"} (${payload.ocr_engine || "unknown"})`,
      doctamperSkipped
        ? "DocTamper: Skipped (no text detected by OCR)"
        : `DocTamper Verdict: ${normalizedDoctamperForged ? "Tampered" : "Authentic"} (${(payload.doctamper_confidence * 100).toFixed(1)}%)`,
      doctamperSkipped
        ? "DocTamper Area: N/A"
        : `DocTamper Area: ${(tamperedRatio * 100).toFixed(1)}% pixels`,
      `Overall Risk Level: ${payload.risk_level.toUpperCase()}`,
      `Inference Device: ${payload.device}`,
    ],
    forgery_regions:
      payload.signature_detected && payload.signature_box
        ? [
            {
              x: payload.signature_box.x,
              y: payload.signature_box.y,
              w: payload.signature_box.w,
              h: payload.signature_box.h,
              source: "layout.pt",
              score: payload.signature_confidence,
            },
          ]
        : [],
    annotated_preview_url: payload.signature_detected
      ? payload.signature_preview
      : payload.doctamper_preview || payload.forgery_preview,
    // Both detection previews for UI
    signature_preview_url: payload.signature_preview,
    forgery_preview_url: payload.forgery_preview,
    doctamper_preview_url: payload.doctamper_preview,
    // OCR and metadata
    text_found: Boolean(payload.text_found),
    extracted_text_preview: payload.extracted_text_preview || "",
    ocr_engine: payload.ocr_engine || "unknown",
    document_metadata: payload.document_metadata || {},
    page_previews: Array.isArray(payload.page_previews)
      ? payload.page_previews.filter(Boolean)
      : [],
    analyzed_pages: Number(payload.analyzed_pages || 1),
    selected_page_index: Number(payload.selected_page_index || 1),
  };
}

/**
 * Verify whether a file hash exists on-chain and is still valid.
 * @param {string} fileHash
 * @returns {Promise<{exists:boolean,is_valid:boolean,revoked:boolean,timestamp:number,issuer:string,text_hash:string}>}
 */
export async function verifyDocumentHash(fileHash) {
  const response = await fetch(`${BASE_URL}/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_hash: fileHash }),
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    const cleanMsg = extractErrorMessage(errorBody);
    throw new Error(
      cleanMsg || `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Revoke a previously issued file hash on-chain.
 * @param {string} fileHash
 * @returns {Promise<{revoked_file_hash:string,tx_hash:string}>}
 */
export async function revokeDocumentHash(fileHash) {
  const response = await fetch(`${BASE_URL}/revoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_hash: fileHash }),
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    const cleanMsg = extractErrorMessage(errorBody);
    throw new Error(
      cleanMsg || `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Fetch chronological blockchain events for a document hash.
 * @param {string} fileHash
 * @returns {Promise<{file_hash:string,history:Array<{event:string,file_hash:string,text_hash:string,issuer:string,timestamp:number,block_number:number,tx_hash:string}>}>}
 */
export async function fetchAuditHistory(fileHash) {
  const response = await fetch(`${BASE_URL}/audit-history`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_hash: fileHash }),
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    const cleanMsg = extractErrorMessage(errorBody);
    throw new Error(
      cleanMsg || `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

/**
 * Store an analyzed hash on-chain.
 * @param {string} fileHash
 * @returns {Promise<{issued_file_hash:string,tx_hash:string}>}
 */
export async function storeDocumentHash(fileHash) {
  const response = await fetch(`${BASE_URL}/issue-hash`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ file_hash: fileHash }),
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    const cleanMsg = extractErrorMessage(errorBody);
    throw new Error(
      cleanMsg || `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

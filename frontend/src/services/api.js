/**
 * frontend/src/services/api.js
 * Centralized API client for the Document Forgery Detection backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/**
 * Upload an image file for signature verification.
 * @param {File} file
 * @param {"save"|"find"} _unusedAction
 * @returns {Promise<{
 *  result: string,
 *  confidence: number,
 *  hash: string,
 *  cid: string,
 *  forensic_verdict?: string,
 *  forensic_confidence?: number,
 *  explanation?: string,
 *  reasons?: string[]
 * }>}
 */
export async function analyzeDocument(file, _unusedAction = "save") {
  const formData = new FormData();
  formData.append("image", file);
  formData.append("blockchain_action", _unusedAction);

  const response = await fetch(`${BASE_URL}/signature-verification/predict`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorBody = await response
      .json()
      .catch(() => ({ detail: "Unknown error" }));
    throw new Error(
      errorBody.detail || `Request failed with status ${response.status}`,
    );
  }

  const payload = await response.json();
  const isAuthentic = payload.result === "Authentic";
  const isNoSignature = payload.signature_detected === false;
  const confidence = payload.confidence;

  return {
    result: isNoSignature ? "Suspicious" : isAuthentic ? "Authentic" : "Forged",
    confidence,
    hash: payload.hash || "N/A",
    cid: "N/A",
    tx_hash: payload.tx_hash ?? null,
    anchor_status: payload.anchor_status ?? null,
    anchor_error: payload.anchor_error ?? null,
    chain_exists: payload.chain_exists ?? null,
    chain_revoked: payload.chain_revoked ?? null,
    chain_timestamp: payload.chain_timestamp ?? null,
    chain_issuer: payload.chain_issuer ?? null,
    forensic_verdict: payload.forensic_verdict,
    forensic_confidence: confidence,
    explanation: payload.reason,
    reasons: [
      `Authentic probability: ${payload.probabilities.authentic.toFixed(2)}%`,
      `Forged probability: ${payload.probabilities.forged.toFixed(2)}%`,
      `Inference device: ${payload.device}`,
      `Layout model: ${payload.weights.layout}`,
      `Signature model: ${payload.weights.signature}`,
    ],
    forgery_regions: isNoSignature
      ? []
      : [
          {
            x: payload.signature_box.x,
            y: payload.signature_box.y,
            w: payload.signature_box.w,
            h: payload.signature_box.h,
            source: "layout.pt",
            score: confidence,
          },
        ],
    annotated_preview_url: payload.annotated_preview,
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
    throw new Error(
      errorBody.detail || `Request failed with status ${response.status}`,
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
    throw new Error(
      errorBody.detail || `Request failed with status ${response.status}`,
    );
  }

  return response.json();
}

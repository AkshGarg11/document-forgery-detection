/**
 * frontend/src/services/api.js
 * Centralized API client for the Document Forgery Detection backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

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
    throw new Error(
      errorBody.detail || `Request failed with status ${response.status}`,
    );
  }

  const payload = await response.json();

  // Map combined detection results to frontend format
  const forgeryType = toTitleCase(payload.forgery_type.replace("_", " "));
  const riskLevelColor = {
    low: "#00DD00",
    medium: "#FF9900",
    high: "#FF0000",
  };

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
    // Combined verdict
    final_verdict: payload.final_verdict,
    risk_level: payload.risk_level,
    risk_color: riskLevelColor[payload.risk_level] || "#FF9900",
    // Signature verification results
    signature_detected: payload.signature_detected,
    signature_result: payload.signature_result,
    signature_confidence: payload.signature_confidence,
    signature_verdict: payload.signature_verdict,
    signature_probabilities: payload.signature_probabilities,
    // Copy-move detection results
    forgery_type: payload.forgery_type,
    forgery_confidence: payload.forgery_confidence,
    is_forged: payload.is_forged,
    all_forgery_scores: payload.all_forgery_scores,
    // DocTamper localization results
    doctamper_type: payload.doctamper_type,
    doctamper_confidence: payload.doctamper_confidence,
    doctamper_is_forged: payload.doctamper_is_forged,
    doctamper_tampered_pixels_ratio: payload.doctamper_tampered_pixels_ratio,
    // Explanation and regions
    explanation: payload.reason,
    reasons: [
      `Signature Detected: ${payload.signature_detected ? "Yes" : "No"}`,
      payload.signature_detected
        ? `Signature Verdict: ${payload.signature_verdict} (${(payload.signature_confidence * 100).toFixed(1)}%)`
        : `Forgery Type: ${forgeryType} (${(payload.forgery_confidence * 100).toFixed(1)}%)`,
      `DocTamper Verdict: ${payload.doctamper_is_forged ? "Tampered" : "Authentic"} (${(payload.doctamper_confidence * 100).toFixed(1)}%)`,
      `DocTamper Area: ${((payload.doctamper_tampered_pixels_ratio || 0) * 100).toFixed(1)}% pixels`,
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

/**
 * frontend/src/services/api.js
 * Centralized API client for the Document Forgery Detection backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1";

/**
 * Upload a document file for forgery analysis.
 * @param {File} file
 * @param {"save"|"find"} blockchainAction
 * @returns {Promise<{
 *  result: string,
 *  confidence: number,
 *  hash: string,
 *  cid: string,
 *  tx_hash?: string|null,
 *  anchor_status?: string|null,
 *  anchor_error?: string|null,
 *  chain_exists?: boolean|null,
 *  chain_revoked?: boolean|null,
 *  chain_timestamp?: number|null,
 *  chain_issuer?: string|null,
 *  module_scores?: Record<string, number>,
 *  explanation?: string,
 *  reasons?: string[],
 *  suspected_forgery_type?: string,
 *  forgery_regions?: Array<{x:number,y:number,w:number,h:number,source?:string,score?:number}>
 * }>}
 */
export async function analyzeDocument(file, blockchainAction = "save") {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("blockchain_action", blockchainAction);

  const response = await fetch(`${BASE_URL}/upload`, {
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

  return response.json();
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

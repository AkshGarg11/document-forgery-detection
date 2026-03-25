/**
 * frontend/src/services/api.js
 * Centralised API client for the Document Forgery Detection backend.
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

/**
 * Upload a document file for forgery analysis.
 * @param {File} file
 * @returns {Promise<{result: string, confidence: number, hash: string, cid: string, tx_hash: string|null, module_scores: object}>}
 */
export async function analyzeDocument(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(errorBody.detail || `Request failed with status ${response.status}`)
  }

  return response.json()
}

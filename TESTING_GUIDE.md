# Phase 1 & 2 Testing Guide

## Prerequisites

- Python 3.13 environment configured for backend
- Ganache running on http://127.0.0.1:7545
- Backend uvicorn server started
- Frontend dev server running
- imagehash dependency installed in AI models environment

## Quick Start Commands

### 1. Install imagehash dependency

```bash
cd d:\document-forgery-detection\ai_models
pip install imagehash>=4.3.1
```

### 2. Start backend (if not running)

```bash
cd d:\document-forgery-detection\backend
uvicorn main:app --reload
# Should be available at http://localhost:8000
```

### 3. Start frontend (if not running)

```bash
cd d:\document-forgery-detection\frontend
npm install
npm run dev
# Should be available at http://localhost:5173
```

---

## Phase 1 Testing: Forensic Verdict Generation

### Test Case 1.1: Save Mode (Anchor on Blockchain)

**Steps:**

1. Open frontend at http://localhost:5173
2. Click "Upload" and select any JPG/PNG image
3. Click "**Save on Blockchain**" button
4. Wait for "Saving to blockchain..." to complete

**Expected Result:**

```json
{
  "result": "Authentic", // or Suspicious/Forged based on AI
  "confidence": 0.85,
  "forensic_verdict": "Proof of Existence Recorded",
  "forensic_confidence": 1.0,
  "anchor_status": "anchored",
  "tx_hash": "0x12345...", // Should be 66 chars
  "perceptual_hash": "a1b2c3d4e5f6..." // 64 hex chars
}
```

**Verification Checklist:**

- ✓ forensic_verdict is "Proof of Existence Recorded"
- ✓ forensic_confidence = 1.0
- ✓ tx_hash returned (valid Ganache transaction)
- ✓ perceptual_hash is exactly 64 hex characters
- ✓ chain_status badge shows "✓ Saved"

---

### Test Case 1.2: Find Mode - Exact Match (Authentic)

**Steps:**

1. Take same image from Test Case 1.1
2. Upload again to frontend
3. Click "**Find on Blockchain**" button
4. Wait for verification

**Expected Result:**

```json
{
  "result": "Authentic",
  "confidence": 0.85,
  "forensic_verdict": "Authentic (Found on-chain)",
  "forensic_confidence": 1.0,
  "anchor_status": "found_on_chain",
  "chain_exists": true,
  "chain_revoked": false,
  "chain_timestamp": 1711824000, // Unix timestamp
  "chain_issuer": "0x..." // Issuer address
}
```

**Verification Checklist:**

- ✓ forensic_verdict confirms "Authentic (Found on-chain)"
- ✓ forensic_confidence = 1.0 (100%)
- ✓ chain_exists = true
- ✓ chain_revoked = false
- ✓ chain_status badge shows "✓ Found" with issuer/timestamp

---

### Test Case 1.3: Find Mode - High AI Confidence (NOT Found)

**Steps:**

1. Upload a clearly forged image (edited, obvious tampering)
2. Click "**Find on Blockchain**" button
3. Wait for verification

**Expected Result:**

```json
{
  "result": "Forged",  // High AI confidence
  "confidence": 0.92,
  "forensic_verdict": "NOT on-chain + AI Forged (92%) = Sophisticated Forgery",
  "forensic_confidence": 0.92,
  "anchor_status": "not_found_on_chain",
  "chain_exists": false,
  "reasons": [..., "Blockchain verification: document hash not found on-chain."]
}
```

**Verification Checklist:**

- ✓ forensic_verdict includes "NOT on-chain + AI"
- ✓ forensic_confidence reflects AI confidence (capped at 0.95)
- ✓ result is "Forged"
- ✓ chain_exists = false
- ✓ chain_status badge shows "✗ Not Found"

---

## Phase 2 Testing: Perceptual Hash Similarity Matching

### Test Case 2.1: Perceptual Hash Storage

**What to verify:**

1. In browser DevTools (F12), check Network tab
2. Upload image with "Save on Blockchain"
3. Check response JSON for:
   ```json
   "perceptual_hash": "a1b2c3d4e5f6..." // 64 hex chars
   ```

**Success Criteria:**

- ✓ perceptual_hash is returned
- ✓ Always exactly 64 hex characters (or "0" \* 64 if image load fails)
- ✓ Different images have different perceptual hashes
- ✓ Recompressing same image yields same/very similar perceptual hash

---

### Test Case 2.2: High Similarity Detection (Re-Forgery)

**Scenario**: Catch an attacker who modifies a forged image

**Steps:**

1. **Phase 1**: Save a forged image on blockchain
   - Note the perceptual hash (e.g., "a1b2c3d4...")
   - Note the SHA-256 hash

2. **Prepare modified version**:
   - Take the same image
   - Crop it slightly (5-10% edge crop)
   - Adjust colors/brightness slightly
   - Save as new file (creates different SHA-256, similar pHash)

3. **Upload modified version**:
   - Click "Find on Blockchain"
   - Wait for verification

**Expected Result:**

```json
{
  "result": "Forged", // Changed by forensic verdict logic
  "forensic_verdict": "Visually Similar to On-Chain Document (97% match) - Possible Re-Forgery",
  "forensic_confidence": 0.97,
  "perceptual_match_score": 97.0,
  "anchor_status": "not_found_on_chain",
  "chain_exists": false, // SHA-256 won't match
  "perceptual_hash": "a1c2c3d4..." // Very similar to original
}
```

**Verification Checklist:**

- ✓ SHA-256 hash is DIFFERENT from original
- ✓ Perceptual hash similarity >95%
- ✓ forensic_verdict mentions "Possible Re-Forgery"
- ✓ result is "Forged" (even if AI thought it was authentic)
- ✓ perceptual_match_score is visible (97% or similar)
- ✓ forensic_confidence ≥ 0.95

---

### Test Case 2.3: Unrelated Document (Similarity <95%)

**Steps:**

1. Use a completely different image
2. Upload with "Find on Blockchain"

**Expected Result:**

- `perceptual_match_score` is either None or <95%
- `forensic_verdict` uses AI confidence, not perceptual match
- Result is determined by AI analysis, not similarity

**Verification Checklist:**

- ✓ perceptual_match_score < 95% or null
- ✓ forensic_verdict does NOT mention "Re-Forgery"
- ✓ Result based on AI confidence (ELA, Copy-Move scores)

---

## Backend API Verification

### Endpoint 1: POST /upload (Save Mode)

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test_image.jpg" \
  -F "blockchain_action=save"
```

**Check for in response:**

- forensic_verdict: "Proof of Existence Recorded"
- perceptual_hash: (64 hex chars)
- tx_hash: (66-char Ganache hash)

### Endpoint 2: POST /upload (Find Mode)

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test_image.jpg" \
  -F "blockchain_action=find"
```

**Check for in response:**

- forensic_verdict: (varies based on match/AI)
- chain_exists: (boolean)
- perceptual_match_score: (0-100 or null)

---

## Debugging Common Issues

### Issue: "Contract address not found"

**Solution:**

- Verify Ganache is running on http://127.0.0.1:7545
- Check .env has correct CONTRACT_ADDRESS
- Re-run deployment script: `cd blockchain && python scripts/deploy_with_web3.py`

### Issue: "imagehash not found"

**Solution:**

```bash
cd ai_models
pip install imagehash>=4.3.1
# Verify: python -c "import imagehash; print('OK')"
```

### Issue: perceptual_hash always "0000..."

**Solution:**

- Check file is valid PNG/JPG
- Verify image loads correctly
- Check ImageHash library can handle image format

### Issue: forensic_verdict incorrect

**Solution:**

- Check blockchain_action parameter is sent ("save" vs "find")
- Verify smart contract has perceptual_hash field
- Check AI confidence scores in module_scores

---

## Success Indicators

### Phase 1 Complete ✅

- [x] Save mode: Creates on-chain anchor with forensic verdict
- [x] Find mode exact match: Returns "Authentic (Found on-chain)"
- [x] Find mode not found + high AI: Returns sophisticated forgery verdict
- [x] Frontend displays forensic verdict and chain status badge

### Phase 2 Complete ✅

- [x] Perceptual hash computed for images
- [x] pHash stored on-chain with SHA-256
- [x] Similarity matching: >95% similarity detected as re-forgery warning
- [x] Returns perceptual_match_score in find mode
- [x] Forensic confidence combines blockchain + AI + similarity

---

## Next Steps (Phase 3)

Once Phase 1 & 2 are verified:

1. Add digital signature verification (MetaMask)
2. Implement forensic report template
3. Add version history UI panel
4. Create downloadable forensic PDF report

import { useState } from "react";

/**
 * frontend/src/components/ResultCard.jsx
 */

const LABEL_CONFIG = {
  Authentic: {
    badge: "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
    bar: "bg-emerald-500",
    glow: "shadow-emerald-500/20",
    icon: "OK",
  },
  Suspicious: {
    badge: "bg-amber-500/15 text-amber-400 border border-amber-500/30",
    bar: "bg-amber-500",
    glow: "shadow-amber-500/20",
    icon: "WARN",
  },
  Forged: {
    badge: "bg-red-500/15 text-red-400 border border-red-500/30",
    bar: "bg-red-500",
    glow: "shadow-red-500/20",
    icon: "FORGED",
  },
};

const DOCTAMPER_ZERO_AREA_RATIO = 0.0005; // 0.05% => 0.0% when shown with one decimal

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

function HashRow({ label, value }) {
  return (
    <div className="mt-4">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-1">
        {label}
      </p>
      <code className="block bg-white/5 border border-white/8 rounded-lg px-3 py-2 text-violet-300 text-xs font-mono break-all">
        {value}
      </code>
    </div>
  );
}

function ScoreBar({ label, score }) {
  const pct = (score * 100).toFixed(0);
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs text-white/50 mb-1">
        <span>{label}</span>
        <span
          className={
            score > 0.6
              ? "text-red-400"
              : score > 0.35
                ? "text-amber-400"
                : "text-emerald-400"
          }
        >
          {pct}%
        </span>
      </div>
      <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            score > 0.6
              ? "bg-red-500"
              : score > 0.35
                ? "bg-amber-400"
                : "bg-emerald-400"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function ChainStatusBadge({ status, issuer, timestamp, revoked }) {
  const statusConfig = {
    anchored: { color: "emerald", label: "✓ Saved", detail: "Proof recorded" },
    found_on_chain: {
      color: "emerald",
      label: "✓ Found",
      detail: "Hash verified",
    },
    not_found_on_chain: {
      color: "red",
      label: "✗ Not Found",
      detail: "Not on-chain",
    },
    revoked_on_chain: {
      color: "red",
      label: "⊘ Revoked",
      detail: "Marked revoked",
    },
    anchor_failed: {
      color: "amber",
      label: "⚠ Failed",
      detail: "Anchor error",
    },
    lookup_failed: {
      color: "amber",
      label: "⚠ Error",
      detail: "Lookup failed",
    },
  };
  const cfg = statusConfig[status] || statusConfig.anchor_failed;
  const colorMap = {
    emerald: "text-emerald-400 bg-emerald-500/15 border-emerald-500/30",
    red: "text-red-400 bg-red-500/15 border-red-500/30",
    amber: "text-amber-400 bg-amber-500/15 border-amber-500/30",
  };
  const tsStr = timestamp ? new Date(timestamp * 1000).toLocaleString() : "";
  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border ${colorMap[cfg.color]}`}
    >
      <span>{cfg.label}</span>
      {revoked && <span className="text-xs">🚫</span>}
      <div className="text-white/40 text-xs ml-1">
        {tsStr && <span>{tsStr}</span>}
        {issuer && <span> • {issuer.slice(0, 6)}...</span>}
      </div>
    </div>
  );
}

function AuditTimeline({ events }) {
  if (!events || events.length === 0) return null;

  return (
    <div className="mb-4 pt-4 border-t border-white/8">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-3 font-medium">
        📜 Audit Timeline
      </p>
      <div className="space-y-2">
        {events.map((entry, idx) => {
          const eventLabel = entry.event === "revoked" ? "Revoked" : "Issued";
          const ts = entry.timestamp
            ? new Date(entry.timestamp * 1000).toLocaleString()
            : "Unknown time";
          return (
            <div
              key={`${entry.tx_hash}-${idx}`}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={`text-xs font-semibold ${
                    entry.event === "revoked"
                      ? "text-red-400"
                      : "text-emerald-400"
                  }`}
                >
                  {eventLabel}
                </span>
                <span className="text-white/40 text-xs">
                  Block {entry.block_number}
                </span>
              </div>
              <p className="text-white/60 text-xs mt-1">
                {ts} •{" "}
                {entry.issuer
                  ? `${entry.issuer.slice(0, 10)}...`
                  : "Unknown issuer"}
              </p>
              <p className="text-violet-300 text-xs mt-1 break-all">
                TX: {entry.tx_hash}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ResultCard({
  hash,
  cid,
  tx_hash,
  anchor_status,
  anchor_error,
  chain_revoked,
  chain_timestamp,
  chain_issuer,
  audit_history,
  previewUrl,
  onRevoke,
  // Combined detection fields
  final_verdict,
  risk_level,
  signature_detected,
  signature_confidence,
  signature_verdict,
  signature_probabilities,
  forgery_type,
  forgery_confidence,
  is_forged,
  all_forgery_scores,
  forgery_regions,
  signature_preview_url,
  forgery_preview_url,
  doctamper_type,
  doctamper_confidence,
  doctamper_is_forged,
  doctamper_tampered_pixels_ratio,
  doctamper_preview_url,
  text_found,
  extracted_text_preview,
  ocr_engine,
  document_metadata,
  page_previews,
  selected_page_index,
  reasons,
}) {
  const doctamperSkipped = doctamper_type === "skipped_no_text";
  const effectiveDoctamperTampered =
    Boolean(doctamper_is_forged) &&
    Number(doctamper_tampered_pixels_ratio || 0) > DOCTAMPER_ZERO_AREA_RATIO;

  const cfg =
    LABEL_CONFIG[final_verdict?.split(" - ")[0]] || LABEL_CONFIG.Suspicious;
  const riskColors = {
    low: "emerald",
    medium: "amber",
    high: "red",
  };
  const riskColor = riskColors[risk_level] || "amber";
  const primaryPreviewUrl =
    (signature_detected && signature_preview_url) ||
    (!doctamperSkipped && doctamper_preview_url) ||
    forgery_preview_url ||
    previewUrl;
  const primaryPreviewLabel =
    (signature_detected && signature_preview_url && "Signature Detection") ||
    (!doctamperSkipped && doctamper_preview_url && "DocTamper + Overlay") ||
    (forgery_preview_url && "Forgery Classification") ||
    "Uploaded Document";

  const previewPages =
    Array.isArray(page_previews) && page_previews.length > 0
      ? page_previews
      : primaryPreviewUrl
        ? [primaryPreviewUrl]
        : [];

  const safeInitialPage = Math.min(
    Math.max(Number(selected_page_index || 1), 1),
    previewPages.length || 1,
  );
  const [currentPage, setCurrentPage] = useState(safeInitialPage);
  const boundedCurrentPage = Math.min(
    Math.max(currentPage, 1),
    previewPages.length || 1,
  );

  const shownPreviewUrl =
    previewPages.length > 0
      ? previewPages[Math.max(0, boundedCurrentPage - 1)]
      : null;
  const shownPreviewLabel =
    previewPages.length > 1
      ? `${primaryPreviewLabel} - Page ${boundedCurrentPage}/${previewPages.length}`
      : primaryPreviewLabel;
  const showSignatureOverlay =
    signature_detected &&
    Array.isArray(forgery_regions) &&
    forgery_regions.length > 0;
  const signatureVerdictText = String(signature_verdict || "").toLowerCase();
  const signatureIsForged = signatureVerdictText.includes("forged");
  const signatureIsAuthentic =
    signatureVerdictText.includes("authentic") && !signatureIsForged;

  return (
    <div
      id="result-card"
      className={`
        bg-white/5 border border-white/10 rounded-2xl p-6
        shadow-2xl ${cfg.glow}
        animate-[fadeSlideUp_0.4s_ease_both]
      `}
      style={{ animation: "fadeSlideUp 0.4s ease both" }}
      role="region"
      aria-label="Analysis result"
    >
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <h2 className="text-lg font-bold text-white mb-5 flex items-center gap-2">
        Combined Analysis Report
      </h2>

      {/* Overall Risk Level */}
      <div className="mb-6 p-4 bg-white/5 border border-white/8 rounded-xl">
        <div className="flex items-center justify-between mb-3">
          <span className="text-white/50 text-sm font-medium">
            Overall Status
          </span>
          <span
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold border ${
              riskColor === "emerald"
                ? "text-emerald-400 bg-emerald-500/15 border-emerald-500/30"
                : riskColor === "amber"
                  ? "text-amber-400 bg-amber-500/15 border-amber-500/30"
                  : "text-red-400 bg-red-500/15 border-red-500/30"
            }`}
          >
            {final_verdict}
          </span>
        </div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-white/50 text-xs uppercase">Risk Level</span>
          <span className="text-white font-bold uppercase tracking-wider">
            {risk_level}
          </span>
        </div>
        <div className="h-2 bg-white/10 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              riskColor === "emerald"
                ? "bg-emerald-500"
                : riskColor === "amber"
                  ? "bg-amber-500"
                  : "bg-red-500"
            }`}
            style={{
              width: `${risk_level === "low" ? 33 : risk_level === "medium" ? 66 : 100}%`,
            }}
          />
        </div>
      </div>

      {/* Multi-Model Detection Results */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {/* Signature Verification */}
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3 font-medium">
            🔐 Signature Verification
          </p>
          <div className="space-y-2">
            {signature_detected ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-white/60 text-sm">Detection</span>
                  <span className="text-emerald-400 font-semibold text-sm">
                    ✓ Found
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-white/60 text-sm">Verdict</span>
                  <span
                    className={`font-semibold text-sm ${
                      signatureIsAuthentic ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {signature_verdict}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-white/60 text-sm">Confidence</span>
                  <span className="text-white font-bold text-sm">
                    {(signature_confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-between">
                <span className="text-white/60 text-sm">Detection</span>
                <span className="text-amber-400 font-semibold text-sm">
                  ⚠ Not Found
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Copy-Move Detection */}
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3 font-medium">
            🔍 Forgery Type Detection
          </p>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Type</span>
              <span
                className={`font-semibold text-sm ${
                  is_forged ? "text-red-400" : "text-emerald-400"
                }`}
              >
                {toTitleCase(forgery_type.replace(/([A-Z])/g, " $1").trim())}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Status</span>
              <span
                className={`font-semibold text-sm ${
                  is_forged ? "text-red-400" : "text-emerald-400"
                }`}
              >
                {is_forged ? "Forged" : "Authentic"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Confidence</span>
              <span className="text-white font-bold text-sm">
                {(forgery_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>

        {/* DocTamper Localization */}
        <div className="p-4 bg-white/5 border border-white/8 rounded-xl">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3 font-medium">
            🎯 DocTamper Localization
          </p>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Status</span>
              <span
                className={`font-semibold text-sm ${
                  doctamperSkipped
                    ? "text-amber-400"
                    : effectiveDoctamperTampered
                      ? "text-red-400"
                      : "text-emerald-400"
                }`}
              >
                {doctamperSkipped
                  ? "Skipped (No Text)"
                  : effectiveDoctamperTampered
                    ? "Tampered"
                    : "Authentic"}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Type</span>
              <span
                className={`font-semibold text-sm ${
                  doctamperSkipped
                    ? "text-amber-400"
                    : effectiveDoctamperTampered
                      ? "text-red-400"
                      : "text-emerald-400"
                }`}
              >
                {doctamperSkipped
                  ? "Skipped"
                  : toTitleCase(
                      (doctamper_type || "unknown").replace(/_/g, " "),
                    )}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Confidence</span>
              <span className="text-white font-bold text-sm">
                {doctamperSkipped
                  ? "N/A"
                  : `${((doctamper_confidence || 0) * 100).toFixed(0)}%`}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-white/60 text-sm">Tampered Area</span>
              <span className="text-white font-bold text-sm">
                {doctamperSkipped
                  ? "N/A"
                  : `${((doctamper_tampered_pixels_ratio || 0) * 100).toFixed(1)}%`}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* OCR + Metadata */}
      <div className="mb-4 pt-4 border-t border-white/8">
        <p className="text-white/40 text-xs uppercase tracking-widest mb-3">
          Document Metadata & OCR
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
            <p className="text-white/60 text-xs mb-1">OCR Status</p>
            <p className="text-sm font-semibold text-white">
              {text_found ? "Text Found" : "No Text Found"}
            </p>
            <p className="text-white/50 text-xs mt-1">
              Engine: {ocr_engine || "unknown"}
            </p>
            {extracted_text_preview && (
              <p className="text-white/60 text-xs mt-2 line-clamp-4">
                {extracted_text_preview}
              </p>
            )}
          </div>

          <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
            <p className="text-white/60 text-xs mb-1">File Metadata</p>
            <div className="space-y-1 text-xs text-white/70">
              <p>Name: {document_metadata?.file_name || "N/A"}</p>
              <p>Type: {document_metadata?.content_type || "N/A"}</p>
              <p>Format: {document_metadata?.format || "N/A"}</p>
              <p>
                Resolution: {document_metadata?.width || 0} x{" "}
                {document_metadata?.height || 0}
              </p>
              <p>Size: {document_metadata?.size_bytes || 0} bytes</p>
            </div>
          </div>
        </div>
      </div>

      {/* Detailed Scores */}
      {(signature_probabilities ||
        all_forgery_scores ||
        (reasons && reasons.length > 0)) && (
        <div className="mb-4 pt-4 border-t border-white/8">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3">
            Detailed Analysis
          </p>

          {signature_probabilities &&
            Object.keys(signature_probabilities).length > 0 && (
              <div className="mb-3">
                <p className="text-white/60 text-xs font-medium mb-2">
                  Signature Classification:
                </p>
                {Object.entries(signature_probabilities).map(([key, val]) => (
                  <ScoreBar key={key} label={key} score={val} />
                ))}
              </div>
            )}

          {all_forgery_scores && Object.keys(all_forgery_scores).length > 0 && (
            <div className="mb-3">
              <p className="text-white/60 text-xs font-medium mb-2">
                Forgery Type Classification:
              </p>
              {Object.entries(all_forgery_scores).map(([key, val]) => (
                <ScoreBar
                  key={key}
                  label={toTitleCase(key.replace("_", " "))}
                  score={val}
                />
              ))}
            </div>
          )}

          {reasons && reasons.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/8">
              <p className="text-white/50 text-xs font-medium mb-2">
                Analysis Notes:
              </p>
              <ul className="list-disc pl-4 space-y-1 text-xs text-white/70">
                {reasons.map((reason, idx) => (
                  <li key={idx}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Detection Preview */}
      {shownPreviewUrl && (
        <div className="mb-4 pt-4 border-t border-white/8">
          <div className="flex items-center justify-between gap-3 mb-3">
            <p className="text-white/40 text-xs uppercase tracking-widest">
              Detection Preview
            </p>
            {previewPages.length > 1 && (
              <div className="inline-flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={boundedCurrentPage <= 1}
                  className="px-2 py-1 text-xs rounded-md border border-white/15 text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Prev
                </button>
                <span className="text-xs text-white/60 min-w-20 text-center">
                  Page {boundedCurrentPage}/{previewPages.length}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    setCurrentPage((p) => Math.min(previewPages.length, p + 1))
                  }
                  disabled={boundedCurrentPage >= previewPages.length}
                  className="px-2 py-1 text-xs rounded-md border border-white/15 text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            )}
          </div>
          <div className="rounded-lg overflow-hidden border border-white/10">
            <p className="text-white/50 text-xs font-medium px-2 py-1.5 bg-white/5">
              {shownPreviewLabel}
            </p>
            <div className="relative">
              <img
                src={shownPreviewUrl}
                alt="Detection preview"
                className="w-full h-auto block"
              />
              {showSignatureOverlay &&
                forgery_regions.map((r, i) => (
                  <div
                    key={`${r.source || "region"}-${i}`}
                    className={`absolute border-2 ${
                      signatureIsForged
                        ? "border-red-400 bg-red-400/10"
                        : "border-emerald-400 bg-emerald-400/10"
                    }`}
                    style={{
                      left: `${(r.x || 0) * 100}%`,
                      top: `${(r.y || 0) * 100}%`,
                      width: `${(r.w || 0) * 100}%`,
                      height: `${(r.h || 0) * 100}%`,
                    }}
                    title={`Signature area (${Math.round((r.score || 0) * 100)}%)`}
                  />
                ))}
            </div>
          </div>
          {showSignatureOverlay && (
            <p
              className={`text-xs mt-2 ${
                signatureIsForged ? "text-red-300" : "text-emerald-300"
              }`}
            >
              Signature area is highlighted on this preview (
              {signatureIsForged ? "forged" : "authentic"}).
            </p>
          )}
          {doctamperSkipped && (
            <p className="text-amber-300 text-xs mt-2">
              DocTamper was skipped because OCR did not detect text.
            </p>
          )}
        </div>
      )}

      {/* Blockchain Status */}
      {anchor_status && (
        <div className="mb-4 pt-4 border-t border-white/8">
          <div className="flex items-center justify-between mb-3">
            <p className="text-white/40 text-xs uppercase tracking-widest font-medium">
              ⛓️ Blockchain Status
            </p>
            {onRevoke &&
              anchor_status === "found_on_chain" &&
              !chain_revoked && (
                <button
                  onClick={onRevoke}
                  className="px-3 py-1 text-xs font-semibold text-red-400 bg-red-500/15 border border-red-500/30 rounded-lg hover:bg-red-500/25 transition-colors duration-200"
                >
                  ⊘ Revoke Document
                </button>
              )}
          </div>
          <ChainStatusBadge
            status={anchor_status}
            issuer={chain_issuer}
            timestamp={chain_timestamp}
            revoked={chain_revoked}
          />
        </div>
      )}

      <AuditTimeline events={audit_history} />

      {/* Hash & Blockchain Data */}
      <div className="pt-4 border-t border-white/8">
        {hash && hash !== "N/A" && (
          <HashRow label="Document SHA-256" value={hash} />
        )}
        {cid && cid !== "N/A" && <HashRow label="IPFS CID" value={cid} />}
        {tx_hash && <HashRow label="Blockchain TX" value={tx_hash} />}
        {anchor_error && <HashRow label="Anchor Error" value={anchor_error} />}
      </div>
    </div>
  );
}

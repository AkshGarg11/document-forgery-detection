import { useEffect, useMemo, useState } from "react";
import FileUpload from "../components/FileUpload";
import ResultCard from "../components/ResultCard";
import {
  analyzeDocument,
  storeDocumentHash,
  revokeDocumentHash,
  verifyDocumentHash,
  fetchAuditHistory,
} from "../services/api";

const HISTORY_STORAGE_KEY = "forgeguard.analysis.history.v1";

const STATUS = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  ERROR: "error",
};

const loadInitialHistory = () => {
  try {
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

export default function Home() {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(STATUS.IDLE);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [storeLoading, setStoreLoading] = useState(false);
  const [storeMsg, setStoreMsg] = useState("");
  const [revokeLoading, setRevokeLoading] = useState(false);
  const [revokeMsg, setRevokeMsg] = useState("");
  const [saveReportMsg, setSaveReportMsg] = useState("");
  const [analysisHistory, setAnalysisHistory] = useState(loadInitialHistory);

  useEffect(() => {
    try {
      localStorage.setItem(
        HISTORY_STORAGE_KEY,
        JSON.stringify(analysisHistory),
      );
    } catch {
      // Ignore storage failures and keep runtime state only.
    }
  }, [analysisHistory]);

  const previewUrl = useMemo(() => {
    if (!file || !file.type?.startsWith("image/")) return null;
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const addHistoryEntry = (analysis, selectedFile) => {
    const entry = {
      id: `${analysis.hash}-${Date.now()}`,
      analyzedAt: Date.now(),
      fileName: selectedFile?.name || "Unknown file",
      fileSize: selectedFile?.size || 0,
      hash: analysis.hash,
      final_verdict: analysis.final_verdict,
      risk_level: analysis.risk_level,
      anchor_status: analysis.anchor_status,
      chain_revoked: analysis.chain_revoked,
      doctamper_tampered_pixels_ratio: analysis.doctamper_tampered_pixels_ratio,
      report: analysis,
    };
    setAnalysisHistory((prev) => [entry, ...prev].slice(0, 15));
  };

  const handleAnalyze = async () => {
    if (!file) return;
    setAnalyzeLoading(true);
    setStatus(STATUS.LOADING);
    setResult(null);
    setStoreMsg("");
    setSaveReportMsg("");
    setErrorMsg("");
    try {
      const data = await analyzeDocument(file, "find");
      setResult(data);
      setStatus(STATUS.SUCCESS);
    } catch (err) {
      setErrorMsg(err.message || "Analysis failed. Please try again.");
      setStatus(STATUS.ERROR);
    } finally {
      setAnalyzeLoading(false);
    }
  };

  const handleStoreOnBlockchain = async () => {
    if (!result?.hash) return;
    setStoreLoading(true);
    setStoreMsg("");
    try {
      const issueResult = await storeDocumentHash(result.hash);
      const updatedVerification = await verifyDocumentHash(result.hash);
      const updatedHistory = await fetchAuditHistory(result.hash);

      setResult((prev) => ({
        ...prev,
        tx_hash: issueResult.tx_hash,
        anchor_status:
          updatedVerification.exists && !updatedVerification.revoked
            ? "found_on_chain"
            : prev.anchor_status,
        chain_exists: updatedVerification.exists,
        chain_revoked: updatedVerification.revoked,
        chain_timestamp: updatedVerification.timestamp,
        chain_issuer: updatedVerification.issuer,
        audit_history: updatedHistory.history || [],
      }));

      setAnalysisHistory((prev) =>
        prev.map((entry) =>
          entry.hash === result.hash
            ? {
                ...entry,
                anchor_status: "found_on_chain",
                chain_revoked: false,
              }
            : entry,
        ),
      );

      setStoreMsg("✓ Document stored on blockchain successfully.");
    } catch (err) {
      setStoreMsg(`✗ Store failed: ${err.message}`);
    } finally {
      setStoreLoading(false);
    }
  };

  const handleRevoke = async () => {
    if (!result?.hash) return;
    setRevokeLoading(true);
    setRevokeMsg("");
    try {
      await revokeDocumentHash(result.hash);

      // Refresh document status and audit history
      const updatedVerification = await verifyDocumentHash(result.hash);
      const updatedHistory = await fetchAuditHistory(result.hash);

      setResult({
        ...result,
        chain_revoked: updatedVerification.revoked,
        anchor_status: "revoked_on_chain",
        audit_history: updatedHistory.history || [],
      });

      setRevokeMsg("✓ Document successfully revoked! Timeline updated.");
    } catch (err) {
      setRevokeMsg(`✗ Revoke failed: ${err.message}`);
    } finally {
      setRevokeLoading(false);
    }
  };

  const handleSaveReport = () => {
    if (!result) return;
    addHistoryEntry(result, file);
    setSaveReportMsg("✓ Report saved to history.");
  };

  const handleSelectHistoryItem = (entry) => {
    if (!entry?.report) return;
    setResult(entry.report);
    setStatus(STATUS.SUCCESS);
    setErrorMsg("");
    setStoreMsg("");
    setRevokeMsg("");
    setSaveReportMsg("");
    setFile(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const isLoading = status === STATUS.LOADING;
  const showStoreButton =
    Boolean(result?.hash) &&
    result?.anchor_status === "not_found_on_chain" &&
    !result?.chain_revoked;
  const displayPreviewUrl = result?.annotated_preview_url || previewUrl;

  return (
    <main className="max-w-6xl mx-auto px-4 py-12 md:py-16">
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-full px-4 py-1.5 text-violet-400 text-sm font-medium mb-6">
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse inline-block" />
          Multi-Model Detection
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight mb-4">
          Forgery{" "}
          <span className="bg-linear-to-r from-violet-400 via-fuchsia-400 to-cyan-400 bg-clip-text text-transparent">
            Detection
          </span>
        </h1>
        <p className="text-white/50 text-lg max-w-xl mx-auto leading-relaxed">
          Parallel analysis: detect signature regions, verify authenticity, and
          detect copy-move/splicing forgeries.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 bg-white/4 border border-white/10 rounded-2xl p-5 md:p-6">
          <h2 className="text-white font-semibold text-lg mb-4">
            Analyze Document
          </h2>
          <div id="upload-form" className="space-y-4">
            <FileUpload onFileSelect={setFile} />

            <button
              id="analyze-submit-btn"
              type="button"
              onClick={handleAnalyze}
              disabled={!file || isLoading}
              aria-busy={analyzeLoading}
              className={`
                w-full py-3.5 rounded-xl font-semibold text-white text-base
                transition-all duration-200
                ${
                  !file || isLoading
                    ? "bg-white/10 text-white/30 cursor-not-allowed"
                    : "bg-linear-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 hover:-translate-y-0.5 shadow-lg shadow-violet-500/25"
                }
              `}
            >
              {analyzeLoading ? "Analyzing..." : "Analyze"}
            </button>

            {showStoreButton && (
              <button
                id="store-submit-btn"
                type="button"
                onClick={handleStoreOnBlockchain}
                disabled={storeLoading}
                className={`
                  w-full py-3 rounded-xl font-semibold text-base transition-all duration-200
                  ${
                    storeLoading
                      ? "bg-white/10 text-white/30 cursor-not-allowed"
                      : "bg-linear-to-r from-cyan-600 to-blue-600 text-white hover:from-cyan-500 hover:to-blue-500 hover:-translate-y-0.5 shadow-lg shadow-cyan-500/25"
                  }
                `}
              >
                {storeLoading
                  ? "Storing on blockchain..."
                  : "Store on Blockchain"}
              </button>
            )}

            {storeMsg && (
              <div
                className={`text-sm font-medium ${
                  storeMsg.startsWith("✓") ? "text-emerald-400" : "text-red-400"
                }`}
              >
                {storeMsg}
              </div>
            )}
          </div>
        </section>

        <aside className="bg-white/4 border border-white/10 rounded-2xl p-5 md:p-6">
          <h2 className="text-white font-semibold text-lg mb-4">
            Analysis History
          </h2>
          {analysisHistory.length === 0 ? (
            <p className="text-white/50 text-sm">
              No analyses yet. Run your first analysis to build history.
            </p>
          ) : (
            <div className="space-y-3 max-h-130 overflow-auto pr-1">
              {analysisHistory.map((entry) => {
                const areaPct = (
                  (entry.doctamper_tampered_pixels_ratio || 0) * 100
                ).toFixed(1);
                return (
                  <button
                    key={entry.id}
                    type="button"
                    onClick={() => handleSelectHistoryItem(entry)}
                    className="w-full text-left rounded-xl border border-white/10 bg-white/5 p-3 hover:bg-white/8 hover:border-violet-400/40 transition-colors duration-200"
                  >
                    <p
                      className="text-white text-sm font-medium truncate"
                      title={entry.fileName}
                    >
                      {entry.fileName}
                    </p>
                    <p className="text-white/45 text-xs mt-1">
                      {new Date(entry.analyzedAt).toLocaleString()}
                    </p>
                    <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                      <span className="text-white/70">
                        {entry.final_verdict}
                      </span>
                      <span className="text-white/50 uppercase">
                        {entry.risk_level}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-white/50">
                      Chain: {entry.anchor_status || "unknown"}
                    </div>
                    <div className="mt-1 text-xs text-white/50">
                      DocTamper area: {areaPct}%
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </aside>
      </div>

      {status === STATUS.ERROR && (
        <div
          role="alert"
          className="mt-4 flex items-start gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-red-400 text-sm"
        >
          <span className="text-base mt-0.5">!</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {status === STATUS.SUCCESS && result && (
        <div className="mt-8">
          <div className="mb-4 flex items-center gap-3">
            <button
              id="save-report-btn"
              type="button"
              onClick={handleSaveReport}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-linear-to-r from-emerald-600 to-teal-600 text-white hover:from-emerald-500 hover:to-teal-500 transition-all duration-200"
            >
              Save Report
            </button>
            {saveReportMsg && (
              <span className="text-emerald-400 text-sm font-medium">
                {saveReportMsg}
              </span>
            )}
          </div>
          <ResultCard
            {...result}
            previewUrl={displayPreviewUrl}
            onRevoke={handleRevoke}
          />
          {revokeLoading && (
            <div className="mt-4 text-center text-white/50 text-sm">
              Revoking document...
            </div>
          )}
          {revokeMsg && (
            <div
              className={`mt-4 text-center text-sm font-medium ${
                revokeMsg.startsWith("✓") ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {revokeMsg}
            </div>
          )}
        </div>
      )}
    </main>
  );
}

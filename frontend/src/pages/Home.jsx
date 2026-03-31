import { useEffect, useMemo, useState } from "react";
import Sidebar from "../components/Sidebar";
import FileUpload from "../components/FileUpload";
import ForensicReport from "../components/ForensicReport";
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
  const [currentTab, setCurrentTab] = useState("upload");
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
      chain_timestamp: analysis.chain_timestamp,
      chain_issuer: analysis.chain_issuer,
      tx_hash: analysis.tx_hash,
      audit_history: analysis.audit_history || [],
      doctamper_tampered_pixels_ratio: analysis.doctamper_tampered_pixels_ratio,
      report: analysis,
    };
    setAnalysisHistory((prev) => {
      // Prevent duplicate entries by checking if hash already exists
      const existing = prev.findIndex((e) => e.hash === analysis.hash);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = entry;
        return updated.slice(0, 15);
      }
      return [entry, ...prev].slice(0, 15);
    });
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
      setCurrentTab("forensic");
      // Auto-add to history after successful analysis
      addHistoryEntry(data, file);
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
                tx_hash: issueResult.tx_hash,
                chain_timestamp: updatedVerification.timestamp,
                chain_issuer: updatedVerification.issuer,
                audit_history: updatedHistory.history || [],
                report: {
                  ...entry.report,
                  tx_hash: issueResult.tx_hash,
                  anchor_status: "found_on_chain",
                  chain_revoked: false,
                  chain_timestamp: updatedVerification.timestamp,
                  chain_issuer: updatedVerification.issuer,
                  audit_history: updatedHistory.history || [],
                },
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

      const revokedResult = {
        ...result,
        chain_revoked: updatedVerification.revoked,
        anchor_status: "revoked_on_chain",
        audit_history: updatedHistory.history || [],
      };
      setResult(revokedResult);

      // Update the history entry with revoked state and audit history
      setAnalysisHistory((prev) =>
        prev.map((entry) =>
          entry.hash === result.hash
            ? {
                ...entry,
                chain_revoked: true,
                anchor_status: "revoked_on_chain",
                audit_history: updatedHistory.history || [],
                report: {
                  ...entry.report,
                  chain_revoked: true,
                  anchor_status: "revoked_on_chain",
                  audit_history: updatedHistory.history || [],
                },
              }
            : entry,
        ),
      );

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
    setCurrentTab("forensic");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleTabChange = (tabId) => {
    setCurrentTab(tabId);
    if (tabId === "upload") {
      setResult(null);
      setStatus(STATUS.IDLE);
      setFile(null);
    }
  };

  const isLoading = status === STATUS.LOADING;
  const showStoreButton =
    Boolean(result?.hash) &&
    result?.anchor_status === "not_found_on_chain" &&
    !result?.chain_revoked;
  const displayPreviewUrl = result?.annotated_preview_url || previewUrl;

  return (
    <div className="flex bg-[#060b0d] min-h-screen text-white font-sans overflow-hidden">
      <Sidebar activeTab={currentTab} onTabChange={handleTabChange} />
      <main className="flex-1 ml-64 min-h-screen overflow-y-auto">
        {currentTab === "forensic" && status === STATUS.SUCCESS && result ? (
          <ForensicReport
            result={result}
            displayPreviewUrl={displayPreviewUrl}
            onRerun={handleAnalyze}
            anchor_status={result?.anchor_status}
            chain_revoked={result?.chain_revoked}
            chain_timestamp={result?.chain_timestamp}
            chain_issuer={result?.chain_issuer}
            onRevoke={
              result?.anchor_status === "not_found_on_chain"
                ? handleStoreOnBlockchain
                : handleRevoke
            }
            storeLoading={storeLoading}
            revokeLoading={revokeLoading}
            storeMsg={storeMsg}
            revokeMsg={revokeMsg}
          />
        ) : currentTab === "history" ? (
          <div className="flex-1 bg-[#060b0d] text-white p-8 overflow-y-auto">
            <div className="max-w-6xl mx-auto">
              <div className="mb-10">
                <h2 className="text-3xl font-extrabold text-white mb-2 tracking-tight">
                  Analysis History
                </h2>
                <p className="text-white/40 text-sm">
                  {analysisHistory.length} analysis result
                  {analysisHistory.length !== 1 ? "s" : ""} stored locally
                </p>
              </div>

              {analysisHistory.length === 0 ? (
                <div className="text-center py-20">
                  <p className="text-white/30 text-lg">
                    No analysis history yet
                  </p>
                  <p className="text-white/20 text-sm mt-2">
                    Start by uploading and analyzing a document
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {analysisHistory.map((entry) => (
                    <div
                      key={entry.id}
                      onClick={() => handleSelectHistoryItem(entry)}
                      className="bg-[#0b1619] border border-white/5 rounded-xl p-5 hover:bg-white/5 hover:border-white/10 transition-all cursor-pointer group"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex-1">
                          <h3 className="text-white font-bold mb-1">
                            {entry.fileName}
                          </h3>
                          <div className="flex items-center gap-4 text-xs text-white/40">
                            <span>
                              {new Date(entry.analyzedAt).toLocaleString()}
                            </span>
                            <span>•</span>
                            <span>{(entry.fileSize / 1024).toFixed(1)} KB</span>
                            <span>•</span>
                            <span className="font-mono">
                              {entry.hash.slice(0, 12)}...
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right mr-4">
                            <p
                              className={`text-sm font-bold ${
                                entry.final_verdict
                                  ?.toLowerCase()
                                  .includes("forged")
                                  ? "text-red-400"
                                  : "text-emerald-400"
                              }`}
                            >
                              {entry.final_verdict || "Unknown"}
                            </p>
                            <p
                              className={`text-xs font-bold uppercase ${
                                entry.risk_level === "high"
                                  ? "text-red-500"
                                  : entry.risk_level === "medium"
                                    ? "text-amber-500"
                                    : "text-emerald-500"
                              }`}
                            >
                              {entry.risk_level} Risk
                            </p>
                          </div>
                          <div className="text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity">
                            👁 VIEW
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto px-6 py-16">
            <header className="mb-12">
              <h1 className="text-4xl font-extrabold text-white mb-4 tracking-tight">
                New Analysis
              </h1>
              <p className="text-white/40 text-lg">
                Upload a document to perform deep forensic verification and
                blockchain anchoring.
              </p>
            </header>

            <div className="bg-[#0b1619] border border-white/5 rounded-3xl p-8 shadow-2xl">
              <FileUpload onFileSelect={setFile} />

              <div className="mt-8">
                <button
                  id="analyze-submit-btn"
                  onClick={handleAnalyze}
                  disabled={!file || isLoading}
                  className={`
                    w-full py-4 rounded-xl font-black text-sm uppercase tracking-widest transition-all duration-300
                    ${
                      !file || isLoading
                        ? "bg-white/5 text-white/20 border border-white/5 cursor-not-allowed"
                        : "bg-cyan-500 text-[#060b0d] hover:bg-cyan-400 hover:-translate-y-1 shadow-[0_0_20px_rgba(6,182,212,0.3)]"
                    }
                  `}
                >
                  {analyzeLoading
                    ? "Running Neural Scan..."
                    : "Initiate Analysis"}
                </button>
              </div>

              {status === STATUS.ERROR && (
                <div className="mt-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl flex items-center gap-3 text-red-500 font-bold text-sm">
                  <span>!</span>
                  {errorMsg}
                </div>
              )}
            </div>

            {/* Recent History Quick Access */}
            <div className="mt-12">
              <h3 className="text-white/40 text-xs font-bold uppercase tracking-widest mb-6 px-1">
                Recent Activity
              </h3>
              <div className="grid grid-cols-2 gap-4">
                {analysisHistory.slice(0, 4).map((entry) => (
                  <button
                    key={entry.id}
                    onClick={() => handleSelectHistoryItem(entry)}
                    className="flex flex-col p-4 bg-[#0b1619] border border-white/5 rounded-2xl hover:bg-white/5 transition-all text-left group"
                  >
                    <span className="text-white font-bold text-sm mb-1 truncate">
                      {entry.fileName}
                    </span>
                    <span className="text-white/30 text-[10px] uppercase font-bold">
                      {new Date(entry.analyzedAt).toLocaleDateString()}
                    </span>
                    <div className="mt-auto pt-4 flex items-center justify-between">
                      <span
                        className={`text-[10px] font-black uppercase ${entry.risk_level === "high" ? "text-red-500" : "text-emerald-500"}`}
                      >
                        {entry.risk_level} Risk
                      </span>
                      <span className="text-cyan-400 opacity-0 group-hover:opacity-100 transition-opacity text-[10px] font-bold">
                        VIEW →
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

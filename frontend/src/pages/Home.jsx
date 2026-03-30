import { useEffect, useMemo, useState } from "react";
import FileUpload from "../components/FileUpload";
import ResultCard from "../components/ResultCard";
import {
  analyzeDocument,
  revokeDocumentHash,
  verifyDocumentHash,
} from "../services/api";

const STATUS = {
  IDLE: "idle",
  LOADING: "loading",
  SUCCESS: "success",
  ERROR: "error",
};

export default function Home() {
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState(STATUS.IDLE);
  const [result, setResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [hashInput, setHashInput] = useState("");
  const [chainAction, setChainAction] = useState(null);
  const [chainResult, setChainResult] = useState(null);
  const [chainError, setChainError] = useState("");
  const [uploadAction, setUploadAction] = useState("save");

  const previewUrl = useMemo(() => {
    if (!file || !file.type?.startsWith("image/")) return null;
    return URL.createObjectURL(file);
  }, [file]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleSubmit = async (action) => {
    if (!file) return;
    setUploadAction(action);
    setStatus(STATUS.LOADING);
    setResult(null);
    setErrorMsg("");
    try {
      const data = await analyzeDocument(file, action);
      setResult(data);
      setHashInput(data.hash || "");
      setStatus(STATUS.SUCCESS);
    } catch (err) {
      setErrorMsg(err.message || "Analysis failed. Please try again.");
      setStatus(STATUS.ERROR);
    }
  };

  const normalizeHash = (value) =>
    value.trim().toLowerCase().replace(/^0x/, "");

  const isHashValid = /^[0-9a-f]{64}$/.test(normalizeHash(hashInput));

  const handleUseLastHash = () => {
    if (result?.hash) {
      setHashInput(result.hash);
      setChainError("");
      setChainResult(null);
    }
  };

  const handleVerify = async () => {
    if (!isHashValid) return;
    setChainAction("verify");
    setChainResult(null);
    setChainError("");
    try {
      const payload = await verifyDocumentHash(normalizeHash(hashInput));
      setChainResult({ type: "verify", payload });
    } catch (err) {
      setChainError(err.message || "Verify request failed.");
    } finally {
      setChainAction(null);
    }
  };

  const handleRevoke = async () => {
    if (!isHashValid) return;
    setChainAction("revoke");
    setChainResult(null);
    setChainError("");
    try {
      const payload = await revokeDocumentHash(normalizeHash(hashInput));
      setChainResult({ type: "revoke", payload });
    } catch (err) {
      setChainError(err.message || "Revoke request failed.");
    } finally {
      setChainAction(null);
    }
  };

  const isLoading = status === STATUS.LOADING;

  return (
    <main className="max-w-2xl mx-auto px-4 py-16">
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-full px-4 py-1.5 text-violet-400 text-sm font-medium mb-6">
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse inline-block" />
          AI + Blockchain Verification
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight mb-4">
          Document{" "}
          <span className="bg-linear-to-r from-violet-400 via-fuchsia-400 to-cyan-400 bg-clip-text text-transparent">
            Forgery Detector
          </span>
        </h1>
        <p className="text-white/50 text-lg max-w-md mx-auto leading-relaxed">
          Upload any document - our AI pipeline detects tampering and anchors
          integrity hashes on-chain.
        </p>
      </div>

      <div id="upload-form" className="space-y-4">
        <FileUpload onFileSelect={setFile} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            id="save-submit-btn"
            type="button"
            onClick={() => handleSubmit("save")}
            disabled={!file || isLoading}
            aria-busy={isLoading && uploadAction === "save"}
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
            {isLoading && uploadAction === "save"
              ? "Saving to blockchain..."
              : "Save on Blockchain"}
          </button>

          <button
            id="find-submit-btn"
            type="button"
            onClick={() => handleSubmit("find")}
            disabled={!file || isLoading}
            aria-busy={isLoading && uploadAction === "find"}
            className={`
              w-full py-3.5 rounded-xl font-semibold text-white text-base
              transition-all duration-200
              ${
                !file || isLoading
                  ? "bg-white/10 text-white/30 cursor-not-allowed"
                  : "bg-linear-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 hover:-translate-y-0.5 shadow-lg shadow-cyan-500/25"
              }
            `}
          >
            {isLoading && uploadAction === "find"
              ? "Finding on blockchain..."
              : "Find on Blockchain"}
          </button>
        </div>
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
          <ResultCard {...result} previewUrl={previewUrl} />
        </div>
      )}

      <section className="mt-8 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-xl">
        <h2 className="text-lg font-bold text-white mb-2">On-Chain Actions</h2>
        <p className="text-sm text-white/50 mb-4">
          Verify or revoke an anchored hash using the blockchain API endpoints.
        </p>

        <label
          htmlFor="hash-input"
          className="text-white/40 text-xs uppercase tracking-widest mb-1 block"
        >
          Document Hash (64 hex)
        </label>
        <input
          id="hash-input"
          type="text"
          value={hashInput}
          onChange={(e) => setHashInput(e.target.value)}
          placeholder="e.g. 9f... (64 hex chars)"
          className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-violet-200 font-mono outline-none focus:border-violet-400"
        />

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleUseLastHash}
            disabled={!result?.hash}
            className={`px-3 py-2 rounded-lg text-sm font-medium transition ${
              result?.hash
                ? "bg-white/10 text-white hover:bg-white/15"
                : "bg-white/5 text-white/30 cursor-not-allowed"
            }`}
          >
            Use Last Upload Hash
          </button>
          <button
            type="button"
            onClick={handleVerify}
            disabled={!isHashValid || !!chainAction}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition ${
              isHashValid && !chainAction
                ? "bg-cyan-600 text-white hover:bg-cyan-500"
                : "bg-white/10 text-white/30 cursor-not-allowed"
            }`}
          >
            {chainAction === "verify" ? "Verifying..." : "Verify"}
          </button>
          <button
            type="button"
            onClick={handleRevoke}
            disabled={!isHashValid || !!chainAction}
            className={`px-4 py-2 rounded-lg text-sm font-semibold transition ${
              isHashValid && !chainAction
                ? "bg-amber-600 text-white hover:bg-amber-500"
                : "bg-white/10 text-white/30 cursor-not-allowed"
            }`}
          >
            {chainAction === "revoke" ? "Revoking..." : "Revoke"}
          </button>
        </div>

        {!isHashValid && hashInput.trim().length > 0 && (
          <p className="mt-3 text-xs text-amber-400">
            Enter a valid 64-character hex hash (with or without 0x).
          </p>
        )}

        {chainError && (
          <div className="mt-4 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2 text-sm text-red-300">
            {chainError}
          </div>
        )}

        {chainResult?.type === "verify" && (
          <div className="mt-4 bg-white/5 border border-white/10 rounded-lg p-4">
            <p className="text-sm text-white mb-2">Verify Response</p>
            <div className="text-xs text-white/70 space-y-1 font-mono break-all">
              <p>exists: {String(chainResult.payload.exists)}</p>
              <p>is_valid: {String(chainResult.payload.is_valid)}</p>
              <p>revoked: {String(chainResult.payload.revoked)}</p>
              <p>timestamp: {String(chainResult.payload.timestamp)}</p>
              <p>issuer: {chainResult.payload.issuer}</p>
              <p>text_hash: {chainResult.payload.text_hash}</p>
            </div>
          </div>
        )}

        {chainResult?.type === "revoke" && (
          <div className="mt-4 bg-white/5 border border-white/10 rounded-lg p-4">
            <p className="text-sm text-white mb-2">Revoke Response</p>
            <div className="text-xs text-white/70 space-y-1 font-mono break-all">
              <p>revoked_file_hash: {chainResult.payload.revoked_file_hash}</p>
              <p>tx_hash: {chainResult.payload.tx_hash}</p>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

import { motion } from "framer-motion";
import { 
  AlertCircle, 
  ShieldAlert, 
  Search, 
  Download, 
  RotateCw,
  Clock,
  Layers,
  Database,
  Type,
  Maximize2
} from "lucide-react";

export default function ForensicReport({ result, displayPreviewUrl, onRerun }) {
  if (!result) return null;

  const { 
    final_verdict, 
    risk_level, 
    hash, 
    confidence,
    audit_history = [],
    reasons = [],
    signature_detected,
    is_forged,
    forgery_type,
    doctamper_is_forged,
    doctamper_tampered_pixels_ratio,
    document_metadata = {}
  } = result;

  const displayConfidence = (confidence * 100).toFixed(0);
  const isHighRisk = risk_level === "high" || final_verdict?.toLowerCase().includes("forged");

  const handleDownloadReport = () => {
    const reportData = {
      title: "VeriScan Forensic Analysis Report",
      timestamp: new Date().toISOString(),
      document: document_metadata?.file_name || "Unknown",
      verdict: final_verdict,
      risk: risk_level,
      confidence: `${displayConfidence}%`,
      hash: hash,
      findings: reasons,
      blockchain_audit: audit_history
    };
    
    const blob = new Blob([JSON.stringify(reportData, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `Forensic_Report_${hash.slice(0, 8)}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex-1 min-h-screen bg-[#060b0d] text-white p-8 overflow-y-auto">
      {/* Top Header */}
      <div className="flex items-center justify-between mb-10">
        <div className="relative w-96 font-sans">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30 font-sans" />
          <input 
            type="text" 
            placeholder="Search case files..." 
            className="w-full bg-white/5 border border-white/10 rounded-xl py-2.5 pl-10 pr-4 text-sm focus:outline-none focus:border-cyan-500/50 transition-all font-sans text-white"
          />
        </div>
        <div className="flex items-center gap-4">
          <button className="p-2.5 rounded-xl bg-white/5 border border-white/10 text-white/50 hover:text-white transition-all">
            <Clock className="w-5 h-5 font-sans" />
          </button>
          <button className="px-5 py-2.5 rounded-xl bg-cyan-500 text-[#060b0d] font-bold text-sm hover:bg-cyan-400 transition-all font-sans flex items-center gap-2">
            Logout
          </button>
        </div>
      </div>

      {/* Main Content Title */}
      <div className="flex items-end justify-between mb-8 font-sans">
        <div>
          <p className="text-cyan-400/60 text-xs font-bold uppercase tracking-widest mb-1 font-sans">
            Forensic Reports › {document_metadata?.file_name || "Deep Scan"}
          </p>
          <h2 className="text-3xl font-extrabold text-white tracking-tight font-sans">Analysis & Forensic Results</h2>
          <div className="flex items-center gap-3 mt-1 font-sans">
            <span className="text-white/40 text-sm font-sans underline underline-offset-4 decoration-white/10 cursor-help">
              Hash: <span className="text-white font-medium">{hash?.slice(0, 16)}...</span>
            </span>
            <span className="w-1 h-1 rounded-full bg-white/20" />
            <span className="text-white/40 text-sm font-sans flex items-center gap-1.5 font-sans">
              Status: <span className="text-emerald-400 font-bold font-sans">Completed</span>
            </span>
          </div>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={onRerun}
            className="px-5 py-2.5 rounded-xl bg-white/5 border border-white/10 text-white/70 font-bold text-sm hover:bg-white/10 transition-all flex items-center gap-2 font-sans"
          >
            <RotateCw className="w-4 h-4" />
            Re-run Analysis
          </button>
          <button 
            onClick={handleDownloadReport}
            className="px-5 py-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 font-bold text-sm hover:bg-cyan-500/20 transition-all flex items-center gap-2 font-sans"
          >
            <Download className="w-4 h-4" />
            Download Forensic Report
          </button>
        </div>
      </div>

      {/* Grid Layout */}
      <div className="grid grid-cols-12 gap-8 font-sans">
        {/* Left Column: Scores & Indicators */}
        <div className="col-span-4 space-y-8 font-sans">
          {/* Authenticity Score */}
          <div className="bg-[#0b1619] border border-white/5 rounded-2xl p-6 relative overflow-hidden font-sans shadow-2xl">
            <div className={`absolute top-0 right-0 w-32 h-32 ${isHighRisk ? 'bg-red-500/10' : 'bg-emerald-500/10'} blur-3xl rounded-full -mr-16 -mt-16`} />
            <div className="flex items-center justify-between mb-6 font-sans">
              <span className="text-white/40 text-xs font-bold uppercase tracking-widest font-sans">Authenticity Score</span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-extrabold uppercase font-sans ${isHighRisk ? 'bg-red-500/10 text-red-500' : 'bg-emerald-500/10 text-emerald-500'}`}>
                {risk_level} Risk
              </span>
            </div>
            
            <div className="flex items-center gap-6 font-sans">
              <div className="relative w-28 h-28 flex items-center justify-center font-sans">
                <svg className="w-full h-full transform -rotate-90">
                  <circle 
                    cx="56" cy="56" r="50" 
                    className="stroke-[#132328]" strokeWidth="8" fill="none" 
                  />
                  <motion.circle 
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: confidence }}
                    transition={{ duration: 1.5, ease: "easeOut" }}
                    cx="56" cy="56" r="50" 
                    className={isHighRisk ? "stroke-red-500/80" : "stroke-emerald-500/80"} 
                    strokeWidth="8" fill="none" strokeDasharray="314.159"
                    strokeLinecap="round"
                    style={{ filter: `drop-shadow(0 0 12px ${isHighRisk ? 'rgba(239, 68, 68, 0.4)' : 'rgba(16, 185, 129, 0.4)'})` }}
                  />
                </svg>
                <div className="absolute flex flex-col items-center font-sans">
                  <span className="text-3xl font-black text-white font-sans">{displayConfidence}%</span>
                </div>
              </div>
              <div className="flex-1 font-sans">
                <h4 className={`font-black text-lg mb-1 leading-tight font-sans ${isHighRisk ? 'text-red-500' : 'text-emerald-500'}`}>
                  {final_verdict}
                </h4>
                <p className="text-white/40 text-xs leading-relaxed font-sans">
                  {isHighRisk 
                    ? "Deep-level document manipulation detected in the analysis pipeline."
                    : "Document matches signature patterns and shows no signs of digital alteration."
                  }
                </p>
              </div>
            </div>
          </div>

          {/* Forensic Indicators */}
          <div className="bg-[#0b1619] border border-white/5 rounded-2xl p-6 font-sans shadow-2xl">
            <p className="text-white/40 text-xs font-bold uppercase tracking-widest mb-6 font-sans">Forensic Indicators</p>
            <div className="space-y-4 font-sans max-h-96 overflow-y-auto pr-2">
              {reasons.length > 0 ? reasons.map((reason, idx) => {
                const isWarning = reason.toLowerCase().includes("detected") || reason.toLowerCase().includes("forged") || reason.toLowerCase().includes("anomaly");
                const Icon = isWarning ? AlertCircle : ShieldAlert;
                
                return (
                  <div key={idx} className={`p-4 rounded-xl border flex items-start gap-4 font-sans ${isWarning ? 'bg-red-500/5 border-red-500/10' : 'bg-cyan-500/5 border-cyan-500/10'}`}>
                    <div className={`p-2 rounded-lg ${isWarning ? 'bg-red-500/20' : 'bg-cyan-500/20'}`}>
                      <Icon className={`w-5 h-5 ${isWarning ? 'text-red-400' : 'text-cyan-400'}`} />
                    </div>
                    <div>
                      <h5 className="text-white font-bold text-sm font-sans">
                        {reason.split(":")[0]}
                      </h5>
                      <p className="text-white/40 text-xs font-sans">
                        {reason.split(":").slice(1).join(":") || "Analysis checkpoint verified."}
                      </p>
                    </div>
                  </div>
                );
              }) : (
                 <div className="text-center py-8">
                    <p className="text-white/20 text-xs font-sans">No specific indicators found.</p>
                 </div>
              )}
            </div>

            <button className="w-full mt-6 py-3 rounded-xl bg-red-500 text-[#060b0d] font-black text-xs uppercase tracking-widest hover:bg-red-400 transition-all font-sans">
              Initiate Flagging Protocol
            </button>
          </div>
        </div>

        {/* Right Column: Viewport & Timeline */}
        <div className="col-span-8 space-y-8 font-sans">
          {/* Document Forensic Viewport */}
          <div className="bg-[#0b1619] border border-white/5 rounded-2xl p-6 font-sans shadow-2xl relative">
            <div className="flex items-center justify-between mb-6 font-sans">
              <div className="flex items-center gap-2 font-sans">
                <Layers className="w-4 h-4 text-cyan-400 font-sans" />
                <span className="text-white/40 text-xs font-bold uppercase tracking-widest font-sans">Document Forensic Viewport</span>
              </div>
              <div className="flex items-center gap-4 text-white/30 font-sans">
                <Search className="w-4 h-4 cursor-pointer hover:text-white transition-all font-sans" />
                <RotateCw className="w-4 h-4 cursor-pointer hover:text-white transition-all font-sans" />
                <Maximize2 className="w-4 h-4 cursor-pointer hover:text-white transition-all font-sans" />
              </div>
            </div>

            <div className="bg-[#122227] rounded-xl relative overflow-hidden aspect-[4/3] flex items-center justify-center p-8 font-sans">
              <div className="relative bg-white w-full h-full shadow-2xl border-4 border-[#1a3a44]/50 pointer-events-none font-sans overflow-hidden">
                {displayPreviewUrl ? (
                  <img src={displayPreviewUrl} className="w-full h-full object-contain mix-blend-multiply opacity-90 font-sans" />
                ) : (
                  <div className="p-12 space-y-4 font-sans">
                     <div className="h-4 bg-gray-200 w-3/4 rounded font-sans" />
                     <div className="h-4 bg-gray-200 w-1/2 rounded font-sans" />
                     {isHighRisk && (
                        <div className="h-24 bg-red-500/10 border-2 border-dashed border-red-500/40 rounded-lg flex items-center justify-center relative font-sans">
                           <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-2 py-0.5 bg-red-500 text-white text-[8px] font-black rounded uppercase font-sans">Manipulation Detected</span>
                        </div>
                     )}
                     <div className="h-4 bg-gray-200 w-full rounded font-sans" />
                     <div className="h-4 bg-gray-200 w-5/6 rounded font-sans" />
                     <div className="h-24 bg-gray-100 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center font-sans">
                        <span className="text-gray-400 text-[10px] uppercase font-bold font-sans">Signature Area</span>
                     </div>
                  </div>
                )}
              </div>
              
              {/* Scanline Effect Overlay */}
              <div className="absolute inset-0 pointer-events-none font-sans overflow-hidden">
                <div className="w-full h-1 bg-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.5)] absolute top-0 animate-[scan_4s_linear_infinite]" />
              </div>
            </div>
          </div>

          {/* Blockchain Audit Trail */}
          <div className="bg-[#0b1619] border border-white/5 rounded-2xl p-6 font-sans shadow-2xl">
            <div className="flex items-center gap-2 mb-6 font-sans">
              <ShieldAlert className="w-4 h-4 text-cyan-400 font-sans" />
              <span className="text-white/40 text-xs font-bold uppercase tracking-widest font-sans">Blockchain Audit Trail</span>
            </div>

            <div className="space-y-6 relative ml-2 font-sans">
               <div className="absolute left-[7px] top-2 bottom-2 w-[1px] bg-white/5 font-sans" />
               
               {audit_history.length > 0 ? audit_history.map((entry, idx) => {
                 const isRevoked = entry.event === "revoked";
                 const ts = entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleString() : "Unknown date";
                 
                 return (
                   <div key={idx} className="relative pl-8 font-sans">
                      <div className={`absolute left-0 top-1 w-4 h-4 rounded-full border-4 border-[#0b1619] ${isRevoked ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.4)]' : 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.4)]'} font-sans`} />
                      <div className="flex items-center justify-between font-sans">
                         <h6 className={`text-sm font-bold font-sans ${isRevoked ? 'text-red-500' : 'text-white'}`}>
                           {entry.event.replace(/_/g, " ").toUpperCase()}
                         </h6>
                         <span className="text-[10px] text-white/30 uppercase font-bold font-sans">{ts}</span>
                      </div>
                      <p className="text-[11px] text-cyan-400 font-mono mt-1 font-sans opacity-60 font-sans">
                        TX: {entry.tx_hash.slice(0, 16)}...
                      </p>
                      {entry.block_number && (
                        <p className="text-[10px] text-white/20 font-bold font-sans">Block {entry.block_number}</p>
                      )}
                   </div>
                 );
               }) : (
                 <div className="text-center py-4">
                   <p className="text-white/20 text-xs font-sans">No on-chain records found yet.</p>
                 </div>
               )}
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes scan {
          0% { top: -5%; }
          100% { top: 105%; }
        }
      `}</style>
    </div>
  );
}

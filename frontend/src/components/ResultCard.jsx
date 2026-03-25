/**
 * frontend/src/components/ResultCard.jsx
 */

const LABEL_CONFIG = {
  Authentic: {
    badge: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
    bar: 'bg-emerald-500',
    glow: 'shadow-emerald-500/20',
    icon: 'OK',
  },
  Suspicious: {
    badge: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
    bar: 'bg-amber-500',
    glow: 'shadow-amber-500/20',
    icon: 'WARN',
  },
  Forged: {
    badge: 'bg-red-500/15 text-red-400 border border-red-500/30',
    bar: 'bg-red-500',
    glow: 'shadow-red-500/20',
    icon: 'FORGED',
  },
}

function HashRow({ label, value }) {
  return (
    <div className="mt-4">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-1">{label}</p>
      <code className="block bg-white/5 border border-white/8 rounded-lg px-3 py-2 text-violet-300 text-xs font-mono break-all">
        {value}
      </code>
    </div>
  )
}

function ScoreBar({ label, score }) {
  const pct = (score * 100).toFixed(0)
  return (
    <div className="mb-3">
      <div className="flex justify-between text-xs text-white/50 mb-1">
        <span>{label}</span>
        <span className={score > 0.6 ? 'text-red-400' : score > 0.35 ? 'text-amber-400' : 'text-emerald-400'}>{pct}%</span>
      </div>
      <div className="h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            score > 0.6 ? 'bg-red-500' : score > 0.35 ? 'bg-amber-400' : 'bg-emerald-400'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function RegionOverlay({ previewUrl, forgery_regions }) {
  if (!previewUrl || !forgery_regions || forgery_regions.length === 0) return null

  return (
    <div className="mb-4 pt-4 border-t border-white/8">
      <p className="text-white/40 text-xs uppercase tracking-widest mb-3">Approximate Forgery Region</p>
      <div className="relative rounded-xl overflow-hidden border border-red-500/30">
        <img src={previewUrl} alt="Uploaded document" className="w-full h-auto block" />
        {forgery_regions.map((r, i) => (
          <div
            key={`${r.source || 'region'}-${i}`}
            className="absolute border-2 border-red-500 bg-red-500/10"
            style={{
              left: `${(r.x || 0) * 100}%`,
              top: `${(r.y || 0) * 100}%`,
              width: `${(r.w || 0) * 100}%`,
              height: `${(r.h || 0) * 100}%`,
            }}
            title={`${r.source || 'region'} (${Math.round((r.score || 0) * 100)}%)`}
          />
        ))}
      </div>
      <p className="text-white/50 text-xs mt-2">Red boxes are approximate suspicious areas (not pixel-perfect segmentation).</p>
    </div>
  )
}

export default function ResultCard({
  result,
  confidence,
  hash,
  cid,
  tx_hash,
  module_scores,
  explanation,
  reasons,
  suspected_forgery_type,
  forgery_regions,
  previewUrl,
}) {
  const cfg = LABEL_CONFIG[result] || LABEL_CONFIG.Suspicious
  const pct = (confidence * 100).toFixed(1)

  return (
    <div
      id="result-card"
      className={`
        bg-white/5 border border-white/10 rounded-2xl p-6
        shadow-2xl ${cfg.glow}
        animate-[fadeSlideUp_0.4s_ease_both]
      `}
      style={{ animation: 'fadeSlideUp 0.4s ease both' }}
      role="region"
      aria-label="Analysis result"
    >
      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(20px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <h2 className="text-lg font-bold text-white mb-5 flex items-center gap-2">Analysis Report</h2>

      <div className="flex items-center justify-between mb-4">
        <span className="text-white/50 text-sm">Classification</span>
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold ${cfg.badge}`}>
          {cfg.icon} {result}
        </span>
      </div>

      <div className="flex items-center justify-between mb-2">
        <span className="text-white/50 text-sm">Overall Confidence</span>
        <span className="text-white font-bold tabular-nums">{pct}%</span>
      </div>
      <div className="h-2 bg-white/10 rounded-full overflow-hidden mb-5">
        <div className={`h-full rounded-full transition-all duration-700 ${cfg.bar}`} style={{ width: `${pct}%` }} />
      </div>

      {(explanation || suspected_forgery_type || (reasons && reasons.length > 0)) && (
        <div className="mb-4 pt-4 border-t border-white/8">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3">Why This Result</p>
          {suspected_forgery_type && (
            <p className="text-sm text-fuchsia-300 mb-2">
              Suspected forgery type: <span className="font-semibold">{suspected_forgery_type}</span>
            </p>
          )}
          {explanation && <p className="text-sm text-white/70 mb-2">{explanation}</p>}
          {reasons && reasons.length > 0 && (
            <ul className="list-disc pl-5 space-y-1 text-sm text-white/70">
              {reasons.map((reason, idx) => (
                <li key={idx}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <RegionOverlay previewUrl={previewUrl} forgery_regions={forgery_regions} />

      {module_scores && Object.keys(module_scores).some((k) => module_scores[k] != null) && (
        <div className="mb-4 pt-4 border-t border-white/8">
          <p className="text-white/40 text-xs uppercase tracking-widest mb-3">Module Scores</p>
          {module_scores.ela != null && <ScoreBar label="Error Level Analysis (ELA)" score={module_scores.ela} />}
          {module_scores.copy_move != null && <ScoreBar label="Copy-Move Detection" score={module_scores.copy_move} />}
          {module_scores.nlp != null && <ScoreBar label="Text Anomaly (NLP)" score={module_scores.nlp} />}
        </div>
      )}

      <div className="pt-4 border-t border-white/8">
        <HashRow label="Document SHA-256" value={hash} />
        <HashRow label="IPFS CID" value={cid} />
        {tx_hash && <HashRow label="Blockchain TX" value={tx_hash} />}
      </div>
    </div>
  )
}

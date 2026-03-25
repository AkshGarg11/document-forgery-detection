import { useEffect, useMemo, useState } from 'react'
import FileUpload from '../components/FileUpload'
import ResultCard from '../components/ResultCard'
import { analyzeDocument } from '../services/api'

const STATUS = { IDLE: 'idle', LOADING: 'loading', SUCCESS: 'success', ERROR: 'error' }

export default function Home() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(STATUS.IDLE)
  const [result, setResult] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  const previewUrl = useMemo(() => {
    if (!file || !file.type?.startsWith('image/')) return null
    return URL.createObjectURL(file)
  }, [file])

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [previewUrl])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!file) return
    setStatus(STATUS.LOADING)
    setResult(null)
    setErrorMsg('')
    try {
      const data = await analyzeDocument(file)
      setResult(data)
      setStatus(STATUS.SUCCESS)
    } catch (err) {
      setErrorMsg(err.message || 'Analysis failed. Please try again.')
      setStatus(STATUS.ERROR)
    }
  }

  const isLoading = status === STATUS.LOADING

  return (
    <main className="max-w-2xl mx-auto px-4 py-16">
      <div className="text-center mb-12">
        <div className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-500/20 rounded-full px-4 py-1.5 text-violet-400 text-sm font-medium mb-6">
          <span className="w-2 h-2 rounded-full bg-violet-400 animate-pulse inline-block" />
          AI + Blockchain Verification
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold text-white leading-tight mb-4">
          Document{' '}
          <span className="bg-linear-to-r from-violet-400 via-fuchsia-400 to-cyan-400 bg-clip-text text-transparent">
            Forgery Detector
          </span>
        </h1>
        <p className="text-white/50 text-lg max-w-md mx-auto leading-relaxed">
          Upload any document - our AI pipeline detects tampering and writes a tamper-proof record to the blockchain.
        </p>
      </div>

      <form id="upload-form" onSubmit={handleSubmit} noValidate className="space-y-4">
        <FileUpload onFileSelect={setFile} />

        <button
          id="submit-btn"
          type="submit"
          disabled={!file || isLoading}
          aria-busy={isLoading}
          className={`
            w-full py-3.5 rounded-xl font-semibold text-white text-base
            transition-all duration-200
            ${
              !file || isLoading
                ? 'bg-white/10 text-white/30 cursor-not-allowed'
                : 'bg-linear-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 hover:-translate-y-0.5 shadow-lg shadow-violet-500/25'
            }
          `}
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Analyzing document...
            </span>
          ) : (
            'Analyze Document'
          )}
        </button>
      </form>

      {status === STATUS.ERROR && (
        <div role="alert" className="mt-4 flex items-start gap-3 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3 text-red-400 text-sm">
          <span className="text-base mt-0.5">!</span>
          <span>{errorMsg}</span>
        </div>
      )}

      {status === STATUS.SUCCESS && result && (
        <div className="mt-8">
          <ResultCard {...result} previewUrl={previewUrl} />
        </div>
      )}
    </main>
  )
}


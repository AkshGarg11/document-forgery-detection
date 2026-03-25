import { useState, useRef } from 'react'

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'application/pdf']
const MAX_MB = 10

export default function FileUpload({ onFileSelect }) {
  const [dragOver, setDragOver] = useState(false)
  const [selectedFile, setSelectedFile] = useState(null)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  const validate = (file) => {
    if (!ACCEPTED_TYPES.includes(file.type))
      return 'Only JPEG, PNG and PDF files are accepted.'
    if (file.size > MAX_MB * 1024 * 1024)
      return `File must be smaller than ${MAX_MB} MB.`
    return ''
  }

  const handleFile = (file) => {
    const err = validate(file)
    if (err) { setError(err); return }
    setError('')
    setSelectedFile(file)
    onFileSelect(file)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleChange = (e) => {
    const file = e.target.files[0]
    if (file) handleFile(file)
  }

  return (
    <div className="w-full">
      <div
        id="drop-zone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
        className={`
          relative flex flex-col items-center justify-center gap-3
          border-2 border-dashed rounded-2xl p-12 cursor-pointer
          transition-all duration-200 select-none
          ${dragOver
            ? 'border-violet-500 bg-violet-500/10'
            : 'border-white/10 bg-white/5 hover:border-violet-500/60 hover:bg-white/8'
          }
        `}
      >
        {/* Icon */}
        <div className="text-5xl">
          {selectedFile
            ? (selectedFile.type === 'application/pdf' ? '📕' : '🖼️')
            : '📂'}
        </div>

        {selectedFile ? (
          <div className="text-center">
            <p className="text-violet-300 font-semibold text-sm break-all">{selectedFile.name}</p>
            <p className="text-white/40 text-xs mt-1">{(selectedFile.size / 1024).toFixed(1)} KB • Click to change</p>
          </div>
        ) : (
          <div className="text-center">
            <p className="text-white/80 font-medium">Drag &amp; drop your document here</p>
            <p className="text-white/40 text-sm mt-1">
              or <span className="text-violet-400 font-semibold">browse files</span>
            </p>
            <p className="text-white/30 text-xs mt-3">JPEG · PNG · PDF &nbsp;—&nbsp; max {MAX_MB} MB</p>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-2 text-red-400 text-sm flex items-center gap-1">
          <span>⚠</span> {error}
        </p>
      )}

      <input
        ref={inputRef}
        id="file-input"
        type="file"
        accept={ACCEPTED_TYPES.join(',')}
        onChange={handleChange}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  )
}

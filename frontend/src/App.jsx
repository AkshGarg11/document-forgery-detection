import Home from './pages/Home'
import './index.css'

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0b14] text-white">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-white/8 bg-[#0a0b14]/80 backdrop-blur-xl">
        <div className="max-w-2xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-600 flex items-center justify-center text-sm">
            🔍
          </div>
          <span className="font-bold text-lg tracking-tight">ForgeGuard</span>
          <span className="ml-auto text-white/30 text-xs font-mono">v1.0.0</span>
        </div>
      </header>

      {/* Page */}
      <Home />

      {/* Footer */}
      <footer className="border-t border-white/8 py-6 text-center text-white/30 text-xs">
        ForgeGuard © {new Date().getFullYear()} — AI + Blockchain Document Verification
      </footer>
    </div>
  )
}

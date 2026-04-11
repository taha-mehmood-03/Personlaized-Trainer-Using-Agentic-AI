import { AlertTriangle, ExternalLink } from 'lucide-react'

// ─── Pure Server-renderable Component ──────────────────────────────────────
export function CrisisBanner() {
  return (
    <div className="w-full bg-red-600 text-white px-4 py-2.5 flex items-center justify-center gap-3 text-sm font-medium z-50 shrink-0">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>
        Feeling in crisis? Please reach out for immediate help. Call or text{' '}
        <strong>988</strong> anytime in the US &amp; Canada.
      </span>
      <a
        href="https://988lifeline.org/find-a-crisis-center/"
        target="_blank"
        rel="noopener noreferrer"
        className="underline font-bold flex items-center gap-1 hover:text-red-100 transition-colors whitespace-nowrap"
      >
        Find Local Resources
        <ExternalLink className="w-3.5 h-3.5" />
      </a>
    </div>
  )
}

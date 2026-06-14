import Link from 'next/link'
import { AlertTriangle, ExternalLink } from 'lucide-react'

export function CrisisBanner() {
  return (
    <div className="flex w-full shrink-0 items-center justify-center gap-2 bg-red-600 px-3 py-1.5 text-xs font-semibold text-white sm:gap-3 sm:px-4 sm:py-2.5 sm:text-sm">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span className="min-w-0 truncate">
        Crisis support: <strong>+92-311-7786264</strong>
      </span>
      <Link
        href="/crisis"
        prefetch={false}
        className="flex shrink-0 items-center gap-1 whitespace-nowrap font-bold underline transition-colors hover:text-red-100"
      >
        Open resources
        <ExternalLink className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}

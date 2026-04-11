import Link from 'next/link'
import { Button } from '@/components/ui/button'

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-slate-50 text-center p-4">
      <h2 className="text-4xl font-black text-slate-900 mb-2">404</h2>
      <p className="text-xl font-semibold text-slate-700 mb-2">Page Not Found</p>
      <p className="text-slate-500 mb-8 max-w-sm">The page you are looking for doesn&apos;t exist or has been moved.</p>
      <Button asChild variant="primary">
        <Link href="/">Return Home</Link>
      </Button>
    </div>
  )
}

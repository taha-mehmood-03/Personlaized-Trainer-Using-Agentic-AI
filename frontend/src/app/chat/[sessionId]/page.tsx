import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'

export const dynamic = 'force-dynamic'

export default async function ChatSessionPage() {
  const session = await getServerSession(authOptions)
  if (!session?.user?.id) redirect('/login')
  redirect('/chat')
}

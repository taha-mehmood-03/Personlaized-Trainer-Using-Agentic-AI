import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { ChatLayout } from '@/components/chat/ChatLayout'
import { CrisisBanner } from '@/components/crisis/CrisisBanner'

export const dynamic = 'force-dynamic'

export default async function ChatPage() {
  const session = await getServerSession(authOptions)

  if (!session?.user?.id) {
    redirect('/login')
  }

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-50">
      <CrisisBanner />
      <ChatLayout
        userId={session.user.id}
        userName={session.user.name}
        userEmail={session.user.email}
        initialSessions={[]}
        initialMessages={[]}
        initialSessionId={null}
      />
    </div>
  )
}

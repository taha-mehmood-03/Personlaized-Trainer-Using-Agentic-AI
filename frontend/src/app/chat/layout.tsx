import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { Message, Session } from '@/types'
import { ChatLayout } from '@/components/chat/ChatLayout'
import { getSessions, getLatestSession } from '@/actions/chat'

// Force dynamic rendering to ensure a fresh session is read on every request
export const dynamic = 'force-dynamic'

export default async function ChatPageLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getServerSession(authOptions)

  // Redirect unauthenticated users to login
  if (!session?.user?.id) {
    redirect('/login')
  }

  const currentUserId = session.user.id

  // Server-side fetch initial data using the real authenticated user ID
  const [sessions, latest] = await Promise.all([
    getSessions(currentUserId),
    getLatestSession(currentUserId),
  ])

  return (
    <ChatLayout
      userId={currentUserId}
      initialSessions={sessions}
      initialMessages={latest.messages}
      initialSessionId={latest.sessionId}
    >
      {/* 
        This is where Next.js pushes /chat/page.tsx or /chat/[sessionId]/page.tsx
        ChatLayout manages local state to prevent hard reloads on SSE streams.
      */}
      {children}
    </ChatLayout>
  )
}

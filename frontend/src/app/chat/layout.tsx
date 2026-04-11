import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { Session, Message } from '@/types'
import { ChatLayout } from '@/components/chat/ChatLayout'
import { getSessions, getLatestSession } from '@/actions/chat'

// Force dynamic rendering to ensure fresh cookies are read
export const dynamic = 'force-dynamic'

export default async function ChatPageLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const cookieStore = cookies()
  const userId = cookieStore.get('sentimind_user_id')?.value

  // For testing, fallback to anonymous if no cookie
  const currentUserId = userId || 'anonymous'

  // Server-side fetch initial data
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
        But since ChatLayout manages local state right now to prevent hard reloads
        on SSE streams, we pass children primarily for Next.js routing structure.
      */}
      {children}
    </ChatLayout>
  )
}

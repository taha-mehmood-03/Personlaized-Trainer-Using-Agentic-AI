import { notFound, redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { getSessionMessages, getSessions } from '@/actions/chat'
import { ChatLayout } from '@/components/chat/ChatLayout'

export const dynamic = 'force-dynamic'

interface ChatSessionPageProps {
  params: {
    sessionId: string
  }
}

export default async function ChatSessionPage({ params }: ChatSessionPageProps) {
  const session = await getServerSession(authOptions)

  if (!session?.user?.id) {
    redirect('/login')
  }

  const [sessions, messages] = await Promise.all([
    getSessions(session.user.id),
    getSessionMessages(params.sessionId, session.user.id),
  ])
  const activeSession = sessions.find((item) => item.id === params.sessionId)

  if (!activeSession && messages.length === 0) {
    notFound()
  }

  return (
    <ChatLayout
      userId={session.user.id}
      userName={session.user.name}
      userEmail={session.user.email}
      initialSessions={sessions}
      initialMessages={messages}
      initialSessionId={params.sessionId}
    />
  )
}

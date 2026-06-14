import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { ProfileClient } from '@/components/profile/ProfileClient'

export const dynamic = 'force-dynamic'

export default async function ProfilePage() {
    const session = await getServerSession(authOptions)

    if (!session?.user?.id) {
        redirect('/login')
    }

    return (
        <ProfileClient
            userId={session.user.id}
            profile={null}
            fallbackName={session.user.name}
            fallbackEmail={session.user.email}
        />
    )
}

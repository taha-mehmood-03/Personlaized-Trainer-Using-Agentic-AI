import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { OnboardingClient } from '@/components/onboarding/OnboardingClient'

export const dynamic = 'force-dynamic'

export default async function OnboardingPage() {
    const session = await getServerSession(authOptions)

    if (!session?.user?.id) {
        redirect('/login')
    }

    return <OnboardingClient userId={session.user.id} />
}

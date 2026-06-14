import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { SignupClient } from '@/components/auth/SignupClient'

export const dynamic = 'force-dynamic'

export default async function SignupPage() {
    const session = await getServerSession(authOptions)

    if (session?.user?.id) {
        redirect('/onboarding')
    }

    return <SignupClient />
}

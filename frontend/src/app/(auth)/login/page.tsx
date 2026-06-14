import { redirect } from 'next/navigation'
import { getServerSession } from 'next-auth'
import { authOptions } from '@/lib/auth'
import { LoginClient } from '@/components/auth/LoginClient'

export const dynamic = 'force-dynamic'

export default async function LoginPage() {
    const session = await getServerSession(authOptions)

    if (session?.user?.id) {
        redirect('/dashboard')
    }

    return <LoginClient />
}

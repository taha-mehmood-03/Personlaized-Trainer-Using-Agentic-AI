import { CrisisPageClient } from '@/components/crisis/CrisisPageClient'
import { DEFAULT_CRISIS_COUNTRY, PAKISTAN_CRISIS_RESOURCES } from '@/lib/crisisResources'

export const dynamic = 'force-static'

export const metadata = {
    title: 'Crisis Resources - SentiMind',
    description: 'Immediate Pakistan crisis and emergency support resources.',
}

export default function CrisisPage() {
    return (
        <CrisisPageClient
            resources={PAKISTAN_CRISIS_RESOURCES}
            countryCode={DEFAULT_CRISIS_COUNTRY}
            initialError={null}
        />
    )
}

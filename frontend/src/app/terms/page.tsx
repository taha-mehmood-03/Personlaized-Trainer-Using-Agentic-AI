import Link from 'next/link'
import { FileText, ArrowLeft } from 'lucide-react'

export const metadata = {
    title: 'Terms of Service — SentiMind',
    description: 'The terms and conditions governing your use of the SentiMind mental wellness application.',
}

const TERMS_VERSION = '2026-05-24'
const CONTACT_EMAIL = 'legal@sentimind.example'

export default function TermsPage() {
    return (
        <main className="min-h-screen bg-slate-50 py-12 px-4">
            <div className="mx-auto max-w-3xl">
                <div className="mb-8 flex items-center gap-3">
                    <Link
                        href="/"
                        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 shadow-sm hover:bg-slate-50"
                    >
                        <ArrowLeft className="h-3.5 w-3.5" />
                        Back to SentiMind
                    </Link>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
                    <div className="mb-8 flex items-center gap-3">
                        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-950 text-white">
                            <FileText className="h-6 w-6" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-slate-950">Terms of Service</h1>
                            <p className="text-sm text-slate-500">
                                Version {TERMS_VERSION} — Effective {TERMS_VERSION}
                            </p>
                        </div>
                    </div>

                    <div className="space-y-8 text-sm leading-7 text-slate-700">
                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">1. Acceptance of Terms</h2>
                            <p>
                                By creating an account or using SentiMind, you agree to these Terms of Service and our{' '}
                                <Link href="/privacy" className="font-semibold text-slate-900 underline">
                                    Privacy Policy
                                </Link>
                                . If you do not agree, please do not use the service.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">2. Description of Service</h2>
                            <p>
                                SentiMind is a <strong>wellness support tool</strong> powered by AI. It provides conversational
                                emotional support, mood tracking, personalized coping techniques, and crisis safety routing.
                                It is <strong>not a licensed medical service</strong>, clinical therapy, or emergency response system.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">3. Not a Medical Device</h2>
                            <div className="rounded-xl border border-amber-100 bg-amber-50 p-4">
                                <p className="font-semibold text-amber-900">
                                    ⚠ Important Medical Disclaimer
                                </p>
                                <p className="mt-2 text-amber-800">
                                    SentiMind is not a substitute for professional mental health care, psychiatric medication
                                    management, or emergency medical services. If you are experiencing a mental health emergency,
                                    please call your local emergency services (e.g., 911 in the US, 1122 in Pakistan) or go to
                                    your nearest emergency room immediately.
                                </p>
                            </div>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">4. Eligibility</h2>
                            <p>
                                You must be at least <strong>16 years old</strong> (or the minimum age of digital consent in your
                                jurisdiction) to use SentiMind. By using the service, you represent that you meet this requirement.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">5. Your Account</h2>
                            <ul className="ml-4 list-disc space-y-2">
                                <li>You are responsible for maintaining the confidentiality of your account credentials.</li>
                                <li>You must provide accurate information at registration.</li>
                                <li>You may not share your account with another person.</li>
                                <li>
                                    You may delete your account at any time from your{' '}
                                    <Link href="/profile" className="font-semibold text-slate-900 underline">
                                        Profile settings
                                    </Link>
                                    . Deletion triggers a GDPR Art. 17 erasure request.
                                </li>
                            </ul>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">6. Data Processing &amp; Consent</h2>
                            <p>
                                You grant SentiMind permission to process your wellness data (conversations, mood logs,
                                wellness signals) to provide and improve the service. You may withdraw specific consents at any
                                time from Profile → Settings. See our{' '}
                                <Link href="/privacy" className="font-semibold text-slate-900 underline">
                                    Privacy Policy
                                </Link>{' '}
                                for full details on data handling.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">7. Crisis Safety Features</h2>
                            <p>
                                SentiMind includes automated crisis detection and safety routing. If crisis language is detected:
                            </p>
                            <ul className="ml-4 mt-2 list-disc space-y-2">
                                <li>The agent will provide emergency resources and hotline numbers.</li>
                                <li>
                                    If you granted crisis location consent during onboarding, SentiMind may transmit your
                                    approximate location to your pre-registered emergency contacts via Twilio.
                                </li>
                                <li>A pseudonymised crisis log is retained for safety documentation purposes.</li>
                            </ul>
                            <p className="mt-3">
                                These features operate under the GDPR vital interests legal basis (Art. 6(1)(d)) and your
                                explicit consent where required.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">8. Prohibited Uses</h2>
                            <p>You agree not to:</p>
                            <ul className="ml-4 mt-2 list-disc space-y-2">
                                <li>Use the service to harm yourself or others.</li>
                                <li>Attempt to reverse engineer or extract model weights.</li>
                                <li>Use automated scripts to abuse the API at scale.</li>
                                <li>Provide false information that could compromise crisis safety responses.</li>
                                <li>Share another person&apos;s data through the service without their consent.</li>
                            </ul>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">9. Limitation of Liability</h2>
                            <p>
                                SentiMind is provided &quot;as is&quot;. To the fullest extent permitted by law, we are not liable
                                for any indirect, incidental, or consequential damages arising from your use of the service,
                                including but not limited to decisions made based on AI-generated wellness content.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">10. Changes to Terms</h2>
                            <p>
                                We may update these terms. Material changes will be communicated with at least 30 days notice
                                and, where required, a fresh consent prompt before you continue using the service.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">11. Contact</h2>
                            <p>
                                For questions about these terms, contact us at{' '}
                                <a href={`mailto:${CONTACT_EMAIL}`} className="font-semibold text-slate-900 underline">
                                    {CONTACT_EMAIL}
                                </a>
                                .
                            </p>
                        </section>

                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
                            Terms version: {TERMS_VERSION} — Contact:{' '}
                            <a href={`mailto:${CONTACT_EMAIL}`} className="underline">{CONTACT_EMAIL}</a>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    )
}

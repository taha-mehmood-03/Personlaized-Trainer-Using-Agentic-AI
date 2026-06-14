import Link from 'next/link'
import { ShieldCheck, ArrowLeft } from 'lucide-react'

export const metadata = {
    title: 'Privacy Policy — SentiMind',
    description: 'How SentiMind collects, uses, and protects your personal mental health data in compliance with GDPR and HIPAA.',
}

const POLICY_VERSION = '2026-05-24'
const CONTACT_EMAIL = 'privacy@sentimind.example'

export default function PrivacyPage() {
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
                            <ShieldCheck className="h-6 w-6" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-black text-slate-950">Privacy Policy</h1>
                            <p className="text-sm text-slate-500">
                                Version {POLICY_VERSION} — Effective {POLICY_VERSION}
                            </p>
                        </div>
                    </div>

                    <div className="space-y-8 text-sm leading-7 text-slate-700">
                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">1. Who We Are</h2>
                            <p>
                                SentiMind is a personalized mental wellness support application. In this policy,
                                &quot;we&quot;, &quot;our&quot;, and &quot;SentiMind&quot; refer to the service and its operators.
                                We act as the <strong>data controller</strong> for your personal data.
                                Contact us at{' '}
                                <a href={`mailto:${CONTACT_EMAIL}`} className="font-semibold text-slate-900 underline">
                                    {CONTACT_EMAIL}
                                </a>{' '}
                                for any privacy-related enquiries.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">2. Data We Collect</h2>
                            <ul className="ml-4 list-disc space-y-2">
                                <li>
                                    <strong>Account data</strong> — your name, email address, and hashed password.
                                </li>
                                <li>
                                    <strong>Conversation data</strong> — messages exchanged with SentiMind, including
                                    detected emotions, intensity, and wellness assessment signals. Classified as{' '}
                                    <strong>SENSITIVE</strong> or <strong>PHI</strong>.
                                </li>
                                <li>
                                    <strong>Mood logs</strong> — daily check-in data and mood ratings.
                                </li>
                                <li>
                                    <strong>Technique outcomes</strong> — which wellness exercises you tried and how effective they were.
                                </li>
                                <li>
                                    <strong>Crisis data</strong> — if crisis language is detected, the message, risk level, and
                                    action taken are logged as <strong>PHI</strong>.
                                </li>
                                <li>
                                    <strong>Location (optional, crisis only)</strong> — only if you explicitly grant location access
                                    during onboarding, and only transmitted to your pre-approved emergency contacts during a detected crisis.
                                </li>
                                <li>
                                    <strong>Voice analysis (optional)</strong> — if you enable voice input, acoustic features
                                    are analysed to detect emotional state. Raw audio is not stored.
                                </li>
                                <li>
                                    <strong>Emergency contacts (optional)</strong> — names and phone numbers you provide, only
                                    used for crisis alerts with your explicit consent.
                                </li>
                                <li>
                                    <strong>Usage metadata</strong> — pseudonymised IP hashes and user agent hashes stored in
                                    audit logs. We never store your raw IP address.
                                </li>
                            </ul>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">3. Legal Basis for Processing (GDPR Art. 6 &amp; 9)</h2>
                            <div className="overflow-x-auto">
                                <table className="w-full border-collapse text-xs">
                                    <thead>
                                        <tr className="border-b border-slate-200 bg-slate-50">
                                            <th className="py-2 pr-4 text-left font-bold text-slate-700">Purpose</th>
                                            <th className="py-2 pr-4 text-left font-bold text-slate-700">Data Category</th>
                                            <th className="py-2 text-left font-bold text-slate-700">Legal Basis</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-slate-100">
                                        <tr>
                                            <td className="py-2 pr-4">Account creation &amp; authentication</td>
                                            <td className="py-2 pr-4">Email, name, password hash</td>
                                            <td className="py-2">Contract (Art. 6(1)(b))</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 pr-4">Wellness chat &amp; emotion tracking</td>
                                            <td className="py-2 pr-4">Conversation, mood, wellness signals</td>
                                            <td className="py-2">Explicit Consent (Art. 9(2)(a))</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 pr-4">Personalization &amp; memory</td>
                                            <td className="py-2 pr-4">Facts, preferences, history</td>
                                            <td className="py-2">Consent (Art. 6(1)(a))</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 pr-4">Crisis safety alerts</td>
                                            <td className="py-2 pr-4">Crisis log, location, contacts</td>
                                            <td className="py-2">Vital interests (Art. 6(1)(d)) + Consent</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 pr-4">Voice tone analysis</td>
                                            <td className="py-2 pr-4">Acoustic features</td>
                                            <td className="py-2">Explicit Consent (Art. 9(2)(a))</td>
                                        </tr>
                                        <tr>
                                            <td className="py-2 pr-4">Security &amp; audit logging</td>
                                            <td className="py-2 pr-4">Pseudonymised IDs &amp; hashes</td>
                                            <td className="py-2">Legal obligation (Art. 6(1)(c))</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">4. Data Retention</h2>
                            <p>
                                Data is retained for a maximum of <strong>365 days</strong> by default, configurable per account.
                                PHI data (crisis logs and wellness assessments) follows stricter minimum retention for safety
                                documentation, then is deleted. You can request immediate erasure at any time.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">5. Data Sharing &amp; Third Parties</h2>
                            <ul className="ml-4 list-disc space-y-2">
                                <li>
                                    <strong>Supabase (PostgreSQL)</strong> — hosted database provider for all structured data.
                                </li>
                                <li>
                                    <strong>Twilio</strong> — used only for crisis SMS/WhatsApp alerts with your explicit consent.
                                </li>
                                <li>
                                    <strong>Google Gemini / OpenRouter (LLM)</strong> — your messages are sent to an AI model to generate
                                    therapeutic responses. No personally identifiable data is included beyond the conversation context.
                                </li>
                                <li>
                                    <strong>ip-api.com</strong> — used as a fallback for city-level location detection during crisis events
                                    only when GPS is unavailable. This transfers your IP address to a third-party service.
                                </li>
                                <li>We do <strong>not</strong> sell your data to any third party.</li>
                            </ul>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">6. Your Rights (GDPR Art. 15–22)</h2>
                            <ul className="ml-4 list-disc space-y-2">
                                <li><strong>Access</strong> — request a copy of all data we hold about you.</li>
                                <li><strong>Rectification</strong> — correct inaccurate personal data.</li>
                                <li><strong>Erasure</strong> — delete your account and all associated data (&quot;right to be forgotten&quot;).</li>
                                <li><strong>Restriction</strong> — limit how we process your data.</li>
                                <li><strong>Portability</strong> — export your data in a machine-readable format.</li>
                                <li><strong>Objection</strong> — object to processing based on legitimate interests.</li>
                                <li><strong>Withdraw consent</strong> — at any time, from your Profile → Settings.</li>
                            </ul>
                            <p className="mt-3">
                                To exercise these rights, visit your{' '}
                                <Link href="/profile" className="font-semibold text-slate-900 underline">
                                    Profile settings
                                </Link>{' '}
                                or email{' '}
                                <a href={`mailto:${CONTACT_EMAIL}`} className="font-semibold text-slate-900 underline">
                                    {CONTACT_EMAIL}
                                </a>
                                . We respond within <strong>30 days</strong>.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">7. Security (HIPAA § 164.312)</h2>
                            <ul className="ml-4 list-disc space-y-2">
                                <li>All data is encrypted in transit (TLS) and at rest (AES-256 via Supabase).</li>
                                <li>Passwords are stored as bcrypt hashes — never in plain text.</li>
                                <li>Audit logs track all data access using pseudonymised identifiers.</li>
                                <li>Security headers (CSP, HSTS, X-Frame-Options) are enforced on all API routes.</li>
                                <li>IP addresses and user agents in logs are stored as one-way HMAC hashes only.</li>
                            </ul>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">8. Not a Medical Service</h2>
                            <p>
                                SentiMind is a <strong>wellness support tool</strong>, not a licensed medical device or clinical
                                service. It is not a substitute for professional mental health care. In a medical emergency, please
                                call your local emergency services.
                            </p>
                        </section>

                        <section>
                            <h2 className="mb-3 text-base font-black text-slate-900">9. Changes to This Policy</h2>
                            <p>
                                We will notify you of material changes by updating the version date above and, where required,
                                by requesting fresh consent before you continue using the service.
                            </p>
                        </section>

                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
                            Policy version: {POLICY_VERSION} — Contact:{' '}
                            <a href={`mailto:${CONTACT_EMAIL}`} className="underline">{CONTACT_EMAIL}</a>
                        </div>
                    </div>
                </div>
            </div>
        </main>
    )
}

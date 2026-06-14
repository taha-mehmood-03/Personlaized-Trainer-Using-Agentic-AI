'use client'

import React, { useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface DangerZoneProps {
    onDeleteAccount: () => Promise<void>
}

/** GDPR erasure request confirmation section. */
export const DangerZone = ({ onDeleteAccount }: DangerZoneProps) => {
    const [confirming, setConfirming] = useState(false)
    const [loading, setLoading] = useState(false)

    const handleDelete = async () => {
        setLoading(true)
        await onDeleteAccount()
        setLoading(false)
        setConfirming(false)
    }

    return (
        <div className="border border-red-200 rounded-2xl p-5 bg-red-50/50">
            <div className="flex items-start gap-3 mb-4">
                <AlertTriangle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
                <div>
                    <h3 className="text-sm font-bold text-red-700">Danger Zone</h3>
                    <p className="text-xs text-red-600 mt-1 leading-relaxed">
                        Submit a GDPR erasure request, revoke consent, and sign out. Your account is
                        marked for deletion and removed according to the retention policy.
                    </p>
                </div>
            </div>

            {!confirming ? (
                <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setConfirming(true)}
                >
                    Request Account Erasure
                </Button>
            ) : (
                <div className="flex items-center gap-3">
                    <Button
                        variant="destructive"
                        size="sm"
                        onClick={handleDelete}
                        disabled={loading}
                    >
                        {loading ? 'Submitting...' : 'Yes, request erasure'}
                    </Button>
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setConfirming(false)}
                        disabled={loading}
                    >
                        Cancel
                    </Button>
                </div>
            )}
        </div>
    )
}

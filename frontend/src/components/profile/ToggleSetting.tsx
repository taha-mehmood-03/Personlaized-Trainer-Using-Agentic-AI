'use client'

import React from 'react'

interface ToggleSettingProps {
    label: string
    description?: string
    checked: boolean
    onChange: (val: boolean) => void
    disabled?: boolean
}

/** Row with a label/description on the left and an animated toggle switch on the right. */
export const ToggleSetting = ({
    label,
    description,
    checked,
    onChange,
    disabled = false,
}: ToggleSettingProps) => {
    return (
        <div className="flex items-center justify-between py-3 border-b border-slate-50 last:border-0">
            <div className="flex-1 pr-4">
                <p className="text-sm font-semibold text-slate-800">{label}</p>
                {description && (
                    <p className="text-xs text-slate-400 mt-0.5">{description}</p>
                )}
            </div>
            <button
                role="switch"
                aria-checked={checked}
                disabled={disabled}
                onClick={() => onChange(!checked)}
                className={`
                    relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full
                    transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-cyan-400
                    focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed
                    ${checked ? 'bg-cyan-700' : 'bg-slate-200'}
                `}
            >
                <span
                    className={`
                        inline-block h-4 w-4 transform rounded-full bg-white shadow-md
                        transition-transform duration-200
                        ${checked ? 'translate-x-6' : 'translate-x-1'}
                    `}
                />
            </button>
        </div>
    )
}

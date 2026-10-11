// components/VialVolumeField.tsx — starting-volume entry tied to the antibody master.
//
// When the antibody has a standard vial volume, the field shows it locked. A
// different volume can only be entered by choosing "Different volume" AND giving a
// reason (the backend enforces the same rule). Without a standard volume the field
// is a plain required number input.
//
// Value convention: '' = use the standard volume.
// Key this component by antibody id so switching antibody resets the override.

import { useState } from 'react'
import { Input } from './ui'

const TOLERANCE_UL = 0.5

export function isNonStandard(standard: number | null | undefined, value: string): boolean {
  if (standard == null || value.trim() === '') return false
  const n = Number(value)
  return Number.isFinite(n) && Math.abs(n - standard) > TOLERANCE_UL
}

/** True when the volume + reason combination will be accepted by the backend. */
export function vialVolumeValid(standard: number | null | undefined, value: string, reason: string): boolean {
  if (standard == null) return value.trim() !== '' && Number(value) > 0
  if (value.trim() === '') return true
  if (!(Number(value) > 0)) return false
  return !isNonStandard(standard, value) || reason.trim() !== ''
}

/** Payload fields for the API: volume omitted when the standard applies. */
export function vialVolumePayload(standard: number | null | undefined, value: string, reason: string) {
  if (standard != null && !isNonStandard(standard, value)) return { volume: standard, reason: undefined }
  return { volume: value.trim() === '' ? undefined : Number(value), reason: reason.trim() || undefined }
}

export default function VialVolumeField({
  standard, catalogNo, value, onChange, reason, onReasonChange, label = 'Vial volume (µl)',
}: {
  standard: number | null | undefined
  catalogNo?: string | null
  value: string
  onChange: (v: string) => void
  reason: string
  onReasonChange: (v: string) => void
  label?: string
}) {
  const [override, setOverride] = useState(isNonStandard(standard, value))

  if (standard == null) {
    return (
      <div>
        <Input label={label} type="number" min="1" value={value} onChange={(e) => onChange(e.target.value)} />
        <p className="text-xs text-amber-700 mt-1">
          No standard vial volume in the antibody master. Set it there so this can't be mistyped.
        </p>
      </div>
    )
  }

  if (!override) {
    return (
      <div>
        <p className="block text-sm font-medium text-slate-700 mb-1">{label}</p>
        <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg border border-slate-200 bg-slate-50">
          <span className="text-sm text-slate-800">
            <span className="font-semibold tabular-nums">{standard} µl</span>
            <span className="text-slate-500"> · standard{catalogNo ? ` for cat. ${catalogNo}` : ''}</span>
          </span>
          <button
            type="button"
            className="text-xs text-slate-500 hover:text-brand-700 underline underline-offset-2"
            onClick={() => { setOverride(true); onChange(String(standard)) }}
          >
            Different volume?
          </button>
        </div>
      </div>
    )
  }

  const nonStandard = isNonStandard(standard, value)
  return (
    <div className="space-y-2 rounded-lg border border-amber-300 bg-amber-50/50 p-3">
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Input label={label} type="number" min="1" value={value} onChange={(e) => onChange(e.target.value)} />
        </div>
        <button
          type="button"
          className="text-xs text-slate-500 hover:text-brand-700 underline underline-offset-2 pb-2.5"
          onClick={() => { setOverride(false); onChange(''); onReasonChange('') }}
        >
          Use standard ({standard} µl)
        </button>
      </div>
      {nonStandard && (
        <Input
          label="Reason for the different volume (required)"
          value={reason}
          onChange={(e) => onReasonChange(e.target.value)}
          placeholder="e.g. vendor changed fill size — label reads 125 µl"
        />
      )}
      <p className="text-xs text-amber-800">
        A wrong starting volume skews every forecast for this lot. Only change it if the vial label differs.
      </p>
    </div>
  )
}

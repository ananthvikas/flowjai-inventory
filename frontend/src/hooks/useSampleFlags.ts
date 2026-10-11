// hooks/useSampleFlags.ts — the tap-to-toggle sample flags, from the backend
// (single source: backend/app/services/sample_flags.py).

import { useQuery } from '@tanstack/react-query'
import { sampleOrdersApi } from '../api/client'
import type { SampleFlagOption } from '../types'

export function useSampleFlags(): { options: SampleFlagOption[]; label: (code: string) => string } {
  const { data: options = [] } = useQuery({
    queryKey: ['sample-flag-options'],
    queryFn: sampleOrdersApi.sampleFlagOptions,
    staleTime: Infinity,
  })
  const label = (code: string) => options.find((o) => o.code === code)?.label ?? code
  return { options, label }
}

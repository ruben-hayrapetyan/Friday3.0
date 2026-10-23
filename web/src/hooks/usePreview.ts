// A command's full preview (a warm solve, about a second), asked again 400 ms after its input stops changing.

import { keepPreviousData, useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { type CommandInput, type CommandName, command } from "@/api/client"

function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), ms)
    return () => clearTimeout(timer)
  }, [value, ms])
  return settled
}

export function usePreview<N extends CommandName>(name: N, input: CommandInput<N> | null) {
  const settled = useSettled(input, 400)
  const key = JSON.stringify(settled)
  const preview = useQuery({
    queryKey: ["preview", name, key],
    queryFn: () => command(name, settled as CommandInput<N>, { preview: "full" }),
    enabled: settled !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
  })
  const busy = preview.isFetching || JSON.stringify(input) !== key
  return { changes: preview.data?.changes, error: preview.error, busy }
}

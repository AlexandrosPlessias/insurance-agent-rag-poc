import { useEffect, useRef, useState } from "react";
import { getPlanStatus } from "../api/client";
import type { PlanStatus } from "../api/types";

export function usePlanPolling(
  planId: string | null,
  intervalMs = 5000
): PlanStatus | null {
  const [status, setStatus] = useState<PlanStatus | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!planId) {
      setStatus(null);
      return;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const s = await getPlanStatus(planId);
        if (!cancelled) setStatus(s);
      } catch {
        // ignore transient errors
      }
    };

    poll();
    timerRef.current = setInterval(poll, intervalMs);

    return () => {
      cancelled = true;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [planId, intervalMs]);

  return status;
}

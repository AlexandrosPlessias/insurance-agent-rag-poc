import { useEffect, useState } from "react";

export function useCountdown(expiresAt: string | null): string {
  const [label, setLabel] = useState("");

  useEffect(() => {
    if (!expiresAt) return;

    const tick = () => {
      const diffMs = new Date(expiresAt).getTime() - Date.now();
      if (diffMs <= 0) {
        setLabel("Expired");
        return;
      }
      const totalSec = Math.floor(diffMs / 1000);
      const mins = Math.floor(totalSec / 60);
      const secs = totalSec % 60;
      setLabel(`${mins} min ${String(secs).padStart(2, "0")} s left`);
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [expiresAt]);

  return label;
}

import { useEffect, useRef, useState } from "react";
import { synthesizeSpeech } from "../api/client";

interface Props {
  text: string;
  language?: string;
}

type PlayerState = "idle" | "loading" | "ready" | "error";

export function AudioPlayer({ text, language = "en" }: Props) {
  const [playerState, setPlayerState] = useState<PlayerState>("idle");
  const [isPlaying, setIsPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onPlay  = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    const onEnded = () => setIsPlaying(false);
    el.addEventListener("play",  onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("play",  onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  const handleStop = () => {
    if (!audioRef.current) return;
    audioRef.current.pause();
    audioRef.current.currentTime = 0;
  };

  const handlePlay = async () => {
    if (playerState === "loading") return;

    // Already loaded — just play
    if (playerState === "ready" && audioRef.current) {
      void audioRef.current.play();
      return;
    }

    setPlayerState("loading");
    try {
      const blob = await synthesizeSpeech(text, language);
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = objectUrlRef.current;
        audioRef.current.load();
        setPlayerState("ready");
        void audioRef.current.play();
      }
    } catch {
      setPlayerState("error");
    }
  };

  if (isPlaying) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
        <button
          onClick={handleStop}
          title="Stop playback"
          style={{
            display: "flex", alignItems: "center", gap: 5,
            background: "#fff1f2",
            border: "1px solid #fecdd3",
            borderRadius: 8,
            padding: "3px 10px",
            cursor: "pointer",
            fontSize: 11, color: "#e11d48", fontWeight: 600,
            transition: "background .15s",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#ffe4e6"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#fff1f2"; }}
        >
          <span>⏹</span>
          <span>Stop</span>
        </button>
        <audio ref={audioRef} style={{ display: "none" }} />
      </div>
    );
  }

  const label =
    playerState === "loading" ? "⏳"
    : playerState === "error"  ? "⚠️"
    : "🔊";

  const title =
    playerState === "loading" ? "Synthesizing…"
    : playerState === "error"  ? "TTS failed — is VOICE_ENABLED=true?"
    : playerState === "ready"  ? "Play again"
    : "Listen to this response";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
      <button
        onClick={() => void handlePlay()}
        disabled={playerState === "loading"}
        title={title}
        style={{
          display: "flex", alignItems: "center", gap: 5,
          background: "#f4f4f5",
          border: "1px solid var(--border)",
          borderRadius: 8,
          padding: "3px 10px",
          cursor: playerState === "loading" ? "not-allowed" : "pointer",
          fontSize: 11, color: "var(--text-muted)", fontWeight: 600,
          transition: "background .15s",
        }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#e4e4e7"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "#f4f4f5"; }}
      >
        <span>{label}</span>
        <span>Listen</span>
      </button>
      <audio ref={audioRef} style={{ display: "none" }} />
    </div>
  );
}

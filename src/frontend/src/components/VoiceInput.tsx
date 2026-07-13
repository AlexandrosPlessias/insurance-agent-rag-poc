import { useRef, useState } from "react";
import { transcribeAudio } from "../api/client";

export type VoiceLanguage = "en" | "el";

interface Props {
  voiceEnabled: boolean;
  disabled: boolean;
  language: VoiceLanguage;
  onLanguageChange: (lang: VoiceLanguage) => void;
  onTranscript: (text: string) => void;
}

type RecordState = "idle" | "recording" | "processing";

const LANG_LABEL: Record<VoiceLanguage, string> = { en: "EN", el: "ΕΛ" };

export function VoiceInput({ voiceEnabled, disabled, language, onLanguageChange, onTranscript }: Props) {
  const [recordState, setRecordState] = useState<RecordState>("idle");
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  if (!voiceEnabled) return null;

  const isSupported = Boolean(navigator.mediaDevices?.getUserMedia);

  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecordState("processing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const result = await transcribeAudio(blob, language);
          if (result.transcript.trim()) onTranscript(result.transcript.trim());
        } catch {
          setError("Transcription failed — check server logs");
        } finally {
          setRecordState("idle");
        }
      };

      recorder.start();
      setRecordState("recording");
    } catch {
      setError("Microphone access denied");
      setRecordState("idle");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
  };

  const handleMicClick = () => {
    if (recordState === "idle") void startRecording();
    else if (recordState === "recording") stopRecording();
  };

  const toggleLanguage = () => {
    onLanguageChange(language === "en" ? "el" : "en");
  };

  const isRecording = recordState === "recording";
  const isProcessing = recordState === "processing";
  const isMicDisabled = disabled || isProcessing || !isSupported;

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2, flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
        {/* Language toggle */}
        <button
          onClick={toggleLanguage}
          disabled={isRecording || isProcessing}
          title={`Switch to ${language === "en" ? "Greek" : "English"}`}
          style={{
            fontSize: 9, fontWeight: 700,
            color: "#71717a",
            background: "none", border: "1px solid #e4e4e7",
            borderRadius: 4, padding: "2px 5px",
            cursor: isRecording || isProcessing ? "not-allowed" : "pointer",
            lineHeight: 1.4,
          }}
        >
          {LANG_LABEL[language]}
        </button>

        {/* Mic button */}
        <button
          onClick={handleMicClick}
          disabled={isMicDisabled}
          title={
            !isSupported
              ? "Microphone not supported in this browser"
              : isRecording
              ? "Stop recording"
              : isProcessing
              ? "Transcribing…"
              : "Record voice input"
          }
          style={{
            width: 34, height: 34,
            borderRadius: "50%",
            border: `2px solid ${isRecording ? "#e11d48" : "transparent"}`,
            background: isRecording ? "rgba(225,29,72,.1)" : "none",
            cursor: isMicDisabled ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: isRecording ? "#e11d48" : isMicDisabled ? "#d4d4d8" : "#71717a",
            fontSize: 18,
            transition: "all .2s",
            boxShadow: isRecording ? "0 0 0 4px rgba(225,29,72,.15)" : "none",
            animation: isRecording ? "pulse 1.2s ease-in-out infinite" : "none",
          }}
        >
          {isProcessing ? "⏳" : "🎙️"}
        </button>
      </div>

      {error && (
        <span style={{ fontSize: 9, color: "#e11d48", textAlign: "center", maxWidth: 70 }}>
          {error}
        </span>
      )}
    </div>
  );
}

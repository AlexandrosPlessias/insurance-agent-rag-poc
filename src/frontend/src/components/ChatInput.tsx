import { useState, useRef, type KeyboardEvent } from "react";
import { VoiceInput, type VoiceLanguage } from "./VoiceInput";

interface Props {
  onSubmit: (text: string) => void;
  disabled?: boolean;
  voiceEnabled?: boolean;
  voiceLanguage?: VoiceLanguage;
  onVoiceLanguageChange?: (lang: VoiceLanguage) => void;
}

export function ChatInput({ onSubmit, disabled, voiceEnabled, voiceLanguage = "en", onVoiceLanguageChange }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  const autoResize = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  const isReady = !disabled && Boolean(value.trim());

  return (
    <div style={{
      display: "flex", alignItems: "flex-end", gap: 10,
      background: "var(--bg-card)",
      border: "1.5px solid var(--border)",
      borderRadius: 14,
      padding: "10px 10px 10px 16px",
      boxShadow: "var(--shadow-md)",
      transition: "border-color .2s, box-shadow .2s",
    }}
      onFocus={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--brand-mid)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 0 0 3px rgba(244,63,94,.1), var(--shadow-md)";
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "var(--shadow-md)";
      }}
    >
      <VoiceInput
        voiceEnabled={Boolean(voiceEnabled)}
        disabled={Boolean(disabled)}
        language={voiceLanguage}
        onLanguageChange={onVoiceLanguageChange ?? (() => {})}
        onTranscript={(t) => setValue(t)}
      />
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => { setValue(e.target.value); autoResize(); }}
        onKeyDown={onKeyDown}
        placeholder={disabled ? "Waiting for response…" : "Ask about a policy, claim, or report…"}
        rows={1}
        disabled={disabled}
        style={{
          flex: 1, resize: "none",
          background: "transparent", border: "none", outline: "none",
          fontSize: 14, lineHeight: 1.6,
          color: "var(--text-primary)",
          fontFamily: "inherit",
          paddingTop: 2,
        }}
      />
      <button
        onClick={submit}
        disabled={!isReady}
        style={{
          background: isReady
            ? "linear-gradient(135deg,#f43f5e,#e11d48)"
            : "#f4f4f5",
          border: "none", borderRadius: 10,
          color: isReady ? "#fff" : "#a1a1aa",
          fontWeight: 700, fontSize: 13,
          padding: "9px 18px",
          cursor: isReady ? "pointer" : "not-allowed",
          boxShadow: isReady ? "0 2px 10px rgba(244,63,94,.3)" : "none",
          transition: "all .2s",
          whiteSpace: "nowrap",
          flexShrink: 0,
        }}
      >
        Send ↵
      </button>
    </div>
  );
}

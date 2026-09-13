// components/MicButton.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";
import { transcribeAudio } from "@/lib/api";
import { isVoiceSupported, micErrorMessage, useVoiceRecorder } from "@/lib/voice";

type MicButtonProps = {
  /** The transcribed question - hand it to the same path a typed one takes. */
  onTranscript: (text: string) => void;
  onError?: (message: string) => void;
  onRecordingChange?: (recording: boolean) => void;
  disabled?: boolean;
  size?: "md" | "sm";
};

/**
 * Push-to-talk: tap to start, tap again to stop and transcribe.
 *
 * Renders nothing where the browser can't record (no secure context, no
 * AudioWorklet) rather than a button that can only fail.
 */
export default function MicButton({
  onTranscript,
  onError,
  onRecordingChange,
  disabled = false,
  size = "md",
}: MicButtonProps) {
  // Decided after mount: the server render has no navigator to ask.
  const [supported, setSupported] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const finishRef = useRef<() => void>(() => {});
  const recorder = useVoiceRecorder({ onAutoStop: () => finishRef.current() });
  const { isRecording } = recorder;

  useEffect(() => setSupported(isVoiceSupported()), []);
  useEffect(() => onRecordingChange?.(isRecording), [isRecording, onRecordingChange]);

  const finish = async () => {
    setIsTranscribing(true);
    try {
      const wav = await recorder.stop();
      if (!wav) {
        onError?.("That was too short - tap the mic, ask your question, then tap again.");
        return;
      }
      const text = await transcribeAudio(wav);
      if (text) onTranscript(text);
      else onError?.("Didn't catch that - try again a little closer to the mic.");
    } catch (error: unknown) {
      onError?.(error instanceof Error ? error.message : "Could not understand the recording.");
    } finally {
      setIsTranscribing(false);
    }
  };
  finishRef.current = finish;

  const handleClick = async () => {
    if (isTranscribing) return;
    if (isRecording) {
      await finish();
      return;
    }
    try {
      await recorder.start();
    } catch (error: unknown) {
      onError?.(micErrorMessage(error));
    }
  };

  if (!supported) return null;

  const label = isRecording ? "Stop and send" : isTranscribing ? "Transcribing…" : "Ask by voice";
  const iconClass = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const sizeClass = size === "sm" ? "rounded-lg px-2.5 py-2" : "rounded-xl px-3.5 py-2.5";
  const stateClass = isRecording
    ? "animate-pulse border-red-500/60 bg-red-500 text-white shadow-[0_0_18px_rgba(239,68,68,0.45)]"
    : "border-slate-300 bg-white text-slate-500 hover:border-cyan-500/40 hover:text-cyan-600 dark:border-white/[0.1] dark:bg-white/[0.03] dark:text-white/55 dark:hover:text-cyan-300";

  return (
    <button
      type="button"
      onClick={handleClick}
      // Stopping must stay possible even if the parent becomes busy mid-recording.
      disabled={(disabled && !isRecording) || isTranscribing}
      aria-label={label}
      aria-pressed={isRecording}
      title={label}
      className={`shrink-0 border transition-all disabled:opacity-40 ${sizeClass} ${stateClass}`}
    >
      {isTranscribing ? (
        <Loader2 className={`${iconClass} animate-spin`} />
      ) : isRecording ? (
        <Square className={`${iconClass} fill-current`} />
      ) : (
        <Mic className={iconClass} />
      )}
    </button>
  );
}

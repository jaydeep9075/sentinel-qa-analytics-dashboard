// components/MicButton.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";
import { transcribeAudio, fetchVoiceCapabilities, VoiceServiceError } from "@/lib/api";
import {
  isBrowserSpeechInputSupported,
  isVoiceSupported,
  listenWithBrowser,
  micErrorMessage,
  useVoiceRecorder,
  warmUpVoiceRecorder,
} from "@/lib/voice";

type MicButtonProps = {
  /** The transcribed question - hand it to the same path a typed one takes.
   * `language` is the BCP-47 tag it was spoken in ("" when undetected), to be
   * handed back to speakText so the answer is heard in that language. */
  onTranscript: (text: string, language: string) => void;
  onError?: (message: string) => void;
  onRecordingChange?: (recording: boolean) => void;
  disabled?: boolean;
  size?: "md" | "sm";
};

/**
 * Hands-free voice input: tap once, ask the question, stop talking.
 *
 * The recording ends itself on the pause that follows a question, so there is
 * no second tap to remember; tapping again still cuts it short for anyone who
 * would rather not wait. Renders nothing where the browser can't record (no
 * secure context, no AudioWorklet) rather than a button that can only fail.
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
  // "server" records and uploads; "browser" lets the browser's own engine
  // listen, which is what keeps the mic working when the LLM has no speech
  // API at all. Null until /voice/capabilities answers.
  const [mode, setMode] = useState<"server" | "browser" | null>(null);
  const finishRef = useRef<() => void>(() => {});
  // Silence detection and a tap can both land on the same recording; without
  // this the second one transcribes an already-torn-down session.
  const finishingRef = useRef(false);
  const listeningRef = useRef<{ stop: () => void; heard: Promise<string> } | null>(null);
  const [isListening, setIsListening] = useState(false);
  const recorder = useVoiceRecorder({ onAutoStop: () => finishRef.current() });
  const isRecording = mode === "browser" ? isListening : recorder.isRecording;

  useEffect(() => {
    let cancelled = false;
    void fetchVoiceCapabilities().then((capabilities) => {
      if (cancelled) return;
      const next = capabilities.mode === "server" ? "server" : "browser";
      setMode(next);
      setSupported(next === "server" ? isVoiceSupported() : isBrowserSpeechInputSupported());
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => onRecordingChange?.(isRecording), [isRecording, onRecordingChange]);

  const finish = async () => {
    if (finishingRef.current) return;
    finishingRef.current = true;
    setIsTranscribing(true);
    try {
      if (mode === "browser") {
        const session = listeningRef.current;
        listeningRef.current = null;
        setIsListening(false);
        if (!session) return;
        session.stop();
        const text = (await session.heard).trim();
        // The browser engine reports no language, so "" lets the rest of the
        // pipeline infer it from the words themselves.
        if (text) onTranscript(text, "");
        else onError?.("Didn't catch that - try again a little closer to the mic.");
        return;
      }
      const wav = await recorder.stop();
      if (!wav) {
        onError?.("Didn't hear anything - check the microphone and tap to try again.");
        return;
      }
      const { text, language } = await transcribeAudio(wav);
      if (text) onTranscript(text, language);
      else onError?.("Didn't catch that - try again a little closer to the mic.");
    } catch (error: unknown) {
      // The speech vendor is down, out of quota or misconfigured. The browser
      // can still listen, so switch to it for the rest of the session rather
      // than leaving the mic dead until someone fixes the server.
      if (error instanceof VoiceServiceError && isBrowserSpeechInputSupported()) {
        setMode("browser");
        onError?.("Speech service unavailable - switched to this browser's own. Tap to try again.");
        return;
      }
      onError?.(error instanceof Error ? error.message : "Could not understand the recording.");
    } finally {
      finishingRef.current = false;
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
      if (mode === "browser") {
        listeningRef.current = listenWithBrowser(() => finishRef.current());
        setIsListening(true);
        return;
      }
      await recorder.start();
    } catch (error: unknown) {
      onError?.(micErrorMessage(error));
    }
  };

  if (!supported) return null;

  const label = isRecording
    ? "Listening - stop talking, or tap to send now"
    : isTranscribing
      ? "Transcribing…"
      : "Ask by voice";
  const iconClass = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const sizeClass = size === "sm" ? "rounded-lg px-2.5 py-2" : "rounded-xl px-3.5 py-2.5";
  const stateClass = isRecording
    ? "animate-pulse border-red-500/60 bg-red-500 text-white shadow-[0_0_18px_rgba(239,68,68,0.45)]"
    : "border-slate-300 bg-white text-slate-500 hover:border-cyan-500/40 hover:text-cyan-600 dark:border-white/[0.1] dark:bg-white/[0.03] dark:text-white/55 dark:hover:text-cyan-300";

  return (
    <button
      type="button"
      onClick={handleClick}
      // Pointer-down is a real user gesture and lands ahead of the click, so
      // the audio graph is already built by the time recording should begin.
      onPointerDown={isRecording || mode !== "server" ? undefined : warmUpVoiceRecorder}
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

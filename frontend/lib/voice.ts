// Push-to-talk recording and spoken-answer playback.
//
// Recording: microphone -> AudioWorklet (public/worklets/pcm-recorder.js) ->
// 16 kHz mono 16-bit WAV, which /voice/transcribe turns into text.
// Playback: one shared <audio> element for the WAV /voice/speak returns, so a
// new answer always cuts off the previous one and audio survives the panel
// that asked for it closing.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

const TARGET_RATE = 16000;
const MAX_RECORDING_MS = 60_000;
// Anything shorter is an accidental double-tap, not a question.
const MIN_RECORDING_SECONDS = 0.3;
const FLUSH_TIMEOUT_MS = 300;

export function isVoiceSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    window.isSecureContext &&
    Boolean(navigator.mediaDevices?.getUserMedia) &&
    typeof AudioWorkletNode !== "undefined"
  );
}

/** A friendly message for getUserMedia / AudioContext failures. */
export function micErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Microphone access is blocked. Allow it from the address bar and try again.";
  }
  if (name === "NotFoundError" || name === "OverconstrainedError") {
    return "No microphone was found.";
  }
  if (name === "NotReadableError") {
    return "The microphone is in use by another app.";
  }
  return error instanceof Error && error.message ? error.message : "Could not start the microphone.";
}

// Averages each window of input samples down to one output sample, then
// converts float [-1, 1] to 16-bit PCM. Ported from the ADK voice workshop's
// streaming client (checkpoints/05_custom_streaming/static/app.js).
function downsampleToPcm16(input: Float32Array, inputRate: number, outputRate: number): Int16Array {
  const ratio = inputRate / outputRate;
  const length = Math.round(input.length / ratio);
  const output = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.round(i * ratio);
    const end = Math.min(Math.round((i + 1) * ratio), input.length);
    let total = 0;
    for (let j = start; j < end; j++) total += input[j];
    const sample = Math.max(-1, Math.min(1, total / Math.max(1, end - start)));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function encodeWav(samples: Int16Array, sampleRate: number): Blob {
  const dataBytes = samples.length * 2;
  const view = new DataView(new ArrayBuffer(44 + dataBytes));
  const writeAscii = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeAscii(8, "WAVE");
  writeAscii(12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeAscii(36, "data");
  view.setUint32(40, dataBytes, true);
  for (let i = 0; i < samples.length; i++) view.setInt16(44 + i * 2, samples[i], true);
  return new Blob([view.buffer], { type: "audio/wav" });
}

type RecordingSession = {
  context: AudioContext;
  stream: MediaStream;
  source: MediaStreamAudioSourceNode;
  node: AudioWorkletNode;
  chunks: Float32Array[];
  onFlushed: (() => void) | null;
  timer: ReturnType<typeof setTimeout>;
};

function teardown(session: RecordingSession) {
  clearTimeout(session.timer);
  session.node.port.onmessage = null;
  session.source.disconnect();
  session.node.disconnect();
  session.stream.getTracks().forEach((track) => track.stop());
  void session.context.close().catch(() => {});
}

/**
 * Tap-to-start / tap-to-stop microphone capture.
 *
 * `stop()` resolves to a 16 kHz WAV, or null when the recording was too short
 * to hold a question. `onAutoStop` fires when the 60 s cap is reached so the
 * caller can finish the recording the same way a second tap would.
 */
export function useVoiceRecorder({ onAutoStop }: { onAutoStop?: () => void } = {}) {
  const sessionRef = useRef<RecordingSession | null>(null);
  const onAutoStopRef = useRef(onAutoStop);
  const [isRecording, setIsRecording] = useState(false);

  useEffect(() => {
    onAutoStopRef.current = onAutoStop;
  }, [onAutoStop]);

  const start = useCallback(async () => {
    if (sessionRef.current) return;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    let context: AudioContext | null = null;
    try {
      context = new AudioContext();
      await context.audioWorklet.addModule("/worklets/pcm-recorder.js");
      await context.resume();
      const source = context.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(context, "pcm-recorder");
      const session: RecordingSession = {
        context,
        stream,
        source,
        node,
        chunks: [],
        onFlushed: null,
        timer: setTimeout(() => onAutoStopRef.current?.(), MAX_RECORDING_MS),
      };
      node.port.onmessage = (event: MessageEvent) => {
        if (event.data instanceof Float32Array) session.chunks.push(event.data);
        else if (event.data?.done) session.onFlushed?.();
      };
      source.connect(node);
      // The processor writes no output, so this is silent; it only keeps the
      // node in the rendered graph so process() keeps being called.
      node.connect(context.destination);
      sessionRef.current = session;
      setIsRecording(true);
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      void context?.close().catch(() => {});
      throw error;
    }
  }, []);

  const stop = useCallback(async (): Promise<Blob | null> => {
    const session = sessionRef.current;
    if (!session) return null;
    sessionRef.current = null;
    setIsRecording(false);

    await new Promise<void>((resolve) => {
      const timeout = setTimeout(resolve, FLUSH_TIMEOUT_MS);
      session.onFlushed = () => {
        clearTimeout(timeout);
        resolve();
      };
      session.node.port.postMessage("flush");
    });
    const inputRate = session.context.sampleRate;
    teardown(session);

    const total = session.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    if (total < inputRate * MIN_RECORDING_SECONDS) return null;
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of session.chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    const outputRate = Math.min(inputRate, TARGET_RATE);
    return encodeWav(downsampleToPcm16(merged, inputRate, outputRate), outputRate);
  }, []);

  // Releasing the microphone on unmount matters: a leaked stream keeps the
  // browser's recording indicator on.
  useEffect(
    () => () => {
      if (sessionRef.current) teardown(sessionRef.current);
      sessionRef.current = null;
    },
    [],
  );

  return { isRecording, start, stop };
}

// ── playback ────────────────────────────────────────────────────────────────

let currentAudio: HTMLAudioElement | null = null;
let playingId: string | null = null;
const playbackListeners = new Set<() => void>();

function setPlaying(id: string | null) {
  playingId = id;
  playbackListeners.forEach((listener) => listener());
}

export function stopVoice() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.src = "";
    currentAudio = null;
  }
  setPlaying(null);
}

/** Play a base64 WAV, stopping anything already playing. `id` names what is
 * being spoken so its button can show a Stop state. */
export async function playVoice(base64Wav: string, id: string): Promise<void> {
  stopVoice();
  const audio = new Audio(`data:audio/wav;base64,${base64Wav}`);
  currentAudio = audio;
  const finish = () => {
    if (currentAudio === audio) {
      currentAudio = null;
      setPlaying(null);
    }
  };
  audio.onended = finish;
  audio.onerror = finish;
  setPlaying(id);
  try {
    await audio.play();
  } catch (error) {
    finish();
    throw error;
  }
}

function subscribePlayback(listener: () => void) {
  playbackListeners.add(listener);
  return () => {
    playbackListeners.delete(listener);
  };
}

/** The id passed to playVoice() for whatever is playing now, or null. */
export function useVoicePlayback(): string | null {
  return useSyncExternalStore(
    subscribePlayback,
    () => playingId,
    () => null,
  );
}

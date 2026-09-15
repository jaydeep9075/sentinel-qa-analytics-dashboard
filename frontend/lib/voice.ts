// Push-to-talk recording and spoken-answer playback.
//
// Recording: microphone -> AudioWorklet (public/worklets/pcm-recorder.js) ->
// 16 kHz mono 16-bit WAV, which /voice/transcribe turns into text.
// Playback: one shared <audio> element for the WAV /voice/speak returns, so a
// new answer always cuts off the previous one and audio survives the panel
// that asked for it closing.
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { fetchVoiceCapabilities, speakText } from "@/lib/api";

const TARGET_RATE = 16000;
const MAX_RECORDING_MS = 60_000;
// Anything shorter is an accidental double-tap, not a question.
const MIN_RECORDING_SECONDS = 0.3;
const FLUSH_TIMEOUT_MS = 300;

// ── silence detection ───────────────────────────────────────────────────────
//
// So a question ends itself. Having to tap a second time means the speaker
// has to think about the button while they are still thinking about the
// question, and every turn carries however long it takes them to notice they
// have finished. The worklet already hands whole blocks of samples to the
// main thread, so the loudness check rides along on those rather than costing
// a second message or a second node in the graph.

// Quiet for this long, once something has actually been said, ends it. Long
// enough to survive the pause mid-sentence that a person takes to think.
const SILENCE_HOLD_MS = 1300;
// Nothing said at all by now: the mic is muted, or the tap was a misfire.
const NO_SPEECH_TIMEOUT_MS = 7000;
const WATCHDOG_TICK_MS = 150;
// An absolute floor under the adaptive threshold, so a silent room can't
// lower it until the speaker's own breathing counts as talking.
const MIN_SPEECH_RMS = 0.01;
// Speech has to be this many times the room's own noise to count, which is
// what lets this work next to a fan or in an open office.
const NOISE_MARGIN = 3.5;

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
  watchdog: ReturnType<typeof setInterval> | null;
  startedAt: number;
  /** A running estimate of the room with nobody talking. */
  noiseFloor: number;
  heardSpeech: boolean;
  lastVoiceAt: number;
};

function rootMeanSquare(samples: Float32Array): number {
  let total = 0;
  for (let i = 0; i < samples.length; i++) total += samples[i] * samples[i];
  return Math.sqrt(total / Math.max(1, samples.length));
}

/** Fold one block of microphone samples into the is-anyone-talking state. */
function observeLevel(session: RecordingSession, samples: Float32Array): void {
  const level = rootMeanSquare(samples);
  // Drops to a new quiet immediately but climbs back slowly, so a passing
  // noise raises the bar without a moment of silence resetting it.
  session.noiseFloor =
    level < session.noiseFloor ? level : session.noiseFloor * 0.98 + level * 0.02;
  if (level > Math.max(MIN_SPEECH_RMS, session.noiseFloor * NOISE_MARGIN)) {
    session.heardSpeech = true;
    session.lastVoiceAt = Date.now();
  }
}

/** Whether the recording has run its course, for whichever of the three
 * reasons: the speaker finished, never started, or ran past the cap. */
function shouldAutoStop(session: RecordingSession, now: number): boolean {
  if (now - session.startedAt > MAX_RECORDING_MS) return true;
  if (!session.heardSpeech) return now - session.startedAt > NO_SPEECH_TIMEOUT_MS;
  return now - session.lastVoiceAt > SILENCE_HOLD_MS;
}

let sharedContext: AudioContext | null = null;
let workletReady: Promise<void> | null = null;
// Chat and chart each render their own mic, so more than one recorder can be
// live on the shared context at a time.
let activeRecordings = 0;

/**
 * The one AudioContext every recording runs on.
 *
 * Building a context and compiling the worklet costs a few hundred
 * milliseconds, and on push-to-talk that lands exactly between the tap and
 * the microphone actually listening - the window in which the first word of a
 * question gets clipped. Keeping both alive makes every tap after the first
 * start instantly.
 */
async function recordingContext(): Promise<AudioContext> {
  if (!sharedContext || sharedContext.state === "closed") {
    sharedContext = new AudioContext();
    workletReady = sharedContext.audioWorklet.addModule("/worklets/pcm-recorder.js");
  }
  try {
    await workletReady;
  } catch (error) {
    // A failed compile would otherwise be cached and rethrown forever.
    sharedContext = null;
    workletReady = null;
    throw error;
  }
  if (sharedContext.state === "suspended") await sharedContext.resume();
  return sharedContext;
}

/** Build the context ahead of the click that needs it. Safe to call often and
 * from any user gesture; failures are the caller's problem to surface later. */
export function warmUpVoiceRecorder(): void {
  void recordingContext().catch(() => {});
}

function teardown(session: RecordingSession) {
  if (session.watchdog) clearInterval(session.watchdog);
  session.watchdog = null;
  session.node.port.onmessage = null;
  session.source.disconnect();
  session.node.disconnect();
  session.stream.getTracks().forEach((track) => track.stop());
  activeRecordings = Math.max(0, activeRecordings - 1);
  // The context is shared and deliberately kept alive. Suspending parks the
  // audio thread without throwing away the compiled worklet; the microphone
  // itself is released by stopping the tracks above, which is what clears the
  // browser's recording indicator.
  if (activeRecordings === 0) void session.context.suspend().catch(() => {});
}

/**
 * Hands-free microphone capture: tap to start, then just stop talking.
 *
 * `onAutoStop` fires once the speaker has finished - a short silence after
 * speech, nothing said at all, or the 60 s cap - so the caller can finish the
 * recording exactly as a second tap would. Tapping again still works, for
 * anyone who would rather not wait out the pause.
 *
 * `stop()` resolves to a 16 kHz WAV, or null when the recording was too short
 * to hold a question.
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
    // The context first: getUserMedia is the slow, permission-gated half, and
    // starting it only once the graph is ready keeps the mic from listening
    // to a moment nothing is recording.
    const context = await recordingContext();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    try {
      const source = context.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(context, "pcm-recorder");
      const session: RecordingSession = {
        context,
        stream,
        source,
        node,
        chunks: [],
        onFlushed: null,
        watchdog: null,
        startedAt: Date.now(),
        // Starts high so the first blocks pull it down to the real room
        // rather than the first word setting the bar for the rest.
        noiseFloor: 1,
        heardSpeech: false,
        lastVoiceAt: Date.now(),
      };
      node.port.onmessage = (event: MessageEvent) => {
        if (event.data instanceof Float32Array) {
          session.chunks.push(event.data);
          observeLevel(session, event.data);
        } else if (event.data?.done) session.onFlushed?.();
      };
      session.watchdog = setInterval(() => {
        if (!shouldAutoStop(session, Date.now())) return;
        // Cleared before handing over, because finishing is asynchronous and
        // this would otherwise fire again while it is in progress.
        if (session.watchdog) clearInterval(session.watchdog);
        session.watchdog = null;
        onAutoStopRef.current?.();
      }, WATCHDOG_TICK_MS);
      source.connect(node);
      // The processor writes no output, so this is silent; it only keeps the
      // node in the rendered graph so process() keeps being called.
      node.connect(context.destination);
      sessionRef.current = session;
      activeRecordings += 1;
      setIsRecording(true);
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      if (activeRecordings === 0) void context.suspend().catch(() => {});
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
    const heardSpeech = session.heardSpeech;
    teardown(session);

    const total = session.chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    // Nothing above the room's own noise: uploading seven seconds of a muted
    // microphone would only buy a slower way of saying the same thing.
    if (!heardSpeech || total < inputRate * MIN_RECORDING_SECONDS) return null;
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
  // The browser engine is a separate player with its own queue, so silencing
  // one without the other would leave an answer still talking.
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
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

// ── browser speech ──────────────────────────────────────────────────────────
//
// The fallback for deployments whose LLM has no speech API at all - Claude,
// or a local Ollama. Both halves run in the browser, need no key and cost
// nothing, so the mic keeps working whatever LLM_PROVIDER is set to. Quality
// is below a hosted speech model, which is why it is only used when the
// server says it has no vendor of its own.

type RecognitionEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};
type RecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionConstructor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as Record<string, unknown>;
  const ctor = scope.SpeechRecognition || scope.webkitSpeechRecognition;
  return (ctor as (new () => RecognitionLike) | undefined) ?? null;
}

export function isBrowserSpeechInputSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function isBrowserSpeechOutputSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/**
 * Listen until the speaker stops talking, then resolve with what was heard.
 *
 * `onAutoStop` fires when the engine ended the turn by itself, so the caller
 * can pick the transcript up without a second tap - the same hands-free shape
 * the server path gets from its own silence detection. Calling `stop()`
 * suppresses it, since the caller is already finishing.
 *
 * No language is given, so the engine uses the page's own - browsers won't
 * auto-detect across languages the way a hosted model does. The transcript's
 * language is reported back as "" and everything downstream infers it from
 * the words instead.
 */
export function listenWithBrowser(onAutoStop?: () => void): {
  stop: () => void;
  heard: Promise<string>;
} {
  const Recognition = recognitionConstructor();
  if (!Recognition) {
    return { stop: () => {}, heard: Promise.reject(new Error("This browser cannot listen.")) };
  }
  const recognition = new Recognition();
  // false is what makes the engine end the turn on its own once the speaker
  // pauses; with it on, the recording only ever ends when told to.
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.lang = typeof navigator !== "undefined" ? navigator.language || "en-US" : "en-US";

  const pieces: string[] = [];
  let stoppedByCaller = false;
  // Assigned synchronously by the executor below; `!` because TypeScript's
  // flow analysis can't see that.
  let settle!: (value: string) => void;
  let fail!: (error: Error) => void;

  const heard = new Promise<string>((resolve, reject) => {
    settle = resolve;
    fail = reject;
  });

  recognition.onresult = (event) => {
    for (let i = 0; i < event.results.length; i++) {
      const alternative = event.results[i]?.[0];
      if (alternative?.transcript) pieces.push(alternative.transcript);
    }
  };
  recognition.onerror = (event) => {
    const code = event?.error || "";
    if (code === "no-speech" || code === "aborted") return;
    fail(new Error(code === "not-allowed" ? "Microphone access is blocked." : "Could not hear that."));
  };
  recognition.onend = () => {
    settle(pieces.join(" ").replace(/\s+/g, " ").trim());
    if (!stoppedByCaller) onAutoStop?.();
  };

  try {
    recognition.start();
  } catch (error) {
    fail(error instanceof Error ? error : new Error("Could not start listening."));
  }
  return {
    stop: () => {
      stoppedByCaller = true;
      recognition.stop();
    },
    heard,
  };
}

const LINK_RE = /\[([^\]]+)\]\([^)]*\)/g;
const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]/gu;
const BULLET_RE = /^\s*(?:[-•]|\d+[.)])\s+/gm;
const MARKDOWN_RE = /[*_`#>|~]+/g;

/** Strip what a speech voice would read out literally. Mirrors
 * services/voice.py's plain_speech(), which the server path applies for us. */
export function plainSpeech(text: string): string {
  return (text || "")
    .replace(LINK_RE, "$1")
    .replace(EMOJI_RE, "")
    .replace(BULLET_RE, "")
    .replace(MARKDOWN_RE, "")
    .replace(/\s+/g, " ")
    .trim();
}

function pickVoice(language: string): SpeechSynthesisVoice | null {
  if (!language) return null;
  const wanted = language.toLowerCase();
  const base = wanted.split("-")[0];
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang?.toLowerCase() === wanted) ||
    voices.find((v) => v.lang?.toLowerCase().startsWith(base)) ||
    null
  );
}

/** Read `text` aloud with the browser's own engine, under the same
 * playing-state as the server path so one Stop button covers both. */
export function speakWithBrowser(text: string, language: string, id: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!isBrowserSpeechOutputSupported()) {
      reject(new Error("This browser cannot speak."));
      return;
    }
    stopVoice();
    const utterance = new SpeechSynthesisUtterance(text);
    if (language) utterance.lang = language;
    const voice = pickVoice(language);
    if (voice) utterance.voice = voice;

    const finish = () => {
      if (playingId === id) setPlaying(null);
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    setPlaying(id);
    window.speechSynthesis.speak(utterance);
  });
}

/**
 * Say an answer out loud, whichever half of the system can do it.
 *
 * Callers don't need to know which: the server's vendor is used when there is
 * one, and the browser's engine when there isn't - or when the vendor is
 * configured but not answering. That last case is why the fallback is here
 * and not only in the capabilities check: a retired speech model, an expired
 * key or a quota that ran out mid-session all leave the server saying it can
 * speak right up until it is asked to, and silently reading the answer with
 * the browser's own voice is a far better outcome than an error toast.
 */
export async function speakAnswer(
  text: string,
  kind: "chat" | "chart",
  language: string | undefined,
  id: string,
): Promise<void> {
  const capabilities = await fetchVoiceCapabilities();
  if (capabilities.mode === "server") {
    try {
      const { audio } = await speakText(text, kind, language);
      await playVoice(audio, id);
      return;
    } catch (error) {
      if (!isBrowserSpeechOutputSupported()) throw error;
      console.warn("Server speech failed; using the browser's voice instead.", error);
    }
  }
  const spoken = plainSpeech(text);
  if (!spoken) throw new Error("There is nothing to say for this answer.");
  await speakWithBrowser(spoken, language || "", id);
}

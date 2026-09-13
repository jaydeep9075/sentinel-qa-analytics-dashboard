// AudioWorklet processor for push-to-talk (see lib/voice.ts).
//
// Runs on the audio thread and only copies microphone samples out: they are
// batched into ~85 ms blocks so the main thread isn't woken for every
// 128-sample render quantum. Downsampling and WAV encoding happen once, on the
// main thread, when the recording stops.
const BLOCK_SIZE = 4096;

class PcmRecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(BLOCK_SIZE);
    this.filled = 0;
    // "flush" is sent on stop: hand over the partial block so the last words
    // aren't cut off, then confirm so the main thread knows it has everything.
    this.port.onmessage = (event) => {
      if (event.data !== "flush") return;
      if (this.filled > 0) this.port.postMessage(this.block.slice(0, this.filled));
      this.filled = 0;
      this.port.postMessage({ done: true });
    };
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    let offset = 0;
    while (offset < channel.length) {
      const count = Math.min(channel.length - offset, BLOCK_SIZE - this.filled);
      this.block.set(channel.subarray(offset, offset + count), this.filled);
      this.filled += count;
      offset += count;
      if (this.filled === BLOCK_SIZE) {
        this.port.postMessage(this.block.slice(0));
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-recorder", PcmRecorderProcessor);

// Short interface sounds, synthesized with the Web Audio API (no audio file to load).

type Note = [frequency: number, start: number, duration: number];

let context: AudioContext | null = null;

function audio(): AudioContext | null {
  try {
    context ??= new AudioContext();
    if (context.state === 'suspended') {
      void context.resume();
    }
    return context;
  } catch {
    return null; // no Web Audio: the app works silently
  }
}

function play(notes: Note[], volume = 0.18, type: OscillatorType = 'sine'): void {
  const ctx = audio();
  if (!ctx) {
    return;
  }
  const now = ctx.currentTime;
  for (const [frequency, start, duration] of notes) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, now + start);
    // Quick attack, smooth release: a soft "pop" rather than a beep.
    gain.gain.setValueAtTime(0.0001, now + start);
    gain.gain.exponentialRampToValueAtTime(volume, now + start + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + start + duration);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now + start);
    osc.stop(now + start + duration + 0.02);
  }
}

/**
 * A clip playing through the shared audio context. Mobile browsers only let a page make
 * sound right after a tap; the context is unlocked when the mic is touched (the start
 * sound), so the spoken answer, which arrives seconds later, can still play by itself.
 */
export interface Clip {
  ended: Promise<void>;
  stop(): void;
}

export async function playClip(audioData: Blob): Promise<Clip> {
  const ctx = audio();
  if (!ctx) {
    throw new Error('Web Audio unavailable');
  }
  const buffer = await ctx.decodeAudioData(await audioData.arrayBuffer());
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  const ended = new Promise<void>((resolve) => (source.onended = () => resolve()));
  source.start();
  return {
    ended,
    stop: () => {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    },
  };
}

/** Call from a tap handler: resumes the audio context so later sounds may play. */
export function unlockAudio(): void {
  audio();
}

export const sounds = {
  /** Mic opens: two rising notes. */
  start: () =>
    play([
      [660, 0, 0.12],
      [990, 0.09, 0.16],
    ]),
  /** Mic closes, the question leaves: two falling notes. */
  stop: () =>
    play([
      [880, 0, 0.1],
      [587, 0.08, 0.14],
    ]),
  /** The answer is ready: a light three-note chime. */
  ready: () =>
    play(
      [
        [784, 0, 0.18],
        [988, 0.1, 0.18],
        [1319, 0.2, 0.28],
      ],
      0.12,
      'triangle',
    ),
};

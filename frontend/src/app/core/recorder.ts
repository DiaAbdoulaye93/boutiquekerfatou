import { Injectable } from '@angular/core';

// Opus in WebM (Chrome, Android, Firefox), then MP4/AAC (Safari, iOS).
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
const MAX_SECONDS = 30;

/** One microphone recording at a time, returned as a Blob when stopped. */
@Injectable({ providedIn: 'root' })
export class Recorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped: ((blob: Blob) => void) | null = null;

  static supported(): boolean {
    return typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia;
  }

  get recording(): boolean {
    return this.recorder?.state === 'recording';
  }

  /**
   * Starts recording once the mic is granted. `done` resolves with the audio when
   * `stop()` is called (or after 30 s). It is wrapped in an object on purpose: an async
   * function returning a bare promise would wait for the end of the recording.
   */
  async start(): Promise<{ done: Promise<Blob> }> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });
    const mimeType = MIME_TYPES.find((t) => MediaRecorder.isTypeSupported(t));
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    this.recorder = recorder;
    this.chunks = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) {
        this.chunks.push(event.data);
      }
    };
    const done = new Promise<Blob>((resolve) => (this.stopped = resolve));
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop()); // release the mic indicator
      if (this.timer) {
        clearTimeout(this.timer);
      }
      this.stopped?.(new Blob(this.chunks, { type: recorder.mimeType || 'audio/webm' }));
      this.recorder = null;
    };
    recorder.start();
    this.timer = setTimeout(() => this.stop(), MAX_SECONDS * 1000);
    return { done };
  }

  stop(): void {
    if (this.recorder?.state === 'recording') {
      this.recorder.stop();
    }
  }
}

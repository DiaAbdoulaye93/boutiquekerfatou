import {
  Component,
  ElementRef,
  OnDestroy,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SwUpdate } from '@angular/service-worker';
import { filter } from 'rxjs';

import { ApiService, errorMessage } from './core/api.service';
import { LANGUAGES } from './core/format';
import { AskOut, TurnIn } from './core/models';
import { Recorder } from './core/recorder';
import { Clip, playClip, sounds, unlockAudio } from './core/sounds';
import { MicSpiral, MicState } from './shared/mic-spiral';
import { ResultCard } from './shared/result-card';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  spoken?: boolean; // the user's question was a voice note
  reply?: AskOut;
}

// What the assistant is doing; each step shows on screen.
type Status = 'idle' | 'recording' | 'transcribing' | 'thinking';
const STATUS_LABELS: Record<Status, string> = {
  idle: 'Touchez pour parler',
  recording: "J'écoute… touchez pour envoyer",
  transcribing: 'Je transcris…',
  thinking: 'Je cherche dans la boutique…',
};

@Component({
  selector: 'app-root',
  imports: [FormsModule, MicSpiral, ResultCard],
  templateUrl: './app.html',
})
export class App implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly recorder = inject(Recorder);
  private readonly bottom = viewChild<ElementRef<HTMLElement>>('bottom');
  private readonly voices = new Map<number, Blob>(); // spoken answers, by message id
  private clip: Clip | null = null;
  private fallback: HTMLAudioElement | null = null;
  private tick: ReturnType<typeof setInterval> | null = null;
  private nextId = 1;

  readonly shopName = signal('Boutique vocale');
  readonly messages = signal<Message[]>([]);
  readonly status = signal<Status>('idle');
  readonly seconds = signal(0);
  readonly error = signal<string | null>(null);
  readonly draft = signal('');
  readonly typing = signal(!Recorder.supported()); // keyboard instead of the mic
  readonly playing = signal<number | null>(null); // message id being read aloud
  readonly loadingVoice = signal<number | null>(null);
  readonly busy = computed(() => this.status() !== 'idle');
  readonly micState = computed<MicState>(() => {
    const status = this.status();
    return status === 'recording' ? 'recording' : status === 'idle' ? 'idle' : 'busy';
  });
  readonly statusLabel = computed(() => {
    const status = this.status();
    return status === 'recording'
      ? `${STATUS_LABELS.recording} · ${this.seconds()} s`
      : STATUS_LABELS[status];
  });
  readonly micSupported = Recorder.supported();
  readonly languages = LANGUAGES;

  constructor() {
    this.api.shop().subscribe({ next: (s) => this.shopName.set(s.name) });
    // The service worker serves the cached app first; once it has fetched a newer
    // deployment, switch to it right away instead of waiting for the next visit.
    const updates = inject(SwUpdate);
    if (updates.isEnabled) {
      updates.versionUpdates
        .pipe(filter((event) => event.type === 'VERSION_READY'))
        .subscribe(() => {
          if (this.status() === 'idle' && !this.messages().length) {
            document.location.reload();
          }
        });
    }
  }

  ngOnDestroy(): void {
    this.stopTick();
    this.stopVoice();
  }

  send(text = this.draft()): void {
    const question = text.trim();
    if (!question || this.busy()) {
      return;
    }
    unlockAudio(); // inside the tap: lets the answer be read aloud by itself
    this.draft.set('');
    this.ask(question);
  }

  async toggleMic(): Promise<void> {
    // Must run synchronously in the tap, before any await (iOS is strict about it).
    unlockAudio();
    if (this.status() === 'recording') {
      sounds.stop();
      this.recorder.stop();
      return;
    }
    if (this.busy()) {
      return;
    }
    this.error.set(null);
    this.stopVoice();
    let recording: Promise<Blob>;
    try {
      recording = (await this.recorder.start()).done;
    } catch {
      this.error.set("Le micro n'est pas accessible. Autorisez-le dans le navigateur.");
      return;
    }
    sounds.start();
    this.status.set('recording');
    this.seconds.set(0);
    this.tick = setInterval(() => this.seconds.update((s) => s + 1), 1000);
    const audio = await recording;
    this.stopTick();
    if (audio.size < 1000) {
      this.status.set('idle');
      this.error.set('Vocal trop court : touchez, parlez, puis touchez de nouveau.');
      return;
    }
    this.status.set('transcribing');
    // No language sent: the transcription detects wolof, French or English by itself.
    this.api.transcribe(audio).subscribe({
      next: (heard) => this.ask(heard.text, true),
      error: (err: unknown) => this.fail(err),
    });
  }

  /** Reads an answer aloud, fetching its audio the first time. */
  listen(message: Message): void {
    const voice = this.voices.get(message.id);
    if (voice) {
      void this.play(message.id, voice);
      return;
    }
    if (!message.reply || this.loadingVoice() !== null) {
      return;
    }
    this.loadingVoice.set(message.id);
    this.api.speak(message.reply.answer, message.reply.language).subscribe({
      next: (blob) => {
        this.loadingVoice.set(null);
        this.voices.set(message.id, blob);
        void this.play(message.id, blob);
      },
      error: () => {
        this.loadingVoice.set(null);
        this.error.set("La voix n'a pas pu être générée ; la réponse écrite reste valable.");
      },
    });
  }

  reset(): void {
    this.stopVoice();
    this.voices.clear();
    this.messages.set([]);
    this.error.set(null);
  }

  private ask(question: string, spoken = false): void {
    const history: TurnIn[] = this.messages().map((m) => ({ role: m.role, text: m.text }));
    this.push({ role: 'user', text: question, spoken });
    this.status.set('thinking');
    this.error.set(null);
    this.api.ask({ question, history }).subscribe({
      next: (reply) => {
        const message = this.push({ role: 'assistant', text: reply.answer, reply });
        this.status.set('idle');
        this.listen(message); // every answer is read aloud
      },
      error: (err: unknown) => this.fail(err),
    });
  }

  private fail(err: unknown): void {
    this.error.set(errorMessage(err));
    this.status.set('idle');
  }

  private async play(id: number, voice: Blob): Promise<void> {
    this.stopVoice();
    this.playing.set(id);
    try {
      // Through the audio context unlocked by the last tap: plays without a new tap.
      const clip = await playClip(voice);
      this.clip = clip;
      await clip.ended;
      if (this.clip === clip) {
        this.clip = null;
        this.playing.set(null);
      }
    } catch {
      // No Web Audio or undecodable audio: a plain audio element (may need a tap).
      const url = URL.createObjectURL(voice);
      const player = new Audio(url);
      this.fallback = player;
      player.onended = () => {
        URL.revokeObjectURL(url);
        this.playing.set(null);
      };
      player.play().catch(() => this.playing.set(null));
    }
  }

  private stopVoice(): void {
    this.clip?.stop();
    this.clip = null;
    this.fallback?.pause();
    this.fallback = null;
    this.playing.set(null);
  }

  private push(message: Omit<Message, 'id'>): Message {
    const full = { ...message, id: this.nextId++ };
    this.messages.update((list) => [...list, full]);
    setTimeout(() => this.bottom()?.nativeElement.scrollIntoView({ behavior: 'smooth' }));
    return full;
  }

  private stopTick(): void {
    if (this.tick) {
      clearInterval(this.tick);
      this.tick = null;
    }
  }
}

/**
 * 파이썬 채점기(메인 화면 쪽). public/pyworker.js(Web Worker)에 학생 코드와 테스트를 보내고 결과를 받는다.
 * - 코드는 브라우저 안에서만 실행한다(서버로 보내지 않음).
 * - 정해진 시간 안에 끝나지 않으면(무한 반복 등) 워커를 끝내고 새로 만든다.
 */
import { BASE_URL } from '../lib/config';
import type { Case, CompareMode, CSpec, Lang } from '../content/types';

export interface PyError {
  type: string;
  message: string;
  line: number | null;
  hint: string;
}
export interface CaseResult {
  ok: boolean;
  got?: string;
  error?: PyError;
}
export interface RunOutput {
  compile: PyError | null;
  results: CaseResult[];
  stdout: string;
  stdoutCut: boolean;
}
export type RunResult = { kind: 'done'; out: RunOutput; ms: number } | { kind: 'timeout'; ms: number } | { kind: 'fail'; message: string };
export type EngineStatus = 'idle' | 'loading' | 'ready' | 'error';

type Reply = { id: number; ok: boolean; result?: RunOutput; error?: string };

class PyRunner {
  private worker: Worker | null = null;
  private ready: Promise<void> | null = null;
  private seq = 0;
  private pending = new Map<number, (r: Reply) => void>();
  status: EngineStatus = 'idle';
  private listeners = new Set<(s: EngineStatus) => void>();

  subscribe(fn: (s: EngineStatus) => void): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private set(s: EngineStatus) {
    this.status = s;
    for (const l of this.listeners) l(s);
  }

  private post(msg: Record<string, unknown>): { id: number; reply: Promise<Reply> } {
    const id = ++this.seq;
    const reply = new Promise<Reply>((resolve) => this.pending.set(id, resolve));
    this.worker!.postMessage({ ...msg, id, base: BASE_URL });
    return { id, reply };
  }

  /** 워커를 만들고 Pyodide를 불러 둔다(이미 준비됐으면 바로 끝남). */
  ensure(): Promise<void> {
    if (this.ready) return this.ready;
    this.set('loading');
    const w = new Worker(`${BASE_URL}pyworker.js`);
    this.worker = w;
    w.onmessage = (e: MessageEvent<Reply>) => {
      const fn = this.pending.get(e.data.id);
      if (fn) {
        this.pending.delete(e.data.id);
        fn(e.data);
      }
    };
    w.onerror = () => {
      this.set('error');
    };
    const { reply } = this.post({ type: 'init' });
    const ready = reply.then((r) => {
      if (!r.ok) throw new Error(r.error || '파이썬 실행 환경을 불러오지 못했어요.');
      this.set('ready');
    });
    ready.catch(() => {
      this.reset();
      this.set('error');
    });
    this.ready = ready;
    return ready;
  }

  private reset() {
    this.worker?.terminate();
    this.worker = null;
    this.ready = null;
    for (const fn of this.pending.values()) fn({ id: -1, ok: false, error: '중단됨' });
    this.pending.clear();
  }

  async run(code: string, func: string, cases: Case[], mode: CompareMode, timeoutMs = 4000, lang: Lang = 'python', spec?: CSpec): Promise<RunResult> {
    try {
      await this.ensure();
    } catch (e) {
      return { kind: 'fail', message: e instanceof Error ? e.message : String(e) };
    }
    const started = performance.now();
    const { reply } = this.post({ type: 'run', code, func, cases: JSON.stringify(cases.map((c) => ({ args: c.args, expected: c.expected }))), mode, lang, spec: JSON.stringify(spec ?? {}) });
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<'timeout'>((r) => {
      timer = setTimeout(() => r('timeout'), timeoutMs);
    });
    const r = await Promise.race([reply, timeout]);
    clearTimeout(timer);
    const ms = Math.round(performance.now() - started);
    if (r === 'timeout') {
      // 무한 반복 등: 워커를 끝내고 다음 실행을 위해 새로 준비한다
      this.reset();
      this.set('idle');
      void this.ensure().catch(() => undefined);
      return { kind: 'timeout', ms };
    }
    if (!r.ok || !r.result) return { kind: 'fail', message: r.error || '실행하지 못했어요.' };
    return { kind: 'done', out: r.result, ms };
  }
}

let runner: PyRunner | null = null;
export function py(): PyRunner {
  runner ??= new PyRunner();
  return runner;
}

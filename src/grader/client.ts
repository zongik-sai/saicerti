/**
 * 채점기(메인 화면 쪽, 파이썬·C 공용). public/pyworker.js(Web Worker)에 학생 코드와 테스트를 보내고 결과를 받는다.
 * - 코드는 브라우저 안에서만 실행한다(서버로 보내지 않음).
 * - 정해진 시간 안에 끝나지 않으면(무한 반복 등) 워커를 끝내고 새로 만든다.
 */
import { BASE_URL } from '../lib/config';
import type { Case, CompareMode, CSpec, Lang, Problem } from '../content/types';

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
  /** Data 과정: 거의 맞았을 때 도움말(반올림 등) */
  hint?: string;
}
export interface RunOutput {
  compile: PyError | null;
  results: CaseResult[];
  stdout: string;
  stdoutCut: boolean;
  /** Data 과정: 그래프 그림(PNG base64) */
  images?: string[];
}

/** Data 과정 코드가 쓰는 패키지(pandas는 늘) */
export function dataPkgs(code: string, plot = false): string[] {
  const out = ['pandas'];
  if (plot || /\bmatplotlib\b/.test(code)) out.push('matplotlib');
  if (/\bscipy\b/.test(code)) out.push('scipy');
  if (/\bsklearn\b/.test(code)) out.push('scikit-learn');
  return out;
}
export type RunResult = { kind: 'done'; out: RunOutput; ms: number } | { kind: 'timeout'; ms: number } | { kind: 'fail'; message: string };
export type EngineStatus = 'idle' | 'loading' | 'ready' | 'error';

type Reply = { id: number; ok: boolean; result?: RunOutput; error?: string };

class PyRunner {
  private worker: Worker | null = null;
  private ready: Promise<void> | null = null;
  private cReady: Promise<void> | null = null;
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

  /** 워커를 만들고 Pyodide를 불러 둔다(이미 준비됐으면 바로 끝남). C면 C 채점기(pycparser·cinterp)까지 불러 둔다. */
  ensure(lang: Lang = 'python'): Promise<void> {
    return lang === 'c' ? this.ensureC() : this.ensurePy();
  }

  private ensureC(): Promise<void> {
    if (this.cReady) return this.cReady;
    const ready = this.ensurePy().then(async () => {
      if (!this.worker) throw new Error('중단됨');
      this.set('loading');
      const r = await this.post({ type: 'initC' }).reply;
      if (!r.ok) throw new Error(r.error || 'C 채점기를 불러오지 못했어요.');
      this.set('ready');
    });
    ready.catch(() => {
      if (this.cReady === ready) this.cReady = null;
      if (this.status === 'loading') this.set('error');
    });
    this.cReady = ready;
    return ready;
  }

  private ensurePy(): Promise<void> {
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
    this.cReady = null;
    this.dataDone.clear();
    for (const fn of this.pending.values()) fn({ id: -1, ok: false, error: '중단됨' });
    this.pending.clear();
  }

  /** Data 과정: 패키지와 데이터 파일(변형들)을 미리 준비한다(시간 제한 밖에서) */
  async prepareData(pkgs: string[], files: { name: string; v: number }[]): Promise<void> {
    await this.ensurePy();
    if (!this.worker) throw new Error('중단됨');
    const key = JSON.stringify([pkgs, files]);
    if (this.dataDone.has(key)) return;
    this.dataBusy++;
    this.set('loading');
    try {
      const r = await this.post({ type: 'initData', pkgs, files }).reply;
      if (!r.ok) throw new Error(r.error || '데이터 분석 도구를 불러오지 못했어요.');
      this.dataDone.add(key);
    } finally {
      this.dataBusy--;
      if (this.worker) this.set('ready');
    }
  }
  private dataDone = new Set<string>();
  private dataBusy = 0;

  /** Data 과정 문제 실행: cases의 data(변형 번호)마다 그 데이터로 코드를 새로 실행하고 solution()의 반환값·그래프를 비교 */
  async runData(code: string, problem: Problem, cases: Case[], timeoutMs = 30000): Promise<RunResult> {
    const plot = !!problem.data?.plot;
    const vs = [...new Set(cases.map((c) => c.data ?? 0))];
    try {
      await this.prepareData(dataPkgs(code, plot), (problem.data?.files ?? []).flatMap((name) => vs.map((v) => ({ name, v }))));
    } catch (e) {
      return { kind: 'fail', message: e instanceof Error ? e.message : String(e) };
    }
    const payload = JSON.stringify(cases.map((c) => ({ dir: `/d2data/v${c.data ?? 0}`, expected: c.expected, ...(plot ? { plot: true } : {}) })));
    return this.exec({ type: 'runData', code, cases: payload, mode: problem.compare ?? 'float' }, timeoutMs, 'python');
  }

  async run(code: string, func: string, cases: Case[], mode: CompareMode, timeoutMs = 4000, lang: Lang = 'python', spec?: CSpec): Promise<RunResult> {
    try {
      await this.ensure(lang);
    } catch (e) {
      return { kind: 'fail', message: e instanceof Error ? e.message : String(e) };
    }
    return this.exec({ type: 'run', code, func, cases: JSON.stringify(cases.map((c) => ({ args: c.args, expected: c.expected }))), mode, lang, spec: JSON.stringify(spec ?? {}) }, timeoutMs, lang);
  }

  private async exec(msg: Record<string, unknown>, timeoutMs: number, lang: Lang): Promise<RunResult> {
    const started = performance.now();
    const { reply } = this.post(msg);
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
      void this.ensure(lang).catch(() => undefined);
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

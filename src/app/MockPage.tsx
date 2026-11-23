import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Course, MockItem, MockSet } from '../content/types';
import { KIND_LABEL, KIND_TASK } from '../content/types';
import { courseMeta } from '../content';
import { inline } from '../components/Rich';
import { BlankCode, countBlanks, fillBlanks } from '../components/BlankCode';
import { CodeView } from '../components/pyHighlight';
import { ResultsView, type Shown } from '../components/Results';
import { py, type RunResult } from '../grader/client';
import { readDraft, useCourseProgress, writeDraft } from '../features/progress/store';
import type { MockResult, MockState } from '../features/progress/model';
import { changedLines, engineText, fixBlockReason, StatementBody, useEngine } from './solveParts';

const CodeEditor = lazy(() => import('../components/CodeEditor').then((m) => ({ default: m.CodeEditor })));

const tkey = (type: number) => `t${String(type).padStart(2, '0')}`;

function elapsedText(fromIso: string, toMs: number): string {
  const s = Math.max(0, Math.floor((toMs - Date.parse(fromIso)) / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0 ? `${h}시간 ${m}분` : `${m}분 ${String(sec).padStart(2, '0')}초`;
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

interface Props {
  course: Course;
  set: MockSet;
  learnerKey: string;
  remote: boolean;
}

/** 모의고사: 원본 유형 10문제를 중간 점검 없이 실전처럼. 제출 결과는 시험을 끝낸 뒤 공개. */
export function MockPage({ course, set, learnerKey, remote }: Props) {
  const meta = courseMeta(course.id)!;
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const ms = prog.state.mocks?.[set.key];
  const inProgress = !!ms && !ms.endedAt;
  const now = useNow(inProgress);
  const [idx, setIdx] = useState(0);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [confirmRetry, setConfirmRetry] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [idx, ms?.endedAt]);

  const start = (round: number) => {
    prog.updateMock(set.key, () => ({ round, startedAt: new Date().toISOString(), results: {} }));
    setIdx(0);
    setConfirmRetry(false);
  };
  const end = () => {
    prog.updateMock(set.key, (m) => (m ? { ...m, endedAt: m.endedAt ?? new Date().toISOString() } : m!));
    setConfirmEnd(false);
  };
  const record = (type: number, r: Omit<MockResult, 'tries' | 'at'>) =>
    prog.updateMock(set.key, (m) => {
      const base = m!;
      const k = tkey(type);
      const old = base.results[k];
      return { ...base, results: { ...base.results, [k]: { ...r, tries: (old?.tries ?? 0) + 1, at: new Date().toISOString() } } };
    });

  const crumb = (
    <div className="crumb">
      <Link to="/">홈</Link> › <Link to={meta.path}>{meta.name}</Link> › 모의고사 {set.n}회
    </div>
  );

  if (set.items.length === 0)
    return (
      <div className="page narrow">
        {crumb}
        <p className="notice">모의고사 {set.n}회 문제를 준비하고 있어요.</p>
      </div>
    );

  if (!ms)
    return (
      <div className="page narrow">
        {crumb}
        <h1>모의고사 {set.n}회</h1>
        <div className="card" style={{ marginTop: '0.75rem' }}>
          <p>
            <strong>{set.items.length}문항</strong> · {meta.exam} 원본 유형 그대로 · 중간 점검 없이 실전처럼 풀어요.
          </p>
          <ul className="rich" style={{ paddingLeft: '1.2rem' }}>
            <li>‘예시로 실행’으로 예시 결과는 바로 볼 수 있어요.</li>
            <li>‘제출하기’를 누르면 숨은 테스트까지 채점해 두고, 결과는 시험을 끝낸 뒤 한꺼번에 보여 줘요. 여러 번 제출하면 마지막 제출로 채점해요.</li>
            <li>시간 제한은 없고 걸린 시간을 보여 줘요. 다 풀면 ‘시험 끝내기’를 눌러요.</li>
          </ul>
          <button className="btn primary" onClick={() => start(1)}>
            모의고사 {set.n}회 시작하기
          </button>
        </div>
      </div>
    );

  if (ms.endedAt) return <MockResults course={course} set={set} ms={ms} crumb={crumb} confirmRetry={confirmRetry} setConfirmRetry={setConfirmRetry} onRetry={() => start(ms.round + 1)} />;

  const item = set.items[Math.min(idx, set.items.length - 1)];
  const submitted = set.items.filter((it) => ms.results[tkey(it.type.type)]).length;
  return (
    <div className="page">
      {crumb}
      <div className="card mock-bar">
        <strong>모의고사 {set.n}회</strong>
        <span className="faint" aria-live="off">
          걸린 시간 {elapsedText(ms.startedAt, now)}
        </span>
        <span className="faint">
          제출 {submitted}/{set.items.length}
        </span>
        <div className="mock-nav" role="tablist" aria-label="문항">
          {set.items.map((it, i) => (
            <button key={it.problem.id} role="tab" aria-selected={i === idx} className={`${i === idx ? 'cur' : ''} ${ms.results[tkey(it.type.type)] ? 'done' : ''}`} onClick={() => setIdx(i)} title={`${i + 1}번${ms.results[tkey(it.type.type)] ? ' (제출함)' : ''}`}>
              {i + 1}
            </button>
          ))}
        </div>
        {!confirmEnd ? (
          <button className="btn small" onClick={() => setConfirmEnd(true)}>
            시험 끝내기
          </button>
        ) : (
          <span className="row">
            <span className="faint">{submitted < set.items.length ? `제출하지 않은 문항 ${set.items.length - submitted}개는 0점이에요. ` : ''}끝낼까요?</span>
            <button className="btn small primary" onClick={end}>
              네, 끝내고 결과 보기
            </button>
            <button className="btn small ghost" onClick={() => setConfirmEnd(false)}>
              계속 풀기
            </button>
          </span>
        )}
      </div>
      <div className="solve">
        <section className="card statement" aria-label="문제">
          <div className="row" style={{ gap: '0.4rem' }}>
            <span className={`badge ${item.type.kind}`}>{KIND_LABEL[item.type.kind]}</span>
            <span className="faint">
              {idx + 1}번 / {set.items.length}
            </span>
            {ms.results[tkey(item.type.type)] && <span className="badge">제출함</span>}
          </div>
          <h1 style={{ marginTop: '0.4rem' }}>{item.problem.title}</h1>
          <StatementBody problem={item.problem} />
        </section>
        <section aria-label="풀이">
          <MockCodePanel
            key={`${item.problem.id}:${ms.round}`}
            item={item}
            round={ms.round}
            learnerKey={learnerKey}
            submittedTimes={ms.results[tkey(item.type.type)]?.tries ?? 0}
            onSubmit={(r) => record(item.type.type, r)}
            onNext={idx < set.items.length - 1 ? () => setIdx(idx + 1) : null}
          />
          {prog.syncError && <p className="notice warn" style={{ marginTop: '0.75rem' }}>{prog.syncError}</p>}
        </section>
      </div>
    </div>
  );
}

interface CodeProps {
  item: MockItem;
  round: number;
  learnerKey: string;
  submittedTimes: number;
  onSubmit: (r: { score: number; solved: boolean }) => void;
  onNext: (() => void) | null;
}

function MockCodePanel({ item, round, learnerKey, submittedTimes, onSubmit, onNext }: CodeProps) {
  const { problem, type } = item;
  const kind = type.kind;
  const engine = useEngine();
  const dkey = `${problem.id}:r${round}`;
  const draft = useMemo(() => readDraft(learnerKey, dkey, problem.version), [learnerKey, dkey, problem.version]);
  const nBlanks = kind === 'blank' ? countBlanks(problem.code) : 0;
  const [code, setCode] = useState<string>(kind === 'blank' ? problem.code : draft?.code ?? problem.code);
  const [blanks, setBlanks] = useState<string[]>(() => Array.from({ length: nBlanks }, (_, i) => draft?.blanks?.[i] ?? ''));
  const [busy, setBusy] = useState<'run' | 'submit' | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submittedNote, setSubmittedNote] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  useEffect(() => {
    if (kind === 'blank') {
      if (blanks.some((b) => b !== '')) writeDraft(learnerKey, dkey, { ver: problem.version, blanks });
    } else if (code !== problem.code) writeDraft(learnerKey, dkey, { ver: problem.version, code });
  }, [code, blanks, kind, learnerKey, dkey, problem.version, problem.code]);

  const changed = kind === 'fix' ? changedLines(problem.code, code) : null;
  const fullCode = kind === 'blank' ? fillBlanks(problem.code, blanks) : code;

  const precheck = (forSubmit: boolean): string | null => {
    if (kind === 'blank') {
      const empty = blanks.findIndex((b) => b.trim() === '');
      if (empty >= 0) return `빈칸 ${empty + 1}을 채워 주세요.`;
    }
    if (kind === 'fix' && forSubmit) return fixBlockReason(changed);
    return null;
  };

  const run = async () => {
    const block = precheck(false);
    setNotice(block);
    setSubmittedNote(null);
    if (block) return;
    setBusy('run');
    const result = await py().run(fullCode, problem.funcName, problem.examples, problem.compare ?? 'exact', 5000);
    setBusy(null);
    setShown({ mode: 'run', result, exampleCount: problem.examples.length });
  };

  const submit = async () => {
    const block = precheck(true);
    setNotice(block);
    if (block) return;
    setBusy('submit');
    const cases = [...problem.examples, ...problem.tests];
    const result: RunResult = await py().run(fullCode, problem.funcName, cases, problem.compare ?? 'exact', 9000);
    setBusy(null);
    if (result.kind === 'fail') {
      setNotice(`채점하지 못했어요: ${result.message} 다시 제출해 주세요.`);
      return;
    }
    const pass = result.kind === 'done' && !result.out.compile ? result.out.results.filter((r) => r.ok).length : 0;
    const score = Math.round((pass / cases.length) * 100);
    onSubmit({ score, solved: pass === cases.length });
    setShown(null);
    setSubmittedNote(`제출했어요(${submittedTimes + 1}번째). 결과는 시험을 끝내면 보여요. 다시 제출하면 마지막 제출로 채점해요.`);
  };

  return (
    <div className="card">
      <div className="code-head">
        <span className={`badge ${kind}`}>{KIND_LABEL[kind]}</span>
        <span className="task">{KIND_TASK[kind]}</span>
      </div>
      {kind === 'blank' ? (
        <BlankCode code={problem.code} values={blanks} onChange={(i, v) => setBlanks((old) => old.map((x, j) => (j === i ? v : x)))} disabled={busy !== null} />
      ) : (
        <Suspense fallback={<div className="code-box" style={{ minHeight: '14rem', padding: '1rem' }} role="status">편집기 불러오는 중…</div>}>
          <CodeEditor value={code} onChange={setCode} changedLines={changed ?? undefined} label={kind === 'fix' ? '한 줄 수정 코드 편집기' : '함수 작성 코드 편집기'} />
        </Suspense>
      )}
      {kind === 'fix' && (
        <p className={`diff-note${changed === null || (changed && changed.length > 1) ? ' bad' : ''}`}>
          {changed === null ? '줄 수가 처음 코드와 달라요(줄을 더하거나 지우지 마세요).' : changed.length === 0 ? '고친 줄: 없음' : `고친 줄: ${changed.join(', ')}번째 줄${changed.length > 1 ? ' — 한 줄만 고쳐야 해요' : ''}`}
        </p>
      )}
      <div className="actions">
        <button className="btn" onClick={() => void run()} disabled={busy !== null}>
          {busy === 'run' ? '실행 중…' : '▶ 예시로 실행'}
        </button>
        <button className="btn primary" onClick={() => void submit()} disabled={busy !== null}>
          {busy === 'submit' ? '제출 중…' : '제출하기'}
        </button>
        {!confirmReset ? (
          <button className="btn ghost" onClick={() => setConfirmReset(true)} disabled={busy !== null}>
            처음 코드로
          </button>
        ) : (
          <span className="row">
            <span className="faint">지금 코드를 지울까요?</span>
            <button
              className="btn small"
              onClick={() => {
                setCode(problem.code);
                setBlanks(Array.from({ length: nBlanks }, () => ''));
                writeDraft(learnerKey, dkey, { ver: problem.version });
                setShown(null);
                setNotice(null);
                setConfirmReset(false);
              }}
            >
              네, 처음으로
            </button>
            <button className="btn small ghost" onClick={() => setConfirmReset(false)}>
              아니요
            </button>
          </span>
        )}
      </div>
      <p className="engine" aria-live="polite">
        {engineText(engine)}
      </p>
      {notice && (
        <p className="notice warn" role="alert">
          {notice}
        </p>
      )}
      {submittedNote && (
        <div className="notice ok" role="status">
          {submittedNote}
          {onNext && (
            <div style={{ marginTop: '0.4rem' }}>
              <button className="btn small primary" onClick={onNext}>
                다음 문항 →
              </button>
            </div>
          )}
        </div>
      )}
      {shown && <ResultsView shown={shown} problem={problem} />}
    </div>
  );
}

function MockResults({ course, set, ms, crumb, confirmRetry, setConfirmRetry, onRetry }: { course: Course; set: MockSet; ms: MockState; crumb: React.ReactNode; confirmRetry: boolean; setConfirmRetry: (v: boolean) => void; onRetry: () => void }) {
  const meta = courseMeta(course.id)!;
  const [open, setOpen] = useState<string | null>(null);
  const rows = set.items.map((it) => ({ it, r: ms.results[tkey(it.type.type)] }));
  const solved = rows.filter((x) => x.r?.solved).length;
  const avg = Math.round(rows.reduce((n, x) => n + (x.r?.score ?? 0), 0) / rows.length);
  return (
    <div className="page narrow">
      {crumb}
      <h1>모의고사 {set.n}회 결과</h1>
      <div className="card" style={{ marginTop: '0.75rem' }}>
        <div className="row" style={{ gap: '1.5rem' }}>
          <div>
            <div className="faint">해결한 문항</div>
            <div className="mock-big">
              {solved}
              <small>/{rows.length}</small>
            </div>
          </div>
          <div>
            <div className="faint">테스트 통과율(평균)</div>
            <div className="mock-big">
              {avg}
              <small>%</small>
            </div>
          </div>
          <div>
            <div className="faint">걸린 시간</div>
            <div className="mock-big small-big">{elapsedText(ms.startedAt, Date.parse(ms.endedAt!))}</div>
          </div>
        </div>
        <p className="faint" style={{ margin: '0.6rem 0 0' }}>
          문항마다 마지막 제출을 예시 + 숨은 테스트로 채점했어요. 연습용 결과이며 실제 시험 점수 계산과는 달라요.
        </p>
      </div>
      <div className="scroll-x card" style={{ padding: 0, marginTop: '0.75rem' }}>
        <table className="t-table mock-table">
          <thead>
            <tr>
              <th>번호</th>
              <th>유형</th>
              <th>형식</th>
              <th>통과율</th>
              <th>결과</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map(({ it, r }, i) => (
              <tr key={it.problem.id}>
                <td>{i + 1}</td>
                <td className="name">{it.type.typeTitle}</td>
                <td>{KIND_LABEL[it.type.kind]}</td>
                <td>{r ? `${r.score}%` : '-'}</td>
                <td>{!r ? <span className="faint">제출 안 함</span> : r.solved ? <span className="pass">해결</span> : <span className="fail">미해결</span>}</td>
                <td>
                  <button className="btn small ghost" aria-expanded={open === it.problem.id} onClick={() => setOpen(open === it.problem.id ? null : it.problem.id)}>
                    {open === it.problem.id ? '접기' : '해설'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.map(({ it }, i) =>
        open === it.problem.id ? (
          <div key={it.problem.id} className="card" style={{ marginTop: '0.75rem' }}>
            <h2>
              {i + 1}번 {it.problem.title}
            </h2>
            <p>{inline(it.problem.explain)}</p>
            <h3 style={{ marginTop: '0.6rem' }}>모범 답안</h3>
            <CodeView code={it.problem.solution} />
            <p style={{ marginTop: '0.6rem' }}>
              <Link to={`${meta.path}/${it.type.problems[0]?.id ?? ''}`.replace(/\/$/, '')} className="btn small">
                이 유형 연습 문제 풀기 →
              </Link>
            </p>
          </div>
        ) : null,
      )}
      <div className="actions" style={{ marginTop: '1rem' }}>
        <Link className="btn" to={meta.path}>
          과정으로
        </Link>
        {!confirmRetry ? (
          <button className="btn ghost" onClick={() => setConfirmRetry(true)}>
            다시 풀기
          </button>
        ) : (
          <span className="row">
            <span className="faint">이번 결과를 지우고 처음부터 다시 풀까요?</span>
            <button className="btn small primary" onClick={onRetry}>
              네, 다시 풀기
            </button>
            <button className="btn small ghost" onClick={() => setConfirmRetry(false)}>
              아니요
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

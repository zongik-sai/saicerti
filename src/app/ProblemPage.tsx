import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Course, Lang, Problem, TypeFile } from '../content/types';
import { KIND_LABEL, KIND_TASK } from '../content/types';
import { courseMeta } from '../content';
import { inline } from '../components/Rich';
import { StepView } from '../components/Steps';
import { BlankCode, countBlanks, fillBlanks } from '../components/BlankCode';
import { CodeView } from '../components/pyHighlight';
import { ResultsView, type Shown } from '../components/Results';
import { py } from '../grader/client';
import { changedLines, engineText, fixBlockReason, StatementBody, useEngine } from './solveParts';
import { clearDraft, readDraft, useCourseProgress, writeDraft } from '../features/progress/store';
import type { ProbState } from '../features/progress/model';

// 코드 편집기(CodeMirror)는 코드 풀이를 열 때만 불러온다
const CodeEditor = lazy(() => import('../components/CodeEditor').then((m) => ({ default: m.CodeEditor })));

interface Props {
  course: Course;
  type: TypeFile;
  problem: Problem;
  index: number;
  /** [심화] 문제 */
  adv?: boolean;
  learnerKey: string;
  remote: boolean;
}

export function ProblemPage({ course, type, problem, index, adv = false, learnerKey, remote }: Props) {
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const raw = prog.state.probs[problem.id];
  const ps: ProbState | undefined = raw && raw.ver === problem.version ? raw : raw ? { ...raw, steps: [], stepsDone: false, revealed: [] } : undefined;
  const stepsDone = !!ps?.stepsDone;
  const doneSteps = new Set(ps?.steps ?? []);
  const firstOpen = problem.steps.findIndex((s) => !doneSteps.has(s.id));
  const [tab, setTab] = useState<'steps' | 'code'>(stepsDone ? 'code' : 'steps');
  const [stepIdx, setStepIdx] = useState(firstOpen < 0 ? 0 : firstOpen);
  const meta = courseMeta(course.id)!;
  const navigate = useNavigate();
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 다른 문제로 이동하면 처음 상태로
    setTab(stepsDone ? 'code' : 'steps');
    setStepIdx(firstOpen < 0 ? 0 : firstOpen);
    window.scrollTo(0, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [problem.id]);

  const update = (fn: (p: ProbState) => ProbState) => prog.update(problem.id, problem.version, fn);

  const markStep = (sid: string, revealed: boolean) =>
    update((p) => {
      const steps = [...new Set([...p.steps, sid])];
      const all = problem.steps.every((s) => steps.includes(s.id));
      return { ...p, steps, stepsDone: p.stepsDone || all, revealed: revealed ? [...new Set([...(p.revealed ?? []), sid])] : p.revealed };
    });

  const next = nextProblem(course, type, index, adv);
  const tier = adv ? '심화' : '기본';
  // 기본 5문제를 모두 풀면 과정 화면에서 [심화]를 열 수 있다고 알려 준다
  const advHint = !adv && !!type.adv?.problems.length && type.problems.every((p) => prog.state.probs[p.id]?.solved) && !prog.state.advOpen?.includes(`t${String(type.type).padStart(2, '0')}`);
  // 한 문제 안에서는 중간 점검 단계와 코드 풀이를 자유롭게 오간다(선생님 요청 2026-11-26). 진도 표시(✓)는 맞힌 단계에만
  const goNext = () => {
    if (stepIdx >= problem.steps.length - 1) setTab('code');
    else setStepIdx(stepIdx + 1);
  };

  return (
    <div className="page" ref={topRef}>
      <div className="crumb">
        <Link to="/">홈</Link> › <Link to={meta.path}>{meta.name}</Link> › 유형 {type.type}. {type.typeTitle} › [{tier}] {index + 1}
      </div>
      <div className="solve">
        <section className="card statement" aria-label="문제">
          <div className="row" style={{ gap: '0.4rem' }}>
            {adv && <span className="badge adv">[심화] 선택</span>}
            <span className={`badge ${type.kind}`}>{KIND_LABEL[type.kind]}</span>
            <span className="faint">
              유형 {type.type} · {tier} {index + 1}/5
            </span>
            {ps?.solved && <span className="badge write">해결</span>}
          </div>
          <h1 style={{ marginTop: '0.4rem' }}>{problem.title}</h1>
          <StatementBody problem={problem} lang={type.lang ?? 'python'} />
        </section>

        <section aria-label="풀이">
          <div className="panel-tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'steps'} className={`panel-tab${stepsDone ? ' done' : ''}`} onClick={() => setTab('steps')}>
              <span className="num">{stepsDone ? '✓' : '1'}</span> 중간 점검
              <small>
                {doneSteps.size > problem.steps.length ? problem.steps.length : problem.steps.filter((s) => doneSteps.has(s.id)).length}/{problem.steps.length}
              </small>
            </button>
            <button role="tab" aria-selected={tab === 'code'} className={`panel-tab${ps?.solved ? ' done' : ''}`} onClick={() => setTab('code')}>
              <span className="num">{ps?.solved ? '✓' : '2'}</span> 코드 풀이
              <small>{ps?.solved ? '해결' : ''}</small>
            </button>
          </div>

          {tab === 'steps' && (
            <>
              <div className="stepper" aria-label="중간 점검 단계">
                {problem.steps.map((s, i) => (
                  <button key={s.id} className={`${i === stepIdx ? 'cur' : ''} ${doneSteps.has(s.id) ? 'done' : ''}`} aria-current={i === stepIdx ? 'step' : undefined} aria-label={`중간 점검 ${i + 1}단계${doneSteps.has(s.id) ? ' (맞힘)' : ''}`} onClick={() => setStepIdx(i)}>
                    {i + 1}
                  </button>
                ))}
              </div>
              <StepView
                seed={problem.id}
                figures={problem.figures}
                lang={type.lang ?? 'python'}
                key={`${problem.id}-${problem.steps[stepIdx].id}`}
                step={problem.steps[stepIdx]}
                index={stepIdx}
                total={problem.steps.length}
                done={doneSteps.has(problem.steps[stepIdx].id)}
                revealed={!!ps?.revealed?.includes(problem.steps[stepIdx].id)}
                onCorrect={() => markStep(problem.steps[stepIdx].id, false)}
                onReveal={() => markStep(problem.steps[stepIdx].id, true)}
                isLast={stepIdx === problem.steps.length - 1}
                onNext={goNext}
              />
              <div className="step-nav">
                <button className="btn small ghost" onClick={() => setStepIdx(stepIdx - 1)} disabled={stepIdx === 0}>
                  ← 이전 단계
                </button>
                {!doneSteps.has(problem.steps[stepIdx].id) && (
                  <button className="btn small ghost" onClick={goNext}>
                    {stepIdx >= problem.steps.length - 1 ? '코드 풀이 보기 →' : '다음 단계 보기 →'}
                  </button>
                )}
              </div>
            </>
          )}

          {tab === 'code' && (
            <>
              {!stepsDone && !ps?.solved && (
                <p className="notice" style={{ marginTop: 0 }}>
                  중간 점검을 먼저 풀어 보면 코드가 훨씬 쉬워져요 ({problem.steps.filter((x) => doneSteps.has(x.id)).length}/{problem.steps.length}단계 맞힘).{' '}
                  <button className="btn small ghost" onClick={() => setTab('steps')}>
                    중간 점검 보기
                  </button>
                </p>
              )}
              <CodePanel
                key={problem.id}
                problem={problem}
                kind={type.kind}
                lang={type.lang ?? 'python'}
                learnerKey={learnerKey}
                ps={ps}
                update={update}
                nextPath={next ? `${meta.path}/${next}` : null}
                onNext={() => next && navigate(`${meta.path}/${next}`)}
                homePath={meta.path}
                advHint={advHint}
              />
            </>
          )}
          {prog.syncError && <p className="notice warn" style={{ marginTop: '0.75rem' }}>{prog.syncError}</p>}
        </section>
      </div>
    </div>
  );
}

function nextProblem(course: Course, type: TypeFile, index: number, adv: boolean): string | null {
  // 심화는 같은 유형의 다음 심화로(심화 5 다음은 과정 화면)
  if (adv) {
    const list = type.adv?.problems ?? [];
    return index + 1 < list.length ? list[index + 1].id : null;
  }
  if (index + 1 < type.problems.length) return type.problems[index + 1].id;
  const ti = course.types.findIndex((t) => t.type === type.type);
  const nt = course.types[ti + 1];
  return nt ? nt.problems[0].id : null;
}

interface CodeProps {
  problem: Problem;
  kind: TypeFile['kind'];
  lang: Lang;
  learnerKey: string;
  ps: ProbState | undefined;
  update: (fn: (p: ProbState) => ProbState) => void;
  nextPath: string | null;
  onNext: () => void;
  homePath: string;
  advHint: boolean;
}

function CodePanel({ problem, kind, lang, learnerKey, ps, update, nextPath, onNext, homePath, advHint }: CodeProps) {
  const engine = useEngine(lang);
  const draft = useMemo(() => readDraft(learnerKey, problem.id, problem.version), [learnerKey, problem.id, problem.version]);
  const nBlanks = kind === 'blank' ? countBlanks(problem.code) : 0;
  const [code, setCode] = useState<string>(kind === 'blank' ? problem.code : draft?.code ?? problem.code);
  const [blanks, setBlanks] = useState<string[]>(() => {
    const b = draft?.blanks ?? [];
    return Array.from({ length: nBlanks }, (_, i) => b[i] ?? '');
  });
  const [busy, setBusy] = useState<'run' | 'submit' | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [confirmAnswer, setConfirmAnswer] = useState(false);
  const [showAnswer, setShowAnswer] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);

  // 코드 초안은 바뀔 때마다 이 기기에 저장(새로고침·탭 닫기에도 남게)
  useEffect(() => {
    if (kind === 'blank') {
      if (blanks.some((b) => b !== '')) writeDraft(learnerKey, problem.id, { ver: problem.version, blanks });
    } else if (code !== problem.code) writeDraft(learnerKey, problem.id, { ver: problem.version, code });
  }, [code, blanks, kind, learnerKey, problem.id, problem.version, problem.code]);

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

  const go = async (mode: 'run' | 'submit') => {
    const block = precheck(mode === 'submit');
    setNotice(block);
    if (block) return;
    setBusy(mode);
    const cases = mode === 'run' ? problem.examples : [...problem.examples, ...problem.tests];
    const result = await py().run(fullCode, problem.funcName, cases, problem.compare ?? 'exact', mode === 'run' ? 5000 : 9000, lang, problem.cspec);
    setBusy(null);
    setShown({ mode, result, exampleCount: problem.examples.length });
    if (mode === 'submit') {
      const solved = result.kind === 'done' && !result.out.compile && result.out.results.every((r) => r.ok);
      update((p) => ({ ...p, tries: p.tries + 1, solved: p.solved || solved, solvedAt: p.solvedAt ?? (solved ? new Date().toISOString() : undefined) }));
    }
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 50);
  };

  const reset = () => {
    setCode(problem.code);
    setBlanks(Array.from({ length: nBlanks }, () => ''));
    clearDraft(learnerKey, problem.id);
    setShown(null);
    setNotice(null);
    setConfirmReset(false);
  };

  const solvedNow = !!ps?.solved;

  return (
    <div className="card">
      <div className="code-head">
        <span className={`badge ${kind}`}>{KIND_LABEL[kind]}</span>
        <span className="task">{KIND_TASK[kind]}</span>
      </div>
      {kind === 'blank' ? (
        <BlankCode lang={lang} code={problem.code} values={blanks} onChange={(i, v) => setBlanks((old) => old.map((x, j) => (j === i ? v : x)))} disabled={busy !== null} />
      ) : (
        <Suspense fallback={<div className="code-box" style={{ minHeight: '14rem', padding: '1rem' }} role="status">편집기 불러오는 중…</div>}>
          <CodeEditor lang={lang} value={code} onChange={setCode} changedLines={changed ?? undefined} label={kind === 'fix' ? '한 줄 수정 코드 편집기' : '함수 작성 코드 편집기'} />
        </Suspense>
      )}
      {kind === 'fix' && (
        <p className={`diff-note${changed === null || (changed && changed.length > 1) ? ' bad' : ''}`}>
          {changed === null ? '줄 수가 처음 코드와 달라요(줄을 더하거나 지우지 마세요).' : changed.length === 0 ? '고친 줄: 없음' : `고친 줄: ${changed.join(', ')}번째 줄${changed.length > 1 ? ' — 한 줄만 고쳐야 해요' : ''}`}
        </p>
      )}
      <div className="actions">
        <button className="btn" onClick={() => void go('run')} disabled={busy !== null}>
          {busy === 'run' ? '실행 중…' : '▶ 예시로 실행'}
        </button>
        <button className="btn primary" onClick={() => void go('submit')} disabled={busy !== null}>
          {busy === 'submit' ? '채점 중…' : '채점하기'}
        </button>
        {!confirmReset ? (
          <button className="btn ghost" onClick={() => setConfirmReset(true)} disabled={busy !== null}>
            처음 코드로
          </button>
        ) : (
          <span className="row">
            <span className="faint">지금 코드를 지울까요?</span>
            <button className="btn small" onClick={reset}>
              네, 처음으로
            </button>
            <button className="btn small ghost" onClick={() => setConfirmReset(false)}>
              아니요
            </button>
          </span>
        )}
      </div>
      <p className="engine" aria-live="polite">
        {engineText(engine, lang)}
      </p>
      {notice && (
        <p className="notice warn" role="alert">
          {notice}
        </p>
      )}
      <div ref={resultsRef}>{shown && <ResultsView shown={shown} problem={problem} lang={lang} />}</div>

      {solvedNow && (
        <div className="solved-box">
          <h3>🎉 해결했어요!</h3>
          <p>{inline(problem.explain)}</p>
          <div className="row">
            <button className="btn small" onClick={() => setShowAnswer((v) => !v)}>
              {showAnswer ? '모범 답안 접기' : '모범 답안 보기'}
            </button>
            {nextPath ? (
              <button className="btn small primary" onClick={onNext}>
                다음 문제 →
              </button>
            ) : (
              <Link to={homePath} className="btn small primary">
                과정 화면으로
              </Link>
            )}
          </div>
          {advHint && (
            <p className="notice adv-hint">
              이 유형의 기본 5문제를 모두 풀었어요! <Link to={homePath}>과정 화면</Link>에서 <b>[심화] 열기</b>를 누르면 더 어려운 문제에 도전할 수 있어요(선택).
            </p>
          )}
          {showAnswer && <CodeView lang={lang} code={problem.solution} />}
        </div>
      )}
      {!solvedNow && (ps?.tries ?? 0) >= 3 && (
        <div style={{ marginTop: '0.8rem' }}>
          {!showAnswer && !confirmAnswer && (
            <button className="btn small ghost" onClick={() => setConfirmAnswer(true)}>
              막혔어요 · 해설과 모범 답안 보기
            </button>
          )}
          {confirmAnswer && !showAnswer && (
            <span className="row">
              <span className="faint">답을 보면 ‘답을 보고 풂’으로 기록돼요. 볼까요?</span>
              <button
                className="btn small"
                onClick={() => {
                  setShowAnswer(true);
                  update((p) => ({ ...p, sawAnswerAt: p.sawAnswerAt ?? new Date().toISOString() }));
                }}
              >
                볼게요
              </button>
              <button className="btn small ghost" onClick={() => setConfirmAnswer(false)}>
                조금 더 해 볼게요
              </button>
            </span>
          )}
          {showAnswer && (
            <div className="explain revealed">
              <p style={{ margin: 0 }}>{inline(problem.explain)}</p>
              <CodeView lang={lang} code={problem.solution} />
              <p className="faint" style={{ margin: '0.4rem 0 0' }}>
                답을 보고 직접 다시 입력해 채점해 보세요.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

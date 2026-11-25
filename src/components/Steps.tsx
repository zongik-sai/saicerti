import { useEffect, useState } from 'react';
import type { Figure, InputCell, Lang, Step, TableCell } from '../content/types';
import { cellOk } from '../lib/pyrepr';
import { inline, Rich } from './Rich';

const KIND: Record<Step['kind'], string> = { mcq: '객관식', table: '표 채우기', short: '단답' };
const REVEAL_AFTER = 3;

interface Props {
  /** 보기 섞기 씨앗(문제 id) */
  seed: string;
  figures?: Figure[];
  lang?: Lang;
  step: Step;
  index: number;
  total: number;
  done: boolean;
  revealed: boolean;
  onCorrect: () => void;
  onReveal: () => void;
  onNext: () => void;
  isLast: boolean;
}

const isInput = (c: TableCell): c is InputCell => typeof c === 'object' && c !== null;

/** 질문·해설이 보기 위치(②, 두 번째 보기 등)를 말하면 순서를 바꾸지 않는다 */
export const refersToPosition = (text: string) => /[①②③④⑤]|번째 보기|마지막 보기|첫 보기/.test(text);

/** 보기 순서: 위치를 말하는 문항은 그대로, 모두 숫자면 작은 순, 아니면 문제·단계마다 고정된 순서로 섞는다(정답이 늘 ①에 있지 않게). */
export function optionOrder(options: string[], seed: string, fixed = false): number[] {
  const idx = options.map((_, i) => i);
  if (fixed) return idx;
  if (options.every((o) => /^-?\d+(\.\d+)?$/.test(o.trim()))) return idx.sort((a, b) => Number(options[a]) - Number(options[b]));
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619) >>> 0;
  for (let i = idx.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
    const j = h % (i + 1);
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx;
}

/** 중간 점검 한 단계. 맞히면 ✓(세 번 틀리면 정답 보기). 단계 이동은 문제 화면에서 자유롭게 한다. */
export function StepView(p: Props) {
  return (
    <div className="card" aria-live="polite">
      <div className="step-kind">
        중간 점검 {p.index + 1}/{p.total} · {KIND[p.step.kind]}
      </div>
      {p.step.kind === 'mcq' && <Mcq {...p} step={p.step} />}
      {p.step.kind === 'table' && <Table {...p} step={p.step} />}
      {p.step.kind === 'short' && <Short {...p} step={p.step} />}
    </div>
  );
}

function Footer({ ok, revealed, explain, wrong, onReveal, onNext, isLast, onCheck, canCheck }: { ok: boolean; revealed: boolean; explain: string; wrong: number; onReveal: () => void; onNext: () => void; isLast: boolean; onCheck: () => void; canCheck: boolean }) {
  return (
    <>
      {!ok && wrong > 0 && <p className="feedback bad">다시 생각해 보세요. ({wrong}번 틀림)</p>}
      {ok && (
        <div className={`explain${revealed ? ' revealed' : ''}`}>
          <strong>{revealed ? '정답을 확인했어요. ' : '맞았어요! '}</strong>
          {inline(explain)}
        </div>
      )}
      <div className="actions">
        {!ok && (
          <button className="btn primary" onClick={onCheck} disabled={!canCheck}>
            확인
          </button>
        )}
        {!ok && wrong >= REVEAL_AFTER && (
          <button className="btn ghost" onClick={onReveal}>
            정답 보기
          </button>
        )}
        {ok && (
          <button className="btn primary" onClick={onNext}>
            {isLast ? '코드 풀러 가기 →' : '다음 단계 →'}
          </button>
        )}
      </div>
    </>
  );
}

function Mcq({ step, seed, figures, done, revealed, onCorrect, onReveal, onNext, isLast }: Props & { step: Extract<Step, { kind: 'mcq' }> }) {
  const order = optionOrder(step.options, `${seed}:${step.id}`, refersToPosition(step.q + step.explain));
  const [sel, setSel] = useState<number | null>(done ? step.answer : null);
  const [wrongPick, setWrongPick] = useState<number | null>(null);
  const [wrong, setWrong] = useState(0);
  useEffect(() => {
    setSel(done ? step.answer : null);
    setWrong(0);
    setWrongPick(null);
  }, [step.id, step.answer, done]);
  const ok = done;
  const check = () => {
    if (sel === null) return;
    if (sel === step.answer) {
      setWrongPick(null);
      onCorrect();
    } else {
      setWrongPick(sel);
      setWrong((w) => w + 1);
    }
  };
  return (
    <>
      <div className="step-q">
        <Rich text={step.q} figures={figures} />
      </div>
      <div className="opts" role="radiogroup" aria-label="보기">
        {order.map((i, pos) => {
          const o = step.options[i];
          const cls = ok && i === step.answer ? 'right' : wrongPick === i ? 'wrong' : sel === i ? 'sel' : '';
          return (
            <button
              key={i}
              role="radio"
              aria-checked={sel === i}
              className={`opt ${cls}`}
              disabled={ok}
              onClick={() => {
                setSel(i);
                setWrongPick(null);
              }}
            >
              <span className="mk">{'①②③④⑤'[pos]}</span>
              <span>{/[=()[\]:%]|\b(if|for|return|def)\b/.test(o) && !/[가-힣]/.test(o) ? <code>{o}</code> : inline(o)}</span>
            </button>
          );
        })}
      </div>
      <Footer ok={ok} revealed={revealed} explain={step.explain} wrong={wrong} onReveal={onReveal} onNext={onNext} isLast={isLast} onCheck={check} canCheck={sel !== null} />
    </>
  );
}

function Table({ step, figures, lang, done, revealed, onCorrect, onReveal, onNext, isLast }: Props & { step: Extract<Step, { kind: 'table' }> }) {
  const cells: InputCell[] = step.rows.flat().filter(isInput);
  const [vals, setVals] = useState<string[]>(() => (done ? cells.map((c) => c.a) : cells.map(() => '')));
  const [marks, setMarks] = useState<(boolean | null)[]>(() => cells.map(() => null));
  const [wrong, setWrong] = useState(0);
  useEffect(() => {
    setVals(done ? cells.map((c) => c.a) : cells.map(() => ''));
    setMarks(cells.map(() => null));
    setWrong(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step.id, done]);
  const check = () => {
    const m = cells.map((c, i) => cellOk(vals[i] ?? '', c.a, c.alts));
    setMarks(m);
    if (m.every(Boolean)) onCorrect();
    else setWrong((w) => w + 1);
  };
  let k = -1;
  return (
    <>
      {step.title && <h3 style={{ marginTop: '0.3rem' }}>{step.title}</h3>}
      <div className="step-q">
        <Rich text={step.prompt} figures={figures} />
      </div>
      <div className="scroll-x">
        <table className="trace">
          <thead>
            <tr>
              {step.columns.map((c, i) => (
                <th key={i} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {step.rows.map((r, ri) => (
              <tr key={ri}>
                {r.map((c, ci) => {
                  if (!isInput(c)) return <td key={ci}>{c}</td>;
                  k++;
                  const idx = k;
                  const mk = done ? true : marks[idx];
                  return (
                    <td key={ci}>
                      <input
                        aria-label={`${ri + 1}행 ${step.columns[ci]}`}
                        className={mk === true ? 'right' : mk === false ? 'wrong' : ''}
                        value={vals[idx] ?? ''}
                        disabled={done}
                        spellCheck={false}
                        autoCapitalize="off"
                        autoComplete="off"
                        style={{ width: `${Math.max(4.2, (vals[idx]?.length ?? 0) + 1.5)}ch` }}
                        onChange={(e) => {
                          const v = e.target.value;
                          setVals((old) => old.map((x, j) => (j === idx ? v : x)));
                          setMarks((old) => old.map((x, j) => (j === idx ? null : x)));
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') check();
                        }}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!done && <p className="faint">{lang === 'c' ? "참/거짓은 1·0, 문자는 작은따옴표('a'), 문자열은 큰따옴표(\"ab\")로 써요." : "참/거짓은 True·False, 글자는 따옴표('a')로 써요."} 빈칸 없이 모두 채운 뒤 확인을 눌러요.</p>}
      <Footer ok={done} revealed={revealed} explain={step.explain} wrong={wrong} onReveal={onReveal} onNext={onNext} isLast={isLast} onCheck={check} canCheck={vals.every((v) => v.trim() !== '')} />
    </>
  );
}

function Short({ step, figures, done, revealed, onCorrect, onReveal, onNext, isLast }: Props & { step: Extract<Step, { kind: 'short' }> }) {
  const [v, setV] = useState(done ? step.a : '');
  const [mark, setMark] = useState<boolean | null>(null);
  const [wrong, setWrong] = useState(0);
  useEffect(() => {
    setV(done ? step.a : '');
    setMark(null);
    setWrong(0);
  }, [step.id, step.a, done]);
  const check = () => {
    const ok = cellOk(v, step.a, step.alts);
    setMark(ok);
    if (ok) onCorrect();
    else setWrong((w) => w + 1);
  };
  return (
    <>
      <div className="step-q">
        <Rich text={step.q} figures={figures} />
      </div>
      <input
        className={`short-input ${done || mark === true ? 'right' : mark === false ? 'wrong' : ''}`}
        aria-label="답"
        value={v}
        disabled={done}
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        onChange={(e) => {
          setV(e.target.value);
          setMark(null);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && v.trim()) check();
        }}
      />
      <Footer ok={done} revealed={revealed} explain={step.explain} wrong={wrong} onReveal={onReveal} onNext={onNext} isLast={isLast} onCheck={check} canCheck={v.trim() !== ''} />
    </>
  );
}

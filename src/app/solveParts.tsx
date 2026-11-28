import { useEffect, useState } from 'react';
import type { Lang, Problem } from '../content/types';
import { Bullets, Rich, inline } from '../components/Rich';
import { ExamplesTable } from '../components/Results';
import { py, type EngineStatus } from '../grader/client';

/** 채점기 상태(화면에 들어오면 미리 불러 둔다). C 과정이면 C 채점기까지 */
export function useEngine(lang: Lang = 'python'): EngineStatus {
  const [s, setS] = useState<EngineStatus>(py().status);
  useEffect(() => {
    const off = py().subscribe(setS);
    setS(py().status);
    void py()
      .ensure(lang)
      .catch(() => undefined);
    return off;
  }, [lang]);
  return s;
}

export const engineText = (engine: EngineStatus, lang: Lang = 'python', data = false) => {
  const name = lang === 'c' ? 'C 채점기' : data ? '파이썬·pandas' : '파이썬';
  const obj = lang === 'c' ? 'C 채점기를' : '파이썬을';
  return engine === 'loading'
    ? `${name} 준비 중… (처음 한 번은 약 ${data ? '15~40' : '10'}MB를 내려받아요)`
    : engine === 'error'
      ? `${obj} 불러오지 못했어요. 인터넷을 확인하고 실행을 다시 눌러 보세요.`
      : engine === 'ready'
        ? `${name} 준비됨 · 코드는 이 브라우저 안에서만 실행돼요`
        : '';
};

/** 처음 코드와 다른 줄 번호(1부터). 줄 수가 다르면 null */
export function changedLines(orig: string, now: string): number[] | null {
  const a = orig.replace(/\s+$/, '').split('\n').map((l) => l.replace(/\s+$/, ''));
  const b = now.replace(/\s+$/, '').split('\n').map((l) => l.replace(/\s+$/, ''));
  if (a.length !== b.length) return null;
  const out: number[] = [];
  a.forEach((l, i) => {
    if (l !== b[i]) out.push(i + 1);
  });
  return out;
}

/** 한 줄 수정 문제: 채점 전에 바꾼 줄이 정확히 한 줄인지 */
export function fixBlockReason(changed: number[] | null): string | null {
  if (changed === null) return '줄을 더하거나 지우면 안 돼요. 틀린 한 줄만 고쳐 주세요(‘처음 코드로’로 되돌릴 수 있어요).';
  if (changed.length === 0) return '아직 고친 줄이 없어요. 틀린 한 줄을 찾아 고쳐 주세요.';
  if (changed.length > 1) return `${changed.length}줄을 바꿨어요(${changed.join(', ')}번째 줄). 한 줄만 고쳐야 채점할 수 있어요.`;
  return null;
}

/** 시험지 형식: 문제 설명 · 매개변수 설명 · return 값 설명 · 예시 */
export function StatementBody({ problem, lang = 'python' }: { problem: Problem; lang?: Lang }) {
  return (
    <>
      <div className="sec">
        <h3>문제 설명</h3>
        <Rich text={problem.statement} figures={problem.figures} />
      </div>
      <div className="sec">
        <h3>매개변수 설명</h3>
        <Bullets items={problem.params} />
      </div>
      <div className="sec">
        <h3>return 값 설명</h3>
        <Bullets items={problem.returns} />
      </div>
      <div className="sec">
        <h3>예시</h3>
        <ExamplesTable problem={problem} lang={lang} />
        {problem.examples.some((e) => e.explain) && (
          <div style={{ marginTop: '0.5rem' }}>
            {problem.examples.map((e, i) =>
              e.explain ? (
                <p key={i} className="muted" style={{ fontSize: '0.92rem' }}>
                  <strong>예시 {i + 1} 설명</strong> {inline(e.explain)}
                </p>
              ) : null,
            )}
          </div>
        )}
      </div>
    </>
  );
}

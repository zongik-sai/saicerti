import type { Example, Lang, Problem } from '../content/types';
import type { PyError, RunResult } from '../grader/client';
import { reprFor, reprPretty } from '../lib/pyrepr';

export function ExamplesTable({ problem, lang = 'python' }: { problem: Problem; lang?: Lang }) {
  return (
    <div className="scroll-x">
      <table className="ex-table">
        <thead>
          <tr>
            {problem.argNames.map((a) => (
              <th key={a} scope="col">
                {a}
              </th>
            ))}
            <th scope="col">return</th>
          </tr>
        </thead>
        <tbody>
          {problem.examples.map((ex: Example, i) => (
            <tr key={i}>
              {ex.args.map((a, j) => (
                <td key={j}>
                  <pre>{reprPretty(lang, a)}</pre>
                </td>
              ))}
              <td>
                <pre>{reprPretty(lang, ex.expected)}</pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ErrorBox({ e, title }: { e: PyError; title: string }) {
  return (
    <div className="err-box" role="alert">
      <strong>{title}</strong>
      {e.line ? <span> · {e.line}번째 줄</span> : null}
      {e.hint && <div>{e.hint}</div>}
      <pre>{e.message}</pre>
    </div>
  );
}

export interface Shown {
  mode: 'run' | 'submit';
  result: RunResult;
  exampleCount: number;
  blocked?: string;
}

/** 실행(예시) / 채점(전체) 결과 */
export function ResultsView({ shown, problem, lang = 'python', submitLabel = '채점하기' }: { shown: Shown; problem: Problem; lang?: Lang; submitLabel?: string }) {
  const r = shown.result;
  if (r.kind === 'fail') return <div className="err-box">{lang === 'c' ? 'C 채점기를' : '파이썬을'} 실행하지 못했어요: {r.message} 잠시 뒤 다시 눌러 보세요.</div>;
  if (r.kind === 'timeout')
    return (
      <div className="err-box" role="alert">
        <strong>시간 초과</strong>
        <div>정해진 시간 안에 끝나지 않았어요. 반복문이 끝나는 조건(while의 조건, 범위)을 확인해 보세요.</div>
      </div>
    );
  const out = r.out;
  const stdout = out.stdout ? (
    <>
      <h4 className="faint" style={{ margin: '0.6rem 0 0' }}>
        {lang === 'c' ? 'printf 출력' : 'print 출력'}{out.stdoutCut ? ' (길어서 앞부분만)' : ''}
      </h4>
      <pre className="stdout">{out.stdout}</pre>
    </>
  ) : null;
  if (out.compile) return (
    <div className="results">
      <ErrorBox e={out.compile} title="코드를 실행하지 못했어요" />
      {stdout}
    </div>
  );
  const pass = out.results.filter((x) => x.ok).length;
  const all = out.results.length;
  if (shown.mode === 'run') {
    const cases = problem.examples;
    return (
      <div className="results">
        <div className="res-head">
          <strong className={pass === all ? 'ok' : 'bad'}>
            예시 {all}개 중 {pass}개 통과
          </strong>
          <span className="faint">{r.ms}ms · {submitLabel === '채점하기' ? '채점하려면' : '답안을 내려면'} ‘{submitLabel}’를 눌러요</span>
        </div>
        <div className="scroll-x">
          <table className="res-table">
            <thead>
              <tr>
                <th>예시</th>
                <th>기댓값</th>
                <th>내 코드 결과</th>
                <th>결과</th>
              </tr>
            </thead>
            <tbody>
              {out.results.map((x, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>
                    <pre>{reprFor(lang, cases[i].expected)}</pre>
                  </td>
                  <td>{x.error ? <pre className="fail">{x.error.message}</pre> : <pre>{x.got}</pre>}</td>
                  <td>{x.ok ? <span className="pass">통과</span> : <span className="fail">실패</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {out.results.find((x) => x.error)?.error?.hint && <p className="faint">{out.results.find((x) => x.error)!.error!.hint}</p>}
        {stdout}
      </div>
    );
  }
  return (
    <div className="results">
      <div className="res-head">
        <strong className={pass === all ? 'ok' : 'bad'}>{pass === all ? '모든 테스트 통과!' : `테스트 ${all}개 중 ${pass}개 통과`}</strong>
        <span className="faint">
          예시 {shown.exampleCount}개 + 숨은 테스트 {all - shown.exampleCount}개 · {r.ms}ms
        </span>
      </div>
      <ul className="test-list">
        {out.results.map((x, i) => (
          <li key={i}>
            {i < shown.exampleCount ? `예시 ${i + 1}` : `테스트 ${i + 1 - shown.exampleCount}`} 〉{' '}
            {x.ok ? <span className="pass">통과</span> : <span className="fail">{x.error ? `실패(${x.error.type})` : '실패'}</span>}
          </li>
        ))}
      </ul>
      {out.results.find((x) => x.error)?.error && <ErrorBox e={out.results.find((x) => x.error)!.error!} title="실행 중 오류가 난 테스트가 있어요" />}
      {stdout}
    </div>
  );
}

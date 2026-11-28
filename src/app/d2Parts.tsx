/** Data 과정(d2) 화면 조각: 데이터 개요, 문제 설명, 객관식 풀이, 데이터 문제 결과 */
import { useState } from 'react';
import type { Problem, ProblemKind } from '../content/types';
import { Rich, inline } from '../components/Rich';
import catalogJson from '../datasets/d2.json';
import type { PyError, RunResult } from '../grader/client';

interface DatasetInfo {
  title: string;
  rows: number[];
  columns: { name: string; desc: string }[];
  sample: string[][];
}
const catalog = catalogJson as Record<string, DatasetInfo>;

/** 시험지의 [데이터 개요]: 변수별 설명 + 데이터 샘플(앞 5행) */
export function DataOverview({ files }: { files: string[] }) {
  return (
    <>
      {files.map((f) => {
        const d = catalog[f];
        if (!d) return null;
        return (
          <div className="data-ov" key={f}>
            <h4>
              <code>{f}</code> · {d.title} <span className="faint">({d.rows[0].toLocaleString()}행)</span>
            </h4>
            <p className="faint small">▶ 변수별 설명</p>
            <div className="scroll-x">
              <table className="ex-table var-table">
                <thead>
                  <tr>
                    <th scope="col">변수명</th>
                    <th scope="col">설명</th>
                  </tr>
                </thead>
                <tbody>
                  {d.columns.map((c) => (
                    <tr key={c.name}>
                      <td>
                        <code>{c.name}</code>
                      </td>
                      <td>{c.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="faint small">▶ 데이터 샘플(앞 5행)</p>
            <div className="scroll-x">
              <table className="ex-table sample-table">
                <thead>
                  <tr>
                    <th scope="col" />
                    {d.columns.map((c) => (
                      <th key={c.name} scope="col">
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.sample.map((r, i) => (
                    <tr key={i}>
                      <th scope="row">{i}</th>
                      {r.map((x, j) => (
                        <td key={j} className={x === 'NaN' ? 'nan' : undefined}>
                          {x}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </>
  );
}

/** Data 과정 문제 설명(객관식: 설명만 / 코드 문제: 설명 + 정답 예시 + 데이터 개요) */
export function D2Statement({ problem, kind }: { problem: Problem; kind: ProblemKind }) {
  return (
    <>
      <div className="sec">
        <h3>문제</h3>
        <Rich text={problem.statement} figures={problem.figures} />
        {kind !== 'choice' && problem.answerFormat && !problem.data?.plot && <p className="faint">(정답 예시: {problem.answerFormat})</p>}
      </div>
      {kind !== 'choice' && problem.data && (
        <div className="sec">
          <h3>데이터 개요</h3>
          <DataOverview files={problem.data.files} />
          <p className="faint small" style={{ marginTop: '0.4rem' }}>
            ‘예시로 실행’은 위 데이터로, ‘채점하기’는 같은 모양에 값만 다른 숨은 데이터 {problem.tests.length}개까지 실행해요. 그래서 답을 숫자로 적어 넣으면 통과하지 못해요.
          </p>
        </div>
      )}
    </>
  );
}

/** 객관식 보기 목록(라디오) */
export function ChoiceList({ problem, value, onChange, disabled, reveal, name }: { problem: Problem; value: number | null; onChange: (i: number) => void; disabled?: boolean; reveal?: { answer: number; wrong?: number[] } | null; name: string }) {
  const c = problem.choice!;
  return (
    <div className="choice-list" role="radiogroup" aria-label="보기">
      {c.options.map((o, i) => {
        const cls = reveal ? (i === reveal.answer ? ' correct' : reveal.wrong?.includes(i) ? ' wrong' : '') : '';
        return (
          <label key={i} className={`choice-opt${value === i ? ' sel' : ''}${cls}`}>
            <input type="radio" name={name} checked={value === i} onChange={() => onChange(i)} disabled={disabled} />
            <span className="no">{'①②③④⑤'[i]}</span>
            <span>{inline(o, `o${i}`)}</span>
          </label>
        );
      })}
    </div>
  );
}

/** 보기마다 왜 맞고 틀린지 */
export function WhyList({ problem }: { problem: Problem }) {
  const c = problem.choice!;
  return (
    <ul className="why-list">
      {c.options.map((_, i) => (
        <li key={i} className={i === c.answer ? 'correct' : ''}>
          <strong>
            {'①②③④⑤'[i]} {i === c.answer ? '정답' : '오답'}
          </strong>{' '}
          {inline(c.why[i] ?? '', `w${i}`)}
        </li>
      ))}
    </ul>
  );
}

function ErrBox({ e, title }: { e: PyError; title: string }) {
  return (
    <div className="err-box" role="alert">
      <strong>{title}</strong>
      {e.line ? <span> · {e.line}번째 줄</span> : null}
      {e.hint && <div>{e.hint}</div>}
      <pre>{e.message}</pre>
    </div>
  );
}

const fmt = (v: unknown) => (typeof v === 'string' ? `'${v}'` : typeof v === 'number' ? String(v) : JSON.stringify(v));

/** Data 문제 실행·채점 결과 */
export function DataResults({ mode, result, problem, hideExpected = false, submitLabel = '채점하기' }: { mode: 'run' | 'submit'; result: RunResult; problem: Problem; hideExpected?: boolean; submitLabel?: string }) {
  const [big, setBig] = useState(false);
  if (result.kind === 'fail') return <div className="err-box">파이썬을 실행하지 못했어요: {result.message} 잠시 뒤 다시 눌러 보세요.</div>;
  if (result.kind === 'timeout')
    return (
      <div className="err-box" role="alert">
        <strong>시간 초과</strong>
        <div>정해진 시간 안에 끝나지 않았어요. 끝나지 않는 반복이 없는지 확인해 보세요.</div>
      </div>
    );
  const out = result.out;
  const plot = !!problem.data?.plot;
  const stdout = out.stdout ? (
    <>
      <h4 className="faint" style={{ margin: '0.6rem 0 0' }}>
        print 출력{out.stdoutCut ? ' (길어서 앞부분만)' : ''}
      </h4>
      <pre className="stdout">{out.stdout}</pre>
    </>
  ) : null;
  const img = out.images?.[0] ? (
    <figure className={`plot-img${big ? ' big' : ''}`}>
      <img src={`data:image/png;base64,${out.images[0]}`} alt="내 코드가 그린 그래프(예시 데이터)" onClick={() => setBig((b) => !b)} />
      <figcaption className="faint small">내 코드가 그린 그래프(예시 데이터)</figcaption>
    </figure>
  ) : null;
  if (out.compile)
    return (
      <div className="results">
        <ErrBox e={out.compile} title="코드를 실행하지 못했어요" />
        {stdout}
      </div>
    );
  const firstErr = out.results.find((x) => x.error)?.error;
  const hint = out.results.find((x) => !x.ok && x.hint)?.hint;
  if (mode === 'run') {
    const x = out.results[0];
    const exp = problem.examples[0]?.expected;
    return (
      <div className="results">
        <div className="res-head">
          {hideExpected ? <strong>예시 데이터로 실행했어요</strong> : <strong className={x?.ok ? 'ok' : 'bad'}>{x?.ok ? '예시 데이터에서 정답!' : '예시 데이터에서 정답과 달라요'}</strong>}
          <span className="faint">
            {result.ms}ms · {submitLabel === '채점하기' ? '숨은 데이터까지 채점하려면' : '답안을 내려면'} ‘{submitLabel}’를 눌러요
          </span>
        </div>
        {x?.error ? (
          <ErrBox e={x.error} title="solution()을 실행하다 오류가 났어요" />
        ) : plot ? (
          img ?? <p className="notice warn">그래프를 찾지 못했어요. 그래프를 그린 뒤 plt.show()를 불렀는지 확인해 보세요.</p>
        ) : (
          <div className="scroll-x">
            <table className="res-table">
              <tbody>
                <tr>
                  <th scope="row">solution()의 반환 값</th>
                  <td>
                    <pre>{x?.got}</pre>
                  </td>
                </tr>
                {!hideExpected && (
                  <tr>
                    <th scope="row">정답(예시 데이터)</th>
                    <td>
                      <pre>{fmt(exp)}</pre>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {plot && img && !hideExpected && <p className={x?.ok ? 'pass' : 'fail'}>{x?.ok ? '정답 그래프와 같아요.' : '정답 그래프와 달라요.'}</p>}
        {!hideExpected && hint && <p className="notice warn">{hint}</p>}
        {stdout}
      </div>
    );
  }
  const pass = out.results.filter((x) => x.ok).length;
  const all = out.results.length;
  const ex = problem.examples.length;
  return (
    <div className="results">
      <div className="res-head">
        <strong className={pass === all ? 'ok' : 'bad'}>{pass === all ? '모든 데이터에서 정답!' : `데이터 ${all}개 중 ${pass}개에서 정답`}</strong>
        <span className="faint">
          예시 데이터 {ex}개 + 숨은 데이터 {all - ex}개 · {result.ms}ms
        </span>
      </div>
      <ul className="test-list">
        {out.results.map((x, i) => (
          <li key={i}>
            {i < ex ? '예시 데이터' : `숨은 데이터 ${i + 1 - ex}`} 〉 {x.ok ? <span className="pass">정답</span> : <span className="fail">{x.error ? `오류(${x.error.type})` : '오답'}</span>}
          </li>
        ))}
      </ul>
      {firstErr && <ErrBox e={firstErr} title="실행 중 오류가 난 데이터가 있어요" />}
      {hint && <p className="notice warn">{hint}</p>}
      {pass < all && pass > 0 && !firstErr && <p className="faint">예시 데이터에서는 맞는데 숨은 데이터에서 틀리면, 값을 직접 적었거나 이 데이터에서만 맞는 방법을 썼는지 확인해 보세요.</p>}
      {img}
      {stdout}
    </div>
  );
}

import { Link } from 'react-router-dom';
import type { Course, TypeFile } from '../content/types';
import { KIND_LABEL, kindOf } from '../content/types';
import { allProblems, courseMeta } from '../content';
import { solvedCount, type CourseState } from '../features/progress/model';
import { useCourseProgress } from '../features/progress/store';
import { chipState, Legend, MockSection } from './CourseHome';
import { ConceptBox } from './d2Parts';

interface Props {
  course: Course;
  learnerKey: string;
  remote: boolean;
  preview?: boolean;
}

/**
 * 시험 문항 번호별 유형을 영역으로 묶은 과정 화면(Data 2급, 선생님 요청 2026-11-28).
 * 유형마다 연습 5문제(①→⑤ 점점 어렵게), [심화] 없음. 기본 문제를 모두 풀면 맨 아래 모의고사가 열린다.
 */
export function ExamCourseHome({ course, learnerKey, remote, preview = false }: Props) {
  const meta = courseMeta(course.id)!;
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const ids = allProblems(course).map((p) => p.id);
  const solved = solvedCount(prog.state, ids);
  const choiceTypes = course.types.filter((t) => t.kind === 'choice').map((t) => t.type);
  const codeTypes = course.types.filter((t) => t.kind !== 'choice').map((t) => t.type);
  const range = (ns: number[]) => (ns.length ? `${Math.min(...ns)}~${Math.max(...ns)}번` : '');
  return (
    <div className="page narrow">
      <div className="crumb">
        <Link to="/">홈</Link> › {meta.name}
      </div>
      <div className="exam faint" style={{ color: 'var(--accent)', fontWeight: 600 }}>
        {meta.exam}
      </div>
      <h1>{meta.name}</h1>
      <p className="muted">{meta.blurb}</p>
      <div className="card" style={{ marginTop: '0.75rem' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <strong>
            해결 {solved} / {ids.length}
          </strong>
          {meta.examMinutes && (
            <span className="faint">
              실제 시험 {meta.examMinutes}분 · 객관식 {choiceTypes.length}문항({range(choiceTypes)}) + 작업형 {codeTypes.length}문항({range(codeTypes)})
            </span>
          )}
        </div>
        <div className="bar" style={{ marginTop: '0.4rem' }} aria-hidden>
          <i style={{ width: `${ids.length ? (solved / ids.length) * 100 : 0}%` }} />
        </div>
        <p className="faint" style={{ margin: '0.5rem 0 0' }}>
          시험의 <b>1~20번 문항 유형</b>을 영역별로 묶었어요. 유형마다 <b>연습 5문제</b>가 ①부터 ⑤까지 점점 어려워져요. 객관식은 바로 답을 고르고, 작업형은 코드를 고쳐 실행·채점해요. 막히면 문제 안의 <b>풀이 도움</b>(단계별 중간 점검)을 열어 보세요. {ids.length}문제를 모두 풀면 맨 아래 <b>모의고사</b>가 열려요.
        </p>
        <p className="faint" style={{ margin: '0.4rem 0 0' }}>
          문제는 <b>전체화면 집중 풀이</b>로 풀어요. 푸는 중에 다른 창으로 가거나 전체화면을 나가면 잠기고, 한 유형에서 <b>3번</b> 잠기면 그 유형 기록이 처음으로 돌아가요.
        </p>
        {preview && (
          <p className="notice" style={{ margin: '0.5rem 0 0' }}>
            선생님 계정이라 모의고사가 잠금 없이 열려 있어요. 학생에게는 연습 문제를 모두 풀어야 열려요.
          </p>
        )}
        {prog.syncError && <p className="notice warn" style={{ margin: '0.5rem 0 0' }}>{prog.syncError}</p>}
      </div>

      {(meta.areas ?? []).map((a, ai) => {
        const types = course.types.filter((t) => t.area === a.id).sort((x, y) => x.type - y.type);
        if (!types.length) return null;
        const aIds = types.flatMap((t) => t.problems.map((p) => p.id));
        return (
          <section key={a.id} className="area" aria-labelledby={`area-${a.id}`}>
            <div className="area-head">
              <h2 id={`area-${a.id}`}>
                <span className="area-no">영역 {ai + 1}</span> {a.name}
              </h2>
              <span className="faint">
                {solvedCount(prog.state, aIds)}/{aIds.length}
              </span>
            </div>
            <p className="faint" style={{ margin: '0 0 0.5rem' }}>
              {a.desc}
            </p>
            <div className="types" style={{ marginTop: 0 }}>
              {types.map((ty) => (
                <ExamTypeCard key={ty.type} ty={ty} path={meta.path} state={prog.state} />
              ))}
            </div>
          </section>
        );
      })}
      <Legend adv={false} />

      <MockSection course={course} state={prog.state} ids={ids} preview={preview} />
    </div>
  );
}

function ExamTypeCard({ ty, path, state }: { ty: TypeFile; path: string; state: CourseState }) {
  const ids = ty.problems.map((p) => p.id);
  const kinds = [...new Set(ty.problems.map((p) => kindOf(ty, p)))];
  return (
    <article className="card type-card exam-type" aria-label={`시험 ${ty.type}번 유형: ${ty.typeTitle}`}>
      <div className="type-no" title={`시험 ${ty.type}번`}>
        {ty.type}
        <small>번</small>
      </div>
      <div style={{ minWidth: 0 }}>
        <h2>
          {ty.typeTitle}{' '}
          {ty.kind === 'choice' ? (
            <span className="badge choice">객관식</span>
          ) : (
            <span className="badge write">작업형</span>
          )}
          <span className="faint" style={{ fontSize: '0.85rem', fontWeight: 400 }}>
            {solvedCount(state, ids)}/{ids.length}
          </span>
        </h2>
        <p>{ty.intro}</p>
        {ty.kind !== 'choice' && <p className="faint small" style={{ marginTop: '-0.3rem' }}>코드 형식: {kinds.map((k) => KIND_LABEL[k]).join(' · ')}</p>}
        {ty.concept && (
          <details className="concept-details">
            <summary>개념 정리</summary>
            <ConceptBox concept={ty.concept} link />
          </details>
        )}
        <div className="tier-list" style={{ marginTop: '0.4rem' }}>
          {ty.problems.map((p, i) => {
            const { cls, label } = chipState(state, p);
            return (
              <Link key={p.id} to={`${path}/${p.id}`} className={`prob-chip ${cls}`} title={`${p.title} · ${label}`}>
                <span className="dot" aria-hidden />
                <span>
                  {'①②③④⑤'[i] ?? i + 1} {p.title}
                </span>
                <span className="sr-only">({label})</span>
              </Link>
            );
          })}
        </div>
      </div>
    </article>
  );
}

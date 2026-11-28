import type { Course, CourseId, MockFile, MockSet, Problem, TypeFile } from './types';

/** 시험 영역(Data 2급: 교재 단원·시험 문항을 묶는 큰 갈래) */
export interface AreaMeta {
  id: string;
  name: string;
  desc: string;
}

export interface CourseMeta {
  id: CourseId;
  name: string;
  exam: string;
  blurb: string;
  path: string;
  /** 실제 시험 시간(분). 시험 화면에서 확인한 것만 적는다 */
  examMinutes?: number;
  /** 필수 연습 문제 수(홈 진도 막대) */
  total: number;
  /**
   * exam: 시험 문항 번호별 유형을 영역으로 묶어 보여 주고, [심화] 없이 유형마다 연습 5문제.
   * 답(코드) 풀이를 먼저 보여 주고 중간 점검은 '풀이 도움'(선택)으로 둔다(Data 2급, 선생님 요청 2026-11-28)
   */
  style?: 'exam';
  /** style exam: 영역 목록(유형 파일의 area가 이 id) */
  areas?: AreaMeta[];
}

/** Data 2급 영역: YBM DATA 2급 Python 교재 단원(빅데이터·데이터 수집 및 전처리·데이터 탐색과 이해·데이터 분석·데이터 시각화) 순서 */
export const D2_AREAS: AreaMeta[] = [
  { id: 'A1', name: '빅데이터 이해', desc: '빅데이터의 특징과 데이터 분석 절차를 묻는 객관식이에요(시험 1·2번).' },
  { id: 'A2', name: '데이터 수집·전처리', desc: '데이터를 꺼내고 합치고 다듬는 일: 쿼리, 데이터 합치기, 극단치, 자료형·날짜, 파생 변수, 결측치(5·7·8·9·17·19번).' },
  { id: 'A3', name: '데이터 탐색과 이해', desc: '통계량과 분포로 데이터를 살피고, 세고 비율을 구해요(3·4·6·14·15·18번).' },
  { id: 'A4', name: '데이터 분석', desc: '머신러닝 기초와 평가 지표, t-검정, 군집 분석(10·11·12·16·20번).' },
  { id: 'A5', name: '데이터 시각화', desc: '데이터를 묶어 센 결과를 그래프로 그려요(13번).' },
];

/** 과정 목록. ID(pyb·pya)는 진도 저장 키라 바꾸지 않는다. */
export const COURSES: CourseMeta[] = [
  {
    id: 'pyb',
    name: '프로그래밍 Python 기본',
    exam: 'COS Pro 2급 Python 대비',
    blurb: '반복문·조건문·리스트로 푸는 10가지 시험 유형. 빈칸 채우기, 한 줄 수정, 함수 작성을 단계별로 연습해요.',
    path: '/basic',
    total: 50,
  },
  {
    id: 'pya',
    name: '프로그래밍 Python 심화',
    exam: 'COS Pro 1급 Python 대비',
    blurb: '정렬 기준, 슬라이싱, 함수 나누기, 시뮬레이션처럼 한 단계 깊은 10가지 시험 유형을 연습해요.',
    path: '/advanced',
    total: 50,
  },
  {
    id: 'cb',
    name: '프로그래밍 C 기본',
    exam: 'COS Pro 2급 C 대비',
    blurb: '반복문·조건문·배열·문자열을 C로 다루는 10가지 시험 유형. 빈칸 채우기, 한 줄 수정, 함수 작성을 단계별로 연습해요.',
    path: '/c-basic',
    examMinutes: 50,
    total: 50,
  },
  {
    id: 'd2',
    name: 'Data 분석 2급',
    exam: 'YBM DAT 2급(Python) 대비',
    blurb: '실제 시험 20문항의 유형을 5개 영역으로 묶어 유형마다 5문제씩 연습해요. 객관식 이론 12유형과 pandas로 CSV 데이터를 다루는 작업형 8유형.',
    path: '/data2',
    examMinutes: 50,
    total: 100,
    style: 'exam',
    areas: D2_AREAS,
  },
];

export const courseMeta = (id: string): CourseMeta | undefined => COURSES.find((c) => c.id === id);
export const courseByPath = (path: string): CourseMeta | undefined => COURSES.find((c) => c.path === path);

const loaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/t*.json', { import: 'default' }),
  d2: import.meta.glob<TypeFile>('./d2/t*.json', { import: 'default' }),
};

const mockLoaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/mock/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/mock/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/mock/t*.json', { import: 'default' }),
  d2: {},
};
/** Data 과정 모의고사: 시험지 순서대로 문항을 담은 파일(mN.json) */
const mockFileLoaders: Partial<Record<CourseId, Record<string, () => Promise<MockFile>>>> = {
  d2: import.meta.glob<MockFile>('./d2/mock/m*.json', { import: 'default' }),
};

const advLoaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/adv/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/adv/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/adv/t*.json', { import: 'default' }),
  // Data 2급은 [심화] 없이 유형마다 연습 5문제(style exam)
  d2: {},
};

/** Data 과정 문제는 객관식·데이터 문제에 없는 칸(매개변수·예시 등)을 빈 값으로 채워 같은 모양으로 쓴다 */
const PROBLEM_DEFAULTS: Pick<Problem, 'params' | 'returns' | 'funcName' | 'argNames' | 'examples' | 'tests' | 'code' | 'solution'> = { params: [], returns: [], funcName: 'solution', argNames: [], examples: [], tests: [], code: '', solution: '' };
export function normalizeProblem(p: Problem): Problem {
  return { ...PROBLEM_DEFAULTS, ...p };
}
const normalizeType = (t: TypeFile): TypeFile => ({ ...t, problems: t.problems.map(normalizeProblem) });

/** Data 과정 모의고사 파일 → 회별 묶음(문항 키 q01~) */
export function buildMockFiles(files: MockFile[], types: TypeFile[]): MockSet[] {
  return files
    .filter((f) => f && Array.isArray(f.items))
    .sort((a, b) => a.mock - b.mock)
    .map((f) => ({
      n: f.mock,
      key: `m${f.mock}`,
      items: f.items.map((it, i) => {
        const type = types.find((t) => t.type === it.type) ?? { course: f.course, type: it.type, typeTitle: `유형 ${it.type}`, kind: it.kind, skills: [], intro: '', problems: [] };
        return { type, problem: normalizeProblem(it.problem), key: `q${String(i + 1).padStart(2, '0')}`, kind: it.kind };
      }),
    }));
}

/** 심화 파일을 같은 유형 번호의 기본 유형에 붙인다 */
export function attachAdv(types: TypeFile[], advFiles: TypeFile[]): TypeFile[] {
  const byType = new Map(advFiles.filter((a) => a && Array.isArray(a.problems)).map((a) => [a.type, a]));
  return types.map((t) => {
    const a = byType.get(t.type);
    return a ? { ...t, adv: { intro: a.intro, skills: a.skills ?? [], problems: a.problems } } : t;
  });
}

export const MOCK_SETS = 3;

/** 유형별 모의고사 파일(문제 3개: 1·2·3회) → 회별 묶음 */
export function buildMocks(files: TypeFile[]): MockSet[] {
  const sorted = files.filter((t) => t && Array.isArray(t.problems)).sort((a, b) => a.type - b.type);
  return Array.from({ length: MOCK_SETS }, (_, i) => ({
    n: i + 1,
    key: `m${i + 1}`,
    items: sorted.filter((t) => t.problems[i]).map((t) => ({ type: t, problem: t.problems[i] })),
  }));
}

const cache = new Map<CourseId, Promise<Course>>();

/** 과정의 문제를 불러온다(과정마다 한 번, 필요할 때). */
export function loadCourse(id: CourseId): Promise<Course> {
  let p = cache.get(id);
  if (!p) {
    const meta = courseMeta(id)!;
    const all = (ls: Record<string, () => Promise<TypeFile>>) => Promise.all(Object.values(ls).map((l) => l()));
    const allM = (ls: Record<string, () => Promise<MockFile>> = {}) => Promise.all(Object.values(ls).map((l) => l()));
    p = Promise.all([all(loaders[id]), all(mockLoaders[id]), all(advLoaders[id]), allM(mockFileLoaders[id])]).then(([types, mocks, adv, mockFiles]) => {
      const ts = attachAdv(
        types
          .filter((t) => t && Array.isArray(t.problems))
          .map(normalizeType)
          .sort((a, b) => a.type - b.type),
        adv.filter((a) => a && Array.isArray(a.problems)).map(normalizeType),
      );
      return {
        id,
        name: meta.name,
        exam: meta.exam,
        blurb: meta.blurb,
        types: ts,
        mocks: mockFiles.length ? buildMockFiles(mockFiles, ts) : buildMocks(mocks),
      };
    });
    cache.set(id, p);
    p.catch(() => cache.delete(id));
  }
  return p;
}

export interface Found {
  type: TypeFile;
  problem: Problem;
  index: number;
  /** [심화] 문제인가 */
  adv: boolean;
}

export function findProblem(course: Course, pid: string): Found | null {
  for (const t of course.types) {
    const i = t.problems.findIndex((p) => p.id === pid);
    if (i >= 0) return { type: t, problem: t.problems[i], index: i, adv: false };
    const j = t.adv?.problems.findIndex((p) => p.id === pid) ?? -1;
    if (j >= 0) return { type: t, problem: t.adv!.problems[j], index: j, adv: true };
  }
  return null;
}

/** [기본] 문제 전체(모의고사를 열 조건, 진도 막대) */
export const allProblems = (course: Course): Problem[] => course.types.flatMap((t) => t.problems);
/** [심화] 문제 전체 */
export const allAdvProblems = (course: Course): Problem[] => course.types.flatMap((t) => t.adv?.problems ?? []);
export const typeKey = (t: { type: number }) => `t${String(t.type).padStart(2, '0')}`;

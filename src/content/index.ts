import type { Course, CourseId, MockSet, Problem, TypeFile } from './types';

export interface CourseMeta {
  id: CourseId;
  name: string;
  exam: string;
  blurb: string;
  path: string;
  /** 실제 시험 시간(분). 시험 화면에서 확인한 것만 적는다 */
  examMinutes?: number;
}

/** 과정 목록. ID(pyb·pya)는 진도 저장 키라 바꾸지 않는다. */
export const COURSES: CourseMeta[] = [
  {
    id: 'pyb',
    name: '프로그래밍 Python 기본',
    exam: 'COS Pro 2급 Python 대비',
    blurb: '반복문·조건문·리스트로 푸는 10가지 시험 유형. 빈칸 채우기, 한 줄 수정, 함수 작성을 단계별로 연습해요.',
    path: '/basic',
  },
  {
    id: 'pya',
    name: '프로그래밍 Python 심화',
    exam: 'COS Pro 1급 Python 대비',
    blurb: '정렬 기준, 슬라이싱, 함수 나누기, 시뮬레이션처럼 한 단계 깊은 10가지 시험 유형을 연습해요.',
    path: '/advanced',
  },
  {
    id: 'cb',
    name: '프로그래밍 C 기본',
    exam: 'COS Pro 2급 C 대비',
    blurb: '반복문·조건문·배열·문자열을 C로 다루는 10가지 시험 유형. 빈칸 채우기, 한 줄 수정, 함수 작성을 단계별로 연습해요.',
    path: '/c-basic',
    examMinutes: 50,
  },
];

export const courseMeta = (id: string): CourseMeta | undefined => COURSES.find((c) => c.id === id);
export const courseByPath = (path: string): CourseMeta | undefined => COURSES.find((c) => c.path === path);

const loaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/t*.json', { import: 'default' }),
};

const mockLoaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/mock/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/mock/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/mock/t*.json', { import: 'default' }),
};

const advLoaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/adv/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/adv/t*.json', { import: 'default' }),
  cb: import.meta.glob<TypeFile>('./cb/adv/t*.json', { import: 'default' }),
};

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
    p = Promise.all([all(loaders[id]), all(mockLoaders[id]), all(advLoaders[id])]).then(([types, mocks, adv]) => ({
      id,
      name: meta.name,
      exam: meta.exam,
      blurb: meta.blurb,
      types: attachAdv(types.filter((t) => t && Array.isArray(t.problems)).sort((a, b) => a.type - b.type), adv),
      mocks: buildMocks(mocks),
    }));
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

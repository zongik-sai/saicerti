/** 문제 데이터 형식(docs/CONTENT_SCHEMA.md). 검수: python3 tools/validate.py */
export type CourseId = 'pyb' | 'pya' | 'cb';
export type Lang = 'python' | 'c';
export type ProblemKind = 'blank' | 'fix' | 'write';
export type CompareMode = 'exact' | 'float';
export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

export interface Case {
  args: Json[];
  expected: Json;
}
export interface Example extends Case {
  explain?: string;
}

export interface InputCell {
  a: string;
  alts?: string[];
}
export type TableCell = string | InputCell;

export type Step =
  | { id: string; kind: 'mcq'; q: string; options: string[]; answer: number; explain: string }
  | { id: string; kind: 'table'; title?: string; prompt: string; columns: string[]; rows: TableCell[][]; check?: string; explain: string }
  | { id: string; kind: 'short'; q: string; a: string; alts?: string[]; check?: string; explain: string };

/** 문제 속 그림(시험지의 이미지를 화면에서 다시 그림). 설명 글에서 한 줄짜리 `{{fig:ID}}`로 넣는다 */
export type Figure =
  | { id: string; kind: 'cells'; caption?: string; alt: string; index?: (string | number)[] | 'auto' | 'auto1'; values: (string | number)[]; highlight?: number[]; dim?: number[]; marks?: { at: number; label: string }[]; arrows?: { from: number; to: number; label?: string; both?: boolean }[]; groups?: { from: number; to: number; label: string }[] }
  | { id: string; kind: 'grid'; caption?: string; alt: string; rows: (string | number)[][]; rowLabels?: string[]; colLabels?: string[]; highlight?: [number, number][]; dim?: [number, number][] }
  | { id: string; kind: 'table'; caption?: string; alt: string; head: string[]; rows: (string | number)[][]; highlight?: number[] }
  | { id: string; kind: 'svg'; caption?: string; alt: string; svg: string };

/** C 문제 채점 정보: 숨긴 길이 매개변수(예: arr_len = len(arr)), 배열 반환 길이 */
export interface CSpec {
  derived?: Record<string, string>;
  ret?: { len?: string };
}

export interface Problem {
  id: string;
  version: number;
  title: string;
  statement: string;
  params: string[];
  returns: string[];
  funcName: string;
  argNames: string[];
  examples: Example[];
  code: string;
  blanks?: { answer: string; alts?: string[] }[];
  bugLine?: number;
  solution: string;
  tests: Case[];
  compare?: CompareMode;
  inputCheck?: string;
  steps: Step[];
  explain: string;
  figures?: Figure[];
  cspec?: CSpec;
}

/** 심화 문제 묶음(src/content/<과정>/adv/tNN.json, id <과정>-tNN-adv1~adv5). 필수가 아니고, 그 유형의 기본 5문제를 모두 풀면 열 수 있다 */
export interface AdvSet {
  intro: string;
  skills: string[];
  problems: Problem[];
}

export interface TypeFile {
  course: CourseId;
  type: number;
  typeTitle: string;
  kind: ProblemKind;
  /** 기본 python */
  lang?: Lang;
  skills: string[];
  intro: string;
  /** [기본] 1~5 */
  problems: Problem[];
  /** [심화] 1~5(불러올 때 adv 파일에서 붙임) */
  adv?: AdvSet;
}

/** 모의고사 한 회: 원본 유형 1~10이 한 문제씩(같은 유형의 1·2·3회는 예시·테스트만 다름) */
export interface MockItem {
  type: TypeFile;
  problem: Problem;
}
export interface MockSet {
  n: number;
  key: string;
  items: MockItem[];
}

export interface Course {
  id: CourseId;
  name: string;
  exam: string;
  blurb: string;
  types: TypeFile[];
  mocks: MockSet[];
}

export const KIND_LABEL: Record<ProblemKind, string> = {
  blank: '빈칸 채우기',
  fix: '한 줄 수정',
  write: '함수 작성',
};

export const KIND_TASK: Record<ProblemKind, string> = {
  blank: '빈칸을 채워 코드를 완성해요.',
  fix: '틀린 한 줄만 고쳐요(두 줄 이상 바꾸면 채점하지 않아요).',
  write: 'solution 함수를 직접 작성해요.',
};

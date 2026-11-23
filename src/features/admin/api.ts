import type { SupabaseClient } from '@supabase/supabase-js';
import type { AccountRow } from '../auth/accountKind';

/**
 * 교사 관리 RPC(배움 숲 saiedu 저장소 supabase/migrations/20261029000000_roles.sql, 같은 Supabase 프로젝트).
 * 권한은 모두 서버가 다시 확인한다: 목록은 선생님만, 지정·해제는 관리자만. 모든 변경은 권한 변경 기록에 남는다.
 */
export class RpcError extends Error {
  constructor(public fn: string, message: string, public code?: string, public status?: number) {
    super(message);
  }
}

/** 서버에 아직 이 기능(migration)이 없음 */
export function isMissingFunction(e: unknown): boolean {
  const x = e as { code?: string; message?: string; status?: number } | null;
  return !!x && (x.code === 'PGRST202' || x.code === '42883' || /Could not find the function|does not exist/i.test(x.message ?? ''));
}

/** 이 기능을 설치하는 migration 파일(saiedu 저장소) */
export const MIGRATION_OF: Record<string, string> = {
  am_i_teacher: '20261007000000_computer_general.sql',
  course_class_overview: '20261026000000_courses.sql',
  am_i_admin: '20261029000000_roles.sql',
  account_list: '20261029000000_roles.sql',
  set_teacher: '20261029000000_roles.sql',
  set_admin: '20261029000000_roles.sql',
  revoke_listed_email: '20261029000000_roles.sql',
  role_audit_list: '20261029000000_roles.sql',
};

const ROLE_CHANGE_FNS = ['set_teacher', 'set_admin', 'revoke_listed_email'];

export function rpcErrorText(fn: string, e: unknown): string {
  const x = e as { code?: string; message?: string } | null;
  if (isMissingFunction(e)) {
    return `서버에 이 기능(${fn})이 아직 설치되지 않았어요. 관리자가 Supabase SQL Editor에서 saiedu 저장소의 supabase/migrations/${MIGRATION_OF[fn] ?? '최신 migration'}을 실행해야 해요.`;
  }
  if (x?.code === '42501') return ROLE_CHANGE_FNS.includes(fn) ? '관리자 계정만 권한을 바꿀 수 있어요.' : '선생님 계정만 볼 수 있어요.';
  if (x?.code === '23505') return '다른 요청이 동시에 처리되고 있어요. 잠시 뒤 다시 시도해 주세요.';
  return x?.message || String(e);
}

export type RoleAction = 'grant_teacher' | 'revoke_teacher' | 'grant_admin' | 'revoke_admin';
export interface RoleAuditRow {
  at: string;
  actor: string | null;
  actor_email: string | null;
  actor_name: string | null;
  target: string | null;
  target_email: string | null;
  target_name: string | null;
  action: RoleAction;
  /** 자동 처리·이메일로 해제 등 까닭(없으면 null) */
  note?: string | null;
}

/** 계정 목록(선생님 읽기)·교사/관리자 지정·해제(관리자). 권한은 서버가 다시 확인한다 */
export interface AccountsApi {
  amIAdmin(): Promise<boolean>;
  list(): Promise<AccountRow[]>;
  /** 바뀌었으면 true, 이미 그 상태면 false */
  setTeacher(userId: string, on: boolean): Promise<boolean>;
  setAdmin(userId: string, on: boolean): Promise<boolean>;
  /** 로그인한 계정이 없는 목록 이메일을 교사·관리자 목록에서 지운다 */
  revokeListed(email: string): Promise<boolean>;
  audit(limit: number): Promise<RoleAuditRow[]>;
}

export function supabaseAccountsApi(sb: SupabaseClient): AccountsApi {
  const call = async <T,>(fn: string, args?: Record<string, unknown>): Promise<T> => {
    const { data, error, status } = args ? await sb.rpc(fn, args) : await sb.rpc(fn);
    if (error) throw new RpcError(fn, error.message, error.code, status);
    return data as T;
  };
  return {
    amIAdmin: async () => (await call<boolean>('am_i_admin').catch(() => false)) === true,
    list: async () => (await call<AccountRow[] | null>('account_list')) ?? [],
    setTeacher: async (userId, on) => (await call<boolean>('set_teacher', { p_user: userId, p_on: on })) === true,
    setAdmin: async (userId, on) => (await call<boolean>('set_admin', { p_user: userId, p_on: on })) === true,
    revokeListed: async (email) => (await call<boolean>('revoke_listed_email', { p_email: email })) === true,
    audit: async (limit) => (await call<RoleAuditRow[] | null>('role_audit_list', { p_limit: limit })) ?? [],
  };
}

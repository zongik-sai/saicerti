import { useEffect, useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { supabase } from '../auth/supabase';

/**
 * 선생님·관리자인지(am_i_teacher·am_i_admin RPC, 사용자마다 한 번만 묻고 기억). 메뉴를 보일지 정하는 데만 쓴다:
 * 실제 권한은 선생님·관리자용 RPC가 서버에서 다시 확인한다.
 */
export interface Roles {
  teacher: boolean;
  admin: boolean;
}
const cache = new Map<string, Promise<Roles>>();

const ask = (fn: string): Promise<boolean> => {
  const sb = supabase();
  if (!sb) return Promise.resolve(false);
  return Promise.resolve(sb.rpc(fn)).then(
    ({ data, error }) => !error && data === true,
    () => false,
  );
};

export function askRoles(userId: string): Promise<Roles> {
  let p = cache.get(userId);
  if (!p) {
    p = Promise.all([ask('am_i_teacher'), ask('am_i_admin')]).then(([teacher, admin]) => ({ teacher, admin }));
    cache.set(userId, p);
  }
  return p;
}

/** 권한이 바뀌었을 때(예: 내 교사 권한 해제) 다음 확인에서 서버에 다시 묻게 한다 */
export function forgetRoles(userId?: string) {
  if (userId) cache.delete(userId);
  else cache.clear();
}

/** 아직 모르면 null */
export function useRoles(): Roles | null {
  const auth = useAuth();
  const uid = auth.identity?.kind === 'user' ? auth.identity.userId : null;
  const [known, setKnown] = useState<{ uid: string; value: Roles } | null>(null);
  useEffect(() => {
    if (!uid) return;
    let alive = true;
    void askRoles(uid).then((value) => {
      if (alive) setKnown({ uid, value });
    });
    return () => {
      alive = false;
    };
  }, [uid]);
  if (auth.status === 'loading') return null;
  if (!uid) return { teacher: false, admin: false };
  return known?.uid === uid ? known.value : null;
}

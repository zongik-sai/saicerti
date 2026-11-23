import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { supabase } from '../auth/supabase';
import { AccountsPanel } from './Accounts';
import { supabaseAccountsApi } from './api';
import { useRoles } from './roles';

/** 교사 관리: 선생님은 계정 목록을 보고, 관리자만 교사·관리자를 지정·해제한다(배움 숲과 같은 권한 목록). */
export function AdminPage() {
  const roles = useRoles();
  const sb = supabase();
  const api = useMemo(() => (sb ? supabaseAccountsApi(sb) : null), [sb]);
  if (roles === null) return <div className="page" role="status">확인 중…</div>;
  if (!roles.teacher || !api)
    return (
      <div className="page narrow">
        <h1>교사 관리</h1>
        <p className="muted">선생님 계정으로 로그인하면 계정 목록을 볼 수 있고, 관리자 계정은 교사를 지정하거나 해제할 수 있어요.</p>
        <Link className="btn" to="/">
          홈으로
        </Link>
      </div>
    );
  return (
    <div className="page">
      <h1>교사 관리</h1>
      <p className="muted" style={{ maxWidth: '48rem' }}>
        {roles.admin ? '관리자 계정이에요. 계정을 교사·관리자로 지정하거나 해제할 수 있어요.' : '선생님 계정이에요. 계정 목록을 볼 수 있어요(지정·해제는 관리자만).'} 교사 권한은 배움 숲(saiedu)과 함께 쓰므로 여기서 바꾸면 두 사이트에 모두 적용돼요.
      </p>
      <AccountsPanel api={api} />
    </div>
  );
}

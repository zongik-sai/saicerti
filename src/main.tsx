import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { App } from './app/App';
import { AuthProvider } from './features/auth/AuthContext';
import { handleOAuthCallback } from './features/auth/supabase';

async function boot() {
  // GitHub Pages 루트 callback: Router 렌더 전에 ?code=를 처리하고 query를 지운다.
  await handleOAuthCallback();
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AuthProvider>
        <App />
      </AuthProvider>
    </StrictMode>,
  );
}

void boot();

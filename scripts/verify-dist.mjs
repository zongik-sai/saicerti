// 빌드 결과 검증: 에셋 경로가 BASE_PATH를 반영하는지, 파이썬 워커·Pyodide·채점 하네스가 들어 있는지, 비밀 키가 없는지.
// 사용: BASE_PATH=/saicerti/ node scripts/verify-dist.mjs dist
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2] ?? 'dist';
const base = (process.env.BASE_PATH ?? '/').replace(/\/?$/, '/');
const fail = (m) => { console.error('✗ ' + m); process.exitCode = 1; };
const ok = (m) => console.log('✓ ' + m);

const html = readFileSync(join(dir, 'index.html'), 'utf8');
const refs = [...html.matchAll(/(?:src|href)="([^"]+)"/g)].map((m) => m[1]).filter((u) => !u.startsWith('http') && !u.startsWith('data:'));
for (const r of refs) {
  if (!r.startsWith(base)) fail(`index.html 참조가 base(${base})로 시작하지 않음: ${r}`);
  else if (!existsSync(join(dir, r.slice(base.length)))) fail(`참조 파일 없음: ${r}`);
}
ok(`index.html 로컬 참조 ${refs.length}개가 ${base} 아래에 존재`);

for (const f of ['pyworker.js', 'privacy.html', 'pyodide/pyodide.js', 'pyodide/pyodide.asm.js', 'pyodide/pyodide.asm.wasm', 'pyodide/python_stdlib.zip', 'pyodide/pyodide-lock.json', 'pyodide/harness.py', 'pyodide/runtime.json', 'pyodide/cinterp.py']) {
  if (!existsSync(join(dir, f))) fail(`파일 없음: ${f}`);
}
if (!process.exitCode) ok(`파이썬 워커·Pyodide·하네스 파일 존재 (wasm ${(statSync(join(dir, 'pyodide/pyodide.asm.wasm')).size / 1e6).toFixed(1)}MB)`);
const rt = JSON.parse(readFileSync(join(dir, 'pyodide/runtime.json'), 'utf8'));
if (!rt.pycparser || !existsSync(join(dir, 'pyodide', rt.pycparser))) fail('pycparser wheel 없음'); else ok(`C 채점: cinterp.py + ${rt.pycparser}`);
if (readFileSync(join(dir, 'pyodide/cinterp.py'), 'utf8') !== readFileSync('src/grader/cinterp.py', 'utf8')) fail('배포된 cinterp.py가 src/grader/cinterp.py와 다름');
const harness = readFileSync(join(dir, 'pyodide/harness.py'), 'utf8');
if (harness !== readFileSync('src/grader/harness.py', 'utf8')) fail('배포된 harness.py가 src/grader/harness.py와 다름'); else ok('harness.py = src/grader/harness.py');

const assets = readdirSync(join(dir, 'assets'));
const js = assets.filter((f) => f.endsWith('.js'));
const all = js.map((f) => readFileSync(join(dir, 'assets', f), 'utf8')).join('\n');
if (!all.includes('pyworker.js')) fail('번들이 pyworker.js를 참조하지 않음'); else ok('번들이 파이썬 워커를 참조');
const contentChunks = js.filter((f) => /^t\d\d-/.test(f)).length;
if (contentChunks < 20) fail(`문제 파일 청크 ${contentChunks}개(20개 이상이어야 함)`); else ok(`문제 파일 청크 ${contentChunks}개`);
// 비밀 키가 번들에 들어가지 않았는지: service_role JWT의 role 클레임(base64) 또는 sb_secret_ 키 형태
if (/InJvbGUiOiJzZXJ2aWNlX3JvbGUi|sb_secret_[A-Za-z0-9_-]{10,}/.test(all)) fail('번들에 service_role/secret 키 흔적'); else ok('번들에 service_role/secret 키 흔적 없음');
if (process.exitCode) console.error('빌드 검증 실패'); else console.log('빌드 검증 통과');

// 파이썬 실행 환경(Pyodide)과 채점 하네스를 public/pyodide/로 복사한다(직접 호스팅: 외부 CDN을 쓰지 않음).
// npm run dev / build 전에 자동 실행. public/pyodide/는 저장소에 넣지 않는다(.gitignore).
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'node_modules', 'pyodide');
const out = join(root, 'public', 'pyodide');
mkdirSync(out, { recursive: true });
const files = ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json'];
for (const f of files) copyFileSync(join(src, f), join(out, f));
const harness = readFileSync(join(root, 'src', 'grader', 'harness.py'));
writeFileSync(join(out, 'harness.py'), harness);
// C 채점: 인터프리터 + pycparser(BSD-3, wheel 그대로 zip 가져오기)
const cinterpPath = join(root, 'src', 'grader', 'cinterp.py');
const cinterp = existsSync(cinterpPath) ? readFileSync(cinterpPath) : Buffer.from('');
writeFileSync(join(out, 'cinterp.py'), cinterp);
const wheel = readdirSync(join(root, 'src', 'grader', 'vendor')).find((f) => /^pycparser-.*\.whl$/.test(f));
copyFileSync(join(root, 'src', 'grader', 'vendor', wheel), join(out, wheel));
const version = JSON.parse(readFileSync(join(src, 'package.json'), 'utf8')).version;
// Data 과정(d2): pandas·matplotlib·scipy·scikit-learn과 의존 패키지(wheel)도 같은 폴더에 직접 올린다.
// .pyodide-pkgs/(저장소에 넣지 않음)에 없으면 Pyodide 공식 배포처에서 받아 pyodide-lock.json의 SHA-256으로 확인한다(빌드할 때만).
const lock = JSON.parse(readFileSync(join(src, 'pyodide-lock.json'), 'utf8'));
const want = [];
const stack = ['pandas', 'matplotlib', 'scipy', 'scikit-learn'];
while (stack.length) {
  const k = stack.pop();
  if (want.includes(k)) continue;
  want.push(k);
  stack.push(...(lock.packages[k].depends ?? []));
}
const cacheDir = join(root, '.pyodide-pkgs');
mkdirSync(cacheDir, { recursive: true });
let fetched = 0;
for (const k of want) {
  const { file_name: fn, sha256 } = lock.packages[k];
  const cached = join(cacheDir, fn);
  const ok = (buf) => createHash('sha256').update(buf).digest('hex') === sha256;
  if (!existsSync(cached) || !ok(readFileSync(cached))) {
    const url = `https://cdn.jsdelivr.net/pyodide/v${version}/full/${fn}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`패키지 내려받기 실패 ${res.status}: ${url}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (!ok(buf)) throw new Error(`패키지 SHA-256 불일치: ${fn}`);
    writeFileSync(cached, buf);
    fetched++;
  }
  copyFileSync(cached, join(out, fn));
}
console.log(`✓ Data 과정 패키지 ${want.length}개(새로 받음 ${fetched}개) → public/pyodide/`);
const hash = createHash('sha256').update(harness).digest('hex').slice(0, 10);
const chash = createHash('sha256').update(cinterp).digest('hex').slice(0, 10);
// Data 과정 CSV(public/data/d2/)의 해시: 데이터를 바꾸면 브라우저가 새로 받게
const dataDir = join(root, 'public', 'data', 'd2');
const dh = createHash('sha256');
if (existsSync(dataDir)) for (const f of readdirSync(dataDir).sort()) dh.update(f).update(readFileSync(join(dataDir, f)));
const dhash = dh.digest('hex').slice(0, 10);
// 워커가 읽는 버전 정보(캐시 무효화용)
writeFileSync(join(out, 'runtime.json'), JSON.stringify({ pyodide: version, harness: hash, cinterp: chash, pycparser: wheel, data: dhash }) + '\n');
console.log(`✓ Pyodide ${version} + harness(${hash}) → public/pyodide/`);

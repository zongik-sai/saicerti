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
const hash = createHash('sha256').update(harness).digest('hex').slice(0, 10);
const chash = createHash('sha256').update(cinterp).digest('hex').slice(0, 10);
// 워커가 읽는 버전 정보(캐시 무효화용)
writeFileSync(join(out, 'runtime.json'), JSON.stringify({ pyodide: version, harness: hash, cinterp: chash, pycparser: wheel }) + '\n');
console.log(`✓ Pyodide ${version} + harness(${hash}) → public/pyodide/`);

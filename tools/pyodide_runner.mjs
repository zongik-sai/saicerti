// Data 과정(d2) 검수용 실행기: 브라우저와 같은 Pyodide·같은 패키지(pandas·matplotlib·scipy·scikit-learn)·같은 harness.py로
// 문제 코드를 실행한다. tools/validate_d2.py가 한 번 띄워 두고 한 줄에 JSON 요청 하나씩 보낸다.
//   {"op":"data","code":…,"cases":[{"data":0,"expected":…,"plot":true}],"mode":"float"} → run_data 결과
//   {"op":"check","code":"def answers(): …","data":0}                                → ["값", …]
//   {"op":"exec","code":"…\nRESULT = …"}                                             → {"result": RESULT}
// 먼저 npm run runtime(패키지 wheel을 .pyodide-pkgs/에 받아 둠)이 되어 있어야 한다.
import { readFileSync, readdirSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadPyodide } from 'pyodide';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const core = join(root, 'node_modules', 'pyodide');
const pkgs = join(root, '.pyodide-pkgs');
const dataDir = join(root, 'public', 'data', 'd2');

const py = await loadPyodide({ indexURL: core + '/', packageBaseUrl: pkgs + '/', packageCacheDir: pkgs + '/', stdout: () => {}, stderr: () => {} });
// pandas는 처음에, 나머지(matplotlib·scipy·scikit-learn)는 코드에 나올 때 불러온다(메모리 절약)
const loaded = new Set();
async function need(code) {
  const want = ['pandas'];
  if (/\bmatplotlib\b/.test(code)) want.push('matplotlib');
  if (/\bscipy\b/.test(code)) want.push('scipy');
  if (/\bsklearn\b/.test(code)) want.push('scikit-learn');
  const todo = want.filter((p) => !loaded.has(p));
  if (todo.length) await py.loadPackage(todo, { messageCallback: () => {}, errorCallback: (m) => process.stderr.write(m + '\n') });
  todo.forEach((p) => loaded.add(p));
}
await need('');
for (const f of readdirSync(dataDir)) {
  const m = /^(.+?)(?:\.v(\d))?\.csv$/.exec(f);
  if (!m) continue;
  const dir = `/d2data/v${m[2] ?? 0}`;
  py.FS.mkdirTree(dir);
  py.FS.writeFile(`${dir}/${m[1]}.csv`, readFileSync(join(dataDir, f)));
}
const ns = py.toPy({ __name__: 'saicerti_harness' });
py.runPython(readFileSync(join(root, 'src', 'grader', 'harness.py'), 'utf8'), { globals: ns });
const runData = ns.get('run_data');
const runCheck = ns.get('run_check');
process.stdout.write(JSON.stringify({ ready: true }) + '\n');

const rl = createInterface({ input: process.stdin });
for await (const line of rl) {
  if (!line.trim()) continue;
  let out;
  try {
    const req = JSON.parse(line);
    await need(String(req.code || '') + (req.cases?.some((c) => c.plot) ? ' matplotlib' : ''));
    if (req.op === 'data') {
      const cases = req.cases.map((c) => ({ ...c, dir: `/d2data/v${c.data ?? 0}` }));
      out = JSON.parse(runData(req.code, JSON.stringify(cases), req.mode || 'float', 6000, false));
    } else if (req.op === 'exec') {
      // 검수 도구의 run_py와 같은 약속: code를 데이터 폴더(변형 0)에서 실행하고 RESULT 변수를 돌려준다
      const g = py.toPy({ __name__: '__main__' });
      py.runPython(`import os\nos.chdir('/d2data/v${req.data ?? 0}')`, { globals: g });
      py.runPython(req.code, { globals: g });
      out = { result: JSON.parse(py.runPython('import json\njson.dumps(RESULT, ensure_ascii=False, default=str)', { globals: g })) };
      g.destroy();
    } else if (req.op === 'check') {
      out = { values: JSON.parse(runCheck(req.code, `/d2data/v${req.data ?? 0}`)) };
    } else out = { error: 'op?' };
  } catch (e) {
    out = { error: String((e && e.message) || e).slice(-1500) };
  }
  process.stdout.write(JSON.stringify(out) + '\n');
}

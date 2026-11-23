/* saicerti 파이썬 채점 워커(classic worker).
 * - 같은 사이트에 직접 올린 Pyodide(pyodide/)를 불러 학생 코드를 이 브라우저 안에서만 실행한다(서버로 보내지 않음).
 * - 무한 반복 등으로 멈추면 메인 화면이 이 워커를 끝내고(terminate) 새로 만든다.
 */
/* global importScripts, loadPyodide */
let py = null;
let runCases = null;
let initPromise = null;

function init(base) {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const info = await (await fetch(base + 'pyodide/runtime.json', { cache: 'no-cache' })).json();
    importScripts(base + 'pyodide/pyodide.js');
    py = await loadPyodide({ indexURL: base + 'pyodide/', stdout: () => {}, stderr: () => {} });
    const src = await (await fetch(base + 'pyodide/harness.py?v=' + encodeURIComponent(info.harness))).text();
    const ns = py.toPy({ __name__: 'saicerti_harness' });
    py.runPython(src, { globals: ns });
    runCases = ns.get('run_cases');
    return info;
  })();
  initPromise.catch(() => {
    initPromise = null;
  });
  return initPromise;
}

self.onmessage = async (e) => {
  const msg = e.data || {};
  try {
    if (msg.type === 'init') {
      const info = await init(msg.base);
      self.postMessage({ id: msg.id, ok: true, info });
    } else if (msg.type === 'run') {
      await init(msg.base);
      const out = runCases(String(msg.code), String(msg.func), msg.cases, msg.mode || 'exact');
      self.postMessage({ id: msg.id, ok: true, result: JSON.parse(out) });
    }
  } catch (err) {
    self.postMessage({ id: msg.id, ok: false, error: String((err && err.message) || err).slice(0, 600) });
  }
};

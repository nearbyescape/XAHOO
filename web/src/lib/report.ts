// Browser errors are sent to the server log (`docker logs xahoo` shows "browser error: ..."), so problems that
// only happen on the live site can be diagnosed. At most 30 distinct reports per page load.
const seen = new Set<string>();
export function report(err: unknown, where = '') {
  try {
    const e = err as { message?: string; stack?: string };
    const msg = (e && e.message) || String(err);
    const key = msg + where;
    if (seen.has(key) || seen.size >= 30) return;
    seen.add(key);
    console.error('[trend-machine]', where, err);
    const stack = (e && e.stack ? e.stack.split('\n').slice(0, 4).join(' / ') : '');
    fetch('/api/clientlog', { method: 'POST', credentials: 'same-origin', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ msg, where: `${where} ${stack}`.trim() }) }).catch(() => { /* offline */ });
  } catch { /* never let reporting break the page */ }
}
/** Run fn; if it throws, report it and carry on (keeps one bad update from freezing the screen). */
export function safe<T>(fn: () => T, where: string): T | undefined {
  try { return fn(); } catch (err) { report(err, where); return undefined; }
}
export function installGlobalReporting() {
  window.addEventListener('error', ev => report(ev.error || ev.message, `window ${ev.filename || ''}:${ev.lineno || ''}`));
  window.addEventListener('unhandledrejection', ev => report(ev.reason, 'promise'));
}

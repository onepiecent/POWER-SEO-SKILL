/* Printerval blog SEO: the top-10 organic results of the Google results page you are on, as serp.csv rows.

   1. Open the Google URL of a keyword in sheet SERP To-do (google.com ...&gl=us&hl=en, or google.co.uk ...&gl=uk).
   2. Run this file: paste it in the DevTools console, or let Claude in Chrome run it with its JavaScript tool, or
      save it as a bookmarklet (a bookmark whose URL is "javascript:void(" + this file + ")").
   3. It returns tab-separated lines (keyword, market, position, url, title, checked_at, source), copies them to the
      clipboard when the page allows it, and shows them in a box at the top of the page. Paste them under the header
      of assets/serp-template.tsv (or into a Google Sheet with the same columns) and pass the file with --serp.

   Only organic results count: ads (#tads), People also ask and other boxes without a result link are skipped, and a
   URL is listed once. Google's layout changes: if it returns nothing on a results page, check the selectors below.
   Comments are block comments only, so the file still works as a one-line bookmarklet. */
(() => {
  const params = new URL(location.href).searchParams;
  const box = document.querySelector('textarea[name="q"], input[name="q"]');
  const keyword = ((box && box.value) || params.get('q') || '').trim();
  const gl = (params.get('gl') || '').toLowerCase();
  const market = /\.co\.uk$/.test(location.hostname) || gl === 'uk' || gl === 'gb' ? 'uk' : 'us';
  const today = new Date().toISOString().slice(0, 10);
  const seen = new Set();
  const rows = [];
  for (const h3 of document.querySelectorAll('#search a h3, #rso a h3')) {
    const a = h3.closest('a');
    if (!a || !a.href) continue;
    let url;
    try { url = new URL(a.href, location.href); } catch (e) { continue; }
    if (/(^|\.)google\./.test(url.hostname)) {
      /* a redirect link (/url?q=...): the real result is in its parameters */
      const real = url.searchParams.get('url') || url.searchParams.get('q') || '';
      if (!/^https?:\/\//.test(real)) continue;
      url = new URL(real);
    }
    const key = url.hostname.replace(/^www\./, '') + url.pathname.replace(/\/$/, '');
    if (seen.has(key)) continue;
    seen.add(key);
    const title = (h3.innerText || h3.textContent || '').replace(/\s+/g, ' ').trim();
    rows.push([keyword, market, rows.length + 1, url.href, title, today, 'browser']);
    if (rows.length === 10) break;
  }
  const text = rows.map(r => r.map(v => String(v).replace(/[\t\r\n]+/g, ' ')).join('\t')).join('\n');
  try { if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {}); } catch (e) { /* not allowed */ }
  const old = document.getElementById('printerval-serp-box');
  if (old) old.remove();
  const out = document.createElement('textarea');
  out.id = 'printerval-serp-box';
  out.value = text || 'No organic result found: is this a Google results page?';
  out.style.cssText = 'position:fixed;top:8px;left:8px;width:90vw;height:30vh;z-index:2147483647;font:12px monospace';
  document.body.appendChild(out);
  out.select();
  return text;
})()

// Turkish federation pool portal, read in a real browser (the portal refuses GitHub's servers with 403).
// Run in the built-in browser on a page of https://portal.bilardo.gov.tr (any page, same origin).
// 1) Paste this file, then:  tbfStart([ids...])   (ids from: python3 tbf_merge.py --todo)
//    It reads 2 pages per id, one page a second, in the background; the page must stay open.
// 2) tbfProgress()  -> {done, total, running}
// 3) tbfChunk(i, size) -> JSON text of results i*size .. (i+1)*size; save the chunks in order as one JSON array
//    and merge with: python3 tbf_merge.py results.json
// Result per id: {id, p: [name, first date, last date, category, venue, format] or null,
//   m: [[code, round, idA, scoreA, race, scoreB, idB, status], ...], n: {player id: name}}
(function () {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const plain = s => { const d = document.createElement('div'); d.innerHTML = s.replace(/<[^>]+>/g, ' '); return d.textContent.replace(/\s+/g, ' ').trim(); };
  async function page(u) {
    for (let i = 0; i < 4; i++) {
      try { const r = await fetch(u, {credentials: 'omit'}); if (r.ok) return await r.text(); if (r.status === 500 || r.status === 404) return ''; } catch (e) {}   // the portal answers 500 for ids with no tournament
      await sleep(5000 * (i + 1));
    }
    throw new Error('could not read ' + u);
  }
  function profile(h) {
    const s = plain(h.replace(/<script[\s\S]*?<\/script>/g, ' '));
    const m = s.match(/Name: (.*?) Dates: (.*?) - (.*?) Category: (.*?) Location: (.*?) Format: (\S*)/);
    return m && m[1].trim() ? [m[1].trim(), m[2].trim(), m[3].trim(), m[4].trim(), m[5].trim().replace(/^,|,$/g, '').trim(), m[6]] : null;
  }
  function matches(h) {
    const heads = [...h.matchAll(/<th[^>]*class=['"]groupHeader['"][^>]*>([\s\S]*?)<\/th>/g)].map(x => [x.index, plain(x[1])]);
    const out = [], names = {}, seen = new Set();
    for (const x of h.matchAll(/<tr[^>]*>((?:(?!<\/tr>)[\s\S])*?date-box[\s\S]*?)<\/tr>/g)) {
      const row = x[1], cells = row.split(/<td\b/).slice(1);
      const ids = [...row.matchAll(/fncViewMatchesClick\((\d+)\)/g)].map(y => y[1]);
      if (cells.length < 7 || ids.length < 2 || ids[0] === '0' || ids[1] === '0') continue;
      const ct = cells.map(c => plain('<td' + c));
      const sa = parseInt(ct[3]), sb = parseInt(ct[5]);
      if (isNaN(sa) || isNaN(sb) || (sa === 0 && sb === 0)) continue;
      let rnd = ''; for (const [pos, n] of heads) { if (pos < x.index) rnd = n; else break; }
      const code = (cells[0].split('>').slice(1).join('>').replace(/<span[\s\S]*/, '').match(/[A-Z]?\d+/) || [''])[0];
      if (seen.has(code)) continue; seen.add(code);
      names[ids[0]] = ct[2]; names[ids[1]] = ct[6];
      out.push([code, rnd, +ids[0], sa, ct[4].replace(/[()]/g, ''), sb, +ids[1], ct[8] || '']);
    }
    return [out, names];
  }
  window.tbfResults = window.tbfResults || [];
  window.tbfState = window.tbfState || {running: false, total: 0, error: ''};
  window.tbfStart = function (ids) {
    if (tbfState.running) return 'already running';
    tbfResults = []; tbfState = {running: true, total: ids.length, error: ''};
    (async () => {
      try {
        for (const id of ids) {
          try {
            const p = profile(await page('page_tour_profile?tour=' + id)); await sleep(1000);
            let m = [], n = {};
            if (p && !/SNOOKER|BANT|KARAMBOL|CAROM|PİRAMİT|PIRAMIT/i.test(p[0])) { [m, n] = matches(await page('page_tour_matches?tour=' + id)); await sleep(1000); }
            tbfResults.push({id, p, m, n});
          } catch (e) { tbfResults.push({id, error: String(e)}); }   // left for the next run
        }
      } catch (e) { tbfState.error = String(e); }
      tbfState.running = false;
    })();
    return 'started ' + ids.length;
  };
  window.tbfProgress = () => ({done: tbfResults.length, total: tbfState.total, running: tbfState.running, error: tbfState.error,
    bytes: JSON.stringify(tbfResults).length});
  window.tbfChunk = (i, size) => JSON.stringify(tbfResults.slice(i * size, (i + 1) * size));
  // checksum of a chunk's text (sum of character codes), compared with: python3 tbf_merge.py --sum chunk.json
  window.tbfSum = (i, size) => { const t = tbfChunk(i, size); let x = 0; for (let k = 0; k < t.length; k++) x = (x + t.charCodeAt(k)) % 1000000007; return [t.length, x]; };
  // the whole result as a file download (first full read only; needs the person's approval to download)
  window.tbfDownload = (name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(tbfResults)], {type: 'application/json'})); a.download = name || 'tbf_results.json'; document.body.appendChild(a); a.click(); a.remove(); return 'download started'; };
  return 'tbf ready';
})();

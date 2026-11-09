const g = require('./original.js');
const c = require('./cases.json');
const out = g.processRows(c.rows, c.ref, g.CONFIG.maxCaptionLength);
console.log(JSON.stringify(out.map((r, i) => r[0] ? r.concat([g.normalizeCountry(c.rows[i][1]), g.normalizeRole(c.rows[i][2])]) : r)));

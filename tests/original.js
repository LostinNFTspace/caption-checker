/**
 * Caption Name Checker — Google Sheets + Apps Script
 * Cleans a raw start list before names go to on-screen graphics:
 * spacing, ALL CAPS, "SURNAME Firstname" order, correct spelling and
 * diacritics from a reference list, duplicates, and captions that are too long.
 *
 * Sheets used:
 *   "Start list"       A: Name (as received)  B: Country  C: Role   -> D–G written by the script
 *   "Reference names"  A: Correct spelling (one name per row, row 1 = header)
 *   "Graphics export"  created by "Export for graphics"
 */

const CONFIG = {
  maxCaptionLength: 20,          // characters that fit in the lower-third name strap
  latvianCountries: ['LAT', 'LV'],
  startSheet: 'Start list',
  refSheet: 'Reference names',
  exportSheet: 'Graphics export',
  colors: { OK: '#d9ead3', FIXED: '#fff2cc', NEW: '#cfe2f3', PROBLEM: '#f4cccc' }
};

/* ---------- Menu ---------- */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Caption tools')
    .addItem('Check & clean names', 'checkNames')
    .addItem('Export for graphics', 'exportForGraphics')
    .addSeparator()
    .addItem('Load sample data', 'loadSampleData')
    .addItem('Show "How to use" tab', 'writeHowTo')
    .addToUi();
}

/* ---------- Pure logic (no Sheets calls — unit-testable) ---------- */

const SPECIAL_LETTERS = {
  'ł': 'l', 'Ł': 'L', 'ø': 'o', 'Ø': 'O', 'đ': 'd', 'Đ': 'D',
  'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ı': 'i'
};
// Country codes as typed -> standard code ("Lat", "lv", "Latvia" -> "LAT")
const COUNTRY_ALIASES = { LV: 'LAT', LATVIA: 'LAT', LATVIJA: 'LAT' };
function normalizeCountry(c) {
  const up = cleanSpaces(c).toUpperCase();
  return COUNTRY_ALIASES[up] || up;
}
/** Role as typed -> one style: "player" / "PLAYER" -> "Player", "commentator GUEST" -> "Commentator guest" */
function normalizeRole(r) {
  const t = cleanSpaces(r).toLowerCase();
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : '';
}
const LATVIAN_MARKS = /[āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ]/;

/** Squash all whitespace (incl. non-breaking spaces) to single spaces and trim. */
function cleanSpaces(s) {
  return String(s == null ? '' : s).replace(/[\s\u00a0]+/g, ' ').trim();
}

/** Comparison key: no diacritics, lower case, single spaces. "Bērziņš" -> "berzins". */
function fold(s) {
  return cleanSpaces(s)
    .replace(/[łŁøØđĐßæÆœŒı]/g, c => SPECIAL_LETTERS[c])
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function isAllCapsWord(w) {
  return /\p{L}{2,}/u.test(w) && w === w.toUpperCase();
}

function isAllLowerWord(w) {
  return /\p{L}/u.test(w) && w === w.toLowerCase();
}

/** "hoffmann-schneider" -> "Hoffmann-Schneider", "O'NEILL" -> "O'Neill", "mcdonald" -> "McDonald" */
function titleCaseWord(w) {
  return w.toLowerCase()
    .replace(/(^|[-'’])(\p{L})/gu, (m, sep, ch) => sep + ch.toUpperCase())
    .replace(/^Mc(\p{L})/u, (m, ch) => 'Mc' + ch.toUpperCase());
}

/**
 * Tidy a raw name without a reference list:
 *  - "BERZINS Karlis" -> "Karlis Berzins" (leading ALL-CAPS surname moved to the end)
 *  - "Berzins, Karlis" -> "Karlis Berzins" (comma means surname first)
 *  - Otherwise the order is kept: "Ģermanis Niklāvs" cannot be told apart from a
 *    first-name-first name, so new names are flagged to confirm order
 *  - every word -> Title Case ("ĢERmaNis" -> "Ģermanis"); exact spellings such as
 *    "DeMarco" come from the reference list, which always wins
 */
function normalizeName(raw) {
  let s = cleanSpaces(raw);
  if (!s) return '';
  // "Surname, Firstname" (common in data feeds) -> "Firstname Surname"
  const comma = s.match(/^([^,]+),\s*([^,]+)$/);
  if (comma) s = comma[2] + ' ' + comma[1];
  let words = s.split(' ');
  const caps = words.map(isAllCapsWord);
  const everyWordCaps = caps.every(Boolean);
  if (!everyWordCaps && caps[0]) {
    let k = 0;
    while (k < words.length && caps[k]) k++;
    words = words.slice(k).concat(words.slice(0, k));
  }
  return words
    .map(titleCaseWord)
    .join(' ');
}

/** Folded key -> correct spelling, for both "First Last" and "Last First" order. */
function buildReferenceIndex(refNames) {
  const index = {};
  refNames.map(cleanSpaces).filter(Boolean).forEach(name => {
    const words = name.split(' ');
    index[fold(name)] = name;
    if (words.length > 1) {
      const surnameFirst = [words[words.length - 1]].concat(words.slice(0, -1)).join(' ');
      if (!index[fold(surnameFirst)]) index[fold(surnameFirst)] = name;
    }
  });
  return index;
}

/** "Kārlis Bērziņš" -> "K. Bērziņš" */
function captionForm(name) {
  const words = cleanSpaces(name).split(' ');
  if (words.length < 2) return words[0] || '';
  return words[0].charAt(0).toUpperCase() + '. ' + words[words.length - 1];
}

/**
 * rows: [[rawName, country], ...]
 * returns [[cleanName, caption, status, note], ...] in the same order
 * status: OK | FIXED | NEW | CHECK | DUPLICATE | TOO LONG (several joined with " + ")
 */
function processRows(rows, refNames, maxLen) {
  const index = buildReferenceIndex(refNames);
  const results = rows.map(r => {
    const original = String(r[0] == null ? '' : r[0]);
    const raw = cleanSpaces(original);
    const country = normalizeCountry(r[1]);
    if (!raw) return null;
    const statuses = [];
    const notes = [];
    let clean = normalizeName(raw);
    const fromRef = index[fold(raw)] || index[fold(clean)];
    if (fromRef) {
      if (fromRef !== original) { statuses.push('FIXED'); notes.push('Spelling from reference list (was "' + original + '")'); }
      clean = fromRef;
    } else {
      if (clean !== original) notes.push('Tidied spacing/capitals (was "' + original + '")');
      if (CONFIG.latvianCountries.indexOf(country) !== -1 && !LATVIAN_MARKS.test(clean)) {
        statuses.push('CHECK');
        notes.push('Latvian name not in reference list and has no diacritics — confirm spelling');
      } else {
        statuses.push('NEW');
        notes.push('Not in reference list — confirm spelling and first/last name order, then add it');
      }
    }
    const caption = captionForm(clean);
    if (caption.length > maxLen) {
      statuses.push('TOO LONG');
      notes.push('Caption is ' + caption.length + ' chars, max ' + maxLen);
    }
    return { clean, caption, statuses, notes };
  });

  // Duplicates: same person after cleaning (diacritics and case ignored)
  const seen = {};
  results.forEach((res, i) => {
    if (!res) return;
    const key = fold(res.clean);
    (seen[key] = seen[key] || []).push(i);
  });
  Object.keys(seen).forEach(key => {
    const idx = seen[key];
    if (idx.length > 1) {
      // First occurrence stays usable; later copies are flagged and held back from export
      results[idx[0]].notes.push('Also on row(s) ' + idx.slice(1).map(j => j + 2).join(', ') + ' — kept this one');
      idx.slice(1).forEach(i => {
        results[i].statuses.push('DUPLICATE');
        results[i].notes.push('Duplicate of row ' + (idx[0] + 2));
      });
    }
  });

  return results.map(res => {
    if (!res) return ['', '', '', ''];
    const status = res.statuses.length ? res.statuses.join(' + ') : 'OK';
    return [res.clean, res.caption, status, res.notes.join('; ')];
  });
}

function rowColor(status) {
  if (!status) return null;
  if (/CHECK|DUPLICATE|TOO LONG/.test(status)) return CONFIG.colors.PROBLEM;
  if (/FIXED/.test(status)) return CONFIG.colors.FIXED;
  if (/NEW/.test(status)) return CONFIG.colors.NEW;
  return CONFIG.colors.OK;
}

/* ---------- Sheets actions ---------- */

function checkNames() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const start = ss.getSheetByName(CONFIG.startSheet);
  const ref = ss.getSheetByName(CONFIG.refSheet);
  if (!start || !ref) {
    ui.alert('Missing sheet', 'Need sheets named "' + CONFIG.startSheet + '" and "' + CONFIG.refSheet + '". Use Caption tools → Load sample data to create them.', ui.ButtonSet.OK);
    return;
  }
  const lastRow = start.getLastRow();
  if (lastRow < 2) { ui.alert('The start list is empty.'); return; }

  const rows = start.getRange(2, 1, lastRow - 1, 2).getValues();
  const refLast = ref.getLastRow();
  const refNames = refLast >= 2 ? ref.getRange(2, 1, refLast - 1, 1).getValues().map(r => r[0]) : [];

  const out = processRows(rows, refNames, CONFIG.maxCaptionLength);

  start.getRange(1, 4, 1, 4).setValues([['Clean name', 'Caption', 'Status', 'Note']]).setFontWeight('bold');
  start.getRange(2, 4, out.length, 4).setValues(out);
  start.getRange(2, 1, out.length, 7).setBackgrounds(
    out.map(r => new Array(7).fill(rowColor(r[2])))
  );
  start.autoResizeColumns(1, 5);
  start.setColumnWidth(6, 170); // Status: fixed width fits "FIXED + DUPLICATE" (no shrink-then-grow flicker)
  SpreadsheetApp.flush();

  const counts = {};
  out.forEach(r => { if (r[2]) r[2].split(' + ').forEach(s => counts[s] = (counts[s] || 0) + 1); });
  const total = out.filter(r => r[0]).length;
  ui.alert('Check complete',
    total + ' names checked\n' +
    Object.keys(counts).sort().map(k => k + ': ' + counts[k]).join('\n'),
    ui.ButtonSet.OK);
}

function exportForGraphics() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const start = ss.getSheetByName(CONFIG.startSheet);
  if (!start || start.getLastRow() < 2) { ui.alert('Run "Check & clean names" first.'); return; }
  const data = start.getRange(2, 1, start.getLastRow() - 1, 7).getValues();
  if (data.every(r => !r[5])) { ui.alert('Run "Check & clean names" first.'); return; }

  const ready = [], held = [];
  data.forEach(r => {
    if (!r[3]) return;
    if (/CHECK|DUPLICATE|TOO LONG/.test(r[5])) held.push(r[3]);
    else ready.push([r[3], r[4], normalizeCountry(r[1]), normalizeRole(r[2])]);
  });

  const exp = ss.getSheetByName(CONFIG.exportSheet) || ss.insertSheet(CONFIG.exportSheet);
  exp.clear();
  exp.getRange(1, 1, 1, 4).setValues([['Full name', 'Caption', 'Country', 'Role']]).setFontWeight('bold');
  if (ready.length) exp.getRange(2, 1, ready.length, 4).setValues(ready);
  exp.autoResizeColumns(1, 4);

  ui.alert('Export ready',
    ready.length + ' names exported to "' + CONFIG.exportSheet + '".\n' +
    (held.length ? held.length + ' held back until fixed: ' + held.join(', ') + '\n' : '') +
    'Download it with File → Download → CSV (while that sheet is open).',
    ui.ButtonSet.OK);
}

function loadSampleData() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const ui = SpreadsheetApp.getUi();
  const existing = ss.getSheetByName(CONFIG.startSheet);
  if (existing && existing.getLastRow() > 1) {
    const ok = ui.alert('Replace data?', 'This overwrites the "' + CONFIG.startSheet + '" and "' + CONFIG.refSheet + '" sheets.', ui.ButtonSet.YES_NO);
    if (ok !== ui.Button.YES) return;
  }
  const start = existing || ss.insertSheet(CONFIG.startSheet);
  start.clear();
  start.getRange(1, 1, 1, 3).setValues([['Name (as received)', 'Country', 'Role']]).setFontWeight('bold');
  const sample = [
    ['BERZINS Karlis', 'LAT', 'Player'],
    ['kalnina ilze', 'LAT', 'Player'],
    ['Martins Klavins', 'LAT', 'Player'],
    ['Elina  Steinberga ', 'LAT', 'Player'],
    ['Rudolfs Petersons', 'LAT', 'Commentator guest'],
    ['Agnese Gegere', 'LAT', 'Player'],
    ['Janis Liepins', 'LAT', 'Player'],
    ['Lukasz Kowalski', 'POL', 'Player'],
    ['HRUSKA Ondrej', 'CZE', 'Player'],
    ['Soren Mikkelsen', 'DEN', 'Player'],
    ['Lucia Ferrand', 'ESP', 'Umpire'],
    ['Kārlis Bērziņš', 'LAT', 'Player'],
    ['Maximilian Alexander Hoffmann-Schneider', 'GER', 'Player'],
    ['Peter Smith', 'GBR', 'Player']
  ];
  start.getRange(2, 1, sample.length, 3).setValues(sample);
  start.setFrozenRows(1);

  const ref = ss.getSheetByName(CONFIG.refSheet) || ss.insertSheet(CONFIG.refSheet);
  ref.clear();
  const refNames = [
    'Correct spelling', 'Kārlis Bērziņš', 'Ilze Kalniņa', 'Mārtiņš Kļaviņš', 'Elīna Šteinberga',
    'Rūdolfs Pētersons', 'Agnese Ģēģere', 'Łukasz Kowalski', 'Ondřej Hruška',
    'Søren Mikkelsen', 'Lucía Ferrand', 'Peter Smith'
  ];
  ref.getRange(1, 1, refNames.length, 1).setValues(refNames.map(n => [n]));
  ref.getRange(1, 1).setFontWeight('bold');
  ref.setFrozenRows(1);
  ref.autoResizeColumns(1, 1);

  writeHowTo(true);
  ss.setActiveSheet(start);
  ui.alert('Sample data loaded', 'Now run Caption tools → Check & clean names.', ui.ButtonSet.OK);
}

/** Creates a "How to use" tab: steps and colour legend for anyone opening the sheet. */
function writeHowTo(quiet) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName('How to use') || ss.insertSheet('How to use', 0);
  sh.clear();
  const rows = [
    ['Caption Name Checker', ''],
    ['Cleans a start list before names go to on-screen graphics.', ''],
    ['', ''],
    ['How to use', ''],
    ['1', 'Paste names into "Start list", column A (any format: CAPS, no diacritics, SURNAME first, "Surname, Firstname"). Country code in column B.'],
    ['2', 'Caption tools → Check & clean names.'],
    ['3', 'Fix red rows. Add confirmed names to "Reference names" so they are always spelled right.'],
    ['4', 'Caption tools → Export for graphics, then File → Download → CSV on the "Graphics export" tab.'],
    ['', ''],
    ['Colour', 'Meaning'],
    ['FIXED', 'Spelling, diacritics or order restored from the reference list'],
    ['NEW', 'Not in the reference list: confirm spelling and first/last name order, then add it'],
    ['CHECK / DUPLICATE / TOO LONG', 'Held back from export until fixed'],
    ['OK', 'Already correct'],
    ['', ''],
    ['Name order rule', 'SURNAME in capitals or a comma ("Ozoliņš, Jēkabs") means surname first. Otherwise first name first is assumed — the reference list fixes exceptions permanently.']
  ];
  sh.getRange(1, 1, rows.length, 2).setValues(rows);
  sh.getRange('A1').setFontSize(16).setFontWeight('bold');
  sh.getRange('A4').setFontWeight('bold');
  sh.getRange('A10:B10').setFontWeight('bold');
  sh.getRange('A16').setFontWeight('bold');
  sh.getRange('A11:B11').setBackground(CONFIG.colors.FIXED);
  sh.getRange('A12:B12').setBackground(CONFIG.colors.NEW);
  sh.getRange('A13:B13').setBackground(CONFIG.colors.PROBLEM);
  sh.getRange('A14:B14').setBackground(CONFIG.colors.OK);
  sh.setColumnWidth(1, 220);
  sh.setColumnWidth(2, 640);
  sh.getRange(1, 2, rows.length, 1).setWrap(true);
  sh.getRange(1, 1, rows.length, 2).setHorizontalAlignment('left').setVerticalAlignment('top');
  if (quiet !== true) ss.setActiveSheet(sh);
}

// Lets the pure functions be required by the Node test; ignored in Apps Script.
if (typeof module !== 'undefined') {
  module.exports = { normalizeRole, normalizeCountry, cleanSpaces, fold, normalizeName, buildReferenceIndex, captionForm, processRows, CONFIG };
}

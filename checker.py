"""
Caption name checker: the rules of the Google Sheets version (caption-checker.gs), in Python.
Cleans a raw start list before names go to on-screen graphics: spacing, ALL CAPS,
"SURNAME Firstname" order, spelling and diacritics from a reference list,
duplicates, and captions too long for the name strap.
"""
import io
import re
import unicodedata

MAX_CAPTION = 20                 # characters that fit in the lower-third name strap
LATVIAN_COUNTRIES = {"LAT", "LV"}
COUNTRY_ALIASES = {"LV": "LAT", "LATVIA": "LAT", "LATVIJA": "LAT"}
SPECIAL_LETTERS = {"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
                   "ß": "ss", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ı": "i"}
LATVIAN_MARKS = re.compile(r"[āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ]")
LETTER = r"[^\W\d_]"
HELD_BACK = ("CHECK", "DUPLICATE", "TOO LONG")
# Surname particles: "Jan van der Berg" -> caption "J. van der Berg", not "J. Berg"
PARTICLES = {"van", "der", "den", "de", "von", "da", "di", "del", "della", "la", "le", "dos", "du", "ten", "ter"}

SAMPLE_START = [
    ("BERZINS Karlis", "LAT", "Player"),
    ("kalnina ilze", "LAT", "Player"),
    ("Martins Klavins", "LAT", "Player"),
    ("Elina  Steinberga ", "LAT", "Player"),
    ("Rudolfs Petersons", "LAT", "Commentator guest"),
    ("Agnese Gegere", "LAT", "Player"),
    ("Janis Liepins", "LAT", "Player"),
    ("Lukasz Kowalski", "POL", "Player"),
    ("HRUSKA Ondrej", "CZE", "Player"),
    ("Soren Mikkelsen", "DEN", "Player"),
    ("Lucia Ferrand", "ESP", "Umpire"),
    ("Kārlis Bērziņš", "LAT", "Player"),
    ("Maximilian Alexander Hoffmann-Schneider", "GER", "Player"),
    ("Peter Smith", "GBR", "Player"),
]
SAMPLE_REFERENCE = [
    "Kārlis Bērziņš", "Ilze Kalniņa", "Mārtiņš Kļaviņš", "Elīna Šteinberga", "Rūdolfs Pētersons",
    "Agnese Ģēģere", "Łukasz Kowalski", "Ondřej Hruška", "Søren Mikkelsen", "Lucía Ferrand", "Peter Smith",
]


def clean_spaces(s):
    """Squash all whitespace (incl. non-breaking spaces) to single spaces and trim."""
    return re.sub(r"[\s ]+", " ", "" if s is None else str(s)).strip()


def fold(s):
    """Comparison key: no diacritics, lower case. "Bērziņš" -> "berzins"."""
    s = "".join(SPECIAL_LETTERS.get(c, c) for c in clean_spaces(s))
    s = unicodedata.normalize("NFD", s)
    return re.sub(r"[̀-ͯ]", "", s).lower()


def normalize_country(c):
    up = clean_spaces(c).upper()
    return COUNTRY_ALIASES.get(up, up)


def normalize_role(r):
    t = clean_spaces(r).lower()
    return t[:1].upper() + t[1:]


def is_all_caps(w):
    return bool(re.search(LETTER + "{2,}", w)) and w == w.upper()


def title_case_word(w):
    """"hoffmann-schneider" -> "Hoffmann-Schneider", "O'NEILL" -> "O'Neill", "mcdonald" -> "McDonald" """
    w = re.sub(r"(^|[-'’])(" + LETTER + ")", lambda m: m.group(1) + m.group(2).upper(), w.lower())
    return re.sub(r"^Mc(" + LETTER + ")", lambda m: "Mc" + m.group(1).upper(), w)


def normalize_name(raw):
    """Tidy a name without the reference list.
    "BERZINS Karlis" / "Berzins, Karlis" -> "Karlis Berzins"; every word Title Case.
    Otherwise the order is kept (a new name is flagged to confirm the order)."""
    s = clean_spaces(raw)
    if not s:
        return ""
    m = re.fullmatch(r"([^,]+),\s*([^,]+)", s)
    if m:
        s = m.group(2) + " " + m.group(1)
    words = s.split(" ")
    caps = [is_all_caps(w) for w in words]
    if not all(caps) and caps[0]:
        k = 0
        while k < len(words) and caps[k]:
            k += 1
        words = words[k:] + words[:k]
    # Casing of particles differs by country ("van der Poel" but "De Bruyne"): when the name
    # was typed with care (not all caps / all lower case), a particle keeps the case it was typed in.
    typed_with_care = s != s.lower() and s != s.upper()
    return " ".join(w if typed_with_care and i and w.lower() in PARTICLES and not is_all_caps(w) else title_case_word(w)
                    for i, w in enumerate(words))


def build_reference_index(ref_names):
    """Folded key -> correct spelling, for both "First Last" and "Last First" order."""
    index = {}
    for name in filter(None, map(clean_spaces, ref_names)):
        words = name.split(" ")
        index[fold(name)] = name
        if len(words) > 1:
            surname_first = " ".join([words[-1]] + words[:-1])
            index.setdefault(fold(surname_first), name)
    return index


def caption_form(name):
    """"Kārlis Bērziņš" -> "K. Bērziņš" """
    words = clean_spaces(name).split(" ")
    if len(words) < 2:
        return words[0] if words else ""
    k = len(words) - 1
    while k > 1 and words[k - 1].lower() in PARTICLES:
        k -= 1
    return words[0][:1].upper() + ". " + " ".join(words[k:])


def process_rows(rows, ref_names, max_len=MAX_CAPTION):
    """rows: [(name, country, role), ...] -> one dict per row (None for an empty name).
    status: OK | FIXED | NEW | CHECK | DUPLICATE | TOO LONG (several joined with " + ")."""
    index = build_reference_index(ref_names)
    results = []
    for r in rows:
        original = "" if r[0] is None else str(r[0])
        raw = clean_spaces(original)
        country = normalize_country(r[1] if len(r) > 1 else "")
        role = normalize_role(r[2] if len(r) > 2 else "")
        if not raw:
            results.append(None)
            continue
        statuses, notes = [], []
        clean = normalize_name(raw)
        from_ref = index.get(fold(raw)) or index.get(fold(clean))
        if from_ref:
            if from_ref != original:
                statuses.append("FIXED")
                notes.append(f'Spelling from reference list (was "{original}")')
            clean = from_ref
        else:
            if clean != original:
                notes.append(f'Tidied spacing/capitals (was "{original}")')
            if country in LATVIAN_COUNTRIES and not LATVIAN_MARKS.search(clean):
                statuses.append("CHECK")
                notes.append("Latvian name not in reference list and has no diacritics — confirm spelling")
            else:
                statuses.append("NEW")
                notes.append("Not in reference list — confirm spelling and first/last name order, then add it")
        caption = caption_form(clean)
        if len(caption) > max_len:
            statuses.append("TOO LONG")
            notes.append(f"Caption is {len(caption)} chars, max {max_len}")
        results.append(dict(original=original, clean=clean, caption=caption, country=country, role=role,
                            statuses=statuses, notes=notes))

    # Duplicates: the same person after cleaning (diacritics and case ignored).
    # The first stays usable; later copies are flagged and held back.
    seen = {}
    for i, res in enumerate(results):
        if res:
            seen.setdefault(fold(res["clean"]), []).append(i)
    for idx in seen.values():
        if len(idx) > 1:
            results[idx[0]]["notes"].append("Also on row(s) " + ", ".join(str(j + 1) for j in idx[1:]) + " — kept this one")
            for i in idx[1:]:
                results[i]["statuses"].append("DUPLICATE")
                results[i]["notes"].append(f"Duplicate of row {idx[0] + 1}")

    for res in results:
        if res:
            res["status"] = " + ".join(res["statuses"]) or "OK"
            res["note"] = "; ".join(res["notes"])
            res["held_back"] = any(h in res["status"] for h in HELD_BACK)
    return results


def export_rows(results):
    """Rows ready for the graphics system: everything not held back."""
    return [dict(full_name=r["clean"], caption=r["caption"], country=r["country"], role=r["role"])
            for r in results if r and not r["held_back"]]


def read_table(filename, data):
    """An uploaded CSV or Excel file -> DataFrame of text. Tries the encodings Baltic Windows exports use."""
    import pandas as pd
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=str)
    for enc in ("utf-8-sig", "cp1257", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), dtype=str, sep=None, engine="python", encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("couldn't read the file's text encoding")

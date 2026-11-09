"""
1) Parity: the web version gives the same result as the Google Sheets version on 30 tricky rows.
   expected_from_sheets.json was produced by running the original caption-checker.gs in Node
   (tests/run_original.js). Only the deliberate improvement (surname particles) differs.
2) The rules themselves, written out by hand.
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))
import checker  # noqa: E402

CASES = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
SHEETS = json.loads((HERE / "expected_from_sheets.json").read_text(encoding="utf-8"))
IMPROVED = {21}  # "VAN DER BERG Jan": the Sheets version captioned it "J. Berg"


def sheet_rows(note):
    # the sheet counts the header as row 1, the web table starts at 1
    return re.sub(r"(row\(s\) |row )([\d, ]+?)(?= —|$|;)",
                  lambda m: m.group(1) + ", ".join(str(int(x) + 1) for x in m.group(2).split(", ")), note)


def test_same_result_as_the_sheets_version():
    res = checker.process_rows(CASES["rows"], CASES["ref"])
    for i, (r, want) in enumerate(zip(res, SHEETS)):
        if i in IMPROVED:
            continue
        got = ["", "", "", ""] if r is None else [r["clean"], r["caption"], r["status"], sheet_rows(r["note"]), r["country"], r["role"]]
        assert got == want, (i, CASES["rows"][i])


def test_particles_stay_in_the_caption():
    res = checker.process_rows([("VAN DER BERG Jan", "NED", "Player")], [])
    assert res[0]["caption"] == "J. Van Der Berg"
    assert checker.caption_form("Mathieu van der Poel") == "M. van der Poel"
    assert checker.normalize_name("Mathieu van der Poel") == "Mathieu van der Poel"  # typed with care: kept
    assert checker.normalize_name("Kevin De Bruyne") == "Kevin De Bruyne"


def test_sample_list():
    res = checker.process_rows(checker.SAMPLE_START, checker.SAMPLE_REFERENCE)
    by = {r["original"]: r for r in res}
    assert by["BERZINS Karlis"]["clean"] == "Kārlis Bērziņš" and by["BERZINS Karlis"]["status"] == "FIXED"
    assert by["Kārlis Bērziņš"]["status"] == "DUPLICATE"
    assert by["Janis Liepins"]["status"] == "CHECK"                      # Latvian, no diacritics, unknown
    assert by["Maximilian Alexander Hoffmann-Schneider"]["status"] == "NEW + TOO LONG"
    assert by["Peter Smith"]["status"] == "OK"
    exported = checker.export_rows(res)
    assert len(exported) == 11 and all(e["full_name"] != "Janis Liepins" for e in exported)


def test_country_and_role_one_style():
    assert [checker.normalize_country(c) for c in ["lv", "Latvia", "LATVIJA", " lat ", "gbr"]] == ["LAT"] * 4 + ["GBR"]
    assert checker.normalize_role("commentator GUEST") == "Commentator guest"


def test_empty_rows_ignored():
    assert checker.process_rows([("", "LAT", ""), ("   ", "", "")], []) == [None, None]
    assert checker.export_rows([None]) == []


def test_the_60_second_walkthrough():
    row = [("ozolins janis", "lat", "")]
    assert checker.process_rows(row, checker.SAMPLE_REFERENCE)[0]["status"] == "CHECK"
    fixed = checker.process_rows(row, checker.SAMPLE_REFERENCE + ["Jānis Ozoliņš"])[0]
    assert (fixed["clean"], fixed["status"], fixed["caption"]) == ("Jānis Ozoliņš", "FIXED", "J. Ozoliņš")


def test_upload_semicolon_csv_from_baltic_excel():
    data = "Vārds;Valsts;Loma\nBĒRZIŅŠ Kārlis;LAT;Player\n".encode("cp1257")
    t = checker.read_table("list.csv", data)
    assert list(t.iloc[0]) == ["BĒRZIŅŠ Kārlis", "LAT", "Player"]

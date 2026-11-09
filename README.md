# Caption name checker

Cleans a start list before player names go on screen as captions: ALL CAPS, SURNAME first,
missing Latvian letters, double spaces, duplicates, captions too long for the name strap.
Every change is explained; anything uncertain is held back from the graphics export.

First built as a Google Sheets tool (Apps Script, `tests/original.js`). This is the web version:
`checker.py` holds the rules, `app.py` is the Streamlit page.

Tests: `pytest tests` checks the web version gives the same result as the Sheets version
on 30 tricky names (plus one deliberate improvement: surname particles such as "van der" stay in the caption).

Demo: all names are invented examples.

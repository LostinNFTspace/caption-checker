"""
Caption name checker, web version.
Paste or upload a start list -> clean names and on-screen captions, with every change explained
and anything uncertain held back from the graphics export.
"""
import html
import os

import pandas as pd
import streamlit as st

import checker

st.set_page_config(page_title="Caption name checker", page_icon="🔤", layout="wide")
st.markdown("""<style>
/* keep the page a readable width on big monitors (the results table needs a little more room) */
.block-container{max-width:1400px}
div[data-testid="stMetricValue"]{font-size:1.7rem}
.small{color:#6b7280;font-size:.9rem}
.strap{display:inline-block;margin:6px 12px 6px 0;font-family:Arial,Helvetica,sans-serif}
.strap .n{background:#0b1f3a;color:#fff;font-weight:700;font-size:20px;padding:6px 14px;letter-spacing:.3px}
.strap .c{background:#e8b100;color:#0b1f3a;font-weight:700;font-size:20px;padding:6px 10px}
.strap .r{display:block;background:#fff;color:#0b1f3a;font-size:13px;padding:3px 14px;border:1px solid #d1d5db;border-top:0}
</style>""", unsafe_allow_html=True)

# Row colours: see-through tints, so they read on both the light and the dark theme and stay right
# when the viewer switches theme mid-session (⋮ menu → Settings). Text keeps the theme's own colour.
COLORS = {"held": "rgba(220,38,38,.28)", "FIXED": "rgba(234,179,8,.30)",
          "NEW": "rgba(59,130,246,.28)", "OK": "rgba(34,197,94,.26)"}
TEXT = "inherit"
START_COLS = ["Name (as received)", "Country", "Role"]


# --- demo strip: a 1-minute video and a short how-to, so a first-time visitor knows what this is
PORTFOLIO = "https://janis-saulitis-portfolio.netlify.app"
DEMO_VIDEO = os.environ.get("DEMO_VIDEO", PORTFOLIO + "/media/captions.mp4")


@st.dialog("Caption name checker in 1 minute", width="large")
def show_demo():
    st.video(DEMO_VIDEO, autoplay=True)


def demo_strip():
    bar = st.container(horizontal=True)
    if bar.button("▶ 1-min demo", type="primary", key="demo_btn"):
        show_demo()
    with bar.popover("How it works"):
        st.markdown('1. The sample list below is already checked: `BERZINS Karlis` became `Kārlis Bērziņš`, the duplicate is held back.\n2. Add a row: `ozolins janis`, country `lat`. It turns **red**: a human must confirm the spelling.\n3. Add `Jānis Ozoliņš` under **Reference names** and the row turns **yellow (FIXED)**.\n4. Download the clean list at the bottom. Red rows are left out.')


st.title("Caption name checker")
st.markdown("**Fixes misspelled player names before they go on screen**, and holds back anything uncertain.")
demo_strip()
st.caption("Names are invented examples.")

# ------------------------------------------------------------------ input
def sample_frames():
    return (pd.DataFrame(checker.SAMPLE_START, columns=START_COLS),
            pd.DataFrame({"Correct spelling": checker.SAMPLE_REFERENCE}))


def read_table(upload):
    return checker.read_table(upload.name, upload.getvalue())


if "start" not in st.session_state:
    st.session_state.start, st.session_state.ref = sample_frames()
    st.session_state.ver = 0

st.subheader("1 · Start list")
b = st.container(horizontal=True)
if b.button("↺ Reset to the sample"):
    st.session_state.start, st.session_state.ref = sample_frames()
    st.session_state.ver += 1
if b.button("Clear the list"):
    st.session_state.start = pd.DataFrame(columns=START_COLS)
    st.session_state.ver += 1
with b.popover("Upload my own list (CSV or Excel)"):
    up = st.file_uploader("First three columns: name, country, role", type=["csv", "xlsx"], key=f"up{st.session_state.ver}")
    if up is not None:
        try:
            t = read_table(up).iloc[:, :3]
            while t.shape[1] < 3:
                t[f"extra{t.shape[1]}"] = ""
            t.columns = START_COLS
            st.session_state.start = t.fillna("")
            st.session_state.ver += 1
            st.rerun()
        except Exception as e:
            st.error(f"Couldn't read that file ({e}). Save it as CSV or Excel with name, country, role columns.")

st.markdown('<p class="small">Edit cells directly, paste rows from a spreadsheet, or add rows at the bottom.</p>',
            unsafe_allow_html=True)
start = st.data_editor(st.session_state.start, num_rows="dynamic", width="stretch", hide_index=True,
                       height=36 * (len(st.session_state.start) + 3) + 4,
                       key=f"start{st.session_state.ver}",
                       column_config={START_COLS[0]: st.column_config.TextColumn(width="large")})

with st.expander(f"Reference names: the correct spellings ({len(st.session_state.ref)} names)"):
    st.markdown('<p class="small">The broadcaster\'s master list. A name that matches one of these, ignoring capitals, '
                "missing diacritics and name order, is replaced by the exact spelling here.</p>", unsafe_allow_html=True)
    ref = st.data_editor(st.session_state.ref, num_rows="dynamic", width="stretch", hide_index=True,
                         height=36 * (len(st.session_state.ref) + 3) + 4, key=f"ref{st.session_state.ver}")
    max_len = st.number_input("Longest caption that fits the name strap (characters)", 10, 40, checker.MAX_CAPTION)

# ------------------------------------------------------------------ check
rows = [tuple("" if pd.isna(v) else str(v) for v in r) for r in start[START_COLS].itertuples(index=False)]
results = checker.process_rows(rows, [str(v) for v in ref.iloc[:, 0].dropna()], int(max_len))
done = [(i + 1, r) for i, r in enumerate(results) if r]

st.subheader("2 · Result")
if not done:
    st.info("The start list is empty. Add names above or reset to the sample.")
    st.stop()

held = [r for _, r in done if r["held_back"]]
c = st.columns(4)
c[0].metric("Names checked", len(done))
c[1].metric("Fixed from the reference list", sum("FIXED" in r["status"] for _, r in done))
c[2].metric("Held back for a human", len(held))
c[3].metric("Ready for graphics", len(done) - len(held))

table = pd.DataFrame([{"Row": n, "As received": r["original"], "Clean name": r["clean"], "Caption": r["caption"],
                       "Country": r["country"], "Role": r["role"], "Status": r["status"], "Why": r["note"]}
                      for n, r in done])


def colour(row):
    s = row["Status"]
    key = "held" if any(h in s for h in checker.HELD_BACK) else "FIXED" if "FIXED" in s else "NEW" if "NEW" in s else "OK"
    return [f"background-color:{COLORS[key]}"] * len(row)


st.dataframe(table.style.apply(colour, axis=1), hide_index=True, width="stretch", height=35 * (len(table) + 1) + 3,
             column_config={"Row": st.column_config.NumberColumn(width=45),
                            "Role": st.column_config.TextColumn(width=130),
                            "Status": st.column_config.TextColumn(width=140),
                            "Why": st.column_config.TextColumn(width="large")})
st.markdown('<p class="small">'
            f'<span style="background:{COLORS["FIXED"]};color:{TEXT};padding:1px 6px">FIXED</span> spelling, letters or order restored from the reference list · '
            f'<span style="background:{COLORS["NEW"]};color:{TEXT};padding:1px 6px">NEW</span> not in the reference list: confirm, then add it · '
            f'<span style="background:{COLORS["held"]};color:{TEXT};padding:1px 6px">CHECK / DUPLICATE / TOO LONG</span> held back from the export · '
            f'<span style="background:{COLORS["OK"]};color:{TEXT};padding:1px 6px">OK</span> already correct</p>', unsafe_allow_html=True)

# ------------------------------------------------------------------ preview + export
ready = checker.export_rows(results)
st.subheader("3 · How it looks on screen")
st.markdown("".join(
    f'<span class="strap"><span class="n">{html.escape(e["caption"].upper())}</span>'
    f'<span class="c">{html.escape(e["country"])}</span><span class="r">{html.escape(e["role"])}</span></span>'
    for e in ready[:6]) or "Nothing ready yet.", unsafe_allow_html=True)
st.markdown('<p class="small">A mock lower-third name strap with the first six names that are ready.</p>', unsafe_allow_html=True)

st.subheader("4 · Download")
d = st.columns(2)
export = pd.DataFrame(ready, columns=["full_name", "caption", "country", "role"]).rename(
    columns={"full_name": "Full name", "caption": "Caption", "country": "Country", "role": "Role"})
d[0].download_button(f"⬇ Clean list for graphics ({len(ready)} names, CSV)", export.to_csv(index=False).encode("utf-8-sig"),
                     file_name="captions_for_graphics.csv", mime="text/csv", type="primary")
d[1].download_button("⬇ Full check with reasons (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
                     file_name="caption_check.csv", mime="text/csv")
if held:
    st.warning("Held back until a human confirms: " + ", ".join(f"{r['clean']} ({r['status'].lower()})" for r in held))

st.divider()
st.markdown('<p class="small">Built with AI by Jānis Saulītis. First built as a Google Sheets tool (Apps Script); '
            "this web version is a Python port, tested to give the same result as the original on 30 tricky names.</p>",
            unsafe_allow_html=True)

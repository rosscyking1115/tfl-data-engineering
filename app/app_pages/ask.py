"""Preset data answers and an optional bring-your-own-key chat."""

import os

import assistant
import data_access as da
import quick_answers as qa
import streamlit as st

st.title("Ask the data")
st.caption(
    "The **Quick answers** below query the gold layer without an API key. The optional free-form "
    "chat uses your own Anthropic key."
)

# --- Tier 1: Quick answers (no key, no cost, always on) ------------------------------------
with st.container(border=True):
    st.subheader("Quick answers", anchor=False)
    st.caption("Pick a question. Each answer is generated directly from a fixed data query.")

    choice = st.pills(
        "Question",
        [
            "Why are lines disrupted now?",
            "Busiest stations",
            "Do strikes boost cycling?",
            "Demand trend (last 90 days)",
            "Look up a station",
        ],
        selection_mode="single",
        default="Why are lines disrupted now?",
        label_visibility="collapsed",
    )

    if choice == "Why are lines disrupted now?":
        st.markdown(qa.why_disrupted())
    elif choice == "Busiest stations":
        lo, hi = da.date_bounds()
        years = list(range(hi.year, lo.year - 1, -1))
        default_year = 2024 if 2024 in years else years[0]
        year = st.selectbox("Year", years, index=years.index(default_year))
        st.markdown(qa.busiest_stations(int(year)))
    elif choice == "Do strikes boost cycling?":
        st.markdown(qa.strike_effect())
    elif choice == "Demand trend (last 90 days)":
        st.markdown(qa.demand_trend())
    elif choice == "Look up a station":
        stations = da.station_names()
        default = stations.index("Hyde Park Corner, Hyde Park") if "Hyde Park Corner, Hyde Park" in stations else 0
        station = st.selectbox("Station", stations, index=default)
        st.markdown(qa.station_lookup(station))


# --- Tier 2: Ask anything (bring your own Anthropic key) -----------------------------------
def _env_or_secrets_key() -> str | None:
    if os.getenv("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:  # no secrets.toml at all raises rather than returning empty
        pass
    return None


st.subheader("Ask anything", anchor=False)
st.caption(
    "Claude answers free-form questions by calling the same curated tools. It reports numbers only "
    "when a tool returns them and declines questions outside the available data."
)

key = _env_or_secrets_key()
if not key:
    with st.container(border=True):
        entered = st.text_input(
            "Your Anthropic API key",
            type="password",
            placeholder="sk-ant-…",
            help="Get one at console.anthropic.com. Each question spends a small amount of your credit.",
        )
        st.caption(
            ":material/lock: Used only in this browser session to contact Anthropic. It is never stored, "
            "logged, or committed. Prefer the Quick answers above if you'd rather not use a key."
        )
        if entered:
            st.session_state.byok_key = entered
    key = st.session_state.get("byok_key")

if not key:
    st.stop()

if "chat" not in st.session_state:
    st.session_state.chat = []

for turn in st.session_state.chat:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("tools"):
            st.caption("tools used: " + ", ".join(t["name"] for t in turn["tools"]))

if not st.session_state.chat:
    st.caption("Try: *Which station was busiest in 2024?* · *Do strikes boost cycling?* · *Which lines are disrupted now?*")

if prompt := st.chat_input("Ask about London cycle-hire…"):
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consulting the data…"):
            try:
                res = assistant.answer(prompt, api_key=key)
            except Exception as exc:
                res = {"text": f"That request failed: `{type(exc).__name__}`. "
                               "If you just entered a key, check it's a valid Anthropic key.",
                       "tools_used": []}
        st.markdown(res["text"])
        if res["tools_used"]:
            st.caption("tools used: " + ", ".join(t["name"] for t in res["tools_used"]))
    st.session_state.chat.append(
        {"role": "assistant", "content": res["text"], "tools": res["tools_used"]}
    )

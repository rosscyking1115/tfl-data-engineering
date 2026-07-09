"""Ask the data — a natural-language chat over the gold layer (Claude tool-calling)."""

import os

import streamlit as st

import assistant

st.title("Ask the data")
st.caption(
    "Ask about the cycle-hire dataset in plain English. Claude answers by calling "
    "curated, read-only tools over the gold layer — it can only report numbers a tool "
    "returned, and declines questions outside the data (no made-up figures)."
)

def _has_key() -> bool:
    if os.getenv("ANTHROPIC_API_KEY"):
        return True
    try:
        return "ANTHROPIC_API_KEY" in st.secrets
    except Exception:  # no secrets.toml at all raises rather than returning empty
        return False


if not _has_key():
    st.info("Set `ANTHROPIC_API_KEY` (in `.env` locally, or Streamlit secrets) to enable the assistant.")
    st.stop()

# assistant.answer() reads the key from the environment; mirror it from st.secrets if needed.
if not os.getenv("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]

if "chat" not in st.session_state:
    st.session_state.chat = []

for turn in st.session_state.chat:
    with st.chat_message(turn["role"]):
        st.markdown(turn["content"])
        if turn.get("tools"):
            st.caption("tools used: " + ", ".join(t["name"] for t in turn["tools"]))

examples = "Try: *Which station was busiest in 2024?* · *Do strikes boost cycling?* · *Which lines are disrupted now?*"
if not st.session_state.chat:
    st.caption(examples)

if prompt := st.chat_input("Ask about London cycle-hire…"):
    st.session_state.chat.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Consulting the data…"):
            res = assistant.answer(prompt)
        st.markdown(res["text"])
        if res["tools_used"]:
            st.caption("tools used: " + ", ".join(t["name"] for t in res["tools_used"]))
    st.session_state.chat.append(
        {"role": "assistant", "content": res["text"], "tools": res["tools_used"]}
    )

"""Shared widget helpers for the Streamlit pages."""

from datetime import date

import streamlit as st


def date_range_input(label: str, lo: date, hi: date, *, key: str) -> tuple[date, date]:
    """A date-range picker that always yields exactly two dates.

    `st.date_input` in range mode returns a tuple of 0-2 dates. Between the two clicks of a
    new range it holds only the start date, so the obvious `start, end = st.date_input(...)`
    raises `ValueError: not enough values to unpack` on that rerun and blanks the page.

    Hold the last complete range until the user has chosen a second date.
    """
    picked = st.date_input(label, value=(lo, hi), min_value=lo, max_value=hi, key=key)
    remembered = f"_{key}_complete"
    if isinstance(picked, tuple) and len(picked) == 2:
        st.session_state[remembered] = picked
        return picked
    return st.session_state.get(remembered, (lo, hi))

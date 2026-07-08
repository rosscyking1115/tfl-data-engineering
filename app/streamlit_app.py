"""TfL cycle-hire analytics — public demo over the gold layer.

Entry point: defines navigation over two pages. Data comes from committed Parquet
(see data_access.py), so no warehouse connection is needed.
"""

import streamlit as st

st.set_page_config(
    page_title="TfL cycle-hire analytics",
    page_icon=":material/pedal_bike:",
    layout="wide",
)

pages = [
    st.Page("app_pages/usage_trends.py", title="Usage trends", icon=":material/trending_up:"),
    st.Page("app_pages/station_explorer.py", title="Station explorer", icon=":material/location_on:"),
]
st.navigation(pages).run()

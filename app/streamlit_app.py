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
    st.Page("app_pages/disruption_impact.py", title="Disruption impact", icon=":material/warning:", default=True),
    st.Page("app_pages/forecast.py", title="Demand forecast", icon=":material/insights:"),
    st.Page("app_pages/todays_network.py", title="Today's network", icon=":material/sensors:"),
    st.Page("app_pages/usage_trends.py", title="Usage trends", icon=":material/trending_up:"),
    st.Page("app_pages/station_explorer.py", title="Station explorer", icon=":material/location_on:"),
    st.Page("app_pages/ask.py", title="Ask the data", icon=":material/chat:"),
]
st.navigation(pages).run()

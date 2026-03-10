import streamlit as st
import pandas as pd
import json
import plotly.express as px
import ollama

st.set_page_config(layout="wide", page_title="Sentinel QA AI Analytics Dashboard")

st.title("Sentinel QA AI Analytics Dashboard")

# Load master JSON
MASTER_FILE = "qa_analytics_master.json"
with open(MASTER_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Prepare test dataframe
df = pd.DataFrame(data.get("tests", []))

# Trend data
trend_data = data.get("trends", {})
history_trend = trend_data.get("history-trend", [])

# --------------------- KPIs ---------------------
st.subheader("Key Performance Indicators (KPIs)")
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Tests", len(df))
col2.metric("Passed", (df.status == "passed").sum())
col3.metric("Failed", (df.status == "failed").sum())
col4.metric("Avg Duration (s)", round(df.duration_sec.mean(), 2))

st.divider()

# --------------------- Status Distribution ---------------------
st.subheader("Test Status Distribution")
if not df.empty:
    fig_status = px.histogram(df, x="status", color="status",
                              color_discrete_map={"passed": "green", "failed": "red"},
                              title="Tests by Status")
    st.plotly_chart(fig_status, use_container_width=True)
else:
    st.info("No test data available.")

# --------------------- Module Stability ---------------------
st.subheader("Module Stability")
if not df.empty:
    fig_module = px.histogram(df, x="module", color="status",
                              barmode="group",
                              color_discrete_map={"passed": "green", "failed": "red"},
                              title="Test Status per Module")
    st.plotly_chart(fig_module, use_container_width=True)
else:
    st.info("No module data available.")

# --------------------- Execution Duration ---------------------
st.subheader("Execution Duration by Module")
if not df.empty:
    fig_duration = px.box(df, x="module", y="duration_sec",
                          title="Execution Duration per Module",
                          color="module")
    st.plotly_chart(fig_duration, use_container_width=True)
else:
    st.info("No duration data available.")

# --------------------- Failure Heatmap ---------------------
st.subheader("Top Failures")
failures = df[df.status == "failed"]
if not failures.empty:
    top_errors = failures["error_msg"].value_counts().head(5).reset_index()
    top_errors.columns = ["error_msg", "count"]
    fig_fail = px.bar(top_errors, x="count", y="error_msg", orientation="h",
                      title="Top 5 Error Messages")
    st.plotly_chart(fig_fail, use_container_width=True)
else:
    st.info("No failures detected.")

# --------------------- Historical Build Trend ---------------------
st.subheader("Historical Build Trend")
if history_trend:
    trend_df = pd.DataFrame(history_trend)
    # Check if passed/failed columns exist, otherwise skip
    if all(col in trend_df.columns for col in ["passed", "failed"]):
        fig_trend = px.line(trend_df, x="buildOrder", y=["passed", "failed"],
                            markers=True, title="Historical Pass/Fail Trend")
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("No passed/failed data in history-trend.json")
else:
    st.info("No historical trend data available.")

# --------------------- Failed Test Table ---------------------
st.subheader("Failed Tests Table")
if not failures.empty:
    st.dataframe(failures[["name", "module", "duration_sec", "error_msg"]])
else:
    st.info("No failed tests to display.")

# --------------------- AI Chart Generator ---------------------
st.divider()
st.header("AI Chart Generator")
st.write(
    "Enter a prompt describing the chart you want. "
    "The assistant will return Python Plotly code based on your test dataset."
)
prompt = st.text_area("Enter analysis prompt here...")

if st.button("Generate Chart via AI"):
    if prompt.strip() == "":
        st.warning("Please enter a prompt for AI to generate the chart.")
    else:
        # Provide a sample schema to AI
        schema_json = df.head(5).to_json(orient="records")

        ai_prompt = f"""
You are a QA analytics assistant.
Dataset schema (sample of first 5 rows):
{schema_json}

User request:
{prompt}

Return only Python code using Plotly for chart visualization. Do not return explanations.
"""

        try:
            response = ollama.chat(
                model="qwen2.5-coder:7b",
                messages=[{"role": "user", "content": ai_prompt}]
            )
            code = response["message"]["content"]
            st.subheader("AI Generated Python Code")
            st.code(code, language="python")
        except Exception as e:
            st.error(f"Error communicating with Ollama AI: {e}")
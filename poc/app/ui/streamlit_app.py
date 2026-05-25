"""Streamlit frontend — entrypoint for `streamlit run app/ui/streamlit_app.py`."""
import sys
from pathlib import Path

# Allow running via `streamlit run app/ui/streamlit_app.py` from the poc/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st  # noqa: E402

from app.ui.api_client import get_health, post_chat  # noqa: E402

st.set_page_config(page_title="Insurance Assistant", layout="wide")
st.title("Insurance Assistant — Local RAG PoC")

with st.sidebar:
    st.subheader("Backend status")
    try:
        h = get_health()
        st.success(f"API reachable — Ollama: {h['ollama_reachable']}")
    except Exception as e:
        st.error(f"API unreachable: {e}")

if "history" not in st.session_state:
    st.session_state.history = []

for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        st.write(entry["content"])
        if entry.get("citations"):
            with st.expander("Sources"):
                for c in entry["citations"]:
                    st.caption(f"{c['source']} — page {c['page']}")

question = st.chat_input("Ask about a policy...")
if question:
    st.session_state.history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = post_chat(question)
            except Exception as e:
                st.error(f"Backend error: {e}")
                st.stop()
        st.write(result["answer"])
        if result.get("citations"):
            with st.expander("Sources"):
                for c in result["citations"]:
                    st.caption(f"{c['source']} — page {c['page']}")
        st.session_state.history.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "citations": result.get("citations", []),
            }
        )

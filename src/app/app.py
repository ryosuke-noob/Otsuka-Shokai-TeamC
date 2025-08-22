import os
import time
import streamlit as st

st.set_page_config(page_title="Streamlit + uv + Docker", page_icon="✨", layout="centered")
st.title("Hello, Streamlit 👋")

name = st.text_input("Your name", "world")
st.write(f"Hello, {name}!")

x = st.slider("Pick a number", 0, 100, 42)

@st.cache_data
def square(n: int) -> int:
    time.sleep(0.3)  # デモ用
    return n * n

st.metric("x²", square(x))
st.caption(f"PORT={os.getenv('PORT','8501')}")

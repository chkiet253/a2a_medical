import streamlit as st
from components.chatUI import render_chat

st.set_page_config(page_title="A2A Hospital", layout="centered")
render_chat()
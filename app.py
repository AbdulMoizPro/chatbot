import streamlit as st
from google import genai
import json
import os
from datetime import datetime

st.set_page_config(page_title="Gemini Chat App", page_icon="🤖")

st.title("🤖 Gemini Chat App with Saved Chats")

# ===== API KEY =====
st.sidebar.header("🔑 API Settings")

user_api_key = st.sidebar.text_input(
    "Enter Gemini API Key (optional)",
    type="password"
)

api_key = user_api_key if user_api_key else st.secrets.get("GEMINI_API_KEY", "")

# ===== STORAGE FILE =====
CHAT_FILE = "chat_history.json"

# Load saved chats
if os.path.exists(CHAT_FILE):
    with open(CHAT_FILE, "r") as f:
        saved_chats = json.load(f)
else:
    saved_chats = {}

# ===== SESSION STATE =====
if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_chat" not in st.session_state:
    st.session_state.current_chat = None

# ===== SAVE FUNCTION =====
def save_chat():
    if st.session_state.messages:
        chat_id = st.session_state.current_chat

        if not chat_id:
            chat_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.current_chat = chat_id

        saved_chats[chat_id] = st.session_state.messages

        with open(CHAT_FILE, "w") as f:
            json.dump(saved_chats, f, indent=2)

# ===== SIDEBAR: CHAT LIST =====
st.sidebar.header("💬 Your Chats")

if st.sidebar.button("➕ New Chat"):
    st.session_state.messages = []
    st.session_state.current_chat = None
    st.rerun()

for chat_id in saved_chats.keys():
    if st.sidebar.button(chat_id):
        st.session_state.messages = saved_chats[chat_id]
        st.session_state.current_chat = chat_id
        st.rerun()

# ===== DISPLAY CHAT =====
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ===== INPUT =====
user_prompt = st.chat_input("Ask anything...")

if user_prompt:
    if not api_key:
        st.error("Please provide an API key.")
        st.stop()

    st.session_state.messages.append({
        "role": "user",
        "content": user_prompt
    })

    with st.chat_message("user"):
        st.write(user_prompt)

    try:
        client = genai.Client(api_key=api_key)

        chat_history = []
        for msg in st.session_state.messages:
            role = "user" if msg["role"] == "user" else "model"
            chat_history.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=chat_history
        )

        answer = response.text

        st.session_state.messages.append({
            "role": "assistant",
            "content": answer
        })

        with st.chat_message("assistant"):
            st.write(answer)

        # SAVE CHAT AFTER EACH MESSAGE
        save_chat()

    except Exception as e:
        st.error(f"Error: {e}")
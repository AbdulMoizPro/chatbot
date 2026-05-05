import streamlit as st
from google import genai
from google.genai import types
import sqlite3
from pathlib import Path
from datetime import datetime

# ================= PAGE CONFIG =================
st.set_page_config(page_title="Gemini Chat App", page_icon="🤖")
st.title("🤖 Gemini Chat App with Image Reading")

# ================= SETTINGS =================
MODEL_NAME = "gemini-2.5-flash-lite"
MAX_MEMORY_MESSAGES = 10
MAX_OUTPUT_TOKENS = 600

# ================= DATABASE SETUP =================
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "database"
DB_DIR.mkdir(exist_ok=True)

DB_FILE = DB_DIR / "chat_app.db"


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES chats(id)
        )
    """)

    conn.commit()
    conn.close()


def create_chat(title):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        "INSERT INTO chats (title, created_at) VALUES (?, ?)",
        (title, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )

    chat_id = c.lastrowid
    conn.commit()
    conn.close()

    return chat_id


def save_message(chat_id, role, content):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO messages (chat_id, role, content, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            chat_id,
            role,
            content,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()
    conn.close()


def get_all_chats():
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        SELECT id, title, created_at
        FROM chats
        ORDER BY id DESC
    """)

    chats = c.fetchall()
    conn.close()

    return chats


def get_chat_messages(chat_id):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        """
        SELECT role, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,)
    )

    messages = [
        {
            "role": row["role"],
            "content": row["content"]
        }
        for row in c.fetchall()
    ]

    conn.close()

    return messages


init_db()

# ================= API KEY =================
st.sidebar.header("🔑 API Settings")

user_api_key = st.sidebar.text_input(
    "Enter Gemini API Key optional",
    type="password"
)


def get_secret_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return ""


secret_api_key = get_secret_api_key()

if user_api_key.strip():
    api_key = user_api_key.strip()
else:
    api_key = secret_api_key.strip()

if api_key:
    st.sidebar.success("API key loaded")
else:
    st.sidebar.warning("Please enter API key or add Streamlit secret")

# ================= SESSION STATE =================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "current_chat" not in st.session_state:
    st.session_state.current_chat = None

# ================= SIDEBAR CHATS =================
st.sidebar.header("💬 Your Chats")

if st.sidebar.button("➕ New Chat"):
    st.session_state.messages = []
    st.session_state.current_chat = None
    st.rerun()

all_chats = get_all_chats()

for chat in all_chats:
    chat_id = chat["id"]
    title = chat["title"]
    created_at = chat["created_at"]

    button_label = f"{title} | {created_at}"

    if st.sidebar.button(button_label, key=f"chat_{chat_id}"):
        st.session_state.current_chat = chat_id
        st.session_state.messages = get_chat_messages(chat_id)
        st.rerun()

# ================= IMAGE UPLOAD =================
st.sidebar.header("🖼️ Upload Image")

uploaded_image = st.sidebar.file_uploader(
    "Upload image",
    type=["png", "jpg", "jpeg", "webp"]
)

if uploaded_image:
    st.sidebar.image(
        uploaded_image,
        caption="Uploaded Image",
        use_container_width=True
    )

# ================= DISPLAY CHAT =================
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# ================= CHAT INPUT =================
user_prompt = st.chat_input("Ask anything about text or uploaded image...")

if user_prompt:
    if not api_key:
        st.error("Please enter Gemini API key in the sidebar or add it in Streamlit Secrets.")
        st.stop()

    # Create new chat if no current chat exists
    if st.session_state.current_chat is None:
        chat_title = user_prompt[:40]

        if len(user_prompt) > 40:
            chat_title += "..."

        st.session_state.current_chat = create_chat(chat_title)

    # Save user message in session state
    user_message = {
        "role": "user",
        "content": user_prompt
    }

    st.session_state.messages.append(user_message)

    # Save user message in database
    save_message(
        st.session_state.current_chat,
        "user",
        user_prompt
    )

    # Display user message
    with st.chat_message("user"):
        st.write(user_prompt)

    # Create Gemini client
    client = genai.Client(api_key=api_key)

    # Assistant response box
    with st.chat_message("assistant"):
        response_box = st.empty()
        response_box.markdown("🤖 **Thinking...**")

        answer = ""

        try:
            prompt_lower = user_prompt.lower()

            use_image = uploaded_image and any(
                word in prompt_lower
                for word in [
                    "image",
                    "photo",
                    "picture",
                    "see",
                    "look",
                    "describe",
                    "read",
                    "scan",
                    "analyze"
                ]
            )

            # ================= IMAGE + TEXT MODE =================
            if use_image:
                image_bytes = uploaded_image.getvalue()

                contents = [
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=uploaded_image.type
                    ),
                    user_prompt
                ]

            # ================= TEXT CHAT MODE WITH MEMORY =================
            else:
                recent_messages = st.session_state.messages[-MAX_MEMORY_MESSAGES:]

                contents = []

                for msg in recent_messages:
                    role = "user" if msg["role"] == "user" else "model"

                    contents.append({
                        "role": role,
                        "parts": [
                            {
                                "text": msg["content"]
                            }
                        ]
                    })

            # ================= STREAM RESPONSE LIVE =================
            stream = client.models.generate_content_stream(
                model=MODEL_NAME,
                contents=contents,
                config=types.GenerateContentConfig(
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.4
                )
            )

            for chunk in stream:
                if chunk.text:
                    answer += chunk.text
                    response_box.markdown(answer)

            if not answer.strip():
                answer = "No response received."
                response_box.write(answer)

            # Save assistant message in session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer
            })

            # Save assistant message in database
            save_message(
                st.session_state.current_chat,
                "assistant",
                answer
            )

        except Exception as e:
            response_box.error(f"Error: {e}")

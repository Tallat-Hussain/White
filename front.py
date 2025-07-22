import streamlit as st
import requests
import time
import os
import re
from datetime import datetime
import PyPDF2
import io

# Set page config once at the very top
st.set_page_config(page_title="LangGraph Chatbot",
                   layout="wide", page_icon="🤖")

# === Constants ===
BACKEND_URL = "http://127.0.0.1:8000"

# === Initialize Session State ===
defaults = {
    "auth_page": "login",
    "authenticated": False,
    "user_email": "",
    "messages": [],
    "chat_started": False,
    "last_input": "",
    "session_token": "",
    "chat_history": [],
    "current_chat_id": None,
    "current_chat_title": "New Chat",
    "displayed_chat_count": 15,
    "awaiting_ai_response": False,
    "uploaded_pdf_content": "",
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# === Attempt persistent login from query parameters on load ===
query_params = st.query_params
if "token" in query_params:
    st.session_state.session_token = query_params["token"]

if not st.session_state.authenticated and st.session_state.session_token:
    try:
        res = requests.post(f"{BACKEND_URL}/verify-token",
                            json={"token": st.session_state.session_token})
        if res.status_code == 200 and res.json().get("valid"):
            st.session_state.authenticated = True
            st.session_state.auth_page = "chat"
        else:
            st.session_state.session_token = ""
            st.query_params["token"] = ""
    except Exception as e:
        st.warning(f"Session verification failed: {e}")
        st.session_state.session_token = ""
        st.query_params["token"] = ""

# === Helper to parse messages from backend string format ===
def parse_backend_messages(message_string: str):
    parsed_messages = []
    if not message_string:
        return []

    segments = re.split(r'(User:|Assistant:)', message_string)
    current_role = None
    current_content = []

    for i, segment in enumerate(segments):
        stripped_segment = segment.strip()
        if stripped_segment == "User:":
            if current_role and current_content:
                parsed_messages.append(
                    {"role": current_role.lower(), "content": "\n".join(current_content).strip()})
            current_role = "User"
            current_content = []
        elif stripped_segment == "Assistant:":
            if current_role and current_content:
                parsed_messages.append(
                    {"role": current_role.lower(), "content": "\n".join(current_content).strip()})
            current_role = "Assistant"
            current_content = []
        elif stripped_segment != "":
            current_content.append(stripped_segment)

    if current_role and current_content:
        parsed_messages.append(
            {"role": current_role.lower(), "content": "\n".join(current_content).strip()})

    if not parsed_messages and message_string.strip():
        if message_string.strip().lower().startswith("user:"):
            parsed_messages.append(
                {"role": "user", "content": message_string.replace("User:", "", 1).strip()})
        elif message_string.strip().lower().startswith("assistant:"):
            parsed_messages.append({"role": "assistant", "content": message_string.replace(
                "Assistant:", "", 1).strip()})
        else:
            parsed_messages.append(
                {"role": "user", "content": message_string.strip()})

    return parsed_messages

# === PDF Processing Function ===
def extract_text_from_pdf(pdf_file):
    """Extract text content from uploaded PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text_content = ""
        
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text_content += page.extract_text() + "\n"
        
        return text_content.strip()
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""

# === Fetch Chat History ===
def fetch_chat_history():
    if st.session_state.authenticated:
        headers = {"Authorization": f"Bearer {st.session_state.session_token}"}
        try:
            res = requests.get(f"{BACKEND_URL}/history", headers=headers)
            if res.status_code == 200:
                st.session_state.chat_history = res.json()
            else:
                st.session_state.chat_history = []
                st.error(f"Failed to fetch chat history: {res.text}")
        except Exception as e:
            st.error(f"Error fetching chat history: {e}")
            st.session_state.chat_history = []

# === Load Chat by ID ===
def load_chat(chat_id: int, chat_title: str, messages_string: str):
    st.session_state.current_chat_id = chat_id
    st.session_state.current_chat_title = chat_title
    st.session_state.messages = parse_backend_messages(messages_string)
    st.session_state.chat_started = True
    st.session_state.awaiting_ai_response = False
    st.rerun()

# === Delete Chat ===
def delete_chat_action(chat_id: int):
    if st.session_state.authenticated:
        headers = {"Authorization": f"Bearer {st.session_state.session_token}"}
        try:
            res = requests.delete(
                f"{BACKEND_URL}/history/{chat_id}", headers=headers)
            if res.status_code == 200:
                st.success("Chat deleted successfully!")
                fetch_chat_history()
                if st.session_state.current_chat_id == chat_id:
                    st.session_state.messages = []
                    st.session_state.current_chat_id = None
                    st.session_state.current_chat_title = "New Chat"
                    st.session_state.chat_started = False
                    st.session_state.awaiting_ai_response = False
                st.rerun()
            else:
                st.error(f"Failed to delete chat: {res.text}")
        except Exception as e:
            st.error(f"Error deleting chat: {e}")

# === Rename Chat ===
def rename_chat_logic(chat_id: int, current_title: str, new_title: str):
    if st.session_state.authenticated:
        headers = {"Authorization": f"Bearer {st.session_state.session_token}"}
        try:
            res = requests.put(f"{BACKEND_URL}/history/{chat_id}/rename",
                               headers=headers, params={"new_title": new_title})
            if res.status_code == 200:
                st.success("Chat renamed successfully!")
                fetch_chat_history()
                if st.session_state.current_chat_id == chat_id:
                    st.session_state.current_chat_title = new_title
                st.session_state[f'show_rename_input_{chat_id}'] = False
                st.rerun()
            else:
                st.error(f"Failed to rename chat: {res.text}")
        except Exception as e:
            st.error(f"Error renaming chat: {e}")

# === Logout ===
def logout():
    for key in ["authenticated", "user_email", "messages", "chat_started", "last_input", "session_token", "chat_history", "current_chat_id", "current_chat_title", "displayed_chat_count", "awaiting_ai_response", "uploaded_pdf_content"]:
        if key == "authenticated" or key == "chat_started" or key == "awaiting_ai_response":
            st.session_state[key] = False
        elif key == "messages" or key == "chat_history":
            st.session_state[key] = []
        elif key == "current_chat_id":
            st.session_state[key] = None
        elif key == "displayed_chat_count":
            st.session_state[key] = 15
        else:
            st.session_state[key] = ""

    st.session_state.auth_page = "login"
    st.query_params["token"] = ""
    st.rerun()

# === Login Page ===
def login():
    # Center the login form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<div class='login-container'>", unsafe_allow_html=True)
        st.title("🔐 Login")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        remember = st.checkbox("Remember Me")

        if st.button("Login", use_container_width=True):
            try:
                res = requests.post(
                    f"{BACKEND_URL}/login", data={"username": username, "password": password})
                if res.status_code == 200:
                    data = res.json()
                    st.session_state.authenticated = True
                    st.session_state.user_email = username
                    st.session_state.session_token = data["access_token"]
                    if remember:
                        st.query_params["token"] = st.session_state.session_token
                    else:
                        st.query_params["token"] = ""
                    st.success("Login successful!")
                    st.session_state.auth_page = "chat"
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
            except Exception as e:
                st.error(f"Login failed: {e}")

        if st.button("Go to Signup", use_container_width=True):
            st.session_state.auth_page = "signup"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# === Signup Page ===
def signup():
    # Center the signup form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<div class='login-container'>", unsafe_allow_html=True)
        st.title("📝 Signup")
        username = st.text_input("Username", key="signup_username")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up", use_container_width=True):
            try:
                res = requests.post(
                    f"{BACKEND_URL}/signup", data={"username": username, "password": password})
                if res.status_code == 200:
                    st.session_state.user_email = username
                    st.info(f"OTP has been sent to {username}")
                    st.session_state.auth_page = "verify_otp"
                    st.rerun()
                else:
                    st.error("Signup failed: " + res.text)
            except Exception as e:
                st.error(f"Signup error: {e}")
        
        if st.button("Back to Login", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# === OTP Verification Page ===
def verify_otp():
    # Center the OTP form
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<div class='login-container'>", unsafe_allow_html=True)
        st.title("📨 Verify OTP")
        st.info(f"OTP sent to: {st.session_state.user_email}")
        otp = st.text_input("Enter the 6-digit OTP", key="otp_input")
        if st.button("Verify", use_container_width=True):
            try:
                res = requests.post(f"{BACKEND_URL}/verify-otp", json={
                    "email": st.session_state.user_email,
                    "otp": otp
                })
                if res.status_code == 200:
                    st.success("OTP verified. You can now login.")
                    st.session_state.auth_page = "login"
                    st.rerun()
                else:
                    st.error("Invalid OTP. Try again.")
            except Exception as e:
                st.error(f"OTP verification failed: {e}")
        
        if st.button("Back to Login", use_container_width=True):
            st.session_state.auth_page = "login"
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

# === Chat App ===
def chat_app():
    # Left Sidebar (Chat History)
    with st.sidebar:
        st.button("🚪 Logout", on_click=logout, use_container_width=True)
        st.title("💬 Chat History")

        # Logic to restore ongoing chat on refresh or initial load
        if st.session_state.authenticated and st.session_state.current_chat_id is not None and not st.session_state.messages:
            fetch_chat_history()  # Ensure chat_history is up-to-date
            found_chat = next(
                (chat for chat in st.session_state.chat_history if chat['id'] == st.session_state.current_chat_id), None)
            if found_chat:
                st.session_state.messages = parse_backend_messages(
                    found_chat['messages'])
                st.session_state.current_chat_title = found_chat['title']
                st.session_state.chat_started = True
                st.session_state.awaiting_ai_response = False
            else:
                # If current chat not found (e.g., deleted by another session), reset
                st.session_state.current_chat_id = None
                st.session_state.current_chat_title = "New Chat"
                st.session_state.messages = []
                st.session_state.chat_started = False
                st.session_state.awaiting_ai_response = False

        # New Chat Button
        if st.button("➕ Start New Chat", key="new_chat_btn", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_chat_id = None
            st.session_state.current_chat_title = "New Chat"
            st.session_state.chat_started = False
            st.session_state.awaiting_ai_response = False
            st.session_state.uploaded_pdf_content = ""
            st.rerun()

        st.markdown("---")
        
        # PDF Upload Section
        st.subheader("📄 Upload PDF")
        uploaded_file = st.file_uploader(
            "Choose a PDF file", 
            type="pdf", 
            help="Upload a PDF file to include its content in your chat"
        )
        
        if uploaded_file is not None:
            if st.button("Process PDF", use_container_width=True):
                with st.spinner("Processing PDF..."):
                    pdf_content = extract_text_from_pdf(uploaded_file)
                    if pdf_content:
                        st.session_state.uploaded_pdf_content = pdf_content
                        st.success(f"PDF processed! {len(pdf_content)} characters extracted.")
                    else:
                        st.error("Failed to extract text from PDF.")
        
        if st.session_state.uploaded_pdf_content:
            st.info(f"PDF content loaded ({len(st.session_state.uploaded_pdf_content)} chars)")
            if st.button("Clear PDF", use_container_width=True):
                st.session_state.uploaded_pdf_content = ""
                st.rerun()
        
        st.markdown("---")
        st.write("Your Past Chats:")
        # Always fetch history here to ensure the sidebar is up-to-date
        fetch_chat_history()

        if st.session_state.chat_history:
            try:
                # Sort by timestamp, newest on top
                sorted_history = sorted(
                    st.session_state.chat_history,
                    key=lambda x: datetime.fromisoformat(
                        x.get('timestamp', '1970-01-01T00:00:00') or '1970-01-01T00:00:00'),
                    reverse=True
                )
            except Exception as e:
                st.warning(
                    f"Error sorting chat history by timestamp: {e}. Displaying as is.")
                sorted_history = st.session_state.chat_history

            for chat in sorted_history[:st.session_state.displayed_chat_count]:
                chat_id = chat['id']
                chat_title = chat['title']
                is_renaming = st.session_state.get(
                    f'show_rename_input_{chat_id}', False)

                chat_display_style = "active-chat-item" if chat_id == st.session_state.current_chat_id else "chat-item"

                with st.container():
                    st.markdown(
                        f'<div class="{chat_display_style}">', unsafe_allow_html=True)
                    col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
                    with col1:
                        # Truncate long titles to prevent overflow
                        display_title = chat_title[:30] + "..." if len(chat_title) > 30 else chat_title
                        if st.button(display_title, key=f"chat_load_{chat_id}", use_container_width=True, help=chat_title):
                            load_chat(chat_id, chat_title, chat['messages'])
                    with col2:
                        if st.button("✏️", key=f"rename_toggle_{chat_id}", help="Rename Chat"):
                            st.session_state[f'show_rename_input_{chat_id}'] = not is_renaming
                    with col3:
                        if st.button("🗑️", key=f"delete_confirm_{chat_id}", help="Delete Chat"):
                            delete_chat_action(chat_id)
                    st.markdown('</div>', unsafe_allow_html=True)

                if is_renaming:
                    with st.container():
                        new_title_input = st.text_input(
                            "New title:", value=chat_title, key=f"rename_text_{chat_id}")
                        if st.button("Save", key=f"save_rename_{chat_id}", use_container_width=True):
                            rename_chat_logic(
                                chat_id, chat_title, new_title_input)

            if st.session_state.displayed_chat_count < len(sorted_history):
                if st.button("Show More Chats", key="show_more_chats", use_container_width=True):
                    st.session_state.displayed_chat_count += 15
                    st.rerun()
        else:
            st.info("No chat history yet. Start a new chat!")

    # Main Chat Area
    with st.expander("⚙ Chat Settings", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            system_prompt = st.text_area(
                "System Prompt", 
                placeholder="You are a helpful assistant.", 
                height=100,
                help="Set the behavior and personality of the AI assistant"
            )
            provider = st.radio(
                "Model Provider", ("Groq", "Gemini", "TogetherAI", "White-Fusion"))
        with col2:
            MODEL_NAMES = {
                "Groq": ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
                "Gemini": ["gemini-2.0-flash"],
                "TogetherAI": ["mistralai/Mixtral-8x7B-Instruct-v0.1"],
                "White-Fusion": ["head-model"]
            }
            selected_model = st.selectbox("Select Model", MODEL_NAMES[provider])
            allow_web_search = st.checkbox("🌍 Enable Web Search")

    # Chat Header with better styling
    st.markdown(f"""
        <div class="chat-header">
            <h2>{st.session_state.current_chat_title}</h2>
        </div>
    """, unsafe_allow_html=True)

    # Chat Messages Container
    if not st.session_state.chat_started and not st.session_state.messages:
        st.markdown("""
            <div class="welcome">
                <div style="display: flex; justify-content: center; align-items: baseline;">
                    <div class="logo">W</div>
                    <div style="font-size: 60px; font-weight: 300; color: #999; margin-left: -10px;">hite</div>
                </div>
                <div class="subtitle">What's in your mind today?</div>
                
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="chat-container">', unsafe_allow_html=True)
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                st.markdown(
                    f"""<div class='message-wrapper user-wrapper'>
                        <div class='user-bubble'>{msg['content']}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.markdown(
                    f"""<div class='message-wrapper assistant-wrapper'>
                        <div class='assistant-bubble'>{msg['content']}</div>
                    </div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Chat Input
    user_input = st.chat_input("Type anything you want...")
    if user_input:
        st.session_state.chat_started = True
        
        # Include PDF content if available
        final_input = user_input
        if st.session_state.uploaded_pdf_content:
            final_input = f"[PDF Content]: {st.session_state.uploaded_pdf_content}\n\n[User Question]: {user_input}"
        
        st.session_state.messages.append(
            {"role": "user", "content": user_input})  # Store original user input for display
        st.session_state.awaiting_ai_response = True

        message_for_backend = f"User: {final_input}"  # Send enhanced input to backend
        chat_id_to_send = st.session_state.current_chat_id

        headers = {"Authorization": f"Bearer {st.session_state.session_token}"}

        try:
            save_chat_res = requests.post(
                f"{BACKEND_URL}/chat",
                json={"message": message_for_backend,
                      "chat_id": chat_id_to_send},
                headers=headers
            )
            if save_chat_res.status_code == 200:
                saved_chat_data = save_chat_res.json()
                if not st.session_state.current_chat_id:
                    st.session_state.current_chat_id = saved_chat_data.get(
                        "chat_id")
                # Update title from backend if provided
                if saved_chat_data.get("title"):
                    st.session_state.current_chat_title = saved_chat_data.get(
                        "title")
                fetch_chat_history()  # Refresh history to show new chat/updated entry
            else:
                st.warning(
                    f"Failed to save user message to chat history: {save_chat_res.text}")
        except Exception as e:
            st.warning(f"Error saving user message to chat history: {e}")

        st.rerun()

    if st.session_state.awaiting_ai_response and st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        # Prepare messages for AI, including PDF content if available
        messages_for_ai = st.session_state.messages.copy()
        if st.session_state.uploaded_pdf_content and messages_for_ai:
            # Enhance the last user message with PDF content for AI processing
            last_message = messages_for_ai[-1]
            enhanced_content = f"[PDF Content]: {st.session_state.uploaded_pdf_content}\n\n[User Question]: {last_message['content']}"
            messages_for_ai[-1] = {"role": "user", "content": enhanced_content}
        
        payload = {
            "model_name": selected_model,
            "model_provider": provider,
            "system_prompt": system_prompt,
            "messages": messages_for_ai,
            "allow_search": allow_web_search
        }
        with st.spinner("🤖 Thinking..."):
            try:
                res = requests.post(f"{BACKEND_URL}/chat-ai", json=payload)
                if res.status_code == 200:
                    answer = res.json().get("response", "⚠ No response.")

                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer})

                    assistant_message_for_backend = f"Assistant: {answer}"

                    if st.session_state.current_chat_id:
                        headers = {
                            "Authorization": f"Bearer {st.session_state.session_token}"}
                        try:
                            requests.post(
                                f"{BACKEND_URL}/chat",
                                json={"message": assistant_message_for_backend,
                                      "chat_id": st.session_state.current_chat_id},
                                headers=headers
                            )
                            fetch_chat_history()
                        except Exception as e:
                            st.warning(
                                f"Error saving assistant message to chat history: {e}")

                    # Typing animation
                    placeholder = st.empty()
                    for i in range(1, len(answer) + 1):
                        placeholder.markdown(f"""
                            <div class='message-wrapper assistant-wrapper'>
                                <div class='assistant-bubble'>{answer[:i]}</div>
                            </div>
                        """, unsafe_allow_html=True)
                        time.sleep(0.003)

                else:
                    answer = "❌ Error: backend not responding."
                    st.session_state.messages.append(
                        {"role": "assistant", "content": answer})
            except Exception as e:
                answer = f"❌ Exception: {e}"
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer})

            st.session_state.awaiting_ai_response = False
            st.rerun()


# === Enhanced CSS ===
st.markdown("""
    <style>
    /* Main container improvements */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    /* Login/Signup container */
    .login-container {
        background: white;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 2rem 0;
    }
    
    /* Chat header */
    .chat-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
        text-align: center;
    }
    
    .chat-header h2 {
        margin: 0;
        font-weight: 300;
    }
    
    /* Message wrappers for better alignment */
    .message-wrapper {
        display: flex;
        margin-bottom: 1rem;
        width: 100%;
    }
    
    .user-wrapper {
        justify-content: flex-end;
    }
    
    .assistant-wrapper {
        justify-content: flex-start;
    }
    
    /* Improved chat bubbles with overflow handling */
    .user-bubble {
        display: inline-block;
        padding: 12px 16px;
        border-radius: 18px 18px 4px 18px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 14px;
        max-width: 70%;
        word-wrap: break-word;
        overflow-wrap: break-word;
        white-space: pre-wrap;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        line-height: 1.4;
    }
    
    .assistant-bubble {
        display: inline-block;
        padding: 12px 16px;
        border-radius: 18px 18px 18px 4px;
        background: #f8f9fa;
        color: #333;
        font-size: 14px;
        max-width: 70%;
        word-wrap: break-word;
        overflow-wrap: break-word;
        white-space: pre-wrap;
        border: 1px solid #e9ecef;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
        line-height: 1.4;
    }
    
    /* Welcome screen improvements */
    .welcome {
        text-align: center;
        padding: 80px 20px;
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 20px;
        margin: 2rem 0;
    }
    
    .welcome .logo {
        font-size: 120px;
        font-weight: bold;
        color: #667eea;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.1);
    }
    
    .welcome .subtitle {
        font-size: 24px;
        color: #666;
        margin: 20px 0 40px 0;
        font-weight: 300;
    }
    
 
    
    /* Sidebar improvements */
    .stSidebar .stButton > button {
        width: 100%;
        text-align: left;
        border-radius: 8px;
        border: none;
        background: #f8f9fa;
        color: #333;
        padding: 0.5rem 1rem;
        margin-bottom: 0.25rem;
        transition: all 0.2s ease;
    }
    
    .stSidebar .stButton > button:hover {
        background: #e9ecef;
        transform: translateY(-1px);
    }
    
    /* Chat history items */
    .chat-item {
        margin-bottom: 8px;
        padding: 4px;
        border-radius: 8px;
        background-color: transparent;
        transition: background-color 0.2s ease-in-out;
    }
    
    .chat-item:hover {
        background-color: rgba(255, 255, 255, 0.1);
    }
    
    .active-chat-item {
        margin-bottom: 8px;
        padding: 4px;
        border-radius: 8px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        transition: background-color 0.2s ease-in-out;
    }
    
    .active-chat-item .stButton > button {
        color: white !important;
        background: transparent !important;
    }
    
    /* Responsive design */
    @media (max-width: 768px) {
        .user-bubble, .assistant-bubble {
            max-width: 85%;
            font-size: 13px;
        }
        
        .welcome .logo {
            font-size: 80px;
        }
        
        .welcome .subtitle {
            font-size: 20px;
        }
        
        .features {
            flex-direction: column;
            align-items: center;
        }
        
        .feature-item {
            margin: 0.5rem 0;
        }
    }
    
    /* File uploader styling */
    .stFileUploader > div > div > div > div {
        border: 2px dashed #667eea;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        background: #f8f9fa;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: #f8f9fa;
        border-radius: 8px;
        border: 1px solid #e9ecef;
    }
    
    /* Input field improvements */
    .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #e9ecef;
        padding: 0.75rem;
    }
    
    .stTextArea > div > div > textarea {
        border-radius: 8px;
        border: 1px solid #e9ecef;
        padding: 0.75rem;
    }
    
    /* Chat input styling */
    .stChatInput > div {
        border-radius: 25px;
        border: 2px solid #e9ecef;
        background: black;
    }
    
    .stChatInput input {
        border: none;
        padding: 1rem 1.5rem;
        font-size: 16px;
    }
    
    /* Scrollbar styling */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #c1c1c1;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #a8a8a8;
    }
    </style>
""", unsafe_allow_html=True)

# === Page Routing ===
if st.session_state.authenticated:
    chat_app()
elif st.session_state.auth_page == "signup":
    signup()
elif st.session_state.auth_page == "verify_otp":
    verify_otp()
else:
    login()


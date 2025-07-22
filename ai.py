from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent
from langchain_community.chat_models import ChatOpenAI # Keep if still using, otherwise can remove
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_together import ChatTogether
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
import os
from dotenv import load_dotenv
import datetime # Import datetime for the utcnow() fix (though not used directly in ai.py)

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY")


groq_llm = ChatGroq(model="llama-3.3-70b-versatile")
gemini_llm = ChatGoogleGenerativeAI(model='gemini-2.0-flash')
together_llm = ChatTogether(model="mistralai/Mixtral-8x7B-Instruct-v0.1")


system_prompt_default = "Act as AI chatbot who is smart and friendly"

def get_respoonse(model_name: str, messages: list, allow_search: bool, system_prompt: str, provider: str):
    if provider == 'Groq':
        llm = ChatGroq(model=model_name)
    elif provider == 'Gemini':
        llm = ChatGoogleGenerativeAI(model=model_name)
    elif provider == 'TogetherAI':
        llm = ChatTogether(model=model_name)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    # Ensure all messages are Langchain message objects
    langchain_messages = []
    for msg in messages:
        if isinstance(msg, dict):
            if msg["role"] == "user":
                langchain_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                langchain_messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                langchain_messages.append(SystemMessage(content=msg["content"]))
            # Add any other roles if necessary
        elif isinstance(msg, (HumanMessage, AIMessage, SystemMessage)):
            langchain_messages.append(msg)
        else:
            # If there are other custom message types, convert them here
            # For now, assume this catch is for the problematic __main__.Message
            # If your schemas.Message is coming from api.py, it's a Pydantic model
            # and needs its 'role' and 'content' attributes extracted.
            if hasattr(msg, 'role') and hasattr(msg, 'content'):
                if msg.role == "user":
                    langchain_messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    langchain_messages.append(AIMessage(content=msg.content))
                elif msg.role == "system":
                    langchain_messages.append(SystemMessage(content=msg.content))
                else:
                    print(f"Warning: Unknown role '{msg.role}' for custom message type. Appending as HumanMessage.")
                    langchain_messages.append(HumanMessage(content=msg.content)) # Default to HumanMessage if role is unexpected
            else:
                # If it's truly an unsupported type without role/content, raise an error
                raise TypeError(f"Unsupported message object type: {type(msg)}. Content: {msg}")

    try:
        is_simple_direct_prompt = (
            not allow_search and
            len(langchain_messages) <= 2 and
            all(isinstance(m, (HumanMessage, SystemMessage)) for m in langchain_messages)
        )

        if is_simple_direct_prompt:
            final_messages_for_direct_invoke = []
            if system_prompt and not any(isinstance(m, SystemMessage) for m in langchain_messages):
                final_messages_for_direct_invoke.append(SystemMessage(content=system_prompt))
            final_messages_for_direct_invoke.extend(langchain_messages)
            
            response = llm.invoke(final_messages_for_direct_invoke)
            return {"response": response.content}
        
        chat_msgs = [SystemMessage(content=system_prompt)]
        chat_msgs.extend(langchain_messages)

        tools = [TavilySearchResults(max_results=2)] if allow_search else []
        agent = create_react_agent(model=llm, tools=tools)
        response = agent.invoke({"messages": chat_msgs})
        
        ai_messages = [msg.content for msg in response.get("messages", []) if isinstance(msg, AIMessage)]
        return {"response": ai_messages[-1] if ai_messages else ""}

    except Exception as e:
        print(f"Error in get_respoonse ({provider}, {model_name}): {str(e)}")
        import traceback
        traceback.print_exc()
        return {"response": f"{provider} failed: {str(e)}"}


def get_head_model_response(messages, allow_search, system_prompt):
    try:
        trimmed_messages = messages[-4:]

        def safe_response(name, model, provider):
            try:
                resp = get_respoonse(model, trimmed_messages, allow_search, system_prompt, provider)
                if isinstance(resp, dict):
                    text = resp.get("response", "")
                    return text[:1200] if text else f"{name} returned no answer."
                else:
                    return f"{name} gave unexpected format."
            except Exception as e:
                return f"{name} failed: {str(e)}"

        groq_resp = safe_response("Groq", "llama-3.3-70b-versatile", "Groq")
        together_resp = safe_response("Together", "mistralai/Mixtral-8x7B-Instruct-v0.1", "TogetherAI")
        gemini_resp = safe_response("Gemini", "gemini-2.0-flash", "Gemini")

        history_text = "\n".join(
            f"{msg['role'].capitalize()}: {msg['content']}" if isinstance(msg, dict)
            else f"{msg.role.capitalize()}: {msg.content}"
            for msg in trimmed_messages if msg
        )[:1500]

        combined_prompt = f"""
You are a smart AI that combines responses from multiple AI models into one accurate, helpful answer.

Conversation so far:
{history_text}

Groq said:
{groq_resp}

TogetherAI said:
{together_resp}

Gemini said:
{gemini_resp}

Now, write the best combined response.
""".strip()[:4000]

        print("Fusion prompt length:", len(combined_prompt))

        fused = get_respoonse(
            "gemini-2.0-flash",
            [{"role": "user", "content": combined_prompt}],
            False,
            system_prompt,
            "Gemini"
        )

        if isinstance(fused, dict):
            return {"response": fused.get("response", "⚠️ No fusion response.")}
        return {"response": str(fused)}

    except Exception as e:
        return {"response": f"⚠️ Fusion Error: {str(e)}"}
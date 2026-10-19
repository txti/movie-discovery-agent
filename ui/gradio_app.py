import os

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)
MODEL = os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")
client = OpenAI()


def chat(message, history):
    stream = client.chat.completions.create(
        model=MODEL,
        messages=[*history, {"role": "user", "content": message}],
        stream=True,
    )
    text = ""
    for chunk in stream:
        if chunk.choices:
            text += chunk.choices[0].delta.content or ""
            yield text


demo = gr.ChatInterface(chat, title=f"OpenRouter Chat ({MODEL})")

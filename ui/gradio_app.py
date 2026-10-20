import gradio as gr

from agents.recommender.agent import MODEL, ask


def chat(message: str, history: list[dict]) -> str:
    return ask(message, [{"role": m["role"], "content": m["content"]} for m in history])


demo = gr.ChatInterface(chat, title=f"Movie Recommender ({MODEL})")

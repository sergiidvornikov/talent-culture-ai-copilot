"""Ask questions from the terminal:  python cli.py"""
from assistant import PolicyAssistant


def main() -> None:
    assistant = PolicyAssistant()
    print("HR Policy Assistant. Type a question, or 'quit' to exit.\n")
    while (question := input("> ").strip()).lower() not in {"quit", "exit"}:
        if not question:
            continue
        answer = assistant.ask(question)
        print(f"\n{answer.text}")
        if answer.sources:
            print("Sources: " + "; ".join(answer.sources))
        print(f"[{answer.status}, {answer.latency_ms} ms]\n")


if __name__ == "__main__":
    main()

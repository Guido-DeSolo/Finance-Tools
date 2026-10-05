import argparse
from .local_llm import LocalLLM, LocalLLMError


def main():
    p = argparse.ArgumentParser(prog="df-fintechterm llm ask")
    p.add_argument("prompt", nargs="+")
    a = p.parse_args()
    try: print(LocalLLM().chat([{"role":"user", "content":" ".join(a.prompt)}]))
    except LocalLLMError as e: p.exit(2, f"llm: {e}\n")


if __name__ == "__main__": main()

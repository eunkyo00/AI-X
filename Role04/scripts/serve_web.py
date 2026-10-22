"""Serve only the web frontend on the local computer."""

import argparse
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent.parent / "web"
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Context Search: http://127.0.0.1:{args.port}", flush=True)
        if args.open_browser:
            threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

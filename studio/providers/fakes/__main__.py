"""Run the fake provider server.

Usage: python -m studio.providers.fakes --port 7704
"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Slack + Jira provider server")
    parser.add_argument("--port", type=int, default=7704, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    args = parser.parse_args()

    uvicorn.run(
        "studio.providers.fakes.server:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()

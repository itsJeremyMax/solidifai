"""Run the engine RPC server.

    python -m solidifai_engine --socket /path/engine.sock --artifacts /path/artifacts \
        [--model /path/workspace/model.py]
"""

from __future__ import annotations

import argparse
import os
import signal

from solidifai_engine.control import OverrideChannel
from solidifai_engine.logconfig import setup_logging
from solidifai_engine.server import Server


def main(argv: list[str] | None = None) -> int:
    # Exit hard on SIGTERM; pairs with the parent-death watchdog so the engine
    # can't outlive the app. os._exit avoids blocking on a wedged main thread.
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))

    parser = argparse.ArgumentParser(prog="solidifai_engine")
    parser.add_argument("--socket", required=True, help="UNIX socket path to listen on")
    parser.add_argument("--artifacts", required=True, help="directory for model.glb / model.json")
    parser.add_argument(
        "--model",
        default=None,
        help="durable workspace model file (e.g. <root>/model.py); loaded on "
        "startup if it exists and rewritten on each successful execute_script",
    )
    args = parser.parse_args(argv)

    setup_logging(args.artifacts)
    override_channel = OverrideChannel.from_stdin()
    server = Server(
        args.socket,
        args.artifacts,
        model_path=args.model,
        override_verifier=override_channel.consume,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        override_channel.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

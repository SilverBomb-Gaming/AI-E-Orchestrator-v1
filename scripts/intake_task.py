from __future__ import annotations

import argparse
import json

from ai_e_runtime.task_intake import ConversationalTaskIntake
from orchestrator.config import OrchestratorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert an operator message into a runnable queue task.")
    parser.add_argument("message", nargs="+", help="Plain-language operator request.")
    parser.add_argument("--session-id", default="operator_session", help="Session id recorded in the request payload.")
    parser.add_argument("--channel", default="operator_console", help="Source channel recorded in the request payload.")
    parser.add_argument("--target-repo", default=None, help="Optional explicit target repo override.")
    parser.add_argument(
        "--simulated-delay-seconds",
        type=float,
        default=0.0,
        help="Optional runtime delay for demo/testing so live task awareness can be observed.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    config = OrchestratorConfig.load()
    intake = ConversationalTaskIntake(config)
    result = intake.accept_message(
        " ".join(args.message),
        session_id=args.session_id,
        channel=args.channel,
        target_repo=args.target_repo,
        simulated_delay_seconds=args.simulated_delay_seconds,
    )
    print(
        "TASK ACCEPTED "
        f"task_id={result.task_id} "
        f"status={result.queue_entry.get('status', 'pending')} "
        f"requested_intent={result.routing.requested_intent} "
        f"requested_lane={result.routing.requested_execution_lane} "
        f"execution_lane={result.routing.execution_lane} "
        f"downgraded={str(result.routing.downgraded).lower()} "
        f"capability_id={result.routing.capability_id or 'none'} "
        f"target_repo={result.target_repo}"
    )
    print(
        json.dumps(
            {
                "task_id": result.task_id,
                "request_id": result.request_id,
                "title": result.title,
                "task_type": result.task_type,
                "target_repo": result.target_repo,
                "routing": result.routing.to_payload(),
                "queue_entry": result.queue_entry,
                "request_payload_path": str(result.artifacts.request_payload_path),
                "task_graph_path": str(result.artifacts.task_graph_path),
                "runtime_task_payload_path": str(result.artifacts.runtime_task_payload_path),
                "created": result.created,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
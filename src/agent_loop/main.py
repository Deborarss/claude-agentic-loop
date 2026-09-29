"""CLI: `uv run agent "sua pergunta"`."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .termination import AgentResult, Limits


def _print_result(result: AgentResult, verbose: bool) -> None:
    if verbose:
        print("--- transcript ---")
        for item in result.transcript:
            print(json.dumps(item, ensure_ascii=False, default=str))
        print("------------------")
    print(result.final_text or "(sem texto)")
    print(
        f"\n[parada: {result.stop_reason.value} | voltas: {result.iterations} | tokens: {result.total_tokens}]",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agentic loop com safe termination.")
    parser.add_argument("prompt", help="Pergunta para o agente")
    parser.add_argument(
        "--mode",
        choices=["sdk", "raw"],
        default="sdk",
        help="sdk = Agent SDK (usa o login do Claude Code); raw = Messages API (precisa de ANTHROPIC_API_KEY)",
    )
    parser.add_argument("--max-turns", type=int, default=Limits.max_iterations)
    parser.add_argument("--timeout", type=float, default=Limits.timeout_seconds, help="segundos")
    parser.add_argument("--model", default=None)
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra o transcript")
    args = parser.parse_args(argv)

    limits = Limits(max_iterations=args.max_turns, timeout_seconds=args.timeout)

    if args.mode == "sdk":
        from .sdk_agent import run_sdk_agent

        result = asyncio.run(run_sdk_agent(args.prompt, limits=limits, model=args.model))
    else:
        try:
            import anthropic
        except ImportError:
            print("O modo raw precisa do pacote `anthropic`: uv add anthropic", file=sys.stderr)
            return 2
        from .raw_loop import DEFAULT_MODEL, run_raw_loop

        result = run_raw_loop(anthropic.Anthropic(), args.prompt, model=args.model or DEFAULT_MODEL, limits=limits)

    _print_result(result, args.verbose)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

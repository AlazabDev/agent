from __future__ import annotations

import sys


def main() -> None:
    """Run the Agent CLI without importing CLI dependencies on package import.

    Frappe imports ``agent.hooks`` during site migrations. Keeping the CLI
    import lazy ensures ``import agent`` and ``import agent.hooks`` stay light
    and do not initialize Agent's standalone runtime unnecessarily.
    """
    from agent.cli import cli

    cli(sys.argv[1:])


if __name__ == "__main__" and getattr(sys, "frozen", False):
    main()

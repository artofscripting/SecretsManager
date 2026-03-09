#!/usr/bin/env python3
"""Command-line interface for Harbor vault files on Linux.

This CLI intentionally reuses the existing SecretsSaver backend so vault
encryption, storage format, and migration behavior remain compatible with the
GUI application.
"""

import argparse
import getpass
import os
import shlex
import sys
import textwrap
from typing import Iterable, Optional


# Allow importing secrets_saver.py from the repository root when this script is
# executed from inside linux_cli/.
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from secrets_saver import SecretsSaver  # noqa: E402


def _resolve_password(prompt: str) -> str:
    return getpass.getpass(prompt)


def _load_saver(vault: str) -> SecretsSaver:
    if not os.path.exists(vault):
        raise FileNotFoundError(f"Vault not found: {vault}")
    pw = _resolve_password(f"Master password for {vault}: ")
    return SecretsSaver(filename=vault, key=pw)


def cmd_init(args: argparse.Namespace) -> int:
    if os.path.exists(args.vault) and not args.force:
        print(f"Vault already exists: {args.vault}")
        print("Use --force if you want to open/re-key an existing vault.")
        return 1

    password = _resolve_password("Create master password: ")
    confirm = _resolve_password("Confirm master password: ")
    if password != confirm:
        print("Passwords do not match.")
        return 1

    _ = SecretsSaver(filename=args.vault, key=password)
    print(f"Initialized vault: {args.vault}")
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    saver = _load_saver(args.vault)
    value = getpass.getpass(f"Secret value for {args.group}::{args.name}: ")
    saver.set_secret(name=args.name, value=value, group=args.group, url=args.url)
    print(f"Saved secret: {args.group}::{args.name}")
    return 0


def cmd_get(args: argparse.Namespace) -> int:
    saver = _load_saver(args.vault)
    value = saver.get_secret(name=args.name, group=args.group)
    if value is None:
        print(f"Secret not found: {args.group}::{args.name}")
        return 1
    print(value)
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    saver = _load_saver(args.vault)
    exists_before = saver.get_secret(name=args.name, group=args.group) is not None
    if not exists_before:
        print(f"Secret not found: {args.group}::{args.name}")
        return 1
    saver.delete_secret(name=args.name, group=args.group)
    print(f"Deleted secret: {args.group}::{args.name}")
    return 0


def _print_rows(rows: Iterable[tuple[str, str, str]]) -> None:
    rows = list(rows)
    if not rows:
        print("No secrets found.")
        return

    group_w = max(len("GROUP"), *(len(r[0]) for r in rows))
    name_w = max(len("NAME"), *(len(r[1]) for r in rows))
    print(f"{'GROUP'.ljust(group_w)}  {'NAME'.ljust(name_w)}  URL")
    print(f"{'-' * group_w}  {'-' * name_w}  {'-' * 30}")
    for group, name, url in rows:
        print(f"{group.ljust(group_w)}  {name.ljust(name_w)}  {url}")


def _interactive_list(saver: SecretsSaver, rows: list[tuple[str, str, str]], vault: str) -> int:
    try:
        import curses
    except ImportError:
        _print_rows(rows)
        print("Interactive mode is unavailable in this environment. Use Linux terminal for arrow-key navigation.")
        return 0

    groups: list[str] = sorted({group for group, _name, _url in rows}, key=str.lower)
    items_by_group: dict[str, list[tuple[str, str]]] = {group: [] for group in groups}
    for group, name, url in rows:
        items_by_group[group].append((name, url))
    for group in groups:
        items_by_group[group].sort(key=lambda item: item[0].lower())

    def _draw(stdscr) -> None:
        curses.curs_set(0)
        stdscr.keypad(True)

        in_groups_view = True
        group_idx = 0
        group_top = 0
        item_idx_by_group = {group: 0 for group in groups}
        item_top_by_group = {group: 0 for group in groups}
        revealed: Optional[tuple[str, str, str, str]] = None

        while True:
            height, width = stdscr.getmaxyx()
            list_height = max(5, height - 7)

            stdscr.erase()
            if in_groups_view:
                title = "Harbor Groups - Up/Down: Select group  Enter/Right: Open group  q: Quit"
            else:
                current_group = groups[group_idx]
                title = (
                    f"Group: {current_group} - Up/Down: Select key  Enter: Show value  "
                    "Left: Back to groups  q: Quit"
                )
            stdscr.addnstr(0, 0, title, width - 1)

            if in_groups_view:
                if group_idx < group_top:
                    group_top = group_idx
                if group_idx >= group_top + list_height:
                    group_top = group_idx - list_height + 1

                end = min(len(groups), group_top + list_height)
                for i in range(group_top, end):
                    group = groups[i]
                    count = len(items_by_group[group])
                    line = f"{group} ({count})"
                    attr = curses.A_REVERSE if i == group_idx else curses.A_NORMAL
                    stdscr.addnstr(2 + (i - group_top), 0, line, width - 1, attr)
            else:
                current_group = groups[group_idx]
                current_items = items_by_group[current_group]
                item_idx = item_idx_by_group[current_group]
                item_top = item_top_by_group[current_group]

                if item_idx < item_top:
                    item_top = item_idx
                if item_idx >= item_top + list_height:
                    item_top = item_idx - list_height + 1
                item_top_by_group[current_group] = item_top

                end = min(len(current_items), item_top + list_height)
                for i in range(item_top, end):
                    name, _url = current_items[i]
                    attr = curses.A_REVERSE if i == item_idx else curses.A_NORMAL
                    stdscr.addnstr(2 + (i - item_top), 0, name, width - 1, attr)

            if revealed:
                r_group, r_name, r_url, r_value = revealed
                info_line = f"Selected: {r_group}::{r_name}"
                stdscr.addnstr(height - 4, 0, info_line, width - 1)
                if r_url:
                    stdscr.addnstr(height - 3, 0, f"URL: {r_url}", width - 1)
                wrapped = textwrap.wrap(r_value, width=max(10, width - 1)) or [""]
                stdscr.addnstr(height - 2, 0, f"Value: {wrapped[0]}", width - 1)
                cmd = (
                    f"./harbor-cli --vault {shlex.quote(vault)} get "
                    f"{shlex.quote(r_name)} --group {shlex.quote(r_group)}"
                )
                stdscr.addnstr(height - 1, 0, f"Command: {cmd}", width - 1)

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord("q"), 27):
                break
            if key in (curses.KEY_UP, ord("k")):
                if in_groups_view:
                    group_idx = max(0, group_idx - 1)
                else:
                    current_group = groups[group_idx]
                    item_idx_by_group[current_group] = max(0, item_idx_by_group[current_group] - 1)
                continue
            if key in (curses.KEY_DOWN, ord("j")):
                if in_groups_view:
                    group_idx = min(len(groups) - 1, group_idx + 1)
                else:
                    current_group = groups[group_idx]
                    max_idx = len(items_by_group[current_group]) - 1
                    item_idx_by_group[current_group] = min(max_idx, item_idx_by_group[current_group] + 1)
                continue
            if in_groups_view and key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")):
                in_groups_view = False
                revealed = None
                continue
            if (not in_groups_view) and key in (curses.KEY_LEFT, ord("h"), 127, curses.KEY_BACKSPACE):
                in_groups_view = True
                revealed = None
                continue
            if (not in_groups_view) and key in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT, ord("l")):
                current_group = groups[group_idx]
                name, url = items_by_group[current_group][item_idx_by_group[current_group]]
                value = saver.get_secret(name=name, group=current_group)
                revealed = (current_group, name, url, value if value is not None else "<not found>")

    curses.wrapper(_draw)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    saver = _load_saver(args.vault)
    entries = saver.list_secrets()
    if args.group:
        entries = [e for e in entries if e.get("group", "Default") == args.group]
    rows = [(e.get("group", "Default"), e.get("name", ""), e.get("url", "")) for e in entries]
    rows.sort(key=lambda item: (item[0].lower(), item[1].lower()))

    if not rows:
        print("No secrets found.")
        return 0

    if args.plain or not sys.stdin.isatty() or not sys.stdout.isatty():
        _print_rows(rows)
        return 0

    return _interactive_list(saver, rows, args.vault)


def cmd_groups(args: argparse.Namespace) -> int:
    saver = _load_saver(args.vault)
    groups = sorted({entry.get("group", "Default") for entry in saver.list_secrets()})
    if not groups:
        print("No groups found.")
        return 0
    for group in groups:
        print(group)
    return 0


def cmd_change_password(args: argparse.Namespace) -> int:
    old_pw = _resolve_password(f"Current password for {args.vault}: ")
    saver = SecretsSaver(filename=args.vault, key=old_pw)

    new_pw = _resolve_password("New master password: ")
    confirm = _resolve_password("Confirm new master password: ")
    if new_pw != confirm:
        print("New passwords do not match.")
        return 1

    saver.change_key(new_pw)
    print("Master password updated.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="harbor-cli",
        description="Manage Harbor encrypted .ep vaults from the command line.",
    )
    parser.add_argument("--vault", default="main.ep", help="Path to .ep vault (default: main.ep)")

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize a new vault")
    p_init.add_argument("--force", action="store_true", help="Allow opening existing vault")
    p_init.set_defaults(func=cmd_init)

    p_set = sub.add_parser("set", help="Create or update a secret")
    p_set.add_argument("name", help="Secret name")
    p_set.add_argument("--group", default="Default", help="Group/folder name")
    p_set.add_argument("--url", default="", help="Optional URL metadata")
    p_set.set_defaults(func=cmd_set)

    p_get = sub.add_parser("get", help="Read a secret value")
    p_get.add_argument("name", help="Secret name")
    p_get.add_argument("--group", default="Default", help="Group/folder name")
    p_get.set_defaults(func=cmd_get)

    p_del = sub.add_parser("delete", help="Delete a secret")
    p_del.add_argument("name", help="Secret name")
    p_del.add_argument("--group", default="Default", help="Group/folder name")
    p_del.set_defaults(func=cmd_delete)

    p_list = sub.add_parser("list", help="List secrets")
    p_list.add_argument("--group", help="Only list this group")
    p_list.add_argument("--plain", action="store_true", help="Disable interactive selector output")
    p_list.set_defaults(func=cmd_list)

    p_groups = sub.add_parser("groups", help="List groups")
    p_groups.set_defaults(func=cmd_groups)

    p_chpw = sub.add_parser("change-password", help="Rotate vault master password")
    p_chpw.set_defaults(func=cmd_change_password)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return 1
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    except KeyboardInterrupt:
        print("Cancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

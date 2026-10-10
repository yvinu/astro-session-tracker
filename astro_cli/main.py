"""Entry point for the `astro` command."""

import argparse
import sys

from astro_tracker import checkout_layout, vocabulary

from astro_cli import checkin, checkout, settings
from astro_cli.api import Api, ApiError


def _api(config):
    if not config.get("server") or not config.get("token"):
        sys.exit("Not configured. Run: astro config --server http://<nas>:8000 --token <token>")
    return Api(config["server"], config["token"])


def cmd_config(args, config):
    if args.server:
        config["server"] = args.server
    if args.token:
        config["token"] = args.token
    if args.work_root:
        config["work_root"] = args.work_root
    for item in args.map or []:
        library_path, sep, local = item.partition("=")
        if not sep or not library_path or not local:
            sys.exit(f"--map expects <library path>=<local path or rsync remote>, got '{item}'")
        config.setdefault("path_map", {})[library_path] = local
    settings.save(config)
    shown = dict(config, token="(set)" if config.get("token") else "(not set)")
    for key in ("server", "token", "work_root", "path_map"):
        print(f"{key}: {shown.get(key)}")


def cmd_projects(args, config):
    for project in _api(config).get_json("/api/cli/projects")["projects"]:
        print(f"{project['slug']:<30} {project['status']:<7} {project['target_name']:<20} {project['checkout_count']} checkout(s)")


def cmd_checkout(args, config):
    summary = checkout.run(_api(config), args.project, args.profile, args.dest, config)
    print(f"\nWorking folder: {summary['working_dir']}")
    print(f"Copied {summary['copied']}, already present {summary['already_present']}, failed {len(summary['failed'])}")
    if summary["failed"]:
        for name in summary["failed"]:
            print(f"  did not verify: {name}")
        sys.exit(1)


def _ask_stage(relpath, guess):
    options = "/".join(vocabulary.STAGES)
    while True:
        answer = input(f"Stage for {relpath} [{guess}] ({options}, or skip): ").strip().lower()
        if not answer:
            return guess
        if answer == "skip" or answer in vocabulary.STAGES:
            return answer
        print("  not a Stage")


def cmd_checkin(args, config):
    stages = {}
    for item in args.stage or []:
        name, sep, stage = item.rpartition("=")
        if not sep or (stage != "skip" and stage not in vocabulary.STAGES):
            sys.exit(f"--stage expects <file>=<stage>, with stage one of {', '.join(vocabulary.STAGES)} or skip; got '{item}'")
        stages[name] = stage
    interactive = sys.stdin.isatty() and not args.yes
    summary = checkin.run(
        _api(config), args.project, args.dir, tool=args.tool, run_kind=args.kind, notes=args.notes,
        stages=stages, include_attachments=args.all, choose_stage=_ask_stage if interactive else None,
    )
    print(f"\nFound {summary['found']}, already stored {summary['already_stored']}, "
          f"stored {len(summary['stored'])}, skipped {len(summary['skipped'])}")


def build_parser():
    parser = argparse.ArgumentParser(prog="astro", description="Check subs out of the astro library and check results back in.")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("config", help="Show or change this Mac's settings")
    p.add_argument("--server", help="Address of the library service, e.g. http://nas.local:8000")
    p.add_argument("--token", help="The CLI token set on the service (ASTRO_CLI_TOKEN)")
    p.add_argument("--work-root", help="Folder that working folders are created in")
    p.add_argument("--map", action="append", metavar="LIBRARY=LOCAL",
                   help="Where a library path is read from here: a mounted folder or an rsync remote. Repeatable.")
    p.set_defaults(func=cmd_config)

    p = commands.add_parser("projects", help="List Projects")
    p.set_defaults(func=cmd_projects)

    p = commands.add_parser("checkout", help="Copy a Project's latest Checkout into a working folder")
    p.add_argument("project", help="Project slug or id")
    p.add_argument("--for", dest="profile", default=checkout_layout.DEFAULT_PROFILE, choices=checkout_layout.PROFILES,
                   help="Stacking tool the folder is laid out for")
    p.add_argument("--dest", help="Working folder to use (default: <work root>/<target>__<project>)")
    p.set_defaults(func=cmd_checkout)

    p = commands.add_parser("checkin", help="Send a working folder's outputs and logs to the Project")
    p.add_argument("project", help="Project slug or id")
    p.add_argument("--dir", default=".", help="Working folder (default: current folder)")
    p.add_argument("--tool", help="Tool this run used (default: guessed from the files)")
    p.add_argument("--kind", choices=("stacking", "post"), help="Kind of run (default: guessed)")
    p.add_argument("--notes", help="What was done, for steps the tools did not log")
    p.add_argument("--stage", action="append", metavar="FILE=STAGE", help="Set an image's Stage, or FILE=skip. Repeatable.")
    p.add_argument("--all", action="store_true", help="Also upload files of unrecognised kinds")
    p.add_argument("--yes", action="store_true", help="Accept guessed Stages without asking")
    p.set_defaults(func=cmd_checkin)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args, settings.load())
    except (ApiError, settings.PathMapError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import os
import sys
import argparse
import traceback
from colorama import init as colorama_init, Fore

from commands.init    import init_main
from commands.stage   import stage_main
from commands.sync    import sync_main
from commands.build   import build_main
from commands.launch  import launch_main
from commands.prepare_base import prepare_base_main
from commands.clean import clean_main
from commands.validate import validate_main
from commands.pixi import pixi_main
from core.exceptions import ForgeError, ConfigurationError, ValidationError
from python_on_whales.exceptions import DockerException
import subprocess

def create_parser():
    colorama_init(autoreset=True)
    p = argparse.ArgumentParser(
        prog="forge",
        description="forge: build & deploy ROS2 in Docker"
    )
    p.add_argument('-p','--project-root', dest='project_root',
                   help='Path to project root')
    p.add_argument('-f','--config', dest='config_file', default='config.yaml',
                   help='Path to configuration file (default: config.yaml)')
    p.add_argument('project_root_pos', nargs='?',
                   help=argparse.SUPPRESS)

    sp = p.add_subparsers(dest='command', required=True)

    pp = sp.add_parser('prep', help='Build base ROS image')
    pp.set_defaults(func=lambda args: prepare_base_main(args.project_root, config_file=args.config_file))

    # init
    pi = sp.add_parser('init', help='Bootstrap a new project')
    pi.set_defaults(func=lambda args: init_main(args.project_root, config_file=args.config_file))

    # stage (formerly prep)
    ps = sp.add_parser('stage', help='Generate multi-stage Dockerfiles & Compose')
    ps.add_argument('-c','--component', default=None,
                    help='Only stage this single component')
    ps.add_argument('--refresh', action='store_true', help='Only re-render docker-compose.yml')
    ps.add_argument('--force-base', action='store_true', help='Force rebuild of base image')
    ps.add_argument('--no-pull', action='store_true',
                    help="Skip pulling images on hosts after build (use 'forge sync' to pull later)")
    ps.add_argument('-j','--jobs', type=int, default=1,
                    help='Max number of components to build in parallel (default: 1)')
    ps.set_defaults(func=lambda args: stage_main(
        project_root=args.project_root,
        component=args.component,
        refresh=args.refresh,
        force_base=args.force_base,
        no_pull=args.no_pull,
        jobs=args.jobs,
        config_file=args.config_file
    ))

    # sync
    psync = sp.add_parser('sync', help='Pull base & component images on hosts')
    psync.add_argument('--host', default=None,
                       help='Only pull on this host (name from config)')
    psync.add_argument('-c','--component', default=None,
                       help='Only pull this component image')
    psync.add_argument('--skip-base', action='store_true', help='Skip pulling the base image')
    psync.add_argument('--skip-components', action='store_true', help='Skip pulling component images')
    psync.add_argument('-j','--jobs', type=int, default=1,
                       help='Max parallel pulls (default: 1)')
    psync.set_defaults(func=lambda args: sync_main(
        project_root=args.project_root,
        host_name=args.host,
        component=args.component,
        skip_base=args.skip_base,
        skip_components=args.skip_components,
        jobs=args.jobs,
        config_file=args.config_file
    ))

    # build
    pb = sp.add_parser('build', help='Compile workspaces in Docker')
    pb.add_argument('-c','--component', default=None,
                    help='Only build this single component')
    pb.add_argument('-j','--jobs', type=int, default=1,
                    help='Max number of components to build in parallel (default: 1)')
    pb.set_defaults(func=lambda args: build_main(
        project_root=args.project_root,
        component=args.component,
        jobs=args.jobs,
        config_file=args.config_file
    ))

    # launch
    pl = sp.add_parser('launch', help='Rsync builds & launch containers')
    pl.add_argument('--host', default=None,
                    help='Only launch on this host (name from config file)')
    pl.add_argument('--no-pull', action='store_true',
                    help='Skip pulling images (use existing local images)')
    pl.set_defaults(func=lambda args: launch_main(
        project_root=args.project_root,
        host_name=args.host,
        no_pull=args.no_pull,
        config_file=args.config_file
    ))

    # clean
    pcl = sp.add_parser('clean', help='Remove build artifacts and workspaces')
    pcl.add_argument('-r', '--remote', action='store_true',
                     help='Also clean remote hosts')
    pcl.add_argument('--local-only', action='store_true',
                     help='Clean only local artifacts (overrides -r)')
    pcl.set_defaults(func=lambda args: clean_main(
        project_root=args.project_root,
        remote=args.remote and not args.local_only,
        local=True,
        config_file=args.config_file
    ))

    # validate
    pval = sp.add_parser('validate', help='Validate configuration without executing operations')
    pval.set_defaults(func=lambda args: sys.exit(validate_main(project_root=args.project_root, config_file=args.config_file)))

    # pixi
    ppixi = sp.add_parser('pixi', help='Activate robostack/pixi environment with DDS configuration')
    ppixi.add_argument('-e', '--env', default='ros_env',
                        help='Name of the robostack environment (default: ros_env)')

    ppixi.set_defaults(func=lambda args: pixi_main(
        project_root=args.project_root,
        env_name=args.env,
        config_file=args.config_file
    ))

    return p

def main():
    parser = create_parser()
    args   = parser.parse_args()

    pr = args.project_root or args.project_root_pos
    if not pr and args.command!='init':
        parser.print_usage()
        sys.exit("[ERROR] project root must be set via -p or positional")
    args.project_root = os.path.abspath(pr) if pr else None

    try:
        args.func(args)
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\n[INFO] Interrupted by user", file=sys.stderr)
        sys.exit(130)
    except (ConfigurationError, ValidationError) as e:
        print(Fore.RED + f"[ERROR] Configuration error: {e}", file=sys.stderr)
        if hasattr(e, 'context') and e.context:
            # Special handling for multiple errors
            if 'errors' in e.context:
                errors = e.context['errors']
                print(Fore.RED + f"\nFound {len(errors)} validation error(s):", file=sys.stderr)
                for i, error in enumerate(errors, 1):
                    print(Fore.RED + f"  {i}. {error}", file=sys.stderr)
            else:
                print(Fore.RED + "\nAdditional context:", file=sys.stderr)
                for key, value in e.context.items():
                    print(Fore.RED + f"  - {key}: {value}", file=sys.stderr)
        sys.exit(1)
    except ForgeError as e:
        print(Fore.RED + f"[ERROR] {e}", file=sys.stderr)
        if hasattr(e, 'context') and e.context:
            # Special handling for multiple errors
            if 'errors' in e.context:
                errors = e.context['errors']
                print(Fore.RED + f"\nFound {len(errors)} error(s):", file=sys.stderr)
                for i, error in enumerate(errors, 1):
                    print(Fore.RED + f"  {i}. {error}", file=sys.stderr)
            else:
                print(Fore.RED + "\nAdditional context:", file=sys.stderr)
                for key, value in e.context.items():
                    print(Fore.RED + f"  - {key}: {value}", file=sys.stderr)
        sys.exit(1)
    except DockerException as e:
        print(Fore.RED + f"[ERROR] Docker command failed", file=sys.stderr)

        # Extract useful information from the exception
        if hasattr(e, 'docker_command') and e.docker_command:
            # Show simplified command (remove full paths)
            cmd = ' '.join(e.docker_command)
            cmd = cmd.replace('/usr/local/bin/docker', 'docker')
            cmd = cmd.replace('/opt/homebrew/bin/docker', 'docker')
            print(Fore.RED + f"\nCommand: {cmd}", file=sys.stderr)

        if hasattr(e, 'return_code') and e.return_code:
            print(Fore.RED + f"Exit code: {e.return_code}", file=sys.stderr)

        # The actual error output was already printed to stderr by docker
        print(Fore.YELLOW + f"\nTip: Check the output above for details", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(Fore.RED + f"[ERROR] Command failed", file=sys.stderr)

        # Show the command that failed
        if e.cmd:
            if isinstance(e.cmd, list):
                cmd = ' '.join(e.cmd)
            else:
                cmd = e.cmd
            print(Fore.RED + f"\nCommand: {cmd}", file=sys.stderr)

        if e.returncode:
            print(Fore.RED + f"Exit code: {e.returncode}", file=sys.stderr)

        # Show stdout/stderr if captured
        if e.stdout:
            print(Fore.YELLOW + f"\nOutput:", file=sys.stderr)
            print(e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout, file=sys.stderr)
        if e.stderr:
            print(Fore.YELLOW + f"\nError output:", file=sys.stderr)
            print(e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr, file=sys.stderr)

        sys.exit(1)
    except Exception:
        print(Fore.RED + "[ERROR] Unhandled exception:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':
    main()

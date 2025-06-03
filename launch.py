# import faulthandler
# faulthandler.enable()

from modules import launch_utils

args = launch_utils.args
python = launch_utils.python
git = launch_utils.git
index_url = launch_utils.index_url
dir_repos = launch_utils.dir_repos

commit_hash = launch_utils.commit_hash
git_tag = launch_utils.git_tag

run = launch_utils.run
is_installed = launch_utils.is_installed
repo_dir = launch_utils.repo_dir

run_pip = launch_utils.run_pip
from pathlib import Path # This line was successfully added in a previous step
check_run_python = launch_utils.check_run_python
git_clone = launch_utils.git_clone
git_pull_recursive = launch_utils.git_pull_recursive
list_extensions = launch_utils.list_extensions
run_extension_installer = launch_utils.run_extension_installer
prepare_environment = launch_utils.prepare_environment
configure_for_tests = launch_utils.configure_for_tests
start = launch_utils.start


def main():
    if args.dump_sysinfo:
        filename = launch_utils.dump_sysinfo()

        print(f"Sysinfo saved as {filename}. Exiting...")

        exit(0)

    launch_utils.startup_timer.record("initial startup")

    # Configure A1111 reference path
    # Use hasattr to gracefully handle if the arg is somehow not defined, though argparse should ensure it.
    if hasattr(args, 'forge_ref_a1111_home') and args.forge_ref_a1111_home:
        print(f"Using A1111 path from command line argument: {args.forge_ref_a1111_home}")
        # The function in launch_utils expects a Path object.
        a1111_path_to_configure = Path(args.forge_ref_a1111_home)
        launch_utils.configure_forge_reference_checkout(a1111_path_to_configure)
    else:
        # get_a1111_path was added in the previous subtask and is available via launch_utils
        a1111_path_str = launch_utils.get_a1111_path()
        if a1111_path_str: # a1111_path_str is a string or None. If string, it's a valid path.
            print(f"Using A1111 path from configuration: {a1111_path_str}")
            launch_utils.configure_forge_reference_checkout(Path(a1111_path_str))
        else:
            # This case means get_a1111_path() returned None (user chose fresh install or skipped path input)
            print("Proceeding with a fresh Forge installation. Default paths will be used.")
            print("If you intended to use an existing A1111/Forge installation, please restart and choose 'yes' when prompted, or use the --forge-ref-a1111-home command-line argument.")

    with launch_utils.startup_timer.subcategory("prepare environment"):
        if not args.skip_prepare_environment:
            prepare_environment()

    if args.test_server:
        configure_for_tests()

    # The original block for args.forge_ref_a1111_home has been integrated above and is no longer needed here.
    # if args.forge_ref_a1111_home:
    #     launch_utils.configure_forge_reference_checkout(args.forge_ref_a1111_home)

    start()


if __name__ == "__main__":
    main()

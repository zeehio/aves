import importlib.resources

import argparse
import os
from shutil import copyfile
import sys
import yaml
from aves.utils import mkdir_p


_TEMPLATE_PACKAGE = 'aves.templates.simple_demo'


def parse_arguments():
    """
    Parses command line arguments
    """
    parser = argparse.ArgumentParser(description="Create files")
    # add expected arguments
    parser.add_argument("--destdir", dest='destdir', default=None,
                        help="Path where the template will be copied")

    # parse args
    args = parser.parse_args()
    if args.destdir is None:
        # Only needed as a fallback when --destdir is omitted, so this
        # stays a local import: it's the only thing in this module that
        # needs Tk installed.
        from aves import dialogs
        args.destdir = dialogs.dirname_from_dialog(path=".")
    return args


def scaffold_project(destdir):
    """
    Copies aves' template files into destdir, creating destdir if it
    doesn't exist yet.

    Args:
        destdir (str): Path where the template's files will be copied.

    Returns:
        list: The relative paths that were copied into destdir.

    Raises:
        FileExistsError: destdir already contains a file the template
            would write. Nothing is copied in that case.
    """
    if not os.path.exists(destdir):
        mkdir_p(destdir)
    pkg_files = importlib.resources.files(_TEMPLATE_PACKAGE)
    res_to_copy = yaml.safe_load((pkg_files / 'skeleton.yaml').read_text())
    conflicts = [
        os.path.join(destdir, res) for res in res_to_copy
        if os.path.exists(os.path.join(destdir, res))
    ]
    if conflicts:
        raise FileExistsError(
            "The following files already exist. Please remove or rename "
            "them: " + ", ".join(conflicts))
    for res in res_to_copy:
        with importlib.resources.as_file(pkg_files / res) as res_path:
            copyfile(res_path, os.path.join(destdir, res))
    return res_to_copy


if __name__ == '__main__':
    args = parse_arguments()
    try:
        copied = scaffold_project(destdir=args.destdir)
    except FileExistsError as exc:
        print(exc)
        sys.exit(1)
    print("Copied {} to {}".format(", ".join(copied), args.destdir))

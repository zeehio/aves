import importlib.resources

import argparse
import os
from shutil import copyfile
import sys
import yaml
from aves.utils import mkdir_p


VALID_TEMPLATES = ['simple_demo']


def parse_arguments():
    """
    Parses command line arguments
    """
    parser = argparse.ArgumentParser(description="Create files")
    # add expected arguments
    parser.add_argument("--template", dest='template', default='simple_demo',
                        help="Template to use [" + ", ".join(VALID_TEMPLATES) + "]")
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


def scaffold_project(destdir, template='simple_demo'):
    """
    Copies the given template's files into destdir, creating destdir if
    it doesn't exist yet.

    Args:
        destdir (str): Path where the template's files will be copied.
        template (str): One of VALID_TEMPLATES.

    Returns:
        list: The relative paths that were copied into destdir.

    Raises:
        ValueError: template is not a known template.
        FileExistsError: destdir already contains a file the template
            would write. Nothing is copied in that case.
    """
    if template not in VALID_TEMPLATES:
        raise ValueError(
            template + " is not a valid template (valid templates are: " +
            ", ".join(VALID_TEMPLATES) + ")")
    if not os.path.exists(destdir):
        mkdir_p(destdir)
    pkg = 'aves.templates.' + template
    pkg_files = importlib.resources.files(pkg)
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
        copied = scaffold_project(destdir=args.destdir, template=args.template)
    except (ValueError, FileExistsError) as exc:
        print(exc)
        sys.exit(1)
    print("Copied {} from template {!r} to {}".format(
        ", ".join(copied), args.template, args.destdir))

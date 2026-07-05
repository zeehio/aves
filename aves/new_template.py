import importlib.resources as importlib_res

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
    if args.template not in VALID_TEMPLATES:
        raise ValueError(args.template + " is not a valid template (Valid " +
                         "templates are: " + ", ".join(VALID_TEMPLATES) + ")")
    if args.destdir is None:
        # Only needed as a fallback when --destdir is omitted, so this
        # stays a local import: it's the only thing in this module that
        # needs Tk installed.
        from aves import dialogs
        args.destdir = dialogs.dirname_from_dialog(path=".")
    if not os.path.exists(args.destdir):
        mkdir_p(args.destdir)
    # Uncomment to debug the output of argparse:
    # raise ValueError(args)
    return args


if __name__ == '__main__':
    args = parse_arguments()
    pkg = 'aves.templates.' + args.template
    skeleton_stream = importlib_res.open_text(pkg, 'skeleton.yaml')
    res_to_copy = yaml.safe_load(skeleton_stream)
    print("Copying files from template: " + args.template +
          " to " + args.destdir)
    res_that_already_exist = []
    for res in res_to_copy:
        dst = os.path.join(args.destdir, res)
        if os.path.exists(dst):
            res_that_already_exist.append(dst)
    if len(res_that_already_exist) > 0:
        print("The following files already exist. Please remove or rename them:")
        print(res_that_already_exist)
        sys.exit(1)
    for res in res_to_copy:
        with importlib_res.path(pkg, res) as res_path:
            print(res)
            dst = os.path.join(args.destdir, res)
            if os.path.exists(dst):
                print("Destination file already exists. Stopping")
                sys.exit(1)
            copyfile(res_path, dst)
    print("All files were copied")

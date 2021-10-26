#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import sys
import click
from woylie.woylie import PhotoWoylie, MetadataBase, Files, Folders
from pathlib import Path


def common_options(fn):
    for decorator in (
        click.option(
            "--symlink",
            help="use symlinks instead of hardlinks for linking the pictures in the by-XYZ folders",
            default=False,
            is_flag=True,
        ),
        click.option(
            "--dump-exif",
            "-d",
            "dump_exif",
            help="save exif information per import into the log directory",
            default=False,
            is_flag=True,
        ),
        click.option(
            "--language",
            "-l",
            type=click.STRING,
            help="browser language code for request to OpenStreetMap. Defaults to local language of OSM",
        ),
    ):
        fn = decorator(fn)
    return fn


@click.group()
@click.version_option()
def cli():
    """this is the PhotoWoylie tool! Organize your photos"""
    pass


@cli.command()
@click.argument(
    "path",
    nargs=-1,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
def stop(path):
    """disallow woylie to scan a directory and it's children by creating a file"""
    for p in path:
        PhotoWoylie.stop(p)


@cli.command()
def list_extensions():
    """list extensions of files that will be sorted and quit"""
    PhotoWoylie.show_extensions()


@cli.command()
@click.argument(
    "base-path",
    nargs=1,
    type=click.Path(file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
@click.argument(
    "import-path",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, allow_dash=False),
    required=True,
)
@common_options
@click.option(
    "-e",
    "--include-extensions",
    "extensions",
    multiple=True,
    type=click.STRING,
    help="add_origin extensions to include",
)
def import_files(
    base_path,
    import_path,
    symlink=False,
    dump_exif=False,
    language=None,
    extensions=None,
):
    """import images and movies to your library"""
    woylie = PhotoWoylie(
        base_path=base_path,
        hardlink=not symlink,
        dump_exif=dump_exif,
        lang=language,
    )

    woylie.add_extensions(extensions)

    for path in import_path:
        woylie.import_files(path)


@cli.command()
@click.argument(
    "base-path",
    nargs=1,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
@click.argument(
    "remove-path",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, allow_dash=False),
    required=True,
)
@common_options
def remove(
    base_path,
    remove_path,
    symlink=False,
    dump_exif=False,
    language=None,
):
    """remove files from the library"""
    woylie = PhotoWoylie(
        base_path=base_path, hardlink=not symlink, dump_exif=dump_exif, lang=language
    )
    for path in remove_path:
        woylie.remove_files(path)


@cli.command()
@click.argument(
    "base-path",
    nargs=1,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
@common_options
@click.option(
    "--reset",
    help="reset all metadata, including import history and cache",
    is_flag=True,
)
def rebuild(
    base_path,
    symlink=False,
    dump_exif=False,
    language=None,
    reset=False,
):
    """rebuild the library"""
    woylie = PhotoWoylie(
        base_path=base_path, hardlink=not symlink, dump_exif=dump_exif, lang=language
    )
    woylie.rebuild(reset=reset)


@cli.command()
@common_options
@click.argument(
    "base-path",
    nargs=1,
    type=click.Path(file_okay=False, dir_okay=True, allow_dash=False),
    required=True,
)
def infer(
    base_path,
    symlink=False,
    dump_exif=False,
    language=None,
):
    """ infer Metadata from existing pictures in the database and link them"""
    woylie = PhotoWoylie(
        base_path=base_path, hardlink=not symlink, dump_exif=dump_exif, lang=language
    )
    woylie.infer()


if "__main__" == __name__:
    sys.exit(cli())

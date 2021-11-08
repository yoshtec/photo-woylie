#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import sys
import click
from woylie.woylie import PhotoWoylie
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


def add_ignore_extensions(fn):
    for decorator in (
        click.option(
            "-e",
            "--include-extensions",
            "add_extensions",
            multiple=True,
            type=click.STRING,
            help="add_origin extensions to include",
        ),
        click.option(
            "-x",
            "--exclude-extensions",
            "exclude_extensions",
            multiple=True,
            type=click.STRING,
            help="extensions to ignore",
        ),
    ):
        fn = decorator(fn)
    return fn


def arg_base_path(fn):
    return click.argument(
        "base-path",
        nargs=1,
        type=click.Path(file_okay=False, dir_okay=True, allow_dash=False),
        required=True,
    )(fn)


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
@arg_base_path
@click.argument(
    "import-path",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, allow_dash=False),
    required=True,
)
@common_options
@add_ignore_extensions
def import_files(
    base_path,
    import_path,
    symlink=False,
    dump_exif=False,
    language=None,
    add_extensions=None,
    exclude_extensions=None,
):
    """import images and movies to your library"""
    woylie = PhotoWoylie(
        base_path=base_path,
        hardlink=not symlink,
        dump_exif=dump_exif,
        lang=language,
    )

    woylie.add_extensions(add_extensions)
    woylie.exclude_extensions(exclude_extensions)

    for path in import_path:
        woylie.import_files(path)


@cli.command()
@arg_base_path
def undo_import(
    base_path,
):
    """Undo last import and delete files from the lib"""
    woylie = PhotoWoylie(
        base_path=base_path,
    )

    woylie.undo_import()


@cli.command()
@arg_base_path
@click.argument(
    "remove-path",
    nargs=-1,
    type=click.Path(exists=True, file_okay=True, dir_okay=True, allow_dash=False),
    required=True,
)
@common_options
@add_ignore_extensions
def remove(
    base_path,
    remove_path,
    symlink=False,
    dump_exif=False,
    language=None,
    add_extensions=None,
    exclude_extensions=None,
):
    """remove files from the library"""
    woylie = PhotoWoylie(
        base_path=base_path, hardlink=not symlink, dump_exif=dump_exif, lang=language
    )

    woylie.add_extensions(add_extensions)
    woylie.exclude_extensions(exclude_extensions)

    for path in remove_path:
        woylie.remove_files(path)


@cli.command()
@arg_base_path
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
@arg_base_path
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


@cli.command()
@arg_base_path
def stats(base_path):
    """ display statistics of the library in base-path"""
    woylie = PhotoWoylie(base_path=base_path)
    woylie.stats()


@cli.command()
@arg_base_path
@click.argument(
    "file",
    nargs=-1,
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
def fileinfo(base_path, file):
    """ display information about the file"""
    woylie = PhotoWoylie(base_path=base_path)
    for f in file:
        fi = Path(f)
        if fi.exists():
            woylie.file_info(file=fi)
        else:
            click.echo(f"Could not find File: {fi}")


if "__main__" == __name__:
    sys.exit(cli())

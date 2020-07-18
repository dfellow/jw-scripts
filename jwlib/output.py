import os
from typing import List

from . import msg
from .parse import Category, Media
from .arguments import Settings

pj = os.path.join


def create_output(s: Settings, data: List[Category], stdout_uniq=False):
    """Settings for output modes

    :keyword stdout_uniq: passed to output_stdout
    """

    if s.mode == 'stdout':
        output_stdout(s, data, uniq=stdout_uniq)
    elif s.mode == 'm3u':
        output_m3u(s, data)
    elif s.mode == 'filesystem':
        clean_symlinks(s)
        output_filesystem(s, data)
    elif s.mode == 'm3ucompat':
        output_m3u(s, data, flat=True)
    elif s.mode == 'html':
        output_m3u(s, data, writer=_write_to_html, file_ending='.html')
    else:
        raise RuntimeError('invalid mode')


def output_stdout(s: Settings, data: List[Category], uniq=False):
    """Output URLs or filenames to stdout.

    :keyword uniq: If True all output is unique, but unordered
    """
    out = []
    for category in data:
        for item in category.contents:
            if isinstance(item, Media):
                if item.exists_in('.'):
                    out.append(os.path.relpath(item.filename, s.work_dir))
                else:
                    out.append(item.url)
    if uniq:
        out = set(out)

    print(*out, sep='\n')


def output_m3u(s: Settings, data: List[Category], writer=None, flat=False, file_ending='.m3u'):
    """Create a M3U playlist tree.

    :keyword writer: Function to write to files
    :keyword flat: If all playlist will be saved outside of subdir
    :keyword file_ending: Well, duh
    """
    wd = s.work_dir
    sd = s.sub_dir

    def fmt(x):
        return format_filename(x, safe=s.safe_filenames)

    if not writer:
        writer = _write_to_m3u

    for category in data:
        if flat:
            # Flat mode, all files in working dir
            output_file = pj(wd, category.key + ' - ' + fmt(category.name) + file_ending)
            source_prepend_dir = sd
        elif category.home:
            # For home/index/starting categories
            # The current file gets saved outside the subdir
            # Links point inside the subdir
            source_prepend_dir = sd
            output_file = pj(wd, fmt(category.name) + file_ending)
        else:
            # For all other categories
            # Things get saved inside the subdir
            # No need to prepend links with the subdir itself
            source_prepend_dir = ''
            output_file = pj(wd, sd, category.key + file_ending)

        is_start = True
        for item in category.contents:
            if isinstance(item, Category):
                if flat:
                    # "flat" playlists does not link to other playlists
                    continue
                name = item.name.upper()
                source = pj('.', source_prepend_dir, item.key + file_ending)
            else:
                name = item.name
                if item.exists_in(pj(wd, sd)):
                    source = pj('.', source_prepend_dir, item.filename)
                else:
                    source = item.url

            if is_start and s.quiet < 1:
                msg('writing: {}'.format(output_file))

            # First line will overwrite existing files
            writer(source, name, output_file, overwrite=is_start)
            is_start = False


def output_filesystem(s: Settings, data: List[Category]):
    """Creates a directory structure with symlinks to videos"""

    wd = s.work_dir
    sd = s.sub_dir

    def fmt(x):
        return format_filename(x, safe=s.safe_filenames)

    if s.quiet < 1:
        msg('creating directory structure')

    for category in data:

        # Create the directory
        output_dir = pj(wd, sd, category.key)
        os.makedirs(output_dir, exist_ok=True)

        # Index/starting/home categories: create link outside subdir
        if category.home:
            link = pj(wd, fmt(category.name))
            # Note: the source will be relative
            source = pj(sd, category.key)
            try:
                os.symlink(source, link)
            except FileExistsError:
                pass

        for item in category.contents:

            if isinstance(item, Category):
                d = pj(wd, sd, item.key)
                os.makedirs(d, exist_ok=True)
                source = pj('..', item.key)

                if s.include_keyname:
                    link = pj(output_dir, item.key + ' - ' + fmt(item.name))
                else:
                    link = pj(output_dir, fmt(item.name))

            else:
                if not item.exists_in(pj(wd, sd)):
                    continue

                source = pj('..', item.filename)
                ext = os.path.splitext(item.filename)[1]
                link = pj(output_dir, fmt(item.name + ext))

            try:
                os.symlink(source, link)
            except FileExistsError:
                pass


def format_filename(string, safe=False):
    """Remove unsafe characters from file names"""

    if safe:
        # NTFS/FAT forbidden characters
        string = string.replace('"', "'").replace(':', '.')
        forbidden = '<>:"|?*/\0'
    else:
        # Unix forbidden characters
        forbidden = '/\0'

    return ''.join(x for x in string if x not in forbidden)


def clean_symlinks(s: Settings):
    """Clean out broken (or all) symlinks from work dir"""

    path = pj(s.work_dir, s.sub_dir)

    if not os.path.isdir(path):
        return

    for subdir in os.listdir(path):
        subdir = pj(path, subdir)
        if not os.path.isdir(subdir):
            continue

        for file in os.listdir(subdir):
            file = pj(subdir, file)
            if not os.path.islink(file):
                continue

            source = pj(subdir, os.readlink(file))

            if s.clean_all_symlinks or not os.path.exists(source):
                if s.quiet < 1:
                    msg('removing link: ' + os.path.basename(file))
                os.remove(file)


def _truncate_file(file, string='', overwrite=False):
    """Create a file and the parent directories."""

    d = os.path.dirname(file)
    os.makedirs(d, exist_ok=True)

    try:
        if not overwrite and os.stat(file).st_size != 0:
            # Don't truncate non-empty files
            return
    except FileNotFoundError:
        pass

    with open(file, 'w', encoding='utf-8') as f:
        f.write(string)


def _write_to_m3u(source, name, file, overwrite=False):
    """Write entry to a M3U playlist file."""

    _truncate_file(file, '#EXTM3U\n', overwrite)
    with open(file, 'a', encoding='utf-8') as f:
        f.write('#EXTINF:0,' + name + '\n' + source + '\n')


def _write_to_html(source, name, file, overwrite=False):
    """Write a HTML file with a hyperlink to a media file."""

    _truncate_file(file, '<!DOCTYPE html>\n<head><meta charset="utf-8" /></head>', overwrite)
    with open(file, 'a', encoding='utf-8') as f:
        f.write('\n<a href="{0}">{1}</a><br>'.format(source, name))

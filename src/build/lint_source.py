#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import cPickle
import collections
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile

import analyze_diffs
import build_common
import open_source

_GROUP_ASM = 'Assembly'
_GROUP_CPP = 'C/C++'
_GROUP_CSS = 'CSS'
_GROUP_HTML = 'HTML'
_GROUP_JAVA = 'Java'
_GROUP_JS = 'Javascript'
_GROUP_PY = 'Python'

_ALL_EXTENSION_GROUPS = {
    '.asm': _GROUP_ASM,
    '.c': _GROUP_CPP,
    '.cc': _GROUP_CPP,
    '.cpp': _GROUP_CPP,
    '.css': _GROUP_CSS,
    '.h': _GROUP_CPP,
    '.hpp': _GROUP_CPP,
    '.html': _GROUP_HTML,
    '.java': _GROUP_JAVA,
    '.js': _GROUP_JS,
    '.py': _GROUP_PY,
    '.s': _GROUP_ASM,
}

# For the report, statistics will be totaled for all files under these
# directories.
_PATH_PREFIX_GROUPS = [
    'internal/mods/',
    'mods/',
    'mods/android/',
    'mods/android/bionic/',
    'mods/android/frameworks/',
    'mods/chromium-ppapi/',
    'src/',
]


class FileStatistics:
  def __init__(self, filename=None):
    self.filename = filename
    self.has_errors = False
    self.stats_dict = collections.defaultdict(int)

  def accumulate(self, source):
    for key, value in source.stats_dict.iteritems():
      self.stats_dict[key] += value


class Linter(object):
  _EXTENSION_GROUPS = []
  _linters = []
  _IGNORE_MODS = False

  @classmethod
  def register(cls, linter):
    assert getattr(linter, 'NAME'), '%s needs a NAME attribute' % linter
    cls._linters.append(linter)

  @classmethod
  def all_linters(cls):
    return cls._linters

  @classmethod
  def _filter_error_line(cls, line):
    return line

  @classmethod
  def _on_linter_error(cls, output):
    has_errors = False
    lines = output.splitlines()
    for line in lines:
      line = cls._filter_error_line(line)
      if line:
        has_errors = True
        logging.error(line)
    return not has_errors

  @classmethod
  def should_ignore(cls, file):
    extension_group = _ALL_EXTENSION_GROUPS.get(
        os.path.splitext(file)[1].lower())
    if cls._EXTENSION_GROUPS and extension_group not in cls._EXTENSION_GROUPS:
      return True
    elif cls._IGNORE_MODS and file.startswith('mods/'):
      return True
    return False

  @classmethod
  def process(cls, filename):
    try:
      cmd = cls._lint_cmd(filename)
      subprocess.check_output(cmd, stderr=subprocess.STDOUT)
      return True
    except OSError:
      logging.error('Unable to invoke %s', cmd[0])
      return False
    except subprocess.CalledProcessError as e:
      return cls._on_linter_error(e.output)


@Linter.register
class CppLinter(Linter):
  NAME = 'cpplint'
  _EXTENSION_GROUPS = [_GROUP_CPP]
  _IGNORE_MODS = True

  @classmethod
  def _lint_cmd(cls, filename):
    return ['third_party/tools/depot_tools/cpplint.py', '--root=src', filename]

  @classmethod
  def _filter_error_line(cls, line):
    if line.startswith('Done processing'):
      return None
    elif line.startswith('Total errors found:'):
      return None
    return line


@Linter.register
class JsLinter(Linter):
  NAME = 'gjslint'
  _EXTENSION_GROUPS = [_GROUP_JS]
  _ROOT_DIR = build_common.get_arc_root()

  @classmethod
  def _lint_cmd(cls, filename):
    # gjslint is run with the following options:
    #
    #  --unix_mode
    #      Lists the filename with each error line, which is what most linters
    #      here do.
    #
    #  --jslint_error=all
    #      Includes all the extra error checks. Some of these are debatable, but
    #      it seemed easiest to enable everything, and then disable the ones we
    #      do not find useful.
    #
    #  --disable=<error numbers>
    #      Disable specific checks by error number. The ones we disable are:
    #
    #      * 210 "Missing docs for parameter" (no @param doc comment)
    #      * 213 "Missing type in @param tag"
    #      * 217 "Missing @return JsDoc in function with non-trivial return"
    #
    #  --custom_jsdoc_tags=<tags>
    #      Indicates extra jsdoc tags that should be allowed, and not have an
    #      error generated for them. By default closure does NOT support the
    #      full set of jsdoc tags, including "@public". This is how we can use
    #      them without gjslint complaining.
    return ['src/build/gjslint', '--unix_mode', '--jslint_error=all',
            '--disable=210,213,217', '--custom_jsdoc_tags=public', filename]

  @classmethod
  def _filter_error_line(cls, line):
    if not line.startswith(cls._ROOT_DIR):
      return None
    return line[len(cls._ROOT_DIR) + 1:]


@Linter.register
class PyLinter(Linter):
  NAME = 'flake8'
  _EXTENSION_GROUPS = [_GROUP_PY]

  @classmethod
  def _lint_cmd(cls, filename):
    return ['src/build/flake8', filename]


@Linter.register
class CopyrightLinter(Linter):
  NAME = 'copyright'
  _EXTENSION_GROUPS = [_GROUP_PY, _GROUP_CPP, _GROUP_JS, _GROUP_ASM,
                       _GROUP_JAVA, _GROUP_HTML, _GROUP_CSS]

  @classmethod
  def should_ignore(cls, file):
    # TODO(crbug.com/411195): Clean up all copyrights so we can turn this on
    # everywhere.  Currently our priority is to have the open sourced
    # copyrights all be consistent.
    return not open_source.is_open_sourced(file)

  @classmethod
  def _lint_cmd(cls, filename):
    return ['src/build/check_copyright.py', filename]


@Linter.register
class UpstreamLinter(Linter):
  NAME = 'upstreamlint'

  @classmethod
  def should_ignore(cls, file):
    # mods/upstream directory is not yet included in open source so we cannot
    # run this linter.
    if open_source.is_open_source_repo():
      return True
    return not file.startswith(analyze_diffs.UPSTREAM_BASE_PATH + os.path.sep)

  @classmethod
  def process(cls, filename):
    description_line_count = 0
    vars = {}
    with open(filename) as f:
      lines = f.read().splitlines()
    for line in lines:
      line = line.strip()
      pos = line.find('=')
      if pos != -1:
        vars[line[:pos].strip()] = line[pos + 1:].strip()
      elif line and not vars:
        description_line_count += 1
    if 'ARC_COMMIT' in vars and vars['ARC_COMMIT'] == '':
      logging.error('Upstream file has empty commit info: ' + filename)
      return False
    if 'UPSTREAM' not in vars:
      logging.error('Upstream file has no upstream info: ' + filename)
      return False
    if description_line_count == 0 and not vars['UPSTREAM']:
      logging.error('Upstream file has no upstream URL and no description: ' +
                    filename)
      return False
    return True


@Linter.register
class LicenseLinter(Linter):
  NAME = 'licenselint'

  @classmethod
  def should_ignore(cls, file):
    basename = os.path.basename(file)
    return not basename == 'MODULE_LICENSE_TODO'

  @classmethod
  def process(cls, filename):
    with open(filename) as f:
      lines = f.read().splitlines()
    if not lines or not lines[0].startswith('crbug.com/'):
      logging.error('MODULE_LICENSE_TODO must contain a crbug.com link for '
                    'resolving the todo: ' + filename)
      return False
    return True


class DiffLinter(object):
  NAME = 'analyze_diffs'
  _DIFF_FILES = 'Files'
  _DIFF_NEW = 'New files'
  _DIFF_NEW_LINES = 'New lines'
  _DIFF_PATCHED = 'Patched files'
  _DIFF_PATCHED_ADD = 'Patched lines added'
  _DIFF_PATCHED_DEL = 'Patched lines removed'

  @classmethod
  def _invoke_analyze_diffs(cls, input_filename, output_filename):
    cmd = ['src/build/analyze_diffs.py', input_filename, output_filename]
    try:
      subprocess.check_call(cmd, stderr=subprocess.STDOUT)
      return True
    except OSError:
      logging.error('Unable to invoke %s', cmd[0])
      return False
    except subprocess.CalledProcessError as e:
      logging.error(e.output)
      return False

  @classmethod
  def _accumulate_diff_stats(cls, file_statistics, diff_stats):
    added = diff_stats['added_lines']
    removed = diff_stats['removed_lines']

    file_statistics[DiffLinter._DIFF_FILES] = 1
    if diff_stats['tracking_path'] is None:
      assert removed == 0
      file_statistics[DiffLinter._DIFF_NEW] = 1
      file_statistics[DiffLinter._DIFF_NEW_LINES] = added
    else:
      file_statistics[DiffLinter._DIFF_PATCHED] = 1
      file_statistics[DiffLinter._DIFF_PATCHED_ADD] = added
      file_statistics[DiffLinter._DIFF_PATCHED_DEL] = removed

  @classmethod
  def process(cls, filename, file_statistics):
    tmpdir = tempfile.mkdtemp(dir='out')
    try:
      temp_diff_stats_output = os.path.join(tmpdir, 'diff.out')

      if not cls._invoke_analyze_diffs(filename, temp_diff_stats_output):
        return False

      with open(temp_diff_stats_output) as f:
        cls._accumulate_diff_stats(file_statistics.stats_dict, cPickle.load(f))
      return True
    finally:
      shutil.rmtree(tmpdir)


def _lint_files(files, all_file_statistics, ignore_rules, ignore_file):
  linters = Linter.all_linters()
  overall_success = True

  for f in ignore_rules.iterkeys():
    # Make sure everything exists in the non-open source repo.  (We do
    # not run this check on the open source repo since not all files are
    # currently open sourced.)
    if not open_source.is_open_source_repo() and not os.path.exists(f):
      overall_success = False
      logging.error('%s in %s does not exist' % (f, ignore_file))
  if not overall_success:
    return False

  for filename in files:
    local_success = True
    if not analyze_diffs.is_tracking_an_upstream_file(filename):
      for linter in linters:
        if linter.NAME in ignore_rules.get(filename, []):
          continue
        if linter.should_ignore(filename):
          continue
        logging.info('%- 10s: %s', linter.__name__, filename)
        local_success &= linter.process(filename)

    file_statistics = FileStatistics(filename)
    if DiffLinter.NAME in ignore_rules.get(filename, []):
      continue
    local_success &= DiffLinter.process(filename, file_statistics)
    all_file_statistics.append(file_statistics)
    if not local_success:
      logging.error('%s: has errors\n', filename)
    overall_success &= local_success
  return overall_success


def _walk(path):
  filelist = []
  for (root, dirs, files) in os.walk(path):
    for f in files:
      filelist.append(os.path.join(root, f))
  return filelist


def _should_ignore(filename):
  extension = os.path.splitext(filename)[1]
  basename = os.path.basename(filename)
  if os.path.isdir(filename):
    return True
  if os.path.islink(filename):
    return True
  if build_common.is_common_editor_tmp_file(basename):
    return True
  if extension == '.pyc':
    return True
  if filename.startswith('src/build/tests/analyze_diffs/'):
    return True
  if filename.startswith('docs/'):
    return True
  return False


def _filter_files(files):
  if not files:
    files = []
    files.extend(_walk('canned'))
    files.extend(_walk('mods'))
    if os.path.isdir('internal/mods'):
      files.extend(_walk('internal/mods'))
    files.extend(_walk('src'))
    # TODO(crbug.com/374475): This subtree should be removed from linting.
    # There should be no ARC MOD sections in third_party, but there are in
    # some NDK directories.
    files.extend(_walk('third_party/examples'))

  files = [x for x in files if not _should_ignore(x)]
  return files


def get_all_files_to_check():
  return _filter_files(None)


def read_ignore_rules(ignore_file_path):
  """Reads the mapping of paths to lint checks to ignore from a file.

  The ignore file is expected to define a simple mapping between file paths
  and the lint rules to ignore (the <List Class>.NAME attributes). Hash
  characters ('#') can be used for comments, as well as blank lines for
  readability.

  A typical # filter in the file should look like:

    # Exclude src/xyzzy.cpp from the checks "gnusto" and "rezrov"
    src/xyzzy.cpp: gnusto rezrov"""
  if not ignore_file_path:
    return {}
  return json.loads('\n'.join(
      build_common.read_metadata_file(ignore_file_path)))


def process(files, ignore_file=None, output_file=None):
  ignore_rules = read_ignore_rules(ignore_file)
  files = _filter_files(files)
  results = []
  success = _lint_files(files, results, ignore_rules, ignore_file)
  if not success:
    return 1

  if output_file:
    with open(output_file, 'wb') as f:
      cPickle.dump(results, f)
  return 0


def _all_file_statistics(files):
  for filename in files:
    with open(filename) as f:
      for file_statistics in cPickle.load(f):
        yield file_statistics


def _all_groups_for_filename(filename):
  # Output groups based on what the path starts with.
  for prefix in _PATH_PREFIX_GROUPS:
    if filename.startswith(prefix):
      yield 'Under:' + prefix + '*'


def _report_stats_for_group(group_name, stats, output_file):
  output_file.write(group_name + '\n')
  for key in sorted(stats.stats_dict.keys()):
    output_file.write('    {0:<30} {1:10,d}\n'.format(
        key, stats.stats_dict[key]))
  output_file.write('-' * 60 + '\n')


def _report_stats(top_stats, grouped_stats, output_file):
  for group_name in sorted(grouped_stats.keys()):
    _report_stats_for_group(group_name, grouped_stats[group_name], output_file)
  _report_stats_for_group('Project Total', top_stats, output_file)


def merge_results(files, output_file):
  top_stats = FileStatistics()
  grouped_stats = collections.defaultdict(FileStatistics)

  for file_statistics in _all_file_statistics(files):
    filename = file_statistics.filename
    top_stats.accumulate(file_statistics)
    for group in _all_groups_for_filename(filename):
      grouped_stats[group].accumulate(file_statistics)

  _report_stats(top_stats, grouped_stats, sys.stdout)
  with open(output_file, 'w') as output_file:
    _report_stats(top_stats, grouped_stats, output_file)


class ResponseFileArgumentParser(argparse.ArgumentParser):
  def __init__(self):
    super(ResponseFileArgumentParser, self).__init__(fromfile_prefix_chars='@')

  def convert_arg_line_to_args(self, arg_line):
    """Separate arguments by spaces instead of the default by newline.

    This matches how Ninja response files are generated.  This prevents us
    from adding source files with spaces in their paths."""
    for arg in arg_line.split():
        if not arg.strip():
            continue
        yield arg


def main():
  parser = ResponseFileArgumentParser()
  parser.add_argument('files', nargs='*', help='The list of files to lint.  If '
                      'no files provided, will lint all files.')
  parser.add_argument('--ignore', '-i', dest='ignore_file', help='A text file '
                      'containting list of files to ignore.')
  parser.add_argument('--merge', action='store_true', help='Merge results.')
  parser.add_argument('--output', '-o', help='Output file for storing results.')
  parser.add_argument('--verbose', '-v', action='store_true', help='Prints '
                      'additional output.')
  args = parser.parse_args()

  log_level = logging.DEBUG if args.verbose else logging.WARNING
  logging.basicConfig(format='%(message)s', level=log_level)

  if args.merge:
    return merge_results(args.files, args.output)
  else:
    return process(args.files, args.ignore_file, args.output)

if __name__ == '__main__':
  sys.exit(main())

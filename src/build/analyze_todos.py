#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import collections
import datetime
import os
import re
import sys

import analyze_diffs
from util import color

_DEFAULT_PATHS_TO_SCAN = ['src/', 'mods/', 'canned/scripts/can_android.py',
                          'canned/scripts']

_DESCRIPTION = """
Analyzes the source code for TODOs, reporting some useful statistics, and
warning about old or malformed TODOs.



We expect TODOs to match a fairly particular pattern, which looks like:

  TODO(<tracking details>): <Some text>

Note that the text may wrap to the next line, but we do not attempt to read
the entire text body here. (though maybe we should for better content
matching?)

The tracking details for a TODO should be one of:
  1) crbug.com/<bug-number>
     This is for issues that represent needed work.

     Example:

       TODO(crbug.com/12345): This needs to be fixed for a feature release.

  2) A list of owners, separated by commas or forward-slashes.
     These are for tasks that it would be nice to do, but there is no hard
     requirement for.

       TODO(leonardofquirm): Need to use more very fast coffee here.
       TODO(penn/teller): Reveal the ball trick here later.

  3) [EXPERIMENTAL] A date, like 2013/12/31
     This is for tasks that it would be nice to do. The date is when the task
     was noted in the code, and it is expected that these will be done in short
     order (at most a few weeks).

       TODO(2013/09/19): Arrr! This here code smells worse that a scurvy-
       ridden bilge rat. It needs the taste of a nice sharp cutlass.

"""

_EXAMPLE_USAGE = """
Examples:

  # Default arguments -- Print out all the TODOs, calling out ones that are
  # too-old or in a bad format.
  %(prog)s
  # Show a summary of counts, including stats by owner.
  %(prog)s --summary --by-owner
  # Show all TODOs mentioning bug 12345
  %(prog)s -q 12345
  # Show all TODOs mentioning 'Remove'
  %(prog)s -q Remove
  # Show all TODOs with a date before December 31, 2013.
  %(prog)s -q 2013/12/31"""


_EXPECTED_TODO_PATTERN = re.compile(r'TODO\(([^)]+)\): \S+')
_FILE_TRACK_PATTERN = re.compile(re.escape(analyze_diffs.FILE_TRACK_TAG) +
                                 r' "([^\"]+)"')
_OTHER_TODO_PATTERN = re.compile(r'TO[^ ]?DO', re.IGNORECASE)


_TODO_DETAIL_BUG = re.compile(r'crbug\.com/(\d+)$')
_TODO_DETAIL_DATE = re.compile(r'\d\d\d\d/\d\d/\d\d$')
_TODO_DETAIL_OWNERS_LIST_SPLIT = re.compile(r'[,/]')
_TODO_DETAIL_OWNERS = re.compile(r'\w+([,/]\w+)*$')


_MAX_TODO_AGE = datetime.timedelta(days=30)


class Analyzer(object):
  def __init__(self, child):
    self._child = child
    self._child.set_root(self)

  def parse(self, file_path):
    self.current_path = file_path
    self._stop = False
    with open(file_path, 'r') as source_file:
      for index, line in enumerate(source_file):
        self.current_line = index + 1
        self._child.handle_line(line)
        if self._stop:
          return

  def stop_parse(self):
    self._stop = True


class AnalyzeFileLevelMetadata(object):
  def __init__(self):
    self.file_track_path = None
    self.has_file_ignore_tag = False
    self.has_file_track_tag = False
    self._root = None

  def set_root(self, root):
    self._root = root

  def handle_line(self, line):
    if analyze_diffs.FILE_IGNORE_TAG in line:
      self.has_file_ignore_tag = True
      self._root.stop_parse()

    match = _FILE_TRACK_PATTERN.search(line)
    if match:
      tracking_path = match.group(1)
      self.has_file_track_tag = True
      self.file_track_path = tracking_path
      self._root.stop_parse()


class AnalyzeCodeInMODRegions(object):
  def __init__(self, child):
    self._root = None
    self._child = child
    self._in_mod_region = False

  def set_root(self, root):
    self._root = root
    self._child.set_root(root)

  def handle_line(self, line):
    if analyze_diffs.REGION_START_TAG in line:
      assert not self._in_mod_region
      self._in_mod_region = True
    elif analyze_diffs.REGION_END_TAG in line:
      assert self._in_mod_region
      self._in_mod_region = False
    elif self._in_mod_region:
      self._child.handle_line(line)


def as_date(value):
  return datetime.datetime.strptime(value, '%Y/%m/%d')


class Todo(object):
  def __init__(self, source_path, source_line, raw_text, bug=None,
               created_timestamp=None, owners=None, is_nonstandard=False):
    self.source_path = source_path
    self.source_line = source_line
    self.raw_text = raw_text
    self.bug = bug
    self.created_timestamp = created_timestamp
    self.owners = owners
    self.is_nonstandard = is_nonstandard

  def __repr__(self):
    return "%s %s" % (self.__class__.__name__, self.__dict__)


class AnalyzeTodos(object):
  def __init__(self, reporter):
    self._reporter = reporter
    self._root = None

  def set_root(self, root):
    self._root = root

  def _extract_detail_metadata(self, todo_metadata, details):
    match = _TODO_DETAIL_BUG.match(details)
    if match:
      todo_metadata['bug'] = match.group(1)
    elif _TODO_DETAIL_DATE.match(details):
      try:
        todo_metadata['created_timestamp'] = as_date(details)
      except ValueError:
        todo_metadata['is_nonstandard'] = True
    elif _TODO_DETAIL_OWNERS.match(details):
      owners = _TODO_DETAIL_OWNERS_LIST_SPLIT.split(details)
      if owners[0] != 'crbug':  # Watch out for malformed crbug urls
        todo_metadata['owners'] = owners

  def handle_line(self, line):
    todo_metadata = {}

    match = _EXPECTED_TODO_PATTERN.search(line)
    if match:
      details = match.group(1)
      self._extract_detail_metadata(todo_metadata, details)
      if not todo_metadata:
        todo_metadata['is_nonstandard'] = True
    elif _OTHER_TODO_PATTERN.search(line):
      todo_metadata['is_nonstandard'] = True

    if todo_metadata:
      self._reporter.report_todo(
          Todo(self._root.current_path, self._root.current_line, line,
               **todo_metadata))


def _analyze_file(path, reporter):
  if os.path.abspath(path) == os.path.abspath(__file__):
    return

  tracking_path = analyze_diffs.compute_default_tracking_path(path)
  metadata = AnalyzeFileLevelMetadata()
  Analyzer(metadata).parse(path)

  if metadata.has_file_ignore_tag:
    reporter.report_skipping(path)
    return

  if metadata.has_file_track_tag:
    tracking_path = metadata.file_track_path

  has_tracked_file = tracking_path and os.path.exists(tracking_path)

  analyzer = AnalyzeTodos(reporter)
  if has_tracked_file:
    analyzer = AnalyzeCodeInMODRegions(analyzer)
  Analyzer(analyzer).parse(path)


def _all_source_code_files(paths):
  for base_path in paths:
    if not os.path.isdir(base_path):
      yield base_path
    else:
      for root, dirs, files in os.walk(base_path, followlinks=True):
        for name in files:
          ext = os.path.splitext(name)[1]
          if ext not in ['.pyc', '.apk', '.so', '.jar']:
            yield os.path.join(root, name)


class TodoReporter(object):
  def __init__(self, filter=None):
    self._bugs = []
    self._count_by_bug = collections.defaultdict(int)
    self._count_by_owner = collections.defaultdict(int)
    self._too_old = []
    self._timestamped = []
    self._filter = filter
    self._matched_count = 0
    self._nonstandard = []
    self._too_old_timestamp = datetime.datetime.now() - _MAX_TODO_AGE
    self._owned = []
    self._skipped_paths = []
    self._todos = []

  def _accumulate_counts(self, todo):
    if todo.bug:
      self._count_by_bug[todo.bug] += 1

    if todo.owners:
      for owner in todo.owners:
        self._count_by_owner[owner] += 1

  def report_todo(self, todo):
    self._todos.append(todo)
    self._accumulate_counts(todo)

    if self._filter.match(todo):
      self._matched_count += 1
      category = None
      if todo.created_timestamp:
        if todo.created_timestamp < self._too_old_timestamp:
          category = self._too_old
        else:
          category = self._timestamped
      elif todo.bug:
        category = self._bugs
      elif todo.owners:
        category = self._owned
      elif todo.is_nonstandard:
        category = self._nonstandard
      assert category is not None, 'No category for todo: %s' % todo
      category.append(todo)

  def report_skipping(self, path):
    self._skipped_paths.append(path)

  def puts(self, text, color=None):
    color.write_ansi_escape(sys.stdout, color, text)

  def _print_todo(self, todo):
    self.puts('%s(%d): ' % (todo.source_path, todo.source_line),
              color=color.MAGENTA)
    if todo.is_nonstandard:
      self.puts('Nonstandard TODO: ', color=color.RED)
    elif (todo.created_timestamp and
          todo.created_timestamp < self._too_old_timestamp):
      self.puts('[OLD]: ', color=color.RED)
    self.puts('%s\n' % todo.raw_text.strip(), color=color.GRAY)

  def _print_todo_list_source_listing(self, todos):
    for todo in todos:
      self._print_todo(todo)

  def _print_count_by_dict(self, count_by_dict):
    output = [(count, key) for key, count in count_by_dict.iteritems()]
    for count, key in sorted(output):
      self.puts("%s %s\n" % (count, key))

  def print_skipped_paths(self):
    for path in self._skipped_paths:
      self.puts('Skipped %s\n' % path, color=color.YELLOW)

  def print_nonstandard_todos(self):
    if self._nonstandard:
      self.puts('Nonstandard TODOs\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._nonstandard)
      self.puts('\n')

  def print_time_stamped_todos(self):
    if self._timestamped:
      self.puts('Time-stamped TODOs\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._timestamped)
      self.puts('\n')

  def print_too_old_todos(self):
    if self._too_old:
      self.puts('Too-old TODOs\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._too_old)
      self.puts('\n')

  def print_owned_todos(self):
    if self._owned:
      self.puts('Owned TODOs\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._owned)
      self.puts('\n')

  def print_bug_todos(self):
    if self._bugs:
      self.puts('Bug TODOs\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._bugs)
      self.puts('\n')

  def print_all_todos(self):
    if self._todos:
      self.puts('TODOs:\n', color=color.GREEN)
      self._print_todo_list_source_listing(self._todos)
      self.puts('\n')

  def print_count_by_bug(self):
    if self._count_by_bug:
      self.puts('Count by bug:\n', color=color.GREEN)
      self._print_count_by_dict(self._count_by_bug)
      self.puts('\n')

  def print_count_by_owner(self):
    if self._count_by_owner:
      self.puts('Count by owner:\n', color=color.GREEN)
      self._print_count_by_dict(self._count_by_owner)
      self.puts('\n')

  def print_summary(self):
    self.puts('%d TODOs observed.\n' % len(self._todos), color=color.MAGENTA)
    self.puts('%d TODOs matched.\n' % self._matched_count, color=color.MAGENTA)
    if self._nonstandard:
      self.puts('  %d are nonstandard.\n' % len(self._nonstandard),
                color=color.RED)
    if self._too_old:
      self.puts('  %d have old timestamps.\n' % len(self._too_old),
                color=color.RED)
    self.puts('\n')


class QueryMatchAny(object):
  def match(self, todo):
    return True


class QueryMatchText(object):
  def __init__(self, text):
    self._match = re.compile(text, re.IGNORECASE)

  def match(self, todo):
    return self._match.search(todo.raw_text) is not None


class QueryCreatedBefore(object):
  def __init__(self, timestamp):
    self._timestamp = timestamp

  def match(self, todo):
    return todo.created_timestamp and todo.created_timestamp < self._timestamp


class StoreQueryAction(argparse.Action):
  def __call__(self, parser, namespace, value, option_string=None):
    if _TODO_DETAIL_DATE.match(value):
      setattr(namespace, self.dest, QueryCreatedBefore(as_date(value)))
    else:
      setattr(namespace, self.dest, QueryMatchText(value))


def main():
  parser = argparse.ArgumentParser(
      description=_DESCRIPTION,
      epilog=_EXAMPLE_USAGE,
      formatter_class=argparse.RawTextHelpFormatter)
  parser.add_argument(
      '--by-owner', action='store_true',
      help='Additionally show the counts by owner.')
  parser.add_argument(
      '--by-bug', action='store_true',
      help='Additionally show the counts by bug.')
  parser.add_argument(
      '--email', action='store_true',
      help=('Top-down order the output for an email (summary first rather than '
            'last).'))
  parser.add_argument(
      '--summary', action='store_true',
      help='Just show the count of TODOs found.')
  parser.add_argument(
      '--malformed', action='store_true', dest='malformed',
      help='Show only non-standard TODOs.')
  parser.add_argument(
      '-q', dest='query', action=StoreQueryAction, default=QueryMatchAny(),
      help=('What to match when finding TODOs, such as a bug number,'
            'a bit of text, or a filter date'))

  args = parser.parse_args()

  reporter = TodoReporter(filter=args.query)
  for file_path in _all_source_code_files(_DEFAULT_PATHS_TO_SCAN):
    _analyze_file(file_path, reporter)

  output_calls = []

  if not args.summary:
    if not args.malformed:
      output_calls.append(reporter.print_skipped_paths)

      output_calls.append(reporter.print_bug_todos)
      output_calls.append(reporter.print_owned_todos)
      output_calls.append(reporter.print_time_stamped_todos)

    output_calls.append(reporter.print_nonstandard_todos)
    output_calls.append(reporter.print_too_old_todos)

  if args.by_bug:
    output_calls.append(reporter.print_count_by_bug)

  if args.by_owner:
    output_calls.append(reporter.print_count_by_owner)

  output_calls.append(reporter.print_summary)

  if args.email:
    output_calls.reverse()

  for call in output_calls:
    call()

if __name__ == '__main__':
  sys.exit(main())

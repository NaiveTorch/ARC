#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import logging
import re
import subprocess
import sys
import traceback


_BUG_PREFIX = 'BUG='
_PERF_PREFIX = 'PERF='
_TEST_PREFIX = 'TEST='
_PREFIXES = [_TEST_PREFIX, _PERF_PREFIX, _BUG_PREFIX]

_CHANGED_FILE_RE = re.compile(r'.*?:\s+(.*)')
_CRBUG_URL_RE = re.compile(r'crbug.com/(\d{6,})')


def _append_prefixes(existing_prefixes, output_lines):
  """Appends missing prefix lines."""
  if len(existing_prefixes) != 3:
    # Remove trailing line breaks.
    while output_lines and output_lines[-1] == '\n':
      output_lines.pop()

    if not existing_prefixes:
      # Add a blank line before TEST/PERF/BUG lines if none present.
      output_lines.append('\n')
    for prefix in _PREFIXES:
      if not prefix in existing_prefixes:
        output_lines.append(prefix + '\n')
    # Add a space after what we added.
    output_lines.append('\n')


def add_mandatory_lines(lines):
  """Adds mandatory lines such as TEST= to the commit message."""
  output_lines = []
  existing_prefixes = set()
  while lines:
    line = lines.pop(0)
    for prefix in _PREFIXES:
      if line.startswith(prefix):
        existing_prefixes.add(prefix)
    if line.startswith('#') or line.startswith('Change-Id:'):
      lines = [line] + lines
      break
    output_lines.append(line)

  _append_prefixes(existing_prefixes, output_lines)
  return output_lines + lines


def get_changed_files(lines):
  changed_files = []
  for i in xrange(len(lines)):
    line = lines[i]
    # The comment lines contain something like:
    #
    # # Changes to be committed:
    # #       new file: path/to/added_file
    # #       modified: path/to/modified_file
    # #
    # # Untracked files:
    # # ...
    if line.startswith('# Changes to be committed'):
      for line in lines[i + 1:]:
        # We do not handle file rename.
        if 'renamed' in line:
          continue
        matched = _CHANGED_FILE_RE.match(line)
        if not matched:
          break
        filename = matched.group(1)
        # MOD for Chromium code may contain non-ARC bugs.
        if filename.startswith('mods/') and 'chromium' in filename:
          continue
        changed_files.append(filename)
      break
  return changed_files


def get_bug_ids_from_diffs(diffs):
  """Gets removed bug IDs from diffs.

  When a bug is removed but also added into another line, this
  function does not return it.
  """
  added_bug_ids = set()
  removed_bug_ids = set()
  for diff in diffs:
    for diff_line in diff.splitlines():
      bug_ids = set(_CRBUG_URL_RE.findall(diff_line))
      if diff_line.startswith('+'):
        added_bug_ids.update(bug_ids)
      elif diff_line.startswith('-'):
        removed_bug_ids.update(bug_ids)
  return removed_bug_ids - added_bug_ids


def update_bug_line(lines, bug_ids):
  """Updates BUG= line.

  When no bug_ids is specified, this function does nothing. When
  bug_ids will be specified, add them into the existing BUG= line. In
  this case, this function removes existing bug description which
  claims there is no existing bug (e.g., N/A or None).
  """
  if not bug_ids:
    return lines

  def _reject_empty_bug(bug_id):
    if not bug_id or re.match(r'(n/a|none)', bug_id, flags=re.IGNORECASE):
      return False
    return True

  for index, line in enumerate(lines):
    if line.startswith(_BUG_PREFIX):
      orig_bug_ids = re.split(r',\s*', line[len(_BUG_PREFIX):].strip())
      orig_bug_ids = filter(_reject_empty_bug, orig_bug_ids)
      bug_ids.update(set(orig_bug_ids))
      orig_bug_ids_str = ', '.join(sorted(orig_bug_ids))
      bug_ids_str = ', '.join(sorted(bug_ids))
      if orig_bug_ids_str != bug_ids_str:
        if orig_bug_ids_str == '':
          lines[index] = _BUG_PREFIX + '%s\n' % bug_ids_str
        else:
          lines[index] = _BUG_PREFIX + '%s\n' % orig_bug_ids_str
          lines.insert(index + 1, '# Suggestion: %s%s\n' % (
              _BUG_PREFIX, bug_ids_str))
      return lines
  logging.error('No BUG= line')
  return lines


def _detect_and_update_bug_id(lines):
  """Updates BUG= line based on the change."""
  optional_args = sys.argv[2:]
  # Decide the base git commit from the type of this commit.
  if not optional_args:
    # A normal commit without --amend.
    base_git_commit = 'HEAD'
  elif optional_args == ['commit', 'HEAD']:
    # An --amend commit.
    base_git_commit = 'HEAD~'
  else:
    # It seems there are some other cases such as merge commit
    # but we do not support them as we do not use them often.
    return

  # Find all changed files from the comment lines. Note that we cannot
  # do just "git diff HEAD" because its result will contain the diff
  # of unstaged files.
  changed_files = get_changed_files(lines)

  diffs = []
  for changed_file in changed_files:
    # This contains the diff of unstaged changes. We can not
    # distinguish whether the git commit was with -a or not, so we
    # cannot decide whether we should use --staged or not.
    # TODO(crbug.com/374776): When you were in a sub-directory of
    # arc, changed_file may contain "../". As git changes the
    # current directory to the top directory before it runs this
    # script, "../" may be invalid and this "git diff" may fail.
    # Use "git status" to get the list of changed files.
    diffs.append(subprocess.check_output(['git', 'diff', base_git_commit,
                                          '--', changed_file]))

  bug_ids = get_bug_ids_from_diffs(diffs)
  lines = update_bug_line(lines, bug_ids)


if __name__ == '__main__':
  commit_file = sys.argv[1]
  with open(commit_file) as f:
    lines = f.readlines()

  lines = add_mandatory_lines(lines)
  # This function is not trivial and may raise an exception. As bug ID
  # detection is an optional feature, the failure in this step must
  # not prevent us from creating a commit.
  try:
    _detect_and_update_bug_id(lines)
  except Exception, e:
    sys.stderr.write('*** An exception is raised, bug IDs will not be '
                     'filled automatically ***\n')
    traceback.print_exc()

  with open(commit_file, 'w') as f:
    f.write(''.join(lines))

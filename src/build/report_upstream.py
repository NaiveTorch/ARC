#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# The tool to produce reports on upstreamable changes.

import argparse
import collections
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import urlparse

import analyze_diffs

from xml.sax.saxutils import escape


_GERRIT_SERVERS = ('android-review.googlesource.com')

_CSV_COL_NAMES = ['Change',
                  'Summary',
                  'Mod/Line Count',
                  'ARC Author',
                  'ARC Hash',
                  'ARC Summary',
                  'Upstream Status',
                  'Upstream Author',
                  'Upstream Url',
                  'Upstream Summary',
                  'Upstream Updated']
_CSV_IDX_ARC_HASH = 4
_CSV_IDX_UPSTREAM_URL = 8

_SECTION_EMPTY = 'Empty'
_SECTION_MERGED = 'Merged'
_SECTION_NOT_STARTED = 'Not Started'
_SECTION_OPEN = 'Open'
_SECTION_UNKNOWN = 'Unknown'

# The sections ordered the way they should appear in the report.
_SECTION_LIST = [_SECTION_EMPTY,
                 _SECTION_NOT_STARTED,
                 _SECTION_OPEN,
                 _SECTION_UNKNOWN,
                 _SECTION_MERGED]


_STATUS_EMPTY = 'NoMods'
_STATUS_NOT_SENT = 'NotSent'

_STATUS_SECTION_MAP = {'MERGED': _SECTION_MERGED,
                       'NEW': _SECTION_OPEN,
                       'DISLIKED': _SECTION_OPEN,
                       'BROKEN': _SECTION_OPEN,
                       _STATUS_NOT_SENT: _SECTION_NOT_STARTED}


def _clean_summary(s):
  # Many summary lines end with '.' which does not look good on reports.
  if s.endswith('.'):
    s = s[:-1]
  return s


def _clean_author(s):
  """ Converts 'someone@google.com' or '@chromium.org' into 'someone@' """
  if s.endswith('@google.com'):
    s = s[:-10]
  elif s.endswith('@chromium.org'):
    s = s[:-12]
  return s


class ChangeDescription(object):

  def __init__(self, description_file):
    self._description_file = description_file
    self._base_name = os.path.basename(description_file)
    self._description_lines = []
    self._description_summary = ''
    self._mod_stats = analyze_diffs.ModStats()
    self._arc_commits = []
    self._arc_authors = []
    self._arc_summaries = []
    self._upstream_url = ''
    self._upstream_author = ''
    self._upstream_summary = ''
    self._upstream_status = ''
    self._upstream_updated = ''

    self._parse_description()
    self._query_arc_info()
    self._query_upstream_info()

  def _parse_description(self):
    vars = collections.defaultdict(list)
    var_matcher = re.compile('^([A-Z_]+)=(.*)$')
    with open(self._description_file) as f:
      lines = f.read().splitlines()
    for line in lines:
      line = line.strip()
      var_matches = var_matcher.search(line)
      if var_matches:
        vars[var_matches.group(1)].append(var_matches.group(2).strip())
      elif line and not vars:
        self._description_lines.append(line)
    if self._description_lines:
      self._description_summary = _clean_summary(
          self._description_lines[0])
    self._arc_commits = [commit for commit in vars['ARC_COMMIT'] if commit]
    upstream_urls = vars['UPSTREAM']
    if upstream_urls:
      self._upstream_url = upstream_urls[0]
    if self._upstream_url.endswith('/'):
      self._upstream_url = self._upstream_url[:-1]

  def _query_arc_info(self):
    if self._arc_commits:
      for commit in self._arc_commits:
        self._read_arc_info_from_log(
            ['git', 'show', '-s', '--format=%H %ae %s', commit])
    else:
      self._read_arc_info_from_log(
          ['git', 'log', '--reverse', '--format=%H %ae %s',
           self._description_file])

  def _read_arc_info_from_log(self, command):
    try:
      with tempfile.TemporaryFile() as file:
        subprocess.check_call(command, stdout=file)
        file.seek(0)
        git_log_lines = file.readlines()
    except subprocess.CalledProcessError as e:
      print 'Error invoking git command: ' + str(e)
      git_log_lines = None

    if not git_log_lines:
      print 'Unable to query git log for ' + self._description_file
      self._arc_authors.append('invalid-hash')
      return

    commit, author, summary = git_log_lines[0].strip().split(' ', 2)
    if commit not in self._arc_commits:
      self._arc_commits.append(commit)
    self._arc_authors.append(_clean_author(author))
    self._arc_summaries.append(_clean_summary(summary))

  def _query_upstream_info(self):
    if not self._upstream_url:
      self._upstream_status = _STATUS_NOT_SENT
      return
    url = urlparse.urlparse(self._upstream_url)
    if url.netloc in _GERRIT_SERVERS:
      self._query_gerrit_info(url)

  def _query_gerrit_info(self, parsed_url):
    path = parsed_url.path + '#' + parsed_url.fragment
    matches = re.search(r'.*/(\d+).*', path)
    if not matches:
      print 'No review id in upstream URL for ' + self._description_file
      return
    review_id = matches.group(1)
    with tempfile.NamedTemporaryFile() as f:
      subprocess.check_call(
          ['wget', '--quiet', '-O', f.name, 'http://' + parsed_url.netloc +
           '/changes/' + review_id + '/detail'])
      f.seek(0)
      change_info_str = f.read()
    if change_info_str.startswith(')]}\'\n'):
      change_info_str = change_info_str[5:]
    if not change_info_str:
      print 'Unable to query upstream for ' + self._description_file
      return
    change_info = json.loads(change_info_str)
    self._upstream_summary = _clean_summary(change_info['subject'])
    self._upstream_author = _clean_author(change_info['owner']['email'])
    self._upstream_updated = change_info['updated'].split(' ')[0]
    self._upstream_status = self._get_upstream_status(change_info)

  def _get_upstream_status(self, change_info):
    if 'labels' not in change_info:
      return change_info['status']
    if ('Verified' in change_info['labels'] and
        'rejected' in change_info['labels']['Verified']):
      return 'BROKEN'
    if ('Code-Review' in change_info['labels'] and
        'disliked' in change_info['labels']['Code-Review']):
      return 'DISLIKED'
    return change_info['status']

  def get_section(self):
    if self._mod_stats.mod_count == 0:
      return _SECTION_EMPTY
    return _STATUS_SECTION_MAP.get(self._upstream_status, _SECTION_UNKNOWN)

  def _get_output_vars(self):
    # The order matches _CSV_COL_NAMES.
    return [self._base_name,
            self._description_summary,
            '%s / %s' % (self._mod_stats.mod_count,
                         self._mod_stats.line_count),
            ' '.join(self._arc_authors),
            self._arc_commits,
            '. '.join(self._arc_summaries),
            self._upstream_status,
            self._upstream_author,
            self._upstream_url,
            self._upstream_summary,
            self._upstream_updated]

  @staticmethod
  def print_csv(section_changes):
    csv_writer = csv.writer(sys.stdout)
    csv_writer.writerow(_CSV_COL_NAMES)
    for section in _SECTION_LIST:
      for change in section_changes[section]:
        csv_writer.writerow(change._get_output_vars())

  @staticmethod
  def print_html(section_changes):
    header_str = '<tr>'
    for name in _CSV_COL_NAMES:
      header_str += '<th>' + escape(name) + '</th>'
    header_str += '</tr>'

    print '<html><body>'
    for section in _SECTION_LIST:
      changes = section_changes[section]
      if not changes:
        continue
      print '<br/>%s (%d)<br/>' % (section, len(changes))
      print '<table border="1">'
      print header_str
      for change in changes:
        change.print_html_line()
      print '</table>'
    print '</body></html>'

  def print_html_line(self):
    output = ['<tr>']
    idx = 0
    for value in self._get_output_vars():
      output.append('<td>')
      if idx == _CSV_IDX_ARC_HASH:
        for hash in value:
          output.append((
              '<a href="https://chrome-internal-review.googlesource.com/#q,'
              '%s,n,z">%s</a> ') % (hash, hash))
      elif idx == _CSV_IDX_UPSTREAM_URL:
        output.append('<a href="%s">%s</a>' % (value, escape(value)))
      else:
        output.append(str(escape(value)))
      output.append('</td>')
      idx += 1
    output.append('</tr>')
    print ''.join(output)


def _walk(path):
  filelist = []
  for (root, dirs, files) in os.walk(path):
    for f in files:
      filelist.append(os.path.join(root, f))
  return filelist


def _get_all_mod_stats_for_upstream_refs(mod_stats, dir):
  for file_name in _walk(dir):
    if analyze_diffs.is_tracking_an_upstream_file(file_name):
      analyze_diffs.get_file_mod_stats_for_upstream_refs(file_name, mod_stats)


def _get_section_changes():
  file_names = [os.path.join(analyze_diffs.UPSTREAM_BASE_PATH, f)
                for f in os.listdir(analyze_diffs.UPSTREAM_BASE_PATH)]
  file_names = [f for f in file_names if os.path.isfile(f)]
  all_changes = [ChangeDescription(f) for f in file_names]

  mod_stats = collections.defaultdict(analyze_diffs.ModStats)
  _get_all_mod_stats_for_upstream_refs(mod_stats, 'mods')
  _get_all_mod_stats_for_upstream_refs(mod_stats, 'src')
  for c in all_changes:
    if c._base_name in mod_stats:
      c._mod_stats = mod_stats[c._base_name]

  all_changes = sorted(all_changes, key=lambda c: c._base_name)

  section_changes = {}
  for section in _SECTION_LIST:
    changes = [c for c in all_changes if c.get_section() == section]
    section_changes[section] = changes
  return section_changes


def main():
  _PRINT_FUNCTIONS = {
      'csv': ChangeDescription.print_csv,
      'html': ChangeDescription.print_html}

  parser = argparse.ArgumentParser()
  parser.add_argument('--format', default='csv',
                      help='Output format (%s)' % _PRINT_FUNCTIONS.keys())
  args = parser.parse_args()

  if args.format not in _PRINT_FUNCTIONS:
    print 'Invalid format: %s' % args.format
    parser.print_help()
    return 1

  section_changes = _get_section_changes()
  _PRINT_FUNCTIONS[args.format](section_changes)
  return 0

if __name__ == '__main__':
  sys.exit(main())

#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
# Suggest owners using owners.py functionality.

import argparse
import glob
import owners
import os
import subprocess
import sys
from util import git


def get_owners_db():
  return owners.Database(os.getcwd(), open, os.path, glob.glob)


def _get_reviewer_set_for_commit(db, commit):
  files = subprocess.check_output(['git', 'diff-tree', '--no-commit-id',
                                   '--name-only', '-r', commit]).splitlines()
  author = subprocess.check_output(['git', '--no-pager', 'show', '-s',
                                    '--format=%ae', commit]).rstrip()
  return db.reviewer_set_for(files, author)


def suggest_reviewer_set_for_in_flight_commits(verbose):
  in_flight_commits = git.get_in_flight_commits()
  if not in_flight_commits:
    print 'All commits have already been landed on this branch'
    return False
  db = get_owners_db()
  for commit in in_flight_commits:
    reviewer_set = _get_reviewer_set_for_commit(db, commit)
    print ('REVIEWERS FOR "%s":\n    %s' %
           (git.get_oneline_for_commit(commit),
            format_reviewer_set_in_conjunctive_normal_form(reviewer_set)))
    if verbose:
      explain_reviewer_set(reviewer_set)
  if verbose:
    print ''
  else:
    print ('For more details run: '
           './src/build/suggest_reviewers.py push -v')


def explain_reviewer_set(rs):
  for r in sorted(rs.reviewers.keys()):
    print '  Reviewer: %s' % r,
    if rs.reviewers[r].alternates:
      print '(or %s)' % ', '.join(rs.reviewers[r].alternates)
    else:
      print ''
    for comment in sorted(rs.reviewers[r].comments.keys()):
      if comment:
        print '    # %s' % comment
      all_paths = sorted(rs.reviewers[r].comments[comment])
      for path in all_paths[:5]:
        print '        ' + path
      if len(all_paths) == 6:
        print '        ' + all_paths[5]
      elif len(all_paths) > 6:
        print '        (...and %d more...)' % (len(all_paths) - 5)
    print ''


def format_reviewer_set_in_conjunctive_normal_form(rs):
  def strip_domain(email):
    return email.split('@')[0]

  def format_disjunction(winner, alternates, needs_parens):
    if alternates:
      result = ' || '.join([strip_domain(winner)] + list([strip_domain(a)
                                                          for a in alternates]))
      if needs_parens:
        result = '(%s)' % result
      return result
    return strip_domain(winner)
  needs_parens = rs.reviewers.keys() > 1
  revs = rs.reviewers
  return ' && '.join([format_disjunction(r, revs[r].alternates, needs_parens)
                      for r in sorted(rs.reviewers.keys())])


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('mode', choices=('push', 'commit', 'file'))
  parser.add_argument('--verbose', '-v', action='store_true',
                      help='Verbose output')
  parser.add_argument('args', nargs='*')
  args = parser.parse_args(sys.argv[1:])
  if args.mode == 'push':
    return suggest_reviewer_set_for_in_flight_commits(args.verbose) is not False
  elif args.mode == 'commit':
    db = get_owners_db()
    for commit in args.args:
      commit = git.canonicalize_commit(commit)
      print ('Suggested reviewers for "%s": ' %
             git.get_oneline_for_commit(commit))
      reviewers = _get_reviewer_set_for_commit(db, commit)
      explain_reviewer_set(reviewers)
  elif args.mode == 'file':
    reviewers = get_owners_db().reviewer_set_for(args.args,
                                                 git.get_current_email())
    explain_reviewer_set(reviewers)
  return 0


if __name__ == '__main__':
  sys.exit(main())

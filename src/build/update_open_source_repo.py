#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import logging
import open_source
import os
import subprocess
import sys

import prepare_open_source_commit
import util.git


_OPEN_SOURCE_URL = 'https://chromium.googlesource.com/arc/arc'


def _update_submodules(dest):
  logging.info('Submodule update')
  subprocess.check_call(['git', 'submodule', 'sync'], cwd=dest)
  subprocess.check_call(['git', 'submodule', 'update', '--init'], cwd=dest)


def _clone_repo_if_needed(dest):
  if not os.path.exists(dest):
    logging.info('Cloning open source repo to "%s"' % dest)
    subprocess.check_call(['git', 'clone', '--recursive', _OPEN_SOURCE_URL,
                           dest])


def _validate_local_repository(dest):
  if not util.git.is_git_dir(dest):
    sys.exit('directory "%s" is not a valid git repo' % dest)


def _check_out_matching_branch(dest):
  # We have to update all the remotes to make sure we can find the remote branch
  # this checkout comes from.  On buildbots, only master and tags are fetched by
  # default.
  subprocess.check_call(['git', 'remote', 'update'])
  subprocess.check_call(['git', 'remote', 'update'], cwd=dest)
  remote_branch = util.git.get_remote_branch(util.git.get_last_landed_commit())
  if not util.git.has_remote_branch(remote_branch, cwd=dest):
    sys.exit('Open source repository does not have the remote branch %s' %
             remote_branch)
  logging.info('Checking out %s branch' % remote_branch)
  # |remote_branch| is the portion after the last slash, e.g., 'master', not
  # 'origin/master'.  There should be a local branch with the same name that
  # was created when the remote was updated with the new branch.
  subprocess.check_call(['git', 'checkout', remote_branch], cwd=dest)
  subprocess.check_call(['git', 'pull'], cwd=dest)
  _update_submodules(dest)


def _test_changes(dest):
  logging.info('Testing changes in open source tree')
  configure_options_file = 'out/configure.options'
  with open(configure_options_file) as f:
    subprocess.check_call(['./configure'] + f.read().split(), cwd=dest)
  subprocess.check_call(['ninja', 'all', '-j50'], cwd=dest)


def _commit_changes(dest, label):
  logging.info('Commiting changes to open source tree')
  subprocess.check_call(['git', 'add', '-A'], cwd=dest)
  subprocess.check_call(['git', 'commit',
                         '--author', 'arc-push <arc-push@chromium.org>',
                         '--allow-empty', '-m', 'Updated to %s' % label],
                        cwd=dest)


def _sync_head_tags(dest, src):
  """Synchronize any tags currently pointing at HEAD to the open source repo."""
  tags = subprocess.check_output(['git', 'tag', '--points-at', 'HEAD'], cwd=src)
  for tag in tags.splitlines():
    logging.warning('Updating tag %s' % tag)
    subprocess.check_call(['git', 'tag', '-f', '-a', '-m', tag, tag], cwd=dest)


def _push_changes(dest):
  logging.info('Pushing changes to open source remote repository')
  subprocess.check_call(['git', 'push'], cwd=dest)
  subprocess.check_call(['git', 'push', '--tags'], cwd=dest)


def _reset_and_clean_repo(dest):
  logging.info('Resetting local open source repository')
  subprocess.check_call(['git', 'reset', '--hard'], cwd=dest)
  logging.info('Clearing untracked files from repository')
  # -f -f is intentional, this will get rid of untracked modules left behind.
  subprocess.check_call(['git', 'clean', '-f', '-f', '-d'], cwd=dest)


# Updates or clones from scratch the open source repository at the location
# provided on the command line.  The resultant repo is useful to pass into
# prepare_open_source_commit.py to then populate the repo with a current
# snapshot.
def main():
  assert not open_source.is_open_source_repo(), ('Cannot be run from open '
                                                 'source repo.')
  parser = argparse.ArgumentParser()
  parser.add_argument('--force', action='store_true',
                      help=('Overwrite any changes in the destination'))
  parser.add_argument('--push-changes', action='store_true',
                      help=('Push changes to the destination repository\'s '
                            'remote'))
  parser.add_argument('--verbose', '-v', action='store_true',
                      help=('Get verbose output'))
  parser.add_argument('dest')
  args = parser.parse_args(sys.argv[1:])
  if args.verbose:
    logging.getLogger().setLevel(logging.INFO)

  _clone_repo_if_needed(args.dest)
  _validate_local_repository(args.dest)
  if (util.git.get_uncommitted_files(cwd=args.dest) and not args.force):
    logging.error('%s has uncommitted files, use --force to override')
    return 1
  _reset_and_clean_repo(args.dest)
  _check_out_matching_branch(args.dest)
  # Submodules abandoned between branches will still leave their directories
  # around which can confuse prepare_open_source_commit, so we clean them out.
  _reset_and_clean_repo(args.dest)

  prepare_open_source_commit.run(args.dest, args.force)

  _test_changes(args.dest)
  if args.push_changes:
    commit_label = subprocess.check_output(['git', 'describe']).strip()
    _commit_changes(args.dest, commit_label)
    _sync_head_tags(args.dest, '.')
    _push_changes(args.dest)
  else:
    _reset_and_clean_repo(args.dest)
  return 0


if __name__ == '__main__':
  sys.exit(main())

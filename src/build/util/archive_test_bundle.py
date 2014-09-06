#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Archives files needed to run integration tests such as arc runtime,
# CRX files, config files, and test jar files.

import argparse
import os
import re
import subprocess
import sys
import zipfile

sys.path.insert(0, 'src/build')

import build_common
import run_integration_tests
import toolchain
from build_options import OPTIONS
from util import remote_executor_util


def _get_stripped_dir():
  return os.path.join(build_common.get_build_dir(), 'test_bundle_stripped')


def _collect_descendants(paths):
   """Returns the set of descendant files of the directories in |paths|.

   If |paths| includes files in |paths|, the files are included in the returned
   set. Unnecessary files for running integration tests such as temporary files
   created by editor, .pyc, and .ncval files are excluded from the returned set.
   """
   files = [path for path in paths if os.path.isfile(path)]
   dirs = [path for path in paths if os.path.isdir(path)]
   files += build_common.find_all_files(dirs, include_tests=True,
                                        use_staging=False)
   files = [f for f in files if not re.match(r'.*\.(pyc|ncval)', f)]
   return set(files)


def _get_archived_file_paths():
  """Returns the file paths to be archived."""
  paths = _collect_descendants(
      remote_executor_util.get_integration_test_files_and_directories())
  paths.add(os.path.relpath(toolchain.get_adb_path_for_chromeos(),
                            build_common.get_arc_root()))
  paths |= set(run_integration_tests.get_configs_for_integration_tests())
  return paths


def _zip_files(filename, paths):
  """Creates a zip file that contains the specified files."""
  # Set allowZip64=True so that large zip files can be handled.
  with zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED,
                       allowZip64=True) as f:
    for path in set(paths):
      if path.startswith(_get_stripped_dir()):
        # When archiving a stripped file, use the path of the corresponding
        # unstripped file as archive name
        f.write(path, arcname=os.path.relpath(path, _get_stripped_dir()))
      else:
        f.write(path)


def _get_integration_tests_args(jobs):
  """Gets args of run_integration_tests.py adjusted for archiving files."""
  args = run_integration_tests.parse_args(['--jobs=%d' % jobs])
  # Create an archive to be used on buildbots.
  args.buildbot = True
  # Assume buildbots support GPU.
  args.gpu = 'on'
  # Archive failing tests as well.
  args.include_failing = True
  return args


def _should_strip(path):
  """Returns true if the file at |path| should be stripped."""
  return (path.startswith(build_common.get_build_dir()) and
          path.endswith(('.nexe', '.so')))


def _strip_binaries(paths):
  """Strips the files in |paths| and returns the paths of stripped files."""
  stripped_paths = []
  for path in paths:
    if _should_strip(path):
      stripped_path = os.path.join(_get_stripped_dir(), path)
      build_common.makedirs_safely(os.path.dirname(stripped_path))
      subprocess.check_call(['strip', path, '-o', stripped_path])
      stripped_paths.append(stripped_path)
    else:
      stripped_paths.append(path)
  return stripped_paths


def _parse_args():
  description = 'Archive files needed to run integration tests.'
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('-j', '--jobs', metavar='N', default=1, type=int,
                      help='Prepare N tests at once.')
  parser.add_argument('-o', '--output',
                      default=build_common.get_test_bundle_name(),
                      help=('The name of the test bundle to be created.'))
  return parser.parse_args()


if __name__ == '__main__':
  OPTIONS.parse_configure_file()

  # Build arc runtime.
  build_common.run_ninja()

  # Prepare all the files needed to run integration tests.
  parsed_args = _parse_args()
  integration_tests_args = _get_integration_tests_args(parsed_args.jobs)
  run_integration_tests.set_test_options(integration_tests_args)
  run_integration_tests.set_test_config_flags(integration_tests_args)
  assert run_integration_tests.prepare_suites(integration_tests_args)

  # Prepare dalvik.401-perf for perf vm tests.
  integration_tests_args.include_patterns = ['dalvik.401-perf:*']
  assert run_integration_tests.prepare_suites(integration_tests_args)

  # Archive all the files needed to run integration tests into a zip file.
  paths = _get_archived_file_paths()
  if OPTIONS.is_debug_info_enabled():
    paths = _strip_binaries(paths)
  print 'Creating %s' % parsed_args.output
  _zip_files(parsed_args.output, paths)
  print 'Done'

#!/usr/bin/env python
#
# Copyright (C) 2014 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import string
import os
import re
import subprocess
import sys

sys.path.insert(0, 'src/build')

import build_common
import open_source
import toolchain
from build_options import OPTIONS


def _get_bionic_fundamental_tests():
  tests = []
  # This uses NaCl syscalls directly and is not compatible with Bare
  # Metal mode.
  if OPTIONS.is_nacl_build():
    # If this passes, the loader is working.
    tests.append(('loader_test', ['$runner', '$test_binary'], {}))
  tests.extend([
      # If this passes, IRT calls are ready.
      ('write_test', ['$runner', '$test_binary'], {}),
      # If this passes, stdio and malloc are ready.
      ('printf_test', ['$runner', '$test_binary'], {}),
      # If this passes, arguments and environment variables are OK.
      ('args_test', ['$runner', '$test_binary', 'foobar'], {}),
      # If this passes, .ctors and .dtors are working.
      ('structors_test', ['$runner', '$test_binary'], {}),
      # If this passes, symbols are available for subsequently loaded binaries.
      ('resolve_parent_sym_test',
       ['$runner_with_extra_ld_library_path', '$test_binary'], {}),
      # If this passes, .ctors and .dtors with DT_NEEDED are working.
      ('so_structors_test',
       ['$runner_with_extra_ld_library_path', '$test_binary'], {}),
      # If this passes, .ctors and .dtors with dlopen are working.
      ('dlopen_structors_test',
       ['$runner_with_extra_ld_library_path', '$test_binary'], {}),
      # If this passes, dlopen fails properly when there is a missing symbol.
      ('dlopen_error_test',
       ['$runner_with_extra_ld_library_path', '$test_binary'], {}),
  ])
  # Bionic does not restart .fini_array when exit() is called in global
  # destructors. This works only for environments which use
  # .fini/.dtors. Currently, Bare Metal uses .fini_array.
  if not OPTIONS.is_arm() and OPTIONS.is_nacl_build():
    # If this passes, exit() in global destructors is working. Note
    # that Bionic does not continue atexit handlers in an exit call so
    # we cannot test this case with other structors_tests.
    tests.append(('dlopen_structors_test-with_exit',
                  ['$runner_with_extra_ld_library_path', '$test_binary'],
                  {'CALL_EXIT_IN_DESTRUCTOR': '1'}))
  return tests


class BionicFundamentalTestRunner(object):
  def __init__(self):
    self._test_out_dir = os.path.join(build_common.get_build_dir(),
                                      'bionic_tests')
    runner = toolchain.get_tool(OPTIONS.target(), 'runner')
    # Add self._test_out_dir to LD_LIBRARY_PATH
    runner_with_extra_ld_library_path = re.sub(
        r'(LD_LIBRARY_PATH=[^ ]+)', r'\1:' + self._test_out_dir, runner)
    self._variables = {
        'runner': runner,
        'runner_with_extra_ld_library_path': runner_with_extra_ld_library_path,
    }

    self._test_cnt = 0
    self._fail_cnt = 0

  def run(self):
    for test_name, test_cmd, test_env in _get_bionic_fundamental_tests():
      # If a test name contains a hyphen, we use the binary before the
      # hyphen character.
      test_binary_basename = re.sub(r'-.*', '', test_name)
      test_binary = os.path.abspath(os.path.join(self._test_out_dir,
                                                 test_binary_basename))
      self._variables['test_binary'] = test_binary

      sys.stdout.write(test_name + ': ')
      test_cmd = string.Template(
          ' '.join(test_cmd)).substitute(self._variables)

      for pair in test_env.iteritems():
        test_cmd = re.sub(r' -E ', ' -E %s=%s -E ' % (pair), test_cmd)

      pipe = subprocess.Popen(test_cmd.split(),
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
      out = pipe.communicate()[0]

      result_filename = os.path.join(self._test_out_dir, test_name) + '.result'
      with open(result_filename, 'w') as f:
        f.write(out)

      self._test_cnt += 1
      if pipe.returncode:
        self._fail_cnt += 1
        sys.stdout.write('FAIL (exit=%d)\n' % pipe.returncode)
        sys.stdout.write(out + '\n')
      elif out.find('PASS\n') < 0:
        self._fail_cnt += 1
        sys.stdout.write('FAIL (no PASS)\n')
        sys.stdout.write(out + '\n')
      else:
        sys.stdout.write('OK\n')

  def is_ok(self):
    return not self._fail_cnt


def main(args):
  OPTIONS.parse_configure_file()

  # TODO(crbug.com/378196): Make qemu-arm available in open source in order to
  # run any unit tests there.
  if open_source.is_open_source_repo() and OPTIONS.is_arm():
    return 0

  test_runner = BionicFundamentalTestRunner()
  test_runner.run()

  if not test_runner.is_ok():
    return 1

  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv))

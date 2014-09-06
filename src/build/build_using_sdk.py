#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Build APK from C/C++ and java sources with Android SDK and NDK.

import argparse
import os
import subprocess
import sys
import shutil

import build_common


_ARC_ROOT = build_common.get_arc_root()
_NDK_PATH = os.path.join(_ARC_ROOT, 'third_party', 'ndk')
_SDK_PATH = os.path.join(_ARC_ROOT, 'third_party', 'android-sdk')
_TOOLS_ROOT = os.path.join(_ARC_ROOT, 'third_party', 'tools')


def _build_apk(source_path, use_ndk, build_path, install_apk, debug, verbose):
  if not os.path.isdir(_SDK_PATH):
    raise Exception('Missing SDK path: ' + str(_SDK_PATH))

  print
  print '--------------------------'
  print 'Building ' + os.path.basename(install_apk)
  print '--------------------------'

  # We use this work directory in order to allow us to completely
  # create it from scratch every time we build.  We cannot do that
  # to the build_path since files in there (like the build.log)
  # should not be deleted on every run.
  work_path = os.path.join(build_path, 'work')

  if os.path.isdir(work_path):
    shutil.rmtree(work_path)
  shutil.copytree(os.path.join('.', source_path), work_path)
  print os.path.join(_SDK_PATH, 'tools', 'android')
  # Any target 14+ should work (tested on 17).
  subprocess.check_call([
      os.path.join(_SDK_PATH, 'tools', 'android'),
      'update', 'project', '--target', 'android-17', '--path', '.',
      '--name', 'test_app'], cwd=work_path)
  if use_ndk:
    if not os.path.isdir(_NDK_PATH):
      raise Exception('Missing NDK path: ' + str(_NDK_PATH))
    app_optim = 'release'
    if debug:
      app_optim = 'debug'
    if not os.path.exists(os.path.join(work_path, 'jni', 'Application.mk')):
      # Write desired ABI before calling ndk-build
      open(os.path.join(work_path, 'jni', 'Application.mk'), 'w').write(
          'APP_ABI := x86 armeabi armeabi-v7a\n' +
          ('APP_OPTIM := %s\n' % app_optim) +
          'APP_STL := stlport_static\n')
    extras = []
    if verbose:
       extras.append('V=1')
    subprocess.check_call([os.path.join(_NDK_PATH, 'ndk-build'),
                           '-j', '16', '-l', '16',
                           'ARC_ROOT=' + _ARC_ROOT] + extras,
                          cwd=work_path)

  subprocess.check_call([os.path.join(_TOOLS_ROOT, 'ant', 'bin', 'ant'),
                         'debug'], cwd=work_path)

  shutil.copyfile(os.path.join(work_path, 'bin', 'test_app-debug.apk'),
                  install_apk)


def main():
  # JAVA_HOME may be set by Android envsetup.sh script.  If so, remove it
  # from the environment and use the default.
  if 'JAVA_HOME' in os.environ:
    del os.environ['JAVA_HOME']

  parser = argparse.ArgumentParser()
  parser.add_argument('--apk', metavar='<output>', required='True')
  parser.add_argument('--build_path', metavar='<path>', required='True')
  parser.add_argument('--debug', action='store_true')
  parser.add_argument('--ndk', metavar='<path>')
  parser.add_argument('--sdk', metavar='<path>')
  parser.add_argument('--source_path', metavar='<path>', required='True')
  parser.add_argument('--use_ndk', action='store_true')
  parser.add_argument('--verbose', '-v', action='store_true')
  args = parser.parse_args()

  global _SDK_PATH
  if args.sdk:
    _SDK_PATH = os.path.abspath(args.sdk)

  global _NDK_PATH
  if args.ndk:
    _NDK_PATH = os.path.abspath(args.ndk)

  build_path = os.path.abspath(args.build_path)
  install_apk = os.path.abspath(args.apk)
  source_path = os.path.abspath(args.source_path)

  try:
    _build_apk(source_path, args.use_ndk, build_path, install_apk,
               args.debug, args.verbose)
  except Exception, e:
    print str(e)
    return 1
  return 0


if __name__ == '__main__':
  sys.exit(main())

#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Downloads buildbot logs for offline use.

Usage:
Simply run the script with no argument.

  $ src/build/util/download_bot_logs.py

This will download the the latest 20 logs of the builders listed in the builders
page (http://chromegw.corp.google.com/i/client.alloy/builders) into
botlogs/<builder name> directories.

You can also tweak the behavior of the script by specifying arguments.

  $ src/build/util/download_bot_logs.py --number-of-logs=50 --jobs=10 \
        --outdir=../botlogs nacl-x86_64-bionic nacl-i686-bionic

This will set the number of logs to 50, run 10 jobs in parallel, download the
logs of nacl-x86_64-bionic and nacl-i686-bionic builders, and save the logs to
../botlogs.
"""

import argparse
import contextlib
import json
import os
import sys
import urllib2

sys.path.insert(0, 'src/build')
import build_common
import util.concurrent

_BUILDBOT_URL = 'https://chromegw.corp.google.com/i/client.alloy'
_LOG_URL_TMPL = ('%(buildbot_url)s/builders/%(builder)s/builds/'
                 '%(build_number)d/steps/steps/logs/stdio/text')

_TARGETS = [
    'bare_metal_arm',
    'bare_metal_i686',
    'nacl_i686',
    'nacl_x86_64',
]


def get_log_path(logs_dir, build_number):
  return os.path.join(logs_dir, '%06d.log' % build_number)


def deduce_target_from_builder(builder):
  for target in _TARGETS:
    if target in builder.replace('-', '_'):
      return target
  raise Exception('Cannot deduce target for ' + builder)


def download_log(builder, build_number, logs_dir):
  log_path = get_log_path(logs_dir, build_number)
  if os.path.exists(log_path):
    sys.stdout.write('Skip downloading log. %s exists.\n' % log_path)
    return
  sys.stdout.write('Downloading %s #%d\n' % (builder, build_number))
  url = _LOG_URL_TMPL % {'buildbot_url': _BUILDBOT_URL,
                         'builder': builder,
                         'build_number': build_number,
                         'target': deduce_target_from_builder(builder)}
  try:
    with contextlib.closing(urllib2.urlopen(url)) as stream:
      build_common.write_atomically(log_path, stream.read())
  except urllib2.URLError:
    print 'Download failed: ' + url


def get_json_data(path):
  """Gets buildbot information using JSON API of buildbot server.

  path is appended to the API entry point (/json/).
  See JSON API help to know what is supported.
  https://chromegw.corp.google.com/i/client.alloy/json/help
  """
  url = '%s/json/%s' % (_BUILDBOT_URL, path)
  try:
    with contextlib.closing(urllib2.urlopen(url)) as stream:
      return json.load(stream)
  except urllib2.HTTPError:
    print '%s not found.' % url
    raise


def get_builders_info():
  """Gets a dict that maps builder names to latest builder numbers."""
  builders_data = get_json_data('builders')
  builder_info = {}
  for builder, builder_data in builders_data.iteritems():
    # Exclude currentsBuilds because their complete logs are not available yet.
    latest_build_number = max(set(builder_data['cachedBuilds']) -
                              set(builder_data['currentBuilds']))
    builder_info[builder] = latest_build_number
  return builder_info


def parse_args():
  parser = argparse.ArgumentParser()
  parser.add_argument('-n', '--number-of-logs', type=int, default=20,
                      help='The number of logs to be downloaded per builder.')
  parser.add_argument('-o', '--outdir', default='botlogs',
                      help=('The directory to save logs. Log files are stored '
                            'in the subdirectories per builder.'))
  parser.add_argument('-j', '--jobs', type=int, default=20,
                      help='The number of jobs to run in parallel.')
  parser.add_argument('-l', '--list', action='store_true',
                      help='List the all builders.')
  parser.add_argument('builders', nargs='*',
                      help=('The builders to download the log. all the '
                            'builders are selected if not specified'))
  return parser.parse_args()


def validate_builders(builders, all_builders):
  for builder in builders:
    if builder not in all_builders:
      print 'Invalid builder name: ' + builder
      return False
  return True


def make_download_args_list(builders_info, outdir, number_of_logs):
  download_args_list = []
  for builder, build_number in builders_info.iteritems():
    logs_dir = os.path.join(outdir, builder)
    build_common.makedirs_safely(logs_dir)
    build_range = range(max(build_number - number_of_logs + 1, 0),
                        build_number + 1)
    download_args_list += [(builder, build_number, logs_dir)
                           for build_number in build_range]
  return download_args_list


def main():
  args = parse_args()
  builders_info = get_builders_info()
  all_builders = sorted(builders_info.keys())
  builders = args.builders
  if args.list or not validate_builders(builders, all_builders):
    print 'Select any of the following builders:'
    print '\n'.join(all_builders)
    return
  if not builders:
    builders = all_builders

  download_args_list = make_download_args_list(
      builders_info, args.outdir, args.number_of_logs)
  with util.concurrent.ThreadPoolExecutor(args.jobs, daemon=True) as executor:
    for download_args in download_args_list:
      executor.submit(download_log, *download_args)
  print 'Downloaded logs in %s' % args.outdir


if __name__ == '__main__':
  main()

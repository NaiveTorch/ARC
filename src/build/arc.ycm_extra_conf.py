# Copyright (c) 2013 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Autocompletion config for YouCompleteMe in ARC.
#
# USAGE:
#
#   1. Install YCM [https://github.com/Valloric/YouCompleteMe]
#          (Googlers should check out [go/ycm])
#
#   2. Point to this config file in your .vimrc:
#          let g:ycm_global_ycm_extra_conf =
#              '<arc_depot>/src/build/arc.ycm_extra_conf.py'
#
#   3. Profit!
#
#
# Usage notes:
#
#   * You must have built ARC before using this.
#
#   * Not all files have correct completion information since ninja does not use
#     gomacc for all C++ files.
#
#   * You can avoid the call to ninja every time a file is saved/loaded by
#     creating a JSON compilation database with the following command:
#       $ ninja -t compdb cxx.nacl_i686 cc.nacl_i686 > \
#         ycm/compile_commands.json
#     Replacing 'nacl_i686' with the current ARC target.
#
# Hacking notes:
#
#   * The purpose of this script is to construct an accurate enough command line
#     for YCM to pass to clang so it can build and extract the symbols.
#
#   * Right now, we only pull some flags. That seems to be sufficient for
#     everything I have used it for.
#
#   * That whole ninja & clang thing? We could support other configs if someone
#     were willing to write the correct commands and a parser.
#
#   * This has only been tested on gPrecise.


import os
import subprocess


# Flags from YCM's default config.
default_flags = [
    '-DUSE_CLANG_COMPLETER',
    '-x',
    'c++',
]


def _get_arc_root():
  """Searches for the root of the ARC checkout.

  This file is checked in the src/build/ directory, so we only need to go
  up two directories.

  Returns:
    (String) Path of the ARC root.
  """
  return os.path.abspath(
      os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', '..'))


def _get_source_filename(filename):
  """Gets the corresponding source file for headers.

  Header files do not have an associated gomacc command. Instead, try to
  find its corresponding .cc/.cpp file to get the right flags.

  Args:
    filename: (String) Path to the file being edited.

  Returns:
    (String) Best guess for the source file corresponding to |filename|.
  """
  root, ext = os.path.splitext(filename)
  if ext == '.h':
    alternates = ['.cc', '.cpp']
    for alt_extension in alternates:
      alt_name = root + alt_extension
      if os.path.exists(alt_name):
        return alt_name
  return filename


def _get_staging_relative_filename(arc_root, filename):
  if not (arc_root and filename.startswith(arc_root)):
    return filename

  # For ARC, ninja and the compilation database it writes out both use file
  # paths relative to the staging directory.
  rel_filename = filename[len(arc_root) + 1:]

  if rel_filename.startswith('mods/'):
    rel_filename = 'out/staging/' + rel_filename[len('mods/'):]
  elif rel_filename.startswith('third_party/'):
    rel_filename = 'out/staging/' + rel_filename[len('third_party/'):]
  elif rel_filename.startswith('src/'):
    rel_filename = 'out/staging/' + rel_filename

  return os.path.join(arc_root, rel_filename)


def _get_clang_command_compdb(arc_root, compilation_database_folder,
                              filename):
  """Query the compdb to get the compiler flags for |filename|.

  This avoids calling ninja every time YCM needs to get the compiler
  flags. The compilation database must be regenerated every time a file
  is added, or ./configure is called. See here for more details:
  http://clang.llvm.org/docs/JSONCompilationDatabase.html

  Args:
    compilation_database_folder: (String) The path of the JSON compilation
      database: the ycm/ directory.
    arc_root: (String) Path to the root of the ARC repository.
    filename: (String) Path to source file being edited.

  Returns:
    (List of Strings) Command line arguments for clang.
  """
  import ycm_core
  filename = _get_staging_relative_filename(arc_root, filename)
  database = ycm_core.CompilationDatabase(compilation_database_folder)
  compilation_info = database.GetCompilationInfoForFile(filename)

  if not compilation_info:
    return []

  return compilation_info.compiler_flags_


def _get_compiled_output_file_from_ninja(arc_root, filename):
  stdout = subprocess.check_output(
      ['ninja', '-v', '-C', arc_root, '-t', 'query', filename])

  object_filename = os.path.splitext(os.path.basename(filename))[0] + '.o'
  for line in stdout.split('\n'):
    if line.endswith(object_filename):
      return line.strip()
  return None


def _get_build_commands_from_ninja(arc_root, filename):
  stdout = subprocess.check_output(
      ['ninja', '-v', '-C', arc_root, '-t', 'commands', filename])
  return stdout.split('\n')


def _find_last_gomacc_command(commands):
  for line in reversed(commands):
    if 'gomacc' in line:
      return line.split(' ')
  return None


def _get_clang_command_ninja(arc_root, filename):
  """Returns the command line to build |filename|.

  Asks ninja how it would build the source file. If the specified file is a
  header, tries to find its companion source file first.

  Args:
    arc_root: (String) Path to the root of the ARC repository.
    filename: (String) Path to source file being edited.

  Returns:
    (List of Strings) Command line arguments for clang.
  """
  if not arc_root:
    return []

  # Ask ninja about the dependency graph for the source file
  filename = _get_staging_relative_filename(arc_root, filename)
  rel_filename = filename[len(arc_root) + 1:]
  output_filename = _get_compiled_output_file_from_ninja(arc_root,
                                                         rel_filename)
  if not output_filename:
    return []

  commands = _get_build_commands_from_ninja(arc_root, output_filename)
  if not commands:
    return []

  # Ninja might execute several commands to build something. We want the last
  # gomacc command.
  gomacc = _find_last_gomacc_command(commands)
  if not gomacc:
    return []
  return gomacc


def absolute_path(filepath, arc_root):
  if filepath[0] == '/':
    return filepath
  return os.path.normpath(os.path.join(arc_root, filepath))


def _process_flags(arc_root, flags):
  """Filter out flags and convert all paths to absolute paths.

  Args:
    arc_root: (String) Path to the root of the ARC repository.
    flags: (List of Strings) List of flags returned by ninja/compdb

  Returns:
    (List of Strings) The filtered flags ready for YCM"""
  arc_flags = []

  take_next_as_path = False

  # Parse out whitelisted flags. These seem to be the only ones that are
  # important for YCM's purposes.
  for flag in flags:
    if take_next_as_path:
      take_next_as_path = False
      arc_flags.append(absolute_path(flag, arc_root))
    elif flag.startswith('-I'):
      # Relative paths need to be resolved, because they're relative to the
      # output dir, not the source.
      if flag == '-I':
        arc_flags.append('-I')
        take_next_as_path = True
      else:
        arc_flags.append('-I' + absolute_path(flag[2:], arc_root))
    elif flag.startswith('-') and flag[1] in 'DUWFfmO':
      if flag == '-Wno-deprecated-register' or flag == '-Wno-header-guard':
        # These flags causes libclang (3.3) to crash. Remove it until things
        # are fixed.
        continue
      arc_flags.append(flag)

  return arc_flags


def FlagsForFile(filename):
  """This is the main entry point for YCM. Its interface is fixed.

  Args:
    filename: (String) Path to source file being edited.

  Returns:
    (Dictionary)
      'flags': (List of Strings) Command line flags.
      'do_cache': (Boolean) True if the result should be cached.
  """
  arc_root = _get_arc_root()
  compilation_database_folder = os.path.join(arc_root, 'ycm')
  filename = _get_source_filename(filename)
  arc_flags = []
  # Try reading the compilation database first
  if os.path.exists(compilation_database_folder):
    arc_flags = _get_clang_command_compdb(arc_root,
                                          compilation_database_folder,
                                          filename)
  # Fall back to getting it from ninja
  if not arc_flags:
    arc_flags = _get_clang_command_ninja(arc_root,
                                         filename)
  final_flags = default_flags + _process_flags(arc_root, arc_flags)
  return {
      'flags': final_flags,
      'do_cache': True
  }

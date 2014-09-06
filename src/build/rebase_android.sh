#!/bin/bash

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Tool to automate rebasing our patched files against upstream
# Android code.

set -e

OUTERPATH=$1
OLDBASE=$2

if [ "$OUTERPATH" = "" ] || [ "$OLDBASE" = "" ]; then
  cat <<EOF
Usage: $0 <submodule path within third_party/android> <previous tag>

The specified submodule must be updated to the tag onto which
you want to rebase.

Example:
  # Update submodule third_party/android/frameworks/base to the new
  # tag you want to base on, such as android-4.1.1_r1.
  # Then, to have all files in this directory be rebased
  # on that tag from old tag android-4.0.4_r1.2-1011-gad3f86a,
  # use this command:
  $0 \
    frameworks/base android-4.0.4_r1.2-1011-gad3f86a
EOF
  exit 1
fi

NEWBASE=$(pushd third_party/android/$OUTERPATH>/dev/null; \
          git describe; popd>/dev/null)
FILES=$(pushd mods/android/$OUTERPATH > /dev/null && find . -type f && \
        popd > /dev/null)
echo "Rebasing $OUTERPATH from $OLDBASE to $NEWBASE"
echo ""
TOTAL_FILES=0
CONFLICT_FILES=0

for file in $FILES; do
  INNERPATH=$file
  pushd third_party/android/$OUTERPATH >/dev/null
  if ! [ -r $INNERPATH ]; then
    echo "Not in third_party/android: $INNERPATH"
    popd >/dev/null
    continue
  fi
  git show $OLDBASE:$INNERPATH > /tmp/$OLDBASE
  git show $NEWBASE:$INNERPATH > /tmp/$NEWBASE
  popd >/dev/null
  echo "Rebasing mods/android/$OUTERPATH/$INNERPATH"
  TOTAL_FILES=$((TOTAL_FILES + 1))
  if ! merge mods/android/$OUTERPATH/$INNERPATH /tmp/$OLDBASE /tmp/$NEWBASE; then
    CONFLICT_FILES=$((CONFLICT_FILES + 1))
  fi
done

echo ""
echo "$CONFLICT_FILES of $TOTAL_FILES files have conflicts"

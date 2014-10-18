#! /bin/sh
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Script to install dependencies needed for running and building ARC.
# For Ubuntu older than 14.04, use install-arc-deps.sh instead.

if ! egrep -q '14\.04' /etc/issue; then
  echo "ERROR: Only Ubuntu 14.04 is currently supported" >&2
  echo "ERROR: Run install-arc-deps.sh instead" >&2
  exit 1
fi

# Packages for building ARC.
arc_list="
g++-arm-linux-gnueabihf
gcc-arm-linux-gnueabihf
libc6-dev-i386
libcap-dev:amd64
libgl1-mesa-dev:i386
linux-libc-dev:i386
openjdk-6-jdk
pbzip2
pigz
"

# Packages for running tests.
arc_list="$arc_list
python3
"

# libosmesa is needed to run Chrome under XVFB and Chromoting.
arc_list="$arc_list
libosmesa6:i386
libosmesa6
"

# libncurses5 is needed for clang.
arc_list="$arc_list
libncurses5:i386
"

# python-markdown is needed to convert Markdown files to HTML.
arc_list="$arc_list
python-markdown
"

# Packages for running 32-bit Chrome at out/chrome32/chrome. To build 32-bit
# Chrome, follow the instructions in install-chroot.sh in Chrome tree.
chrome32_list="
libasound2:i386
libcairo2:i386
libcap2:i386
libcups2:i386
libfontconfig1:i386
libgconf-2-4:i386
libglib2.0-0:i386
libgtk2.0-0:i386
libnss3:i386
libpango1.0-0:i386
libudev1:i386
libxcomposite1:i386
libxcursor1:i386
libxdamage1:i386
libxi6:i386
libxinerama1:i386
libxrandr2:i386
libxss1:i386
libxtst6:i386
"

# Packages for running NaCl, its toolchains, and its ports.
# libtinfo5 is needed for running nacl-gdb.
nacl_list="
libtinfo5:i386
libtinfo5
"

sudo apt-get install --no-install-recommends \
  ${arc_list} ${chrome32_list} ${nacl_list}

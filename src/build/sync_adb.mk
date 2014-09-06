# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# This makefile is used to build 'adb' command from a subset of gingerbread
# source code. This makefile is intended to be used with sync_adb.py, but to
# use it standalone, run like this:
#
# make -f src/build/sync_adb.mk TARGET=linux-arm CC=arm-linux-gnueabihf-gcc
#
# Note that the source code must be placed at out/adb/src
#

TOPDIR= out/adb
SRCS =  $(TOPDIR)/src/system/core/adb/adb.c \
	$(TOPDIR)/src/system/core/adb/adb_client.c \
	$(TOPDIR)/src/system/core/adb/commandline.c \
	$(TOPDIR)/src/system/core/adb/console.c \
	$(TOPDIR)/src/system/core/adb/file_sync_client.c \
	$(TOPDIR)/src/system/core/adb/fdevent.c \
	$(TOPDIR)/src/system/core/adb/get_my_path_linux.c \
	$(TOPDIR)/src/system/core/adb/services.c \
	$(TOPDIR)/src/system/core/adb/sockets.c \
	$(TOPDIR)/src/system/core/adb/transport.c \
	$(TOPDIR)/src/system/core/adb/transport_local.c \
	$(TOPDIR)/src/system/core/adb/transport_usb.c \
	$(TOPDIR)/src/system/core/adb/usb_linux.c \
	$(TOPDIR)/src/system/core/adb/usb_vendors.c \
	$(TOPDIR)/src/system/core/adb/utils.c \
	$(TOPDIR)/src/system/core/libcutils/abort_socket.c \
	$(TOPDIR)/src/system/core/libcutils/socket_inaddr_any_server.c \
	$(TOPDIR)/src/system/core/libcutils/socket_local_client.c \
	$(TOPDIR)/src/system/core/libcutils/socket_local_server.c \
	$(TOPDIR)/src/system/core/libcutils/socket_loopback_client.c \
	$(TOPDIR)/src/system/core/libcutils/socket_loopback_server.c \
	$(TOPDIR)/src/system/core/libcutils/socket_network_client.c \
	$(TOPDIR)/src/system/core/libzipfile/centraldir.c \
	$(TOPDIR)/src/system/core/libzipfile/zipfile.c \
	$(TOPDIR)/src/external/zlib/adler32.c \
	$(TOPDIR)/src/external/zlib/compress.c \
	$(TOPDIR)/src/external/zlib/crc32.c \
	$(TOPDIR)/src/external/zlib/deflate.c \
	$(TOPDIR)/src/external/zlib/infback.c \
	$(TOPDIR)/src/external/zlib/inffast.c \
	$(TOPDIR)/src/external/zlib/inflate.c \
	$(TOPDIR)/src/external/zlib/inftrees.c \
	$(TOPDIR)/src/external/zlib/trees.c \
	$(TOPDIR)/src/external/zlib/uncompr.c \
	$(TOPDIR)/src/external/zlib/zutil.c

BUILD_DIR = $(TOPDIR)/$(TARGET)

CC = gcc
LD = $(CC)

CPPFLAGS = -DADB_HOST=1 -DHAVE_FORKEXEC=1 -DHAVE_SYMLINKS -DHAVE_TERMIO_H \
	   -D_GNU_SOURCE -D_XOPEN_SOURCE \
	   -I $(TOPDIR)/src/system/core/adb \
	   -I $(TOPDIR)/src/system/core/include \
	   -I $(TOPDIR)/src/external/zlib
CFLAGS = -O2
LIBS =  -lrt -lpthread
LDFLAGS = -static
OBJS = ${SRCS:%.c=$(BUILD_DIR)/%.o}

$(BUILD_DIR)/adb: $(OBJS)
	@mkdir -p $(dir $@)
	$(LD) -o $@ $(LDFLAGS) $(OBJS) $(LIBS)

$(OBJS): $(BUILD_DIR)/%.o : %.c
	@mkdir -p $(dir $@)
	$(COMPILE.c) -o $@ $<

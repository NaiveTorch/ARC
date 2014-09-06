// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <sys/stat.h>

#include "bare_metal/common/nacl_stat.h"

void __stat_to_nacl_abi_stat(struct stat* st, struct nacl_abi_stat* out) {
  out->nacl_abi_st_dev = st->st_dev;
  out->nacl_abi_st_ino = st->st_ino;
  out->nacl_abi_st_mode = st->st_mode;
  out->nacl_abi_st_nlink = st->st_nlink;
  out->nacl_abi_st_uid = st->st_uid;
  out->nacl_abi_st_gid = st->st_gid;
  out->nacl_abi_st_rdev = st->st_rdev;
  out->nacl_abi_st_size = st->st_size;
  out->nacl_abi_st_blksize = st->st_blksize;
  out->nacl_abi_st_blocks = st->st_blocks;
  out->nacl_abi_st_atime = st->st_atim.tv_sec;
  out->nacl_abi_st_atimensec = st->st_atim.tv_nsec;
  out->nacl_abi_st_mtime = st->st_mtim.tv_sec;
  out->nacl_abi_st_mtimensec = st->st_mtim.tv_nsec;
  out->nacl_abi_st_ctime = st->st_ctim.tv_sec;
  out->nacl_abi_st_ctimensec = st->st_ctim.tv_nsec;
}

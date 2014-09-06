// ARC MOD TRACK "third_party/nacl-glibc/sysdeps/nacl/fxstat.c"
// ARC MOD BEGIN
// Copyright and headers.
// Copyright (C) 2014 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <sys/stat.h>

#include <nacl_stat.h>
// ARC MOD END

void __nacl_abi_stat_to_stat (struct nacl_abi_stat *nacl_st,
                                struct stat *st)
{
  st->st_dev = nacl_st->nacl_abi_st_dev;
  st->st_mode = nacl_st->nacl_abi_st_mode;
  st->st_nlink = nacl_st->nacl_abi_st_nlink;
  st->st_uid = nacl_st->nacl_abi_st_uid;
  st->st_gid = nacl_st->nacl_abi_st_gid;
  st->st_rdev = nacl_st->nacl_abi_st_rdev;
  st->st_size = nacl_st->nacl_abi_st_size;
  st->st_blksize = nacl_st->nacl_abi_st_blksize;
  st->st_blocks = nacl_st->nacl_abi_st_blocks;
  // ARC MOD BEGIN
  // Field names are different.
  st->st_atime = nacl_st->nacl_abi_st_atime;
  st->st_atime_nsec = 0;
  st->st_mtime = nacl_st->nacl_abi_st_mtime;
  st->st_mtime_nsec = 0;
  st->st_ctime = nacl_st->nacl_abi_st_ctime;
  st->st_ctime_nsec = 0;
  // ARC MOD END
  st->st_ino = nacl_st->nacl_abi_st_ino;
}

// ARC MOD BEGIN
// Removed other __fxstat function definitions.
// ARC MOD END

// Copyright 2014 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.
//

#include <errno.h>
#include <unistd.h>

#include "bare_metal/common/irt_dev.h"
#include "bare_metal/common/irt_interfaces.h"

namespace {

int nacl_irt_getcwd(char* pathname, size_t len) {
  if (!getcwd(pathname, len))
    return errno;
  return 0;
}

int nacl_irt_unlink(const char* pathname) {
  int result = unlink(pathname);
  if (result)
    return errno;
  return 0;
}

extern "C" {
struct nacl_irt_dev_filename nacl_irt_dev_filename = {
  NULL,  // open
  NULL,  // stat
  NULL,  // mkdir
  NULL,  // rmdir
  NULL,  // chdir
  nacl_irt_getcwd,
  nacl_irt_unlink,
  NULL,  // truncate
  NULL,  // lstat
  NULL,  // link
  NULL,  // rename
  NULL,  // symlink
  NULL,  // chmod
  NULL,  // access
  NULL,  // readlink
  NULL,  // utimes
};
}

}  // namespace

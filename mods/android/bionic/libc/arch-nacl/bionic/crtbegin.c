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
//
// The start up routine of all binaries. This does some initialization
// and calls main using __libc_init. This should be linked into all
// executables.
//

#include <elf.h>

#include <irt_syscalls.h>

// For structors.
#include "../../bionic/libc_init_common.h"

// Include ctors and dtors, but ask it not to register _fini to
// atexit(). The _fini for the main executable is registered in
// libc_init_dynamic.
#define CRTBEGIN_FOR_EXEC
#include "crtbegin_so.c"

void exit(int status);

// Bionic ignores onexit, so this function must not be called.
static void onexit(void) {
  static const char msg[] = "onexit must not be called!\n";
  static const int kStderrFd = 2;
  write(kStderrFd, msg, sizeof(msg) - 1);
  exit(1);
}

static structor_fn fini_array[3];

__attribute__((visibility("hidden")))
void _start(unsigned **info) {
  structors_array_t structors;
  memset(&structors, 0, sizeof(structors));
  fini_array[0] = (structor_fn)-1;
  fini_array[1] = _fini;
  fini_array[2] = NULL;
  // Though Bionic will not use init_array, we will fill a sane value.
  // We do not have preinit_array.
  structors.init_array = (structor_fn *)__CTOR_LIST__;
  // We must not pass __DTOR_LIST__ as fini_array because they are not
  // compatible. fini_array will be called in reverse order but
  // __DTOR_LIST__ is called in normal order.
  structors.fini_array = fini_array;
  __libc_init(&info[2], onexit, main, &structors);
}

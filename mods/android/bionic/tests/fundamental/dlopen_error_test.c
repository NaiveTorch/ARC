/*
 * Copyright (C) 2014 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
//
// Checks if dlopen fails when there is a missing symbol.
//

#include <dlfcn.h>
#include <link.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_is_ok = 1;

void check_dlopen_fail(const char* filename) {
  dlerror();  // Reset the error string (if any).

  void* handle = dlopen(filename, RTLD_NOW);
  if (handle) {
    fprintf(stderr, "dlopen unnexpectedly succeeded!\n");
    dlclose(handle);
    exit(1);
  }

  const char* err = dlerror();
  if (!err) {
    fprintf(stderr, "dlerror() was not updated!\n");
    exit(1);
  }

  const char* expected_substr = "cannot locate symbol \"undefined_sym\"";
  if (strstr(err, expected_substr) == NULL) {
    fprintf(stderr, "%s is not in dlerror(): %s\n", expected_substr, err);
    exit(1);
  }

  fprintf(stderr, "dlopen(%s) failed properly\n", filename);
}

int iterate_phdr_callback(struct dl_phdr_info* info, size_t size, void* data) {
  fprintf(stderr, "name=%s size=%zu data=%p\n", info->dlpi_name, size, data);
  if (info->dlpi_name && strstr(info->dlpi_name, "undefined")) {
    g_is_ok = 0;
    fprintf(stderr, "%s is unexpectedly loaded\n", info->dlpi_name);
  }
  return 0;
}

int main() {
  check_dlopen_fail("libuse_undefined_sym.so");
  check_dlopen_fail("libuse_use_undefined_sym.so");

  // Make sure we did not load the shared objects above.
  dl_iterate_phdr(iterate_phdr_callback, NULL);
  if (!g_is_ok)
    return 1;

  fprintf(stderr, "PASS\n");
  return 0;
}

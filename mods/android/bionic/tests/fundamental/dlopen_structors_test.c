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
// Checks if .ctors and .dtors in a dlopen-ed shared object are called.
//

#include <dlfcn.h>
#include <stdio.h>

typedef void (*record_call_fn)(const char* name);
typedef void (*set_test_expectations_fn)(int expect_calls_num,
                                         const char** expect_calls);
typedef void (*register_test_finished_callback_fn)(void (*cb)(int));

int g_ok = -1;  // -1 means unfinished.

void set_ok(int ok) {
  g_ok = ok;
}

int main() {
  void* handle = dlopen("libstructors_test.so", RTLD_NOW);
  if (!handle) {
    fprintf(stderr, "dlopen failed!\n");
    return 1;
  }

  record_call_fn record_call = (record_call_fn)dlsym(handle, "record_call");
  set_test_expectations_fn set_test_expectations =
      (set_test_expectations_fn)dlsym(handle, "set_test_expectations");
  register_test_finished_callback_fn register_test_finished_callback =
      (register_test_finished_callback_fn)dlsym(
          handle, "register_test_finished_callback");

  register_test_finished_callback(&set_ok);
  record_call("main");

  static const char* expect_calls[] = {
    "init", "init2", "init3",
    "main",
    "fini3", "fini2", "fini",
  };
  set_test_expectations(sizeof(expect_calls) / sizeof(expect_calls[0]),
                        expect_calls);

  if (g_ok != -1) {
    fprintf(stderr, "Test finished too early\n");
    return 1;
  }

  dlclose(handle);

  // This test must finish in the dlclose() above.
  fprintf(stderr, "Test status: %d\n", g_ok);
  return g_ok != 1;
}

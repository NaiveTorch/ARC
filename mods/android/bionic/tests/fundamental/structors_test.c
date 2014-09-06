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
// Checks if .ctors, .dtors, and atexit are called.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t g_actual_calls_num;
static const char* g_actual_calls[99];
static size_t g_expect_calls_num;
static const char** g_expect_calls;
void (*g_test_finished_callback)(int ok);
static int g_call_exit_in_destructor;

void record_call(const char* name) {
  fprintf(stderr, "in %s()\n", name);
  g_actual_calls[g_actual_calls_num++] = name;

  if (!g_expect_calls || strcmp(name, g_expect_calls[g_expect_calls_num - 1]))
    return;

  int ok = 1;
  if (g_actual_calls_num != g_expect_calls_num) {
    fprintf(stderr, "Unexpected numbers of call: expected=%d actual=%d\n",
            g_expect_calls_num, g_actual_calls_num);
    ok = 0;
  }

  size_t i;
  for (i = 0; i < g_expect_calls_num; i++) {
    if (strcmp(g_actual_calls[i], g_expect_calls[i])) {
      fprintf(stderr, "Mismatched call at %d: expected=%s actual=%s\n",
              i, g_expect_calls[i], g_actual_calls[i]);
      ok = 0;
    }
  }

  if (g_test_finished_callback)
    g_test_finished_callback(ok);
  fprintf(stderr, "%s\n", ok ? "PASS" : "FAIL");
}

void register_test_finished_callback(void (*cb)(int ok)) {
  g_test_finished_callback = cb;
}

__attribute__((constructor(101)))
static void init() {
  record_call("init");
  g_call_exit_in_destructor = getenv("CALL_EXIT_IN_DESTRUCTOR") != NULL;
}

__attribute__((constructor(102)))
static void init2() {
  record_call("init2");
}

__attribute__((constructor))
static void init3() {
  record_call("init3");
}

__attribute__((destructor(101)))
static void fini() {
  record_call("fini");
}

__attribute__((destructor(102)))
static void fini2() {
  record_call("fini2");
  if (g_call_exit_in_destructor) {
    fprintf(stderr, "call exit() in fini2().\n");
    exit(0);
  }
}

__attribute__((destructor))
static void fini3() {
  record_call("fini3");
}

void atexit_func() {
  record_call("atexit_func");
}

void atexit_func2() {
  record_call("atexit_func2");
}

void set_test_expectations(size_t expect_calls_num,
                           const char** expect_calls) {
  if (expect_calls_num > sizeof(g_actual_calls) / sizeof(g_actual_calls[0])) {
    fprintf(stderr, "Too many expect_calls\n");
    abort();
  }

  g_expect_calls_num = expect_calls_num;
  g_expect_calls = expect_calls;
}

#if !defined(FOR_SHARED_OBJECT)
int main() {
  record_call("main");

  atexit(atexit_func);
  atexit(atexit_func2);

  static const char* expect_calls[] = {
    "init", "init2", "init3",
    "main",
    "atexit_func2", "atexit_func",
    // TODO(crbug.com/404987): Support fini_array for Bare Metal mode.
#if defined(__native_client__)
    "fini3", "fini2", "fini",
#endif
  };
  set_test_expectations(sizeof(expect_calls) / sizeof(expect_calls[0]),
                        expect_calls);
  return 0;
}
#endif

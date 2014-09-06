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
// Checks if .ctors and .dtors in a DT_NEED-ed shared object are called.
//

#include <stdio.h>
#include <stdlib.h>

void atexit_func();
void atexit_func2();
void record_call(const char* name);
void set_test_expectations(int expect_calls_num, const char** expect_calls);

int main() {
  record_call("main");

  atexit(atexit_func);
  atexit(atexit_func2);

  static const char* expect_calls[] = {
    "init", "init2", "init3",
    "main",
    "atexit_func2", "atexit_func",
    // It seems upstream Bionic does not call destructor functions for
    // DT_NEEDED shared object as well. See
    // third_party/android/bionic/libc/arch-arm/bionic/crtbegin_so.c.
#if !defined(__arm__) && defined(__native_client__)
    // TODO(yusukes): At this point, destructors in DT_NEEDED objects are not
    // properly called upon exit. We should fix this.
    // "fini3", "fini2", "fini",
#endif
  };
  set_test_expectations(sizeof(expect_calls) / sizeof(expect_calls[0]),
                        expect_calls);
  return 0;
}

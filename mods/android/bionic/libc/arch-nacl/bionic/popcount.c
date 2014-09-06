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
// Defines __popcountsi2 for x86-64.
// TODO(crbug.com/283798): Build libgcc ourselves and remove this file.
//

#if defined(__x86_64__)
#include <stdint.h>

// __popcountsi2 is not available in nacl_x86_64/libgcc_s.so.1,
// but some code in Android uses it.
int __popcountdi2(int64_t value);

int __popcountsi2(int value) {
  // Counting 1-bits through 64-bit function is somewhat slower
  // but should still work.
  return __popcountdi2(value);
}
#endif

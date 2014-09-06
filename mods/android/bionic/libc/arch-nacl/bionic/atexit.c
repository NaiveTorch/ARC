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
// Define atexit using __cxa_atexit.
//

#if !defined(__arm__)

#include <stdlib.h>

extern void *__dso_handle __attribute__((weak));

int atexit(void (*function)(void)) {
  return __cxa_atexit((void (*)(void *))function, NULL  /* arg */,
                      __dso_handle);
}

#endif

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

#include <sys/types.h>

pid_t getpid() {
  // Returning -1 with an errno like ENOSYS is not POSIX compliant. It requires
  // getpid to always succeed, but we do not have a way to obtain host's real
  // pid (see https://code.google.com/p/nativeclient/issues/detail?id=537).
  // The best we can do is just to return an arbitrary chosen positive number.
  return 42;
}

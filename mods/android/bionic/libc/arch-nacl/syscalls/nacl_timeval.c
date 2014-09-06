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

#include "nacl_timeval.h"

void __nacl_abi_timeval_to_timeval(
    const struct nacl_abi_timeval *nacl_timeval,
    struct timeval *timeval) {
  timeval->tv_sec = nacl_timeval->tv_sec;
  timeval->tv_usec = nacl_timeval->tv_usec;
}

void __timeval_to_nacl_abi_timeval(const struct timeval *timeval,
                                   struct nacl_abi_timeval *nacl_timeval) {
  nacl_timeval->tv_sec = timeval->tv_sec;
  nacl_timeval->tv_usec = timeval->tv_usec;
}

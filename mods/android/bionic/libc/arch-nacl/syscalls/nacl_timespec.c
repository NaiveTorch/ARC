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

#include "nacl_timespec.h"

void __nacl_abi_timespec_to_timespec(
    const struct nacl_abi_timespec *nacl_timespec,
    struct timespec *timespec) {
  timespec->tv_sec = nacl_timespec->tv_sec;
  timespec->tv_nsec = nacl_timespec->tv_nsec;
}

void __timespec_to_nacl_abi_timespec(const struct timespec *timespec,
                                     struct nacl_abi_timespec *nacl_timespec) {
  nacl_timespec->tv_sec = timespec->tv_sec;
  nacl_timespec->tv_nsec = timespec->tv_nsec;
}

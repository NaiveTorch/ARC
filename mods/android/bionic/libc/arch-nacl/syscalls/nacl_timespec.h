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
// Define nacl_abi_timespec and its conversion functions.
//
// Note that nacl-glibc's timespec is as same as NaCl IRT's. In
// bionic, time_t is a 32bit value so we need conversion.
//

#ifndef _NACL_TIMESPEC_H
#define _NACL_TIMESPEC_H

#include <stdint.h>
#include <sys/cdefs.h>
#include <time.h>

__BEGIN_DECLS

struct nacl_abi_timespec {
  int64_t tv_sec;
  int64_t tv_nsec;
};

void __nacl_abi_timespec_to_timespec(
    const struct nacl_abi_timespec *nacl_timespec,
    struct timespec *timespec);

void __timespec_to_nacl_abi_timespec(const struct timespec *timespec,
                                     struct nacl_abi_timespec *nacl_timespec);

__END_DECLS

#endif  // _NACL_TIMESPEC_H

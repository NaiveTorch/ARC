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
// Stub definitions for undefined functions.
//
// TODO(crbug.com/243244): Remove this file once bionic becomes ready.
//

#define DEFINE_STUB(name)                       \
  int name() {                                  \
    print_str("*** " #name " is called ***\n"); \
    return 0;                                   \
  }

DEFINE_STUB(__bionic_clone)
DEFINE_STUB(__cxa_bad_typeid)
DEFINE_STUB(__fstatfs64)
DEFINE_STUB(__getcpu)
DEFINE_STUB(__getpriority)
DEFINE_STUB(__openat)
DEFINE_STUB(__reboot)
DEFINE_STUB(__rt_sigtimedwait)
DEFINE_STUB(__sched_getaffinity)
DEFINE_STUB(__setresuid)
DEFINE_STUB(__setreuid)
DEFINE_STUB(__setuid)
DEFINE_STUB(__statfs64)
DEFINE_STUB(__timer_create)
DEFINE_STUB(__timer_delete)
DEFINE_STUB(__timer_getoverrun)
DEFINE_STUB(__timer_gettime)
DEFINE_STUB(__timer_settime)
DEFINE_STUB(__waitid)
DEFINE_STUB(futex)
DEFINE_STUB(futimes)
DEFINE_STUB(getdents)
DEFINE_STUB(getxattr)
DEFINE_STUB(mknod)
DEFINE_STUB(pipe2)
DEFINE_STUB(poll)
DEFINE_STUB(pread64)
DEFINE_STUB(pwrite64)
DEFINE_STUB(signalfd4)
DEFINE_STUB(socketpair)
DEFINE_STUB(times)
DEFINE_STUB(utimensat)
DEFINE_STUB(wait4)

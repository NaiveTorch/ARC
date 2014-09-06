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

#include <errno.h>
#include <time.h>

// clock_nanosleep is not available in NaCl IRT, so we define
// clock_nanosleep() by ourselves.
int clock_nanosleep(clockid_t clock_id, int flags,
                    const struct timespec *request,
                    struct timespec *remain) {
    if (request->tv_sec < 0 ||
        request->tv_nsec < 0 || request->tv_nsec > 999999999) {
        return -EINVAL;
    }

    if (flags != TIMER_ABSTIME) {
        return nanosleep(request, remain);
    }

    struct timespec now;
    int ret = clock_gettime(clock_id, &now);
    if (ret == -1) {
        return -errno;
    }

    struct timespec to_sleep = *request;
    to_sleep.tv_sec -= now.tv_sec;
    to_sleep.tv_nsec -= now.tv_nsec;

    if (to_sleep.tv_nsec < 0) {
        to_sleep.tv_sec--;
        to_sleep.tv_nsec += 1000000000;
    }

    if (to_sleep.tv_sec < 0) {
        to_sleep.tv_sec = 0;
        to_sleep.tv_nsec = 0;
    }

    return nanosleep(&to_sleep, NULL);
}

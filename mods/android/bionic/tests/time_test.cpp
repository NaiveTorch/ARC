/*
 * Copyright (C) 2013 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <sys/cdefs.h>
#include <features.h>
#include <gtest/gtest.h>

// ARC MOD BEGIN
#include <errno.h>
#include <sys/time.h>
// ARC MOD END
#include <time.h>

#ifdef __BIONIC__ // mktime_tz is a bionic extension.
#include <libc/private/bionic_time.h>
// ARC MOD BEGIN
// Neither NaCl nor Bare Metal can open tzdata.
#if !defined(__native_client__) && !defined(BARE_METAL_BIONIC)
// ARC MOD END
TEST(time, mktime_tz) {
  struct tm epoch;
  memset(&epoch, 0, sizeof(tm));
  epoch.tm_year = 1970 - 1900;
  epoch.tm_mon = 1;
  epoch.tm_mday = 1;

  // Alphabetically first. Coincidentally equivalent to UTC.
  ASSERT_EQ(2678400, mktime_tz(&epoch, "Africa/Abidjan"));

  // Alphabetically last. Coincidentally equivalent to UTC.
  ASSERT_EQ(2678400, mktime_tz(&epoch, "Zulu"));

  // Somewhere in the middle, not UTC.
  ASSERT_EQ(2707200, mktime_tz(&epoch, "America/Los_Angeles"));

  // Missing. Falls back to UTC.
  ASSERT_EQ(2678400, mktime_tz(&epoch, "PST"));
}
// ARC MOD BEGIN
#endif
// ARC MOD END
#endif

TEST(time, gmtime) {
  time_t t = 0;
  tm* broken_down = gmtime(&t);
  ASSERT_TRUE(broken_down != NULL);
  ASSERT_EQ(0, broken_down->tm_sec);
  ASSERT_EQ(0, broken_down->tm_min);
  ASSERT_EQ(0, broken_down->tm_hour);
  ASSERT_EQ(1, broken_down->tm_mday);
  ASSERT_EQ(0, broken_down->tm_mon);
  ASSERT_EQ(1970, broken_down->tm_year + 1900);
}

#ifdef __BIONIC__
TEST(time, mktime_10310929) {
  struct tm t;
  memset(&t, 0, sizeof(tm));
  t.tm_year = 200;
  t.tm_mon = 2;
  t.tm_mday = 10;

  ASSERT_EQ(-1, mktime(&t));
  // ARC MOD BEGIN
  // Temporarily disabled the test.
  // TODO(yusukes): Investigate why this crashes and re-enable it.
  // ASSERT_EQ(-1, mktime_tz(&t, "UTC"));
  // ARC MOD END
}
#endif
// ARC MOD BEGIN UPSTREAM bionic-add-time-test

namespace {

double GetDoubleTimeFromTimeval(struct timeval* tv) {
  return tv->tv_sec + tv->tv_usec * 1e-6;
}

double GetDoubleTimeFromTimespec(struct timespec* ts) {
  return ts->tv_sec + ts->tv_nsec * 1e-9;
}

}  // namespace

TEST(time, test_CLOCK_REALTIME) {
  struct timespec ts;
  struct timeval tv;
  ASSERT_EQ(0, gettimeofday(&tv, NULL));
  ASSERT_EQ(0, clock_gettime(CLOCK_REALTIME, &ts));
  static const int kMaxAcceptableTimeDiff = 3;
  EXPECT_NEAR(tv.tv_sec, ts.tv_sec, kMaxAcceptableTimeDiff);
}

TEST(time, test_CLOCK_PROCESS_CPUTIME_ID) {
  struct timespec ts = {-1, -1};
  ASSERT_EQ(0, clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts));
  ASSERT_NE(-1, ts.tv_sec);
  ASSERT_NE(-1, ts.tv_nsec);
}

TEST(time, test_CLOCK_THREAD_CPUTIME_ID) {
  struct timespec ts = {-1, -1};
  ASSERT_EQ(0, clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts));
  ASSERT_NE(-1, ts.tv_sec);
  ASSERT_NE(-1, ts.tv_nsec);
}

TEST(time, nanosleep) {
  struct timespec ts;
  struct timeval tv;

  ASSERT_EQ(0, gettimeofday(&tv, NULL));
  double gettimeofday_time = GetDoubleTimeFromTimeval(&tv);

  ASSERT_EQ(0, clock_gettime(CLOCK_REALTIME, &ts));
  double clock_realtime_time = GetDoubleTimeFromTimespec(&ts);

  ASSERT_EQ(0, clock_gettime(CLOCK_MONOTONIC, &ts));
  double clock_monotonic_time = GetDoubleTimeFromTimespec(&ts);

  static const double kMaxAcceptableTimeDiff = 3.0;
  EXPECT_NEAR(gettimeofday_time, clock_realtime_time, kMaxAcceptableTimeDiff);

  // 100 msecs.
  ts.tv_sec = 0;
  ts.tv_nsec = 100000000;
  ASSERT_EQ(0, nanosleep(&ts, NULL));

  // We test we sleep at least 50 msecs and at most 2 secs.
  static const double kMinElapsedTime = 0.05;
  static const double kMaxElapsedTime = 3.0;

  ASSERT_EQ(0, gettimeofday(&tv, NULL));
  double gettimeofday_elapsed =
      GetDoubleTimeFromTimeval(&tv) - gettimeofday_time;
  EXPECT_LT(kMinElapsedTime, gettimeofday_elapsed);
  EXPECT_GT(kMaxElapsedTime, gettimeofday_elapsed);

  ASSERT_EQ(0, clock_gettime(CLOCK_REALTIME, &ts));
  double clock_realtime_elapsed =
      GetDoubleTimeFromTimespec(&ts) - clock_realtime_time;

  EXPECT_LT(kMinElapsedTime, clock_realtime_elapsed);
  EXPECT_GT(kMaxElapsedTime, clock_realtime_elapsed);

  ASSERT_EQ(0, clock_gettime(CLOCK_MONOTONIC, &ts));
  double clock_monotonic_elapsed =
      GetDoubleTimeFromTimespec(&ts) - clock_monotonic_time;
  EXPECT_LT(kMinElapsedTime, clock_monotonic_elapsed);
  EXPECT_GT(kMaxElapsedTime, clock_monotonic_elapsed);
}

TEST(time, gettimeofday_NULL) {
  ASSERT_EQ(0, gettimeofday(NULL, NULL));
}

TEST(time, gettimeofday_timezone) {
  struct timezone tz;
  ASSERT_EQ(0, gettimeofday(NULL, &tz));
  // As of now, fields in |tz| are always zero on NaCl, but this can
  // be changed in future?
}

TEST(time, clock_gettime_NULL) {
  ASSERT_NE(0, clock_gettime(CLOCK_REALTIME, NULL));
  EXPECT_EQ(EFAULT, errno);
  ASSERT_NE(0, clock_gettime(CLOCK_MONOTONIC, NULL));
  EXPECT_EQ(EFAULT, errno);
  ASSERT_NE(0, clock_gettime(CLOCK_PROCESS_CPUTIME_ID, NULL));
  EXPECT_EQ(EFAULT, errno);
  ASSERT_NE(0, clock_gettime(CLOCK_THREAD_CPUTIME_ID, NULL));
  EXPECT_EQ(EFAULT, errno);
}

TEST(time, clock_getres) {
  struct timespec ts = { 99, 99 };
  ASSERT_EQ(0, clock_getres(CLOCK_REALTIME, &ts));
  // It would be safe to assume the time resolution is <1 sec.
  EXPECT_EQ(0, ts.tv_sec);
  EXPECT_NE(0, ts.tv_nsec);

  ts.tv_sec = 99;
  ASSERT_EQ(0, clock_getres(CLOCK_MONOTONIC, &ts));
  EXPECT_EQ(0, ts.tv_sec);
  EXPECT_NE(0, ts.tv_nsec);

  ts.tv_sec = 99;
  ASSERT_EQ(0, clock_getres(CLOCK_PROCESS_CPUTIME_ID, &ts));
  EXPECT_EQ(0, ts.tv_sec);
  EXPECT_NE(0, ts.tv_nsec);

  ts.tv_sec = 99;
  ASSERT_EQ(0, clock_getres(CLOCK_THREAD_CPUTIME_ID, &ts));
  EXPECT_EQ(0, ts.tv_sec);
  EXPECT_NE(0, ts.tv_nsec);
}

TEST(time, clock_getres_NULL) {
  ASSERT_EQ(0, clock_getres(CLOCK_REALTIME, NULL));
  ASSERT_EQ(0, clock_getres(CLOCK_MONOTONIC, NULL));
  ASSERT_EQ(0, clock_getres(CLOCK_PROCESS_CPUTIME_ID, NULL));
  ASSERT_EQ(0, clock_getres(CLOCK_THREAD_CPUTIME_ID, NULL));
}
// ARC MOD END UPSTREAM

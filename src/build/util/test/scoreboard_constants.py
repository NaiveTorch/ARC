# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# An enumeration of the different states a single test or suite can be in at
# any given moment.
INCOMPLETE = 0  # Any test is expected to be run eventually is initially marked
                # as INCOMPLETE and remains so until it is either run or the
                # scoreboard is finalized.
SKIPPED = 1  # INCOMPLETE tests get marked as SKIPPED once the scoreboard is
             # finalized since they were never actually run.
EXPECT_PASS = 2  # The test/suite passed as expected.
EXPECT_FAIL = 3  # The test/suite failed as expected.
UNEXPECT_PASS = 4  # The test/suite marked for failure passed unexpectedly.
UNEXPECT_FAIL = 5  # The test/suite marked for pass failed unexpectedly.
FLAKE = 6  # The test is expected to be flaky.  Any flaky tests that fail will
           # not be considered as failing until the Scoreboard is finalized.
           # This gives the SuiteRunner a chance to rerun the flaky tests.
           # Passing tests will be marked as EXPECT_PASS as soon as they pass.

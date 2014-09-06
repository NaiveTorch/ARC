#!/usr/bin/env python

# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from util.test.atf_instrumentation_result_parser \
    import ATFInstrumentationResultParser


class InstrumentationStatusMessageFilterTests(unittest.TestCase):
  def _process(self, text):
    results = ATFInstrumentationResultParser()
    ignored = []
    for line in text.splitlines():
      if not results.process_line(line):
        ignored.append(line)
    return results, ignored

  def test_with_irrelevant_input(self):
    text = 'able was I\nere\nI saw elba'
    result, ignored = self._process(text)
    self.assertEquals(text.split('\n'), ignored)
    self.assertFalse(result.output_recognized)
    self.assertFalse(result.run_completed_cleanly)

  def test_complete_run(self):
    result, ignored = self._process("""This should be ignored #1
INSTRUMENTATION_STATUS: current=5
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
INSTRUMENTATION_STATUS: stream=
INSTRUMENTATION_STATUS: numtests=100
INSTRUMENTATION_STATUS: test=testDelta
INSTRUMENTATION_STATUS_CODE: 1
This should be ignored #2
INSTRUMENTATION_STATUS: current=5
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
This should be ignored #3
INSTRUMENTATION_STATUS: stream=.Echo Foxtrot!
Golf Hotel!
INSTRUMENTATION_STATUS: numtests=100
This should be ignored #4
INSTRUMENTATION_STATUS: test=testDelta
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_STATUS: current=5
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
INSTRUMENTATION_STATUS: stream=
INSTRUMENTATION_STATUS: numtests=100
INSTRUMENTATION_STATUS: test=testIndia
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: current=6
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
INSTRUMENTATION_STATUS: stream=.
INSTRUMENTATION_STATUS: numtests=100
INSTRUMENTATION_STATUS: test=testIndia
INSTRUMENTATION_STATUS_CODE: -1
INSTRUMENTATION_STATUS: current=7
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
INSTRUMENTATION_STATUS: stream=
INSTRUMENTATION_STATUS: numtests=100
INSTRUMENTATION_STATUS: test=testJuliet
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_RESULT: stream=Yankee
Zulu
INSTRUMENTATION_CODE: -1
This should be ignored #5
""")
    self.assertEquals(['This should be ignored #%d' % n for n in xrange(1, 6)],
                      ignored)
    self.assertTrue(result.output_recognized)
    self.assertTrue(result.run_completed_cleanly)
    self.assertEquals('Yankee\nZulu', result.run_message)
    self.assertTrue(result.run_passed_cleanly)
    self.assertEquals(100, result.test_methods_total)
    self.assertEquals(1, result.test_methods_passed)
    self.assertEquals(1, result.test_methods_failed)

    self.assertEquals(3, len(result.test_method_results))

    testResult = result.test_method_results['alpha.bravo.charlie#testDelta']
    self.assertTrue(testResult.passed)
    self.assertFalse(testResult.failed)
    self.assertFalse(testResult.incomplete)
    self.assertEquals('.Echo Foxtrot!\nGolf Hotel!', testResult.message)

    testResult = result.test_method_results['alpha.bravo.charlie#testIndia']
    self.assertFalse(testResult.passed)
    self.assertTrue(testResult.failed)
    self.assertFalse(testResult.incomplete)
    self.assertEquals('.', testResult.message)
    self.assertNotEquals(testResult, result.get_latest_result())

    testResult = result.test_method_results['alpha.bravo.charlie#testJuliet']
    self.assertFalse(testResult.passed)
    self.assertFalse(testResult.failed)
    self.assertTrue(testResult.incomplete)
    self.assertEquals('', testResult.message)
    self.assertEquals(testResult, result.get_latest_result())

  def test_incomplete_run(self):
    result, ignored = self._process("""
INSTRUMENTATION_STATUS: current=5
INSTRUMENTATION_STATUS: id=InstrumentationTestRunner
INSTRUMENTATION_STATUS: class=alpha.bravo.charlie
INSTRUMENTATION_STATUS: stream=
INSTRUMENTATION_STATUS: numtests=100
INSTRUMENTATION_STATUS: test=testDelta
INSTRUMENTATION_STATUS_CODE: 1
""")
    self.assertTrue(result.output_recognized)
    self.assertFalse(result.run_completed_cleanly)

    testResult = result.test_method_results['alpha.bravo.charlie#testDelta']
    self.assertFalse(testResult.passed)
    self.assertFalse(testResult.failed)
    self.assertTrue(testResult.incomplete)
    self.assertEquals('', testResult.message)

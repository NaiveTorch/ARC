#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Tests for stat_util."""

import math
import unittest

from util import statistics


class TestStatUtil(unittest.TestCase):
  def test_compute_average(self):
    self.assertTrue(math.isnan(statistics.compute_average([])))
    self.assertEquals(42, statistics.compute_average([42]))
    self.assertEquals(6.5, statistics.compute_average([5, 8]))
    self.assertEquals(4, statistics.compute_average([2, 3, 7]))

  def test_compute_median(self):
    self.assertTrue(math.isnan(statistics.compute_median([])))
    self.assertEquals(42, statistics.compute_median([42]))
    self.assertEquals(6.5, statistics.compute_median([5, 8]))
    self.assertEquals(3, statistics.compute_median([2, 3, 7]))

  def test_compute_percentiles(self):
    self.assertTrue(all(map(math.isnan, statistics.compute_percentiles([]))))
    self.assertEquals(statistics.compute_median([5, 8]),
                      statistics.compute_percentiles([5, 8], [50])[0])
    self.assertEquals(statistics.compute_median([2, 3, 7]),
                      statistics.compute_percentiles([2, 3, 7], [50])[0])
    # All expected values below agree with Google Docs.
    self.assertEquals((42, 42), statistics.compute_percentiles([42]))
    self.assertEquals((6.5, 7.7), statistics.compute_percentiles([5, 8]))
    self.assertEquals((3, 6.2), statistics.compute_percentiles([2, 3, 7]))
    self.assertEquals((5, 8.4), statistics.compute_percentiles([2, 3, 7, 9]))
    self.assertEquals((7, 63.6),
                      statistics.compute_percentiles([2, 3, 7, 9, 100]))
    self.assertEquals((39.5, 43.4),
                      statistics.compute_percentiles([6, 7, 15, 36, 39, 40,
                                                      41, 42, 43, 47]))
    self.assertEquals((40.0, 47.0),
                      statistics.compute_percentiles([6, 7, 15, 36, 39, 40,
                                                      41, 42, 43, 47, 49]))
    self.assertEquals((37.5, 40.5),
                      statistics.compute_percentiles([7, 15, 36, 39, 40, 41]))
    self.assertEquals((39, 42.2),
                      statistics.compute_percentiles([6, 7, 15, 36, 39, 40,
                                                      41, 42, 43]))


if __name__ == '__main__':
  unittest.main()

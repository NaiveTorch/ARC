#!/usr/bin/python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility functions which compute statistical values."""


def compute_average(values):
  if not values:
    return float('NaN')
  return float(sum(values)) / len(values)


def compute_median(values):
  values = sorted(values)
  n = len(values)
  if not n:
    return float('NaN')
  if n % 2 == 0:
    return (values[n / 2 - 1] + values[n / 2]) * 0.5
  else:
    return values[n / 2]


def compute_percentiles(values, percentiles=(50, 90)):
  """Returns the percentiles as a tuple which has as many elements as the
  percentiles array."""
  values = sorted(values)
  n = len(values)
  if n <= 1:
    v = values[0] if values else float('NaN')
    return (v,) * len(percentiles)
  # We use a generalized version of "method 3" from
  # http://en.wikipedia.org/wiki/Quartile.
  d = []
  for p in percentiles:
    if p <= 0:
      d.append(values[0])
    elif p >= 100:
      d.append(values[-1])
    else:
      idx = int(p * (n - 1) / 100)
      w = p * (n - 1) % 100
      d.append(((100 - w) * values[idx] +
                w * values[idx + 1]) / 100.0)
  return tuple(d)

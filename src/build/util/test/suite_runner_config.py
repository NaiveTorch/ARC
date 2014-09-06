# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import collections
import copy
import re

from build_options import OPTIONS
from util import platform_util
from util.test.suite_runner_config_flags import ExclusiveFlagSet
from util.test.suite_runner_config_flags import FLAKY
from util.test.suite_runner_config_flags import PASS


DEFAULT_OUTPUT_TIMEOUT = 300

# For use in the suite configuration files, to identify a default configuration
# to use for a list of related suites.
SUITE_DEFAULTS = 'SUITE-DEFAULTS'


class _SuiteRunConfiguration(object):
  _BUG_PATTERN = re.compile(r'crbug.com/\d+$')

  def __init__(self, name, config=None):
    self._name = name
    self._config = config if config else {}

  def validate(self):
    validators = dict(
        flags=self._validate_flags,
        deadline=self._validate_deadline,
        bug=self._validate_bug,
        configurations=self._validate_configurations,
        suite_test_expectations=self._validate_suite_test_expectations,
        metadata=self._validate_metadata)

    for key, value in self._config.iteritems():
      validators[key](value)

    return self

  def _validate_flags(self, value):
    assert isinstance(value, ExclusiveFlagSet), (
        'Not a recognized flag: %s' % value)

  def _validate_deadline(self, value):
    assert isinstance(value, int) and int > 0, (
        'Not a valid integer: %s' % value)

  def _validate_bug(self, value):
    for bug_url in value.split(','):
      assert self._BUG_PATTERN.match(bug_url.strip()), (
          'Not a valid bug url (crbug.com/NNNNNN): %s' % bug_url)

  def _validate_configurations(self, configuration_list):
    if configuration_list is None:
      return
    assert isinstance(configuration_list, list), (
        'configurations is not a list')
    for configuration in configuration_list:
      self._validate_configuration(configuration)

  def _validate_suite_test_expectations(self, class_config_dict):
    if class_config_dict is None:
      return
    assert isinstance(class_config_dict, dict), (
        'suite_test_expectations is not a dictionary')
    for outer_name, outer_expectation in class_config_dict.iteritems():
      assert isinstance(outer_name, basestring), (
          'suite_test_expectations %s is not a string' % outer_name)
      if isinstance(outer_expectation, ExclusiveFlagSet):
        pass  # Not much more to validate.
      elif isinstance(outer_expectation, dict):
        for inner_name, inner_expectation in outer_expectation.iteritems():
          assert isinstance(inner_name, basestring), (
              'suite_test_expectations %s.%s is not a string' % (
                  outer_name, outer_expectation))
          assert isinstance(inner_expectation, ExclusiveFlagSet), (
              'suite_test_expectations %s.%s is not an expectation flag '
              'combination' % (outer_name, inner_name, inner_expectation))
      else:
        assert False, (
            'suite_test_expectations %s needs to be a dictionary or an '
            'expectation flag combination' % outer_name)

  def _validate_enable_if(self, value):
    assert isinstance(value, bool), (
        'configuration enable_if is not a boolean')

  def _validate_metadata(self, value):
    if value is None:
      return
    assert isinstance(value, dict), (
        'metadata is not a dictionary')

  def _validate_test_order(self, value):
    assert isinstance(value, collections.OrderedDict), (
        'test_order is not a collections.OrderedDict')
    for k, v in value.iteritems():
      assert isinstance(k, basestring), (
          '"%s" is not a string.' % k)
      unused = int(v)  # Ensure conversion  # NOQA

  def _validate_configuration(self, config_dict):
    assert isinstance(config_dict, dict), (
        'configuration is not a dictionary')

    validators = dict(
        bug=self._validate_bug,
        deadline=self._validate_deadline,
        enable_if=self._validate_enable_if,
        flags=self._validate_flags,
        test_order=self._validate_test_order,
        suite_test_expectations=self._validate_suite_test_expectations)

    for key, value in config_dict.iteritems():
      validators[key](value)

  def evaluate(self, defaults=None):
    # TODO(lpique): Combine validation and evaluation. We only need to walk
    # through the data once.
    self.validate()

    output = dict(bug=None, deadline=DEFAULT_OUTPUT_TIMEOUT,
                  flags=PASS, test_order=collections.OrderedDict(),
                  suite_test_expectations={})
    if defaults:
      # We need to make a deep copy so that we do not modify any dictionary or
      # array data in place and affect the default values for subsequent use.
      output.update(copy.deepcopy(defaults))

    evaluators = dict(
        flags=self._eval_flags,
        deadline=self._eval_deadline,
        bug=self._eval_bug,
        configurations=self._eval_configurations,
        suite_test_expectations=self._eval_suite_test_expectations,
        metadata=self._eval_metadata)

    for key, value in self._config.iteritems():
      evaluators[key](output, value)

    return output

  def _eval_flags(self, output, value):
    output['flags'] |= value

  def _eval_deadline(self, output, value):
    output['deadline'] = value

  def _eval_bug(self, output, value):
    output['bug'] = value

  def _eval_suite_test_expectations(self, output, config_dict):
    expectations = output['suite_test_expectations']
    for outer_name, outer_expectation in config_dict.iteritems():
      if isinstance(outer_expectation, dict):
        for inner_name, inner_expectation in outer_expectation.iteritems():
          test_name = '%s#%s' % (outer_name, inner_name)
          expectations[test_name] = PASS | inner_expectation
      else:
        expectations[outer_name] = PASS | outer_expectation

  def _eval_enable_if(self, output, value):
    # We don't expect this configuration section to be evaluated at all unless
    # it has already been evaluated as enabled!
    assert value

  def _eval_metadata(self, output, value):
    output['metadata'] = value

  def _eval_test_order(self, output, value):
    test_order = output['test_order']
    for k, v in value.iteritems():
      test_order[k] = v

  def _eval_configurations(self, output, configuration_list):
    if configuration_list is None:
      return

    evaluators = dict(
        bug=self._eval_bug,
        deadline=self._eval_deadline,
        enable_if=self._eval_enable_if,
        flags=self._eval_flags,
        test_order=self._eval_test_order,
        suite_test_expectations=self._eval_suite_test_expectations)

    for configuration in configuration_list:
      if configuration.get('enable_if', True):
        for key, value in configuration.iteritems():
          evaluators[key](output, value)

  _eval_config_expected_failing_tests = _eval_suite_test_expectations
  _eval_config_flags = _eval_flags
  _eval_config_bug = _eval_bug
  _eval_config_deadline = _eval_deadline


default_run_configuration = lambda: _SuiteRunConfiguration(None, config={
    'flags': PASS,
    'suite_test_expectations': {},
    'deadline': 300,  # Seconds
    'configurations': [{
        'enable_if': OPTIONS.weird(),
        'flags': FLAKY,
    }, {
        'enable_if': platform_util.is_running_on_cygwin(),
        'bug': 'crbug.com/361474',
        'flags': FLAKY,
    }],
    'metadata': {}
}).evaluate()


def make_suite_run_configs(raw_config):
  def _deferred():
    global_defaults = default_run_configuration()
    raw_config_dict = raw_config()

    # Locate the defaults up front so they can be used to initialize
    # everything else.
    defaults = raw_config_dict.get(SUITE_DEFAULTS)
    if defaults is not None:
      del raw_config_dict[SUITE_DEFAULTS]
      defaults = _SuiteRunConfiguration(
          None, config=defaults).evaluate(defaults=global_defaults)
    else:
      defaults = global_defaults

    # Evaluate the runner configuration of everything we might want to run.
    configs = {}
    for package_name, package_config in raw_config_dict.iteritems():
      configs[package_name] = _SuiteRunConfiguration(
          package_name, config=package_config).evaluate(defaults=defaults)
    return configs

  return _deferred  # Defer to pick up runtime configuration options properly.

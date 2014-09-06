#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Unit tests of filtered_subprocess."""

import os
import unittest

from filtered_subprocess import Popen


class SimpleOutputHandler(object):
  """Simple ouput handler type with functionality useful for tests.

  Buffers all output (stdout and stderr) send to it by
  filtered_subprocess.Popen, and can terminate the process early.
  """

  def __init__(self, done=False):
    """Constructor.

    If done is set to True, this handler will signal that it is done
    immediately.
    """

    self.stdout = ''
    self.stderr = ''
    self.timeout = False
    self._done = done

  def is_done(self):
    """Invoked to check if the process is done and should be terminated."""
    return self._done or self.timeout

  def handle_stdout(self, text):
    """Invoked to handle output written to stdout."""
    self.stdout += text

  def handle_stderr(self, text):
    """Invoked to handle output written to stderr."""
    self.stderr += text

  def handle_timeout(self):
    """Invoked to notify the handler that the child has timed-out."""
    self.timeout = True


class FilteredSubprocessFake(Popen):
  """Fakes out the normal behavior of the filtered_subprocess.Popen class.

  No actual child process is created, but pipes for holding fake output_handler
  are, along with methods to control what goes in them.

  Also tracks some state for tracking if the process was terminated or not.
  """

  def __init__(self, ignore_terminate=False, ignore_kill=False,
               output_on_terminate=None):
    """Overriding Constructor.

    Allows the filtered_subprocess.Popen instance to be created with correct
    initial state, without actually creating a subprocess.

    If ignore_terminate is True, this fake will be configured to ignore the
    terminate() call, simulating a subprocess that ignores the SIGTERM signal.

    If ignore_kill is True, this fake will be configured to ignore the kill()
    call, simulating a subprocess that ignores the SIGKILL signal.

    If output_on_terminate is set to a string, that string will be written to
    the stdout pipe as if the subprocess were doing so as part of flushing its
    buffers when responding to the SIGTERM signal.
    """

    self.stdout, self._stdout_write = self._make_pipes()
    self.stderr, self._stderr_write = self._make_pipes()
    self.pid = -1
    self._ignore_terminate = ignore_terminate
    self._ignore_kill = ignore_kill
    self._output_on_sigterm = output_on_terminate

    self.was_terminated = False
    self.was_killed = False

    self._initialize_state()

  def _make_pipes(self):
    read, write = os.pipe()
    return os.fdopen(read, 'r'), os.fdopen(write, 'w', 0)

  def close_child_end_of_pipes(self):
    if not self._stdout_write.closed:
      self._stdout_write.close()
    if not self._stderr_write.closed:
      self._stderr_write.close()

  def __enter__(self):
    return self

  def __exit__(self, type, value, traceback):
    self.close_child_end_of_pipes()
    return False

  def write_stdout(self, text, close=False):
    """Writes text to the stdout pipe as if the child had written it."""
    self._stdout_write.write(text)

  def write_stderr(self, text, close=False):
    """Writes text to the stderr pipe as if the child had written it."""
    self._stderr_write.write(text)

  def poll(self):
    """Overrides the default poll() method."""
    return None

  def wait(self):
    """Overrides the default wait() method."""
    return None

  def terminate(self):
    """Overrides the default terminate() method.

    Allows the behavior to be faked, while still having the filtered_subprocess
    update its internal state.
    """
    self.was_terminated = True

    if self._output_on_sigterm:
      self._stdout_write.write(self._output_on_sigterm)

    if not self._ignore_terminate:
      self.close_child_end_of_pipes()

    self._terminate()

  def kill(self):
    """Overrides the default kill() method.

    Allows the behavior to be faked, while still having the filtered_subprocess
    update its internal state.
    """
    self.was_killed = True

    if not self._ignore_kill:
      self.close_child_end_of_pipes()

    self._kill()


class TestFilteredSubprocessFake(unittest.TestCase):
  """Tests of filtered_subprocess.Popen using the fake."""

  def test_trivial_successful_run(self):
    with FilteredSubprocessFake() as p:
      p.write_stdout('xyz\n123')
      p.write_stderr('abc\n456')
      p.close_child_end_of_pipes()

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(output_handler)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertFalse(p.was_terminated)
      self.assertFalse(p.was_killed)
      self.assertEquals('xyz\n123', output_handler.stdout)
      self.assertEquals('abc\n456', output_handler.stderr)
      self.assertFalse(output_handler.timeout)

  def test_large_outputs_handled_correctly_even_with_timeouts(self):
    large_string = 1024 * (50 * 'x' + '\n')

    with FilteredSubprocessFake() as p:
      p.write_stdout(large_string)
      p.close_child_end_of_pipes()

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(
          output_handler, timeout=1, output_timeout=1)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertFalse(p.was_terminated)
      self.assertFalse(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals(large_string, output_handler.stdout)
      self.assertFalse(output_handler.timeout)

  def test_output_handler_can_terminate_child_early(self):
    with FilteredSubprocessFake() as p:
      p.write_stdout('xyz\n123')

      output_handler = SimpleOutputHandler(done=True)
      p.run_process_filtering_output(
          output_handler, timeout=1, stop_on_done=True)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertTrue(p.was_terminated)
      self.assertFalse(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals('xyz\n', output_handler.stdout)
      self.assertFalse(output_handler.timeout)

  def test_global_timeout_detected_and_child_can_be_terminated(self):
    with FilteredSubprocessFake() as p:
      p.write_stdout('xyz\n123')

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(
          output_handler, timeout=1, stop_on_done=True)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertTrue(p.was_terminated)
      self.assertFalse(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals('xyz\n', output_handler.stdout)
      self.assertTrue(output_handler.timeout)

  def test_output_timeout_detected_and_child_can_be_terminated(self):
    with FilteredSubprocessFake() as p:
      p.write_stdout('xyz\n123')

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(
          output_handler, output_timeout=1, stop_on_done=True)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertTrue(p.was_terminated)
      self.assertFalse(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals('xyz\n', output_handler.stdout)
      self.assertTrue(output_handler.timeout)

  def test_timeout_detected_but_subprocess_ignores_sigterm(self):
    with FilteredSubprocessFake(ignore_terminate=True) as p:
      p.write_stdout('xyz\n123')

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(
          output_handler, timeout=1, stop_on_done=True)

      self.assertEquals(p._STATE_FINISHED, p._state)
      self.assertTrue(p.was_terminated)
      self.assertTrue(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals('xyz\n', output_handler.stdout)
      self.assertTrue(output_handler.timeout)

  def test_subprocess_abandoned_on_timeout_if_unkillable(self):
    with FilteredSubprocessFake(ignore_terminate=True, ignore_kill=True) as p:
      p.write_stdout('xyz\n123')

      output_handler = SimpleOutputHandler()
      p.run_process_filtering_output(
          output_handler, timeout=1, stop_on_done=True)

      self.assertEquals(p._STATE_ABANDON, p._state)
      self.assertTrue(p.was_terminated)
      self.assertTrue(p.was_killed)
      self.assertEquals('', output_handler.stderr)
      self.assertEquals('xyz\n', output_handler.stdout)
      self.assertTrue(output_handler.timeout)


class TestFilteredSubprocessReal(unittest.TestCase):
  """Tests of filtered_subprocess.Popen using a real subprocess.

  These tests need to be limited to simple operations, as short timeouts (as
  appropriate for a unit test) will not work when the build machine is under
  typical load when building/testing lots of code.
  """

  def test_simple_run(self):
    output_handler = SimpleOutputHandler()
    self.assertFalse(output_handler.timeout)

    p = Popen(['python', '-c', 'print "abc"'])
    p.run_process_filtering_output(output_handler)
    self.assertEquals(p._STATE_FINISHED, p._state)
    self.assertEquals('', output_handler.stderr)
    self.assertEquals('abc\n', output_handler.stdout)
    self.assertFalse(output_handler.timeout)


if __name__ == '__main__':
  unittest.main()

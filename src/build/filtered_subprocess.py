# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utility class, extending subprocess.Popen"""

import errno
import io
import logging
import select
import signal
import subprocess
import sys
import time

import build_common
from util import nonblocking_io


class _BlackHoleOutputHandler(object):
  """Does nothing with any input/timeout callbacks made."""
  def handle_stderr(self, text):
    pass

  def handle_stdout(self, text):
    pass

  def handle_timeout(self):
    pass

  def is_done(self):
    return True


def _handle_stream_output(reader, handler):
  if reader.closed:
    return False

  read = False
  try:
    for line in reader:
      handler(line)
      read = True
    reader.close()  # EOF is found.
  except io.BlockingIOError:
    # All available lines are read. No more line is available for now.
    pass
  return read


class Popen(subprocess.Popen):
  """Extends subprocess.Popen to run a process and filter its output. """

  _SHUTDOWN_WAIT_SECONDS = 5
  _MIN_TIMEOUT_SECONDS = 1

  _STATE_RUNNING = 0  # Running normally
  _STATE_TIMED_OUT = 1  # Timeout detected
  _STATE_SENDING_SIGTERM = 2  # Sending SIGTERM
  _STATE_SENDING_SIGKILL = 3  # Sending SIGKILL
  _STATE_ABANDON = 4  # Tried killing, but did not seem to shut down.
  _STATE_FINISHED = 5  # Shutdown, though might have been SIGTERM'd
  _SHUTDOWN_STATES = (_STATE_SENDING_SIGKILL, _STATE_SENDING_SIGTERM)

  def __init__(self, args, stdin=None, stdout=subprocess.PIPE,
               stderr=subprocess.PIPE, **kwargs):
    assert not kwargs.get('shell', False), (
        'We do not expect to run process with shell.')
    assert kwargs.get('bufsize', 0) == 0, (
        'buffering should be disabled.')
    try:
      super(Popen, self).__init__(
          args, stdout=stdout, stderr=stderr, stdin=stdin, **kwargs)
    except:
      logging.error('Popen for args %s failed', args)
      raise

    logging.info('Created pid %d; the command follows:', self.pid)
    build_common.log_subprocess_popen(args, **kwargs)
    self._initialize_state()

  def _initialize_state(self):
    if self.stdout:
      self.stdout = nonblocking_io.LineReader(self.stdout)
    if self.stderr:
      self.stderr = nonblocking_io.LineReader(self.stderr)

    # This is the wall clock time the child needs to emit output by or be
    # considered dead (timed-out). If None, there is no timeout.
    self._child_output_deadline = None

    # This is the rate (in seconds) at which the child needs to generate output.
    # It is used to recompute _child_output_deadline.
    self._child_output_timeout = None

    # This is the wallclock time at which we expect the child to have completed.
    # It can be None if we do not care when it finishes.
    # It is set later based on the actual current time as needed if we set up a
    # deadline on the call to run_process_filtering_output()
    self._child_finish_deadline = None

    # This is the wallclock time at which we will try the next shutdown step.
    # This is initialized here intentionally to the beginning of time, and is
    # updated based on the current time and a reasonable delay as each shutdown
    # step is tried.
    self._shutdown_deadline = None

    # Sorted list of all the deadlines (wallclock times), for quickly choosing
    # the next one.
    self._deadlines = []

    self._state = self._STATE_RUNNING  # As far as we know yet.

    # These are set later by run_process_filtering_output
    self._output_handler = None
    self._stop_on_done = False

  def _are_all_pipes_closed(self):
    return self.stdout.closed and self.stderr.closed

  def _close_all_pipes(self):
    if not self.stdout.closed:
      self.stdout.close()
    if not self.stderr.closed:
      self.stderr.close()

  def _handle_output(self):
    # Consume output from any streams.
    stderr_read = _handle_stream_output(
        self.stderr, self._output_handler.handle_stderr)
    stdout_read = _handle_stream_output(
        self.stdout, self._output_handler.handle_stdout)

    if stderr_read or stdout_read:
      self._update_child_output_deadline()
      return True

    if self._state == self._STATE_RUNNING:
      now = time.time()
      if (self._child_output_deadline and now >= self._child_output_deadline or
          self._child_finish_deadline and now >= self._child_finish_deadline):
        # Report a timeout
        logging.debug("Process %d has timed out", self.pid)
        self._output_handler.handle_timeout()
        self._state = self._STATE_TIMED_OUT

    return False

  def update_timeout(self, timeout):
    self._child_finish_deadline = time.time() + timeout
    self._regenerated_deadline_list()

  def _update_child_output_deadline(self):
    if self._child_output_timeout is None:
      self._child_output_deadline = None
    else:
      self._child_output_deadline = time.time() + self._child_output_timeout
    self._regenerated_deadline_list()

  def _update_shutdown_deadline(self):
    self._shutdown_deadline = time.time() + self._SHUTDOWN_WAIT_SECONDS
    self._regenerated_deadline_list()

  def _regenerated_deadline_list(self):
    self._deadlines = []

    def add_deadline(deadline):
      if deadline is not None:
        self._deadlines.append(deadline)

    add_deadline(self._child_output_deadline)
    add_deadline(self._child_finish_deadline)
    add_deadline(self._shutdown_deadline)
    self._deadlines.sort()

  def _find_next_deadline(self, now):
    """Returns the next deadline after 'now'.
    If there are no deadlines, returns None."""
    for deadline in self._deadlines:
      if now < deadline:
        return deadline
    return None

  def _compute_timeout(self, max_timeout=5):
    """Calculate the time (up to |max_timeout| seconds) before |deadline|"""
    now = time.time()
    deadline = self._find_next_deadline(now)
    if deadline is None:
      return max_timeout
    else:
      now = time.time()
      # Clamp the timeout to a positive value less than |max_timeout|, since
      # some versions of Python may throw an exception on negative values.
      return max(0, min(deadline - now, max_timeout))

  def _wait_for_child_output(self):
    """Waits for the child process to generate output."""
    streams_to_block_reading_on = []

    # Generate a list of handles to wait on for being able to read them.
    # Filter out any that have been closed.
    if not self.stdout.closed:
      streams_to_block_reading_on.append(self.stdout)
    if not self.stderr.closed:
      streams_to_block_reading_on.append(self.stderr)

    # If we have nothing to wait on, we're on our way out.
    if not streams_to_block_reading_on:
      assert self._are_all_pipes_closed()
      return

    try:
      select.select(
          streams_to_block_reading_on, [], [], self._compute_timeout())[0]
    except select.error as e:
      if e[0] == errno.EINTR:
        logging.info("select has been interrupted, exit normally.")
        sys.exit(0)
      logging.error("select error: " + e[1])
      sys.exit(-1)

  def _signal_children_of_xvfb(self, signum):
    # On platforms other than Linux, psutil may not exist. As such
    # environment does not have xvfb-run, we can ignore the error.
    # We should also ignore NoSuchProcess. This means the program has
    # finished after creating psutil.Process object.
    try:
      import psutil
      try:
        proc = psutil.Process(self.pid)

        if proc.name != 'xvfb-run':
          return False

        for child in proc.get_children():
          if child.name != 'Xvfb':
            child.send_signal(signum)
        return True
      except psutil.NoSuchProcess:
        return False
    except ImportError:
      return False

  def terminate(self):
    if not self._signal_children_of_xvfb(signal.SIGTERM):
      super(Popen, self).terminate()
    self._terminate()

  def _terminate(self):
    self._update_shutdown_deadline()
    self._state = self._STATE_SENDING_SIGTERM

  def kill(self):
    if not self._signal_children_of_xvfb(signal.SIGKILL):
      super(Popen, self).kill()
    self._kill()

  def _kill(self):
    self._update_shutdown_deadline()
    self._state = self._STATE_SENDING_SIGKILL

  def _is_done(self):
    return (self._output_handler.is_done() or
            self._state in self._SHUTDOWN_STATES)

  def _advance_shutdown_state(self):
    if self._stop_on_done:
      # Switch to a black hole output handler, as the caller does not want any
      # more output. But we still need to process it.
      self._output_handler = _BlackHoleOutputHandler()
      self._stop_on_done = False

    if self._shutdown_deadline > time.time():
      # Still waiting on the previous termination step
      return True

    if self._state < self._STATE_SENDING_SIGTERM:
      logging.debug("Terminating process %d", self.pid)
      self.terminate()
      return True
    elif self._state < self._STATE_SENDING_SIGKILL:
      logging.error("Killing process %d", self.pid)
      self.kill()
      return True

    return False

  def run_process_filtering_output(self, output_handler, timeout=None,
                                   output_timeout=None, stop_on_done=False):
    """Runs the process, invoking methods on output_handler as appropriate.

    output_handler is expected to have the following interface:

        output_handler.is_done()
            Should returns true if process should be terminated. Note however
            it is called only immediately after output is processed, so if
            the process is not generating any output when this call would
            return True, then it will not be terminated.
        output_handler.handle_stdout(line)
            Called whenever the process writes a line of text to stdout.
        output_handler.handle_stderr(line)
            Called whenever the process writes a line of text to stderr.
        output_handler.handle_timeout()
            Called whenever the process timeout is over.

    If timeout is not None, it is a count in seconds to wait for process
    termination.

    if output_timeout is not None, it is the maximum count in seconds to wait
    for any output activity from the child process.

    If stop_on_done is True, the run loop stops trying to filter output as soon
    as the output_handler signals it is done, and just waits for process
    termination."""

    assert self._state == self._STATE_RUNNING

    if timeout:
      self.update_timeout(timeout)
    if output_timeout:
      self._child_output_timeout = output_timeout
      self._update_child_output_deadline()

    self._output_handler = output_handler
    self._stop_on_done = stop_on_done

    while not self._are_all_pipes_closed():
      self._wait_for_child_output()
      if not self._handle_output():
        # We had no output. Check if the child process has already shut down.
        # By design we ensure all output is read before doing this.
        if self.poll() is not None:
          self._close_all_pipes()
          break

      if self._is_done():
        # Step towards shutting down the child process
        if not self._advance_shutdown_state():
          # If we made no progress, abandon the process in whatever state it is
          # in.
          self._state = self._STATE_ABANDON
          logging.error("Abandoning process %d", self.pid)
          return

    # Wait for the normal process exit to complete, but this requires all output
    # to be over, otherwise we could deadlock waiting for the child process to
    # terminate, while the child process waits us to make room in the output
    # pipes.
    assert self._are_all_pipes_closed()
    logging.debug("Waiting on process %d", self.pid)
    self.wait()

    self._state = self._STATE_FINISHED

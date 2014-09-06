# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import tempfile
import threading
import time
import traceback
import unittest

from util import concurrent


class TestCondition(unittest.TestCase):
  def test_wait_for(self):
    cond = concurrent.Condition(threading.Lock())
    event = threading.Event()
    with cond:
      def _task(cond, event):
        # The thread is started while the |cond| is acquired by the original
        # thread, so it is blocked here initially. In the wait_for() below,
        # |cond| is released and then this thread actually runs the with-block.
        with cond:
          event.set()
          cond.notify_all()
      thread = threading.Thread(target=_task, args=(cond, event))
      thread.start()
      result = cond.wait_for(lambda: event.is_set())
      thread.join()
      self.assertTrue(result)

  def test_wait_for_timeout(self):
    cond = concurrent.Condition(threading.Lock())
    # Timeout quickly.
    with cond:
      result = cond.wait_for(lambda: False, timeout=0.05)
    self.assertFalse(result)

  def test_wait_for_not_aquired(self):
    cond = concurrent.Condition(threading.Lock())
    # If the wait_for() is called without acquiring the lock, RuntimeError
    # should be raised.
    # Note that if predicate returns True at the first time, it does not raise
    # an exception due to implementation. As Python 3 behaves so, it should
    # not be a problem.
    with self.assertRaises(RuntimeError):
      cond.wait_for(lambda: False)


class ThreadPoolExecutorTest(unittest.TestCase):
  """Simple tests for ThreadPoolExecutor."""
  def test_simple_scenario(self):
    started_event = threading.Event()
    waiting_event = threading.Event()

    def task_run():
      started_event.set()
      waiting_event.wait()

    with concurrent.ThreadPoolExecutor(max_workers=1) as executor:
      future1 = executor.submit(task_run)
      future2 = executor.submit(task_run)
      started_event.wait()
      # Here the task is actually started. The worker is one, so only the first
      # task should be running.
      self.assertTrue(future1.running())
      self.assertFalse(future2.running())
      waiting_event.set()

    # Finally, all tasks should be done.
    self.assertTrue(future1.done())
    self.assertTrue(future2.done())

  def test_multi_worker(self):
    started_event1 = threading.Event()
    waiting_event1 = threading.Event()
    started_event2 = threading.Event()
    waiting_event2 = threading.Event()

    def task_run(started_event, waiting_event):
      started_event.set()
      waiting_event.wait()

    with concurrent.ThreadPoolExecutor(max_workers=2) as executor:
      future1 = executor.submit(task_run, started_event1, waiting_event1)
      future2 = executor.submit(task_run, started_event2, waiting_event2)
      future3 = executor.submit(lambda: None)
      started_event1.wait()
      started_event2.wait()

      # Since the executor has two workers, two tasks should be running
      # in parallel.
      self.assertTrue(future1.running())
      self.assertTrue(future2.running())
      self.assertFalse(future3.running())
      self.assertFalse(future3.done())

      waiting_event1.set()
      waiting_event2.set()

    # Finally, all tasks should be done.
    self.assertTrue(future1.done())
    self.assertTrue(future2.done())
    self.assertTrue(future3.done())

  def test_cancel(self):
    started_event = threading.Event()
    waiting_event = threading.Event()

    def task_run():
      started_event.set()
      waiting_event.wait()

    cancel_event = threading.Event()

    def task_cancel_run():
      cancel_event.set()

    with concurrent.ThreadPoolExecutor(max_workers=1) as executor:
      future1 = executor.submit(task_run)
      future2 = executor.submit(task_cancel_run)
      started_event.wait()
      self.assertTrue(future1.running())
      self.assertFalse(future2.running())

      # Cancel the second task. So it shouldn't run.
      self.assertTrue(future2.cancel())
      waiting_event.set()

    # The task_cancel_run should not be called.
    self.assertFalse(cancel_event.is_set())


# Unfortunately, there seems no easy way to share Event object between a worker
# process and the master process, so here we use tempfile instead.
class TempFileEvent(object):
  def __init__(self):
    f = tempfile.NamedTemporaryFile(delete=False)
    f.close()
    while not os.path.exists(f.name):
      time.sleep(0.1)
    assert os.path.exists(f.name)
    self._name = f.name

  def set(self):
    try:
      os.remove(self._name)
    except:
      # Ignore any error.
      pass

  def wait(self):
    while os.path.exists(self._name):
      # Poll every 0.1 secs.
      time.sleep(0.1)

  def is_set(self):
    return not os.path.exists(self._name)


def _process_task_run(set_event, wait_event):
  # This function needs to be global.
  if set_event:
    set_event.set()
  if wait_event:
    wait_event.wait()


class ProcessPoolExecutorTest(unittest.TestCase):
  """Simple tests for ThreadPoolExecutor."""
  def test_simple_scenario(self):
    started_event = TempFileEvent()
    waiting_event = TempFileEvent()

    try:
      with concurrent.ProcessPoolExecutor(max_workers=1) as executor:
        future1 = executor.submit(
            _process_task_run, started_event, waiting_event)
        future2 = executor.submit(_process_task_run, None, None)
        started_event.wait()
        # Here the task is actually started. The worker is one, so only the
        # first task should be running.
        self.assertTrue(future1.running())
        self.assertFalse(future2.running())
        waiting_event.set()

      # Finally, all tasks should be done.
      self.assertTrue(future1.done())
      self.assertTrue(future2.done())
    finally:
      started_event.set()
      waiting_event.set()

  def test_multi_worker(self):
    started_event1 = TempFileEvent()
    waiting_event1 = TempFileEvent()
    started_event2 = TempFileEvent()
    waiting_event2 = TempFileEvent()

    try:
      with concurrent.ProcessPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(
            _process_task_run, started_event1, waiting_event1)
        future2 = executor.submit(
            _process_task_run, started_event2, waiting_event2)
        future3 = executor.submit(_process_task_run, None, None)

        started_event1.wait()
        started_event2.wait()
        # Since the executor has two workers, two tasks should be running
        # in parallel.
        self.assertTrue(future1.running())
        self.assertTrue(future2.running())
        self.assertFalse(future3.running())
        self.assertFalse(future3.done())

        waiting_event1.set()
        waiting_event2.set()

      # On completion, all tasks should be done.
      self.assertTrue(future1.done())
      self.assertTrue(future2.done())
      self.assertTrue(future3.done())
    finally:
      started_event1.set()
      waiting_event1.set()
      started_event2.set()
      waiting_event2.set()

  def test_cancel(self):
    started_event = TempFileEvent()
    waiting_event = TempFileEvent()
    cancel_event = TempFileEvent()

    try:
      with concurrent.ProcessPoolExecutor(max_workers=1) as executor:
        future1 = executor.submit(
            _process_task_run, started_event, waiting_event)
        future2 = executor.submit(_process_task_run, cancel_event, None)
        started_event.wait()
        self.assertTrue(future1.running())
        self.assertFalse(future2.running())

        # Cancel the second task. So it shouldn't run.
        self.assertTrue(future2.cancel())
        waiting_event.set()

      # Second task should not run.
      self.assertFalse(cancel_event.is_set())
    finally:
      started_event.set()
      waiting_event.set()
      cancel_event.set()


class SynchronousExecutorTest(unittest.TestCase):
  def test_simple_scenario(self):
    def run():
      pass

    with concurrent.SynchronousExecutor() as executor:
      future = executor.submit(run)
      # The task runs synchronously, so returned future should be always done.
      self.assertTrue(future.done())


class FutureTest(unittest.TestCase):
  """Simple tests for Future."""

  _DUMMY_RESULT = object()

  def test_simple_scenario(self):
    future = concurrent.Future()
    # Make sure the precondition.
    self.assertFalse(future.cancelled())
    self.assertFalse(future.running())
    self.assertFalse(future.done())

    with self.assertRaises(concurrent.TimeoutError):
      future.result(timeout=0)

    # Start the task.
    self.assertTrue(future.set_running_or_notify_cancel())

    self.assertFalse(future.cancelled())
    self.assertTrue(future.running())
    self.assertFalse(future.done())
    with self.assertRaises(concurrent.TimeoutError):
      future.result(timeout=0)

    # Then finished.
    future.set_result(FutureTest._DUMMY_RESULT)

    self.assertFalse(future.cancelled())
    self.assertFalse(future.running())
    self.assertTrue(future.done())
    # Expect that future.result() returns immediately.
    self.assertEquals(FutureTest._DUMMY_RESULT, future.result())

  def test_exception_scenario(self):
    future = concurrent.Future()

    # Start the task and finish with an exception.
    self.assertTrue(future.set_running_or_notify_cancel())
    future.set_exception(AssertionError())

    self.assertFalse(future.cancelled())
    self.assertFalse(future.running())
    self.assertTrue(future.done())
    # Expect that future.result() raises the exception immediately.
    with self.assertRaises(AssertionError):
      future.result()

  def test_cancel_success(self):
    future = concurrent.Future()

    self.assertTrue(future.cancel())

    self.assertTrue(future.cancelled())
    self.assertFalse(future.running())
    self.assertTrue(future.done())
    # Expect that CancelledError is raised immediately.
    with self.assertRaises(concurrent.CancelledError):
      future.result()

  def test_cancel_failed(self):
    future = concurrent.Future()

    # Running task is not cancellable.
    self.assertTrue(future.set_running_or_notify_cancel())
    self.assertFalse(future.cancel())

    # Completed task is not cancellable, neither.
    future.set_result(FutureTest._DUMMY_RESULT)
    self.assertFalse(future.cancel())

  def test_wait_result(self):
    def worker_run(future):
      future.set_running_or_notify_cancel()
      future.set_result(FutureTest._DUMMY_RESULT)

    # Note: unfortunately there is no reliable way to ensure set_result()
    # is called (on worker thread) after result() is called on the main thread.
    # However, even if the order is inverted, this test should pass
    # successfully.
    future = concurrent.Future()
    thread = threading.Thread(target=worker_run, args=(future,))
    thread.daemon = True
    thread.start()
    self.assertEquals(FutureTest._DUMMY_RESULT, future.result())
    self.assertEquals(None, future.exception())
    thread.join()

  def test_wait_exception(self):
    def worker_run(future):
      future.set_running_or_notify_cancel()
      future.set_exception(AssertionError())

    # Note: unfortunately there is no reliable way to ensure set_exception()
    # is called (on worker thread) after result() is called on the main thread.
    # However, even if the order is inverted, this test should pass
    # successfully.
    future = concurrent.Future()
    thread = threading.Thread(target=worker_run, args=(future,))
    thread.daemon = True
    thread.start()
    with self.assertRaises(AssertionError):
      future.result()
    self.assertIsInstance(future.exception(), AssertionError)
    thread.join()

  def test_callback(self):
    future = concurrent.Future()
    event = threading.Event()
    future.add_done_callback(lambda _: event.set())
    self.assertFalse(event.is_set())

    # Start the task.
    self.assertTrue(future.set_running_or_notify_cancel())
    self.assertFalse(event.is_set())

    # And finish it. The callback should be called then.
    future.set_result(FutureTest._DUMMY_RESULT)
    self.assertTrue(event.is_set())

  def test_callback_exception(self):
    future = concurrent.Future()
    event = threading.Event()
    future.add_done_callback(lambda _: event.set())
    self.assertFalse(event.is_set())

    # Start the task and finish with an exception
    self.assertTrue(future.set_running_or_notify_cancel())
    self.assertFalse(event.is_set())

    # And finish it with an exception. The callback should be called then.
    future.set_exception(AssertionError())
    self.assertTrue(event.is_set())

  def test_callback_cancel(self):
    future = concurrent.Future()
    event = threading.Event()
    future.add_done_callback(lambda _: event.set())
    self.assertFalse(event.is_set())

    # Cancel the task, then the callback should be called.
    self.assertTrue(future.cancel())
    self.assertTrue(event.is_set())

  def test_callback_done(self):
    future = concurrent.Future()

    # Mark the future as the task is completed.
    self.assertTrue(future.set_running_or_notify_cancel())
    future.set_result(FutureTest._DUMMY_RESULT)
    self.assertTrue(future.done())

    # Add the callback to the future in DONE state. The callback should be
    # called immediately.
    event = threading.Event()
    future.add_done_callback(lambda _: event.set())
    self.assertTrue(event.is_set())

  def test_exception_traceback(self):
    future = concurrent.Future()
    self.assertTrue(future.set_running_or_notify_cancel())

    # Set an exception inside the inner function.
    class TestException(Exception):
      pass

    def inner_function(future):
      try:
        raise TestException
      except TestException as e:
        future.set_exception(e)
    inner_function(future)

    # Then we expect the raised exception to be propagated, with the inner
    # function appearing in the stack traceback.
    with self.assertRaises(TestException):
      try:
        future.result()
      except TestException:
        self.assertTrue('inner_function' in traceback.format_exc())
        raise


class WaitTest(unittest.TestCase):
  """Simple tests for wait function."""

  _DUMMY_RESULT = object()

  def test_all_completed(self):
    future1 = concurrent.Future()
    future2 = concurrent.Future()

    # First of all, no futures are completed.
    done, not_done = concurrent.wait([future1, future2], timeout=0.01)
    self.assertFalse(done)  # Empty.
    self.assertEqual({future1, future2}, not_done)

    # Mark future1 as completed.
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_result(WaitTest._DUMMY_RESULT)
    done, not_done = concurrent.wait([future1, future2], timeout=0.01)
    self.assertEqual({future1}, done)
    self.assertEqual({future2}, not_done)

    # Mark future2 as completed, too.
    self.assertTrue(future2.set_running_or_notify_cancel())
    future2.set_result(WaitTest._DUMMY_RESULT)

    # Now, wait should return immediately, even timeout is not set.
    done, not_done = concurrent.wait([future1, future2])
    self.assertEqual({future1, future2}, done)
    self.assertFalse(not_done)  # Empty.

  def test_all_completed_with_exception(self):
    future1 = concurrent.Future()
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_exception(AssertionError())

    # Finished with an exception is also considered as completed.
    done, not_done = concurrent.wait([future1])
    self.assertEqual({future1}, done)
    self.assertFalse(not_done)  # Empty.

  def test_first_completed(self):
    future1 = concurrent.Future()
    future2 = concurrent.Future()

    # First of all, no futures are completed.
    done, not_done = concurrent.wait([future1, future2], timeout=0.01,
                                     return_when=concurrent.FIRST_COMPLETED)
    self.assertFalse(done)  # Empty.
    self.assertEqual({future1, future2}, not_done)

    # Mark future1 as completed.
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_result(WaitTest._DUMMY_RESULT)
    # Here, wait should return immediately even without timeout.
    done, not_done = concurrent.wait([future1, future2],
                                     return_when=concurrent.FIRST_COMPLETED)
    self.assertEqual({future1}, done)
    self.assertEqual({future2}, not_done)

  def test_first_completed_with_exception(self):
    future1 = concurrent.Future()
    future2 = concurrent.Future()

    # Mark future1 as completed with an exception.
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_exception(AssertionError())
    # Here, wait should return immediately even without timeout.
    done, not_done = concurrent.wait([future1, future2],
                                     return_when=concurrent.FIRST_COMPLETED)
    self.assertEqual({future1}, done)
    self.assertEqual({future2}, not_done)

  def test_first_exception(self):
    future1 = concurrent.Future()
    future2 = concurrent.Future()

    # First of all, no futures are completed.
    done, not_done = concurrent.wait([future1, future2], timeout=0.01,
                                     return_when=concurrent.FIRST_EXCEPTION)
    self.assertFalse(done)  # Empty.
    self.assertEqual({future1, future2}, not_done)

    # Mark future1 as completed with an exception.
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_exception(AssertionError())
    # Here, wait should return immediately even without timeout.
    done, not_done = concurrent.wait([future1, future2],
                                     return_when=concurrent.FIRST_EXCEPTION)
    self.assertEqual({future1}, done)
    self.assertEqual({future2}, not_done)

  def test_first_exception_without_error(self):
    future1 = concurrent.Future()
    future2 = concurrent.Future()

    # Mark both futures as completed without any exceptions.
    self.assertTrue(future1.set_running_or_notify_cancel())
    future1.set_result(WaitTest._DUMMY_RESULT)
    self.assertTrue(future2.set_running_or_notify_cancel())
    future2.set_result(WaitTest._DUMMY_RESULT)

    # If all futures are completed, wait() should return immediately,
    # even if return_when is set to FIRST_EXCEPTION.
    done, not_done = concurrent.wait([future1, future2],
                                     return_when=concurrent.FIRST_EXCEPTION)
    self.assertEqual({future1, future2}, done)
    self.assertFalse(not_done)  # Empty.


if __name__ == '__main__':
  unittest.main()

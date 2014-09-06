# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Utilities to run tasks in parallel and concurrently."""

import Queue
import collections
import logging
import multiprocessing
import multiprocessing.queues
import signal
import sys
import threading
import time

FIRST_COMPLETED = 0
FIRST_EXCEPTION = 1
ALL_COMPLETED = 2


class Condition(object):
  """This is thin wrapper of threading.Condition to support wait_for().

  Python3's threading.Condition has a convenient method wait_for() which
  supports spurious wake up. This class is a kind of its back port.
  """
  def __init__(self, *args, **kwargs):
    self._cond = threading.Condition(*args, **kwargs)
    # Delegate following methods to threading.Condition.
    self.acquire = self._cond.acquire
    self.release = self._cond.release
    self.wait = self._cond.wait
    self.notify = self._cond.notify
    self.notify_all = self._cond.notify_all
    # __enter__() and __exit__() must be defined as methods to support with
    # statement. It is done below.

  def __enter__(self, *args, **kwargs):
    self._cond.__enter__(*args, **kwargs)

  def __exit__(self, *args, **kwargs):
    self._cond.__exit__(*args, **kwargs)

  def wait_for(self, predicate, timeout=None):
    """Wait until a condition evaluates to True.

    This is the back port implementation of python3's
    threading.Condition.wait_for. See also the document.
    """
    # Unfortunately, monotonic timer is not supported until 3.4, so here
    # time.time() is used.
    end_time = time.time() + timeout if timeout is not None else None
    while True:
      # Note that the predicate() is evaluated for each iteration to handle
      # spurious wake up properly.
      result = predicate()
      if result:
        return result

      # Even if end_time is None (i.e., timeout is not specified), we need to
      # set some timeout to Condition.wait(). Otherwise, the thread is blocked
      # in C-layer, so there is not chance to be interrupted (e.g., by
      # KeyboardInterruption initiated by Ctrl-C).
      # We heuristically chose 1e6 seconds for the huge value.
      remaining_time = end_time - time.time() if end_time is not None else 1e6
      if remaining_time < 0:
        return result
      self._cond.wait(remaining_time)


class Executor(object):
  """Defines an interface of a task executor.

  This class is designed to emulate the concurrent.futures.Executor in
  Python 3. Please see also
  https://docs.python.org/3/library/concurrent.futures.html#executor-objects
  Note that map() is not supported, just because it is not used in ARC now.
  """
  def __init__(self):
    pass

  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc_value, traceback):
    # Note that, on exit from the with-statement's scope, we probably want to
    # terminate workers. However, currently there seems no simple way to do it,
    # unfortunately.
    self.shutdown(wait=True)

  def submit(self, fn, *args, **kwargs):
    raise NotImplemented()

  def shutdown(self, wait=True):
    raise NotImplemented()


# Hereafter, the implementation of the ThreadPoolExecutor.
def _thread_worker_run(queue):
  """The main routine of the thread worker."""
  while True:
    task = queue.get()
    if task is None:
      # Sentinel is found. Quit the worker.
      break

    (fn, args, kwargs, future) = task
    if not future.set_running_or_notify_cancel():
      # The task was cancelled. Do nothing.
      continue

    # Run the task.
    try:
      future.set_result(fn(*args, **kwargs))
    except BaseException as e:
      # Here, we capture any exception to notify the main thread.
      future.set_exception(e)


class ThreadPoolExecutor(Executor):
  """Thread base implementation of Executor."""
  def __init__(self, max_workers, daemon=False):
    """Creates worker threads and starts them.

    In addition to the original ThreadPoolExecutor(), this has one more
    argument, which is |daemon| to make worker threads as daemon.
    """
    super(ThreadPoolExecutor, self).__init__()
    self._max_workers = max_workers
    self._queue = Queue.Queue()
    self._worker_list = []
    self._shutdown = False
    for _ in xrange(max_workers):
      worker_thread = threading.Thread(
          target=_thread_worker_run, args=(self._queue,))
      worker_thread.daemon = daemon
      worker_thread.start()
      self._worker_list.append(worker_thread)

  def submit(self, fn, *args, **kwargs):
    if self._shutdown:
      raise RuntimeError('The executor is already shutdown.')

    future = Future()
    self._queue.put((fn, args, kwargs, future))
    return future

  def shutdown(self, wait=True):
    if not self._shutdown:
      self._shutdown = True
      for _ in xrange(self._max_workers):
        # Send sentinel to all the workers. Each worker takes exact one None.
        self._queue.put(None)
    if wait:
      self._join_worker()

  def _join_worker(self):
    for worker_thread in self._worker_list:
      # We should set a timeout for Thread.join. Otherwise, this script
      # keeps running even after KeyboardInturrupt. See http://goo.gl/YrCR8
      while worker_thread.is_alive():
        worker_thread.join(1)


# Hereafter, the implementation of the ProcessPoolExecutor.
def _process_worker_run(in_queue, out_queue):
  """The main routine of the process worker."""
  # First of all, prevent KeyboardInterrupt exception in workers.
  signal.signal(signal.SIGINT, signal.SIG_IGN)

  while True:
    task = in_queue.get()
    if task is None:
      # Sentinel. Exiting.
      break

    future_id, fn, args, kwargs = task
    try:
      out_queue.put((future_id, False, fn(*args, **kwargs)))
    except BaseException as e:
      # Catch any exceptions, and send it back to the master.
      out_queue.put((future_id, True, e))


def _broker_thread_run(
    max_workers, task_queue, in_queue, out_queue, is_terminated):
  future_dict = {}
  send_sentinel = False
  num_available_workers = max_workers
  while True:
    if send_sentinel and not future_dict:
      # Sentinels were sent to all the workers, and all running tasks are
      # completed.
      break

    task_result = out_queue.get()
    if is_terminated.is_set():
      # Termination process.
      break

    # If |task_result| is None, it is just a notification from the master that
    # a new task is enqueued. Do nothing in such a case.
    if task_result is not None:
      future_id, is_exception, result = task_result
      future = future_dict.pop(future_id)
      (future.set_exception if is_exception else future.set_result)(result)
      num_available_workers += 1

    if num_available_workers == 0:
      # Currently, there is no available worker.
      # Wait until some task is completed.
      continue

    try:
      while True:
        # Try to take a task from task_queue. If the task is already cancelled
        # just skip it, and retry.
        task = task_queue.get_nowait()
        # task[3] is its Future instance.
        if task is None or task[3].set_running_or_notify_cancel():
          # Found a sentinel, or a non-cancelled task.
          break
    except Queue.Empty:
      # Now, there is no new task.
      continue

    assert not send_sentinel
    if task is None:
      # None means a sentinel.
      for _ in xrange(max_workers):
        # Send sentinels to each worker process.
        in_queue.put(None)
      send_sentinel = True
      continue

    fn, args, kwargs, future = task
    future_id = id(future)
    future_dict[future_id] = future
    in_queue.put((future_id, fn, args, kwargs))
    num_available_workers -= 1


class ProcessPoolExecutor(Executor):
  """Process base implementation of Executor."""
  def __init__(self, max_workers=None):
    super(ProcessPoolExecutor, self).__init__()
    if max_workers is None:
      # Use cpu_count by default.
      max_workers = multiprocessing.cpu_count()

    self._shutdown = False

    # |task_queue| is a queue to send a task from the main thread to the broker
    # thread.
    self._task_queue = Queue.Queue()

    # |in_queue| is a queue to send a task from the broker thread to a worker
    # process.
    self._in_queue = multiprocessing.queues.SimpleQueue()

    # |out_queue| is a queue to send back the result of a task from the worker
    # process to the broker thread. This is also used to notify the broker
    # thread that a new task comes.
    self._out_queue = multiprocessing.queues.SimpleQueue()

    # Create worker processes, and start them.
    self._worker_list = [
        multiprocessing.Process(target=_process_worker_run,
                                name='WorkerProcess',
                                args=(self._in_queue, self._out_queue))
        for _ in xrange(max_workers)]
    for worker_process in self._worker_list:
      worker_process.start()

    # Create a broker process, and start it.
    self._is_terminated = threading.Event()
    self._broker_thread = threading.Thread(
        target=_broker_thread_run,
        args=(max_workers, self._task_queue, self._in_queue, self._out_queue,
              self._is_terminated))
    self._broker_thread.daemon = True
    self._broker_thread.start()

  def submit(self, fn, *args, **kwargs):
    if self._shutdown:
      raise RuntimeError('The executor is already shutdown.')

    future = Future()
    self._task_queue.put((fn, args, kwargs, future))
    # Notify the broker thread.
    self._out_queue.put(None)
    return future

  def shutdown(self, wait=True):
    if not self._shutdown:
      self._shutdown = True
      # Send a sentinel to the broker thread.
      self._task_queue.put(None)
      self._out_queue.put(None)
    if wait:
      self._join_worker()

  def _join_worker(self):
    while self._broker_thread.is_alive():
      self._broker_thread.join(1)
    for worker_process in self._worker_list:
      while worker_process.is_alive():
        worker_process.join(1)

  def terminate(self):
    """Force to terminate the workers."""
    # Terminate the broker thread.
    self._is_terminated.set()
    self._out_queue.put(None)

    # Terminate worker processes.
    for worker_process in self._worker_list:
      worker_process.terminate()


class SynchronousExecutor(Executor):
  def __init__(self):
    super(SynchronousExecutor, self).__init__()

  def submit(self, fn, *args, **kwargs):
    future = Future()
    if not future.set_running_or_notify_cancel():
      # This must not happen. set_running_or_notify_cancel() has side effect,
      # so we should not write it in assert statement directly.
      assert False

    # Run the task synchronously.
    try:
      future.set_result(fn(*args, **kwargs))
    except BaseException as e:
      future.set_exception(e)
    return future

  def shutdown(self, wait=True):
    # Nothing to do.
    pass


class CancelledError(Exception):
  """Raised when Future.result() is called for cancelled instance."""
  pass


class TimeoutError(Exception):
  """Raised when Future.result() is timed out."""
  pass


def _run_callback_list(callback_list, future):
  """Runs callbacks in |callback_list| with given |future|.

  This may be invoked on the main thread synchronously, or on a worker thread.
  """
  for callback in callback_list:
    try:
      callback(future)
    except BaseException as e:
      # Note: If callback raises an BaseException (but not Exception), the
      # behavior is undefined. We, here, catch and log it, too, to avoid
      # worker threads' unexpected termination, just in case.
      logging.error(e)


class Future(object):
  """Future object implementation in python2.

  Please see also https://docs.python.org/3/library/concurrent.futures.html.
  """
  # State of the Future object.
  _PENDING, _RUNNING, _FINISHED, _CANCELLED = range(4)

  def __init__(self):
    # Note: Members may be accessed from the main thread or on a worker thread.
    self._cond = Condition(threading.Lock())
    self._state = Future._PENDING
    self._result = None
    self._exception = None
    self._done_callback_list = []

  def _take_done_callback_list(self):
    """Returns |_done_callback_list| with resetting it.

    This function must be called while the |_cond| is acquired.
    """
    result = self._done_callback_list
    self._done_callback_list = []
    return result

  def cancel(self):
    with self._cond:
      if self._state != Future._PENDING:
        # Cannot cancel tasks which are already finished, already cancelled, or
        # now running.
        return False
      self._state = Future._CANCELLED
      done_callback_list = self._take_done_callback_list()
    _run_callback_list(done_callback_list, self)
    return True

  def cancelled(self):
    with self._cond:
      return self._state == Future._CANCELLED

  def running(self):
    with self._cond:
      return self._state == Future._RUNNING

  def done(self):
    with self._cond:
      return self._state in (Future._FINISHED, Future._CANCELLED)

  def result(self, timeout=None):
    with self._cond:
      self._wait_for_done(timeout)
      if self._exception:
        if sys.version_info < (3,) and self._traceback:
          # Simulate traceback passing in Python 2. Using exec() since the
          # 3-argument raise statement is a syntax error in Python 3.
          exec('raise type(self._exception), self._exception, self._traceback')
        else:
          raise self._exception
      return self._result

  def exception(self, timeout=None):
    with self._cond:
      self._wait_for_done(timeout)
      return self._exception

  def _wait_for_done(self, timeout):
    if not self._cond.wait_for(
        lambda: self._state in (Future._FINISHED, Future._CANCELLED), timeout):
      raise TimeoutError()
    if self._state == Future._CANCELLED:
      raise CancelledError()
    assert self._state == Future._FINISHED

  def set_running_or_notify_cancel(self):
    # This should be invoked on a worker thread.
    with self._cond:
      assert self._state not in (Future._FINISHED, Future._RUNNING)
      if self._state == Future._CANCELLED:
        # The task is already cancelled.
        return False

      assert self._state == Future._PENDING
      self._state = Future._RUNNING
      return True

  def set_result(self, result):
    self._done(result, None)

  def set_exception(self, exception):
    self._traceback = sys.exc_info()[2]
    self._done(None, exception)

  def _done(self, result, exception):
    """Called when a task is completed successfully or fails.

    |result| is the result returned by the task function on success.
    |exception| is raised one from the task function on failure.
    """
    with self._cond:
      assert self._state == Future._RUNNING
      self._state = Future._FINISHED
      self._result = result
      self._exception = exception
      done_callback_list = self._take_done_callback_list()
      self._cond.notify_all()
    # We should run callbacks outside of the lock, in order to avoid unexpected
    # deadlock issue.
    _run_callback_list(done_callback_list, self)

  def add_done_callback(self, fn):
    with self._cond:
      if self._state not in (Future._FINISHED, Future._CANCELLED):
        self._done_callback_list.append(fn)
        return

    # If the task will not run (i.e., already done or cancelled), call the |fn|
    # here, synchronously.
    fn(self)


class _Waiter(object):
  """Helper object to implement wait() function defined below."""

  def __init__(self, return_when, num_futures):
    self._return_when = return_when
    self._num_futures = num_futures
    # _cond guards _num_completed_futures, _num_exception_futures and _done.
    self._cond = Condition(threading.Lock())
    self._num_completed_futures = 0
    self._num_exception_futures = 0
    self._done = False

  def __call__(self, future):
    if future.cancelled():
      return

    with self._cond:
      self._num_completed_futures += 1
      if future.exception(timeout=0) is not None:
        self._num_exception_futures += 1

      self._done = (
          (self._return_when == FIRST_COMPLETED and
           self._num_completed_futures > 0) or
          (self._return_when == FIRST_EXCEPTION and
           self._num_exception_futures > 0) or
          (self._num_futures <= self._num_completed_futures))
      if self._done:
        self._cond.notify_all()

  def wait(self, timeout):
    with self._cond:
      self._cond.wait_for(lambda: self._done, timeout)


DoneAndNotDoneFutures = collections.namedtuple('DoneAndNotDoneFutures',
                                               ['done', 'not_done'])


def wait(fs, timeout=None, return_when=ALL_COMPLETED):
  """Implementation of concurrent.futures.wait() in Python 3. See its doc."""
  waiter = _Waiter(return_when, len(fs))
  for future in fs:
    future.add_done_callback(waiter)
  waiter.wait(timeout)

  done = set()
  not_done = set()
  for future in fs:
    (done if future.done() else not_done).add(future)
  return DoneAndNotDoneFutures(done, not_done)

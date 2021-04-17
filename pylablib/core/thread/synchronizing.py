from . import threadprop
from . import notifier
from ..utils import general

import threading


class QThreadNotifier(notifier.ISkipableNotifier):
    """
    Wait-notify thread synchronizer for controlled Qt threads based on :class:`.notifier.ISkipableNotifier`.

    Like :class:`.notifier.ISkipableNotifier`, the main functions are :meth:`.ISkipableNotifier.wait` (wait in a message loop until notified or until timeout expires)
    and :meth:`.ISkipableNotifier.notify` (notify the waiting thread). Both of these can only be called once and will raise and error on repeating calls.
    Along with notifying a variable can be passed, which can be accessed using :meth:`get_value` and :meth:`get_value_sync`.

    Args:
        skipable (bool): if ``True``, allows for skipable wait events
            (if :meth:`.ISkipableNotifier.notify` is called before :meth:`.ISkipableNotifier.wait`, neither methods are actually called).
    """
    _uid_gen=general.UIDGenerator(thread_safe=True)
    _notify_tag="#sync.notifier"
    def __init__(self, skipable=True):
        notifier.ISkipableNotifier.__init__(self,skipable=skipable)
        self._uid=None
        self.value=None
    def _pre_wait(self, *args, **kwargs):  # pylint: disable=unused-argument
        self._controller=threadprop.current_controller(require_controller=True)
        self._uid=self._uid_gen()
        return True
    def _do_wait(self, timeout=None):
        try:
            self._controller.wait_for_sync(self._notify_tag,self._uid,timeout=timeout)
            return True
        except threadprop.TimeoutThreadError:
            return False
    def _pre_notify(self, value=None):
        self.value=value
    def _do_notify(self, *args, **kwargs):  # pylint: disable=unused-argument
        self._controller.send_sync(self._notify_tag,self._uid)
        return True
    def get_value(self):
        """Get the value passed by the notifier (doesn't check if it has been passed already)"""
        return self.value
    def get_value_sync(self, timeout=None):
        """Wait (with the given `timeout`) for the value passed by the notifier"""
        if not self.done_wait():
            self.wait(timeout=timeout)
        return self.get_value()


class QMultiThreadNotifier(object):
    """
    Wait-notify thread synchronizer that can be used for multiple threads and called multiple times.

    Performs similar function to conditional variables.
    The synchronizer has an internal counter which is incread by 1 every time it is notified.
    The wait functions have an option to wait until the counter reaches the specific counter value (usually, 1 above the last wait call).
    """
    def __init__(self):
        object.__init__(self)
        self._lock=threading.Lock()
        self._cnt=0
        self._failed=False
        self._notifiers={}
    def wait(self, state=1, timeout=None):
        """
        Wait until notifier counter is equal to at least `state`
        
        Return current counter state plus 1, which is the next smallest value resulting in waiting.
        """
        with self._lock:
            if self._failed:
                raise threadprop.NoControllerThreadError("synchronizer failed")
            if self._cnt>=state:
                return self._cnt+1
            n=QThreadNotifier()
            self._notifiers.setdefault(state,[]).append(n)
        success=n.wait(timeout=timeout)
        if success:
            value=n.get_value()
            if value is None:
                raise threadprop.NoControllerThreadError("synchronizer failed")
            return value
        raise threadprop.TimeoutThreadError("synchronizer timed out")
    def wait_until(self, condition, timeout=None):
        """
        Wait until `condition` is met.

        `condition` is a function which is called (in the waiting thread) every time the synchronizer is notified.
        If it return non-``False``, the waiting is complete and its result is returned.
        """
        ctd=general.Countdown(timeout)
        cnt=1
        while True:
            res=condition()
            if res:
                return res
            cnt=self.wait(cnt,timeout=ctd.time_left())
    def notify(self):
        """Notify all waiting threads"""
        with self._lock:
            self._cnt+=1
            cnt=self._cnt
            notifiers=[]
            for k in list(self._notifiers):
                if k<=self._cnt:
                    notifiers+=self._notifiers.pop(k)
        for n in notifiers:
            n.notify(cnt)
    def fail(self):
        """
        Mark notifier as fails
        
        Fails all waiting notifiers.
        All subsequent wait calls raise an error
        """
        with self._lock:
            self._failed=True
            notifiers=[n for nlist in self._notifiers.values() for n in nlist]
            self._notifiers={}
        for n in notifiers:
            n.notify(None)
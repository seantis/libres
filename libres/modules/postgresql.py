import os
import signal

from datetime import datetime
from shutil import rmtree
from time import sleep

try:
    import testing.postgresql
    baseclass = testing.postgresql.Postgresql
except ImportError:
    baseclass = object


# testing.postgresql currently is a bit buggy if used in a script like in the
# flask example. This wrapper fixes the bug until the maintainer can fix it.
# https://pypi.python.org/pypi/testing.postgresql/1.0.2
# (no issue tracker unfortunately)
class Postgresql(baseclass):
    def terminate(self, _signal=signal.SIGTERM):

        if self.pid is None:
            return  # not started

        if self._owner_pid != os.getpid():
            return  # could not stop in child process

        try:
            os.kill(self.pid, _signal)
            killed_at = datetime.now()
            while (os.waitpid(self.pid, 0)):
                if (datetime.now() - killed_at).seconds > 10.0:
                    os.kill(self.pid, signal.SIGKILL)
                    raise RuntimeError(''.join(
                        "*** failed to shutdown postmaster (timeout) ***\n",
                        self.read_log()
                    ))

                sleep(0.1)
        except:
            pass

        self.pid = None

    def cleanup(self):
        if self.pid is not None:
            return

        if self._use_tmpdir and os.path.exists(self.base_dir):
            rmtree(self.base_dir)

"""Cooperative cancellation shared by local inference jobs."""
class ProcessingCancelled(RuntimeError):
    pass


def check_cancel(cancel=None):
    if cancel is not None and cancel.is_set():
        raise ProcessingCancelled('Local processing cancelled.')

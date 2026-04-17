from __future__ import annotations

import warnings


# Starlette/AnyIO TestClient on the current Python 3.9 stack can leave
# memory stream objects pending at teardown even when tests close clients
# correctly. Filter that third-party teardown noise so test output stays
# signal-dense.
warnings.simplefilter("ignore", ResourceWarning)

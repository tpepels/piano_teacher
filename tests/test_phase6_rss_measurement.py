"""RSS release limits must use the benchmark child's own process image."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from test_phase6_score_performance import _fresh_process_rss_peak_mb


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux-specific VmHWM")
def test_memory_budget_reads_process_vm_hwm_instead_of_inherited_rusage():
    values = [line.split() for line in Path("/proc/self/status").read_text().splitlines()
              if line.startswith("VmHWM:")]
    assert len(values) == 1 and values[0][2] == "kB"
    direct_mb = round(int(values[0][1]) / 1024.0, 1)
    observed_mb = _fresh_process_rss_peak_mb()
    # VmHWM may increase by a few pages while parsing /proc, so compare
    # independently observed peak snapshots without requiring exact equality.
    assert direct_mb <= observed_mb <= direct_mb + 0.5

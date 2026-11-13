import json
import time
import tracemalloc

from learning_statistics_fixture import populate
from piano_teacher.progress_repository import ProgressRepository


def test_large_ledger_has_bounded_window_bytes_observations_and_read_cost(tmp_path):
    from piano_teacher.learning_statistics import learning_statistics
    path = tmp_path / "large.db"
    populate(path)
    repository = ProgressRepository(path)
    changes = repository.db.total_changes
    tracemalloc.start()
    started = time.perf_counter()
    report = learning_statistics(repository.ledger, query={"limit": 1000})
    elapsed = time.perf_counter()-started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    encoded = len(json.dumps(report))
    print(f"LEARNING_STATISTICS_RESOURCE attempts=5000 selected=1000 elapsed_ms={elapsed*1000:.1f} peak_mib={peak/2**20:.2f} report_bytes={encoded} detail_bytes={report['coverage']['detail_bytes_read']}")
    assert repository.db.total_changes == changes
    assert report["attempts"]["count"] == 1000
    assert report["query"]["has_more"]
    assert report["coverage"]["detail_bytes_read"] <= 2*1024*1024
    assert report["coverage"]["observation_count"] <= 10000
    assert report["coverage"]["detail_budget_truncated_attempts"] > 0
    assert elapsed < 8, "Finite resource envelope on the 5000-attempt fixture (with tracemalloc)"
    assert peak < 96*1024*1024
    assert encoded < 8*1024*1024
    assert learning_statistics(repository.ledger)["attempts"]["count"] == 250
    repository.close()

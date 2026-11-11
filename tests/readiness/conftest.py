# R1 readiness sweep harness (run_sweep.sh, r1_sweep.gd, analyze.py,
# preview.py, pyhook/sitecustomize.py). These drive the real application and
# are not pytest tests; keep ci-full from collecting anything here.
collect_ignore_glob = ["*"]

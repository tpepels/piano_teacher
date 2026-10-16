extends SceneTree

var failures: Array[String] = []

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("LISTEN_SYNC_FAIL: ", description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Monitor = load("res://listen_sync.gd")
    check(Monitor != null, "Listen sync module loads in Godot 4")
    if Monitor == null:
        quit(1)
        return
    var monitor = Monitor.new()
    check(not monitor.evaluate(.1, 0, 10, 1000),
        "Ignore noisy audio startup before one buffer settles")
    check(not monitor.evaluate(1.0, .81, 10, 1200),
        "Normal sub-200ms audio jitter cannot cause a seek")
    check(not monitor.evaluate(2.0, 1.70, 10, 1400),
        "One outlier cannot seek the player")
    check(not monitor.evaluate(2.2, 1.90, 10, 1600),
        "Two outliers still cannot seek")
    check(monitor.evaluate(2.4, 2.10, 10, 1800),
        "A persistent 300ms phase error causes one bounded correction")
    check(monitor.corrections == 1, "One correction only after three outliers")
    check(not monitor.evaluate(3.0, 2.7, 10, 2000),
        "Rate limit repeated seeks")
    check(not monitor.evaluate(3.2, 2.9, 10, 2200),
        "Rate limit must continue across later samples")
    check(not monitor.evaluate(3.4, 3.1, 10, 2400),
        "Cannot seek again before cooldown")
    check(not monitor.evaluate(3.6, 3.48, 10, 2600),
        "Small phase error resets accumulated outliers")
    check(not monitor.evaluate(4.0, 3.7, 10, 3700),
        "After stability another isolated outlier is harmless")
    check(not monitor.evaluate(4.2, 3.9, 10, 3900),
        "A second distant outlier is also harmless")
    check(monitor.evaluate(4.4, 4.1, 10, 4100),
        "Persistent drift after cooldown may correct again")
    check(not monitor.evaluate(9.8, 9.1, 10, 5000),
        "No audible seek close to the end of a musical passage")
    check(not monitor.evaluate(INF, 0, 10, 5200),
        "Invalid measured clock never seeks")
    check(monitor.report()["physical_latency_measured"] == false,
        "Software drift report cannot claim a physical-latency measurement")
    monitor.reset_session()
    check(monitor.corrections == 0 and monitor.peak_error_s == 0,
        "New Listen token clears all previous drift statistics")
    print("LISTEN_SYNC_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)

import numpy as np

from validate import metrics


def test_binary_counts():
    c = metrics.binary_counts([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert (c["hits"], c["misses"], c["false_alarms"], c["correct_quiet"], c["n"]) == (2, 1, 1, 1, 5)
    assert c["hit_rate"] == 2 / 3 and c["false_alarm_ratio"] == 1 / 3
    empty = metrics.binary_counts([0, 0], [0, 0])
    assert empty["hit_rate"] is None and empty["false_alarm_ratio"] is None


def _case():
    # 4 nights x 8 hours x 1 monitor; observed peaks 50, 3, 40, 2
    obs = np.full((4, 8, 1), 1.0)
    obs[0, 3] = 50; obs[1, 3] = 3; obs[2, 3] = 40; obs[3, 3] = 2
    p50 = np.full((4, 8, 1), 1.0); p50[0, 2] = 35; p50[3, 2] = 31        # hit, quiet, miss, false alarm
    p90 = p50 * 3; p90[2, 2] = 60                                         # possible rule also catches night 2
    pers = np.roll(obs, 1, axis=0)                                        # last night's values
    prev = np.array([[2.0], [50.0], [3.0], [40.0]])
    return obs, p50, p90, pers, prev


def test_evaluate_scores_all_methods_on_the_same_nights():
    obs, p50, p90, pers, prev = _case()
    pers[1] = np.nan                                                      # persistence missing -> night 1 dropped for all
    r = metrics.evaluate(obs, {"model": p50, "persistence": pers}, prev, ["a"], None, {"model_possible": p90})
    assert r["eligible"][:, 0].tolist() == [True, False, True, True]
    b = r["binary"]["all_nights"]["all"]
    assert all(v["n"] == 3 for v in b.values())
    assert (b["model_likely"]["hits"], b["model_likely"]["misses"], b["model_likely"]["false_alarms"]) == (1, 1, 1)
    assert b["model_possible"]["hits"] == 2
    assert r["summary"]["model"]["a"]["n_orange_nights"] == 2
    assert set(r["summary"]["model"]["a"]) == {"n_nights", "n_orange_nights", "hit_rate", "false_alarm_ratio",
                                               "category_accuracy", "mae_log"}


def test_after_quiet_night_subset_is_where_persistence_cannot_hit():
    obs, p50, p90, pers, prev = _case()
    r = metrics.evaluate(obs, {"model": p50, "persistence": pers}, prev, ["a"], None, {"model_possible": p90})
    q = r["binary"]["after_quiet_night"]["a"]
    assert q["persistence"]["hits"] == 0 and q["persistence"]["false_alarms"] == 0
    assert q["model_likely"]["n"] == 2 and q["model_likely"]["hits"] == 1   # nights 0 and 2 follow quiet nights


def test_coverage_and_auc():
    obs, p50, p90, pers, prev = _case()
    p90[2, 2] = 30                                                        # night 2 peaked at 40: above its P90
    r = metrics.evaluate(obs, {"model": p50}, prev, ["a"])
    c = metrics.coverage(obs, p90, r["eligible"])
    assert c["night_peak_under_p90"] == 0.75
    assert metrics.auc(np.array([3.0, 1.0, 2.0, 0.0]), np.array([True, False, True, False])) == 1.0
    assert metrics.auc(np.array([1.0, 2.0]), np.array([True, True])) is None

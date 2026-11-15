"""Tests for BellPair-Factory (pure stdlib, deterministic)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as m


# ---- physics layer (cross-checked vs EntangleNet-Q) ----

def test_werner_roundtrip():
    assert abs(m.werner_w_from_fidelity(m.werner_fidelity_from_w(0.6)) - 0.6) < 1e-12


def test_purify_threshold_behavior():
    assert m.purify_fidelity(0.8) > 0.8
    assert abs(m.purify_fidelity(0.5) - 0.5) < 1e-12
    assert m.purify_fidelity(0.4) < 0.4


def test_purify_rounds_entanglenet_value():
    assert abs(m.purify_rounds(0.75, 6) - 0.9446) < 1e-3


def test_teleport_entanglenet_values():
    assert abs(m.teleport_fidelity_from_pair(0.75) - 0.8333) < 1e-3
    assert abs(m.teleport_fidelity_from_pair(m.purify_rounds(0.75, 6)) - 0.9631) < 1e-3


def test_teleport_classical_limit():
    assert abs(m.teleport_fidelity_from_pair(0.5) - 2.0 / 3.0) < 1e-12
    assert m.teleport_fidelity_from_pair(0.4) < 2.0 / 3.0
    assert m.teleport_fidelity_from_pair(1.0) == 1.0


def test_decay_behavior():
    assert m.decayed_fidelity(0.85, 0.0) == 0.85
    assert m.decayed_fidelity(0.85, 0.1) > m.decayed_fidelity(0.85, 0.5)
    assert abs(m.decayed_fidelity(0.9, 50.0) - 0.25) < 1e-6


# ---- production lines ----

def test_sources_tradeoff():
    tab = m.sources_table()
    assert len(tab) == 4
    assert tab["ion-trap-line"]["fidelity"] > tab["spdc-line-a"]["fidelity"]
    assert tab["quantum-dot-line"]["rate_per_s"] > tab["spdc-line-a"]["rate_per_s"]
    assert tab["spdc-line-a"]["fidelity"] == 0.75


def test_unknown_source_rejected():
    try:
        m.source("laser-pointer-line")
    except ValueError:
        return
    raise AssertionError("unknown source must raise ValueError")


# ---- purification economics ----

def test_pairs_expected():
    assert m.pairs_expected(0.75, 0) == 1.0
    assert m.pairs_expected(0.75, 3) > m.pairs_expected(0.75, 1) > 1.0
    assert abs(m.pairs_expected(0.75, 6) - 223.99) < 0.5


def test_rounds_to_target():
    rounds, F = m.rounds_to_target(0.75, 0.90)
    assert rounds == 5 and abs(F - 0.9232) < 1e-3
    assert m.rounds_to_target(0.95, 0.90) == (0, 0.95)
    assert m.rounds_to_target(0.68, 0.97)[0] is None


def test_purification_table():
    tab = m.purification_table("spdc-line-a")
    assert len(tab) == 7
    assert abs(tab[6]["fidelity"] - 0.9446) < 1e-3
    assert tab[0]["output_rate_per_s"] > tab[6]["output_rate_per_s"]


# ---- swapping chains ----

def test_swap_chain_raw_below_classical():
    chain = m.swap_chain([0.75] * 4)
    assert abs(chain["end_fidelity"] - 0.3981) < 1e-3
    assert chain["beats_classical_limit"] is False
    assert abs(chain["success_probability"] - 0.9 ** 3) < 1e-6


def test_swap_chain_purified_above_classical():
    chain = m.swap_chain([m.purify_rounds(0.75, 6)] * 4)
    assert chain["beats_classical_limit"] is True
    assert chain["end_fidelity"] > 0.80


def test_swap_single_pair():
    chain = m.swap_chain([0.9])
    assert chain["swaps"] == 0 and chain["success_probability"] == 1.0


# ---- throughput planner ----

def test_plan_spdc_one_line():
    plan = m.plan_factory("spdc-line-a", 10, 0.90)
    assert plan["feasible"] and plan["one_line_enough"]
    assert plan["rounds"] == 5
    assert plan["raw_pairs_per_s_needed"] <= 1200.0


def test_plan_scales():
    assert m.plan_factory("spdc-line-a", 100, 0.90)["lines_needed"] >= 8


def test_plan_ion_direct():
    plan = m.plan_factory("ion-trap-line", 10, 0.90)
    assert plan["rounds"] == 0 and plan["pairs_expected_per_delivered"] == 1.0
    assert plan["cost_per_delivered"] == 25.0


def test_plan_unreachable():
    plan = m.plan_factory("quantum-dot-line", 10, 0.97)
    assert plan["feasible"] is False and "unreachable" in plan["reason"]


def test_factory_report():
    rep = m.factory_report(0.90)
    assert rep["lines"]["ion-trap-line"]["output_rate_per_s"] == 40.0
    assert rep["lines"]["quantum-dot-line"]["feasible"] is False


# ---- output queue + memory decay ----

def test_queue_balanced():
    q = m.simulate_queue("spdc-line-a", 1200.0, 0.25)
    assert q["discarded"] == 0 and q["delivered"] > 0
    assert q["avg_delivered_fidelity"] > 0.74


def test_queue_backlog_discards():
    q = m.simulate_queue("quantum-dot-line", 800.0, 0.5)
    assert q["produced"] == 2500
    assert q["discarded"] > 0 and q["queued_end"] > 0
    assert q["avg_delivered_fidelity"] < 0.68
    assert q["produced"] == q["delivered"] + q["discarded"] + q["queued_end"]


def test_queue_starved():
    q = m.simulate_queue("ion-trap-line", 5000.0, 0.25)
    assert q["queued_end"] == 0 and q["delivered"] == q["produced"]


def test_queue_deterministic():
    a = m.simulate_queue("quantum-dot-line", 800.0, 0.5)
    b = m.simulate_queue("quantum-dot-line", 800.0, 0.5)
    assert a == b


# ---- quality grading ----

def test_grade_bands():
    assert m.grade_pair(0.97) == "A"
    assert m.grade_pair(0.90) == "B"
    assert m.grade_pair(0.80) == "C"
    assert m.grade_pair(0.65) == "D"
    assert m.grade_pair(0.55) == "REJECT"


def test_grade_batch():
    gb = m.grade_batch(m.demo_batch_fidelities())
    assert gb["counts"] == {"A": 1, "B": 3, "C": 1, "D": 2, "REJECT": 2}
    assert gb["usable"] == 7 and gb["total"] == 9


# ---- cost / yield accounting ----

def test_account_batch():
    acc = m.account_batch("spdc-line-a", 10000, 5)
    assert abs(acc["delivered_expected"] - 10000 / m.pairs_expected(0.75, 5)) < 0.01
    assert acc["total_cost"] == 10000.0
    assert abs(acc["cost_per_delivered"] - m.pairs_expected(0.75, 5)) < 1e-3


# ---- classifier ----

def test_classifier_labels():
    reg = m.regime_report()
    assert reg["ion_trap_premium"] == "direct-use"
    assert reg["nv_midrange"] == "purify-light"
    assert reg["spdc_workhorse"] == "purify-heavy"
    assert reg["dot_bulk_overreach"] == "infeasible"


# ---- gates and seats ----

def test_hold_gates():
    assert len(m.HOLD_GATES) == 14
    assert m.gate("real_quantum_hardware") == "HOLD"
    assert m.gate("live_network_control") == "HOLD"
    assert m.gate("run_simulation") == "PROCEED"


def test_seats_never_override():
    b = m.brains_report()
    assert b["decider"]["can_override_hold"] is False
    assert b["advisor"]["can_override_hold"] is False
    assert b["flow"]["rendered"] is False and b["flow"]["live"] == 0


def test_demo_runs(capsys):
    assert m.demo() == 0
    out = capsys.readouterr().out
    assert "CHECKS 53/53" in out and "VERDICT PROCEED" in out


def test_hold_demo_exit_codes():
    assert m.main(["hold-demo", "real_quantum_hardware"]) == 2
    assert m.main(["hold-demo", "run_simulation"]) == 0

#!/usr/bin/env python3
"""BellPair-Factory - educational Bell pair / entanglement factory lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
This is the SUPPLY layer of Darion's quantum network stack:

  * TeleportX            = the teleportation protocol (one hop).
  * EntangleNet-Q        = the physics layer (links, swapping,
                           DEJMPS purification, memory decay).
  * TeleportNet-Router   = the routing layer (sessions, paths,
                           deadlines, contention).
  * BellPair-Factory     = the FACTORY layer underneath all of
                           them: where do the raw Bell pairs come
                           from, at what fidelity, at what rate,
                           at what cost - and what does it take to
                           turn raw production into delivered
                           pairs good enough to teleport with?

The factory questions this lab answers, with real arithmetic:

  * four production lines (SPDC photon, trapped-ion, NV-center,
    quantum-dot), each with its own raw fidelity, pair rate and
    cost per raw pair (all labeled SIM parameters)
  * DEJMPS purification economics: fidelity gain per round vs the
    raw pairs each round consumes (2 / P_success per round)
  * entanglement swapping chains built from factory pairs - and
    why a raw chain falls below the classical teleport limit
  * a throughput planner: raw pairs/sec and production lines
    needed to sustain a teleportation session rate at a target
    fidelity
  * memory decoherence while pairs WAIT in the output queue:
    a backlog is not free inventory, it is decaying inventory
  * quality grading (A / B / C / D / REJECT) and cost / yield
    accounting per delivered pair

All pair physics is the Werner-state model simulation-verified
in EntangleNet-Q (Werner weight product rule for swapping, DEJMPS
purification map + success probability, teleport output fidelity
(2F + 1)/3, memory decay exp(-t / T2)). The headline numbers
cross-check against EntangleNet-Q's published results: a raw
pair at F = 0.75 purifies to F = 0.9446 in 6 DEJMPS rounds, and
the classical teleport limit is 2/3 = 0.6667.

Honest scope: no production quantum hardware is operated here,
no real entanglement factory exists as a service, and nothing in
this lab controls a real source, detector, repeater, or network.
Every live / product claim is a permanent HOLD gate (14 total).

Seats: Gemini Carbon 4 DECIDER (names-only, tighten-only), Muse
advisor (never overrides HOLD), Google Flow plan-only.
"""
import hashlib
import json
import math
import sys

VERSION = "1.0.0"

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "real_quantum_hardware": "HOLD - no control of any real quantum hardware (sources, detectors, repeaters), ever",
    "live_network_control": "HOLD - no control of any live quantum or classical network, ever",
    "claim_production_factory": "HOLD - no production entanglement factory or supply service exists; this is a simulation lab",
    "guaranteed_fidelity_claim": "HOLD - fidelities here are model estimates under labeled assumptions, never guarantees",
    "guaranteed_rate_claim": "HOLD - production rates here are labeled simulation parameters, never promised output",
    "teleport_matter_claim": "HOLD - no teleporting matter; only quantum states of simulated qubits are produced",
    "teleport_living_being_claim": "HOLD - no teleporting living beings, ever",
    "claim_ftl_communication": "HOLD - entanglement never sends information faster than light; teleportation needs a classical channel",
    "live_qkd_key_use": "HOLD - no generating or using real cryptographic keys for real traffic",
    "commercial_service_claim": "HOLD - no commercial entanglement supply service is offered or implied",
    "bypass_no_cloning_claim": "HOLD - the no-cloning theorem is not bypassed; purification consumes pairs, it never copies them",
    "live_satellite_link": "HOLD - no commanding or tasking any real satellite link",
    "intercept_traffic_claim": "HOLD - no intercepting, decrypting, or monitoring anyone's real traffic",
    "medical_data_transport_claim": "HOLD - no claims about transporting real medical or personal data",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ physics layer
# Inherited from EntangleNet-Q, where every formula below was
# verified against a from-scratch statevector / density-matrix
# simulator (swapping product rule to 1e-9, DEJMPS map and success
# probability to 1e-9, teleport circuit vs (2F + 1)/3 to 1e-9).
# A pair is a Werner state: rho = w |phi+><phi+| + (1-w) I/4,
# fidelity F = (1 + 3w)/4.

MEMORY_T2_S = 1.0               # memory coherence time, seconds (sim parameter)
MAX_PURIFY_ROUNDS = 6           # factory policy cap per delivered pair
SWAP_SUCCESS_P = 0.90           # per-swap success probability (sim parameter)
CLASSICAL_LIMIT = 2.0 / 3.0     # best classical teleport fidelity


def werner_w_from_fidelity(F):
    if not 0.25 <= F <= 1.0:
        raise ValueError("Werner fidelity must be in [0.25, 1]")
    return (4.0 * F - 1.0) / 3.0


def werner_fidelity_from_w(w):
    return (1.0 + 3.0 * w) / 4.0


def purify_fidelity(F):
    """Fidelity after one successful DEJMPS round on two Werner pairs."""
    if not 0.25 <= F <= 1.0:
        raise ValueError("Werner fidelity must be in [0.25, 1]")
    third = (1.0 - F) / 3.0
    num = F * F + third * third
    den = F * F + (2.0 / 3.0) * F * (1.0 - F) + 5.0 * third * third
    return num / den


def purify_success_prob(F):
    """Probability the two measurement outcomes agree (pair is kept)."""
    if not 0.25 <= F <= 1.0:
        raise ValueError("Werner fidelity must be in [0.25, 1]")
    third = (1.0 - F) / 3.0
    return F * F + (2.0 / 3.0) * F * (1.0 - F) + 5.0 * third * third


def purify_rounds(F, rounds):
    """Fidelity after `rounds` successful purification rounds."""
    for _ in range(rounds):
        F = purify_fidelity(F)
    return F


def chain_w(weights):
    """End-to-end Werner weight of a swapped chain: product of weights."""
    w = 1.0
    for x in weights:
        w *= x
    return w


def chain_fidelity(fidelities):
    """End-to-end fidelity of a chain of Werner pairs (product rule)."""
    return werner_fidelity_from_w(chain_w([werner_w_from_fidelity(f)
                                           for f in fidelities]))


def teleport_fidelity_from_pair(F):
    """Average teleportation fidelity using a Werner pair of fidelity F."""
    return (2.0 * F + 1.0) / 3.0


def decayed_fidelity(F, wait_s, t2=MEMORY_T2_S):
    """Fidelity of a Werner pair after waiting `wait_s` in memory.

    The Werner weight decays: w(t) = w0 * exp(-t / T2). A pair that
    waits long enough decays toward the maximally mixed floor
    F = 0.25 - inventory on the shelf is inventory going bad.
    """
    if wait_s < 0:
        raise ValueError("wait time must be non-negative")
    return werner_fidelity_from_w(werner_w_from_fidelity(F)
                                  * math.exp(-wait_s / t2))


# ================================================================ production lines
# Four labeled SIM production lines. Each trades fidelity against
# rate against cost - there is no free corner of the triangle:
#   spdc-line-a       the workhorse: EntangleNet-Q's raw pair
#                     (F = 0.75) at a solid rate, mid cost
#   ion-trap-line     premium: near-perfect pairs, painfully slow
#   nv-center-line    midrange: good fidelity, modest rate
#   quantum-dot-line  bulk: firehose rate, noisy pairs, cheap -
#                     purification and queue decay eat the savings

SOURCES = {
    "spdc-line-a": {
        "kind": "SPDC photon-pair source",
        "fidelity": 0.75,
        "rate_per_s": 1200.0,
        "cost_per_pair": 1.0,
    },
    "ion-trap-line": {
        "kind": "trapped-ion pair source",
        "fidelity": 0.95,
        "rate_per_s": 40.0,
        "cost_per_pair": 25.0,
    },
    "nv-center-line": {
        "kind": "NV-center diamond pair source",
        "fidelity": 0.85,
        "rate_per_s": 300.0,
        "cost_per_pair": 4.0,
    },
    "quantum-dot-line": {
        "kind": "quantum-dot pair source",
        "fidelity": 0.68,
        "rate_per_s": 5000.0,
        "cost_per_pair": 0.2,
    },
}


def source(name):
    if name not in SOURCES:
        raise ValueError("unknown source %r (have: %s)"
                         % (name, ", ".join(sorted(SOURCES))))
    return SOURCES[name]


def sources_table():
    """All production lines with their raw teleport quality."""
    out = {}
    for name, s in SOURCES.items():
        out[name] = dict(s, teleport_fidelity=round(
            teleport_fidelity_from_pair(s["fidelity"]), 6))
    return out


# ================================================================ purification economics
# DEJMPS is not free fidelity. One round consumes two pairs and
# keeps one only when the measurement outcomes agree, so the
# expected raw pairs behind one delivered pair multiply by
# 2 / P_success(F) at the fidelity entering EVERY round. Fidelity
# climbs; the pair bill compounds. That trade is the factory's
# central economic fact.

def pairs_expected(F0, rounds):
    """Expected raw pairs consumed to deliver one purified pair."""
    pairs = 1.0
    F = F0
    for _ in range(rounds):
        pairs *= 2.0 / purify_success_prob(F)
        F = purify_fidelity(F)
    return pairs


def rounds_to_target(F0, target_F, max_rounds=MAX_PURIFY_ROUNDS):
    """Smallest round count reaching `target_F`, or (None, best F).

    Returns (rounds, fidelity_after). DEJMPS only helps above
    F = 0.5 and converges slowly, so some targets are honestly
    unreachable inside the factory's round cap.
    """
    F = F0
    if F >= target_F:
        return 0, F
    for r in range(1, max_rounds + 1):
        F = purify_fidelity(F)
        if F >= target_F:
            return r, F
    return None, F


def purification_table(source_name, max_rounds=MAX_PURIFY_ROUNDS):
    """Round-by-round economics for one production line."""
    s = source(source_name)
    rows = []
    F = s["fidelity"]
    for r in range(max_rounds + 1):
        pe = pairs_expected(s["fidelity"], r)
        rows.append({
            "rounds": r,
            "fidelity": round(F, 6),
            "pairs_expected": round(pe, 4),
            "output_rate_per_s": round(s["rate_per_s"] / pe, 4),
            "cost_per_delivered": round(s["cost_per_pair"] * pe, 4),
            "teleport_fidelity": round(teleport_fidelity_from_pair(F), 6),
        })
        F = purify_fidelity(F)
    return rows


# ================================================================ swapping chains
# The factory's pairs feed repeater chains: n pairs, n-1 swaps.
# Werner weights multiply, so chain fidelity falls off fast with
# raw pairs - the arithmetic reason purification happens at the
# factory, before the chain, not as an afterthought.

def swap_chain(fidelities, swap_success_p=SWAP_SUCCESS_P):
    """Swap a chain of factory pairs end to end.

    Returns end-to-end fidelity, its teleport quality, the chain
    success probability (every swap must succeed), and the
    expected number of full-chain attempts per success.
    """
    if not fidelities:
        raise ValueError("a chain needs at least one pair")
    swaps = len(fidelities) - 1
    p = swap_success_p ** swaps
    F = chain_fidelity(fidelities)
    return {
        "pairs": len(fidelities),
        "swaps": swaps,
        "end_fidelity": round(F, 6),
        "teleport_fidelity": round(teleport_fidelity_from_pair(F), 6),
        "beats_classical_limit": teleport_fidelity_from_pair(F) > CLASSICAL_LIMIT,
        "success_probability": round(p, 6),
        "expected_attempts": round(1.0 / p, 4),
    }


# ================================================================ throughput planner
# The operator's question: "TeleportNet-Router wants N sessions
# per second, each burning pairs_per_session pairs at fidelity
# >= target. Can this line feed it - and if not, how many lines?"
# The planner prices purification first (rounds + pair bill),
# then divides by the line rate. No hand-waving: a shortfall is
# reported as a shortfall, with the line count that closes it.

def plan_factory(source_name, sessions_per_s, target_F, pairs_per_session=1,
                 max_rounds=MAX_PURIFY_ROUNDS):
    """Plan production to sustain a teleportation session rate."""
    s = source(source_name)
    rounds, F_after = rounds_to_target(s["fidelity"], target_F, max_rounds)
    base = {"source": source_name, "sessions_per_s": sessions_per_s,
            "target_fidelity": target_F, "pairs_per_session": pairs_per_session}
    if rounds is None:
        return dict(base, feasible=False, rounds=None,
                    best_fidelity=round(F_after, 6),
                    reason="target fidelity unreachable from raw F = %.2f "
                           "within %d purification rounds"
                           % (s["fidelity"], max_rounds))
    pe = pairs_expected(s["fidelity"], rounds)
    raw_needed = sessions_per_s * pairs_per_session * pe
    lines = max(1, math.ceil(raw_needed / s["rate_per_s"]))
    return dict(base, feasible=True, rounds=rounds,
                fidelity_after=round(F_after, 6),
                pairs_expected_per_delivered=round(pe, 4),
                raw_pairs_per_s_needed=round(raw_needed, 2),
                line_rate_per_s=s["rate_per_s"],
                lines_needed=lines,
                one_line_enough=lines == 1,
                utilization_of_last_line=round(
                    raw_needed / (lines * s["rate_per_s"]), 6),
                cost_per_delivered=round(s["cost_per_pair"] * pe, 4),
                cost_per_s=round(raw_needed * s["cost_per_pair"], 2))


def factory_report(target_F=0.90):
    """Every line priced at one delivery target, side by side."""
    out = {"target_fidelity": target_F, "lines": {}}
    for name in SOURCES:
        s = SOURCES[name]
        rounds, F_after = rounds_to_target(s["fidelity"], target_F)
        if rounds is None:
            out["lines"][name] = {"feasible": False,
                                  "best_fidelity": round(F_after, 6)}
            continue
        pe = pairs_expected(s["fidelity"], rounds)
        out["lines"][name] = {
            "feasible": True,
            "rounds": rounds,
            "fidelity_after": round(F_after, 6),
            "pairs_expected": round(pe, 4),
            "output_rate_per_s": round(s["rate_per_s"] / pe, 4),
            "cost_per_delivered": round(s["cost_per_pair"] * pe, 4),
        }
    return out


# ================================================================ output queue + memory decay
# Produced pairs wait in a FIFO output queue until a session
# consumes them. Waiting is decay: w(t) = w0 * exp(-t / T2).
# Produce faster than you consume and the queue becomes a
# warehouse of expiring pairs - the tail of the queue decays
# below the grading threshold and is discarded. This discrete
# simulation is deterministic: fixed dt, accumulator production
# and consumption, no randomness anywhere.

QUEUE_DT_S = 0.001


def simulate_queue(source_name, consumption_rate, duration_s,
                   reject_below=0.60, t2=MEMORY_T2_S):
    """Simulate one line feeding a FIFO queue for `duration_s`.

    Pairs are graded on ARRIVAL at the consumer: a pair whose
    decayed fidelity fell below `reject_below` while waiting is
    discarded instead of delivered.
    """
    s = source(source_name)
    queue = []            # birth times, FIFO (index 0 = oldest)
    head = 0              # consumed/discarded prefix length
    produced = delivered = discarded = 0
    wait_sum = 0.0
    fid_sum = 0.0
    prod_acc = 0.0
    cons_acc = 0.0
    steps = int(round(duration_s / QUEUE_DT_S))
    for i in range(steps):
        now = (i + 1) * QUEUE_DT_S
        prod_acc += s["rate_per_s"] * QUEUE_DT_S
        while prod_acc >= 1.0:
            prod_acc -= 1.0
            queue.append(now)
            produced += 1
        if head < len(queue):
            cons_acc += consumption_rate * QUEUE_DT_S
        else:
            cons_acc = 0.0
        while cons_acc >= 1.0 and head < len(queue):
            cons_acc -= 1.0
            birth = queue[head]
            head += 1
            wait = now - birth
            F = decayed_fidelity(s["fidelity"], wait, t2)
            if F < reject_below:
                discarded += 1
            else:
                delivered += 1
                wait_sum += wait
                fid_sum += F
    return {
        "source": source_name,
        "production_rate_per_s": s["rate_per_s"],
        "consumption_rate_per_s": consumption_rate,
        "duration_s": duration_s,
        "produced": produced,
        "delivered": delivered,
        "discarded": discarded,
        "queued_end": len(queue) - head,
        "avg_wait_s": round(wait_sum / delivered, 6) if delivered else 0.0,
        "avg_delivered_fidelity": round(fid_sum / delivered, 6) if delivered else 0.0,
        "yield_fraction": round(delivered / produced, 6) if produced else 0.0,
    }


# ================================================================ quality grading
# Every delivered pair gets a grade from its fidelity at hand-off.
# Grade D is the floor: below REJECT_BELOW the pair cannot beat
# the classical teleport limit by enough margin to be worth a
# session slot, and the factory says so instead of shipping it.

GRADE_BANDS = [(0.95, "A"), (0.85, "B"), (0.75, "C"), (0.60, "D")]
REJECT_BELOW = 0.60


def grade_pair(F, reject_below=REJECT_BELOW):
    """Letter grade for one pair's fidelity."""
    if F < reject_below:
        return "REJECT"
    for floor, label in GRADE_BANDS:
        if F >= floor:
            return label
    return "REJECT"


def grade_batch(fidelities, reject_below=REJECT_BELOW):
    """Grade a batch: counts per grade + usable fraction."""
    counts = {"A": 0, "B": 0, "C": 0, "D": 0, "REJECT": 0}
    for F in fidelities:
        counts[grade_pair(F, reject_below)] += 1
    total = len(fidelities)
    usable = total - counts["REJECT"]
    return {"counts": counts, "total": total, "usable": usable,
            "usable_fraction": round(usable / total, 6) if total else 0.0}


# ================================================================ cost / yield accounting
# The ledger view: run a batch of raw pairs through r purification
# rounds and count what comes out the other side - expected
# delivered pairs, yield, total cost, and the honest cost of one
# delivered pair (the number a customer would actually pay).

def account_batch(source_name, raw_pairs, rounds):
    """Expected yield + cost ledger for one production batch."""
    s = source(source_name)
    pe = pairs_expected(s["fidelity"], rounds)
    delivered = raw_pairs / pe
    total_cost = raw_pairs * s["cost_per_pair"]
    return {
        "source": source_name,
        "raw_pairs": raw_pairs,
        "rounds": rounds,
        "fidelity_after": round(purify_rounds(s["fidelity"], rounds), 6),
        "pairs_expected_per_delivered": round(pe, 4),
        "delivered_expected": round(delivered, 2),
        "yield_fraction": round(1.0 / pe, 6),
        "total_cost": round(total_cost, 2),
        "cost_per_delivered": round(total_cost / delivered, 4) if delivered else 0.0,
        "cost_unit": "sim credits",
    }


# ================================================================ production-regime classifier (TinyML kNN)
# Features: (raw fidelity, rate / 1000 pairs-per-s, target
# fidelity). Labels: direct-use / purify-light / purify-heavy /
# infeasible. Tiny labeled set, euclidean kNN, k=3. Advisory
# only - the planner's exact arithmetic always outranks it.

KNN_TRAINING = [
    ((0.95, 0.04, 0.90), "direct-use"),
    ((0.93, 0.10, 0.88), "direct-use"),
    ((0.97, 0.02, 0.95), "direct-use"),
    ((0.90, 0.30, 0.85), "direct-use"),
    ((0.85, 0.30, 0.90), "purify-light"),
    ((0.87, 0.25, 0.92), "purify-light"),
    ((0.83, 0.50, 0.88), "purify-light"),
    ((0.88, 0.20, 0.90), "purify-light"),
    ((0.75, 1.20, 0.90), "purify-heavy"),
    ((0.72, 1.00, 0.88), "purify-heavy"),
    ((0.78, 0.80, 0.92), "purify-heavy"),
    ((0.70, 2.00, 0.90), "purify-heavy"),
    ((0.68, 5.00, 0.97), "infeasible"),
    ((0.60, 4.00, 0.95), "infeasible"),
    ((0.75, 1.20, 0.99), "infeasible"),
    ((0.55, 3.00, 0.90), "infeasible"),
]


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def classify_regime(features, k=3):
    """kNN regime from (raw fidelity, rate/1000, target fidelity)."""
    ranked = sorted(KNN_TRAINING, key=lambda row: _dist(features, row[0]))
    votes = {}
    for _, label in ranked[:k]:
        votes[label] = votes.get(label, 0) + 1
    return sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def regime_report():
    scenarios = {
        "ion_trap_premium": (0.95, 0.04, 0.90),
        "nv_midrange": (0.85, 0.30, 0.90),
        "spdc_workhorse": (0.75, 1.20, 0.90),
        "dot_bulk_overreach": (0.68, 5.00, 0.97),
    }
    return {name: classify_regime(f) for name, f in scenarios.items()}


# ================================================================ advisory seats
def _trace(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def carbon4_decide(topic="bellpair-factory-demo"):
    """Gemini Carbon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-carbon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Carbon 4 Extended Thinking",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all real-hardware and live-network gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="bellpair-factory-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Price purification in raw pairs before promising a session rate; treat the output queue as decaying inventory, not storage; and grade pairs at hand-off, because the fidelity on the production ticket is not the fidelity the session receives.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["four production lines light up at different speeds",
                  "raw pairs enter the purification hall",
                  "each DEJMPS round halves the stream and lifts fidelity",
                  "the output queue glows dimmer as pairs wait and decay",
                  "graded pairs ship to the router, rejects fall away"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": carbon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ demo scenarios
def demo_batch_fidelities():
    """A deterministic mixed hand-off batch for the grading demo."""
    return [0.97, 0.9446, 0.90, 0.85, 0.75, 0.68, 0.62, 0.55, 0.40]


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # physics layer cross-checks vs EntangleNet-Q's sim-verified numbers
    chk("werner_roundtrip", abs(werner_w_from_fidelity(werner_fidelity_from_w(0.6)) - 0.6) < 1e-12)
    chk("purify_improves_above_half", purify_fidelity(0.8) > 0.8)
    chk("purify_fixed_point_half", abs(purify_fidelity(0.5) - 0.5) < 1e-12)
    chk("purify_worsens_below_half", purify_fidelity(0.4) < 0.4)
    chk("purify_rounds_entanglenet_value", abs(purify_rounds(0.75, 6) - 0.9446) < 1e-3)
    chk("teleport_raw_pair_entanglenet_value",
        abs(teleport_fidelity_from_pair(0.75) - 0.8333) < 1e-3)
    chk("teleport_purified_entanglenet_value",
        abs(teleport_fidelity_from_pair(purify_rounds(0.75, 6)) - 0.9631) < 1e-3)
    chk("teleport_classical_limit_exact",
        abs(teleport_fidelity_from_pair(0.5) - CLASSICAL_LIMIT) < 1e-12
        and teleport_fidelity_from_pair(0.4) < CLASSICAL_LIMIT)
    # memory decay
    chk("decay_zero_wait_identity", decayed_fidelity(0.85, 0.0) == 0.85)
    chk("decay_reduces_fidelity",
        decayed_fidelity(0.85, 0.5) < 0.85 and decayed_fidelity(0.85, 0.1)
        > decayed_fidelity(0.85, 0.5))
    chk("decay_long_wait_floor", abs(decayed_fidelity(0.9, 50.0) - 0.25) < 1e-6)
    # production lines
    tab = sources_table()
    chk("sources_four_lines", len(tab) == 4)
    chk("sources_fidelity_rate_tradeoff",
        tab["ion-trap-line"]["fidelity"] > tab["spdc-line-a"]["fidelity"]
        > tab["quantum-dot-line"]["fidelity"]
        and tab["quantum-dot-line"]["rate_per_s"]
        > tab["spdc-line-a"]["rate_per_s"] > tab["ion-trap-line"]["rate_per_s"])
    chk("sources_spdc_is_entanglenet_raw_pair",
        tab["spdc-line-a"]["fidelity"] == 0.75
        and abs(tab["spdc-line-a"]["teleport_fidelity"] - 0.8333) < 1e-3)
    # purification economics
    chk("pairs_expected_grows_with_rounds",
        pairs_expected(0.75, 3) > pairs_expected(0.75, 1) > 1.0)
    chk("pairs_expected_zero_rounds_is_one", pairs_expected(0.75, 0) == 1.0)
    r90 = rounds_to_target(0.75, 0.90)
    chk("rounds_to_target_spdc_five_rounds",
        r90[0] == 5 and abs(r90[1] - 0.9232) < 1e-3)
    chk("rounds_to_target_already_met",
        rounds_to_target(0.95, 0.90) == (0, 0.95))
    chk("rounds_to_target_unreachable",
        rounds_to_target(0.68, 0.97)[0] is None
        and rounds_to_target(0.68, 0.97)[1] < 0.97)
    ptab = purification_table("spdc-line-a")
    chk("purify_table_output_rate_falls",
        ptab[0]["output_rate_per_s"] > ptab[3]["output_rate_per_s"]
        > ptab[6]["output_rate_per_s"])
    chk("purify_table_six_rounds_entanglenet",
        abs(ptab[6]["fidelity"] - 0.9446) < 1e-3 and ptab[6]["rounds"] == 6)
    # swapping chains
    raw_chain = swap_chain([0.75, 0.75, 0.75, 0.75])
    chk("swap_chain_product_rule",
        abs(raw_chain["end_fidelity"] - chain_fidelity([0.75] * 4)) < 1e-6)
    chk("swap_chain_raw_below_classical",
        raw_chain["beats_classical_limit"] is False
        and raw_chain["teleport_fidelity"] < CLASSICAL_LIMIT)
    pur_chain = swap_chain([purify_rounds(0.75, 6)] * 4)
    chk("swap_chain_purified_above_classical",
        pur_chain["beats_classical_limit"] is True
        and pur_chain["end_fidelity"] > raw_chain["end_fidelity"])
    chk("swap_chain_success_probability",
        abs(raw_chain["success_probability"] - SWAP_SUCCESS_P ** 3) < 1e-6
        and raw_chain["expected_attempts"] > 1.0)
    chk("swap_single_pair_no_swap",
        swap_chain([0.9])["swaps"] == 0
        and swap_chain([0.9])["success_probability"] == 1.0)
    # throughput planner
    plan10 = plan_factory("spdc-line-a", 10, 0.90)
    chk("plan_spdc_sessions_feasible_one_line",
        plan10["feasible"] and plan10["one_line_enough"]
        and plan10["raw_pairs_per_s_needed"] <= 1200.0)
    chk("plan_scales_with_session_rate",
        plan_factory("spdc-line-a", 100, 0.90)["lines_needed"] >= 8)
    plan_ion = plan_factory("ion-trap-line", 10, 0.90)
    chk("plan_ion_direct_no_purification",
        plan_ion["feasible"] and plan_ion["rounds"] == 0
        and plan_ion["pairs_expected_per_delivered"] == 1.0)
    chk("plan_unreachable_flagged",
        plan_factory("quantum-dot-line", 10, 0.97)["feasible"] is False)
    chk("plan_cost_matches_pair_bill",
        abs(plan10["cost_per_delivered"]
            - plan10["pairs_expected_per_delivered"] * 1.0) < 1e-6)
    rep = factory_report(0.90)
    chk("factory_report_all_lines_priced",
        len(rep["lines"]) == 4
        and rep["lines"]["spdc-line-a"]["feasible"]
        and rep["lines"]["nv-center-line"]["feasible"]
        and rep["lines"]["ion-trap-line"]["output_rate_per_s"] == 40.0
        and rep["lines"]["spdc-line-a"]["output_rate_per_s"] < 40.0)
    chk("factory_report_dot_cannot_reach_090",
        rep["lines"]["quantum-dot-line"]["feasible"] is False
        and rep["lines"]["quantum-dot-line"]["best_fidelity"] < 0.90)
    # output queue + memory decay
    q_bal = simulate_queue("spdc-line-a", 1200.0, 0.25)
    chk("queue_balanced_no_discards",
        q_bal["discarded"] == 0 and q_bal["delivered"] > 0
        and q_bal["avg_delivered_fidelity"] > 0.74)
    q_back = simulate_queue("quantum-dot-line", 800.0, 0.5)
    chk("queue_backlog_decays_and_discards",
        q_back["discarded"] > 0 and q_back["queued_end"] > 0
        and q_back["avg_delivered_fidelity"] < 0.68)
    q_starve = simulate_queue("ion-trap-line", 5000.0, 0.25)
    chk("queue_starved_empties",
        q_starve["queued_end"] == 0
        and q_starve["delivered"] == q_starve["produced"])
    chk("queue_deterministic",
        simulate_queue("quantum-dot-line", 800.0, 0.5) == q_back)
    chk("queue_accounting_balances",
        q_back["produced"] == q_back["delivered"] + q_back["discarded"]
        + q_back["queued_end"])
    # quality grading
    chk("grade_bands",
        grade_pair(0.97) == "A" and grade_pair(0.90) == "B"
        and grade_pair(0.80) == "C" and grade_pair(0.65) == "D"
        and grade_pair(0.55) == "REJECT")
    gb = grade_batch(demo_batch_fidelities())
    chk("grade_batch_counts",
        gb["counts"] == {"A": 1, "B": 3, "C": 1, "D": 2, "REJECT": 2}
        and gb["usable"] == 7 and gb["total"] == 9)
    # cost / yield accounting
    acc = account_batch("spdc-line-a", 10000, 5)
    chk("account_batch_yield",
        abs(acc["delivered_expected"]
            - 10000 / pairs_expected(0.75, 5)) < 0.01
        and abs(acc["yield_fraction"] - 1.0 / pairs_expected(0.75, 5)) < 1e-6)
    chk("account_batch_cost_per_delivered",
        abs(acc["cost_per_delivered"] - pairs_expected(0.75, 5) * 1.0) < 1e-3
        and acc["total_cost"] == 10000.0)
    # classifier
    reg = regime_report()
    chk("classifier_direct_use", reg["ion_trap_premium"] == "direct-use")
    chk("classifier_purify_light", reg["nv_midrange"] == "purify-light")
    chk("classifier_purify_heavy", reg["spdc_workhorse"] == "purify-heavy")
    chk("classifier_infeasible", reg["dot_bulk_overreach"] == "infeasible")
    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14 and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_hardware_hold", gate("real_quantum_hardware") == "HOLD")
    chk("gate_network_hold", gate("live_network_control") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    b = brains_report()
    chk("carbon4_no_override", b["decider"]["can_override_hold"] is False)
    chk("claude_no_override", b["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", b["flow"]["rendered"] is False and b["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("BellPair-Factory - educational Bell pair / entanglement factory lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | SIMULATION ONLY")
    print("=" * 68)
    print("\n[1] Production lines (labeled SIM parameters)")
    for name, s in sources_table().items():
        print(f"    {name:18s} {s['kind']:32s} raw F = {s['fidelity']:.2f}, "
              f"{s['rate_per_s']:>7.0f} pairs/s, {s['cost_per_pair']:>5.1f} credits/pair, "
              f"teleport F raw = {s['teleport_fidelity']:.4f}")
    print("    (no free corner: ion trap is near-perfect but slow, the quantum")
    print("     dot is a firehose but noisy, SPDC is the workhorse in between)")
    print("\n[2] Purification economics: SPDC line, raw F = 0.75 (EntangleNet-Q's pair)")
    for row in purification_table("spdc-line-a"):
        print(f"    {row['rounds']} round(s): F = {row['fidelity']:.4f}, "
              f"expected raw pairs per delivered = {row['pairs_expected']:>8.2f}, "
              f"output = {row['output_rate_per_s']:>8.2f} pairs/s, "
              f"cost/delivered = {row['cost_per_delivered']:.2f}")
    print("    6 rounds take F 0.75 -> 0.9446 - EntangleNet-Q's published value -")
    print("    and the pair bill compounds to 224 raw pairs per delivered pair.")
    print("\n[3] Swapping chains built from factory pairs (4 pairs, 3 swaps)")
    raw = swap_chain([0.75] * 4)
    pur = swap_chain([purify_rounds(0.75, 6)] * 4)
    print(f"    raw SPDC pairs:      end F = {raw['end_fidelity']:.4f}, "
          f"teleport F = {raw['teleport_fidelity']:.4f} "
          f"-> BELOW the {CLASSICAL_LIMIT:.4f} classical limit")
    print(f"    purified pairs:      end F = {pur['end_fidelity']:.4f}, "
          f"teleport F = {pur['teleport_fidelity']:.4f} "
          f"-> above the classical limit")
    print(f"    chain success probability = {raw['success_probability']:.4f} "
          f"(expected attempts {raw['expected_attempts']:.2f})")
    print("\n[4] Throughput planner: sustain 10 teleport sessions/s at F >= 0.90")
    for name in SOURCES:
        p = plan_factory(name, 10, 0.90)
        if p["feasible"]:
            print(f"    {name:18s} {p['rounds']} round(s), "
                  f"{p['raw_pairs_per_s_needed']:>9.2f} raw pairs/s needed, "
                  f"lines needed = {p['lines_needed']}, "
                  f"cost/delivered = {p['cost_per_delivered']:.2f}")
        else:
            print(f"    {name:18s} INFEASIBLE - {p['reason']}")
    print("\n[5] Output queue + memory decay (T2 = 1.0 s): inventory expires")
    qb = simulate_queue("spdc-line-a", 1200.0, 0.25)
    print(f"    balanced  (SPDC 1200/s in, 1200/s out, 0.25 s): "
          f"delivered {qb['delivered']}, discarded {qb['discarded']}, "
          f"avg delivered F = {qb['avg_delivered_fidelity']:.4f}")
    qk = simulate_queue("quantum-dot-line", 800.0, 0.5)
    print(f"    backlog   (dot 5000/s in,  800/s out, 0.50 s): "
          f"produced {qk['produced']}, delivered {qk['delivered']}, "
          f"discarded {qk['discarded']}, still queued {qk['queued_end']}, "
          f"avg delivered F = {qk['avg_delivered_fidelity']:.4f}")
    print("    the firehose line floods its own queue: pairs wait, decay below")
    print("    the 0.60 grade floor, and are discarded - yield, not rate, is king.")
    print("\n[6] Quality grading of a mixed hand-off batch")
    gb = grade_batch(demo_batch_fidelities())
    print(f"    batch of {gb['total']}: " + ", ".join(
        f"{k} x {v}" for k, v in gb["counts"].items())
          + f" -> usable {gb['usable']}/{gb['total']}")
    print("\n[7] Cost / yield ledger: 10,000 raw SPDC pairs, 5 purification rounds")
    acc = account_batch("spdc-line-a", 10000, 5)
    print(f"    delivered (expected) = {acc['delivered_expected']:.1f} pairs "
          f"at F = {acc['fidelity_after']:.4f}, yield = {acc['yield_fraction']:.4f}, "
          f"total cost = {acc['total_cost']:.0f} credits, "
          f"cost per delivered = {acc['cost_per_delivered']:.2f} credits")
    print("\n[8] Production-regime classifier (TinyML kNN)")
    for name, label in regime_report().items():
        print(f"    {name:22s} -> {label}")
    print("\n[9] Advisory seats")
    print(f"    decider: {carbon4_decide()['decision']} trace={carbon4_decide()['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {claude_advisor()['can_override_hold']}")
    print(f"    flow rendered = {google_flow_plan()['rendered']} live = {google_flow_plan()['live']}")
    print(f"\n[10] HOLD gates: {len(HOLD_GATES)}")
    for k in HOLD_GATES:
        print(f"    HOLD  {k}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "sources":
        print(json.dumps(sources_table(), indent=2, sort_keys=True))
        return 0
    if cmd == "purify":
        print(json.dumps(purification_table("spdc-line-a"), indent=2, sort_keys=True))
        return 0
    if cmd == "plan":
        print(json.dumps(factory_report(0.90), indent=2, sort_keys=True))
        return 0
    if cmd == "queue":
        print(json.dumps(simulate_queue("quantum-dot-line", 800.0, 0.5),
                         indent=2, sort_keys=True))
        return 0
    if cmd == "swap":
        print(json.dumps({"raw": swap_chain([0.75] * 4),
                          "purified": swap_chain([purify_rounds(0.75, 6)] * 4)},
                         indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(regime_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for k, v in HOLD_GATES.items():
            print(f"{k}: {v}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "real_quantum_hardware"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""tube.py - 12AU7 (ECC82) triode device model for the Duke DI reference.

Koren's empirical triode equation, the standard white-box choice for audio
plate-curve modelling. Parameters are a published 12AU7 set; the starved-heater
operating condition of the Nobelium circuit is applied as an *emission* scaling
(perveance derate) on top, per the plan's "fit perveance empirically" decision.

Everything here is desktop reference math (Tier A). It freely uses exp/log/pow
and division - none of which may appear in the embedded C674x kernel. The
kernel instead reads the *sampled* result of this model from a const LUT.

Koren triode:
    E1 = (Vpk / Kp) * ln(1 + exp(Kp * (1/mu + Vgk / sqrt(Kvb + Vpk^2))))
    Ip = (E1^Ex / Kg1) * (1 + sgn(E1))           [A]
"""
from __future__ import annotations
import numpy as np

# Published Koren parameters for the 12AU7 / ECC82 (Duncan Amps / common sets).
KOREN_12AU7 = dict(mu=21.5, Ex=1.3, Kg1=1180.0, Kp=84.0, Kvb=300.0)

# Starved-heater derate. Heaters run from 9 V through 1 k (R4/R6) instead of a
# 12.6 V/6.3 V rail, so cathode emission is reduced: plate current saturates
# earlier and the stage compresses sooner. Modelled as a perveance (Kg1) boost
# -> lower current for a given drive -> earlier soft limiting. 1.0 == nominal;
# >1.0 == more starved. Fitted against the H2/H3 target in validation; this is
# the provisional starting value, flagged in docs/assumptions.md.
STARVED_KG1_SCALE = 2.6


def plate_current(vgk: np.ndarray, vpk: np.ndarray,
                  p: dict = KOREN_12AU7,
                  kg1_scale: float = STARVED_KG1_SCALE) -> np.ndarray:
    """Koren plate current [A]. vgk, vpk in volts (arrays or scalars)."""
    vpk = np.asarray(vpk, dtype=np.float64)
    vgk = np.asarray(vgk, dtype=np.float64)
    kg1 = p["Kg1"] * kg1_scale
    inner = p["Kp"] * (1.0 / p["mu"] + vgk / np.sqrt(p["Kvb"] + vpk * vpk))
    # ln(1+exp(x)) computed stably (softplus) to avoid overflow for large x.
    e1 = (vpk / p["Kp"]) * np.logaddexp(0.0, inner)
    e1 = np.maximum(e1, 0.0)
    ip = (np.power(e1, p["Ex"]) / kg1) * 2.0
    return ip


def solve_plate_voltage(vg: np.ndarray, vk: float, b_plus: float, r_load: float,
                        p: dict = KOREN_12AU7,
                        kg1_scale: float = STARVED_KG1_SCALE,
                        iters: int = 40) -> np.ndarray:
    """Common-cathode load line: find Vp such that
          Ip(Vg-Vk, Vp-Vk) == (B+ - Vp) / R_load.
    Vectorised Newton over the input array. vg = instantaneous grid voltage,
    vk = (slow) cathode voltage. Returns plate voltage Vp [V]."""
    vg = np.asarray(vg, dtype=np.float64)
    vp = np.full(vg.shape, b_plus * 0.5)      # midpoint seed
    for _ in range(iters):
        vpk = vp - vk
        vgk = vg - vk
        ip = plate_current(vgk, vpk, p, kg1_scale)
        # f(Vp) = Ip(Vp) - (B+ - Vp)/R = 0
        f = ip - (b_plus - vp) / r_load
        # numerical derivative dIp/dVp
        d = 1e-3
        ip2 = plate_current(vgk, vpk + d, p, kg1_scale)
        dip = (ip2 - ip) / d
        df = dip + 1.0 / r_load
        step = f / df
        step = np.clip(step, -40.0, 40.0)
        vp = np.clip(vp - step, 0.0, b_plus)
    return vp


def cathode_voltage_dc(b_plus: float, r_load: float, r_k: float,
                       p: dict = KOREN_12AU7,
                       kg1_scale: float = STARVED_KG1_SCALE,
                       n_tubes: int = 1, iters: int = 80) -> tuple[float, float]:
    """Self-biased DC operating point for a common-cathode stage whose cathode
    resistor r_k carries n_tubes identical triodes. Returns (Vk, Vp)."""
    vk = 1.0
    for _ in range(iters):
        vp = float(solve_plate_voltage(np.array([0.0]), vk, b_plus, r_load,
                                       p, kg1_scale)[0])
        ip = float(plate_current(np.array([-vk]), np.array([vp - vk]),
                                 p, kg1_scale)[0])
        vk_new = n_tubes * ip * r_k
        vk += 0.5 * (vk_new - vk)
    return vk, vp

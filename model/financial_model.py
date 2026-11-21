"""Reproducible 24-month financial model for VK social commerce strategy."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = Path(__file__).resolve().parent / "financial_model_results.json"

DEDUP_FACTOR = 0.85
BNPL_AOV_RUB = 5500.0
BNPL_BANK_RATE = 0.04
BNPL_VK_SHARE = 0.25
SAAS_PRICE_RUB = 1490.0
SAAS_COGS_RUB = 390.0
CPA_GROSS_FEE = 0.02
CPA_COST_RATE = 0.003
LOGISTICS_MARGIN_PER_PARCEL_RUB = 25.0
LOGISTICS_CARRIER_SHARE = 0.70
ORDER_SUPPORT_COST_RUB = 8.0
ACQUIRING_COST_RATE = 0.012
DISPUTE_RESERVE_RATE = 0.0025
CASHBACK_COMM_SHARE = 0.25
CASHBACK_ELIGIBLE_GMV_SHARE = 0.30
CASHBACK_TRUE_COST_LAMBDA = 0.35

# Allocation weights for the unified checkout/delivery/in-chat transaction stack
STACK_WEIGHTS = {
    "escrow_fiscal": 0.45,
    "one_click_delivery": 0.35,
    "in_chat_checkout": 0.20,
}

# CAPEX & OPEX (incremental cost of upgrading existing VK modules, RUB)
CAPEX_BY_MONTH = (
    [48_000_000.0 / 3.0] * 3
    + [42_000_000.0 / 3.0] * 3
    + [48_000_000.0 / 6.0] * 6
    + [3_000_000.0] * 12
)
OPEX_BY_MONTH = [10_000_000.0] * 12 + [14_000_000.0] * 12


@dataclass(frozen=True)
class ScenarioConfig:
    """Parameters defining pessimistic, base, and optimistic scenarios."""

    name: str
    label_ru: str
    paid_share_m12: float
    paid_share_m24: float
    driver_stack_lift_m24: float
    cpa_p1_ref_share_m24: float
    cpa_open_to_order_cr: float
    driver_market_lift_m24: float
    driver_bnpl_lift_m24: float
    buyout_rate: float
    escrow_take_rate: float
    bnpl_gmv_share_m24: float
    saas_paid_share_m24: float
    biz_pay_share_m24: float
    biz_delivery_share_m24: float
    biz_selling_share_m24: float


SCENARIOS: tuple[ScenarioConfig, ...] = (
    ScenarioConfig(
        name="pessimistic",
        label_ru="Пессимистичный",
        paid_share_m12=0.12,
        paid_share_m24=0.18,
        driver_stack_lift_m24=0.15,
        cpa_p1_ref_share_m24=0.10,
        cpa_open_to_order_cr=0.012,
        driver_market_lift_m24=0.10,
        driver_bnpl_lift_m24=0.04,
        buyout_rate=0.84,
        escrow_take_rate=0.025,
        bnpl_gmv_share_m24=0.08,
        saas_paid_share_m24=0.015,
        biz_pay_share_m24=0.18,
        biz_delivery_share_m24=0.35,
        biz_selling_share_m24=0.15,
    ),
    ScenarioConfig(
        name="base",
        label_ru="Базовый",
        paid_share_m12=0.18,
        paid_share_m24=0.28,
        driver_stack_lift_m24=0.25,
        cpa_p1_ref_share_m24=0.15,
        cpa_open_to_order_cr=0.015,
        driver_market_lift_m24=0.18,
        driver_bnpl_lift_m24=0.07,
        buyout_rate=0.88,
        escrow_take_rate=0.030,
        bnpl_gmv_share_m24=0.12,
        saas_paid_share_m24=0.030,
        biz_pay_share_m24=0.26,
        biz_delivery_share_m24=0.45,
        biz_selling_share_m24=0.22,
    ),
    ScenarioConfig(
        name="optimistic",
        label_ru="Оптимистичный",
        paid_share_m12=0.25,
        paid_share_m24=0.38,
        driver_stack_lift_m24=0.35,
        cpa_p1_ref_share_m24=0.22,
        cpa_open_to_order_cr=0.018,
        driver_market_lift_m24=0.25,
        driver_bnpl_lift_m24=0.10,
        buyout_rate=0.90,
        escrow_take_rate=0.035,
        bnpl_gmv_share_m24=0.16,
        saas_paid_share_m24=0.045,
        biz_pay_share_m24=0.35,
        biz_delivery_share_m24=0.55,
        biz_selling_share_m24=0.30,
    ),
)


def parse_market_summary(path: Path) -> dict[str, float]:
    """Parse baseline funnel numbers for VK Market and Partner 1 from markdown."""
    text = path.read_text(encoding="utf-8")
    metrics: dict[str, float] = {}
    patterns = {
        "vk_card_opens": r"\|\s*Открытия карточки товара\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        "vk_orders": r"\|\s*Оформленные заказы\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        "vk_paid_orders": r"\|\s*Оплаченные заказы\s*\|\s*(\d+)\s*\|",
        "vk_gmv": r"\|\s*GMV, ₽\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
        "p1_ref_card_opens": r"\|\s*в т\.ч\. из реферальных постов и клипов\s*\|\s*(\d+)\s*\|",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if not match:
            raise ValueError(f"Metric pattern not found in {path}: {key}")
        metrics[key] = float(match.group(1))
        if key == "vk_orders":
            metrics["p1_orders"] = float(match.group(2))
        elif key == "vk_gmv":
            metrics["p1_gmv"] = float(match.group(2))
        elif key == "vk_card_opens":
            metrics["p1_card_opens"] = float(match.group(2))
    metrics["vk_aov"] = metrics["vk_gmv"] / metrics["vk_orders"]
    metrics["p1_aov"] = metrics["p1_gmv"] / metrics["p1_orders"]
    metrics["vk_paid_share_0"] = metrics["vk_paid_orders"] / metrics["vk_orders"]
    return metrics


def load_businesses_baseline(path: Path) -> dict[str, float]:
    """Compute baseline community metrics and 1M-community scaling from businesses.csv."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    total_rows = len(rows)
    nonref = [r for r in rows if r["Участие в реферальной программе"] == "0"]
    goods = [
        r
        for r in nonref
        if r["Тип бизнеса (товары / услуги)"] in ("товарное", "товарное и услужное")
    ]
    n_goods = len(goods)
    n_pay = sum(1 for r in goods if r["Подключена оплата"] == "1")
    n_deliv = sum(1 for r in goods if r["Подключена доставка"] == "1")
    n_both = sum(
        1
        for r in goods
        if r["Подключена оплата"] == "1" and r["Подключена доставка"] == "1"
    )
    ordered = [r for r in goods if int(r["Заказы через чекаут"]) > 0]
    n_ordered = len(ordered)

    scale_to_1m = 1_000_000.0 / total_rows
    total_goods_scaled = round(n_goods * scale_to_1m)

    atoll_breakeven_monthly = 38500.0 / 0.015 / 12.0
    below_be_cnt = sum(
        1 for r in ordered if float(r["GMV через чекаут, ₽"]) < atoll_breakeven_monthly
    )

    return {
        "sample_total": float(total_rows),
        "sample_goods_nonref": float(n_goods),
        "sample_goods_pay": float(n_pay),
        "sample_goods_delivery": float(n_deliv),
        "sample_goods_both": float(n_both),
        "sample_goods_ordered": float(n_ordered),
        "pay_share_0": n_pay / n_goods,
        "delivery_share_0": n_deliv / n_goods,
        "both_share_0": n_both / n_goods,
        "selling_share_0": n_ordered / n_goods,
        "scale_factor_1m": scale_to_1m,
        "scaled_goods_communities": float(total_goods_scaled),
        "scaled_pay_0": round(n_pay * scale_to_1m),
        "scaled_delivery_0": round(n_deliv * scale_to_1m),
        "scaled_selling_0": round(n_ordered * scale_to_1m),
        "ordered_below_atoll_breakeven_share": below_be_cnt / n_ordered,
    }


def concave_ramp(month: int, start_month: int, end_month: int = 24) -> float:
    """Concave adoption ramp from launch month to full run-rate at end_month."""
    if month < start_month:
        return 0.0
    return min(
        1.0, ((month - start_month + 1) / (end_month - start_month + 1)) ** 0.75
    )


def flow1_paid_share(month: int, base_share: float, m12: float, m24: float) -> float:
    """Online payment share among existing checkout orders."""
    if month <= 12:
        return base_share + (m12 - base_share) * ((month / 12.0) ** 0.85)
    return m12 + (m24 - m12) * ((month - 12) / 12.0)


def simulate_month(
    month: int,
    cfg: ScenarioConfig,
    mkt: dict[str, float],
    biz: dict[str, float],
) -> dict[str, float]:
    """Simulate a single month t in 1..24 for the given scenario."""
    n0 = mkt["vk_orders"]
    n_paid_0 = mkt["vk_paid_orders"]
    aov0 = mkt["vk_aov"]
    o_ref_p1 = mkt["p1_ref_card_opens"]
    m_goods = biz["scaled_goods_communities"]

    r1 = concave_ramp(month, 1)
    r4 = concave_ramp(month, 4)
    r7 = concave_ramp(month, 7)

    # Flow 1: migration of existing orders to online payment (incremental above base n_paid_0)
    p1_share = flow1_paid_share(
        month, mkt["vk_paid_share_0"], cfg.paid_share_m12, cfg.paid_share_m24
    )
    flow1_online_total = n0 * p1_share
    flow1_online_inc = max(0.0, flow1_online_total - n_paid_0)

    # Flow 2: incremental orders from 4 drivers (gross before dedup and net after DEDUP_FACTOR)
    gross_d_stack = cfg.driver_stack_lift_m24 * n0 * r1
    gross_d_cpa = (cfg.cpa_p1_ref_share_m24 * o_ref_p1 * r4) * cfg.cpa_open_to_order_cr
    gross_d_market = cfg.driver_market_lift_m24 * n0 * r4
    gross_d_bnpl = cfg.driver_bnpl_lift_m24 * n0 * r7
    gross_inc_orders = gross_d_stack + gross_d_cpa + gross_d_market + gross_d_bnpl

    d_stack = gross_d_stack * DEDUP_FACTOR
    d_cpa = gross_d_cpa * DEDUP_FACTOR
    d_market = gross_d_market * DEDUP_FACTOR
    d_bnpl = gross_d_bnpl * DEDUP_FACTOR
    net_inc_orders = d_stack + d_cpa + d_market + d_bnpl
    dedup_reduction_orders = gross_inc_orders - net_inc_orders

    total_placed_orders = n0 + net_inc_orders

    # Online-paid orders before buyout adjustment
    onl_d_stack = d_stack * 0.70
    onl_d_cpa = d_cpa * 1.00
    onl_d_market = d_market * 0.65
    onl_d_bnpl = d_bnpl * 1.00
    inc_online_orders = flow1_online_inc + onl_d_stack + onl_d_cpa + onl_d_market + onl_d_bnpl
    total_online_orders = n_paid_0 + inc_online_orders

    # Buyout orders and GMV (incremental scope for project ROI, plus total portfolio GMV)
    buyout = cfg.buyout_rate
    inc_buyout_orders = inc_online_orders * buyout
    total_buyout_orders = total_online_orders * buyout

    inc_buyout_gmv = (
        (inc_online_orders - onl_d_bnpl) * aov0 + onl_d_bnpl * BNPL_AOV_RUB
    ) * buyout
    total_buyout_gmv = inc_buyout_gmv + n_paid_0 * aov0 * buyout

    cpa_buyout_orders = onl_d_cpa * buyout
    cpa_buyout_gmv = cpa_buyout_orders * aov0

    # Revenue and net gross margin across 4 non-ad streams (strictly incremental)
    rev_escrow = inc_buyout_gmv * cfg.escrow_take_rate
    cashback_cost = (
        rev_escrow * CASHBACK_COMM_SHARE * CASHBACK_ELIGIBLE_GMV_SHARE * CASHBACK_TRUE_COST_LAMBDA
        if month >= 7
        else 0.0
    )
    gm_escrow = (
        inc_buyout_gmv * (cfg.escrow_take_rate - ACQUIRING_COST_RATE - DISPUTE_RESERVE_RATE)
        - inc_buyout_orders * ORDER_SUPPORT_COST_RUB
        - cashback_cost
    )

    bnpl_share = cfg.bnpl_gmv_share_m24 * r7 if month >= 7 else 0.0
    bnpl_gmv = inc_buyout_gmv * bnpl_share
    rev_bnpl = bnpl_gmv * BNPL_BANK_RATE * BNPL_VK_SHARE
    gm_bnpl = rev_bnpl

    saas_clients = round(m_goods * (cfg.saas_paid_share_m24 * r7)) if month >= 7 else 0
    rev_saas = saas_clients * SAAS_PRICE_RUB
    gm_saas = saas_clients * (SAAS_PRICE_RUB - SAAS_COGS_RUB)

    rev_cpa = cpa_buyout_gmv * CPA_GROSS_FEE
    gm_cpa = cpa_buyout_gmv * (CPA_GROSS_FEE - CPA_COST_RATE)

    parcels_carrier = inc_buyout_orders * LOGISTICS_CARRIER_SHARE
    rev_log = parcels_carrier * LOGISTICS_MARGIN_PER_PARCEL_RUB
    gm_log = rev_log

    total_rev = rev_escrow + rev_bnpl + rev_saas + rev_cpa + rev_log
    total_gm = gm_escrow + gm_bnpl + gm_saas + gm_cpa + gm_log

    capex = CAPEX_BY_MONTH[month - 1]
    opex = OPEX_BY_MONTH[month - 1]
    total_cost = capex + opex
    ebitda = total_gm - total_cost

    # Tool-level incremental attribution (sums strictly to total incremental figures)
    unit_escrow_gm_rate = (
        gm_escrow / inc_buyout_gmv if inc_buyout_gmv > 0 else 0.0
    )
    stack_orders = flow1_online_inc + onl_d_stack
    stack_gmv = stack_orders * buyout * aov0
    stack_gm = stack_gmv * unit_escrow_gm_rate

    tool_escrow_orders = stack_orders * STACK_WEIGHTS["escrow_fiscal"]
    tool_escrow_gmv = stack_gmv * STACK_WEIGHTS["escrow_fiscal"]
    tool_escrow_gm = stack_gm * STACK_WEIGHTS["escrow_fiscal"]

    tool_deliv_orders = stack_orders * STACK_WEIGHTS["one_click_delivery"]
    tool_deliv_gmv = stack_gmv * STACK_WEIGHTS["one_click_delivery"]
    tool_deliv_gm = stack_gm * STACK_WEIGHTS["one_click_delivery"] + gm_log

    tool_chat_orders = stack_orders * STACK_WEIGHTS["in_chat_checkout"]
    tool_chat_gmv = stack_gmv * STACK_WEIGHTS["in_chat_checkout"]
    tool_chat_gm = stack_gm * STACK_WEIGHTS["in_chat_checkout"]

    tool_cpa_orders = onl_d_cpa
    tool_cpa_gmv = cpa_buyout_gmv
    tool_cpa_gm = cpa_buyout_gmv * unit_escrow_gm_rate + gm_cpa

    tool_market_orders = onl_d_market
    tool_market_gmv = onl_d_market * buyout * aov0
    tool_market_gm = tool_market_gmv * unit_escrow_gm_rate

    tool_bnpl_saas_orders = onl_d_bnpl
    tool_bnpl_saas_gmv = onl_d_bnpl * buyout * BNPL_AOV_RUB
    tool_bnpl_saas_gm = tool_bnpl_saas_gmv * unit_escrow_gm_rate + gm_bnpl + gm_saas

    # Business adoption counts (1M-community scale)
    pay_share_t = biz["pay_share_0"] + (cfg.biz_pay_share_m24 - biz["pay_share_0"]) * r1
    deliv_share_t = biz["delivery_share_0"] + (
        cfg.biz_delivery_share_m24 - biz["delivery_share_0"]
    ) * r1
    sell_share_t = biz["selling_share_0"] + (
        cfg.biz_selling_share_m24 - biz["selling_share_0"]
    ) * r1

    return {
        "month": month,
        "total_placed_orders": total_placed_orders,
        "gross_inc_placed_orders": gross_inc_orders,
        "dedup_reduction_orders": dedup_reduction_orders,
        "net_inc_placed_orders": net_inc_orders,
        "total_online_orders": total_online_orders,
        "inc_online_orders": inc_online_orders,
        "inc_buyout_orders": inc_buyout_orders,
        "total_buyout_orders": total_buyout_orders,
        "inc_buyout_gmv": inc_buyout_gmv,
        "total_buyout_gmv": total_buyout_gmv,
        "rev_escrow": rev_escrow,
        "rev_bnpl": rev_bnpl,
        "rev_saas": rev_saas,
        "rev_cpa": rev_cpa,
        "rev_log": rev_log,
        "total_rev": total_rev,
        "cashback_cost": cashback_cost,
        "gm_escrow": gm_escrow,
        "gm_bnpl": gm_bnpl,
        "gm_saas": gm_saas,
        "gm_cpa": gm_cpa,
        "gm_log": gm_log,
        "total_gm": total_gm,
        "capex": capex,
        "opex": opex,
        "total_cost": total_cost,
        "ebitda": ebitda,
        "saas_clients": float(saas_clients),
        "biz_pay_count": m_goods * pay_share_t,
        "biz_delivery_count": m_goods * deliv_share_t,
        "biz_selling_count": m_goods * sell_share_t,
        "biz_pay_share": pay_share_t,
        "biz_delivery_share": deliv_share_t,
        "biz_selling_share": sell_share_t,
        "tool_escrow_orders": tool_escrow_orders,
        "tool_escrow_gmv": tool_escrow_gmv,
        "tool_escrow_gm": tool_escrow_gm,
        "tool_deliv_orders": tool_deliv_orders,
        "tool_deliv_gmv": tool_deliv_gmv,
        "tool_deliv_gm": tool_deliv_gm,
        "tool_chat_orders": tool_chat_orders,
        "tool_chat_gmv": tool_chat_gmv,
        "tool_chat_gm": tool_chat_gm,
        "tool_cpa_orders": tool_cpa_orders,
        "tool_cpa_gmv": tool_cpa_gmv,
        "tool_cpa_gm": tool_cpa_gm,
        "tool_market_orders": tool_market_orders,
        "tool_market_gmv": tool_market_gmv,
        "tool_market_gm": tool_market_gm,
        "tool_bnpl_saas_orders": tool_bnpl_saas_orders,
        "tool_bnpl_saas_gmv": tool_bnpl_saas_gmv,
        "tool_bnpl_saas_gm": tool_bnpl_saas_gm,
    }


def aggregate_period(months: list[dict[str, float]]) -> dict[str, float]:
    """Sum flow metrics across a list of monthly dicts and take ending stock metrics."""
    sum_keys = [
        "total_placed_orders",
        "gross_inc_placed_orders",
        "dedup_reduction_orders",
        "net_inc_placed_orders",
        "total_online_orders",
        "inc_online_orders",
        "inc_buyout_orders",
        "total_buyout_orders",
        "inc_buyout_gmv",
        "total_buyout_gmv",
        "rev_escrow",
        "rev_bnpl",
        "rev_saas",
        "rev_cpa",
        "rev_log",
        "total_rev",
        "cashback_cost",
        "gm_escrow",
        "gm_bnpl",
        "gm_saas",
        "gm_cpa",
        "gm_log",
        "total_gm",
        "capex",
        "opex",
        "total_cost",
        "ebitda",
        "tool_escrow_orders",
        "tool_escrow_gmv",
        "tool_escrow_gm",
        "tool_deliv_orders",
        "tool_deliv_gmv",
        "tool_deliv_gm",
        "tool_chat_orders",
        "tool_chat_gmv",
        "tool_chat_gm",
        "tool_cpa_orders",
        "tool_cpa_gmv",
        "tool_cpa_gm",
        "tool_market_orders",
        "tool_market_gmv",
        "tool_market_gm",
        "tool_bnpl_saas_orders",
        "tool_bnpl_saas_gmv",
        "tool_bnpl_saas_gm",
    ]
    out = {k: sum(m[k] for m in months) for k in sum_keys}
    last = months[-1]
    for stock_k in (
        "saas_clients",
        "biz_pay_count",
        "biz_delivery_count",
        "biz_selling_count",
        "biz_pay_share",
        "biz_delivery_share",
        "biz_selling_share",
    ):
        out[stock_k] = last[stock_k]
    return out


def run_scenario(
    cfg: ScenarioConfig,
    mkt: dict[str, float],
    biz: dict[str, float],
) -> dict[str, Any]:
    """Run 24-month simulation and compute quarterly, yearly, and payback stats."""
    monthly: list[dict[str, float]] = []
    cum_cf = 0.0
    payback_month: int | None = None
    first_ebitda_pos_month: int | None = None

    for t in range(1, 25):
        row = simulate_month(t, cfg, mkt, biz)
        cum_cf += row["ebitda"]
        row["cum_cf"] = cum_cf
        if first_ebitda_pos_month is None and row["ebitda"] > 0:
            first_ebitda_pos_month = t
        if payback_month is None and cum_cf >= 0:
            payback_month = t
        monthly.append(row)

    # Estimate implied payback beyond M24 if not reached within 24 months
    implied_payback_month: int | None = payback_month
    m24_ebitda = monthly[-1]["ebitda"]
    if implied_payback_month is None and m24_ebitda > 0:
        implied_payback_month = 24 + int(-cum_cf // m24_ebitda) + 1

    quarters = [
        {
            "quarter": f"Q{q + 1}",
            **aggregate_period(monthly[q * 3 : (q + 1) * 3]),
            "cum_cf": monthly[(q + 1) * 3 - 1]["cum_cf"],
        }
        for q in range(8)
    ]

    return {
        "config": asdict(cfg),
        "year1": aggregate_period(monthly[:12]),
        "year2": aggregate_period(monthly[12:]),
        "total_24m": aggregate_period(monthly),
        "m12": monthly[11],
        "m24": monthly[23],
        "quarters": quarters,
        "monthly": monthly,
        "payback_month_within_24m": payback_month,
        "implied_payback_month": implied_payback_month,
        "first_ebitda_positive_month": first_ebitda_pos_month,
        "cum_cf_m24": cum_cf,
    }


def compute_store_unit_economics(aov: float) -> dict[str, Any]:
    """Compare monthly P&L of a typical brand store (200k RUB/mo) across channels."""
    monthly_gmv = 200_000.0
    orders_per_month = monthly_gmv / aov
    cogs = monthly_gmv * 0.40

    # Ozon (typical fashion/brand category assumptions verified in research)
    ozon_comm = monthly_gmv * 0.22
    ozon_acq = monthly_gmv * 0.015
    ozon_log = monthly_gmv * 0.08
    ozon_ads = monthly_gmv * 0.05
    ozon_fees_no_ads = ozon_comm + ozon_acq + ozon_log
    ozon_profit_no_ads = monthly_gmv - cogs - ozon_fees_no_ads
    ozon_profit_with_ads = ozon_profit_no_ads - ozon_ads

    # Current VK Pay + ATOL Online (mid-range 38,500 RUB/yr upfront)
    atoll_annual = 38_500.0
    vk_cur_acq = monthly_gmv * 0.020
    vk_cur_kassa_mo = atoll_annual / 12.0
    vk_cur_total_cost = vk_cur_acq + vk_cur_kassa_mo
    vk_cur_profit = monthly_gmv - cogs - vk_cur_total_cost

    # New VK (Safe Deal 3.0% incl. 54-FZ + acquiring + escrow; buyer pays delivery)
    vk_new_comm = monthly_gmv * 0.030
    vk_new_profit = monthly_gmv - cogs - vk_new_comm
    vk_new_with_10pct_promo = vk_new_profit - monthly_gmv * 0.10

    # New VK with seller-subsidized free delivery (250 RUB per order)
    seller_deliv_subsidy = orders_per_month * 250.0
    vk_new_free_deliv_profit = vk_new_profit - seller_deliv_subsidy

    # Break-even table for ATOL vs 3.0% agency scheme
    breakeven_rows = []
    for kassa_cost in (32_000.0, 38_500.0, 45_000.0):
        for delta_rate in (0.010, 0.015):
            annual_gmv = kassa_cost / delta_rate
            breakeven_rows.append(
                {
                    "atoll_annual_cost": kassa_cost,
                    "rate_spread_pct": delta_rate * 100.0,
                    "breakeven_annual_gmv": annual_gmv,
                    "breakeven_monthly_gmv": annual_gmv / 12.0,
                }
            )

    return {
        "typical_store_monthly_gmv": monthly_gmv,
        "typical_store_orders_mo": orders_per_month,
        "cogs_40pct": cogs,
        "channels": {
            "ozon_no_ads": {
                "platform_and_logistics_cost": ozon_fees_no_ads,
                "cost_pct_of_gmv": ozon_fees_no_ads / monthly_gmv,
                "gross_profit": ozon_profit_no_ads,
                "gross_margin_pct": ozon_profit_no_ads / monthly_gmv,
            },
            "ozon_with_5pct_ads": {
                "platform_and_ads_cost": ozon_fees_no_ads + ozon_ads,
                "cost_pct_of_gmv": (ozon_fees_no_ads + ozon_ads) / monthly_gmv,
                "gross_profit": ozon_profit_with_ads,
                "gross_margin_pct": ozon_profit_with_ads / monthly_gmv,
            },
            "vk_current_atol": {
                "upfront_annual_kassa": atoll_annual,
                "monthly_equiv_cost": vk_cur_total_cost,
                "cost_pct_of_gmv": vk_cur_total_cost / monthly_gmv,
                "gross_profit": vk_cur_profit,
                "gross_margin_pct": vk_cur_profit / monthly_gmv,
            },
            "vk_new_buyer_pays_delivery": {
                "platform_cost_3pct": vk_new_comm,
                "cost_pct_of_gmv": 0.03,
                "gross_profit": vk_new_profit,
                "gross_margin_pct": vk_new_profit / monthly_gmv,
            },
            "vk_new_with_10pct_promo": {
                "platform_plus_promo_cost": vk_new_comm + monthly_gmv * 0.10,
                "cost_pct_of_gmv": 0.13,
                "gross_profit": vk_new_with_10pct_promo,
                "gross_margin_pct": vk_new_with_10pct_promo / monthly_gmv,
            },
            "vk_new_seller_free_delivery": {
                "platform_plus_delivery_cost": vk_new_comm + seller_deliv_subsidy,
                "cost_pct_of_gmv": (vk_new_comm + seller_deliv_subsidy) / monthly_gmv,
                "gross_profit": vk_new_free_deliv_profit,
                "gross_margin_pct": vk_new_free_deliv_profit / monthly_gmv,
            },
        },
        "atol_breakeven_matrix": breakeven_rows,
    }


def main() -> None:
    """Load data, run all three scenarios, verify consistency, and save JSON."""
    mkt = parse_market_summary(DATA_DIR / "market_summary.md")
    biz = load_businesses_baseline(DATA_DIR / "businesses.csv")

    results: dict[str, Any] = {
        "baseline_market": mkt,
        "baseline_businesses": biz,
        "scenarios": {},
        "store_unit_economics": compute_store_unit_economics(mkt["vk_aov"]),
    }

    for cfg in SCENARIOS:
        res = run_scenario(cfg, mkt, biz)
        results["scenarios"][cfg.name] = res

    # Verify zero double counting: sum of 6 tools must match aggregate incremental totals
    base_24 = results["scenarios"]["base"]["total_24m"]
    tool_gm_sum = (
        base_24["tool_escrow_gm"]
        + base_24["tool_deliv_gm"]
        + base_24["tool_chat_gm"]
        + base_24["tool_cpa_gm"]
        + base_24["tool_market_gm"]
        + base_24["tool_bnpl_saas_gm"]
    )
    if abs(tool_gm_sum - base_24["total_gm"]) > 1e-3:
        raise AssertionError(
            f"Tool GM attribution mismatch: {tool_gm_sum} vs {base_24['total_gm']}"
        )

    OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== BASELINE ===")
    print(
        f"VK Orders/mo={mkt['vk_orders']:,.0f}, Paid={mkt['vk_paid_orders']:,.0f} "
        f"({mkt['vk_paid_share_0']*100:.2f}%), GMV={mkt['vk_gmv']/1e6:,.1f}M, AOV={mkt['vk_aov']:,.1f}"
    )
    print(
        f"Goods communities (1M scale)={biz['scaled_goods_communities']:,.0f}, "
        f"Pay={biz['pay_share_0']*100:.2f}%, Deliv={biz['delivery_share_0']*100:.2f}%, "
        f"Below ATOL BE={biz['ordered_below_atoll_breakeven_share']*100:.1f}%"
    )
    print("\n=== SCENARIOS SUMMARY (RUB M) ===")
    for name in ("pessimistic", "base", "optimistic"):
        sc = results["scenarios"][name]
        y1, y2, tot, m24 = sc["year1"], sc["year2"], sc["total_24m"], sc["m24"]
        print(
            f"{name:11s} | M24 placed={m24['total_placed_orders']/1e3:6.1f}k "
            f"onl_buy={m24['total_buyout_orders']/1e3:5.1f}k | "
            f"Y1 Rev={y1['total_rev']/1e6:5.1f}M GM={y1['total_gm']/1e6:5.1f}M | "
            f"Y2 Rev={y2['total_rev']/1e6:6.1f}M GM={y2['total_gm']/1e6:5.1f}M | "
            f"24m Net={tot['ebitda']/1e6:+6.1f}M | Payback=M{sc['implied_payback_month']}"
        )


if __name__ == "__main__":
    main()

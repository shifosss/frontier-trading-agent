"""Declared USD order-cost scenarios, not historical or realized broker tariffs."""

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from math import isfinite
from numbers import Integral

_NAMES = ("proportional", "wealthsimple_usd", "moomoo_ca_us")
_MOOMOO = "https://www.moomoo.com/ca/support/topic10_122"
_WEALTHSIMPLE = "https://www.wealthsimple.com/en-ca/legal/fees/trade"
_SEC = "https://www.sec.gov/rules-regulations/fee-rate-advisories/2026-2"


def _quantity(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError("quantity must be a nonnegative whole number")


def _nonnegative(value: float, name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _side(side: str) -> None:
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_CEILING)


@dataclass(frozen=True)
class ExecutionCosts:
    """Immutable cost identity; each fee call represents one single-day order.

    Broker profiles add explicit charges to the declared half-round-trip friction.
    USD funding/account charges and unresolved venue/tax charges are excluded.
    """

    name: str = "proportional"
    round_trip_bps: float = 40

    def __post_init__(self) -> None:
        if self.name not in _NAMES:
            raise ValueError(f"unknown execution cost profile: {self.name}")
        _nonnegative(self.round_trip_bps, "round_trip_bps")

    def fee(self, quantity: int, notional: float, side: str) -> float:
        """Cost in USD; zero orders incur no minimum; fees may exceed sale value."""
        _quantity(quantity)
        _nonnegative(notional, "notional")
        _side(side)
        if quantity == 0:
            if notional != 0:
                raise ValueError("zero quantity requires zero notional")
            return 0.0
        if notional == 0:
            raise ValueError("positive quantity requires positive notional")
        # Preserve the legacy float operation order exactly.
        friction = notional * (self.round_trip_bps / 20000)
        if self.name != "moomoo_ca_us":
            return friction
        amount = Decimal(str(notional))
        shares = Decimal(int(quantity))
        low_price = amount < shares  # average execution price < USD1
        commission_rate = Decimal("0.0005" if low_price else "0.0049")
        platform_rate = Decimal("0.0005" if low_price else "0.005")
        explicit = _cents(max(Decimal("0.99"), shares * commission_rate))
        explicit += _cents(max(Decimal("1.00"), shares * platform_rate))
        if side == "sell":
            explicit += _cents(max(Decimal("0.01"), amount * Decimal("0.0000206")))
        return float(explicit) + friction

    def maximum_quantity(
        self, max_quantity: int, price: float, budget: float, side: str = "buy"
    ) -> int:
        """Largest bounded whole quantity with notional + fee <= budget.

        The sell variant is the same gross-cost budget calculation, not proceeds
        or an instruction to sell. At fixed price costs are monotone in quantity.
        Negative available cash yields zero, never debt or an overdraft tolerance.
        """
        _quantity(max_quantity)
        _nonnegative(price, "price")
        if price == 0:
            raise ValueError("price must be positive")
        if not isfinite(budget):
            raise ValueError("budget must be finite")
        _side(side)
        if budget <= 0 or max_quantity == 0:
            return 0
        lo, hi = 0, int(max_quantity)
        while lo < hi:
            middle = (lo + hi + 1) // 2
            notional = middle * price
            if not isfinite(notional):
                hi = middle - 1
            elif notional + self.fee(middle, notional, side) <= budget:
                lo = middle
            else:
                hi = middle - 1
        return lo

    @property
    def specification(self) -> dict:
        """Fresh serializable identity, including assumptions affecting interpretation."""
        broker = self.name != "proportional"
        result = {
            "schema_version": 2,
            "name": self.name,
            "round_trip_bps": float(self.round_trip_bps) or 0.0,
            "currency": "USD",
            "friction": "notional * (round_trip_bps / 20000) on each side; unrounded",
            "friction_status": "declared sensitivity, not calibrated realized slippage",
            "tariff_checked_at": "2026-09-19" if broker else None,
            "historical_tariff": False,
            "interpretation": (
                "current-tariff counterfactual; incomplete cost coverage"
                if broker
                else "legacy proportional cost sensitivity"
            ),
            "incomplete_cost_lower_bound": broker,
            "lower_bound_scope": (
                "omitted costs; rounding/friction are scenarios, not a proven bound on actual fees"
            ),
            "source_urls": [],
            "rounding": "no monetary rounding for proportional friction",
            "order_assumption": "one order per side per day; no multiday fills or promotion",
            "excluded_charges": [
                "initial funding and eventual FX conversion/spread",
                "recurring account or subscription charges and applicable taxes",
                "unverified venue, regulatory, clearing or service charges",
                "actual spread, market impact and slippage beyond declared friction",
            ],
            "action_limitation": (
                "engine uses original entry whole shares with synthetic adjusted exit notional; "
                "not action-complete current shares or realized broker fills; per-share fees "
                "and USD1 bracket can be distorted across corporate actions"
            ),
        }
        if self.name == "wealthsimple_usd":
            result.update(
                {
                    "source_urls": [_WEALTHSIMPLE],
                    "source_access": "primary legal page retrieved directly",
                    "commission": "0 for listed US/Canadian securities",
                    "funding_assumption": "existing USD cash in an active USD account; no trade FX",
                    "account_charge": "ordinary CAD10/month plus tax excluded; waiver unverified",
                }
            )
        elif self.name == "moomoo_ca_us":
            result.update(
                {
                    "source_urls": [_MOOMOO, _SEC],
                    "source_access": "Moomoo indexed primary page; prior direct retrieval HTTP403",
                    "commission": "max(0.99,q*0.0049); price<1 uses q*0.0005",
                    "platform": "max(1.00,q*0.005); price<1 uses q*0.0005",
                    "sec_sell": "max(0.01,notional*0.0000206)",
                    "rounding": (
                        "each explicit component rounded up to USD0.01 using Decimal; "
                        "scenario rounding; broker convention unverified; friction unrounded"
                    ),
                }
            )
        return result

    def to_dict(self) -> dict:
        return self.specification


def get_cost_profile(name: str, round_trip_bps: float = 40) -> ExecutionCosts:
    return ExecutionCosts(name=name, round_trip_bps=round_trip_bps)

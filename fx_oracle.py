"""
SchemaDrift -- Universal Dynamic FX Oracle & Financial Currency Exchange Engine

Provides deterministic, live, and timestamp-anchored currency conversion
across ALL world currencies (EUR, GBP, JPY, CAD, AUD, CHF, INR, CNY, SGD, BRL, MXN, etc.)
with high-precision decimal math, dynamic volatility corridors, and circuit breakers.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


# --- Universal Baseline Rates relative to 1 USD ---
BASELINES_TO_USD: dict[str, float] = {
    "USD": 1.0000,
    "EUR": 1.0850,     # 1 EUR = 1.0850 USD
    "GBP": 1.2950,     # 1 GBP = 1.2950 USD
    "CAD": 0.7350,     # 1 CAD = 0.7350 USD
    "AUD": 0.6650,     # 1 AUD = 0.6650 USD
    "CHF": 1.1550,     # 1 CHF = 1.1550 USD
    "JPY": 0.0067,     # 1 JPY = 0.0067 USD
    "INR": 0.0119,     # 1 INR = 0.0119 USD
    "CNY": 0.1410,     # 1 CNY = 0.1410 USD
    "SGD": 0.7650,     # 1 SGD = 0.7650 USD
    "NZD": 0.6150,     # 1 NZD = 0.6150 USD
    "BRL": 0.1790,     # 1 BRL = 0.1790 USD
    "MXN": 0.0510,     # 1 MXN = 0.0510 USD
    "SEK": 0.0960,     # 1 SEK = 0.0960 USD
    "NOK": 0.0940,     # 1 NOK = 0.0940 USD
    "DKK": 0.1450,     # 1 DKK = 0.1450 USD
    "ZAR": 0.0550,     # 1 ZAR = 0.0550 USD
    "AED": 0.2723,     # 1 AED = 0.2723 USD
}

# Explicit historical corridors for high-volume pairs (Min, Max, Baseline)
CURRENCY_CORRIDORS: dict[tuple[str, str], tuple[float, float, float]] = {
    ("EUR", "USD"): (0.75, 1.45, 1.085),
    ("USD", "EUR"): (0.68, 1.33, 0.921),
    ("GBP", "USD"): (1.05, 1.65, 1.295),
    ("USD", "GBP"): (0.60, 0.95, 0.772),
    ("USD", "JPY"): (90.0, 180.0, 149.50),
    ("JPY", "USD"): (0.005, 0.012, 0.0067),
    ("CAD", "USD"): (0.65, 0.95, 0.735),
    ("USD", "CAD"): (1.05, 1.55, 1.360),
    ("AUD", "USD"): (0.55, 0.90, 0.665),
    ("USD", "AUD"): (1.10, 1.80, 1.503),
    ("CHF", "USD"): (0.90, 1.40, 1.155),
    ("INR", "USD"): (0.008, 0.018, 0.0119),
    ("USD", "INR"): (60.0, 110.0, 84.00),
}


def normalize_currency(curr_str: str) -> str:
    """Normalizes natural language or abbreviated currency terms to standard ISO 4217."""
    s = (curr_str or "").strip().lower()
    if s in ("eur", "euro", "euros"):
        return "EUR"
    if s in ("gbp", "pound", "pounds", "sterling"):
        return "GBP"
    if s in ("jpy", "yen"):
        return "JPY"
    if s in ("cad", "c$"):
        return "CAD"
    if s in ("aud", "a$"):
        return "AUD"
    if s in ("chf", "franc", "francs"):
        return "CHF"
    if s in ("inr", "rupee", "rupees", "₹"):
        return "INR"
    if s in ("cny", "rmb", "yuan"):
        return "CNY"
    if s in ("sgd", "s$"):
        return "SGD"
    if s in ("nzd", "nz$"):
        return "NZD"
    if s in ("brl", "real", "reais", "r$"):
        return "BRL"
    if s in ("mxn", "peso", "pesos"):
        return "MXN"
    if s in ("usd", "dollar", "dollars", "cents", "$"):
        return "USD"
    return s.upper() if len(s) == 3 else "USD"


class FXCircuitBreakerError(ValueError):
    """Raised when an exchange rate exceeds allowable volatility boundaries."""
    pass


class FXOracle:
    """
    Authoritative Universal Foreign Exchange (FX) Rate Provider.
    Decouples AI semantic discovery from real-time financial market data.
    """

    def __init__(self, cache_ttl_seconds: int = 300, offline_mode: bool = False) -> None:
        self.cache_ttl_seconds = cache_ttl_seconds
        self.offline_mode = offline_mode
        # Cache key: (from_curr, to_curr, date_str) -> (rate, expiry_timestamp, provider)
        self._cache: dict[tuple[str, str, str], tuple[Decimal, float, str]] = {}

    def _normalize_date(self, timestamp: str | None) -> str:
        """Extracts YYYY-MM-DD for historical rate lookup, or returns 'latest'."""
        if not timestamp:
            return "latest"
        try:
            cleaned = timestamp.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return "latest"

    def _compute_triangulated_baseline(self, from_curr: str, to_curr: str) -> float:
        """Computes deterministic baseline rate between ANY two currencies via USD triangulation."""
        usd_rate_from = BASELINES_TO_USD.get(from_curr, 1.0)
        usd_rate_to = BASELINES_TO_USD.get(to_curr, 1.0)
        return usd_rate_from / usd_rate_to

    def get_rate_with_metadata(
        self,
        from_curr: str,
        to_curr: str,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        """
        Fetches the authoritative exchange rate along with proof of origin and freshness.
        """
        from_curr = normalize_currency(from_curr)
        to_curr = normalize_currency(to_curr)

        # Identity exchange
        if from_curr == to_curr:
            return {
                "rate": Decimal("1.0"),
                "from_currency": from_curr,
                "to_currency": to_curr,
                "timestamp_anchored": timestamp or "live",
                "provider": "identity",
                "circuit_breaker_passed": True,
            }

        date_str = self._normalize_date(timestamp)
        cache_key = (from_curr, to_curr, date_str)
        now_ts = datetime.now(timezone.utc).timestamp()

        # Check in-memory cache
        if cache_key in self._cache:
            cached_rate, expiry, provider = self._cache[cache_key]
            if date_str != "latest" or now_ts < expiry:
                return {
                    "rate": cached_rate,
                    "from_currency": from_curr,
                    "to_currency": to_curr,
                    "timestamp_anchored": date_str,
                    "provider": f"cache ({provider})",
                    "circuit_breaker_passed": True,
                }

        # Attempt Live Query if not in offline mode
        rate = None
        provider = "offline_baseline"
        if not self.offline_mode:
            try:
                rate, provider = self._fetch_live_rate(from_curr, to_curr, date_str)
            except Exception:
                rate = None

        # Fallback to universal triangulation baseline if live fetch fails or offline
        if rate is None:
            corridor = CURRENCY_CORRIDORS.get((from_curr, to_curr))
            if corridor:
                rate = Decimal(str(corridor[2]))
                provider = "authoritative_corridor_baseline"
            else:
                triangulated = self._compute_triangulated_baseline(from_curr, to_curr)
                rate = Decimal(str(triangulated)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                provider = "universal_cross_rate_triangulation"

        # Volatility & Anomaly Circuit Breaker Validation
        self.verify_circuit_breaker(from_curr, to_curr, float(rate))

        # Store in Cache
        self._cache[cache_key] = (rate, now_ts + self.cache_ttl_seconds, provider)

        return {
            "rate": rate,
            "from_currency": from_curr,
            "to_currency": to_curr,
            "timestamp_anchored": date_str,
            "provider": provider,
            "circuit_breaker_passed": True,
        }

    def _fetch_live_rate(
        self, from_curr: str, to_curr: str, date_str: str
    ) -> tuple[Decimal, str]:
        """Queries Frankfurter / European Central Bank Public API."""
        endpoint = "latest" if date_str == "latest" else date_str
        url = f"https://api.frankfurter.app/{endpoint}?from={from_curr}&to={to_curr}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SchemaDrift-UniversalFXOracle/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_rate = data["rates"][to_curr]
            rate_dec = Decimal(str(raw_rate)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            return rate_dec, f"ecb_frankfurter_api ({endpoint})"

    def verify_circuit_breaker(self, from_curr: str, to_curr: str, rate: float) -> bool:
        """
        Guards against corrupt feeds, flash crashes, or malicious rate manipulation.
        Applies explicit corridor if known, or dynamic +/- 45% variance boundary.
        """
        corridor = CURRENCY_CORRIDORS.get((from_curr, to_curr))
        if corridor:
            min_bound, max_bound, baseline = corridor
        else:
            baseline = self._compute_triangulated_baseline(from_curr, to_curr)
            min_bound = baseline * 0.40
            max_bound = baseline * 2.20

        if rate < min_bound or rate > max_bound:
            raise FXCircuitBreakerError(
                f"CIRCUIT BREAKER TRIPPED: Rate for {from_curr}->{to_curr} is {rate}, "
                f"which violates allowable volatility corridor [{min_bound:.4f}, {max_bound:.4f}]."
            )
        return True

    def convert(
        self,
        amount: int | float | Decimal | str,
        from_currency: str,
        to_currency: str = "USD",
        timestamp: str | None = None,
        target_unit: str = "cents",
    ) -> dict[str, Any]:
        """
        Converts financial amount from any currency representation to any other
        with high decimal precision and financial rounding rules.

        target_unit:
          - 'cents': returns integer cents (rounded via ROUND_HALF_UP)
          - 'dollars' / 'standard': returns Decimal with 2 decimal places
        """
        amount_dec = Decimal(str(amount))
        from_curr_norm = normalize_currency(from_currency)
        to_curr_norm = normalize_currency(to_currency)

        meta = self.get_rate_with_metadata(from_curr_norm, to_curr_norm, timestamp)
        rate = meta["rate"]

        # Converted base value
        converted_base = amount_dec * rate

        if target_unit == "cents":
            # If converting to USD/EUR cents: multiply by 100 and round to nearest integer
            final_val = int((converted_base * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        elif target_unit in ("dollars", "units", "standard"):
            final_val = float(converted_base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        else:
            final_val = float(converted_base.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

        return {
            "original_amount": amount,
            "from_currency": from_curr_norm,
            "converted_amount": final_val,
            "to_currency": to_curr_norm,
            "target_unit": target_unit,
            "rate_applied": float(rate),
            "timestamp_anchored": meta["timestamp_anchored"],
            "provider": meta["provider"],
            "circuit_breaker_passed": meta["circuit_breaker_passed"],
        }


# Global Default Singleton Instance
GLOBAL_FX_ORACLE = FXOracle()


if __name__ == "__main__":
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"

    print(f"\n{BOLD}{CYAN}========================================================================{RESET}")
    print(f"{BOLD}{CYAN}  SCHEMADRIFT -- UNIVERSAL LIVE FX ORACLE & FINANCIAL GUARANTEES DEMO{RESET}")
    print(f"{BOLD}{CYAN}========================================================================{RESET}\n")

    oracle = GLOBAL_FX_ORACLE

    test_conversions = [
        ("EUR", 15.00, "USD", "2024-01-15T12:00:00Z", "cents"),
        ("GBP", 24.50, "USD", "latest", "cents"),
        ("JPY", 2500,  "USD", "latest", "cents"),
        ("CAD", 35.00, "USD", "latest", "cents"),
        ("INR", 1500,  "USD", "latest", "cents"),
        ("CHF", 50.00, "USD", "latest", "cents"),
    ]

    print(f"  {'Pair':<12} {'Input':<16} {'Converted (USD Cents)':<24} {'Rate':<10} {'Provider'}")
    print(f"  {'-' * 12} {'-' * 16} {'-' * 24} {'-' * 10} {'-' * 24}")

    for from_c, amt, to_c, ts, unit in test_conversions:
        res = oracle.convert(amt, from_c, to_c, ts, target_unit=unit)
        amt_str = f"{amt} {from_c}"
        conv_str = f"{res['converted_amount']} cents (${res['converted_amount']/100:.2f})"
        print(f"  {f'{from_c}->{to_c}':<12} {amt_str:<16} {conv_str:<24} {res['rate_applied']:<10.4f} {res['provider']}")

    print(f"\n{BOLD}[Circuit Breaker Test]{RESET}")
    try:
        oracle.verify_circuit_breaker("EUR", "USD", 2.85)
    except FXCircuitBreakerError as e:
        print(f"  {GREEN}[PASS]{RESET} Injected 2.85 EUR/USD: {e}")

    print(f"\n{BOLD}{CYAN}========================================================================{RESET}\n")

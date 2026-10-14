"""Drawdown behavior through the scanner and generated dashboard, without I/O to providers."""
import datetime as dt
import importlib.util
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "high_low_scan.py"
SPEC = importlib.util.spec_from_file_location("high_low_scan_drawdown_tests", SCRIPT)
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)

DRAW_COLS = {
    "3개월고점", "52주고점", "3개월고점대비(%)", "52주고점대비(%)",
    "낙폭기준일", "가격소스",
}
STAMP = int(dt.datetime(2026, 10, 13, 20, tzinfo=dt.timezone.utc).timestamp())


def tv_quote(name="DROP", **overrides):
    # Full decoded TradingView row: deliberately distinct daily / 3M / 52W highs.
    row = {
        "name": name, "description": name + " Company", "sector": "Technology",
        "market_cap_basic": 20_000_000_000, "close": 79.994, "change": -2.5,
        "high": 83.0, "low": 79.0, "price_52_week_high": 160.0,
        "price_52_week_low": 79.0, "High.3M": 100.0, "Low.3M": 79.0,
        "time": STAMP, "currency": "USD", "price_earnings_fwd": 12.0,
        "price_earnings_ttm": 15.0, "price_book_fq": 2.0,
    }
    row.update(overrides)
    return row


def csv_row(ticker, direction="신저가", **overrides):
    row = {
        "시장": "미국", "구분": direction, "NEW/OLD": "NEW", "티커": ticker,
        "종목명": ticker, "섹터": "Technology", "종가": 80.0,
        "등락률(%)": -1.0, "시총($B)": 20.0, "PER(12MF)": 12.0,
        "PER(TTM)": 15.0, "PBR": 2.0, "60일": "O", "52주": "O", "이유": "",
    }
    row.update(overrides)
    return row


class DashboardMarkup(HTMLParser):
    """Read functional headers and subtitle without depending on their nested markup."""
    def __init__(self, markup):
        super().__init__()
        self.headers = {}
        self.subtitle = ""
        self._header = None
        self._subtitle = False
        self.feed(markup)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "th" and "data-k" in attrs:
            self._header = attrs["data-k"]
            self.headers[self._header] = ""
        if tag == "div" and attrs.get("class") == "sub":
            self._subtitle = True

    def handle_endtag(self, tag):
        if tag == "th":
            self._header = None
        if tag == "div":
            self._subtitle = False

    def handle_data(self, data):
        if self._header is not None:
            self.headers[self._header] += data
        if self._subtitle:
            self.subtitle += data


class DrawdownHelperTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(callable(getattr(SCAN, "drawdown_pct", None)),
                        "drawdown_pct must provide validated signed percentages")
        return SCAN.drawdown_pct

    def test_valid_drawdown_keeps_raw_precision_until_percentage_rounding(self):
        calc = self.helper()
        self.assertEqual(calc(79.994, 100.0), -20.01)
        self.assertEqual(calc(80.0, 160.0), -50.0)
        self.assertEqual(calc(100.0, 100.0), 0.0)

    def test_invalid_price_pairs_are_missing_instead_of_invented_percentages(self):
        calc = self.helper()
        pairs = [
            (None, 100), (80, None), ("bad", 100), (80, "bad"),
            (float("nan"), 100), (80, float("nan")),
            (float("inf"), 100), (80, float("inf")),
            (float("-inf"), 100), (80, float("-inf")),
            (0, 100), (-1, 100), (80, 0), (80, -1), (101, 100),
        ]
        for close, high in pairs:
            with self.subTest(close=close, high=high):
                self.assertTrue(math.isnan(calc(close, high)))


class TradingViewDrawdownTests(unittest.TestCase):
    def test_new_lows_use_same_quote_highs_and_asof_before_close_rounding(self):
        def provider(market, floor_local, exchanges, currency):
            if market == "america":
                return [tv_quote(), tv_quote("OTHER", close=90.0, high=95.0,
                                            **{"High.3M": 120.0, "price_52_week_high": 200.0})]
            # Taiwan must have a real, non-empty universe; this neutral row is not a hit.
            return [tv_quote("2330", close=90.0, high=95.0, low=85.0,
                             **{"Low.3M": 80.0, "currency": currency})]

        with tempfile.TemporaryDirectory() as temp, patch.object(SCAN, "tv_market_scan", provider):
            markets, dates, _ = SCAN.scan_tradingview(SCAN.FX_FALLBACK, Path(temp))
        us = markets["미국"]
        self.assertTrue(DRAW_COLS.issubset(us.columns),
                        "raw scan rows must persist reference highs, percentages, date and source")
        rows = us.set_index("티커")
        drop = rows.loc["DROP US Equity"]
        self.assertEqual(drop["종가"], 79.99)
        self.assertEqual(drop["구분"], "신저가")
        self.assertEqual(drop["3개월고점"], 100.0)
        self.assertEqual(drop["52주고점"], 160.0)
        self.assertEqual(drop["3개월고점대비(%)"], -20.01)
        self.assertEqual(drop["52주고점대비(%)"], -50.0)
        other = rows.loc["OTHER US Equity"]
        self.assertEqual(other["3개월고점"], 120.0)
        self.assertEqual(other["52주고점"], 200.0)
        self.assertEqual(other["3개월고점대비(%)"], -25.0)
        self.assertEqual(other["52주고점대비(%)"], -55.0)
        self.assertEqual(drop["낙폭기준일"], "2026-10-13")
        self.assertEqual(dates["미국"], "2026-10-13")
        self.assertIn("TradingView", str(drop["가격소스"]))


class LegacyDrawdownTests(unittest.TestCase):
    def history(self, count):
        dates = pd.bdate_range(end="2026-10-14", periods=count)
        frame = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"),
                              "high": 100.0, "low": 80.0, "close": 90.0})
        frame.loc[frame.index[-1], ["high", "low", "close"]] = [83.0, 70.0, 79.994]
        return frame

    def build(self, history):
        universe = pd.DataFrame([{
            "yahoo": "DROP", "bb": "DROP US Equity", "name": "Drop Company",
            "sector": "Technology", "mcap_usd": 20_000_000_000,
            "pe_fwd": 12.0, "pe_ttm": 15.0, "pbr": 2.0,
        }])
        rows, date = SCAN.build_rows(universe, {"DROP": history})
        self.assertEqual(len(rows), 1)
        self.assertTrue(DRAW_COLS.issubset(rows.columns))
        self.assertEqual(date, "2026-10-14")
        return rows.iloc[0]

    def test_legacy_three_month_high_is_calendar_based_and_52_week_is_252_sessions(self):
        history = self.history(300)
        history.loc[history["date"] == "2026-07-13", "high"] = 160.0
        history.loc[history["date"] == "2026-07-14", "high"] = 120.0
        history.loc[history["date"] == "2026-02-02", "high"] = 200.0
        history.loc[0, "high"] = 300.0  # Outside the 252-session reference period.
        row = self.build(history)
        self.assertEqual(row["구분"], "신저가")
        self.assertEqual(row["종가"], 79.99)
        self.assertEqual(row["3개월고점"], 120.0)
        self.assertEqual(row["52주고점"], 200.0)
        self.assertEqual(row["3개월고점대비(%)"], -33.34)
        self.assertEqual(row["52주고점대비(%)"], -60.0)
        self.assertEqual(row["낙폭기준일"], "2026-10-14")
        self.assertEqual(row["가격소스"], "yfinance(분할·배당조정)")

    def test_legacy_less_than_252_sessions_has_no_52_week_drawdown(self):
        row = self.build(self.history(251))
        self.assertEqual(row["3개월고점"], 100.0)
        self.assertEqual(row["3개월고점대비(%)"], -20.01)
        self.assertTrue(pd.isna(row["52주고점"]))
        self.assertTrue(pd.isna(row["52주고점대비(%)"]))

    def test_legacy_short_history_cannot_invent_a_full_three_month_reference(self):
        row = self.build(self.history(41))
        self.assertTrue(pd.isna(row["3개월고점"]))
        self.assertTrue(pd.isna(row["3개월고점대비(%)"]))
        self.assertTrue(pd.isna(row["52주고점"]))
        self.assertTrue(pd.isna(row["52주고점대비(%)"]))


class DashboardDrawdownTests(unittest.TestCase):
    def generate(self, extra_values=None):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            pd.DataFrame([csv_row("OLD US Equity")]).to_csv(
                output / "scan_20261013.csv", index=False, encoding="utf-8-sig")
            new_values = {
                "3개월고점": 100.0, "52주고점": 160.0,
                "3개월고점대비(%)": -20.01, "52주고점대비(%)": -50.0,
                "낙폭기준일": "2026-10-14", "가격소스": "TradingView",
            }
            new_values.update(extra_values or {})
            pd.DataFrame([
                csv_row("LOW US Equity", **new_values),
                # Even a malformed high row with stored values must not show low-only fields.
                csv_row("HIGH US Equity", "신고가", **new_values),
            ]).to_csv(output / "scan_20261014.csv", index=False, encoding="utf-8-sig")
            with patch.object(SCAN, "publish_pages", return_value=None):
                SCAN.write_html(output, "20261014", {}, {"미국": "2026-10-14"}, SCAN.TV_NOTE)
            return (output / "index.html").read_text(encoding="utf-8")

    def test_dashboard_only_uses_persisted_new_low_values_and_leaves_history_missing(self):
        html = self.generate()
        match = re.search(r"const DATA\s*=\s*(\[.*?\]);", html, re.DOTALL)
        self.assertIsNotNone(match, "generated dashboard must embed its data")
        rows = {row["t"]: row for row in json.loads(match.group(1))}
        for ticker in ("OLD US Equity", "HIGH US Equity", "LOW US Equity"):
            self.assertIn("dd3", rows[ticker], "dashboard rows must expose sortable drawdown data")
            self.assertIn("dd52", rows[ticker])
        for ticker in ("OLD US Equity", "HIGH US Equity"):
            self.assertIsNone(rows[ticker]["dd3"])
            self.assertIsNone(rows[ticker]["dd52"])
        self.assertEqual(rows["LOW US Equity"]["dd3"], -20.01)
        self.assertEqual(rows["LOW US Equity"]["dd52"], -50.0)
        for key in ("h3", "h52", "asof", "ps"):
            self.assertIn(key, rows["LOW US Equity"], "tooltip metadata must come from the saved scan")
            self.assertIsNone(rows["OLD US Equity"][key])
        self.assertEqual(rows["LOW US Equity"]["h3"], 100.0)
        self.assertEqual(rows["LOW US Equity"]["h52"], 160.0)
        self.assertEqual(rows["LOW US Equity"]["asof"], "2026-10-14")
        self.assertEqual(rows["LOW US Equity"]["ps"], "TradingView")

    def test_dashboard_exposes_both_sortable_drawdown_columns_with_three_month_label(self):
        markup = DashboardMarkup(self.generate())
        for key in ("dd3", "dd52"):
            self.assertIn(key, markup.headers)
        self.assertIn("3개월", markup.headers["dd3"])
        # The normal TradingView dashboard must label its actual period correctly.
        self.assertIn("3개월", markup.subtitle)
        self.assertNotIn("60일", markup.subtitle)

    def test_nonfinite_reference_highs_are_serialized_as_missing(self):
        html = self.generate({"3개월고점": float("inf"), "52주고점": float("-inf"),
                              "3개월고점대비(%)": None, "52주고점대비(%)": None})
        rows = json.loads(re.search(r"const DATA\s*=\s*(\[.*?\]);", html, re.DOTALL).group(1))
        row = next(r for r in rows if r["t"] == "LOW US Equity")
        self.assertIsNone(row["h3"])
        self.assertIsNone(row["h52"])


if __name__ == "__main__":
    unittest.main()

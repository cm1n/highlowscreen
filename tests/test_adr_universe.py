import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "scanner_adr_test", Path(__file__).parents[1] / "tools" / "high_low_scan.py"
)
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


class AdrUniverseTest(unittest.TestCase):
    def test_us_adr_survives_the_provider_security_type_filter(self):
        """The provider calls VALE a dr, so a stock-only request silently loses it."""
        vale = dict.fromkeys(scanner.TV_COLS)
        vale.update(name="VALE", description="Vale ADR", market_cap_basic=44e9,
                    high=11.45, low=11.14, close=11.18, currency="USD",
                    price_52_week_low=11.14, **{"High.3M": 16.015, "Low.3M": 11.14})

        def provider(url, *, json, **kwargs):
            data = []
            if "dr" in json["symbols"]["query"]["types"]:
                data.append({"s": "NYSE:VALE", "d": [vale.get(c) for c in json["columns"]]})
            response = Mock()
            response.json.return_value = {"data": data}
            return response

        with patch.object(scanner.requests, "post", side_effect=provider):
            rows = scanner.tv_market_scan("america", 10e9, ["NYSE", "NASDAQ", "AMEX"], "USD")
        self.assertEqual([r["name"] for r in rows], ["VALE"])
        self.assertLessEqual(rows[0]["low"], rows[0]["price_52_week_low"])

    def test_non_us_security_types_and_size_currency_filters_stay_scoped(self):
        for market, (provider_market, currency, exchanges) in scanner.TV_MARKETS.items():
            response = Mock()
            response.json.return_value = {"data": []}
            with self.subTest(market=market), patch.object(scanner.requests, "post", return_value=response) as post:
                scanner.tv_market_scan(provider_market, 123456, exchanges, currency)
                body = post.call_args.kwargs["json"]
                self.assertEqual(body["symbols"]["query"]["types"],
                                 ["stock", "dr"] if market == "미국" else ["stock"])
                filters = {f["left"]: f for f in body["filter"]}
                self.assertEqual(filters["market_cap_basic"]["right"], 123456)
                self.assertEqual(filters["exchange"]["right"], exchanges)
                self.assertEqual(filters["currency"]["right"], [currency])
                self.assertEqual(filters["typespecs"]["right"], ["preferred"])


if __name__ == "__main__":
    unittest.main()

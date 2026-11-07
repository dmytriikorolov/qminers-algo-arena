import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from arena.market_data import FEATURE_ROW_LIMIT, analyze_csv, depth_features


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "market.csv"

    def analyze(self, text, kind="snapshots", **kwargs):
        self.path.write_text(text)
        return analyze_csv(self.path, kind=kind, **kwargs)

    def test_snapshots_have_actual_features_not_fills(self):
        result = self.analyze("time,bid,ask,bid_size,ask_size\n0,99,101,3,1\n1,100,102,1,1\n")
        self.assertEqual(result["metrics"]["rows"], 2)
        self.assertIsNone(result["synthetic"])
        self.assertNotIn("observed_buy_volume", result["metrics"])
        self.assertEqual(result["feature_rows"][0]["microprice"], 100.5)
        self.assertEqual(result["feature_rows"][0]["imbalance"], 0.5)
        self.assertEqual(result["feature_rows"][1]["rolling_mean"], 100.5)
        self.assertNotIn("fills", result["metrics"])
        self.assertNotIn("order_flow_imbalance", result["feature_rows"][0])
        self.assertEqual(result["feature_summaries"]["mid"]["count"], 2)
        self.assertEqual(len(result["dataset_fingerprint"]), 64)
        json.dumps(result, allow_nan=False)

    def test_bar_values_and_causal_windows(self):
        result = self.analyze("time,open,high,low,close,volume\n"
                              "0,99,101,98,100,5\n1,100,103,99,102,7\n2,102,105,101,104,9\n",
                              kind="bars", window=2)
        rows = result["feature_rows"]
        self.assertEqual(rows[0]["log_return"], 0)
        self.assertEqual(rows[0]["volatility"], 0)
        self.assertEqual(rows[2]["rolling_mean"], 103)
        self.assertEqual(rows[2]["rolling_volume"], 16)
        self.assertAlmostEqual(rows[2]["log_return"], math.log(104 / 102))
        self.assertEqual(rows[0]["bar_range"], 3)
        self.assertEqual(rows[0]["notional"], 500)

    def test_trade_signs_require_explicit_observations(self):
        result = self.analyze("time,price,quantity,side\n0,100,2,buy\n1,101,3,sell\n"
                              "2,102,5,\n3,103,4,buy\n4,104,1,sell\n", kind="trades", window=2)
        rows = result["feature_rows"]
        self.assertEqual([row["signed_quantity"] for row in rows], [2, -3, None, 4, -1])
        self.assertEqual([row["rolling_signed_quantity"] for row in rows], [2, -1, None, None, 3])
        self.assertEqual(result["quality"]["unknown_trade_side_rows"], 1)
        self.assertEqual(result["metrics"]["observed_buy_volume"], 6)
        self.assertEqual(result["metrics"]["observed_sell_volume"], 4)

    def test_unsigned_trades_are_not_signed_from_price_change(self):
        result = self.analyze("time,price,quantity\n0,100,2\n1,101,2\n", kind="trades")
        self.assertTrue(all(row["signed_quantity"] is None for row in result["feature_rows"]))
        self.assertTrue(all(row["rolling_signed_quantity"] is None for row in result["feature_rows"]))

    def test_future_changes_do_not_change_past_features(self):
        initial = self.analyze("time,price,quantity,side\n0,100,2,buy\n1,101,2,sell\n2,102,3,buy\n",
                               kind="trades")
        changed = self.analyze("time,price,quantity,side\n0,100,2,buy\n1,101,2,sell\n2,1000,50,sell\n",
                               kind="trades")
        self.assertEqual(initial["feature_rows"][:2], changed["feature_rows"][:2])
        self.assertNotEqual(initial["dataset_fingerprint"], changed["dataset_fingerprint"])

    def test_bad_snapshot_data_rejected(self):
        for row in ("0,101,100,1,1", "0,99,101,0,0", "0,99,101,-1,1",
                    "0,99,nan,1,1", "0,99,inf,1,1", "0,99,,1,1"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.analyze("time,bid,ask,bid_size,ask_size\n" + row + "\n")

    def test_locked_snapshot_counted(self):
        result = self.analyze("time,bid,ask,bid_size,ask_size\n0,100,100,1,1\n")
        self.assertEqual(result["quality"]["locked_snapshot_rows"], 1)

    def test_bad_bar_constraints_rejected(self):
        for row in ("0,100,99,101,100,1", "0,110,105,99,102,1", "0,100,105,99,110,1",
                    "0,100,105,99,102,-1", "0,100,105,0,102,1"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.analyze("time,open,high,low,close,volume\n" + row + "\n", kind="bars")

    def test_trade_price_quantity_and_side_validation(self):
        for row in ("0,0,1,buy", "0,100,0,buy", "0,100,-1,sell", "0,100,1,up",
                    "0,100,1,BUY", "0,100,nan,buy"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.analyze("time,price,quantity,side\n" + row + "\n", kind="trades")

    def test_time_is_numeric_nonnegative_strictly_increasing(self):
        for times in ((0, 0), (1, 0), (-1, 0), ("not-time", 1), (0, "inf")):
            with self.subTest(times=times), self.assertRaises(ValueError):
                self.analyze("time,price,quantity\n" + "\n".join(f"{t},100,1" for t in times), kind="trades")

    def test_schema_and_malformed_rows_rejected(self):
        for text in ("time,price\n0,100\n", "time,price,price\n0,100,100\n",
                     "time,price,quantity,unexpected\n0,100,1,2\n", "time,price,quantity\n0,100\n",
                     "time,price,quantity\n0,100,1,2\n", "time,price,quantity\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.analyze(text, kind="trades")

    def test_row_and_byte_caps_reject_incomplete_analysis(self):
        with patch("arena.market_data.MAX_ROWS", 2), self.assertRaisesRegex(ValueError, "row limit"):
            self.analyze("time,price,quantity\n0,100,1\n1,100,1\n2,100,1\n", kind="trades")
        with patch("arena.market_data.MAX_BYTES", 10), self.assertRaisesRegex(ValueError, "byte limit"):
            self.analyze("time,price,quantity\n0,100,1\n", kind="trades")

    def test_only_latest_feature_rows_retained(self):
        count = FEATURE_ROW_LIMIT + 5
        result = self.analyze("time,price,quantity\n" + "\n".join(f"{i},100,1" for i in range(count)),
                              kind="trades")
        self.assertEqual(result["metrics"]["rows"], count)
        self.assertEqual(len(result["feature_rows"]), FEATURE_ROW_LIMIT)
        self.assertEqual(result["feature_rows"][0]["time"], 5)
        self.assertEqual(result["feature_summaries"]["price"]["count"], count)
        self.assertTrue(result["feature_rows_truncated"])

    def test_huge_csv_field_has_descriptive_error(self):
        with self.assertRaisesRegex(ValueError, "market CSV"):
            self.analyze("time,price,quantity\n0," + "1" * 140000 + ",1\n", kind="trades")

    def test_invalid_configuration(self):
        self.path.write_text("time,price,quantity\n0,100,1\n")
        for kwargs in ({"kind": "guess"}, {"window": 0}, {"window": True}, {"window": 10001},
                       {"tick": 0}, {"tick": float("nan")}, {"tick": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                analyze_csv(self.path, **kwargs)


class DepthFeatureTests(unittest.TestCase):
    def test_actual_top_k_depth_only(self):
        result = depth_features([(100, 4), (99, 6), (98, 100)], [(101, 2), (102, 3)], k=2)
        self.assertEqual(result["bid_depth"], 10)
        self.assertEqual(result["ask_depth"], 5)
        self.assertEqual(result["depth_imbalance"], 1 / 3)
        self.assertEqual(result["bid_levels_used"], 2)

    def test_bad_actual_levels_rejected(self):
        for bids, asks in (([], [(101, 1)]), ([(100, 0)], [(101, 0)]),
                           ([(102, 1)], [(101, 1)]), ([(100, -1)], [(101, 1)]),
                           ([(100, 1), (101, 1)], [(102, 1)]),
                           ([(100, 1)], [(102, 1), (101, 1)]),
                           ([(100, 1), (100, 2)], [(101, 1)])):
            with self.subTest(bids=bids, asks=asks), self.assertRaises(ValueError):
                depth_features(bids, asks)


if __name__ == "__main__":
    unittest.main()

"""
StockMind AI — Unit Tests for the screener, daily list pipeline, flows and alerts
"""

import asyncio

import pytest

from app.api.routes.alerts import _is_hit
from app.core.security import hash_password, verify_password
from app.services.analytics.daily_list import DailyStockListService
from app.services.analytics.screener import SECTOR_UNIVERSE, all_symbols, sector_summary
from app.services.analytics.signals import PortfolioConfig
from app.services.upstox.provider import UpstoxDataProvider


def make_row(symbol, sector="Defence", entry="WAIT", change_pct=0.0, **extra):
    row = {
        "symbol": symbol,
        "name": symbol,
        "sector": sector,
        "instrument_key": f"NSE_EQ|{symbol}",
        "ltp": 100.0,
        "change_pct": change_pct,
        "entry": entry,
        "signal_type": "no_signal",
        "probability_up": 0.5,
        "confidence": "low",
        "risk": "medium",
        "trend": "Mixed",
        "rsi": 50.0,
        "volume_ratio": 1.0,
        "entry_zone": [98.0, 101.0],
        "stop_loss": 95.0,
        "target_1": 110.0,
        "target_2": 117.5,
        "risk_reward": 2.0,
        "return_5d": 1.0,
        "return_20d": 2.0,
        "return_60d": 3.0,
        "buckets": [],
        "explanation": "",
    }
    row.update(extra)
    return row


class TestUniverse:
    def test_symbols_are_unique(self):
        symbols = [s for s, _ in all_symbols()]
        assert len(symbols) == len(set(symbols))

    def test_every_sector_has_stocks(self):
        assert all(len(v) >= 5 for v in SECTOR_UNIVERSE.values())


class TestSectorSummary:
    def test_breadth_and_averages(self):
        rows = [
            make_row("A", change_pct=2.0),
            make_row("B", change_pct=-1.0),
            make_row("C", change_pct=1.0, entry="BUY_NOW"),
        ]
        defence = next(s for s in sector_summary(rows) if s["sector"] == "Defence")
        assert defence["advances"] == 2
        assert defence["declines"] == 1
        assert defence["change_pct"] == pytest.approx(0.67, abs=0.01)
        assert defence["top_gainer"] == "A"
        assert defence["top_loser"] == "B"
        assert defence["bullish_signals"] == 1

    def test_empty_sector(self):
        summary = sector_summary([])
        assert all(s["stocks"] == 0 for s in summary)


class TestDailyListPipeline:
    def generate(self, rows, previous=None, capital=200000.0):
        service = DailyStockListService(PortfolioConfig(total_capital=capital))
        market = {"regime": {"regime": "Neutral", "risk_alerts": []}, "metadata": {}}
        return asyncio.run(service.generate(market_data=market, screened=rows, previous_signals=previous)).to_dict()

    def test_classification_into_actionable_groups(self):
        report = self.generate([
            make_row("BUY", entry="BUY_NOW"),
            make_row("RETEST", entry="BUY_ON_RETEST"),
            make_row("BAD", entry="AVOID"),
            make_row("IGNORED", entry="WAIT"),
        ])
        actionable = report["actionable"]
        assert [s["symbol"] for s in actionable["buy_now"]] == ["BUY"]
        assert [s["symbol"] for s in actionable["watch_retest"]] == ["RETEST"]
        assert [s["symbol"] for s in actionable["avoid"]] == ["BAD"]
        listed = {s["symbol"] for h in report["stocks"].values() for s in h}
        assert listed == {"BUY", "RETEST"}

    def test_position_sizing_respects_risk_and_concentration(self):
        report = self.generate([make_row("BUY", entry="BUY_NOW")])
        item = report["actionable"]["buy_now"][0]
        # Risk/share = 5, max loss 1500 -> 300 shares, but 20% cap = 40000 / 100 = 400 -> 300
        assert item["quantity"] == 300
        assert item["max_risk"] == pytest.approx(1500)

        capped = self.generate([make_row("BUY", entry="BUY_NOW", stop_loss=99.0)])
        # Risk/share = 1 -> 1500 shares, capped at 20% of capital -> 400
        assert capped["actionable"]["buy_now"][0]["quantity"] == 400

    def test_horizon_assignment(self):
        report = self.generate([
            make_row("MOMO", entry="BREAKOUT_WATCH", buckets=["momentum_breakout"]),
            make_row("PULL", entry="BREAKOUT_WATCH", buckets=["quality_pullback"]),
            make_row("MID", entry="BUY_ON_RETEST"),
        ])
        assert [s["symbol"] for s in report["stocks"]["short_term"]] == ["MOMO"]
        assert [s["symbol"] for s in report["stocks"]["long_term"]] == ["PULL"]
        assert [s["symbol"] for s in report["stocks"]["mid_term"]] == ["MID"]

    def test_continuity_tracks_new_retained_removed(self):
        report = self.generate([make_row("KEEP", entry="BUY_NOW"), make_row("FRESH", entry="BUY_NOW")], previous=["KEEP", "GONE"])
        status = {c["symbol"]: c["today_status"] for c in report["continuity"]}
        assert status == {"KEEP": "RETAINED", "FRESH": "NEW", "GONE": "REMOVED"}

    def test_held_symbol_still_gets_bucketed_not_excluded(self):
        """
        Holdings used to be hard-excluded from the daily list entirely. They're
        no longer special-cased here at all — is_holding/holding_action are
        attached upstream (from the user's live broker holdings) and just ride
        along on the row into whichever bucket its entry classification earns,
        same as any other candidate.
        """
        report = self.generate([make_row("AVANTEL", entry="BUY_NOW", is_holding=True, holding_action="ADD")])
        buy_now = report["actionable"]["buy_now"]
        assert [s["symbol"] for s in buy_now] == ["AVANTEL"]
        assert buy_now[0]["is_holding"] is True
        assert buy_now[0]["holding_action"] == "ADD"

    def test_held_symbol_with_avoid_entry_lands_in_avoid_tagged_reduce(self):
        report = self.generate([make_row("GARUDA", entry="AVOID", is_holding=True, holding_action="REDUCE")])
        avoid = report["actionable"]["avoid"]
        assert [s["symbol"] for s in avoid] == ["GARUDA"]
        assert avoid[0]["holding_action"] == "REDUCE"


class TestFlowsNormalisation:
    def test_net_is_buy_minus_sell_newest_first(self):
        provider = UpstoxDataProvider(access_token="x")
        raw = {
            "status": "success",
            "data": {"NSE_EQ|CASH": [
                {"time_stamp": 1790620200000, "buy_amount": 100.0, "sell_amount": 50.0},
                {"time_stamp": 1790706600000, "buy_amount": 10.0, "sell_amount": 30.0},
            ]},
        }
        data = provider._wrap_flows(raw, "fii_data")["data"]
        assert data["net"] == -20.0
        assert [h["net"] for h in data["history"]] == [-20.0, 50.0]

    def test_empty_flows(self):
        provider = UpstoxDataProvider(access_token="x")
        assert provider._wrap_flows({"data": {}}, "fii_data")["data"] is None


class TestAlertConditions:
    @pytest.mark.parametrize(
        "alert_type,target,ltp,change,expected",
        [
            ("price_above", 100, 101, None, True),
            ("price_above", 100, 99, None, False),
            ("price_below", 100, 99, None, True),
            ("change_above", 2, 100, 2.5, True),
            ("change_below", -2, 100, -1.0, False),
            ("change_below", -2, 100, None, False),
        ],
    )
    def test_is_hit(self, alert_type, target, ltp, change, expected):
        assert _is_hit(alert_type, target, ltp, change) is expected


class TestPasswordHashing:
    def test_roundtrip(self):
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed)
        assert not verify_password("wrong", hashed)

    def test_long_passwords_do_not_crash(self):
        hashed = hash_password("x" * 200)
        assert verify_password("x" * 200, hashed)

    def test_malformed_hash_is_rejected(self):
        assert not verify_password("secret123", "not-a-hash")

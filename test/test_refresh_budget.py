#!/usr/bin/python3
"""Checks how Mistral's billing answers become panel fields. Makes no network calls."""

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "refresh-budget.py"
spec = importlib.util.spec_from_file_location("refresh_budget", SCRIPT)
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

RESET = "2026-12-01T00:00:00Z"
PAYG_ON = {"plan_name": "TEAM", "payg_enabled": True, "vibe_payg_enabled": True}
PAYG_OFF = {"plan_name": "TEAM", "payg_enabled": False, "vibe_payg_enabled": False}


def vibe(**overrides):
  return {"usage_percentage": 40.0, "initial_budget": 300.0, "currency": "EUR", "reset_at": RESET, **overrides}


def api(**overrides):
  return {"usage_percentage": 10.0, "initial_budget": 30.0, "currency": "EUR", "reset_at": RESET, **overrides}


def build(vibe_pool, api_pool=None, subscription=None):
  budget = {"vibe_budget": vibe_pool}
  if api_pool is not None:
    budget["api_budget"] = api_pool
  return plugin.build_patch(budget, subscription, 1)


class DotenvValue(unittest.TestCase):
  def test_quotes_and_trailing_comments_are_dropped(self):
    for raw in ("fake-key", " fake-key ", "fake-key # personal key", "'fake-key' # personal key", '"fake-key"'):
      with self.subTest(raw):
        self.assertEqual(plugin.dotenv_value(raw), "fake-key")

  def test_a_hash_inside_a_key_is_kept(self):
    self.assertEqual(plugin.dotenv_value("fake#key"), "fake#key")


class BuildPatch(unittest.TestCase):
  def test_both_pools_get_labelled_meters(self):
    limits = build(vibe(), api(), PAYG_ON)["limits"]
    self.assertEqual([limit["title"] for limit in limits], ["Vibe", "API"])
    self.assertAlmostEqual(limits[0]["percent"], 0.4)
    self.assertAlmostEqual(limits[1]["percent"], 0.1)
    self.assertEqual(limits[0]["resetsAt"], RESET)

  def test_balance_covers_the_vibe_pool_only(self):
    self.assertEqual(
      build(vibe(), api(), PAYG_ON)["balance"],
      {"remaining": 180.0, "funded": 300.0, "spent": 120.0, "currency": "EUR"},
    )

  def test_full_pool_leaves_nothing_remaining(self):
    balance = build(vibe(usage_percentage=100.0))["balance"]
    self.assertEqual((balance["remaining"], balance["spent"]), (0.0, 300.0))

  def test_tier_says_whether_payg_is_on(self):
    self.assertEqual(build(vibe(), subscription=PAYG_ON)["tierLabel"], "Team · PAYG")
    self.assertEqual(build(vibe(), subscription=PAYG_OFF)["tierLabel"], "Team")

  def test_no_subscription_answer_leaves_the_tier_alone(self):
    self.assertNotIn("tierLabel", build(vibe()))

  def test_markup_in_the_plan_name_is_dropped(self):
    patch = build(vibe(), subscription={"plan_name": '<img src="https://example.invalid/t">', "payg_enabled": True})
    self.assertNotIn("tierLabel", patch)

  def test_bad_api_pool_is_dropped_but_vibe_stays(self):
    self.assertEqual([limit["title"] for limit in build(vibe(), api(currency="<b>EUR</b>"))["limits"]], ["Vibe"])

  def test_implausible_vibe_pools_are_rejected(self):
    for name, pool in {
      "markup currency": vibe(currency="<b>EUR</b>"),
      "NaN": vibe(usage_percentage=float("nan")),
      "infinite budget": vibe(initial_budget=float("inf")),
      "zero budget": vibe(initial_budget=0),
      "negative": vibe(usage_percentage=-1),
      "boolean": vibe(usage_percentage=True),
      "string": vibe(usage_percentage="40"),
      "bad reset": vibe(reset_at="<img>"),
      "no reset": vibe(reset_at=None),
      "missing": None,
    }.items():
      with self.subTest(name):
        self.assertIsNone(build(pool))

  def test_non_object_answer_is_rejected(self):
    self.assertIsNone(plugin.build_patch([], None, 1))


if __name__ == "__main__":
  unittest.main()

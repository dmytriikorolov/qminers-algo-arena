import copy
import tempfile
import unittest
from pathlib import Path

from arena.game_reporting import PUZZLES, puzzle_cards
from arena.games import demo


class TestPuzzleCards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from reportlab.lib.styles import getSampleStyleSheet
            from pypdf import PdfReader
        except ImportError:
            raise unittest.SkipTest("optional reportlab/pypdf dependencies unavailable")
        cls.styles = getSampleStyleSheet()
        cls.reader = PdfReader
        cls.record = {"id": "verified-games-seed7", "seed": 7,
                      "config": {"family": "games"}, "result": demo(seed=7, trials=100)}

    def render(self, record):
        from reportlab.platypus import SimpleDocTemplate
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "answers.pdf"
            SimpleDocTemplate(str(path), leftMargin=48, rightMargin=48,
                              topMargin=36, bottomMargin=36).build(puzzle_cards(record, self.styles))
            reader = self.reader(path)
            return [(page.extract_text() or "") for page in reader.pages]

    def test_exactly_six_pages_with_run_and_source(self):
        pages = self.render(self.record)
        self.assertEqual(len(pages), 6)
        for name, text in zip(PUZZLES, pages):
            self.assertIn(name, text)
            self.assertIn("verified-games-seed7", text)
            self.assertIn("SYNTHETIC / EXAMPLE", text)
            self.assertIn("result.json", text)

    def test_actual_observed_values_present(self):
        pages = self.render(self.record)
        puzzles = {p["name"]: p for p in self.record["result"]["puzzles"]}
        self.assertIn("19", pages[0])
        self.assertIn(f'{puzzles["shared_reward"]["solution"]["expected_payoffs"][1]:.8g}', pages[1])
        self.assertIn(f'{puzzles["sealed_bid_auction"]["solution"]["best_utility"]:.8g}', pages[2])
        self.assertIn(f'{puzzles["matrix_game"]["solution"]["exploitability_gap"]:.8g}', pages[3])
        self.assertIn(f'{puzzles["conversion_graph"]["solution"]["final_amount"]:.8g}', pages[4])
        self.assertIn("aggressive", pages[5])

    def test_reporting_uses_saved_values_without_rerunning(self):
        record = copy.deepcopy(self.record)
        record["result"]["puzzles"][0]["solution"]["reward"] = 123.456
        self.assertIn("123.456", self.render(record)[0])

    def test_missing_or_duplicate_puzzles_rejected(self):
        for puzzles in (self.record["result"]["puzzles"][:5],
                        self.record["result"]["puzzles"][:5] + [self.record["result"]["puzzles"][0]]):
            record = copy.deepcopy(self.record)
            record["result"]["puzzles"] = puzzles
            with self.assertRaisesRegex(ValueError, "six distinct"):
                puzzle_cards(record, self.styles)

    def test_reject_wrong_family(self):
        record = copy.deepcopy(self.record)
        record["config"]["family"] = "ml"
        with self.assertRaises(ValueError):
            puzzle_cards(record, self.styles)


if __name__ == "__main__":
    unittest.main()

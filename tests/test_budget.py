from pathlib import Path
import tempfile
import unittest
from services.pipeline.budget import Budget,BudgetExceeded

class BudgetTests(unittest.TestCase):
    def test_crash_reservation_survives_resume_and_blocks_next_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ledger.json'
            budget=Budget(path, .04)
            context={'model':'gpt-6.1-terra','stage':'generate','request':{'max_output_tokens':6000}}
            budget.before(context)
            resumed=Budget(path,.04)
            self.assertGreater(resumed.spent,.03)
            with self.assertRaises(BudgetExceeded):resumed.before(context)

    def test_reasoning_is_not_double_charged(self):
        with tempfile.TemporaryDirectory() as folder:
            budget=Budget(Path(folder)/'ledger.json')
            budget.before({'model':'gpt-6-luna','stage':'classify','request':{'max_output_tokens':6000}})
            budget.after({'usage':{'input_tokens':1000,'output_tokens':1000,'output_tokens_details':{'reasoning_tokens':900}}})
            self.assertAlmostEqual(budget.spent,.0006)

    def test_missing_usage_keeps_full_reservation(self):
        with tempfile.TemporaryDirectory() as folder:
            budget=Budget(Path(folder)/'ledger.json')
            budget.before({'model':'gpt-6-luna','stage':'classify','request':{'max_output_tokens':6000}})
            reserved=budget.spent;budget.after({'usage':None})
            self.assertEqual(budget.spent,reserved)

    def test_no_model_fallback_or_budget_increase(self):
        with self.assertRaises(ValueError):Budget(limit=2.01)
        with tempfile.TemporaryDirectory() as folder:
            budget=Budget(Path(folder)/'ledger.json')
            with self.assertRaises(BudgetExceeded):budget.before({'model':'gpt-4.1-mini','request':{},'stage':'classify'})

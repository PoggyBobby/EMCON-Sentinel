"""CI must check tracked notices before any generation can hide their drift."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InventoryWorkflowTests(unittest.TestCase):
    def test_ci_checks_notices_before_running_other_repository_code(self):
        workflow = (ROOT / '.github/workflows/test.yml').read_text()
        gate = 'run: python3 scripts/dependency_inventory.py --check-notices'
        self.assertEqual(workflow.count(gate), 1)
        self.assertLess(workflow.index(gate), workflow.index('run: python3 -m unittest'))
        inventory_runs = re.findall(r'^\s*run: (.*scripts/dependency_inventory\.py[^\n]*)$',
                                    workflow, re.MULTILINE)
        self.assertEqual(inventory_runs, ['python3 scripts/dependency_inventory.py --check-notices'])


if __name__ == '__main__':
    unittest.main()

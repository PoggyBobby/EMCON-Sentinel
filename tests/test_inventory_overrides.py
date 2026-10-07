"""Synthetic Gradle resolution-override observations; no Gradle/config reads."""
import unittest

from test_dependency_inventory import tool


class OverrideTests(unittest.TestCase):
    def test_qualified_literal_override_calls_are_surfaced(self):
        for call in (
            "resolutionStrategy.force 'a.b:c:9'",
            "configurations.all { resolutionStrategy.force('a.b:c:9') }",
            "details.useVersion '9'",
            "details.useTarget('a.b:c:9')",
            "details . useVersion ( '9' )",
        ):
            with self.subTest(call=call):
                found = tool().parse_gradle_text(call, 'b.gradle')
                self.assertEqual(len(found), 1, found)
                self.assertEqual(found[0]['status'], 'unparsed')
                self.assertEqual(found[0]['form'], 'resolution-strategy')
                self.assertEqual(found[0]['source'], 'b.gradle:1')
                self.assertNotIn('coordinate', found[0])
                self.assertNotIn('9', str(found))

    def test_override_identifiers_with_nonliteral_arguments_or_references_are_surfaced(self):
        for call in (
            'resolutionStrategy.force versions',
            'details.useVersion selectedVersion',
            'details.useTarget target',
            'force coordinates',
            'useVersion selectedVersion',
            'useTarget target',
            'resolutionStrategy.force\n coordinates',
            'def callback = details.&useVersion',
            'def callback = details::useTarget',
            'def callback = resolutionStrategy.force',
            'resolutionStrategy.forcedModules = coordinates',
        ):
            with self.subTest(call=call):
                found = tool().parse_gradle_text(call, 'b.gradle')
                self.assertEqual(len(found), 1, found)
                self.assertEqual(found[0]['form'], 'resolution-strategy')
                self.assertEqual(found[0]['status'], 'unparsed')
                self.assertNotIn('coordinate', found[0])
                self.assertNotIn('selectedVersion', str(found))

    def test_comments_strings_and_longer_identifiers_do_not_create_observations(self):
        source = '''// resolutionStrategy.force 'hidden'
/* details.useVersion hidden */
def text = "details.useTarget hidden"
def multiline = ''' + "'''force\\nforcedModules'''" + '''
def forceful = 1
def useVersionExtra = 2
def $force = 3
def force$other = 4
'''
        self.assertEqual(tool().parse_gradle_text(source, 'b.gradle'), [])

    def test_observations_preserve_order_and_do_not_duplicate_block_statements(self):
        source = '''details.useVersion privateVersion
// details.useTarget ignored
resolutionStrategy.force privateCoordinates
dependencies { details.useTarget privateTarget }
'''
        found = tool().parse_gradle_text(source, 'b.gradle')
        self.assertEqual(len(found), 3, found)
        self.assertEqual([item['source'] for item in found], ['b.gradle:1', 'b.gradle:3', 'b.gradle:4'])
        self.assertTrue(all(item['status'] == 'unparsed' for item in found))
        self.assertNotIn('private', str(found))
        self.assertEqual([item['form'] for item in found[:2]], ['resolution-strategy'] * 2)

"""Wrapper parser regressions: isolated strings, never developer configuration."""
import unittest

from test_dependency_inventory import tool


URL = 'https://services.gradle.org/distributions/gradle-7.6.4-all.zip'
WRAPPER = 'distributionUrl=' + URL + '\n'
SOURCE = 'plugin/gradle/wrapper/gradle-wrapper.properties'


class WrapperPropertiesTests(unittest.TestCase):
    def test_duplicate_properties_are_rejected_even_when_values_match(self):
        module = tool()
        for text in (WRAPPER + WRAPPER, WRAPPER + 'networkTimeout=10000\nnetworkTimeout=10000\n'):
            with self.subTest(text=text), self.assertRaises(module.InventoryError):
                module.read_wrapper(text, SOURCE)

    def test_nonliteral_keys_cannot_hide_java_properties_aliases(self):
        module = tool()
        for key in (r'distribution\u0055rl', r'distribution\Url', 'distributionUrl:ignored',
                    'distributionUrl ignored', 'distributionUrl\tignored'):
            with self.subTest(key=key), self.assertRaises(module.InventoryError):
                module.read_wrapper(WRAPPER + key + '=https://example.org/other.zip\n', SOURCE)

    def test_unsupported_value_escapes_and_continuations_are_rejected(self):
        module = tool()
        for value in (r'\u0061', r'\t', r'\n', r'\r', r'\f', r'\=', r'\\', r'\q', 'first\\\nsecond=value'):
            with self.subTest(value=value), self.assertRaises(module.InventoryError):
                module.read_wrapper(WRAPPER + 'distributionPath=' + value + '\n', SOURCE)

    def test_trailing_java_value_whitespace_is_not_silently_trimmed(self):
        module = tool()
        for suffix in (' ', '\t', '\f'):
            for property_line in ('distributionUrl=' + URL,
                                  'distributionSha256Sum=' + 'c' * 64):
                text = property_line + suffix + '\n'
                if property_line.startswith('distributionSha256Sum'):
                    text = WRAPPER + text
                with self.subTest(property_line=property_line, suffix=suffix), self.assertRaises(module.InventoryError):
                    module.read_wrapper(text, SOURCE)

    def test_non_ascii_and_non_java_control_characters_are_rejected(self):
        module = tool()
        for char in ('\v', '\x1c', '\x1d', '\x1e', '\x00', '\x7f', '\x85', '\xa0', '\u2028', '\u2029', 'é'):
            for text in (char + WRAPPER, WRAPPER + 'networkTimeout=10000' + char + '\n'):
                with self.subTest(char=repr(char), text=text), self.assertRaises(module.InventoryError):
                    module.read_wrapper(text, SOURCE)

    def test_supported_ascii_properties_preserve_wrapper_metadata(self):
        module = tool()
        for newline in ('\n', '\r', '\r\n'):
            for escaped in (False, True):
                url = URL.replace('https:', r'https\:') if escaped else URL
                text = newline.join((' \t\f# comment with ignored trailing backslash\\', '! comment', '',
                                     ' \t\fdistributionUrl \t\f= \t\f' + url,
                                     'distributionSha256Sum=' + 'c' * 64,
                                     'distributionPath=wrapper/dists', 'networkTimeout=10000'))
                with self.subTest(newline=newline, escaped=escaped):
                    self.assertEqual(module.read_wrapper(text, SOURCE), {
                        'name': 'gradle-7.6.4-all.zip', 'version': '7.6.4', 'url': URL, 'source': SOURCE,
                        'hashes': [{'alg': 'SHA-256', 'content': 'c' * 64}]})
        self.assertNotIn('hashes', module.read_wrapper(WRAPPER, SOURCE))


if __name__ == '__main__':
    unittest.main()

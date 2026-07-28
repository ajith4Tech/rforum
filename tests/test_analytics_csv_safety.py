"""Unit tests for app/routers/analytics.py::_csv_safe — the CSV/spreadsheet
formula-injection mitigation applied to guest-controlled response fields
(value, guest_identifier, name) in the event/session CSV exports."""
from app.routers.analytics import _csv_safe


class TestCsvSafe:

    def test_plain_text_unchanged(self):
        assert _csv_safe("hello world") == "hello world"

    def test_equals_prefix_is_neutralized(self):
        assert _csv_safe("=1+1") == "'=1+1"

    def test_plus_prefix_is_neutralized(self):
        assert _csv_safe("+1+1") == "'+1+1"

    def test_minus_prefix_is_neutralized(self):
        assert _csv_safe("-1+1") == "'-1+1"

    def test_at_prefix_is_neutralized(self):
        assert _csv_safe("@SUM(A1:A10)") == "'@SUM(A1:A10)"

    def test_tab_prefix_is_neutralized(self):
        assert _csv_safe("\t=cmd") == "'\t=cmd"

    def test_formula_char_mid_string_is_not_touched(self):
        # Only a leading formula-trigger character is dangerous — a normal
        # response containing "=" or "+" elsewhere must not be mutated.
        assert _csv_safe("2 + 2 = 4") == "2 + 2 = 4"

    def test_none_passed_through(self):
        assert _csv_safe(None) is None

    def test_non_string_passed_through(self):
        assert _csv_safe(5) == 5

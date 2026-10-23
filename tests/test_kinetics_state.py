"""Regression tests for restored kinetics controls and page navigation."""

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.elements.lib import policies
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).parents[1]
KINETICS_PAGE = "pages/1_Kinetics_Simulation.py"
DEFAULTS = {
    "simulation_rtol": 1e-6,
    "simulation_atol": 1e-9,
    "perturbation_variation": 20,
    "perturbation_levels": 9,
    "perturbation_sweep_end_time": 120.0,
}


class KineticsStateTests(unittest.TestCase):
    """Verify kinetics defaults, restored controls, and model invalidation.

    Examples
    --------
    >>> suite = unittest.defaultTestLoader.loadTestsFromTestCase(KineticsStateTests)
    >>> suite.countTestCases()
    3
    """

    def test_first_visit_uses_defaults_without_duplicate_state_warning(self):
        """Render the initial controls with their established defaults.

        Returns
        -------
        None
            Assertions fail if defaults change or Streamlit logs a warning.

        Examples
        --------
        >>> DEFAULTS["simulation_rtol"]
        1e-06
        """
        with patch.object(policies, "_shown_default_value_warning", False):
            with self.assertNoLogs(policies._LOGGER, level="WARNING"):
                app = AppTest.from_file(ROOT / KINETICS_PAGE, default_timeout=30).run()
                app.run()
        self.assertEqual(list(app.exception), [])
        for key, value in DEFAULTS.items():
            self.assertEqual(app.session_state[key], value)

    def test_navigation_restores_edits_without_duplicate_state_warning(self):
        """Restore edited controls after visiting both other app pages.

        Returns
        -------
        None
            Assertions fail on lost edits, page exceptions, or duplicate defaults.

        Examples
        --------
        >>> KINETICS_PAGE.endswith("1_Kinetics_Simulation.py")
        True
        """
        edited = {
            "simulation_rtol": 2e-5,
            "simulation_atol": 3e-8,
            "perturbation_variation": 35,
            "perturbation_levels": 11,
            "perturbation_sweep_end_time": 180.0,
        }
        app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
        app.switch_page(KINETICS_PAGE).run()
        self.assertEqual(list(app.exception), [])
        for key in ("simulation_rtol", "simulation_atol", "perturbation_sweep_end_time"):
            app.number_input(key=key).set_value(edited[key])
        app.slider(key="perturbation_variation").set_value(edited["perturbation_variation"])
        app.select_slider(key="perturbation_levels").set_value(edited["perturbation_levels"])
        app.run()
        for page in ("pages/0_Model_Overview.py", "pages/2_Importance_Analysis.py"):
            with self.subTest(page=page):
                app.switch_page(page).run()
                self.assertEqual(list(app.exception), [])
                self.assertNotIn("simulation_rtol", app.session_state.filtered_state)
                with patch.object(policies, "_shown_default_value_warning", False):
                    with self.assertNoLogs(policies._LOGGER, level="WARNING"):
                        app.switch_page(KINETICS_PAGE).run()
                        app.run()
                self.assertEqual(list(app.exception), [])
                for key, value in edited.items():
                    self.assertEqual(app.session_state[key], value)

    def test_model_change_discards_stale_results_and_saved_settings(self):
        """Keep model invalidation ahead of settings restoration.

        Returns
        -------
        None
            Assertions fail if stale model results or settings survive.

        Examples
        --------
        >>> DEFAULTS["perturbation_levels"]
        9
        """
        app = AppTest.from_file(ROOT / KINETICS_PAGE, default_timeout=30)
        app.session_state["kinetics_experiment_model_signature"] = "previous-model"
        app.session_state["simulation_results"] = "stale-result"
        app.session_state["perturbation_sweep_result"] = "stale-sweep"
        app.session_state["perturbation_saved_settings"] = {
            "simulation_rtol": 0.5,
            "perturbation_levels": 21,
        }
        app.run()
        self.assertEqual(list(app.exception), [])
        self.assertIsNone(app.session_state["simulation_results"])
        self.assertIsNone(app.session_state["perturbation_sweep_result"])
        for key, value in DEFAULTS.items():
            self.assertEqual(app.session_state[key], value)


if __name__ == "__main__":
    unittest.main()

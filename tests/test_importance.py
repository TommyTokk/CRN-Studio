"""Contract and UI tests for fixed-grid species importance analysis."""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import libsbml
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from logic import importance
from logic.experiments import sim_ut

PAGE = Path(__file__).parents[1] / "pages" / "2_Importance_Analysis.py"


def model_bytes():
    """Build an SBML fixture with three observable species.

    Returns
    -------
    bytes
        Serialized SBML with one extra independent reporter.

    Examples
    --------
    >>> b'S3' in model_bytes()
    True
    """
    document = libsbml.SBMLDocument(3, 2)
    model = document.createModel()
    model.setId("importance_fixture")
    compartment = model.createCompartment()
    compartment.setId("cell")
    compartment.setSize(1.0)
    compartment.setConstant(True)
    for sid, name, initial in (("S1", "Source", 1.0), ("S2", "Product", 0.0)):
        species = model.createSpecies()
        species.setId(sid)
        species.setName(name)
        species.setCompartment("cell")
        species.setInitialConcentration(initial)
        species.setHasOnlySubstanceUnits(False)
        species.setBoundaryCondition(False)
        species.setConstant(False)
    parameter = model.createParameter()
    parameter.setId("k")
    parameter.setValue(0.1)
    parameter.setConstant(True)
    reaction = model.createReaction()
    reaction.setId("R1")
    reaction.setReversible(False)
    reactant = reaction.createReactant()
    reactant.setSpecies("S1")
    reactant.setStoichiometry(1.0)
    reactant.setConstant(True)
    product = reaction.createProduct()
    product.setSpecies("S2")
    product.setStoichiometry(1.0)
    product.setConstant(True)
    reaction.createKineticLaw().setMath(libsbml.parseL3Formula("k * S1"))
    species = model.createSpecies()
    species.setId("S3")
    species.setName("Reporter")
    species.setCompartment("cell")
    species.setInitialConcentration(0.5)
    species.setHasOnlySubstanceUnits(False)
    species.setBoundaryCondition(False)
    species.setConstant(False)
    return libsbml.writeSBMLToString(model.getSBMLDocument()).encode()


def configured_app():
    """Create a page with a model and valid multi-target selections.

    Returns
    -------
    AppTest
        Ready-to-run importance page.

    Examples
    --------
    >>> app = configured_app()
    >>> app.button(key="importance_run").disabled
    False
    """
    raw = model_bytes()
    app = AppTest.from_file(PAGE, default_timeout=30)
    app.session_state["shapcrn_loaded_model"] = libsbml.readSBMLFromString(
        raw.decode()
    ).getModel()
    app.session_state["shapcrn_model_bytes"] = raw
    app.run()
    app.multiselect(key="importance_inputs").set_value(["S1"]).run()
    app.multiselect(key="importance_targets").set_value(["S2", "S3"]).run()
    return app


class ImportanceTests(unittest.TestCase):
    """Verify library integration, scientific values, and UI result lifecycle.

    Examples
    --------
    >>> suite = unittest.defaultTestLoader.loadTestsFromTestCase(ImportanceTests)
    >>> suite.countTestCases() > 0
    True
    """

    def test_contract_and_temporary_cleanup(self):
        """Check fixed levels, forwarding, normalization, and cleanup.

        Returns
        -------
        None
            Assertions fail if the public API contract changes.

        Examples
        --------
        >>> ImportanceTests('test_contract_and_temporary_cleanup').run().wasSuccessful()
        True
        """
        raw = model_bytes()
        frame = pd.DataFrame(
            {"[S2]": [np.nan, -2.5], "S3": [4.0, np.nan], "[S1]": [99.0, 99.0]},
            index=["S2", "S3"],
        )
        response = SimpleNamespace(shapley_values=frame, variations=frame.abs())
        for operation in ("knockout", "knockin"):
            for payoff in ("last", "max", "min"):
                with patch.object(
                    importance, "assess_importance", return_value=response
                ) as assess:
                    result = importance.run_importance_analysis(
                        raw,
                        input_species_ids=["S1"],
                        target_species_ids=["S3", "S2"],
                        knock_species_ids=["S3", "S2"],
                        level_count=3,
                        operation=operation,
                        payoff=payoff,
                    )
                self.assertFalse(assess.call_args.args[0].exists())
                self.assertEqual(
                    assess.call_args.kwargs["fixed_perturbations"], [-20.0, 0.0, 20.0]
                )
                self.assertEqual(assess.call_args.kwargs["operation"], operation)
                self.assertEqual(assess.call_args.kwargs["payoff"], payoff)
                self.assertTrue(assess.call_args.kwargs["preserve_inputs"])
                self.assertTrue(assess.call_args.kwargs["use_perturbations"])
                self.assertIsNone(assess.call_args.kwargs["output_dir"])
                self.assertEqual(list(result.shapley_values.columns), ["S3", "S2"])
                self.assertEqual(list(result.shapley_values.index), ["S3", "S2"])
                self.assertEqual(result.shapley_values.loc["S3", "S2"], -2.5)
                self.assertTrue(pd.isna(result.shapley_values.loc["S3", "S3"]))
                self.assertEqual(result.combination_count, 3)
        with (
            patch.object(
                importance, "assess_importance", side_effect=RuntimeError("failed")
            ) as assess,
            self.assertRaisesRegex(RuntimeError, "failed"),
        ):
            importance.run_importance_analysis(
                raw,
                input_species_ids=["S1"],
                target_species_ids=["S2"],
                knock_species_ids=["S3"],
            )
        self.assertFalse(assess.call_args.args[0].parent.exists())

    def test_invalid_configurations_never_call_library(self):
        """Reject invalid selections and oversized grids before simulation.

        Returns
        -------
        None
            Validations must fail before invoking ShapCRN.

        Examples
        --------
        >>> ImportanceTests('test_invalid_configurations_never_call_library').run().wasSuccessful()
        True
        """
        defaults = {
            "input_species_ids": ["S1"],
            "target_species_ids": ["S2"],
            "knock_species_ids": ["S3"],
        }
        for change in (
            {"input_species_ids": []},
            {"target_species_ids": []},
            {"knock_species_ids": []},
            {"input_species_ids": ["missing"]},
            {"target_species_ids": ["S1"]},
            {"knock_species_ids": ["S1"]},
            {"target_species_ids": ["S2", "S2"]},
            {"level_count": 4},
            {"level_count": float("nan")},
            {"level_count": 3.5},
            {"end_time": 0},
            {"end_time": float("inf")},
            {"variation_percentage": 101},
            {"operation": "other"},
            {"payoff": "other"},
            {"max_combinations": 2},
        ):
            with (
                self.subTest(change=change),
                patch.object(importance, "assess_importance") as assess,
            ):
                with self.assertRaises(ValueError):
                    importance.run_importance_analysis(
                        model_bytes(), **(defaults | change)
                    )
                assess.assert_not_called()

    def test_real_library_preserves_model_and_returns_targets(self):
        """Run the public ShapCRN API against a small real model.

        Returns
        -------
        None
            Real KO/KI results must match the requested matrix dimensions.

        Examples
        --------
        >>> ImportanceTests('test_real_library_preserves_model_and_returns_targets').run().wasSuccessful()
        True
        """
        raw = model_bytes()
        for operation in ("knockout", "knockin"):
            with patch.object(sim_ut, "_resolve_n_processes", return_value=1):
                result = importance.run_importance_analysis(
                    raw,
                    input_species_ids=["S1"],
                    target_species_ids=["S2", "S3"],
                    knock_species_ids=["S2", "S3"],
                    level_count=3,
                    end_time=1.0,
                    operation=operation,
                )
            self.assertEqual(result.shapley_values.shape, (2, 2))
            self.assertEqual(result.variations.shape, (2, 2))
            self.assertTrue(np.isnan(result.shapley_values.loc["S2", "S2"]))
            self.assertTrue(np.isfinite(result.shapley_values.loc["S2", "S3"]))
            self.assertEqual(raw, model_bytes())

    def test_rejects_missing_matrices_and_ambiguous_labels(self):
        """Reject incomplete or ambiguous results instead of fabricating values.

        Returns
        -------
        None
            Invalid library results must raise a descriptive error.

        Examples
        --------
        >>> ImportanceTests('test_rejects_missing_matrices_and_ambiguous_labels').run().wasSuccessful()
        True
        """
        for frame in (
            None,
            pd.DataFrame({"wrong": [1.0]}, index=["S3"]),
            pd.DataFrame([[1.0, 2.0]], columns=["S2", "[S2]"], index=["S3"]),
        ):
            response = SimpleNamespace(shapley_values=frame, variations=frame)
            with (
                patch.object(importance, "assess_importance", return_value=response),
                self.assertRaisesRegex((ValueError, TypeError), "ShapCRN"),
            ):
                importance.run_importance_analysis(
                    model_bytes(),
                    input_species_ids=["S1"],
                    target_species_ids=["S2"],
                    knock_species_ids=["S3"],
                )

    def test_page_selections_limits_and_empty_state(self):
        """Check disabled states and pruning when inputs change.

        Returns
        -------
        None
            UI selections must remain valid for the active model.

        Examples
        --------
        >>> ImportanceTests('test_page_selections_limits_and_empty_state').run().wasSuccessful()
        True
        """
        empty = AppTest.from_file(PAGE).run()
        self.assertFalse(list(empty.exception))
        self.assertTrue(empty.button(key="importance_run").disabled)
        app = configured_app()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.multiselect(key="importance_players").value, ["S2", "S3"])
        app.multiselect(key="importance_inputs").set_value(["S1", "S2"]).run()
        self.assertEqual(app.multiselect(key="importance_targets").value, ["S3"])
        self.assertEqual(app.multiselect(key="importance_players").value, ["S3"])
        self.assertTrue(
            any("start at zero" in warning.value for warning in app.warning)
        )
        app.multiselect(key="importance_inputs").set_value(["S1", "S2", "S3"]).run()
        app.select_slider(key="importance_levels").set_value(21).run()
        self.assertTrue(app.button(key="importance_run").disabled)
        self.assertTrue(any("2,000 combinations" in error.value for error in app.error))

    def test_page_charts_and_result_lifecycle(self):
        """Verify raw tooltips, transformed colors, and persistent results.

        Returns
        -------
        None
            Chart content and stale-result handling must reflect saved data.

        Examples
        --------
        >>> ImportanceTests('test_page_charts_and_result_lifecycle').run().wasSuccessful()
        True
        """
        app = configured_app()
        frame = pd.DataFrame(
            {"S2": [np.nan, -2.5], "S3": [4.0, np.nan]}, index=["S2", "S3"]
        )
        result = importance.ImportanceAnalysisResult(
            frame, frame.abs(), (-20.0, 0.0, 20.0), 3
        )
        for mode in ("KO", "KI"):
            for payoff in ("last", "max", "min"):
                app.radio(key="importance_operation").set_value(mode).run()
                app.selectbox(key="importance_payoff").set_value(payoff).run()
                with patch.object(
                    importance, "run_importance_analysis", return_value=result
                ) as run:
                    app.button(key="importance_run").click().run()
                self.assertFalse(list(app.exception))
                self.assertEqual(
                    run.call_args.kwargs["operation"],
                    "knockout" if mode == "KO" else "knockin",
                )
                self.assertEqual(run.call_args.kwargs["payoff"], payoff)
        self.assertEqual(
            [tab.label for tab in app.tabs], ["S2 — Product", "S3 — Reporter"]
        )
        rendered = "\n".join(element.value for element in app.markdown)
        self.assertIn("S3 — Reporter", rendered)
        self.assertIn("S2 — Product", rendered)
        self.assertIn("Payoff ↑", rendered)
        self.assertIn("Payoff ↓", rendered)
        self.assertIn("2.5", rendered)
        self.assertIn("4", rendered)
        self.assertIn("Median |log₂ ratio|", rendered)
        charts = {
            chart.key: json.loads(chart.proto.spec) for chart in app.get("plotly_chart")
        }
        self.assertEqual(len(charts), 4)
        self.assertEqual(charts["importance_bar_S2"]["data"][0]["x"], [-2.5])
        heatmap = charts["importance_heatmap_shapley"]["data"][0]
        self.assertEqual(heatmap["customdata"][1][0], -2.5)
        self.assertNotEqual(heatmap["z"][1][0], -2.5)
        self.assertEqual(heatmap["zmid"], 0)
        self.assertIn("customdata", heatmap["hovertemplate"])
        app.number_input(key="importance_end_time").set_value(130.0).run()
        self.assertTrue(any("settings have changed" in info.value for info in app.info))
        with patch.object(
            importance,
            "run_importance_analysis",
            side_effect=RuntimeError("test failure"),
        ):
            app.button(key="importance_run").click().run()
        self.assertTrue(any("test failure" in error.value for error in app.error))
        self.assertIs(app.session_state["importance_result"], result)
        app.session_state["shapcrn_model_bytes"] = b"changed-model"
        app.run()
        self.assertNotIn("importance_result", app.session_state)
        self.assertEqual(len(app.get("plotly_chart")), 0)

    def test_cached_target_and_player_subsets_do_not_rerun_analysis(self):
        """Filter cached importance matrices without calling ShapCRN again.

        Returns
        -------
        None
            Assertions verify target/player slicing and cached button state.

        Examples
        --------
        >>> ImportanceTests(
        ...     'test_cached_target_and_player_subsets_do_not_rerun_analysis'
        ... ).run().wasSuccessful()
        True
        """
        app = configured_app()
        frame = pd.DataFrame(
            {"S2": [np.nan, -2.5], "S3": [4.0, np.nan]},
            index=["S2", "S3"],
        )
        result = importance.ImportanceAnalysisResult(
            frame,
            frame.abs(),
            (-20.0, 0.0, 20.0),
            3,
        )
        app.multiselect(key="importance_targets").set_value(["S2"]).run()
        with patch.object(
            importance,
            "run_importance_analysis",
            return_value=result,
        ) as initial_run:
            app.button(key="importance_run").click().run()
        self.assertEqual(
            initial_run.call_args.kwargs["target_species_ids"],
            ("S2", "S3"),
        )

        with patch.object(importance, "run_importance_analysis") as run:
            app.multiselect(key="importance_targets").set_value(["S3"]).run()
            app.multiselect(key="importance_players").set_value(["S3"]).run()

        run.assert_not_called()
        self.assertTrue(app.button(key="importance_run").disabled)
        self.assertEqual([tab.label for tab in app.tabs], ["S3 — Reporter"])
        heatmap = next(
            json.loads(chart.proto.spec)
            for chart in app.get("plotly_chart")
            if chart.key == "importance_heatmap_shapley"
        )
        self.assertEqual(heatmap["data"][0]["y"], ["S3 — Reporter"])

    def test_summary_cards_handle_ties_zeroes_and_missing_values(self):
        """Render explicit summaries for tied, zero, and unavailable results.

        Returns
        -------
        None
            Card values must remain meaningful for attribution edge cases.

        Examples
        --------
        >>> ImportanceTests('test_summary_cards_handle_ties_zeroes_and_missing_values').run().wasSuccessful()
        True
        """
        app = configured_app()
        tied_and_zero = importance.ImportanceAnalysisResult(
            pd.DataFrame(
                {"S2": [2.0, -2.0], "S3": [0.0, 0.0]},
                index=["S2", "S3"],
            ),
            pd.DataFrame(
                {"S2": [0.5, 1.5], "S3": [3.0, 4.0]},
                index=["S2", "S3"],
            ),
            (-20.0, 0.0, 20.0),
            3,
        )
        with patch.object(
            importance, "run_importance_analysis", return_value=tied_and_zero
        ):
            app.button(key="importance_run").click().run()
        self.assertFalse(list(app.exception))
        rendered = "\n".join(element.value for element in app.markdown)
        self.assertIn("Tie (2)", rendered)
        self.assertIn("S2 — Product · S3 — Reporter", rendered)
        self.assertIn("Mixed", rendered)
        self.assertIn("0.5–1.5", rendered)
        self.assertIn("No dominant effect", rendered)
        self.assertIn("No change", rendered)
        self.assertIn("Not applicable without a dominant effect", rendered)

        missing = importance.ImportanceAnalysisResult(
            pd.DataFrame(
                {"S2": [np.nan, -3.0], "S3": [np.nan, np.nan]},
                index=["S2", "S3"],
            ),
            pd.DataFrame(
                {"S2": [np.nan, np.nan], "S3": [np.nan, np.nan]},
                index=["S2", "S3"],
            ),
            (-20.0, 0.0, 20.0),
            3,
        )
        app.selectbox(key="importance_payoff").set_value("max").run()
        with patch.object(
            importance, "run_importance_analysis", return_value=missing
        ):
            app.button(key="importance_run").click().run()
        self.assertFalse(list(app.exception))
        rendered = "\n".join(element.value for element in app.markdown)
        self.assertIn("No variation value is available for the top species", rendered)
        self.assertEqual(rendered.count("Top knock species"), 1)
        self.assertTrue(
            any("No valid attribution values" in info.value for info in app.info)
        )

    def test_sidebar_model_switch_uses_current_source(self):
        """Reparse a newly selected source even if Overview still holds old data.

        Returns
        -------
        None
            New selectors must reflect the active source rather than stale SBML.

        Examples
        --------
        >>> ImportanceTests('test_sidebar_model_switch_uses_current_source').run().wasSuccessful()
        True
        """
        app = configured_app()
        document = libsbml.readSBMLFromString(model_bytes().decode())
        document.getModel().getSpecies("S3").setId("S4")
        app.session_state["shapcrn_model_bytes"] = libsbml.writeSBMLToString(
            document
        ).encode()
        app.run()
        self.assertFalse(list(app.exception))
        self.assertIn(
            "S4 — Reporter", app.multiselect(key="importance_targets").options
        )
        self.assertNotIn(
            "S3 — Reporter", app.multiselect(key="importance_targets").options
        )
        self.assertEqual(app.multiselect(key="importance_targets").value, [])
        app.session_state["shapcrn_model_library"] = {}
        del app.session_state["shapcrn_model_bytes"]
        app.run()
        self.assertTrue(app.button(key="importance_run").disabled)

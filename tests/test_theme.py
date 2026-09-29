"""Theme-token, contrast, and Plotly presentation tests."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from ui.phase_plot_3d import SceneTransform, apply_scientific_scene
from ui.styles import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    THEME_STATE_KEY,
    apply_plotly_theme,
    get_theme_palette,
)

APP_ENTRYPOINT = Path(__file__).parents[1] / "app.py"


def _relative_luminance(color: str) -> float:
    """Return WCAG relative luminance for a six-digit hexadecimal colour.

    Parameters
    ----------
    color : str
        Colour formatted as ``#RRGGBB``.

    Returns
    -------
    float
        Relative luminance between zero and one.

    Examples
    --------
    >>> _relative_luminance("#000000")
    0.0
    """
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    """Return the WCAG contrast ratio between two hexadecimal colours.

    Parameters
    ----------
    first : str
        First colour formatted as ``#RRGGBB``.
    second : str
        Second colour formatted as ``#RRGGBB``.

    Returns
    -------
    float
        Contrast ratio from one to twenty-one.

    Examples
    --------
    >>> _contrast_ratio("#000000", "#FFFFFF")
    21.0
    """
    luminances = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (luminances[0] + 0.05) / (luminances[1] + 0.05)


class ThemeTests(unittest.TestCase):
    """Verify accessible theme tokens and themed visualisations.

    Examples
    --------
    >>> suite = unittest.defaultTestLoader.loadTestsFromTestCase(ThemeTests)
    >>> suite.countTestCases() > 0
    True
    """

    def test_palettes_expose_the_same_semantic_tokens(self):
        """Require both themes to implement the complete semantic contract.

        Returns
        -------
        None
            Assertions fail if either palette loses or changes a token.

        Examples
        --------
        >>> set(LIGHT_PALETTE) == set(DARK_PALETTE)
        True
        """
        self.assertEqual(set(LIGHT_PALETTE), set(DARK_PALETTE))
        self.assertEqual(get_theme_palette("light"), LIGHT_PALETTE)
        self.assertEqual(get_theme_palette("dark"), DARK_PALETTE)
        self.assertIsNot(get_theme_palette("light"), LIGHT_PALETTE)

    def test_text_and_interaction_contrast_meet_wcag_thresholds(self):
        """Check AA text contrast and non-text component contrast.

        Returns
        -------
        None
            Assertions fail when a protected colour pair falls below WCAG AA.

        Examples
        --------
        >>> _contrast_ratio("#2B2D42", "#FFFDF9") > 4.5
        True
        """
        text_pairs = (
            ("text", "paper"),
            ("text", "canvas"),
            ("text_soft", "paper"),
            ("primary_text", "primary_bg"),
            ("primary_text", "primary_hover"),
            ("terra_text", "terra_bg"),
            ("success_text", "success_bg"),
            ("amber_text", "amber_bg"),
            ("text", "plot_bg"),
            ("text_soft", "plot_area"),
        )
        component_pairs = (
            ("focus", "canvas"),
            ("border_strong", "paper"),
            ("graph_edge", "plot_bg"),
            ("graph_species", "plot_bg"),
            ("graph_reaction", "plot_bg"),
        )
        for palette in (LIGHT_PALETTE, DARK_PALETTE):
            for foreground, background in text_pairs:
                with self.subTest(
                    theme=palette["canvas"], pair=(foreground, background)
                ):
                    self.assertGreaterEqual(
                        _contrast_ratio(palette[foreground], palette[background]),
                        4.5,
                    )
            for foreground, background in component_pairs:
                with self.subTest(
                    theme=palette["canvas"], pair=(foreground, background)
                ):
                    self.assertGreaterEqual(
                        _contrast_ratio(palette[foreground], palette[background]),
                        3.0,
                    )

    def test_plotly_theme_styles_layout_axes_hover_and_colorway(self):
        """Apply every major Plotly presentation token in both themes.

        Returns
        -------
        None
            Assertions fail when a figure retains an unthemed visual surface.

        Examples
        --------
        >>> apply_plotly_theme(go.Figure(), "dark").layout.paper_bgcolor
        '#252837'
        """
        for theme in ("light", "dark"):
            palette = get_theme_palette(theme)
            figure = apply_plotly_theme(
                go.Figure(go.Scatter(x=[0, 1], y=[0, 1])), theme
            )
            self.assertEqual(figure.layout.paper_bgcolor, palette["plot_bg"])
            self.assertEqual(figure.layout.plot_bgcolor, palette["plot_area"])
            self.assertEqual(figure.layout.font.color, palette["text"])
            self.assertEqual(figure.layout.xaxis.gridcolor, palette["plot_grid"])
            self.assertEqual(figure.layout.yaxis.tickfont.color, palette["text_soft"])
            self.assertEqual(figure.layout.hoverlabel.bgcolor, palette["hover_bg"])
            self.assertEqual(list(figure.layout.colorway), [
                palette[f"data_{index}"] for index in range(1, 9)
            ])

    def test_scientific_scene_accepts_dark_theme_tokens(self):
        """Render the 3D scene without retaining a white canvas.

        Returns
        -------
        None
            Assertions fail when the scene does not use supplied dark tokens.

        Examples
        --------
        >>> get_theme_palette("dark")["plot_bg"]
        '#252837'
        """
        points = np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]])
        transform = SceneTransform.from_point_sets([points])
        figure = go.Figure()
        palette = get_theme_palette("dark")
        apply_scientific_scene(
            figure,
            title="Dark trajectory",
            axis_titles=("A", "B", "C"),
            transform=transform,
            theme_tokens=palette,
        )
        self.assertEqual(figure.layout.paper_bgcolor, palette["plot_bg"])
        self.assertEqual(figure.layout.scene.bgcolor, palette["plot_area"])
        self.assertEqual(
            figure.layout.scene.xaxis.tickfont.color,
            palette["text_soft"],
        )
        self.assertEqual(figure.layout.hoverlabel.bgcolor, palette["hover_bg"])
        self.assertEqual(figure.layout.legend.orientation, "h")
        self.assertLess(figure.layout.legend.y, 0)
        self.assertGreaterEqual(figure.layout.margin.b, 150)

    def test_app_theme_control_switches_session_theme(self):
        """Switch the shared app shell from light to dark without exceptions.

        Returns
        -------
        None
            Assertions fail when the theme widget cannot rerun the application.

        Examples
        --------
        >>> APP_ENTRYPOINT.name
        'app.py'
        """
        app = AppTest.from_file(APP_ENTRYPOINT, default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        app.radio(key=THEME_STATE_KEY).set_value("dark").run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state[THEME_STATE_KEY], "dark")


if __name__ == "__main__":
    unittest.main()

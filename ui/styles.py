"""Design-system tokens and global Streamlit styling.

The visual language is based on the supplied "Kinetic Lab Minimal" design system:
warm editorial surfaces, terracotta/sage/amber accents, Inter for UI copy, and
IBM Plex Mono for scientific/technical labels.

Keep *presentation* here. Keep ShapCRN/scientific logic in ``logic/``.
"""

from __future__ import annotations

import streamlit as st


LIGHT_PALETTE = {
    # Canvas / surfaces
    "canvas": "#FBF8FF",
    "paper": "#FFFDF9",
    "surface": "#F8F5F0",
    "surface_low": "#F4F2FF",
    "surface_mid": "#EDECFB",
    "well": "#EFEAE1",
    "border": "#E8E2D9",
    "border_strong": "#D9D0C3",
    # Text
    "text": "#2B2D42",
    "text_soft": "#666A86",
    "code": "#1E202C",
    # Scientific accents
    "terracotta": "#E07A5F",
    "terracotta_dark": "#9A442D",
    "sage": "#81B29A",
    "sage_dark": "#386753",
    "amber": "#F2CC8F",
    "amber_dark": "#765A28",
    "slate": "#3D405B",
    "mineral": "#8D99AE",
    "error": "#D1495B",
    # Component state colours
    "success_bg": "#DDF3E7",
    "success_text": "#386753",
    "success_border": "#B8EBD1",
    "terra_bg": "#F9E1DA",
    "terra_text": "#8A321E",
    "amber_bg": "#FCECCB",
    "amber_text": "#745214",
    "nav_hover": "#F1ECE6",
    "upload_hover": "#F9EFEC",
    "disabled_bg": "#F1EEE8",
    "disabled_text": "#777A8E",
    "tab_border": "#ECE8F7",
    # Derived / visualization helpers
    "negative": "#5F8F7C",
    "neutral": "#F4EFE9",
    "positive": "#D86F55",
}


DARK_PALETTE = {
    # Dark-mode tokens from the supplied design system.
    "canvas": "#1E202C",
    "paper": "#252837",
    "surface": "#252837",
    "surface_low": "#2D3043",
    "surface_mid": "#33364A",
    "well": "#181923",
    "border": "#3D4158",
    "border_strong": "#4E536F",
    "text": "#F8F5F0",
    "text_soft": "#A5A9C0",
    "code": "#FDFBF7",
    "terracotta": "#E07A5F",
    "terracotta_dark": "#FFB4A1",
    "sage": "#81B29A",
    "sage_dark": "#9FD1B8",
    "amber": "#F2CC8F",
    "amber_dark": "#E6C185",
    "slate": "#D6D8F9",
    "mineral": "#8D99AE",
    "error": "#FF7B86",
    "success_bg": "#243D34",
    "success_text": "#AEE0C7",
    "success_border": "#355A4B",
    "terra_bg": "#4A2A25",
    "terra_text": "#FFB4A1",
    "amber_bg": "#493B22",
    "amber_text": "#F2CC8F",
    "nav_hover": "#303347",
    "upload_hover": "#352B31",
    "disabled_bg": "#2A2D3C",
    "disabled_text": "#7F849E",
    "tab_border": "#3D4158",
    "negative": "#81B29A",
    "neutral": "#33364A",
    "positive": "#E07A5F",
}

# Backwards-compatible alias for code that only needs the light design tokens.
PALETTE = LIGHT_PALETTE


THEME_STATE_KEY = "ui_theme"


def ensure_ui_state() -> None:
    """Initialise UI state shared by every Streamlit page.

    Streamlit multipage apps share ``st.session_state`` within the same browser
    session. Keeping the theme under one key means switching it in the sidebar
    immediately applies to Overview, Kinetics, and Importance on their next run.
    """
    if THEME_STATE_KEY not in st.session_state:
        # Migrate the older boolean key if someone opens a session created by a
        # previous version of the skeleton.
        if "ui_dark_mode" in st.session_state:
            st.session_state[THEME_STATE_KEY] = (
                "dark" if st.session_state.get("ui_dark_mode") else "light"
            )
        else:
            st.session_state[THEME_STATE_KEY] = "light"


def current_theme() -> str:
    """Return the app-wide theme selected in the custom sidebar."""
    ensure_ui_state()
    theme = str(st.session_state.get(THEME_STATE_KEY, "light")).lower()
    return "dark" if theme == "dark" else "light"



def apply_global_styles() -> None:
    """Inject the design-system CSS used by every page.

    Notes for future you:
    - Streamlit owns the HTML structure, so some selectors target ``data-testid``.
    - These selectors can occasionally change between Streamlit releases.
    - If a Streamlit update breaks one visual rule, the scientific code is still
      isolated from styling here.
    """

    ensure_ui_state()
    palette = DARK_PALETTE if current_theme() == "dark" else LIGHT_PALETTE

    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');

            :root {{
                --canvas: {palette['canvas']};
                --paper: {palette['paper']};
                --surface: {palette['surface']};
                --surface-low: {palette['surface_low']};
                --surface-mid: {palette['surface_mid']};
                --well: {palette['well']};
                --border: {palette['border']};
                --border-strong: {palette['border_strong']};
                --text: {palette['text']};
                --text-soft: {palette['text_soft']};
                --terracotta: {palette['terracotta']};
                --terracotta-dark: {palette['terracotta_dark']};
                --sage: {palette['sage']};
                --amber: {palette['amber']};
                --slate: {palette['slate']};
                --sage-dark: {palette['sage_dark']};
                --amber-dark: {palette['amber_dark']};
                --mineral: {palette['mineral']};
                --error: {palette['error']};
                --success-bg: {palette['success_bg']};
                --success-text: {palette['success_text']};
                --success-border: {palette['success_border']};
                --terra-bg: {palette['terra_bg']};
                --terra-text: {palette['terra_text']};
                --amber-bg: {palette['amber_bg']};
                --amber-text: {palette['amber_text']};
                --nav-hover: {palette['nav_hover']};
                --upload-hover: {palette['upload_hover']};
                --disabled-bg: {palette['disabled_bg']};
                --disabled-text: {palette['disabled_text']};
                --tab-border: {palette['tab_border']};
                --negative: {palette['negative']};
                --neutral: {palette['neutral']};
                --positive: {palette['positive']};
                color-scheme: {'dark' if current_theme() == 'dark' else 'light'};
            }}

            html, body, [class*="css"] {{
                font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}

            /* Paint every root layer with the active theme. During a page rerun
               Streamlit briefly exposes layers beneath .stApp; styling only
               .stApp can therefore produce a white flash between pages. */
            html,
            body,
            #root,
            .stApp,
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            [data-testid="stMainBlockContainer"] {{
                background: var(--canvas) !important;
                color: var(--text);
            }}

            .stApp {{
                background: var(--canvas);
                color: var(--text);
            }}

            /* Streamlit marks the previous page DOM as stale while the selected
               page reruns. Do not fade that DOM to translucent gray/white; keep
               it opaque until the next page is ready, which makes navigation
               feel like a stable application shell instead of a full repaint. */
            [data-stale="true"] {{
                opacity: 1 !important;
            }}

            /* Theme-aware defaults for native Streamlit text. Custom components
               already use CSS variables, but these rules prevent stray black/white
               defaults from leaking through when the global mode changes. */
            .stApp,
            .stApp p,
            .stApp li,
            .stApp span,
            .stApp label {{
                color: var(--text);
            }}

            .stCaption,
            [data-testid="stCaptionContainer"],
            [data-testid="stCaptionContainer"] * {{
                color: var(--text-soft) !important;
            }}

            /* -------------------------------------------------------------
               Streamlit chrome
               -------------------------------------------------------------
               Streamlit renders its own fixed header / toolbar above the app.
               Because this project has a custom workspace topbar, leaving that
               chrome visible creates a half-height strip of floating controls at
               the top of every page. Hide only Streamlit's global chrome; the
               sidebar collapse control remains owned by the sidebar itself.
            */
            /* Keep the header node alive because Streamlit mounts the mobile
               "open sidebar" control inside it. We collapse the visual chrome
               to zero height instead of removing the whole header. */
            header[data-testid="stHeader"] {{
                height: 0 !important;
                min-height: 0 !important;
                background: transparent !important;
                border: 0 !important;
                overflow: visible !important;
                pointer-events: none !important;
            }}

            div[data-testid="stToolbar"],
            div[data-testid="stDecoration"],
            div[data-testid="stStatusWidget"],
            #MainMenu,
            footer,
            [data-testid="viewerBadge_link__container"] {{
                display: none !important;
            }}

            [data-testid="stSidebarCollapsedControl"] {{
                pointer-events: auto !important;
                z-index: 1000000 !important;
            }}

            /* Without Streamlit's fixed header the main view should begin at y=0. */
            [data-testid="stAppViewContainer"] {{
                padding-top: 0 !important;
            }}

            [data-testid="stSidebar"] {{
                background: var(--surface);
                border-right: 1px solid var(--border);
                width: 20rem !important;
                min-width: 20rem !important;
                max-width: 20rem !important;
                transition: none !important;
            }}

            [data-testid="stSidebar"] * {{
                box-sizing: border-box;
            }}

            /* Stable internal rail padding across Streamlit versions. */
            [data-testid="stSidebarContent"] {{
                padding: .9rem .85rem 1.15rem .85rem !important;
            }}

            [data-testid="stSidebarHeader"] {{
                padding: .2rem .2rem .35rem .2rem !important;
                min-height: 2rem !important;
            }}

            [data-testid="stSidebarCollapseButton"] button {{
                color: var(--text-soft) !important;
                background: transparent !important;
                border: 0 !important;
                box-shadow: none !important;
            }}

            [data-testid="stSidebarCollapseButton"] button * {{
                color: inherit !important;
                fill: currentColor !important;
            }}

            /* Hide Streamlit's auto-generated page list. We render a deliberate nav rail. */
            [data-testid="stSidebarNav"] {{
                display: none;
            }}

            .block-container {{
                max-width: 1600px;
                padding-top: 1rem !important;
                padding-bottom: 3.5rem !important;
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }}

            /* Prevent wide controls / charts from forcing columns outside cards. */
            [data-testid="stHorizontalBlock"],
            [data-testid="column"],
            [data-testid="stVerticalBlock"] {{
                min-width: 0;
            }}

            h1, h2, h3, h4 {{
                color: var(--text);
                letter-spacing: -0.02em;
            }}

            h1 {{
                font-size: 2.25rem !important;
                line-height: 2.75rem !important;
                font-weight: 600 !important;
            }}

            h2 {{
                font-size: 1.45rem !important;
                font-weight: 600 !important;
            }}

            h3 {{
                font-size: 1.05rem !important;
                font-weight: 600 !important;
            }}

            p, label, .stCaption {{
                color: var(--text-soft);
            }}

            code, pre, kbd,
            [data-testid="stMetricValue"],
            [data-testid="stMetricDelta"],
            .tech, .micro-label, .stat-label, .stat-value, .status-pill,
            .topbar, .sidebar-kicker, .sidebar-meta, .science-chip {{
                font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace !important;
                font-variant-numeric: tabular-nums;
            }}

            /* ---------- custom shell ---------- */
            .brand-lockup {{
                display: flex;
                align-items: center;
                gap: .7rem;
                padding: .2rem .15rem .9rem .15rem;
            }}

            .brand-mark {{
                width: 31px;
                height: 31px;
                border-radius: 8px;
                display: grid;
                place-items: center;
                background:
                    radial-gradient(circle at 30% 32%, var(--sage) 0 3px, transparent 4px),
                    radial-gradient(circle at 70% 30%, var(--terracotta) 0 3px, transparent 4px),
                    radial-gradient(circle at 51% 72%, var(--amber) 0 3px, transparent 4px),
                    var(--paper);
                border: 1px solid var(--border);
                box-shadow: 0 1px 3px rgba(61,64,91,.04);
            }}

            .brand-title {{
                color: var(--text);
                font-weight: 700;
                line-height: 1.05;
                font-size: .98rem;
            }}

            .brand-subtitle {{
                color: var(--text-soft);
                font-size: .65rem;
                margin-top: .18rem;
                font-family: "IBM Plex Mono", monospace;
                letter-spacing: .02em;
            }}

            .sidebar-kicker {{
                color: var(--text-soft);
                text-transform: uppercase;
                letter-spacing: .08em;
                font-size: .64rem;
                font-weight: 600;
                margin: 1rem 0 .35rem 0;
            }}

            .sidebar-file {{
                background: var(--paper);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: .65rem .7rem;
                box-shadow: 0 1px 3px rgba(61,64,91,.04);
            }}

            .sidebar-file-name {{
                color: var(--text);
                font-family: "IBM Plex Mono", monospace;
                font-size: .76rem;
                margin-top: .25rem;
                overflow-wrap: anywhere;
            }}

            .sidebar-meta {{
                color: var(--text-soft);
                font-size: .64rem;
                margin-top: .18rem;
            }}

            .sidebar-summary {{
                margin-top: 1rem;
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: .35rem;
                background: var(--paper);
                border: 1px solid var(--border);
                border-radius: 8px;
                padding: .65rem;
            }}

            .sidebar-summary strong {{
                display: block;
                color: var(--text);
                font-size: .88rem;
                font-family: "IBM Plex Mono", monospace;
            }}

            .sidebar-summary span {{
                color: var(--text-soft);
                font-size: .58rem;
                text-transform: uppercase;
                letter-spacing: .05em;
                font-family: "IBM Plex Mono", monospace;
            }}

            .topbar {{
                min-height: 40px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 1rem;
                padding: .35rem .15rem .65rem .15rem;
                border-bottom: 1px solid var(--border);
                margin-bottom: 1.05rem;
                font-size: .68rem;
                color: var(--text-soft);
                letter-spacing: .035em;
            }}

            .topbar-left, .topbar-right {{
                display: flex;
                align-items: center;
                gap: .8rem;
                flex-wrap: wrap;
            }}

            .status-pill {{
                display: inline-flex;
                align-items: center;
                gap: .32rem;
                padding: .23rem .58rem;
                border-radius: 999px;
                background: var(--success-bg);
                color: var(--success-text);
                font-size: .66rem;
                border: 1px solid var(--success-border);
            }}

            .topbar-link {{
                color: var(--text-soft);
            }}

            .eyebrow {{
                font-family: "IBM Plex Mono", monospace;
                color: var(--terracotta-dark);
                font-size: .67rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: .075em;
                margin-bottom: .28rem;
            }}

            .page-subtitle {{
                color: var(--text-soft);
                max-width: 850px;
                line-height: 1.55;
                margin-top: -.35rem;
            }}

            .header-status {{
                display: inline-flex;
                align-items: center;
                gap: .42rem;
                background: var(--surface-low);
                border: 1px solid var(--tab-border);
                border-radius: 999px;
                padding: .42rem .7rem;
                color: var(--text-soft);
                font-family: "IBM Plex Mono", monospace;
                font-size: .68rem;
            }}

            /* ---------- native navigation links ---------- */
            div[data-testid="stPageLink"] a {{
                border-radius: 6px;
                padding: .5rem .62rem;
                color: var(--text-soft) !important;
                transition: background 120ms ease, color 120ms ease;
            }}

            /* Streamlit puts the visible label inside nested <p>/<span> nodes;
               force those nodes to inherit the link colour as well. */
            div[data-testid="stPageLink"] a *,
            div[data-testid="stPageLink"] a p {{
                color: inherit !important;
            }}

            div[data-testid="stPageLink"] a:hover {{
                background: var(--nav-hover);
                color: var(--text) !important;
            }}

            .nav-active {{
                background: var(--terracotta);
                color: #3D180F;
                border-radius: 6px;
                padding: .52rem .65rem;
                font-size: .82rem;
                font-weight: 600;
                margin-bottom: .18rem;
            }}

            /* ---------- metric / content cards ---------- */
            .stat-card {{
                position: relative;
                background: var(--paper);
                border: 1px solid var(--border);
                border-left: 3px solid var(--terracotta);
                border-radius: 8px;
                padding: .82rem .86rem .78rem .86rem;
                min-height: 112px;
                box-shadow: 0 1px 3px rgba(61,64,91,.04);
            }}

            .stat-card.sage {{ border-left-color: var(--sage); }}
            .stat-card.amber {{ border-left-color: var(--amber); }}
            .stat-card.slate {{ border-left-color: var(--slate); }}

            .stat-label {{
                color: var(--text-soft);
                font-size: .64rem;
                line-height: .9rem;
                text-transform: uppercase;
                letter-spacing: .065em;
                font-weight: 600;
                margin-bottom: .42rem;
            }}

            .stat-value {{
                color: var(--text);
                font-size: 1.8rem;
                line-height: 1;
                font-weight: 500;
                margin-bottom: .45rem;
            }}

            .stat-help {{
                color: var(--text-soft);
                font-size: .73rem;
                line-height: 1.3;
            }}

            .science-chip {{
                display: inline-block;
                border-radius: 4px;
                padding: .15rem .34rem;
                font-size: .62rem;
                background: var(--surface-low);
                color: var(--text-soft);
                border: 1px solid rgba(219,193,186,.55);
            }}

            .science-chip.terra {{ background:var(--terra-bg); color:var(--terra-text); }}
            .science-chip.sage {{ background:var(--success-bg); color:var(--success-text); }}
            .science-chip.amber {{ background:var(--amber-bg); color:var(--amber-text); }}

            .panel-title {{
                display:flex;
                align-items:center;
                gap:.5rem;
                color:var(--text);
                font-weight:600;
                font-size:1rem;
                margin-bottom:.12rem;
            }}

            .panel-subtitle {{
                color: var(--text-soft);
                font-size: .76rem;
                margin-bottom: .6rem;
            }}

            .placeholder-box {{
                background: var(--paper);
                border: 1px dashed var(--border-strong);
                border-radius: 8px;
                min-height: 190px;
                padding: 1.1rem;
                display: flex;
                flex-direction: column;
                justify-content: center;
                color: var(--text-soft);
            }}

            .placeholder-title {{
                color: var(--text);
                font-family: "IBM Plex Mono", monospace;
                font-size: .75rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: .04em;
                margin-bottom: .35rem;
            }}

            .placeholder-copy {{
                font-size: .78rem;
                line-height: 1.45;
            }}

            .network-toolbar {{
                background: var(--surface-low);
                border: 1px solid var(--tab-border);
                border-radius: 8px 8px 0 0;
                padding: .55rem .65rem;
                color: var(--text-soft);
                font-family: "IBM Plex Mono", monospace;
                font-size: .68rem;
            }}

            .graph-legend {{
                display:flex;
                align-items:center;
                flex-wrap:wrap;
                gap:.45rem .9rem;
                color:var(--text-soft);
                font-family:"IBM Plex Mono", monospace;
                font-size:.64rem;
                padding:.48rem .65rem;
                background:var(--paper);
                border-left:1px solid var(--border);
                border-right:1px solid var(--border);
            }}

            .legend-item {{ display:inline-flex; align-items:center; gap:.32rem; }}
            .legend-dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; }}
            .legend-diamond {{ width:8px; height:8px; transform:rotate(45deg); display:inline-block; }}

            .gradient-legend {{
                height: 10px;
                border-radius: 2px;
                background: linear-gradient(90deg, var(--negative) 0%, var(--neutral) 50%, var(--positive) 100%);
                border: 1px solid var(--border);
                margin: .3rem 0;
            }}

            .legend-labels {{
                display:flex;
                justify-content:space-between;
                color:var(--text-soft);
                font-family:"IBM Plex Mono", monospace;
                font-size:.62rem;
            }}

            /* ---------- Streamlit controls ---------- */
            div[data-testid="stVerticalBlockBorderWrapper"] {{
                background: var(--paper);
                border-color: var(--border) !important;
                border-radius: 8px !important;
                box-shadow: 0 1px 3px rgba(61,64,91,.04);
                overflow: visible !important;
                box-sizing: border-box;
            }}

            /* Streamlit changed the default padding of bordered containers across
               releases. Own it here so all three pages line up consistently. */
            div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {{
                padding: 1rem 1.05rem 1.05rem 1.05rem !important;
                gap: .72rem !important;
                box-sizing: border-box;
            }}

            /* Some releases insert one anonymous wrapper before stVerticalBlock. */
            div[data-testid="stVerticalBlockBorderWrapper"] > div:not([data-testid]) > div[data-testid="stVerticalBlock"] {{
                padding: 1rem 1.05rem 1.05rem 1.05rem !important;
                gap: .72rem !important;
                box-sizing: border-box;
            }}

            /* Avoid accidental double vertical margins at the card boundaries. */
            div[data-testid="stVerticalBlockBorderWrapper"] h1,
            div[data-testid="stVerticalBlockBorderWrapper"] h2,
            div[data-testid="stVerticalBlockBorderWrapper"] h3,
            div[data-testid="stVerticalBlockBorderWrapper"] p {{
                max-width: 100%;
            }}

            div[data-testid="stFileUploader"] {{
                background: var(--paper);
                border-radius: 8px;
            }}

            div[data-testid="stFileUploaderDropzone"] {{
                border: 1.5px dashed var(--border-strong);
                border-radius: 6px;
                background: var(--surface-low);
            }}

            div[data-testid="stFileUploaderDropzone"]:hover {{
                border-color: var(--terracotta);
                background: var(--upload-hover);
            }}

            .stButton > button,
            .stDownloadButton > button,
            div[data-testid="stFileUploader"] button {{
                border-radius: 6px !important;
                border: 1px solid var(--border-strong) !important;
                background: var(--paper) !important;
                color: var(--text) !important;
                font-weight: 600 !important;
                box-shadow: 0 1px 3px rgba(61,64,91,.04) !important;
                min-height: 2.35rem;
            }}

            /* Button labels are nested elements in recent Streamlit versions.
               Apply text colour to text descendants, but do NOT force `fill` on
               every uploader child: Streamlit's + / × controls use icon markup
               whose paths can become a solid blob if every SVG path is filled. */
            .stButton > button *,
            .stDownloadButton > button * {{
                color: inherit !important;
                fill: currentColor !important;
            }}

            div[data-testid="stFileUploader"] button p,
            div[data-testid="stFileUploader"] button span {{
                color: inherit !important;
            }}

            div[data-testid="stFileUploader"] button svg {{
                color: currentColor !important;
                opacity: 1 !important;
            }}

            /* File-row remove control. The selector list intentionally covers
               several Streamlit releases; unknown selectors are simply ignored. */
            [data-testid="stFileUploaderDeleteBtn"],
            div[data-testid="stFileUploader"] button[aria-label*="Remove"],
            div[data-testid="stFileUploader"] button[aria-label*="Delete"],
            div[data-testid="stFileUploader"] button[title*="Remove"],
            div[data-testid="stFileUploader"] button[title*="Delete"] {{
                width: 2rem !important;
                min-width: 2rem !important;
                height: 2rem !important;
                min-height: 2rem !important;
                padding: .28rem !important;
                border: 0 !important;
                border-radius: 5px !important;
                background: transparent !important;
                color: var(--text-soft) !important;
                box-shadow: none !important;
                opacity: 1 !important;
            }}

            [data-testid="stFileUploaderDeleteBtn"]:hover,
            div[data-testid="stFileUploader"] button[aria-label*="Remove"]:hover,
            div[data-testid="stFileUploader"] button[aria-label*="Delete"]:hover,
            div[data-testid="stFileUploader"] button[title*="Remove"]:hover,
            div[data-testid="stFileUploader"] button[title*="Delete"]:hover {{
                background: var(--surface-low) !important;
                color: var(--error) !important;
                border: 0 !important;
            }}

            [data-testid="stFileUploaderDeleteBtn"] svg,
            div[data-testid="stFileUploader"] button[aria-label*="Remove"] svg,
            div[data-testid="stFileUploader"] button[aria-label*="Delete"] svg,
            div[data-testid="stFileUploader"] button[title*="Remove"] svg,
            div[data-testid="stFileUploader"] button[title*="Delete"] svg {{
                width: 1rem !important;
                height: 1rem !important;
                display: block !important;
                overflow: visible !important;
                fill: none !important;
                stroke: currentColor !important;
                stroke-width: 1.8 !important;
            }}

            [data-testid="stFileUploaderDeleteBtn"] [data-testid="stIconMaterial"],
            div[data-testid="stFileUploader"] button[aria-label*="Remove"] [data-testid="stIconMaterial"],
            div[data-testid="stFileUploader"] button[aria-label*="Delete"] [data-testid="stIconMaterial"] {{
                color: currentColor !important;
                font-size: 1.05rem !important;
                line-height: 1 !important;
                opacity: 1 !important;
            }}

            .stButton > button[kind="primary"] {{
                background: var(--terracotta-dark) !important;
                border-color: var(--terracotta-dark) !important;
                color: #FFFFFF !important;
            }}

            .stButton > button[kind="primary"] * {{
                color: #FFFFFF !important;
                fill: #FFFFFF !important;
            }}

            .stButton > button:hover:not(:disabled),
            .stDownloadButton > button:hover:not(:disabled),
            div[data-testid="stFileUploader"] button:hover:not(:disabled) {{
                border-color: var(--terracotta) !important;
                color: var(--terracotta-dark) !important;
            }}

            .stButton > button[kind="primary"]:hover:not(:disabled) {{
                color: #FFFFFF !important;
                background: #873A27 !important;
            }}

            .stButton > button[kind="primary"]:hover:not(:disabled) * {{
                color: #FFFFFF !important;
                fill: #FFFFFF !important;
            }}

            /* Keep intentionally disabled skeleton actions readable rather than
               allowing Streamlit's opacity rule to wash their labels away. */
            .stButton > button:disabled,
            .stDownloadButton > button:disabled {{
                opacity: 1 !important;
                background: var(--disabled-bg) !important;
                border-color: var(--border) !important;
                color: var(--disabled-text) !important;
                box-shadow: none !important;
            }}

            .stButton > button:disabled *,
            .stDownloadButton > button:disabled * {{
                color: var(--disabled-text) !important;
                fill: var(--disabled-text) !important;
            }}

            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div,
            .stNumberInput input,
            .stTextInput input {{
                background: var(--well) !important;
                border-color: var(--border) !important;
                border-radius: 6px !important;
                color: var(--text) !important;
            }}

            div[data-baseweb="select"] > div:focus-within,
            div[data-baseweb="input"] > div:focus-within {{
                border-color: var(--terracotta) !important;
                box-shadow: none !important;
            }}

            div[data-testid="stSlider"] [role="slider"] {{
                background: var(--terracotta) !important;
                border: 2px solid white !important;
                box-shadow: 0 1px 3px rgba(0,0,0,.15);
            }}

            .stTabs [data-baseweb="tab-list"] {{
                gap: .18rem;
                background: var(--surface-low);
                border-radius: 6px;
                padding: .22rem;
                border: 1px solid var(--tab-border);
            }}

            .stTabs [data-baseweb="tab"] {{
                height: 36px;
                border-radius: 4px;
                padding: 0 .7rem;
                color: var(--text-soft) !important;
                font-size: .78rem;
                font-weight: 500;
            }}

            .stTabs [data-baseweb="tab"] * {{
                color: inherit !important;
            }}

            .stTabs [aria-selected="true"] {{
                background: var(--paper) !important;
                color: var(--terracotta-dark) !important;
                box-shadow: 0 1px 3px rgba(61,64,91,.06);
            }}

            /* Native widget labels occasionally receive BaseWeb's default gray,
               which can have poor contrast on our recessed wells. */
            [data-testid="stWidgetLabel"] p,
            [data-testid="stWidgetLabel"] span,
            .stRadio label p,
            .stCheckbox label p,
            .stToggle label p {{
                color: var(--text-soft) !important;
            }}

            [data-baseweb="select"] *,
            [data-baseweb="input"] * {{
                color: var(--text) !important;
            }}

            /* Popovers and menus are rendered in a portal outside the widget
               container, so they need explicit theme-aware surfaces. */
            [data-baseweb="popover"],
            [data-baseweb="popover"] > div,
            [role="listbox"],
            [role="menu"] {{
                background: var(--paper) !important;
                color: var(--text) !important;
                border-color: var(--border) !important;
            }}

            [role="option"],
            [role="menuitem"] {{
                color: var(--text) !important;
                background: var(--paper) !important;
            }}

            [role="option"]:hover,
            [role="menuitem"]:hover {{
                background: var(--surface-low) !important;
            }}

            [data-testid="stAlert"] {{
                color: var(--text) !important;
            }}

            /* Make toggles/checkmarks harmonise with the scientific accent. */
            [data-testid="stCheckbox"] svg,
            [data-testid="stToggle"] svg {{
                color: var(--terracotta-dark) !important;
            }}

            div[data-testid="stDataFrame"] {{
                border: 1px solid var(--border);
                border-radius: 8px;
                overflow: hidden;
                background: var(--paper);
            }}

            hr {{ border-color: var(--border) !important; }}

            /* -------------------------------------------------------------
               Persistent desktop rail
               -------------------------------------------------------------
               The custom navigation is the app shell, so on desktop we do not
               allow Streamlit to collapse it. This also prevents the rail from
               disappearing after page navigation when the native header is hidden.
            */
            @media (min-width: 1024px) {{
                /* Keep the scientific control rail permanently visible on desktop.
                   Streamlit remembers a collapsed sidebar across reruns/pages; these
                   rules intentionally override that persisted collapsed geometry. */
                section[data-testid="stSidebar"],
                [data-testid="stSidebar"] {{
                    display: block !important;
                    visibility: visible !important;
                    opacity: 1 !important;
                    transform: translateX(0) !important;
                    left: 0 !important;
                    margin-left: 0 !important;
                    flex: 0 0 20rem !important;
                    width: 20rem !important;
                    min-width: 20rem !important;
                    max-width: 20rem !important;
                    height: 100vh !important;
                    position: sticky !important;
                    top: 0 !important;
                    overflow: hidden !important;
                }}

                section[data-testid="stSidebar"] > div,
                [data-testid="stSidebar"] > div {{
                    visibility: visible !important;
                    opacity: 1 !important;
                    width: 20rem !important;
                    min-width: 20rem !important;
                    max-width: 20rem !important;
                }}

                [data-testid="stSidebarContent"] {{
                    height: 100vh !important;
                    overflow-y: auto !important;
                    overscroll-behavior: contain;
                }}

                /* There is no desktop collapse affordance because the sidebar is
                   part of the application shell rather than an optional drawer. */
                [data-testid="stSidebarCollapseButton"],
                [data-testid="stSidebarCollapsedControl"] {{
                    display: none !important;
                }}
            }}

            /* Small screens */
            @media (max-width: 1023px) {{
                .block-container {{
                    padding-left: 1.25rem !important;
                    padding-right: 1.25rem !important;
                }}
                [data-testid="stSidebar"] {{
                    width: 18rem !important;
                    min-width: 18rem !important;
                    max-width: 18rem !important;
                }}

                [data-testid="stSidebarCollapsedControl"] {{
                    display: flex !important;
                    position: fixed !important;
                    top: .65rem !important;
                    left: .65rem !important;
                }}

                [data-testid="stSidebarCollapsedControl"] button {{
                    background: var(--paper) !important;
                    color: var(--text) !important;
                    border: 1px solid var(--border) !important;
                    border-radius: 6px !important;
                    box-shadow: 0 2px 6px rgba(0,0,0,.12) !important;
                }}

                [data-testid="stSidebarCollapsedControl"] button * {{
                    color: inherit !important;
                    fill: currentColor !important;
                }}

                h1 {{
                    font-size: 1.75rem !important;
                    line-height: 2.25rem !important;
                }}
                .topbar-right {{ display:none; }}
            }}

            @media (max-width: 767px) {{
                .block-container {{
                    padding-top: .75rem !important;
                    padding-left: 1rem !important;
                    padding-right: 1rem !important;
                    padding-bottom: 2.5rem !important;
                }}

                div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"],
                div[data-testid="stVerticalBlockBorderWrapper"] > div:not([data-testid]) > div[data-testid="stVerticalBlock"] {{
                    padding: .82rem .82rem .9rem .82rem !important;
                }}

                .topbar {{
                    margin-bottom: .75rem;
                }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

import functools
from pathlib import Path
from typing import List, Dict, Any

from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QColorDialog,
    QColor,
    QIcon,
    QPixmap,
    QLabel,
    Qt,
)

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.utils import showInfo, tooltip

# --- Configuration ---

CONFIG_KEY = "highlight_colors_addon_config_v3"

DEFAULT_CONFIG = {
    "foregroundColors": [
        {"color": "#fef08a"},
        {"color": "#7dd3fc"},
        {"color": "#6ee7b7"},
        {"color": "#ccfbf1"},
        {"color": "#fda4af"},
        {"color": "#d9f99d"},
        {"color": "#d8b4fe"},
    ],
    "backgroundColors": [
        {"color": "#fef08a", "shortcut": "Alt+Y"},
        {"color": "#7dd3fc", "shortcut": "Alt+B"},
        {"color": "#6ee7b7", "shortcut": "Alt+G"},
        {"color": "#ccfbf1", "shortcut": "Ctrl+Shift+T"},
        {"color": "#fda4af", "shortcut": "Alt+R"},
        {"color": "#d9f99d", "shortcut": "Alt+L"},
        {"color": "#d8b4fe", "shortcut": "Alt+P"},
    ],
}


def load_config() -> Dict[str, Any]:
    """Load config from addon manager, falling back to defaults."""
    try:
        addon_config = mw.addonManager.getConfig(__name__)
        if addon_config:
            result = {}
            result["foregroundColors"] = addon_config.get(
                "foregroundColors", DEFAULT_CONFIG["foregroundColors"]
            )
            result["backgroundColors"] = addon_config.get(
                "backgroundColors", DEFAULT_CONFIG["backgroundColors"]
            )
            return result
    except Exception:
        pass
    return DEFAULT_CONFIG


def save_config(config: Dict[str, Any]) -> None:
    """Persist config via addon manager."""
    try:
        current = mw.addonManager.getConfig(__name__) or {}
        current["foregroundColors"] = config.get("foregroundColors", [])
        current["backgroundColors"] = config.get("backgroundColors", [])
        mw.addonManager.writeConfig(__name__, current)
    except Exception:
        pass


# --- Text Color Logic ---


def get_text_color(hex_color: str) -> str:
    """Return 'white' or 'black' based on background luminance."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if luminance < 128:
                return "white"
        except ValueError:
            pass
    return "black"


# --- Apply / Remove Highlight ---

__TOGGLE_HIGHLIGHT_JS_TEMPLATE = (Path(__file__).parent / "highlighter.js").read_text(
    encoding="utf-8"
)


def inject_relative_style_to_buttons(editor: Editor, button_ids: List[str]) -> None:
    """Inject CSS so the absolutely-positioned label spans render correctly."""
    if not button_ids:
        return

    first_id = button_ids[0]
    selectors = ", ".join([f"#{bid}" for bid in button_ids])

    custom_css = f"""
    #{first_id} {{
        margin-left: 4px;
    }}
    {selectors} {{
        position: relative;
        overflow: hidden;
    }}
    """
    js = f"""
    (function() {{
        var style = document.createElement('style');
        style.innerHTML = `{custom_css}`;
        document.head.appendChild(style);
    }})();
    """
    editor.web.eval(js)


def build_highlighter_js(color: str, text_color: str, is_foreground: bool) -> str:
    return (
        __TOGGLE_HIGHLIGHT_JS_TEMPLATE.replace("__COLOR__", color)
        .replace("__TEXT_COLOR__", text_color)
        .replace("__FOREGROUND__", str(is_foreground))
    )


def set_highlight(
    editor: Editor, color: str, text_color: str, is_foreground: bool
) -> None:
    js = build_highlighter_js(color, text_color, is_foreground)
    editor.web.eval(js)


def create_button_label(
    text: str, bg: str, text_color: str, weight: str, is_foreground: bool
) -> str:
    """
    Background mode: colored swatch with contrasting text.
    Foreground mode: white/light swatch with the color applied to the text.
    """
    if not is_foreground:
        return (
            "<span style='background-color:{bg};color:{fg};font-weight:{w};"
            "display:flex;justify-content:center;align-items:center;"
            "position:absolute;inset:0;'>{t}</span>"
        ).format(bg=bg, fg=text_color, w=weight, t=text)
    else:
        return (
            "<span style='background-color:transparent;color:{color};font-weight:bold;"
            "display:flex;justify-content:center;align-items:center;"
            "position:absolute;inset:0;'>{t}</span>"
        ).format(color=bg, t=text)


# --- Config Dialog ---


class ColorListWidget(QListWidget):
    """A QListWidget that displays a list of color dicts."""

    def populate(self, colors: List[Dict[str, Any]], show_shortcut: bool = True) -> None:
        self.clear()
        for d in colors:
            c = d["color"]
            shortcut = d.get("shortcut", "") if show_shortcut else ""
            label = "{}  —  {}".format(c, shortcut) if shortcut else c
            item = QListWidgetItem(label)
            px = QPixmap(16, 16)
            px.fill(QColor(c))
            item.setIcon(QIcon(px))
            self.addItem(item)


class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Highlight Colors")
        self.setMinimumWidth(420)
        self.setModal(True)

        config = load_config()
        self.fg_colors: List[Dict[str, Any]] = list(config.get("foregroundColors", []))
        self.bg_colors: List[Dict[str, Any]] = list(config.get("backgroundColors", []))

        layout = QVBoxLayout(self)

        # --- Background colors section ---
        layout.addWidget(QLabel("<b>Background / Highlight Colors</b> (with optional shortcuts)"))
        self.bg_list = ColorListWidget()
        self.bg_list.populate(self.bg_colors, show_shortcut=True)
        layout.addWidget(self.bg_list)

        bg_btn_row = QHBoxLayout()
        add_bg_btn = QPushButton("Add")
        add_bg_btn.clicked.connect(self.add_bg_color)
        rem_bg_btn = QPushButton("Remove Selected")
        rem_bg_btn.clicked.connect(lambda: self._remove_selected(self.bg_list, self.bg_colors, True))
        bg_btn_row.addWidget(add_bg_btn)
        bg_btn_row.addWidget(rem_bg_btn)
        bg_btn_row.addStretch()
        layout.addLayout(bg_btn_row)

        # --- Foreground colors section ---
        layout.addWidget(QLabel("<b>Foreground / Text Colors</b>"))
        self.fg_list = ColorListWidget()
        self.fg_list.populate(self.fg_colors, show_shortcut=True)
        layout.addWidget(self.fg_list)

        fg_btn_row = QHBoxLayout()
        add_fg_btn = QPushButton("Add")
        add_fg_btn.clicked.connect(self.add_fg_color)
        rem_fg_btn = QPushButton("Remove Selected")
        rem_fg_btn.clicked.connect(lambda: self._remove_selected(self.fg_list, self.fg_colors, True))
        fg_btn_row.addWidget(add_fg_btn)
        fg_btn_row.addWidget(rem_fg_btn)
        fg_btn_row.addStretch()
        layout.addLayout(fg_btn_row)

        # --- Save / Cancel ---
        ok_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addStretch()
        ok_row.addWidget(ok_btn)
        ok_row.addWidget(cancel_btn)
        layout.addLayout(ok_row)

    # -- helpers --

    def add_bg_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.bg_colors.append({"color": color.name(), "shortcut": ""})
            self.bg_list.populate(self.bg_colors, show_shortcut=True)

    def add_fg_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.fg_colors.append({"color": color.name(), "shortcut": ""})
            self.fg_list.populate(self.fg_colors, show_shortcut=True)

    def _remove_selected(
        self,
        list_widget: ColorListWidget,
        color_list: List[Dict[str, Any]],
        show_shortcut: bool,
    ) -> None:
        row = list_widget.currentRow()
        if row >= 0:
            color_list.pop(row)
            list_widget.populate(color_list, show_shortcut=show_shortcut)
        else:
            tooltip("Select a color to remove.", parent=self)

    def accept(self) -> None:
        save_config({"foregroundColors": self.fg_colors, "backgroundColors": self.bg_colors})
        tooltip("Colors saved!", parent=self)
        super().accept()


def open_config_dialog(editor: Editor) -> None:
    dialog = ConfigDialog(editor.parentWindow)
    if dialog.exec():
        if hasattr(editor, "load_buttons"):
            editor.load_buttons()
        else:
            showInfo("Colors saved. Close and reopen the editor to see changes.")


# --- Editor Buttons ---


def add_buttons(buttons: List[str], editor: Editor) -> List[str]:
    config = load_config()
    bg_colors: List[Dict[str, Any]] = config.get("backgroundColors", [])
    fg_colors: List[Dict[str, Any]] = config.get("foregroundColors", [])

    button_ids: List[str] = []

    # 1. Background / highlight color buttons
    for i, data in enumerate(bg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        text_color = get_text_color(color)
        cmd_id = "bg_highlight_{}".format(i)

        tip = "Highlight with {}".format(color)
        if shortcut:
            tip += " ({})".format(shortcut)

        label = create_button_label("A", color, text_color, "normal", is_foreground=False)

        buttons.append(
            editor.addButton(
                icon=None,
                cmd=cmd_id,
                id=cmd_id,
                func=functools.partial(
                    set_highlight,
                    color=color,
                    text_color=text_color,
                    is_foreground=False,
                ),
                tip=tip,
                label=label,
                keys=shortcut,
            )
        )
        button_ids.append(cmd_id)

    # 2. Foreground / text color buttons
    for i, data in enumerate(fg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        cmd_id = "fg_highlight_{}".format(i)

        tip = "Set text color to {}".format(color)
        if shortcut:
            tip += " ({})".format(shortcut)

        label = create_button_label("A", color, color, "bold", is_foreground=True)

        buttons.append(
            editor.addButton(
                icon=None,
                cmd=cmd_id,
                id=cmd_id,
                func=functools.partial(
                    set_highlight,
                    color=color,
                    text_color=color,
                    is_foreground=True,
                ),
                tip=tip,
                label=label,
                keys=shortcut,
            )
        )
        button_ids.append(cmd_id)

    # Inject CSS for all color buttons
    inject_relative_style_to_buttons(editor, button_ids)

    # 3. Config / gear button
    buttons.append(
        editor.addButton(
            icon=None,
            cmd="highlight_config",
            func=open_config_dialog,
            tip="Manage highlight colors (Ctrl+Shift+H)",
            label="⚙️",
            keys="Ctrl+Shift+H",
        )
    )

    return buttons


# --- Hooks ---


def on_config_saved(new_config: dict, addon: str) -> None:
    if addon != __name__:
        return

    for key in ("backgroundColors", "foregroundColors"):
        raw = new_config.get(key, [])
        fixed = []
        for entry in raw:
            if isinstance(entry, dict) and "color" in entry:
                fixed.append({
                    "color": entry["color"],
                    "shortcut": entry.get("shortcut", ""),
                })
        new_config[key] = fixed


gui_hooks.editor_did_init_buttons.append(add_buttons)

try:
    gui_hooks.addon_config_editor_will_save_json.append(on_config_saved)
except AttributeError:
    pass
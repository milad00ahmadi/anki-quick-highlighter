import functools
import json
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
from aqt.utils import tooltip

# --- Configuration ---

DEFAULT_CONFIG = {
    "foregroundColors": [
        {"color": "#fef08a", "shortcut": ""},
        {"color": "#7dd3fc", "shortcut": ""},
        {"color": "#6ee7b7", "shortcut": ""},
        {"color": "#ccfbf1", "shortcut": ""},
        {"color": "#fda4af", "shortcut": ""},
        {"color": "#d9f99d", "shortcut": ""},
        {"color": "#d8b4fe", "shortcut": ""},
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
    try:
        addon_config = mw.addonManager.getConfig(__name__)
        if addon_config:
            return {
                "foregroundColors": addon_config.get(
                    "foregroundColors", DEFAULT_CONFIG["foregroundColors"]
                ),
                "backgroundColors": addon_config.get(
                    "backgroundColors", DEFAULT_CONFIG["backgroundColors"]
                ),
            }
    except Exception:
        pass
    return DEFAULT_CONFIG


def save_config(config: Dict[str, Any]) -> None:
    try:
        current = mw.addonManager.getConfig(__name__) or {}
        current["foregroundColors"] = config.get("foregroundColors", [])
        current["backgroundColors"] = config.get("backgroundColors", [])
        mw.addonManager.writeConfig(__name__, current)
    except Exception:
        pass


# --- Text Color Logic ---


def get_text_color(hex_color: str) -> str:
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


# --- Highlighter JS ---

__TOGGLE_HIGHLIGHT_JS_TEMPLATE = (Path(__file__).parent / "highlighter.js").read_text(
    encoding="utf-8"
)


def build_highlighter_js(color: str, text_color: str, is_foreground: bool) -> str:
    return (
        __TOGGLE_HIGHLIGHT_JS_TEMPLATE.replace("__COLOR__", color)
        .replace("__TEXT_COLOR__", text_color)
        .replace("__FOREGROUND__", str(is_foreground))
    )


def set_highlight(
    editor: Editor, color: str, text_color: str, is_foreground: bool
) -> None:
    editor.web.eval(build_highlighter_js(color, text_color, is_foreground))


# --- Button HTML helpers ---


def create_button_label(
    text: str, bg: str, text_color: str, is_foreground: bool
) -> str:
    if not is_foreground:
        return (
            "<span style='background-color:{bg};color:{fg};font-weight:normal;"
            "display:flex;justify-content:center;align-items:center;"
            "position:absolute;inset:0;'>{t}</span>"
        ).format(bg=bg, fg=text_color, t=text)
    else:
        return (
            "<span style='background-color:transparent;color:{color};font-weight:bold;"
            "display:flex;justify-content:center;align-items:center;"
            "position:absolute;inset:0;'>{t}</span>"
        ).format(color=bg, t=text)


def _button_html(cmd_id: str, tip: str, label: str) -> str:
    safe_tip = tip.replace("'", "&#39;")
    return (
        "<button tabindex='-1'"
        " title='" + safe_tip + "'"
        " onclick=\"pycmd('" + cmd_id + "');\""
        " id='" + cmd_id + "'>" + label + "</button>"
    )


# --- Live toolbar rebuild ---


def _build_inject_css_js(bg_ids: List[str], fg_ids: List[str]) -> str:
    all_ids = bg_ids + fg_ids
    if not all_ids:
        return ""

    css_lines = [
        ", ".join(["#" + bid for bid in all_ids])
        + " { position: relative; overflow: hidden; }",
    ]
    if bg_ids:
        css_lines.append("#" + bg_ids[0] + " { margin-left: 4px; }")
    if fg_ids:
        css_lines.append("#" + fg_ids[0] + " { margin-left: 2px; }")
    css_lines += [
        ".highlight-group-divider {",
        "  display: inline-block; width: 1px; height: 16px;",
        "  background: currentColor; opacity: 0.25;",
        "  margin: 0 3px; vertical-align: middle;",
        "  align-self: center; flex-shrink: 0;",
        "}",
    ]
    css_text = "\n".join(css_lines)

    divider_js = ""
    if fg_ids:
        fgid_json = json.dumps(fg_ids[0])
        divider_js = (
            "var fgBtn = document.getElementById(" + fgid_json + ");"
            "if (fgBtn && fgBtn.parentNode"
            " && !fgBtn.parentNode.querySelector('.highlight-group-divider')) {"
            "  var divEl = document.createElement('span');"
            "  divEl.className = 'highlight-group-divider';"
            "  fgBtn.parentNode.insertBefore(divEl, fgBtn);"
            "}"
        )

    return (
        "(function() {"
        "  var prev = document.getElementById('highlight-addon-style');"
        "  if (prev) prev.remove();"
        "  var s = document.createElement('style');"
        "  s.id = 'highlight-addon-style';"
        "  s.textContent = " + json.dumps(css_text) + ";"
        "  document.head.appendChild(s);" + divider_js + "})();"
    )


def _build_swap_js(new_html: str) -> str:
    selector = '[id^="bg_highlight_"], [id^="fg_highlight_"], .highlight-group-divider'
    return (
        "(function() {"
        "  document.querySelectorAll(" + json.dumps(selector) + ")"
        "    .forEach(function(el) { el.remove(); });"
        "  var gear = document.getElementById('highlight_config');"
        "  if (!gear) return;"
        "  var tmp = document.createElement('div');"
        "  tmp.innerHTML = " + json.dumps(new_html) + ";"
        "  while (tmp.firstChild) {"
        "    gear.parentNode.insertBefore(tmp.firstChild, gear);"
        "  }"
        "})();"
    )


def rebuild_toolbar(editor: Editor) -> None:
    config = load_config()
    bg_colors = config.get("backgroundColors", [])
    fg_colors = config.get("foregroundColors", [])
    bg_ids = ["bg_highlight_{}".format(i) for i in range(len(bg_colors))]
    fg_ids = ["fg_highlight_{}".format(i) for i in range(len(fg_colors))]

    for i, data in enumerate(bg_colors):
        color = data["color"]
        text_color = get_text_color(color)
        editor._links[bg_ids[i]] = functools.partial(
            set_highlight, color=color, text_color=text_color, is_foreground=False
        )
    for i, data in enumerate(fg_colors):
        color = data["color"]
        editor._links[fg_ids[i]] = functools.partial(
            set_highlight, color=color, text_color=color, is_foreground=True
        )

    html_parts: List[str] = []
    for i, data in enumerate(bg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        text_color = get_text_color(color)
        tip = "Highlight with " + color + (" (" + shortcut + ")" if shortcut else "")
        html_parts.append(
            _button_html(
                bg_ids[i], tip, create_button_label("A", color, text_color, False)
            )
        )

    for i, data in enumerate(fg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        tip = "Set text color to " + color + (" (" + shortcut + ")" if shortcut else "")
        html_parts.append(
            _button_html(fg_ids[i], tip, create_button_label("A", color, color, True))
        )

    editor.web.eval(_build_swap_js("".join(html_parts)))
    editor.web.eval(
        "console.log(" + json.dumps(_build_swap_js("".join(html_parts))) + ")"
    )
    editor.web.eval(_build_inject_css_js(bg_ids, fg_ids))
    editor.set_note(editor.note)


# --- Config Dialog ---


class ColorListWidget(QListWidget):
    def populate(self, colors: List[Dict[str, Any]]) -> None:
        self.clear()
        for d in colors:
            c = d["color"]
            shortcut = d.get("shortcut", "")
            label = "{}  —  {}".format(c, shortcut) if shortcut else c
            item = QListWidgetItem(label)
            px = QPixmap(16, 16)
            px.fill(QColor(c))
            item.setIcon(QIcon(px))
            self.addItem(item)


class ConfigDialog(QDialog):
    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle("Manage Highlight Colors")
        self.setMinimumWidth(420)
        self.setModal(True)

        config = load_config()
        self.fg_colors: List[Dict[str, Any]] = list(config.get("foregroundColors", []))
        self.bg_colors: List[Dict[str, Any]] = list(config.get("backgroundColors", []))

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel("<b>Background / Highlight Colors</b> (with optional shortcuts)")
        )
        self.bg_list = ColorListWidget()
        self.bg_list.populate(self.bg_colors)
        layout.addWidget(self.bg_list)

        bg_btn_row = QHBoxLayout()
        add_bg_btn = QPushButton("Add")
        add_bg_btn.clicked.connect(self.add_bg_color)
        rem_bg_btn = QPushButton("Remove Selected")
        rem_bg_btn.clicked.connect(lambda: self._remove(self.bg_list, self.bg_colors))
        bg_btn_row.addWidget(add_bg_btn)
        bg_btn_row.addWidget(rem_bg_btn)
        bg_btn_row.addStretch()
        layout.addLayout(bg_btn_row)

        layout.addWidget(
            QLabel("<b>Foreground / Text Colors</b> (with optional shortcuts)")
        )
        self.fg_list = ColorListWidget()
        self.fg_list.populate(self.fg_colors)
        layout.addWidget(self.fg_list)

        fg_btn_row = QHBoxLayout()
        add_fg_btn = QPushButton("Add")
        add_fg_btn.clicked.connect(self.add_fg_color)
        rem_fg_btn = QPushButton("Remove Selected")
        rem_fg_btn.clicked.connect(lambda: self._remove(self.fg_list, self.fg_colors))
        fg_btn_row.addWidget(add_fg_btn)
        fg_btn_row.addWidget(rem_fg_btn)
        fg_btn_row.addStretch()
        layout.addLayout(fg_btn_row)

        ok_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addStretch()
        ok_row.addWidget(ok_btn)
        ok_row.addWidget(cancel_btn)
        layout.addLayout(ok_row)

    def add_bg_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.bg_colors.append({"color": color.name(), "shortcut": ""})
            self.bg_list.populate(self.bg_colors)

    def add_fg_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.fg_colors.append({"color": color.name(), "shortcut": ""})
            self.fg_list.populate(self.fg_colors)

    def _remove(
        self, list_widget: ColorListWidget, color_list: List[Dict[str, Any]]
    ) -> None:
        row = list_widget.currentRow()
        if row >= 0:
            color_list.pop(row)
            list_widget.populate(color_list)
        else:
            tooltip("Select a color to remove.", parent=self)

    def accept(self) -> None:
        save_config(
            {"foregroundColors": self.fg_colors, "backgroundColors": self.bg_colors}
        )
        tooltip("Colors saved! Reopen the editor to see changes.", parent=self)
        super().accept()


def open_config_dialog(editor: Editor) -> None:
    dialog = ConfigDialog(editor, editor.parentWindow)
    dialog.exec()


# --- Editor Buttons (initial load) ---


def add_buttons(buttons: List[str], editor: Editor) -> List[str]:
    config = load_config()
    bg_colors = config.get("backgroundColors", [])
    fg_colors = config.get("foregroundColors", [])

    bg_button_ids: List[str] = []
    fg_button_ids: List[str] = []

    for i, data in enumerate(bg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        text_color = get_text_color(color)
        cmd_id = "bg_highlight_{}".format(i)
        tip = "Highlight with {}{}".format(
            color, " ({})".format(shortcut) if shortcut else ""
        )
        label = create_button_label("A", color, text_color, is_foreground=False)
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
        bg_button_ids.append(cmd_id)

    for i, data in enumerate(fg_colors):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        cmd_id = "fg_highlight_{}".format(i)
        tip = "Set text color to {}{}".format(
            color, " ({})".format(shortcut) if shortcut else ""
        )
        label = create_button_label("A", color, color, is_foreground=True)
        buttons.append(
            editor.addButton(
                icon=None,
                cmd=cmd_id,
                id=cmd_id,
                func=functools.partial(
                    set_highlight, color=color, text_color=color, is_foreground=True
                ),
                tip=tip,
                label=label,
                keys=shortcut,
            )
        )
        fg_button_ids.append(cmd_id)

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

    editor.web.eval(_build_inject_css_js(bg_button_ids, fg_button_ids))

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
                fixed.append(
                    {"color": entry["color"], "shortcut": entry.get("shortcut", "")}
                )
        new_config[key] = fixed


gui_hooks.editor_did_init_buttons.append(add_buttons)

try:
    gui_hooks.addon_config_editor_will_save_json.append(on_config_saved)
except AttributeError:
    pass

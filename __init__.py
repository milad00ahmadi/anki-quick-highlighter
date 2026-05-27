import functools
from typing import List, Dict, Any

from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QColorDialog,
    QColor, QIcon, QPixmap, Qt
)

from aqt import gui_hooks, mw
from aqt.editor import Editor
from aqt.utils import showInfo, tooltip

# --- Configuração ---

CONFIG_KEY = "highlight_colors_addon_config_v2"

DEFAULT_COLORS = [
    {"color": "#fef08a", "shortcut": "Ctrl+Shift+Y"},
    {"color": "#7dd3fc", "shortcut": "Ctrl+Shift+B"},
    {"color": "F#f5d0feF0000", "shortcut": "Ctrl+Shift+F"},
    {"color": "#fda4af", "shortcut": "Ctrl+Shift+R"},
    {"color": "#d9f99d", "shortcut": "Ctrl+Shift+L"},
]

def load_colors() -> List[Dict[str, Any]]:
    try:
        addon_config = mw.addonManager.getConfig(__name__)
        if addon_config and "colors" in addon_config:
            return addon_config["colors"]
    except Exception:
        pass
    if mw.col:
        saved = mw.col.conf.get(CONFIG_KEY, None)
        if saved:
            return saved
    return DEFAULT_COLORS

def save_colors(colors: List[Dict[str, Any]]) -> None:
    try:
        current = mw.addonManager.getConfig(__name__) or {}
        current["colors"] = colors
        mw.addonManager.writeConfig(__name__, current)
    except Exception:
        pass
    if mw.col:
        mw.col.conf.set(CONFIG_KEY, colors)

# --- Lógica de Cor da Letra ---

def get_text_color(hex_color: str) -> str:
    """Calcula a luminosidade da cor para decidir se a letra deve ser branca ou preta."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            # Fórmula padrão de luminância
            luminance = (0.299 * r + 0.587 * g + 0.114 * b)
            if luminance < 128:
                return "white"
        except ValueError:
            pass
    return "black"

# --- Aplicar / Remover destaque ---

TOGGLE_HIGHLIGHT_JS = r"""
(function() {
    var color = '__COLOR__';
    var textColor = '__TEXT_COLOR__';
    var dummyHex = '#010203';
    var dummyRgb = 'rgb(1, 2, 3)';

    function hexToRgbStr(hex) {
        var r = parseInt(hex.slice(1,3), 16);
        var g = parseInt(hex.slice(3,5), 16);
        var b = parseInt(hex.slice(5,7), 16);
        return 'rgb(' + r + ', ' + g + ', ' + b + ')';
    }

    function colorsMatch(cssColor, hex) {
        if (!cssColor) return false;
        var a = cssColor.replace(/\s/g,'').toLowerCase();
        var b1 = hexToRgbStr(hex).replace(/\s/g,'').toLowerCase();
        var b2 = hex.toLowerCase();
        return a === b1 || a === b2;
    }

    function findHighlightSpan(node, hex) {
        var el = (node.nodeType === 3) ? node.parentElement : node;
        while (el) {
            if (el.tagName === 'SPAN' && el.style && el.style.backgroundColor && colorsMatch(el.style.backgroundColor, hex)) {
                return el;
            }
            if (el.tagName === 'ANKI-EDITABLE' || el === document.body) break;
            el = el.parentElement;
        }
        return null;
    }

    function unwrap(el) {
        var parent = el.parentNode;
        while (el.firstChild) parent.insertBefore(el.firstChild, el);
        parent.removeChild(el);
    }

    // Tenta obter seleção do documento principal E de dentro de shadow roots
    var sel = null;
    var active = document.activeElement;
    var root = document;
    if (active && active.shadowRoot) {
        root = active.shadowRoot;
        try { sel = root.getSelection ? root.getSelection() : null; } catch(e) {}
    }
    if (!sel || sel.rangeCount === 0) {
        sel = window.getSelection();
    }
    if (!sel || sel.rangeCount === 0) return;

    var range = sel.getRangeAt(0);
    var startNode = range.startContainer;

    var existing = findHighlightSpan(startNode, color);

    document.execCommand('styleWithCSS', false, true);

    if (existing) {
        // REMOVER
        if (range.collapsed) {
            unwrap(existing);
            sel.removeAllRanges();
        } else {
            document.execCommand('hiliteColor', false, dummyHex);
            
            var els = root.querySelectorAll('*');
            var toClean = [];
            for (var i = 0; i < els.length; i++) {
                if (els[i].style && els[i].style.backgroundColor) {
                    var bg = els[i].style.backgroundColor.replace(/\s/g, '').toLowerCase();
                    if (bg === dummyRgb.replace(/\s/g, '') || bg === dummyHex.toLowerCase()) {
                        toClean.push(els[i]);
                    }
                }
            }
            
            for (var i = 0; i < toClean.length; i++) {
                var el = toClean[i];
                el.style.backgroundColor = '';
                el.style.color = ''; 
                
                if (!el.getAttribute('style') || el.getAttribute('style').trim() === '') {
                    el.removeAttribute('style');
                }
                if (el.tagName === 'SPAN' && el.attributes.length === 0) {
                    unwrap(el);
                }
            }
        }
    } else {
        // APLICAR via execCommand
        if (range.collapsed) return;
        document.execCommand('hiliteColor', false, color);

        // CORREÇÃO PARA O MODO NOTURNO E CORES ESCURAS:
        if (sel.rangeCount > 0) {
            var newRange = sel.getRangeAt(0);
            var container = newRange.commonAncestorContainer;
            if (container.nodeType === 3) container = container.parentElement;
            
            if (container) {
                var spans = container.querySelectorAll ? Array.from(container.querySelectorAll('span')) : [];
                if (container.tagName === 'SPAN') spans.push(container);
                
                for (var i = 0; i < spans.length; i++) {
                    if (spans[i].style && spans[i].style.backgroundColor && colorsMatch(spans[i].style.backgroundColor, color)) {
                        spans[i].style.color = textColor; // Aplica branca ou preta dependendo da cor de fundo
                    }
                }
            }
            
            newRange.collapse(false);
        }
    }
})();
"""

def set_highlight(editor: Editor, color: str, text_color: str) -> None:
    js = TOGGLE_HIGHLIGHT_JS.replace('__COLOR__', color).replace('__TEXT_COLOR__', text_color)
    editor.web.eval(js)

def create_button_label(text: str, bg: str, text_color: str, weight: str) -> str:
    return "<span style='background-color:{};color:{};font-weight:{};'>{}</span>".format(bg, text_color, weight, text)

# --- Diálogo de configuração ---

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar Cores de Destaque")
        self.setModal(True)
        self.colors = load_colors()

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.populate_list()
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Adicionar Cor")
        add_btn.clicked.connect(self.add_color)
        btn_row.addWidget(add_btn)
        rem_btn = QPushButton("Remover Selecionada")
        rem_btn.clicked.connect(self.remove_color)
        btn_row.addWidget(rem_btn)
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_btn = QPushButton("Salvar")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addStretch()
        ok_row.addWidget(ok_btn)
        ok_row.addWidget(cancel_btn)
        layout.addLayout(ok_row)

    def populate_list(self):
        self.list_widget.clear()
        for d in self.colors:
            c = d["color"]
            shortcut = d.get("shortcut", "")
            label = "{}  —  {}".format(c, shortcut) if shortcut else c
            item = QListWidgetItem(label)
            px = QPixmap(16, 16)
            px.fill(QColor(c))
            item.setIcon(QIcon(px))
            self.list_widget.addItem(item)

    def add_color(self):
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.colors.append({"color": color.name(), "shortcut": ""})
            self.populate_list()

    def remove_color(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.colors.pop(row)
            self.populate_list()
        else:
            tooltip("Selecione uma cor para remover.", parent=self)

    def accept(self):
        save_colors(self.colors)
        tooltip("Cores salvas!", parent=self)
        super().accept()

def open_config_dialog(editor: Editor):
    dialog = ConfigDialog(editor.parentWindow)
    if dialog.exec():
        if hasattr(editor, "load_buttons"):
            editor.load_buttons()
        else:
            showInfo("Cores salvas. Feche e reabra o editor para ver as alterações.")

# --- Botões no editor ---

def add_buttons(buttons: List[str], editor: Editor) -> List[str]:
    for i, data in enumerate(load_colors()):
        color = data["color"]
        shortcut = data.get("shortcut", "")
        text_color = get_text_color(color)
        
        tip = "Destacar/Remover destaque com {}".format(color)
        if shortcut:
            tip += " ({})".format(shortcut)
            
        label = create_button_label("H", color, text_color, "bold")

        buttons.append(
            editor.addButton(
                icon=None,
                cmd="text_highlight_{}".format(i),
                func=functools.partial(set_highlight, color=color, text_color=text_color),
                tip=tip,
                label=label,
                keys=shortcut,
            )
        )

    buttons.append(
        editor.addButton(
            icon=None,
            cmd="highlight_config",
            func=open_config_dialog,
            tip="Gerenciar cores de destaque (Ctrl+Shift+H)",
            label="⚙️",
            keys="Ctrl+Shift+H",
        )
    )
    return buttons

# --- Hooks ---

def on_config_saved(new_config: dict, addon: str) -> None:
    if addon != __name__:
        return
    colors = new_config.get("colors", [])
    fixed = []
    for entry in colors:
        if isinstance(entry, dict) and "color" in entry:
            fixed.append({
                "color": entry["color"],
                "shortcut": entry.get("shortcut", ""),
            })
    new_config["colors"] = fixed

gui_hooks.editor_did_init_buttons.append(add_buttons)

try:
    gui_hooks.addon_config_editor_will_save_json.append(on_config_saved)
except AttributeError:
    pass
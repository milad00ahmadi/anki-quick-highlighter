(function() {
    var color = '__COLOR__';
    var textColor = '__TEXT_COLOR__';
    var isForegroundColor = '__FOREGROUND__' === 'True';
    console.log(typeof isForegroundColor)

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
            var prop = isForegroundColor ? el.style.color : el.style.backgroundColor;
            if (el.tagName === 'SPAN' && el.style && prop && colorsMatch(prop, hex)) {
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

    // Try to get the selection from the main document or a shadow root
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
        // REMOVE the color
        if (range.collapsed) {
            unwrap(existing);
            sel.removeAllRanges();
        } else {
            // Apply a dummy color first so we can find and strip the affected spans
            var dummyCmd = isForegroundColor ? 'foreColor' : 'hiliteColor';
            document.execCommand(dummyCmd, false, dummyHex);

            var els = root.querySelectorAll('*');
            var toClean = [];
            for (var i = 0; i < els.length; i++) {
                var prop = isForegroundColor ? els[i].style.color : els[i].style.backgroundColor;
                if (els[i].style && prop) {
                    var val = prop.replace(/\s/g, '').toLowerCase();
                    if (val === dummyRgb.replace(/\s/g, '') || val === dummyHex.toLowerCase()) {
                        toClean.push(els[i]);
                    }
                }
            }

            for (var i = 0; i < toClean.length; i++) {
                var el = toClean[i];
                if (isForegroundColor) {
                    el.style.color = '';
                } else {
                    el.style.backgroundColor = '';
                    el.style.color = '';
                }

                if (!el.getAttribute('style') || el.getAttribute('style').trim() === '') {
                    el.removeAttribute('style');
                }
                if (el.tagName === 'SPAN' && el.attributes.length === 0) {
                    unwrap(el);
                }
            }
        }
    } else {
        // APPLY the color
        if (range.collapsed) return;

        if (isForegroundColor) {
            // Set the text (foreground) color directly
            document.execCommand('foreColor', false, color);
        } else {
            // Set the background highlight color
            document.execCommand('hiliteColor', false, color);

            // Fix for night mode and dark colors: force the correct text color
            // on any spans that just received the background color
            if (sel.rangeCount > 0) {
                var newRange = sel.getRangeAt(0);
                var container = newRange.commonAncestorContainer;
                if (container.nodeType === 3) container = container.parentElement;

                if (container) {
                    var spans = container.querySelectorAll ? Array.from(container.querySelectorAll('span')) : [];
                    if (container.tagName === 'SPAN') spans.push(container);

                    for (var i = 0; i < spans.length; i++) {
                        if (spans[i].style && spans[i].style.backgroundColor && colorsMatch(spans[i].style.backgroundColor, color)) {
                            // Apply white or black text depending on the background color
                            spans[i].style.color = textColor;
                        }
                    }
                }

                newRange.collapse(false);
            }
        }
    }
})();
// THE SCREEN LOCK, the half CSS cannot do. Loaded by css_bundle.html only when the
// session's `screen_lock` is on, so with it off nothing here runs. The class below
// switches on the rules in base.css (COMPONENT: screen lock). See DECISIONS.md.
document.documentElement.classList.add('screen-lock');
(function () {
    function inside(e, selector) { return e.target.closest && e.target.closest(selector); }
    // No right-click menu. Two exceptions, so that nobody is ever stuck:
    // `.selectable` (copy a completion link), and a long-press in a field, which
    // is the only way to paste on a phone. Ctrl+V is the way on a computer. Written
    // as "not a mouse" so that a browser not reporting a pointer leaves fields alone.
    document.addEventListener('contextmenu', function (e) {
        if (inside(e, '.selectable')) return;
        if (e.pointerType !== 'mouse' && inside(e, 'input, textarea')) return;
        e.preventDefault();
    });
    // No dragging. Dragging selected text inside a field stays as it was.
    document.addEventListener('dragstart', function (e) {
        if (!inside(e, 'input, textarea, .selectable')) e.preventDefault();
    });
})();

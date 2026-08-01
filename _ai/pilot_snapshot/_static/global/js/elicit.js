/* Shared behaviour for the bet widget (main/widget_allocation.html). ONE
   implementation, used by BOTH the real task screen
   (main/allocation_screen.html) and the practice demo on the instructions
   page (intro/instructions_text.html), so the two can never drift.

   It wires whichever widgets are present on the page, by the ids the partial
   defines (allocation_pos_pct / fill_pos / fill_zero / pts_pos / pts_zero;
   info_btn / info_panel). Each page renders the partial at most once, so the
   ids are unique per page. This file is behaviour only; it records nothing
   and knows nothing about forms. */
(function () {
    // The bet: one handle splits 100 points; the Growing (pos) region is
    // left-anchored so its right edge (the split) sits under the handle.
    function initAllocation() {
        var slider = document.getElementById('allocation_pos_pct');
        if (!slider) { return; }
        var fillPos = document.getElementById('fill_pos');
        var fillZero = document.getElementById('fill_zero');
        var ptsPos = document.getElementById('pts_pos');
        var ptsZero = document.getElementById('pts_zero');
        function render(v) {
            var pos = parseInt(v, 10);
            if (isNaN(pos)) { pos = 50; }
            var zero = 100 - pos;
            fillPos.style.width = pos + '%';
            fillZero.style.width = zero + '%';
            ptsPos.textContent = pos;
            ptsZero.textContent = zero;
            slider.setAttribute('aria-valuetext',
                zero + ' points on Stable, ' + pos + ' points on Growing');
        }
        slider.addEventListener('input', function () { render(this.value); });
        render(slider.value);
    }

    // The "?" payment info panel on the bet widget.
    function initInfoPanel() {
        var btn = document.getElementById('info_btn');
        var panel = document.getElementById('info_panel');
        if (!btn || !panel) { return; }
        btn.addEventListener('click', function () {
            var open = panel.classList.toggle('open');
            btn.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
    }

    function init() {
        initAllocation();
        initInfoPanel();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    // exposed in case a page wants to re-init after swapping widgets in
    window.initElicitWidgets = init;
})();

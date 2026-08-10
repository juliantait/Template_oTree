//GLOBAL
    // Function to log to console
    function cl(print) {
      console.log(print)
    }

    // COOKIES
      // Function to get the value of a cookie by name
    function getCookie(name) {
      let cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
          let cookie = cookies[i].trim();
          if (cookie.indexOf(name + '=') === 0) {
              return cookie.substring(name.length + 1);
          }
      }
      return null;
    }

    // Function to set a cookie
    function setCookie(name, value, minutes) {
        let expires = "";
        if (minutes) {
            let date = new Date();
            date.setTime(date.getTime() + (minutes * 60 * 1000));
            expires = "; expires=" + date.toUTCString();
        }
        document.cookie = name + "=" + value + expires + "; path=/";
    }

    // Function to get the value of all cookies
    function printCookies() {
        let cookies = document.cookie;
        console.log("Cookies: ", cookies); // Prints cookies in browser console
    }

    // Function to clear all cookies
    function clearAllCookies() {
        // Get all cookies
        const cookies = document.cookie.split(";");

        // Iterate over the cookies and set each one to expire
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i];
            const equalPos = cookie.indexOf("=");
            const name = equalPos > -1 ? cookie.substr(0, equalPos) : cookie;
            // Set the cookie to expire in the past
            document.cookie = name + "=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
        }
    }

    // Helper to set hidden form values
    function setValue(id, val) {
        const el = document.getElementById(id);
        if (el) {
            el.value = val;
        }
    }

    // Paint the shared `.submit-veil` (base.css) over the whole page. Used
    // whenever a script has to TOUCH FORM CONTROLS before submitting — the
    // DEBUG skip-quiz fill, the re-read route-back, and anything similar added
    // later.
    //
    // WHY: the browser keeps the CURRENT page visible for the whole navigation
    // round-trip, so controls set just before submit are on screen for a
    // moment — the participant sees radios flicking to the answers. Painting the
    // veil in the SAME synchronous task as the fill means no intermediate frame
    // is ever rendered: the veil is all that shows.
    //
    // Use `submitFormBehindVeil` below rather than calling this directly.
    function showSubmitVeil(label) {
        if (document.querySelector('.submit-veil')) { return; }
        const veil = document.createElement('div');
        veil.className = 'submit-veil';
        veil.textContent = label || 'One moment…';
        document.body.appendChild(veil);
    }

    // Fill a form and submit it without the participant seeing the controls
    // change. `fill` runs behind the veil, in the same task, then the form is
    // submitted.
    //
    // Pass a form to have it submitted here. Omit it when the caller is already
    // a submit control (an onclick on <input type="submit">, which submits
    // natively straight after the handler) — the veil still goes up first.
    function submitFormBehindVeil(form, fill) {
        showSubmitVeil();
        if (typeof fill === 'function') { fill(); }
        if (form) { form.submit(); }
    }

    // Allow Enter key to activate the primary forward action (Next/Submit).
    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') {
            return;
        }

        const targetTag = (event.target.tagName || '').toLowerCase();
        if (targetTag === 'textarea') {
            return; // keep multiline entry unaffected
        }

        // Prefer explicit next button if present (e.g., instructions flow).
        const nextButton =
            document.getElementById('nextBtn') ||
            document.querySelector('button.next-button:not([disabled])') ||
            document.querySelector('input.next-button[type="submit"]:not([disabled])') ||
            document.querySelector('.next-button:not([disabled])') ||
            document.querySelector('input[type="submit"]:not([disabled])');

        if (nextButton) {
            event.preventDefault();
            nextButton.click();
        }
    });
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
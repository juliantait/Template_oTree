//GLOBAL
        //   SET HIDDEN VALUES
    function setValue(s,val) {
        document.getElementById(s).value = val;
    }

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
    // Function to check if the page was loaded before
    function checkForPastLoad() {
    //   printCookies(); // Call the function to print cookies when page loads // debugging cookies

      let roundCount = ww.roundNumber; // Insert Python round_count value here
      let loadedCookie = getCookie('loaded.'+ roundCount);
      
      if (loadedCookie === '1') {
          // If the cookie is set to 1, show 'loaded' div and hide others
          document.getElementById('loaded').style.display = 'block';
          document.getElementById('content').style.display = 'none';
          refresh = 1;
      } else {
          // If the cookie is not set or is 0, show normal content
          document.getElementById('content').style.display = 'block';
          // Set the cookie to indicate the page has been loaded
          setCookie('loaded.' + roundCount, '1', 5); // Cookie lasts 5 minutes
      }
    }

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
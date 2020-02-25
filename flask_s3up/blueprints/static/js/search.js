//var typingTimer;                //timer identifier
//var doneTypingInterval = 1000;  //time in ms, 5 second for example
document.getElementById('search').addEventListener('keydown', function(e) {
  if (e.key == "Enter") {
    runSearch();
  }
});

//search.addEventListener('keyup', function () {
  //clearTimeout(typingTimer);
  //typingTimer = setTimeout(runSearch, doneTypingInterval);
//});

//search.addEventListener('keydown', function () {
  //clearTimeout(typingTimer);
//});

function runSearch() {
  var search = document.getElementById('search');
  var urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('search') == true) {
    if (urlParams.get('search') != search.value) {
      urlParams.set('search', search.value);
    } else {
      return;
    }
    if (urlParams.get('search') == '') {
      urlParams.delete('search');
    }
  } else {
    urlParams.append('search', search.value);
  }
  location.href = location.pathname + '?' + urlParams.toString();
}

/* ========== CLOSEST POLYFILL ========== */
(function (ElementProto) {
  if (typeof ElementProto.matches !== 'function') {
    ElementProto.matches = ElementProto.msMatchesSelector || ElementProto.mozMatchesSelector || ElementProto.webkitMatchesSelector || function matches(selector) {
      var element = this;
      var elements = (element.document || element.ownerDocument).querySelectorAll(selector);
      var index = 0;

      while (elements[index] && elements[index] !== element) {
        ++index;
      }

      return Boolean(elements[index]);
    };
  }

  if (typeof ElementProto.closest !== 'function') {
    ElementProto.closest = function closest(selector) {
      var element = this;

      while (element && element.nodeType === 1) {
        if (element.matches(selector)) {
          return element;
        }

        element = element.parentNode;
      }

      return null;
    };
  }
})(window.Element.prototype);
/* ==========// CLOSEST POLYFILL ========== */

var FLASK_S3_VIEWER_CORE = (function(){
  var uploadProgress = [];
  var postSigns = [];

  /* ========== URI PARSER ========== */
  function __getUrlParam(name){
    var results = new RegExp('[\?&]' + name + '=([^&#]*)').exec(window.location.href);
    if (results == null){
      return null;
    }
    else {
      return decodeURI(results[1]) || 0;
    }
  }

  function __setUrlParam(key, value) {
    key = encodeURIComponent(key);
    value = encodeURIComponent(value);
    var kvp = [];
    kvp = document.location.search.substr(1).split('&');
    var i=kvp.length; var x; 
    while(i--){
      x = kvp[i].split('=');
      if (x[0]==key){
        if(value == ''){
          delete kvp[i];
        } else{
          x[1] = value;
          kvp[i] = x.join('=');
        }
        break;
      }
    }
    if(i<0) {
      if(value != ''){
        kvp[kvp.length] = [key,value].join('=');
      }
    }
    kvp = kvp.filter(function(x){
      return x != "";
    });

    return kvp.join('&');
  }
  /* ==========// URI PARSER ========== */


  /* ========== UTILS  ========== */
  function __checkBrowser() {
    var userAgent = navigator.userAgent;
    if (userAgent.indexOf("Opera") !== -1) return 'Opera';
    if (userAgent.indexOf("compatible") !== -1 && userAgent.indexOf('MSIE') && !(userAgent.indexOf("Opera") !== -1)) return 'IE';
    if (userAgent.indexOf("Edge") !== -1) return 'Edge';
    if (userAgent.indexOf('Firefox') !== -1) return 'Firefox';
    if (userAgent.indexOf('Safari') !== -1 && userAgent.indexOf('Chrome') === -1) return 'Safari';
    if (!(userAgent.indexOf("Edge") !== -1) && userAgent.indexOf('Chrome') !== -1 && userAgent.indexOf('Safari') !== -1) return 'Chrome';
    if (userAgent.indexOf('Trident') !== -1 && userAgent.indexOf('rv:11.0') !== -1) return 'IE11';
  };

  function __secure_name(text, el) {
    var regex = /([\\\\\\/:*?\"<>|.])/g;
    var result = text.match(regex);
    if (result !== null && result.length > 0) {
      el.value = text.replace(regex, "");
      return false;
    }
    return true;
  }

  function __makeDispatchEvent(eventName){
    var event;
    if(typeof(Event) === 'function') {
      event = new Event(eventName);
    } else {
      event = document.createEvent('HTMLEvents');
      event.initEvent('change', true, true);
    }
    return event;
  }
  /* ==========// UTILS  ========== */

  /* ========== EVENT CONTROLL ========== */
  function preventDefaults (e) {
    e.preventDefault();
    e.stopPropagation();
  }

  function copyToClipboard(txt){
    var tempElem = document.createElement('textarea');
    tempElem.value = txt;
    document.body.appendChild(tempElem);

    tempElem.select();
    tempElem.setSelectionRange(0, 9999);
    document.execCommand("copy");
    document.body.removeChild(tempElem);
  }

  function resetSearching(e, callback) {
    if (e != null) e = e || window.event;
    var search = __setUrlParam('search', '');
    if (typeof callback === 'function') {
      callback(e, search);
    } else {
      document.location.search = search;
    }
  }

  function runSearching(e, callback){
    if (e != null) e = e || window.event;
    var value = document.getElementById('fs3viewer_search').value;
    var search = __setUrlParam('search', value);

    if (typeof callback === 'function') {
      callback(e, redirection);
    } else {
      document.location.search = search;
    }
  }

  function __addRefreshingBadge(count) {
    var el = document.getElementById('fs3viewer_refresh');
    el.value = count + parseInt(el.value);
    el.dispatchEvent(__makeDispatchEvent('change'));

  }

  function readyFileHandling(e, callback){
    if (e != null) e = e || window.event;
    target = document.getElementById('fs3viewer_files');
    if (FLASK_S3_VIEWER_UPLOAD_TYPE == 'presign') __postPresigns(e, target.files, callback);
    else __handleFiles(e, target.files, [], callback);
  }

  function __handleFiles(e, files, presigns, callback) {
    __initializeProgress(files.length);
    if (typeof callback === 'function') {
      callback(e, files, presigns);
    }
  }

  function __initializeProgress(numFiles) {
    uploadProgress = [];
    for(var i = numFiles; i > 0; i--) uploadProgress.push(0);
    var el = document.getElementById('fs3viewer_progress')
    el.value = 0;
    el.dispatchEvent(__makeDispatchEvent('change'));
  }

  function __postPresigns(e, files, callback){
    var url = FLASK_S3_VIEWER_FILES_ENDPOINT + '/presign';
    var prefix = document.getElementById('fs3viewer_prefix');
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    var fileList = [];
    for (var i = 0; i < files.length; i++) {
      fileList.push(files[i]['name']);
    }
    xhr.open('POST', url, true);
    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4) {
        if (xhr.status == 200) {
          postSigns = JSON.parse(xhr.responseText);
        }
        __handleFiles(e, files, postSigns, callback);
      }
    });

    formData.append('file_list',fileList.join(','));
    formData.append('prefix', prefix.value);
    xhr.send(formData);
  }

  function __uploadWithPresign(e, callback){
    var files = document.getElementById('fs3viewer_files');
    Array.prototype.forEach.call(files.files, uploadFile);
    function uploadFile(file, i, arr) {
      var url = postSigns[i]['url'];
      if(url !== undefined) {
        var xhr = new XMLHttpRequest();
        var formData = new FormData();
        xhr.open('POST', url, true);
        //xhr.setRequestHeader('Content-Type', 'multipart/form-data');
        xhr.upload.addEventListener("progress", function(xe) {
          __updateProgress(i, (xe.loaded * 100.0 / xe.total) || 100);
        });

        xhr.addEventListener('readystatechange', function(xe) {
          if (xhr.readyState == 4) {
            if (xhr.status >= 200 && xhr.status < 300) __addRefreshingBadge(1);
            __updateProgress(i, 100);
          }
          if (typeof callback === 'function') {
            callback(e, xhr, file);
          }
        });

        Object.keys(postSigns[i]['fields']).forEach(function(key){
          //console.log(key, postSigns[i]['fields'][key]);
          formData.append(key, postSigns[i]['fields'][key]);
        });
        formData.append('file', file);
        xhr.send(formData);
      } else {
          __updateProgress(i, 100);
      }
    }
  }

  function __upload(e, callback){
    var files = document.getElementById('fs3viewer_files');
    Array.prototype.forEach.call(files.files, uploadFile);
    function uploadFile(file, i, arr) {
      var prefix = document.getElementById('fs3viewer_prefix');
      //console.log('uploadFile', prefix.value, file,i)
      var url = FLASK_S3_VIEWER_FILES_ENDPOINT;
      var xhr = new XMLHttpRequest();
      var formData = new FormData();
      xhr.open('POST', url, true);
      //xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
      xhr.upload.addEventListener("progress", function(xe) {
        __updateProgress(i, (xe.loaded * 100.0 / xe.total) || 100);
      });

      xhr.addEventListener('readystatechange', function(xe) {
        if (xhr.readyState == 4) {
          if (xhr.status == 201) __addRefreshingBadge(1);
          __updateProgress(i, 100);
        }
        if (typeof callback === 'function') {
          callback(e, xhr, file);
        }
      });

      formData.append('files[]', file);
      formData.append('prefix', prefix.value);
      xhr.send(formData);
    }
  }

  function uploadFiles(e, callback){
    if (e != null) {
      e = e || window.event;
      preventDefaults(e);
    }
    if (FLASK_S3_VIEWER_UPLOAD_TYPE == 'default') {
      __upload(e, callback);
    } else if (FLASK_S3_VIEWER_UPLOAD_TYPE == 'presign') {
      __uploadWithPresign(e, callback);
    }
  }

  function __updateProgress(fileNumber, percent) {
    uploadProgress[fileNumber] = percent;
    var total = uploadProgress.reduce(function(tot, curr) {
      return tot + curr;
    }, 0) / uploadProgress.length;
    //console.log('__updateProgress', fileNumber, percent, total);
    var el = document.getElementById('fs3viewer_progress');
    el.value = total;
    el.dispatchEvent(__makeDispatchEvent('change'));
  }

  function makeDir(e, callback) {
    if (e != null){
      e = e || window.event;
      preventDefaults(e);
    }
    preventDefaults(e);
    var prefix = document.getElementById('fs3viewer_prefix');
    var suffix = document.getElementById('fs3viewer_suffix');
    if (__secure_name(suffix.value, suffix) == false){
      alert('Not secure name');
      return false;
    }
    if (suffix.value == ''){
      alert('Folder name is empty.')
      return false;
    }
    // prefix: enocoded
    // suffix: decoded
    var realPrefix = prefix.value + encodeURIComponent(suffix.value);
    var url = FLASK_S3_VIEWER_FILES_ENDPOINT;
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4) {
        if (xhr.status == 201) {
          __addRefreshingBadge(1);
        } else {

        }
        if (typeof callback === 'function') {
          callback(e, xhr, realPrefix);
        }
      }
    });
    formData.append('prefix', realPrefix);
    xhr.send(formData);
  }

  function deleteFile(e, key, callback, el) {
    //key: decoded
    if (e != null){
      e = e || window.event;
      preventDefaults(e);
    }
    var xhr = new XMLHttpRequest();
    xhr.open('DELETE', FLASK_S3_VIEWER_FILES_ENDPOINT + '/' + encodeURIComponent(key), true);
    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4) {
        if (xhr.status == 204) {
          __addRefreshingBadge(1);
        } else {

        }
        if (typeof callback === 'function') {
          callback(e, xhr, key, el);
        }
      }
    });
    xhr.send();
  }
  /* ==========// EVENT CONTROLL ========== */

  return {
    makeDir: makeDir,
    deleteFile: deleteFile,
    copyToClipboard: copyToClipboard,
    uploadFiles: uploadFiles,
    preventDefaults: preventDefaults,
    resetSearching: resetSearching,
    readyFileHandling: readyFileHandling,
    runSearching: runSearching
  }
}());

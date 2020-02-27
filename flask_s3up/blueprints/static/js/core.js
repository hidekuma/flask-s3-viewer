var BROWSER = checkBrowser();

function preventDefaults (e) {
  e.preventDefault();
  e.stopPropagation();
}

function checkBrowser() {
  var userAgent = navigator.userAgent;
  if (userAgent.indexOf("Opera") !== -1) return 'Opera';
  if (userAgent.indexOf("compatible") !== -1 && userAgent.indexOf('MSIE') && !(userAgent.indexOf("Opera") !== -1)) return 'IE';
  if (userAgent.indexOf("Edge") !== -1) return 'Edge';
  if (userAgent.indexOf('Firefox') !== -1) return 'Firefox';
  if (userAgent.indexOf('Safari') !== -1 && userAgent.indexOf('Chrome') === -1) return 'Safari';
  if (!(userAgent.indexOf("Edge") !== -1) && userAgent.indexOf('Chrome') !== -1 && userAgent.indexOf('Safari') !== -1) return 'Chrome';
  if (userAgent.indexOf('Trident') !== -1 && userAgent.indexOf('rv:11.0') !== -1) return 'IE11';
};

function copyToClipboard(id){
  var dummy = document.getElementById(id);
  dummy.select();
  document.execCommand('copy');
}

function resetSearching(e, callback) {
  var urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('search') == true) {
    urlParams.delete('search');
  }
  var redirection = ''
  if (urlParams.toString() != '') {
    redirection = location.pathname + '?' + urlParams.toString();
  } else {
    redirection = location.pathname;
  }

  if (typeof callback === 'function') {
    callback(redirection);
  } else {
    location.href = redirection;
  }
}

function runSearching(e, callback) {
  e = e || window.event;
  if (e.key == "Enter") {
    var target = e.target || e.srcElement;
    var value = target.value;
    var urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('search') == true) {
      if (urlParams.get('search') != value) {
        urlParams.set('search', value);
      } else {
        return false;
      }
      if (urlParams.get('search') == '') {
        urlParams.delete('search');
      }
    } else {
      urlParams.append('search', value);
    }
    var redirection = '';
    if (urlParams.toString() != '') {
      redirection = location.pathname + '?' + urlParams.toString();
    } else {
      redirection = location.pathname;
    }
    if (typeof callback === 'function') {
      callback(redirection);
    } else {
      location.href= redirection;
    }
  }
}

function addRefreshingBadge(count) {
  var el = document.getElementById('flask_s3up_refresh');
  el.value = count + parseInt(el.value);
  el.dispatchEvent(new Event('change'));
}

function readyFileHandling(e, callback){
  e = e || window.event;
  var target = e.target || e.srcElement;
  handleFiles(target.files, callback);
}

function handleFiles(files, callback) {
  initializeProgress(files.length);
  //document.getElementById('flask_s3up_gallery').innerHTML = '';
  //Array.prototype.forEach.call(files, previewFile);
  if (typeof callback === 'function') {
    callback(files);
  }
}

var uploadProgress = [];

function initializeProgress(numFiles) {
  uploadProgress = [];
  for(var i = numFiles; i > 0; i--) {
    uploadProgress.push(0);
  }
  var el = document.getElementById('flask_s3up_progress')
  el.value = 0;
  el.dispatchEvent(new Event('change'));
}

function uploadFiles(e, callback){
  preventDefaults(e);
  var files = document.getElementById('flask_s3up_files');
  var results = [];
  Array.prototype.forEach.call(files.files, uploadFile);
  function uploadFile(file, i, arr) {
    var urlParams = new URLSearchParams(window.location.search);
    var prefix = document.getElementById('flask_s3up_prefix');
    //console.log('uploadFile', prefix.value, file,i)
    var url = FLASK_S3UP_FILES_ENDPOINT;
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    xhr.open('POST', url, true);
    //xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.addEventListener("progress", function(e) {
      updateProgress(i, (e.loaded * 100.0 / e.total) || 100);
    });

    xhr.addEventListener('readystatechange', function(e) {
      if (xhr.readyState == 4 && xhr.status == 201) {
        updateProgress(i, 100);
        addRefreshingBadge(1);
      } else if (xhr.readyState == 4 && xhr.status != 201) {
      }
    });

    formData.append('files[]', file);
    formData.append('prefix', prefix.value);
    xhr.send(formData);
    results.push(xhr);
  }
  if (typeof callback === 'function') {
    callback(results, files.files);
  }
}

function updateProgress(fileNumber, percent) {
  uploadProgress[fileNumber] = percent;
  var total = uploadProgress.reduce(function(tot, curr) {
    return tot + curr;
  }, 0) / uploadProgress.length;
  //console.log('updateProgress', fileNumber, percent, total);
  var el = document.getElementById('flask_s3up_progress')
  el.value = total;
  el.dispatchEvent(new Event('change'));
}


function makeDir(e, callback) {
  e = e || window.event;
  preventDefaults(e);
  var prefix = document.getElementById('flask_s3up_prefix');
  var suffix = document.getElementById('flask_s3up_suffix');
  if (suffix.value == ''){
    return false;
  }
  var realPrefix = prefix.value + suffix.value;
  var url = FLASK_S3UP_FILES_ENDPOINT;
  var xhr = new XMLHttpRequest();
  var formData = new FormData();
  xhr.open('POST', url, true);
  xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 201) {
      addRefreshingBadge(1);
    }
    else if (xhr.readyState == 4 && xhr.status != 201) {
    }
  });
  formData.append('prefix', realPrefix);
  xhr.send(formData);
  if (typeof callback === 'function') {
    callback(xhr, realPrefix);
  }
}

function deleteFile(key, callback) {
  var xhr = new XMLHttpRequest();
  xhr.open('DELETE', FLASK_S3UP_FILES_ENDPOINT + '/' + key, true);
  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 204) {
      addRefreshingBadge(1);
    } else if (xhr.readyState == 4 && xhr.status != 204) {
    }
  });
  xhr.send();
  if (typeof callback === 'function') {
    callback(xhr, key);
  }
}

/*
  * DropArea
  * */
//var dropArea = document.getElementById('flask_s3up_drop_area');
//if (BROWSER.indexOf('IE') !== -1) dropArea.style.display = 'none';

//// Prevent default drag behaviors
//['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function(eventName) {
  //dropArea.addEventListener(eventName, preventDefaults, false);
  //document.body.addEventListener(eventName, preventDefaults, false);
//});

//// Highlight drop area when item is dragged over it
//['dragenter', 'dragover'].forEach(function(eventName) {
  //dropArea.addEventListener(eventName, highlight, false);
//});

//['dragleave', 'drop'].forEach(function(eventName) {
  //dropArea.addEventListener(eventName, unhighlight, false);
//});

//// Handle dropped files
//dropArea.addEventListener('drop', handleDrop, false);


//function highlight(e) {
  //dropArea.classList.add('highlight');
//}

//function unhighlight(e) {
  //dropArea.classList.remove('active');
//}

//function handleDrop(e) {
  //var dt = e.dataTransfer;
  //var files = dt.files;
  //document.getElementById('flask_s3up_files').files = files;
  //handleFiles(files);
//}

//function previewFile(file) {
  //var reader = new FileReader();
  //reader.readAsDataURL(file);
  //reader.onloadend = function() {
    //var img = document.createElement('img');
    //img.src = reader.result;
    //document.getElementById('flask_s3up_gallery').appendChild(img);
  //}
//}


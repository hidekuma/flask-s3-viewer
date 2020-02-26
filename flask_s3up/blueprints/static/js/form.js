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

function resetSearching(e) {
  var urlParams = new URLSearchParams(window.location.search);
  if (urlParams.has('search') == true) {
    urlParams.delete('search');
  }
  if (urlParams.toString() != '') {
    location.href = location.pathname + '?' + urlParams.toString();
  } else {
    location.href = location.pathname;
  }
}

function runSearching(e) {
  e = e || window.event;
  if (e.key == "Enter") {
    var target = e.target || e.srcElement;
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
      urlParams.append('search', target.value);
    }
    if (urlParams.toString() != '') {
      location.href = location.pathname + '?' + urlParams.toString();
    } else {
      location.href = location.pathname;
    }
  }
}

function fileHandling(e){
  e = e || window.event;
  var target = e.target || e.srcElement;
  handleFiles(target.files);
}

function uploadFiles(e){
  preventDefaults(e);
  var files = document.getElementById('flask_s3up_files');
  var new_files = Array.from(files.files);
  new_files.forEach(uploadFile);
}

function resetForm(e) {
  e = e || window.event;
  preventDefaults(e);
  document.getElementById('flask_s3up_form').reset();
  document.getElementById('flask_s3up_gallery').innerHTML = '';
}

function makeDir(e) {
  e = e || window.event;
  //var target = e.target || e.srcElement;
  preventDefaults(e);
  var prefix = document.getElementById('flask_s3up_prefix');
  var suffix = document.getElementById('flask_s3up_suffix');
  var url = FILES_ENDPOINT;
  var xhr = new XMLHttpRequest();
  var formData = new FormData();
  xhr.open('POST', url, true);
  xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 200) {
    }
    else if (xhr.readyState == 4 && xhr.status != 200) {
    }
  });
  formData.append('prefix', prefix.value + suffix.value);
  xhr.send(formData);
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

var uploadProgress = [];
var progressBar = document.getElementById('flask_s3up_progress_bar');

function initializeProgress(numFiles) {
  progressBar.value = 0;
  uploadProgress = [];

  for(var i = numFiles; i > 0; i--) {
    uploadProgress.push(0);
  }
}

function updateProgress(fileNumber, percent) {
  uploadProgress[fileNumber] = percent;
  var total = uploadProgress.reduce(function(tot, curr) {
    return tot + curr;
  }, 0) / uploadProgress.length;
  console.debug('updateProgress', fileNumber, percent, total);
  progressBar.value = total;
}


function handleFiles(files) {
  console.log('handleFiles', files);
  files = Array.from(files);
  initializeProgress(files.length);
  //document.getElementById('flask_s3up_gallery').innerHTML = '';
  //files.forEach(previewFile);
}

function previewFile(file) {
  var reader = new FileReader();
  reader.readAsDataURL(file);
  reader.onloadend = function() {
    var img = document.createElement('img');
    img.src = reader.result;
    document.getElementById('flask_s3up_gallery').appendChild(img);
  }
}

function deleteFile(key, id) {
  console.log('deleteFile', key)
  var xhr = new XMLHttpRequest();
  xhr.open('DELETE', FILES_ENDPOINT + '/' + key, true);

  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 204) {
      //document.getElementById(id).remove();
    } else if (xhr.readyState == 4 && xhr.status >= 400) {
      alert('error');
    }
  });
  xhr.send();
}

function uploadFile(file, i) {
  var urlParams = new URLSearchParams(window.location.search);
  var prefix = document.getElementById('flask_s3up_prefix');
  console.log('uploadFile', prefix.value, file,i)
  var url = FILES_ENDPOINT;
  var xhr = new XMLHttpRequest();
  var formData = new FormData();
  xhr.open('POST', url, true);
  //xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  xhr.upload.addEventListener("progress", function(e) {
    console.log('progress', e)
    updateProgress(i, (e.loaded * 100.0 / e.total) || 100);
  })

  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 201) {
      updateProgress(i, 100);
    } else if (xhr.readyState == 4 && xhr.status >= 400) {
      alert('error');
    }
  });

  formData.append('files[]', file)
  formData.append('prefix', prefix.value)
  xhr.send(formData)
}

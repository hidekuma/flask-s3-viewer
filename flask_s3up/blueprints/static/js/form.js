document.getElementById('files').onchange = function(){
  handleFiles(files.files);
}

document.getElementById('submit').onclick = function(e){
  var prefix = document.getElementById('prefix');
  preventDefaults(e);
  var new_files = Array.from(files.files);
  new_files.forEach(uploadFile);
  //location.href = FILES_ENDPOINT + "?prefix=" + encodeURIComponent(prefix.value);
}

document.getElementById('reset_form').onclick = function(e) {
  preventDefaults(e);
  document.getElementById('upload_form').reset();
  document.getElementById('gallery').innerHTML = '';
}

document.getElementById('make_dir').onclick = function(e) {
  preventDefaults(e);
  var prefix = document.getElementById('prefix');
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
  formData.append('prefix', prefix.value)
  xhr.send(formData)
}

/*
  * DropArea
  * */
browser = checkBrowser()
var dropArea = document.getElementById('drop_area');
if (browser.indexOf('IE') !== -1) dropArea.style.display = 'none';

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function(eventName) {
  dropArea.addEventListener(eventName, preventDefaults, false);
  document.body.addEventListener(eventName, preventDefaults, false);
});

// Highlight drop area when item is dragged over it
['dragenter', 'dragover'].forEach(function(eventName) {
  dropArea.addEventListener(eventName, highlight, false);
});

['dragleave', 'drop'].forEach(function(eventName) {
  dropArea.addEventListener(eventName, unhighlight, false);
});

// Handle dropped files
dropArea.addEventListener('drop', handleDrop, false);

function preventDefaults (e) {
  e.preventDefault();
  e.stopPropagation();
}

function highlight(e) {
  dropArea.classList.add('highlight');
}

function unhighlight(e) {
  dropArea.classList.remove('active');
}

function handleDrop(e) {
  var dt = e.dataTransfer;
  var files = dt.files;
  document.getElementById('files').files = files;
  handleFiles(files);
}

var uploadProgress = [];
var progressBar = document.getElementById('progress_bar');

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
  document.getElementById('gallery').innerHTML = '';
  files.forEach(previewFile);
}

function previewFile(file) {
  var reader = new FileReader();
  reader.readAsDataURL(file);
  reader.onloadend = function() {
    var img = document.createElement('img');
    img.src = reader.result;
    document.getElementById('gallery').appendChild(img);
  }
}

function deleteFile(key, id) {
  console.log(key)
  var xhr = new XMLHttpRequest();
  xhr.open('DELETE', FILES_ENDPOINT + '/' + key, true);

  xhr.addEventListener('readystatechange', function(e) {
    if (xhr.readyState == 4 && xhr.status == 204) {
      document.getElementById(id).remove();
    } else if (xhr.readyState == 4 && xhr.status >= 400) {
      alert('error');
    }
  });
  xhr.send();
}
function uploadFile(file, i) {
  console.log('uploadFile', file,i)
  var prefix = document.getElementById('prefix');
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


function copyToClipboard(id){
  var dummy = document.getElementById(id);
  dummy.select();
  document.execCommand('copy');
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


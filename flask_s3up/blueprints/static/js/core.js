var BROWSER = checkBrowser();

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

function getUrlParam(name){
    var results = new RegExp('[\?&]' + name + '=([^&#]*)').exec(window.location.href);
    if (results == null){
       return null;
    }
    else {
       return decodeURI(results[1]) || 0;
    }
}

function setUrlParam(key, value) {
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
  var search = setUrlParam('search', '');
  if (typeof callback === 'function') {
    callback(e, search);
  } else {
    document.location.search = search;
  }
}

function runSearching(e, callback){
    e = e || window.event;
    var target = e.target || e.srcElement;
    var value = target.value;
    var search = setUrlParam('search', value);

    if (typeof callback === 'function') {
      callback(e, redirection);
    } else {
      document.location.search = search;
    }
}

function makeDispatchEvent(eventName){
  var event;
  if(typeof(Event) === 'function') {
      event = new Event(eventName);
  }else{
      event = document.createEvent('HTMLEvents');
      event.initEvent('change', true, true);
  }
  return event;
}

function addRefreshingBadge(count) {
  var el = document.getElementById('flask_s3up_refresh');
  el.value = count + parseInt(el.value);
  el.dispatchEvent(makeDispatchEvent('change'));

}

function readyFileHandling(e, callback){
  e = e || window.event;
  var target = e.target || e.srcElement;
  handleFiles(e, target.files, callback);
}

function handleFiles(e, files, callback) {
  initializeProgress(files.length);
  //document.getElementById('flask_s3up_gallery').innerHTML = '';
  //Array.prototype.forEach.call(files, previewFile);
  if (typeof callback === 'function') {
    callback(e, files);
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
  el.dispatchEvent(makeDispatchEvent('change'));
}

function uploadFiles(e, callback){
  preventDefaults(e);
  var files = document.getElementById('flask_s3up_files');
  Array.prototype.forEach.call(files.files, uploadFile);
  function uploadFile(file, i, arr) {
    var prefix = document.getElementById('flask_s3up_prefix');
    //console.log('uploadFile', prefix.value, file,i)
    var url = FLASK_S3UP_FILES_ENDPOINT;
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    xhr.open('POST', url, true);
    //xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.upload.addEventListener("progress", function(xe) {
      updateProgress(i, (xe.loaded * 100.0 / xe.total) || 100);
    });

    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4 && xhr.status == 201) {
        updateProgress(i, 100);
        addRefreshingBadge(1);
      } else if (xhr.readyState == 4 && xhr.status != 201) {

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

function updateProgress(fileNumber, percent) {
  uploadProgress[fileNumber] = percent;
  var total = uploadProgress.reduce(function(tot, curr) {
    return tot + curr;
  }, 0) / uploadProgress.length;
  //console.log('updateProgress', fileNumber, percent, total);
  var el = document.getElementById('flask_s3up_progress');
  el.value = total;
  el.dispatchEvent(makeDispatchEvent('change'));
}


function secure_name(text, el) {
  var regex = /([\\\\\\/:*?\"<>|.()])/g;
  var result = text.match(regex);
  if (result !== null && result.length > 0) {
    //el.val(text.replace(regex, ""));
    return false;
  }
  return true;
}

function makeDir(e, callback) {
  if (confirm('Are you sure you want to make folder?')){
    e = e || window.event;
    preventDefaults(e);
    var prefix = document.getElementById('flask_s3up_prefix');
    var suffix = document.getElementById('flask_s3up_suffix');
    //if (!secure_name(suffix.value, suffix)){
      //alert('Not secure name');
      //return false;
    //}
    if (suffix.value == ''){
      alert('Folder name is empty.')
      return false;
    }
    // prefix: enocoded
    // suffix: decoded
    var realPrefix = prefix.value + encodeURIComponent(suffix.value);
    var url = FLASK_S3UP_FILES_ENDPOINT;
    var xhr = new XMLHttpRequest();
    var formData = new FormData();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4 && xhr.status == 201) {
        addRefreshingBadge(1);
      }
      else if (xhr.readyState == 4 && xhr.status != 201) {

      }
      if (typeof callback === 'function') {
        callback(e, xhr, realPrefix);
      }
    });
    formData.append('prefix', realPrefix);
    xhr.send(formData);
  } else {
    e.target.value = '';
  }
}

function deleteFile(e, key, callback) {
  //key: decoded
  if (confirm('Are you sure you want to delete?')){
    e = e || window.event;
    preventDefaults(e);
    var xhr = new XMLHttpRequest();
    xhr.open('DELETE', FLASK_S3UP_FILES_ENDPOINT + '/' + encodeURIComponent(key), true);
    xhr.addEventListener('readystatechange', function(xe) {
      if (xhr.readyState == 4 && xhr.status == 204) {
        addRefreshingBadge(1);
      } else if (xhr.readyState == 4 && xhr.status != 204) {

      }
      if (typeof callback === 'function') {
        callback(e, xhr, key);
      }
    });
    xhr.send();
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

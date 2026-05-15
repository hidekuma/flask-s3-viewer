/*!
 * flask.s3viewer.core.js — slim presign-only client (v1.0+).
 *
 * HTMX handles default uploads, navigation, search, pagination, and delete
 * in the new UI. This module is loaded ONLY when ``upload_type='presign'``
 * and owns the multi-file presigned-POST → S3 fan-out plus its progress UI.
 *
 * Public surface (``window.FLASK_S3_VIEWER_CORE``):
 *   - readyFileHandling(event, cb)   file input ``onchange`` entry point
 *   - uploadFiles(event, cb)         chip "Upload" click entry point
 *   - preventDefaults(event)         form reset / cancel helper
 *
 * Required DOM ids (kept in sync with the presign branch of
 * ``_upload_form.html`` — and pinned by ``tests/test_presign.py``):
 *   - ``upload_form``        the multipart <form>
 *   - ``fs3viewer_files``    the <input type=file>
 *   - ``fs3viewer_prefix``   hidden input carrying the upload prefix
 *   - ``fs3viewer_progress`` hidden 0..100 int; its ``onchange`` drives the bar
 *   - ``file_chip``          chip with file_count + Upload + Cancel
 *   - ``file_count``         selected file count text
 *   - ``floading``           spinner shown while uploading
 *
 * Public globals consumed (defined in layout.html):
 *   - ``FLASK_S3_VIEWER_FILES_ENDPOINT``
 *   - ``FLASK_S3_VIEWER_UPLOAD_TYPE`` (``'presign'`` here)
 */
var FLASK_S3_VIEWER_CORE = (function () {
  'use strict';

  var presigns = [];
  var pending = 0;
  var done = 0;
  var totalBytes = 0;
  var loadedBytes = 0;
  var progressCallback = null;

  function preventDefaults(e) {
    if (e && e.preventDefault) e.preventDefault();
    if (e && e.stopPropagation) e.stopPropagation();
  }

  function setProgress(pct) {
    var el = document.getElementById('fs3viewer_progress');
    if (!el) return;
    var v = String(Math.round(pct));
    if (v === el.value) return;
    el.value = v;
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function fetchPresigns(files, cb, overwrite) {
    var url = FLASK_S3_VIEWER_FILES_ENDPOINT + '/presign';
    var prefix = document.getElementById('fs3viewer_prefix');
    var fd = new FormData();
    fd.append('prefix', prefix ? prefix.value : '');
    fd.append('file_list', files.map(function (f) { return f.name; }).join(','));
    if (overwrite) fd.append('overwrite', '1');
    var xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('HX-Request', 'true');
    xhr.onload = function () {
      var slots = [];
      try { slots = JSON.parse(xhr.responseText) || []; } catch (e) { /* keep [] */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        cb(slots, null);
        return;
      }
      cb([], {
        status: xhr.status,
        responseText: xhr.responseText,
      });
    };
    xhr.onerror = function () {
      cb([], {
        status: 0,
        responseText: '',
      });
    };
    xhr.send(fd);
  }

  function readyFileHandling(event, cb) {
    var input = event && event.target;
    if (!input || !input.files || !input.files.length) return;
    var files = Array.prototype.slice.call(input.files);
    if (typeof FLASK_S3_VIEWER_UPLOAD_TYPE !== 'undefined' &&
        FLASK_S3_VIEWER_UPLOAD_TYPE === 'presign') {
      fetchPresigns(files, function (slots, error) {
        presigns = slots;
        if (typeof cb === 'function') cb(event, files, slots, error);
      });
    } else if (typeof cb === 'function') {
      cb(event, files, null, null);
    }
  }

  function emitProgress(pct, failures) {
    if (typeof progressCallback === 'function') {
      progressCallback({
        percent: Math.round(pct),
        done: done,
        total: pending,
        failures: failures || [],
      });
    }
    setProgress(pct);
  }

  function putOne(file, slot, done_cb) {
    var fd = new FormData();
    var fields = slot.fields || {};
    Object.keys(fields).forEach(function (k) { fd.append(k, fields[k]); });
    fd.append('file', file);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', slot.url);
    if (xhr.upload) {
      var prev = 0;
      xhr.upload.addEventListener('progress', function (e) {
        if (!e.lengthComputable) return;
        loadedBytes += (e.loaded - prev);
        prev = e.loaded;
        emitProgress(totalBytes ? (loadedBytes / totalBytes) * 100 : 0);
      });
    }
    xhr.onload = function () {
      done_cb(xhr.status >= 200 && xhr.status < 300 ? null : xhr.status);
    };
    xhr.onerror = function () { done_cb(0); };
    xhr.send(fd);
  }

  function putAll(files, slots, cb) {
    pending = 0; done = 0; totalBytes = 0; loadedBytes = 0;
    var failures = [];
    files.forEach(function (file, i) {
      var slot = slots[i] || {};
      if (slot.status_code) {
        failures.push({ name: file.name, status: slot.status_code });
      } else {
        pending += 1;
        totalBytes += file.size;
      }
    });
    if (pending === 0) {
      emitProgress(0, failures);
      if (typeof cb === 'function') cb(null, { failures: failures, ok: 0 });
      return;
    }
    emitProgress(0, failures);
    files.forEach(function (file, i) {
      var slot = slots[i] || {};
      if (slot.status_code) return;
      putOne(file, slot, function (status) {
        done += 1;
        if (status !== null) failures.push({ name: file.name, status: status });
        emitProgress(totalBytes ? (loadedBytes / totalBytes) * 100 : 100, failures);
        if (done === pending) {
          emitProgress(100, failures);
          if (typeof cb === 'function') {
            cb(null, { failures: failures, ok: pending - failures.length });
          }
        }
      });
    });
  }

  function uploadFiles(event, cb) {
    preventDefaults(event);
    var input = document.getElementById('fs3viewer_files');
    if (!input || !input.files || !input.files.length) return;
    var files = Array.prototype.slice.call(input.files);
    if (!presigns.length || presigns.length !== files.length) {
      fetchPresigns(files, function (slots, error) {
        presigns = slots;
        putAll(files, slots, cb);
      });
    } else {
      putAll(files, presigns, cb);
    }
  }

  return {
    readyFileHandling: readyFileHandling,
    uploadFiles: uploadFiles,
    fetchPresigns: fetchPresigns,
    putAll: putAll,
    onProgress: function (cb) { progressCallback = cb; },
    preventDefaults: preventDefaults,
  };
})();

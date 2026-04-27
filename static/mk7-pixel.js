// MK7 Media — unified Meta Pixel + Conversions API tracker.
// Fires browser Pixel and posts a matching event to /api/track for server-side CAPI dedup.
(function () {
  function uuid() {
    return (window.crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : 'ev_' + Date.now() + '_' + Math.random().toString(36).slice(2);
  }
  function cookie(n) {
    var m = document.cookie.match(new RegExp('(?:^|; )' + n + '=([^;]+)'));
    return m ? decodeURIComponent(m[1]) : '';
  }
  var STANDARD = ['Lead', 'InitiateCheckout', 'Contact', 'ViewContent', 'CompleteRegistration', 'Schedule', 'SubmitApplication', 'Purchase', 'AddToCart'];
  var STANDARD_CUSTOM_KEYS = ['value', 'currency', 'content_name', 'content_category', 'content_ids', 'contents', 'content_type', 'order_id', 'predicted_ltv', 'num_items', 'search_string', 'status', 'delivery_category'];
  var fired = {};

  // Coerce reserved Meta keys to valid types; bundle anything else under custom_properties.
  function sanitize(custom) {
    var clean = {};
    var extras = {};
    for (var k in custom) {
      if (!Object.prototype.hasOwnProperty.call(custom, k)) continue;
      var v = custom[k];
      if (v === null || v === undefined || v === '') continue;
      if (STANDARD_CUSTOM_KEYS.indexOf(k) !== -1) {
        if (k === 'value') {
          var n = parseFloat(v);
          if (!isNaN(n)) clean.value = n;
        } else if (k === 'currency') {
          var s = String(v).toUpperCase();
          if (/^[A-Z]{3}$/.test(s)) clean.currency = s;
        } else if (k === 'num_items') {
          var ni = parseInt(v, 10);
          if (!isNaN(ni)) clean.num_items = ni;
        } else if (k === 'content_ids' || k === 'contents') {
          if (Array.isArray(v)) clean[k] = v;
        } else {
          clean[k] = String(v);
        }
      } else {
        extras[k] = v;
      }
    }
    if (Object.keys(extras).length) clean.custom_properties = extras;
    return clean;
  }

  window.mk7Track = function (eventName, custom, opts) {
    custom = custom || {};
    opts = opts || {};

    if (opts.dedupeKey) {
      var key = eventName + '|' + opts.dedupeKey;
      if (fired[key]) return;
      fired[key] = true;
    }

    var eventId = uuid();
    var cleaned = sanitize(custom);

    if (window.fbq) {
      if (STANDARD.indexOf(eventName) !== -1) {
        fbq('track', eventName, cleaned, { eventID: eventId });
      } else {
        fbq('trackCustom', eventName, cleaned, { eventID: eventId });
      }
    }

    try {
      var body = JSON.stringify({
        event_name: eventName,
        event_id: eventId,
        custom_data: cleaned,
        fbp: cookie('_fbp'),
        fbc: cookie('_fbc'),
        page_url: window.location.href
      });
      if (navigator.sendBeacon) {
        navigator.sendBeacon('/api/track', new Blob([body], { type: 'application/json' }));
      } else {
        fetch('/api/track', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
          keepalive: true
        });
      }
    } catch (e) { /* noop */ }
  };

  // Click delegation: any element with [data-track="EventName"] fires once per page load.
  // Optional: data-track-source, data-track-name, data-track-dedupe (custom dedupe key, default once-per-element-per-event)
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest('[data-track]');
    if (!el) return;
    var name = el.getAttribute('data-track');
    if (!name) return;
    var custom = {
      lead_source: el.getAttribute('data-track-source') || '',
      content_name: el.getAttribute('data-track-name') || (el.textContent || '').trim().slice(0, 80)
    };
    var dedupeKey = el.getAttribute('data-track-dedupe');
    if (dedupeKey === null) {
      dedupeKey = name + ':' + (custom.lead_source || custom.content_name || '');
    }
    mk7Track(name, custom, { dedupeKey: dedupeKey });
  });
})();

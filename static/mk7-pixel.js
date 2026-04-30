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

  // ── Audience tracking → lumenmarketing.co/admin ─────────────────
  // Posts every page load + final time-on-page to the Lumen admin database
  // so the /admin/audiences page can build retargeting audiences from MK7
  // visitor IPs and dwell time. Runs on every page that loads this script,
  // not just the grow funnel.
  var AUDIENCE_ENDPOINT = 'https://lumenmarketing.co/api/grow/pageview';
  // "mk7media.com/grow/lb", "mk7media.com/", etc. — readable, consistent
  // across the whole site so the admin filter has stable page labels.
  var pageLabel = 'mk7media.com' + window.location.pathname;
  var pageStart = Date.now();
  var sentDuration = false;

  // Use text/plain so the request stays CORS-simple (no preflight needed).
  // The Lumen endpoint parses with force=True, so JSON-stringified text/plain
  // bodies are decoded the same as application/json.
  function pingAudience(payload) {
    try {
      var body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(AUDIENCE_ENDPOINT, new Blob([body], { type: 'text/plain' }));
        return;
      }
      fetch(AUDIENCE_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'text/plain' },
        body: body,
        keepalive: true,
        mode: 'cors'
      }).catch(function () {});
    } catch (e) { /* noop */ }
  }

  // Fire the initial pageview once the document has a referrer to read
  function sendInitialPageview() {
    pingAudience({
      page: pageLabel,
      referrer: document.referrer || '',
      time_on_page: 0
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sendInitialPageview);
  } else {
    sendInitialPageview();
  }

  // Send time-on-page when the user actually leaves. visibilitychange→hidden
  // is the most reliable signal on mobile Safari (where pagehide/beforeunload
  // are flaky). beforeunload is the desktop fallback. Guard with sentDuration
  // so we never double-count a single visit.
  function sendDuration() {
    if (sentDuration) return;
    var seconds = Math.round((Date.now() - pageStart) / 1000);
    if (seconds <= 0) return;
    sentDuration = true;
    pingAudience({
      page: pageLabel,
      referrer: document.referrer || '',
      time_on_page: seconds
    });
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') sendDuration();
  });
  window.addEventListener('pagehide', sendDuration);
  window.addEventListener('beforeunload', sendDuration);
})();

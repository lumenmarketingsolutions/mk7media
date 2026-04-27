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
  var fired = {};

  window.mk7Track = function (eventName, custom, opts) {
    custom = custom || {};
    opts = opts || {};

    if (opts.dedupeKey) {
      var key = eventName + '|' + opts.dedupeKey;
      if (fired[key]) return;
      fired[key] = true;
    }

    var eventId = uuid();

    if (window.fbq) {
      if (STANDARD.indexOf(eventName) !== -1) {
        fbq('track', eventName, custom, { eventID: eventId });
      } else {
        fbq('trackCustom', eventName, custom, { eventID: eventId });
      }
    }

    try {
      var body = JSON.stringify({
        event_name: eventName,
        event_id: eventId,
        custom_data: custom,
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

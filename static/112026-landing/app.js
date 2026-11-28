/* Fixaligner landing page: qualifier form, attribution and tracking.
   SETUP: put the n8n webhook address that should receive leads in WEBHOOK_URL.
   While it is empty the form runs in demo mode: it fires the tracking events and
   shows the thank you message, but sends the lead nowhere. */
(function () {
  "use strict";

  var CONFIG = {
    WEBHOOK_URL: "", // for example "https://n8n.fixaligner.com/webhook/aligner-landing"
    WHATSAPP: "96170000557",
    QUESTIONS: 4
  };

  function track(meta, ga, params, eventId) {
    try { if (window.fbq) fbq("track", meta, params || {}, eventId ? { eventID: eventId } : undefined); } catch (e) {}
    try { if (window.gtag) gtag("event", ga, params || {}); } catch (e) {}
  }

  /* 1. Attribution: keep UTMs and fbclid from the ad link, also across page reloads */
  var form = document.getElementById("quiz");
  var params = new URLSearchParams(location.search);
  ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"].forEach(function (k) {
    var v = params.get(k);
    try { if (v) sessionStorage.setItem("fx_" + k, v); else v = sessionStorage.getItem("fx_" + k); } catch (e) {}
    if (v && form.elements[k]) form.elements[k].value = v;
  });

  /* 2. Click tracking for WhatsApp, calls and buttons */
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-track]");
    if (!a) return;
    var t = a.getAttribute("data-track");
    if (t.indexOf("whatsapp") === 0) track("Contact", "whatsapp_click", { method: "whatsapp", location: t });
    else if (t === "call") track("Contact", "phone_click", { method: "phone" });
    else try { if (window.gtag) gtag("event", "cta_click", { location: t }); } catch (err) {}
  });

  /* 3. Qualifier */
  var steps = Array.prototype.slice.call(form.querySelectorAll(".q"));
  var bar = form.querySelector(".quiz-progress i");
  var back = document.getElementById("back");
  var count = document.getElementById("count");
  var nav = document.getElementById("quiz-nav");
  var answers = {};
  var current = 0;
  var started = false;

  function show(i) {
    steps.forEach(function (s, n) { s.classList.toggle("active", n === i); });
    current = i;
    bar.style.width = ((i + 1) / steps.length * 100) + "%";
    back.hidden = i === 0;
    count.textContent = i < CONFIG.QUESTIONS ? "Question " + (i + 1) + " of " + CONFIG.QUESTIONS : "Last step";
  }

  steps.forEach(function (step, i) {
    step.querySelectorAll(".opt").forEach(function (btn) {
      btn.addEventListener("click", function () {
        step.querySelectorAll(".opt").forEach(function (b) { b.classList.remove("picked"); });
        btn.classList.add("picked");
        answers[step.getAttribute("data-name")] = btn.textContent.trim();
        if (!started) { started = true; try { if (window.gtag) gtag("event", "quiz_start"); } catch (e) {} }
        setTimeout(function () {
          show(i + 1);
          if (i + 1 === CONFIG.QUESTIONS) { var n = document.getElementById("f-name"); if (window.innerWidth > 900) n.focus(); }
        }, 180);
      });
    });
  });
  back.addEventListener("click", function () { if (current > 0) show(current - 1); });

  /* A lead counts as qualified when the patient is 14 or older and accepts the price or the deposit */
  function qualified() {
    return answers.age !== "Under 14" && answers.budget !== "I need to think about it";
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var name = form.elements.name.value.trim();
    var phone = form.elements.phone.value.replace(/[^\d+]/g, "");
    var err = document.getElementById("err");
    if (name.length < 2 || phone.replace(/\D/g, "").length < 7) { err.classList.add("show"); return; }
    err.classList.remove("show");

    var submit = document.getElementById("submit");
    submit.disabled = true; submit.textContent = "Sending...";

    var eventId = "lead_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
    var payload = {
      source: "aligner_landing",
      name: name,
      phone: phone,
      concern: answers.concern || "",
      age: answers.age || "",
      timing: answers.timing || "",
      budget: answers.budget || "",
      qualified: qualified(),
      event_id: eventId,
      page: location.href.split("#")[0],
      submitted_at: new Date().toISOString()
    };
    ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "fbclid"].forEach(function (k) { payload[k] = form.elements[k].value; });

    function finish() {
      track("Lead", "generate_lead", { content_name: "smile_design_visit", qualified: payload.qualified }, eventId);
      steps.forEach(function (s) { s.classList.remove("active"); });
      nav.style.display = "none";
      bar.style.width = "100%";
      document.getElementById("done").classList.add("active");
      form.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    if (!CONFIG.WEBHOOK_URL) { setTimeout(finish, 400); return; }
    fetch(CONFIG.WEBHOOK_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); finish(); })
      .catch(function () {
        submit.disabled = false; submit.textContent = "Request my visit";
        err.textContent = "Something went wrong. Please try again, or message us on WhatsApp.";
        err.classList.add("show");
      });
  });

  show(0);

  /* 4. Sticky booking bar on phones: shows after the hero, hides while the form is on screen */
  var stickyBar = document.getElementById("bar");
  var hero = document.querySelector(".hero");
  var book = document.getElementById("book");
  var pastHero = false, onForm = false;
  function update() { stickyBar.classList.toggle("show", pastHero && !onForm); }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (en) { pastHero = !en[0].isIntersecting; update(); }).observe(hero);
    new IntersectionObserver(function (en) { onForm = en[0].isIntersecting; update(); }, { threshold: 0.15 }).observe(book);
  }
})();

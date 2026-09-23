"""Google Calendar booking for the Lumen Ai agent.

One job: turn "Thursday 4pm" plus an email into a real event on Kendall's
calendar, with a Meet link, and let Google send the invite. Google is the mail
sender here on purpose -- it attaches the .ics, it comes from Kendall's own
address, and it puts the event in the prospect's calendar rather than in a
message they have to act on.

Everything is Asia/Beirut. Kendall takes these calls on Beirut time and the
calendar itself is set to Beirut, so there is no conversion anywhere and no
chance of the classic off-by-a-timezone booking.
"""
import os
import datetime as _dt

TZ = "Asia/Beirut"
CAL_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
DURATION_MIN = int(os.environ.get("LUMENAI_CALL_MINUTES", "15"))
# Beirut working hours. Without these the agent happily books 3am because the
# prospect said "3" and nobody asked which 3.
WORK_START = int(os.environ.get("LUMENAI_WORK_START", "9"))
WORK_END = int(os.environ.get("LUMENAI_WORK_END", "19"))

try:
    from zoneinfo import ZoneInfo
    _BEIRUT = ZoneInfo(TZ)
except Exception:  # pragma: no cover - py<3.9 or missing tzdata
    _BEIRUT = None


def configured():
    return bool(CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN)


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        None, refresh_token=REFRESH_TOKEN, client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET, token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/calendar.events",
                "https://www.googleapis.com/auth/calendar.readonly"])
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def now_beirut():
    return _dt.datetime.now(_BEIRUT) if _BEIRUT else _dt.datetime.now()


def parse_when(s):
    """'2026-09-30 16:00' -> aware datetime in Beirut. None if unparseable.

    Deliberately strict. A loose parser that guesses is worse than one that
    fails: a wrong guess books a real prospect at the wrong hour and nobody
    finds out until one of them sits waiting."""
    try:
        naive = _dt.datetime.strptime((s or "").strip(), "%Y-%m-%d %H:%M")
    except Exception:
        return None
    return naive.replace(tzinfo=_BEIRUT) if _BEIRUT else naive


def is_free(start, minutes=None):
    """True if nothing else is on the calendar then. Fails OPEN.

    If the availability check itself errors we return True and book anyway: a
    double booking is a conversation Kendall can have, a prospect who agreed to
    a time and then got silence is one he never speaks to again."""
    minutes = minutes or DURATION_MIN
    try:
        svc = _service()
        end = start + _dt.timedelta(minutes=minutes)
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(),
                "timeZone": TZ, "items": [{"id": CAL_ID}]}
        r = svc.freebusy().query(body=body).execute()
        busy = r.get("calendars", {}).get(CAL_ID, {}).get("busy", [])
        return not busy
    except Exception as e:
        print(f"[lumen-ai][gcal] freebusy check failed ({e}) — assuming free")
        return True


def in_hours(start):
    """Inside Kendall's working day, Beirut time."""
    return WORK_START <= start.hour < WORK_END


def busy_windows(day_from, days=7):
    """All busy blocks over the next N days, so we can propose real openings."""
    try:
        svc = _service()
        end = day_from + _dt.timedelta(days=days)
        r = svc.freebusy().query(body={
            "timeMin": day_from.isoformat(), "timeMax": end.isoformat(),
            "timeZone": TZ, "items": [{"id": CAL_ID}]}).execute()
        out = []
        for b in r.get("calendars", {}).get(CAL_ID, {}).get("busy", []):
            out.append((_dt.datetime.fromisoformat(b["start"]),
                        _dt.datetime.fromisoformat(b["end"])))
        return out
    except Exception as e:
        print(f"[lumen-ai][gcal] busy_windows failed ({e})")
        return []


def next_free_slots(after=None, want=2, minutes=None):
    """The next few genuinely open slots, on the hour, inside working hours.

    Used when a prospect asks for a time that is already taken. Offering two real
    alternatives keeps the booking alive in the same breath as the refusal --
    "that one is gone" with nothing after it is where a conversation dies."""
    minutes = minutes or DURATION_MIN
    start = (after or now_beirut()) + _dt.timedelta(hours=1)
    start = start.replace(minute=0, second=0, microsecond=0)
    busy = busy_windows(start, days=7)
    out, cur, guard = [], start, 0
    while len(out) < want and guard < 24 * 7:
        guard += 1
        if in_hours(cur):
            end = cur + _dt.timedelta(minutes=minutes)
            if not any(bs < end and cur < be for bs, be in busy):
                out.append(cur)
        cur += _dt.timedelta(hours=1)
    return out


def book(start, attendee_email, attendee_name=None, phone=None, minutes=None):
    """Create the event and let Google email the invite.

    Returns (event_dict, None) or (None, "reason"). The caller decides what to
    say; this never talks to the prospect."""
    if not configured():
        return None, "google calendar not configured"
    if not start:
        return None, "no start time"
    if not attendee_email or "@" not in attendee_email:
        return None, "no valid email"
    minutes = minutes or DURATION_MIN
    end = start + _dt.timedelta(minutes=minutes)
    who = attendee_name or attendee_email.split("@")[0]
    # The prospect reads this in the invite, so it is the agenda, not a machine
    # signature. "Booked by the agent" as a footer reads like a bot left a note;
    # the same fact placed last, as the proof, reads like the product working.
    desc = [
        "15 minutes.",
        "",
        "We look at how your messages get handled today, and what changes when "
        "nobody has to wait for a reply.",
        "",
        "The video link is in this invite. If the time stops working, just reply "
        "to this email and we will move it.",
        "",
        "Booked over WhatsApp in under two minutes, by the thing we are going to "
        "talk about.",
    ]
    if phone:
        desc += ["", f"WhatsApp: +{phone}"]
    body = {
        "summary": f"Lumen x {who}",
        "description": "\n".join(desc),
        "start": {"dateTime": start.isoformat(), "timeZone": TZ},
        "end": {"dateTime": end.isoformat(), "timeZone": TZ},
        "attendees": [{"email": attendee_email}],
        # Explicit, not useDefault. Google's reminder is the BACKSTOP for anyone
        # the WhatsApp reminder cannot legally reach (outside the 24h window), so
        # it must not depend on whatever default that account happens to carry.
        "reminders": {"useDefault": False, "overrides": [
            {"method": "email", "minutes": 24 * 60},
            {"method": "popup", "minutes": 30},
        ]},
        "conferenceData": {"createRequest": {
            "requestId": f"lumen-{int(start.timestamp())}-{abs(hash(attendee_email)) % 10**6}",
            "conferenceSolutionKey": {"type": "hangoutsMeet"}}},
    }
    try:
        svc = _service()
        ev = svc.events().insert(
            calendarId=CAL_ID, body=body,
            conferenceDataVersion=1,
            sendUpdates="all",          # this is what emails them the invite
        ).execute()
        link = (ev.get("conferenceData", {}).get("entryPoints") or [{}])[0].get("uri")
        print(f"[lumen-ai][gcal] booked {ev.get('id')} {start.isoformat()} "
              f"{attendee_email} meet={link}")
        return ev, None
    except Exception as e:
        print(f"[lumen-ai][gcal] BOOKING FAILED {attendee_email} {start}: {e}")
        return None, str(e)[:200]

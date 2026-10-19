#!/usr/bin/env python3
"""rainbow_i18n — the words RainbowOMMA shows a person, in English and Hebrew.

The language: RAINBOW_LANG (en | he), else the first macOS preferred language, else LC_ALL / LC_MESSAGES / LANG, else English.
JSON status words and exit codes are an API and never translated — only `why`, notifications, names and frame text are.

    rainbow_i18n.py KEY [name=value ...]     print one message (for the shell scripts)
    rainbow_i18n.py lang | dir               print the language (en | he) or its direction (ltr | rtl)
"""
from __future__ import annotations

import os
import subprocess
import sys

LANGS = ("en", "he")
RTL = {"he"}

M = {
    # ── browser-owner ──
    "bo.display_name": {"en": "{label} — agent · do not touch", "he": "{label} — סוכן · לא לגעת"},
    "bo.theme_title": {"en": "Agent: {label}", "he": "סוכן: {label}"},
    "bo.frame_text": {"en": "{label} · AI Agent · Do not touch", "he": "{label} · סוכן · לא לגעת"},
    "bo.human_label": {"en": "Human", "he": "האדם"},
    "bo.human_text": {"en": "HUMAN · free to use", "he": "האדם · HUMAN · ניתן להשתמש"},
    "bo.human_title": {"en": "HUMAN", "he": "האדם · HUMAN"},
    "bo.launcher_missing": {"en": "launcher missing: {path}", "he": "המפעיל חסר: {path}"},
    "bo.port_silent": {"en": "Chrome opened but port {port} did not answer", "he": "Chrome נפתח אבל פורט {port} לא ענה"},
    "bo.unknown_process": {"en": "an unidentified process", "he": "תהליך לא מזוהה"},
    "bo.blocked": {"en": "port {port} answers, but not from {label}'s browser ({who}); not touching it. The human needs to close it",
                   "he": "פורט {port} עונה, אבל לא מהדפדפן של {label} ({who}); לא נוגעים. האדם צריך לסגור אותו"},
    "bo.profile_busy": {"en": "{label}'s profile is open in another Chrome without its control port (pid {pids}) — "
                              "not painting or opening it; the human needs to close it",
                        "he": "הפרופיל של {label} פתוח ב-Chrome אחר בלי פורט השליטה (pid {pids}) — "
                              "לא צובעים ולא פותחים; האדם צריך לסגור אותו"},
    "bo.refused_off": {"en": "the human closed {label}'s browser at {at} — it opens only when the human opens it",
                       "he": "האדם סגר את הדפדפן של {label} ב-{at} — נפתח רק כשהאדם פותח"},
    "bo.refused_off_short": {"en": "the human closed {label}'s browser at {at}", "he": "האדם סגר את הדפדפן של {label} ב-{at}"},
    "bo.hung": {"en": "{label}'s Chrome is running (pid {pids}) but not answering — use recover, not start",
                "he": "Chrome של {label} רץ (pid {pids}) אבל לא עונה — recover, לא start"},
    "bo.closed_by_person": {"en": "{label}'s browser was quit normally (⌘Q) in the last two hours — not reopening it automatically; "
                                  "the human opens it, or the agent asks them to",
                            "he": "הדפדפן של {label} נסגר ביציאה רגילה (⌘Q) בשעתיים האחרונות — לא נפתח אוטומטית; "
                                  "האדם פותח, או שהסוכן מבקש זאת"},
    "bo.only_human_stops": {"en": "only the human closes {label}'s browser (stop --by human). An agent that needs a recovery uses recover",
                            "he": "רק האדם סוגר את הדפדפן של {label} (stop --by human). סוכן שצריך התאוששות — recover"},
    "bo.no_idle": {"en": "{label}'s browser has no idle close (idleMinutes) — only the human closes it (stop --by human)",
                   "he": "לדפדפן של {label} אין סגירה בחוסר פעילות (idleMinutes) — רק האדם סוגר (stop --by human)"},
    "bo.many_roots": {"en": "more than one root of {label}'s browser: {roots} — not touching it",
                      "he": "יותר משורש אחד של הדפדפן של {label}: {roots} — לא נוגעים"},
    "bo.healthy_recheck": {"en": "answered on the re-check — not closed", "he": "ענה בבדיקה החוזרת — לא נסגר"},
    "bo.healthy_last": {"en": "answered right before the close — not closed", "he": "ענה ממש לפני הסגירה — לא נסגר"},
    "bo.tree_changed": {"en": "the processes changed during the check ({before} → {after}) — not closing; try again",
                        "he": "התהליכים השתנו בזמן הבדיקה ({before} → {after}) — לא סוגרים; לנסות שוב"},
    "bo.unknown_agent": {"en": "unknown agent: {agent} — registered: {names}", "he": "סוכן לא רשום: {agent} — רשומים: {names}"},
    "bo.managed": {"en": "{label}'s browser is managed by {by} — report only here", "he": "הדפדפן של {label} מנוהל על ידי {by} — כאן רק דיווח"},
    "bo.no_registry": {"en": "no browsers.json at {path} — run install.sh, or copy examples/browsers.example.json there",
                       "he": "אין browsers.json ב-{path} — להריץ את install.sh, או להעתיק לשם את examples/browsers.example.json"},
    "bo.idle_not_yours": {"en": "{by} is another agent — only {label}'s own reaper (or the keepalive) idle-closes {label}'s browser",
                          "he": "{by} הוא סוכן אחר — רק המנקה של {label} (או ה-keepalive) סוגר את הדפדפן של {label} בחוסר פעילות"},
    "bo.idle_too_soon": {"en": "{label}'s browser was started {mins} min ago — not idle yet (idleMinutes = {idle})",
                         "he": "הדפדפן של {label} נפתח לפני {mins} דק׳ — עוד לא בחוסר פעילות (idleMinutes = {idle})"},
    "bo.front_down": {"en": "{label}'s browser is not running", "he": "הדפדפן של {label} לא רץ"},
    "bo.heal_missing_open": {"en": "{label}'s colors are gone (Chrome Sync) — they come back the next time its browser starts",
                             "he": "הצבעים של {label} ירדו (סנכרון Chrome) — הם יחזרו בהפעלה הבאה של הדפדפן שלו"},
    "bo.heal_chrome_ok": {"en": "Chrome updated to {ver} — every agent's colors and Dock shortcut are in place",
                          "he": "Chrome עודכן ל-{ver} — הצבעים וקיצורי ה-Dock של כל הסוכנים במקום"},
    "bo.heal_chrome_check": {"en": "Chrome updated to {ver} — check: {names}", "he": "Chrome עודכן ל-{ver} — לבדוק: {names}"},
    "bo.no_chrome_app": {"en": "{path} is not installed — install that Chrome, or set \"chrome\" to another one in browsers.json",
                         "he": "{path} לא מותקן — להתקין את ה-Chrome הזה, או לבחור אחר ב-\"chrome\" ב-browsers.json"},
    "bo.busy": {"en": "another action on this browser is running right now", "he": "פעולה אחרת על הדפדפן הזה רצה עכשיו"},
    # ── port-owner ──
    "po.human_port": {"en": "port {port} is kept for the human (humanPorts) — take one of your own: port-owner lease {agent}",
                      "he": "פורט {port} שמור לאדם (humanPorts) — לקחת פורט משלך: port-owner lease {agent}"},
    "po.not_yours": {"en": "port {port} is outside {agent}'s range {range}", "he": "פורט {port} מחוץ לטווח של {agent}‏ ({range})"},
    "po.taken": {"en": "port {port} is taken ({who})", "he": "פורט {port} תפוס ({who})"},
    "po.full": {"en": "no free port left in {agent}'s range {range}", "he": "לא נשאר פורט פנוי בטווח של {agent}‏ ({range})"},
    # ── proc-owner ──
    "pc.no_process": {"en": "no process {pid}", "he": "אין תהליך {pid}"},
    "pc.protected": {"en": "process {pid} is never stopped from here", "he": "את תהליך {pid} לא עוצרים מכאן"},
    "pc.not_yours": {"en": "process {pid} is {owner}'s (by {via}) — {by} may stop only its own", "he": "תהליך {pid} שייך ל-{owner} (לפי {via}) — {by} עוצר רק את שלו"},
    # ── rainbowomma-doctor ──
    "dr.python": {"en": "Python 3.9 or newer", "he": "Python 3.9 ומעלה"},
    "dr.python_fix": {"en": "install a newer python3 (Homebrew: brew install python)", "he": "להתקין python3 חדש יותר (Homebrew: brew install python)"},
    "dr.registry": {"en": "the agent registry (browsers.json)", "he": "רישום הסוכנים (browsers.json)"},
    "dr.agents": {"en": "{n} agents: {names}", "he": "{n} סוכנים: {names}"},
    "dr.registry_fix": {"en": "fix the row named above in browsers.json", "he": "לתקן את השורה שצוינה ב-browsers.json"},
    "dr.chrome": {"en": "{app} installed", "he": "{app} מותקן"},
    "dr.chrome_fix": {"en": "install {app}, or choose another \"chrome\" for those agents", "he": "להתקין את {app}, או לבחור \"chrome\" אחר לסוכנים האלה"},
    "dr.state": {"en": "the state folder is writable", "he": "אפשר לכתוב בתיקיית המצב"},
    "dr.state_fix": {"en": "make {path} writable, or set RAINBOW_HOME to another folder", "he": "לאפשר כתיבה ב-{path}, או לקבוע RAINBOW_HOME לתיקייה אחרת"},
    "dr.tool": {"en": "{tool} beside the others", "he": "{tool} ליד שאר הכלים"},
    "dr.tool_fix": {"en": "run install.sh again", "he": "להריץ שוב את install.sh"},
    "dr.system_events": {"en": "permission to ask System Events which app is in front", "he": "הרשאה לשאול את System Events איזו אפליקציה בחזית"},
    "dr.system_events_fix": {"en": "System Settings → Privacy & Security → Automation: allow your terminal to control System Events",
                             "he": "הגדרות המערכת ← פרטיות ואבטחה ← אוטומציה: לאפשר למסוף לשלוט ב-System Events"},
    "dr.unknown": {"en": "could not tell", "he": "לא ידוע"},
    "dr.hid": {"en": "keyboard and mouse idle time (to wait while the human types)", "he": "זמן ללא מקלדת ועכבר (כדי לחכות כשהאדם מקליד)"},
    "dr.hid_fix": {"en": "ioreg did not report HIDIdleTime — agents won't wait for a typing human", "he": "ioreg לא החזיר HIDIdleTime — סוכנים לא יחכו לאדם שמקליד"},
    "dr.macos": {"en": "macOS", "he": "macOS"},
    "dr.macos_fix": {"en": "browsers, documents and the desktop work on macOS only; ports and processes work here too",
                     "he": "דפדפנים, מסמכים ושולחן העבודה עובדים רק ב-macOS; פורטים ותהליכים עובדים גם כאן"},
    "dr.app": {"en": "{app} (office-owner)", "he": "{app} (office-owner)"},
    "dr.app_fix": {"en": "only needed for documents and PDF conversion in {app}", "he": "נדרש רק למסמכים ולהמרה ל-PDF ב-{app}"},
    "dr.cua": {"en": "Cua Driver (the colored cursor)", "he": "Cua Driver (הסמן הצבעוני)"},
    "dr.cua_fix": {"en": "only needed for computer use with a colored cursor — see the README", "he": "נדרש רק לשליטה במחשב עם סמן צבעוני — ראו README"},
    "dr.job": {"en": "launchd job {label}", "he": "משימת launchd ‏{label}"},
    "dr.job_fix": {"en": "install.sh {flag} installs it", "he": "install.sh {flag} מתקין אותה"},
    "dr.guard": {"en": "the guardrail in an agent's settings", "he": "השומר בהגדרות של סוכן"},
    "dr.guard_fix": {"en": "add your agent's adapter — docs/AGENTS.md, or install.sh --adapter <agent>",
                     "he": "להוסיף את המתאם של הסוכן — docs/AGENTS.md, או install.sh --adapter <agent>"},
    "dr.summary_ok": {"en": "Everything needed is in place.", "he": "כל מה שנדרש במקום."},
    "dr.summary_bad": {"en": "{n} needed thing(s) missing — the fix is under each ✗.", "he": "חסרים {n} דברים נדרשים — התיקון מתחת לכל ✗."},
    # ── menu bar ──
    "mb.paused_title": {"en": "agents paused", "he": "הסוכנים בהשהיה"},
    "mb.open": {"en": "Open its browser", "he": "לפתוח את הדפדפן"},
    "mb.front": {"en": "Bring its browser to the front", "he": "להביא את הדפדפן לקדמת המסך"},
    "mb.close": {"en": "Close its browser", "he": "לסגור את הדפדפן"},
    "mb.pause_all": {"en": "Pause all agents", "he": "להשהות את כל הסוכנים"},
    "mb.resume_all": {"en": "Resume all agents", "he": "להמשיך את כל הסוכנים"},
    "mb.recent": {"en": "Latest receipts", "he": "הקבלות האחרונות"},
    "mb.doctor": {"en": "Check the setup (doctor)…", "he": "לבדוק את ההתקנה (doctor)…"},
    # ── rainbowomma-approve ──
    "ap.dialog": {"en": "{agent} wants to send something that can't be taken back.\n\nWhy: {why}\n\nExactly this:\n{command}",
                  "he": "{agent} רוצה לשלוח משהו שאי אפשר להחזיר.\n\nלמה: {why}\n\nבדיוק את זה:\n{command}"},
    "ap.allow": {"en": "Allow once", "he": "לאשר פעם אחת"},
    "ap.deny": {"en": "Don't allow", "he": "לא לאשר"},
    "ap.refused": {"en": "the human did not allow it (or did not answer in time) — don't send it; ask them what to do",
                   "he": "האדם לא אישר (או לא ענה בזמן) — לא לשלוח; לשאול אותו מה לעשות"},
    "ap.next": {"en": "run exactly the same command again within 5 minutes — it is allowed once",
                "he": "להריץ שוב בדיוק את אותה פקודה תוך 5 דקות — היא מותרת פעם אחת"},
    "mb.takeover": {"en": "Take over the screen", "he": "להשתלט על המסך"},
    "mb.handback": {"en": "Hand the screen back", "he": "להחזיר את המסך לסוכנים"},
    "mb.screen_held": {"en": "screen: {who}", "he": "המסך: {who}"},
    # ── office-owner / agent-office ──
    "ao.no_file": {"en": "no such file: {path}", "he": "אין קובץ: {path}"},
    "ao.bad_app": {"en": "unsupported app — word / excel / acrobat / preview", "he": "אפליקציה לא נתמכת — word / excel / acrobat / preview"},
    "ao.no_lease": {"en": "this agent holds no lease on this document (by its full path) — only what the agent opened through "
                          "agent-office is closed",
                    "he": "אין חכירה של הסוכן הזה על המסמך הזה (לפי הנתיב המלא) — סוגרים רק מה שהסוכן פתח דרך agent-office"},
    "ao.pdf_types": {"en": "pdf through Word — doc / docx / rtf only", "he": "pdf דרך Word — רק doc / docx / rtf"},
    "ao.pdf_out": {"en": "--out must be a .pdf file and not the source file", "he": "--out חייב להיות קובץ ‎.pdf ולא קובץ המקור"},
    "ao.pdf_exists": {"en": "{path} already exists — not replacing it (pass --force to replace it, or --out for another name)",
                      "he": "{path} כבר קיים — לא מחליפים אותו (‎--force כדי להחליף, או ‎--out לשם אחר)"},
    "ao.xlsx_types": {"en": "xlsx through Excel — xlsx / xlsm / xls only", "he": "xlsx דרך Excel — רק xlsx / xlsm / xls"},
    "ao.xlsx_out": {"en": "--out must be a {ext} file too", "he": "--out חייב להיות גם הוא קובץ {ext}"},
    "ao.xlsx_open": {"en": "{path} is open in Excel (or Excel could not say) — not writing under it; close it, or use --out",
                     "he": "{path} פתוח ב-Excel (או ש-Excel לא ענה) — לא כותבים מתחתיו; לסגור אותו, או להשתמש ב-‎--out"},
    "ao.xlsx_failed": {"en": "Excel did not recalculate the workbook — {detail}", "he": "Excel לא חישב מחדש את חוברת העבודה — {detail}"},
    "ao.pdf_failed": {"en": "Word produced no PDF — {detail}", "he": "Word לא הפיק PDF — {detail}"},
    # ── desktop icons (desk-browser.sh, make-desktop-apps.sh) ──
    "desk.name.human": {"en": "Human", "he": "האדם"},
    "desk.name.all": {"en": "All", "he": "הכל"},
    "desk.human_open": {"en": "The human's Chrome is open", "he": "Chrome של האדם פתוח"},
    "desk.human_open_failed": {"en": "Could not open the human's Chrome", "he": "לא הצלחתי לפתוח את Chrome של האדם"},
    "desk.opened": {"en": "{name}'s browser is open", "he": "הדפדפן של {name} נפתח"},
    "desk.already_open": {"en": "{name}'s browser is already open", "he": "הדפדפן של {name} כבר פתוח"},
    "desk.in_front": {"en": "{name}'s browser is in front", "he": "הדפדפן של {name} בקדמת המסך"},
    "desk.not_opened": {"en": "{name}'s browser did not open: {status} — {why}", "he": "הדפדפן של {name} לא נפתח: {status} — {why}"},
    "desk.closed": {"en": "{name}'s browser is closed — it will not open by itself until it is opened by hand from the shortcut",
                    "he": "הדפדפן של {name} נסגר — לא ייפתח לבד עד לפתיחה ידנית מהקיצור"},
    "desk.not_closed": {"en": "{name}'s browser did not close: {status} — {why}", "he": "הדפדפן של {name} לא נסגר: {status} — {why}"},
    "desk.closed_word": {"en": "closed", "he": "נסגר"},
    "desk.owner_silent": {"en": "browser-owner did not answer", "he": "browser-owner לא ענה"},
    "desk.all_closed_tail": {"en": "they will not open by themselves until they are opened by hand", "he": "לא ייפתחו לבד עד לפתיחה ידנית"},
    "desk.usage": {"en": "usage: desk-browser.sh open|close <agent in browsers.json>|human  ·  desk-browser.sh close agents",
                   "he": "שימוש: desk-browser.sh open|close <סוכן מ-browsers.json>|human  ·  desk-browser.sh close agents"},
    "desk.app.open_human": {"en": "Human — open Chrome", "he": "האדם — פתח Chrome"},
    "desk.app.open_agent": {"en": "{name} — open browser", "he": "{name} — פתח דפדפן"},
    "desk.app.close_human": {"en": "Human — close Chrome (not the agents')", "he": "האדם — סגור Chrome (לא סוכנות)"},
    "desk.app.close_agent": {"en": "{name} — close browser", "he": "{name} — סגור דפדפן"},
    "desk.app.close_all": {"en": "All agents — close ⚠️", "he": "כל הסוכנים — סגור ⚠️"},
    "desk.confirm_one": {"en": "Close {name}'s browser? The agent will be logged out, and the browser will not open by itself until "
                               "it is opened by hand from the shortcut.",
                         "he": "לסגור את הדפדפן של {name}? ההתחברות של הסוכן תתנתק, והוא לא ייפתח לבד עד לפתיחה ידנית מהקיצור."},
    "desk.confirm_all": {"en": "Close the browsers of all the agents ({names})? The agents will be logged out, and none of them will "
                               "open by itself until it is opened by hand.",
                         "he": "לסגור את הדפדפנים של כל הסוכנים ({names})? ההתחברויות של הסוכנים יתנתקו, ואף אחד מהם לא ייפתח לבד "
                               "עד לפתיחה ידנית."},
    "dock.app_name": {"en": "{n} · {name} — agent browser", "he": "{n} · {name} — דפדפן סוכן"},
    "dock.human_name": {"en": "{n} · {name} — my browser", "he": "{n} · {name} — הדפדפן שלי"},
    "desk.btn_cancel": {"en": "Cancel", "he": "ביטול"},
    "desk.btn_close": {"en": "Close", "he": "סגור"},
    "desk.error": {"en": "Error: ", "he": "שגיאה: "},
    # ── human-chrome.sh ──
    "hc.title": {"en": "The human's Chrome", "he": "Chrome של האדם"},
    "hc.not_up": {"en": "did not start — check that Google Chrome is installed", "he": "לא עלה — לבדוק ש-Google Chrome מותקן"},
    # ── kill-chrome.sh ──
    "kc.owner_silent": {"en": "browser-owner did not answer — the agents' browsers were not closed (only the rest was). To close them: "
                              "fix browser-owner, or close them by hand.",
                        "he": "browser-owner לא ענה — דפדפני הסוכנים לא נסגרו (נסגר רק השאר). לסגור אותם: לתקן את browser-owner, "
                              "או לסגור ידנית."},
    "kc.agent_closed": {"en": "{name}'s browser was closed through browser-owner and recorded as 'closed by the human' — it will not "
                              "open by itself.",
                        "he": "הדפדפן של {name} נסגר דרך browser-owner ונרשם 'נסגר ע\"י האדם' — הוא לא ייפתח לבד."},
    "kc.agent_kept": {"en": "browser-owner did not close {name}'s browser ({out}) — it stays open (it is not closed here directly, so "
                            "it cannot reopen without a record).",
                      "he": "browser-owner לא סגר את הדפדפן של {name} ({out}) — הוא נשאר פתוח (לא נסגר כאן ישירות, כדי שלא "
                            "ייפתח מחדש בלי רישום)."},
    "kc.only_agents": {"en": "No Chrome processes to close. What is open are the agents' CDP browsers ({n} processes), left out on "
                             "purpose (so the agents keep their logins). To close them too: kill-chrome.sh --all",
                       "he": "אין תהליכי Chrome לסגירה. מה שפתוח הם דפדפני ה-CDP של הסוכנים ({n} תהליכים), והם מוחרגים בכוונה "
                             "(כדי לא לאבד התחברויות פעילות של הסוכנים). לסגור גם אותם: kill-chrome.sh --all"},
    "kc.none": {"en": "No open Chrome processes found.", "he": "לא נמצאו תהליכי Chrome פתוחים."},
    "kc.spared": {"en": "The agents' CDP browsers ({n} processes) are not included — they stayed open on purpose (so the agents keep "
                        "their logins).",
                  "he": "לא כולל את דפדפני ה-CDP של הסוכנים ({n} תהליכים) — הם נשארו פתוחים בכוונה (כדי לא לאבד התחברויות "
                        "פעילות של הסוכנים)."},
    "kc.closed_all": {"en": "Closed {n} Chrome processes.", "he": "נסגרו {n} תהליכי Chrome."},
    "kc.closed_some": {"en": "Closed {n} of {total}. {left} did not respond.", "he": "נסגרו {n} מתוך {total}. נשארו {left} שלא נענו."},
    # ── examples/agent-launcher.sh ──
    "al.title": {"en": "{name}'s browser (CDP)", "he": "דפדפן {name} (CDP)"},
    "al.already": {"en": "already running (port {port}) — no new window opened", "he": "כבר רץ (פורט {port}) — לא נפתח חלון חדש"},
    "al.up": {"en": "up — CDP channel active", "he": "עלה — ערוץ CDP פעיל"},
    "al.failed": {"en": "failed to open — {out}", "he": "הפתיחה נכשלה — {out}"},
    "al.no_chrome": {"en": "error: Google Chrome not found", "he": "שגיאה: Google Chrome לא נמצא"},
    "al.up_tabs": {"en": "up — CDP channel active, {tabs} tabs restored", "he": "עלה — ערוץ CDP פעיל, {tabs} טאבים שוחזרו"},
    "al.port_silent": {"en": "opened, but the CDP channel did not come up on {port} — the agent cannot control it",
                       "he": "נפתח אבל ערוץ ה-CDP לא עלה על {port} — הסוכן לא יוכל לשלוט בו"},
}

_detected = None


def _mac_lang():
    if sys.platform != "darwin":
        return ""
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=3).stdout
        for tok in out.replace("(", " ").replace(")", " ").replace(",", " ").replace('"', " ").split():
            return tok.lower()
    except Exception:
        pass
    return ""


def lang():
    """en | he — RAINBOW_LANG wins; the macOS / locale guess is made once per process"""
    want = (os.environ.get("RAINBOW_LANG") or "").strip().lower()[:2]
    if want in LANGS:
        return want
    global _detected
    if _detected is None:
        guess = _mac_lang() or os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
        _detected = "he" if guess.lower().startswith(("he", "iw")) else "en"
    return _detected


def direction(lg=None):
    return "rtl" if (lg or lang()) in RTL else "ltr"


def t(key, **kw):
    """the message in the current language (English when a translation is missing)"""
    m = M[key]
    s = m.get(lang()) or m["en"]
    return s.format(**kw) if kw else s


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    if argv[0] == "lang":
        print(lang())
        return 0
    if argv[0] == "dir":
        print(direction())
        return 0
    if argv[0] not in M:
        print(argv[0])
        return 1
    kw = dict(x.split("=", 1) for x in argv[1:] if "=" in x)
    print(t(argv[0], **kw))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

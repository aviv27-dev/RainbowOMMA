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
    "bo.heal_missing_still": {"en": "{label} has been running without its colors for {hours} h — stop and start its browser when it "
                                    "suits you (or it gets them back at its next idle stop)",
                              "he": "{label} רץ בלי הצבעים שלו כבר {hours} שעות — לעצור ולהפעיל את הדפדפן שלו כשנוח (או שהצבעים "
                                    "יחזרו בעצירה הבאה שלו בחוסר פעילות)"},
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
    "ao.damaged": {"en": "Word was not asked to open it: {detail} — a damaged file opens a dialog in Word that blocks every "
                         "conversion after it; fix or re-save the file", "he": "Word לא התבקש לפתוח אותו: {detail} — קובץ פגום פותח "
                         "ב-Word חלון שחוסם את כל ההמרות שאחריו; לתקן או לשמור מחדש את הקובץ"},
    "ao.word_dialog": {"en": "Word is showing a dialog, which blocks every conversion — close it (or ask the human), then try "
                             "again", "he": "Word מציג חלון דו-שיח שחוסם כל המרה — לסגור אותו (או לבקש מהאדם) ולנסות שוב"},
    # ── desktop icons (desk-browser.sh, make-desktop-apps.sh) ──
    # ── rainbow-panel (the window: open / close / front, color and name, add an agent) ──
    "panel.title": {"en": "RainbowOMMA — browsers", "he": "RainbowOMMA — מצב דפדפנים"},
    "panel.sub": {"en": "The browsers on this shared Mac — which are open, each one's color and name",
                  "he": "הדפדפנים על המק המשותף — מי פתוח, הצבע והשם של כל אחד"},
    "panel.loading": {"en": "Loading…", "he": "טוען…"},
    "panel.add": {"en": "➕ Add an agent", "he": "➕ הוספת סוכן"},
    "panel.name_ph": {"en": "Name in English (charlie)", "he": "שם באנגלית (charlie)"},
    "panel.label_ph": {"en": "Display name (Charlie)", "he": "שם לתצוגה (צ׳רלי)"},
    "panel.add_go": {"en": "Add", "he": "הוסף"},
    "panel.add_hint": {"en": "It gets a free port and a Chrome profile of its own. Its browser does not open now — only when you press Open, or the agent asks.",
                       "he": "הסוכן יקבל פורט פנוי ופרופיל Chrome משלו. הדפדפן שלו לא נפתח עכשיו — רק כשלוחצים פתח, או כשהסוכן מבקש."},
    "panel.toast_close": {"en": "Close", "he": "סגור"},
    "panel.act_open": {"en": "Open", "he": "פתח"},
    "panel.act_opening": {"en": "Opening…", "he": "פותח…"},
    "panel.act_front": {"en": "To front", "he": "לחזית"},
    "panel.act_close": {"en": "Close", "he": "סגור"},
    "panel.act_closing": {"en": "Closing…", "he": "סוגר…"},
    "panel.st_open": {"en": "open", "he": "פתוח"},
    "panel.st_closed": {"en": "closed", "he": "סגור"},
    "panel.st_hung": {"en": "not answering", "he": "תקוע"},
    "panel.st_blocked": {"en": "port taken", "he": "פורט תפוס"},
    "panel.st_busy": {"en": "profile busy", "he": "פרופיל תפוס"},
    "panel.human_detail": {"en": "Your own Chrome · {label}", "he": "ה-Chrome שלך · {label}"},
    "panel.agent_detail": {"en": "agent · port {port}", "he": "סוכן · פורט {port}"},
    "panel.off_by_human": {"en": " · the human closed it at {at} — it won't open by itself", "he": " · האדם סגר ב-{at} — לא ייפתח לבד"},
    "panel.stopped_by": {"en": " · closed by {by} at {at}", "he": " · נסגר ע״י {by} ב-{at}"},
    "panel.managed": {"en": " · managed by another program", "he": " · מנוהל ע״י תוכנה אחרת"},
    "panel.style_title": {"en": "Color and name", "he": "צבע ושם"},
    "panel.save": {"en": "Save", "he": "שמור"},
    "panel.save_hint": {"en": "Goes into the browser the next time it opens after closing", "he": "נכנס לדפדפן בפתיחה הבאה אחרי סגירה"},
    "panel.read_failed": {"en": "The panel can't read the state ({why}) — close it and open it again",
                          "he": "הלוח לא מצליח לקרוא את המצב ({why}) — לסגור ולפתוח שוב"},
    "panel.unknown_action": {"en": "Unknown action", "he": "פעולה לא מוכרת"},
    "panel.human_front_ok": {"en": "✓ The human's Chrome is in front", "he": "✓ Chrome של האדם בחזית"},
    "panel.front_ok": {"en": "✓ In front", "he": "✓ הובא לחזית"},
    "panel.front_failed": {"en": "✗ The browser isn't running", "he": "✗ הדפדפן לא רץ"},
    "panel.failed": {"en": "✗ That didn't work", "he": "✗ לא הצלחתי"},
    "panel.no_answer": {"en": "no answer", "he": "אין תשובה"},
    "panel.bad_color": {"en": "Not a #RRGGBB color", "he": "צבע לא תקין"},
    "panel.empty_label": {"en": "The name is empty", "he": "שם ריק"},
    "panel.human_fixed": {"en": "The human's row keeps its own color and name", "he": "לשורה של האדם צבע ושם קבועים"},
    "panel.not_registered": {"en": "Not a registered agent", "he": "סוכן לא רשום"},
    "panel.saved": {"en": "✓ Saved — the color and name go into the browser the next time it opens after closing",
                    "he": "✓ נשמר — הצבע והשם ייכנסו לדפדפן בפתיחה הבאה אחרי סגירה"},
    "panel.bad_name": {"en": "A name in English: lowercase letters, digits and - (e.g. charlie)",
                       "he": "שם באנגלית: אותיות קטנות, ספרות ומקף (למשל charlie)"},
    "panel.no_port": {"en": "No free port in 9222–9299", "he": "אין פורט פנוי בטווח 9222–9299"},
    "panel.exists": {"en": "There is already an agent with that name", "he": "כבר רשום סוכן בשם הזה"},
    "panel.added": {"en": "✓ Added — port {port}; its browser opens when you press Open, or when the agent asks",
                    "he": "✓ נוסף — פורט {port}; הדפדפן שלו ייפתח כשלוחצים פתח, או כשהסוכן מבקש"},
    "panel.opened": {"en": "✓ The panel is open", "he": "✓ הלוח נפתח"},
    "panel.not_up": {"en": "✗ The panel did not start: {why}", "he": "✗ הלוח לא עלה: {why}"},
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
    # ── --help (bin/rainbow_help.py): every tool's help, one shape ──
    "help.commands": {"en": "Commands:", "he": "פקודות:"},
    "help.exits": {"en": "Exit codes:", "he": "קודי יציאה:"},
    "help.more": {"en": "More:", "he": "עוד:"},
    "help.eg": {"en": "e.g.", "he": "לדוגמה:"},
    "help.x.ok": {"en": "ok", "he": "תקין"},
    "help.x.refused": {"en": "refused — don't retry (the reason is in the answer)",
                       "he": "סורב — לא לנסות שוב (הסיבה בתשובה)"},
    "help.x.failed": {"en": "failure (the status word and the reason are in the answer)",
                      "he": "כשל (מילת הסטטוס והסיבה בתשובה)"},
    "help.browser-owner": {"en": "the one owner of every agent's Chrome on a shared Mac",
                           "he": "הבעלים היחיד של ה-Chrome של כל סוכן ב-Mac משותף"},
    "help.browser-owner.1": {"en": "who's up, blocked or hung; the agents' names; one agent",
                             "he": "מי פתוח, חסום או תקוע; שמות הסוכנים; סוכן אחד"},
    "help.browser-owner.2": {"en": "open the agent's own browser, painted in its color",
                             "he": "פותח את הדפדפן של הסוכן, צבוע בצבע שלו"},
    "help.browser-owner.3": {"en": "only the human closes an agent's browser", "he": "רק האדם סוגר דפדפן של סוכן"},
    "help.browser-owner.4": {"en": "close an idle browser; restart a hung one; bring it forward",
                             "he": "סוגר דפדפן שלא בשימוש; מפעיל מחדש דפדפן תקוע; מביא לחזית"},
    "help.browser-owner.5": {"en": "open an address in the agent's own browser, never the human's",
                             "he": "פותח כתובת בדפדפן של הסוכן, אף פעם לא של האדם"},
    "help.browser-owner.6": {"en": "tidy tabs; a job's tabs close when it ends",
                             "he": "מסדר טאבים; הטאבים של משימה נסגרים כשהיא מסתיימת"},
    "help.browser-owner.7": {"en": "point a browser MCP server at the agent's own browser",
                             "he": "מכוון שרת MCP של דפדפן לדפדפן של הסוכן"},
    "help.browser-owner.8": {"en": "repair what drifted; repaint the human's Chrome; is the human here?",
                             "he": "מתקן מה שזז; צובע מחדש את ה-Chrome של האדם; האם האדם כאן?"},
    "help.port-owner": {"en": "every agent's network ports: a range per agent, leases inside it, the usual ports left to the human",
                        "he": "הפורטים של כל סוכן: טווח לכל סוכן, השאלות בתוכו, והפורטים הרגילים נשארים לאדם"},
    "help.port-owner.1": {"en": "a free port of the agent's own, held for it", "he": "פורט פנוי של הסוכן, שמור בשבילו"},
    "help.port-owner.2": {"en": "the same, as shell words", "he": "אותו דבר, כמילים ל-shell"},
    "help.port-owner.3": {"en": "whose port this is, and who listens on it", "he": "של מי הפורט, ומי מאזין עליו"},
    "help.port-owner.4": {"en": "give a lease back", "he": "מחזיר השאלה"},
    "help.port-owner.5": {"en": "the ranges and the leases", "he": "הטווחים וההשאלות"},
    "help.proc-owner": {"en": "whose process this is on a shared Mac, and stopping only your own",
                        "he": "של מי התהליך ב-Mac משותף, ועצירה רק של שלך"},
    "help.proc-owner.1": {"en": "which agent (or the human) a process belongs to", "he": "לאיזה סוכן (או לאדם) שייך תהליך"},
    "help.proc-owner.2": {"en": "stop it only if it is WHO's (the human may stop any)",
                          "he": "עוצר רק אם הוא של WHO (האדם יכול לעצור כל תהליך)"},
    "help.proc-owner.3": {"en": "the agent's processes, and the ports they listen on",
                          "he": "התהליכים של הסוכן, והפורטים שהם מאזינים עליהם"},
    "help.proc-owner.4": {"en": "the calling process becomes one of the agent's roots",
                          "he": "התהליך הקורא נהיה אחד השורשים של הסוכן"},
    "help.proc-owner.5": {"en": "after a session: its leftover servers stop, its port leases go back",
                          "he": "אחרי סשן: השרתים שנשארו נעצרים, השאלות הפורטים חוזרות"},
    "help.office-owner": {"en": "the one owner of the shared Office and PDF apps an agent touches",
                          "he": "הבעלים היחיד של אפליקציות Office ו-PDF המשותפות שסוכן נוגע בהן"},
    "help.office-owner.1": {"en": "lease a document; close it only if it is saved and nobody had it open",
                            "he": "משאיל מסמך; סוגר רק אם נשמר ואף אחד לא פתח אותו לפני"},
    "help.office-owner.2": {"en": "convert through Word, on a temp copy", "he": "המרה דרך Word, על עותק זמני"},
    "help.office-owner.3": {"en": "formulas recalculated by Excel", "he": "הנוסחאות מחושבות מחדש ב-Excel"},
    "help.office-owner.4": {"en": "close leftovers, quit apps it launched; the leases; the apps",
                            "he": "סוגר שאריות, יוצא מאפליקציות שהוא הפעיל; ההשאלות; האפליקציות"},
    "help.office-owner.x0": {"en": "done", "he": "בוצע"},
    "help.office-owner.x3": {"en": "left open (not saved, or someone else had it open)",
                             "he": "נשאר פתוח (לא נשמר, או שמישהו אחר פתח אותו)"},
    "help.office-owner.x2": {"en": "refused (a damaged file)", "he": "סורב (קובץ פגום)"},
    "help.office-owner.x1": {"en": "failure (blocked-by-dialog included)", "he": "כשל (כולל blocked-by-dialog)"},
    "help.auth-owner": {"en": "one agent at a time signs in to a site; the human hands the one-time code to that agent only",
                        "he": "סוכן אחד בכל פעם מתחבר לאתר; האדם מעביר את הקוד החד-פעמי רק לסוכן הזה"},
    "help.auth-owner.1": {"en": "sign in to SITE now; it is yours until you release it",
                          "he": "מתחבר ל-SITE עכשיו; הוא שלך עד שתשחרר"},
    "help.auth-owner.2": {"en": "done signing in", "he": "סיים להתחבר"},
    "help.auth-owner.3": {"en": "ask the human for the one-time code — it comes back to you only",
                          "he": "מבקש מהאדם את הקוד החד-פעמי — הוא חוזר רק אליך"},
    "help.auth-owner.4": {"en": "who holds a site; every lease", "he": "מי מחזיק אתר; כל ההשאלות"},
    "help.screen-owner": {"en": "who may drive the screen — keyboard, mouse, the window in front",
                          "he": "מי רשאי לשלוט במסך — מקלדת, עכבר, החלון שבחזית"},
    "help.screen-owner.1": {"en": "hold the screen for an agent that drives the foreground",
                            "he": "מחזיק את המסך לסוכן שעובד בחזית"},
    "help.screen-owner.2": {"en": "give it back", "he": "מחזיר אותו"},
    "help.screen-owner.3": {"en": "the human takes the screen (every agent's GUI action waits); gives it back",
                            "he": "האדם לוקח את המסך (כל פעולת ממשק של סוכן ממתינה); מחזיר אותו"},
    "help.screen-owner.4": {"en": "who holds it now, and until when", "he": "מי מחזיק אותו עכשיו, ועד מתי"},
    "help.sim-owner": {"en": "an iOS Simulator of its own for every agent", "he": "סימולטור iOS משלו לכל סוכן"},
    "help.sim-owner.1": {"en": "the agent's own simulator, booted", "he": "הסימולטור של הסוכן, מופעל"},
    "help.sim-owner.2": {"en": "whose simulator this is", "he": "של מי הסימולטור"},
    "help.sim-owner.3": {"en": "give it back (it stays installed)", "he": "מחזיר אותו (הוא נשאר מותקן)"},
    "help.sim-owner.4": {"en": "every agent's simulator", "he": "הסימולטור של כל סוכן"},
    "help.rainbowomma-approve": {"en": "the human says yes (or no) before an agent sends something that can't be taken back",
                                 "he": "האדם אומר כן (או לא) לפני שסוכן שולח משהו שאי אפשר להחזיר"},
    "help.rainbowomma-approve.1": {"en": "a dialog shows the human exactly what will be sent; allowed once, within 5 minutes",
                                   "he": "חלון מראה לאדם בדיוק מה יישלח; מאושר פעם אחת, תוך 5 דקות"},
    "help.rainbowomma-approve.2": {"en": "the approvals waiting to be used", "he": "האישורים שמחכים לשימוש"},
    "help.rainbowomma-approve.x0": {"en": "approved", "he": "אושר"},
    "help.rainbowomma-approve.x2": {"en": "refused, or no answer", "he": "סורב, או שאין תשובה"},
    "help.rainbowomma-clip": {"en": "a clipboard of its own for every agent, so no agent overwrites (or reads) the human's",
                              "he": "לוח העתקה משלו לכל סוכן, כדי שאף סוכן לא ידרוס (או יקרא) את של האדם"},
    "help.rainbowomma-clip.1": {"en": "keep what comes on stdin", "he": "שומר את מה שמגיע ב-stdin"},
    "help.rainbowomma-clip.2": {"en": "print it back", "he": "מדפיס אותו בחזרה"},
    "help.rainbowomma-clip.3": {"en": "forget them all", "he": "שוכח את כולם"},
    "help.rainbowomma-pause": {"en": "the human's stop button for every agent at once",
                               "he": "כפתור העצירה של האדם לכל הסוכנים בבת אחת"},
    "help.rainbowomma-pause.1": {"en": "pause every agent (nothing is killed); resume",
                                 "he": "משהה את כל הסוכנים (שום דבר לא נהרג); ממשיך"},
    "help.rainbowomma-pause.2": {"en": "paused or not, since when", "he": "מושהה או לא, ממתי"},
    "help.rainbowomma-doctor": {"en": "is everything RainbowOMMA needs in place on this Mac? Changes nothing",
                                "he": "האם כל מה ש-RainbowOMMA צריך נמצא ב-Mac הזה? לא משנה כלום"},
    "help.rainbowomma-doctor.1": {"en": "one line per check, each missing one with its fix",
                                  "he": "שורה לכל בדיקה, וכל חוסר עם התיקון שלו"},
    "help.rainbowomma-doctor.2": {"en": "the running system: agents, presence, ports, Office, recent errors — each problem with its fix",
                                  "he": "המערכת שרצה: סוכנים, נוכחות, פורטים, Office, שגיאות אחרונות — כל בעיה עם התיקון שלה"},
    "help.rainbowomma-doctor.3": {"en": "every log RainbowOMMA writes, as one timeline",
                                  "he": "כל הלוגים ש-RainbowOMMA כותב, כציר זמן אחד"},
    "help.rainbowomma-doctor.x0": {"en": "everything needed is in place", "he": "כל מה שצריך קיים"},
    "help.rainbowomma-doctor.x1": {"en": "something needed is missing (status: something needs attention)",
                                   "he": "משהו שצריך חסר (status: משהו דורש תשומת לב)"},
    "help.rainbowomma-report": {"en": "file a bug or a feature request, after a privacy scan of what you send",
                                "he": "פתיחת באג או בקשה, אחרי סריקת פרטיות של מה שנשלח"},
    "help.rainbowomma-report.1": {"en": "scan, check the issue template, then send with gh",
                                  "he": "סורק, בודק את התבנית, ואז שולח עם gh"},
    "help.rainbowomma-report.2": {"en": "only the scan: every finding, nothing sent",
                                  "he": "רק הסריקה: כל הממצאים, שום דבר לא נשלח"},
    "help.rainbowomma-report.x0": {"en": "sent (or a clean dry run or scan)", "he": "נשלח (או הרצה יבשה או סריקה נקייה)"},
    "help.rainbowomma-report.x2": {"en": "refused: a finding, or the template's headings missing",
                                   "he": "סורב: ממצא, או שכותרות התבנית חסרות"},
    "help.receipts": {"en": "one line per thing the owners did or refused, for the human to read back",
                      "he": "שורה לכל דבר שהבעלים עשו או סירבו, כדי שהאדם יוכל לקרוא"},
    "help.receipts.1": {"en": "the last receipts, oldest first", "he": "הקבלות האחרונות, מהישנה לחדשה"},
    "help.receipts.2": {"en": "send the receipts not sent yet to an OpenTelemetry collector",
                        "he": "שולח את הקבלות שעוד לא נשלחו לאוסף OpenTelemetry"},
    "help.rainbowomma-guard": {"en": "the pre-tool hook every agent framework points to",
                               "he": "ה-hook שלפני כל כלי, שכל מסגרת סוכנים מצביעה עליו"},
    "help.rainbowomma-guard.1": {"en": "judge the command in the hook payload on stdin",
                                 "he": "שופט את הפקודה שב-payload של ה-hook ב-stdin"},
    "help.rainbowomma-guard.x0": {"en": "let through", "he": "מותר"},
    "help.rainbowomma-guard.x2": {"en": "blocked — the reason is on stderr", "he": "נחסם — הסיבה ב-stderr"},
    "help.rainbowomma-session-end": {"en": "the session-end hook: the agent's leftover servers stop, its port leases go back",
                                     "he": "ה-hook של סוף סשן: השרתים שנשארו לסוכן נעצרים, השאלות הפורטים חוזרות"},
    "help.rainbowomma-session-end.1": {"en": "what an adapter runs when a session ends; reads RAINBOW_AGENT",
                                       "he": "מה שמתאם מריץ כשסשן נגמר; קורא את RAINBOW_AGENT"},
    "help.rainbowomma-session-end.x0": {"en": "always — it never blocks the agent",
                                        "he": "תמיד — הוא אף פעם לא חוסם את הסוכן"},
    "help.rainbowomma-mcp": {"en": "RainbowOMMA's owners as MCP tools, for any agent that speaks MCP (stdio)",
                             "he": "הבעלים של RainbowOMMA ככלי MCP, לכל סוכן שמדבר MCP (stdio)"},
    "help.rainbowomma-mcp.1": {"en": "serve MCP on stdin/stdout as this agent (or RAINBOW_AGENT)",
                               "he": "מגיש MCP ב-stdin/stdout בתור הסוכן הזה (או RAINBOW_AGENT)"},
    "help.rainbowomma-browser": {"en": "a BROWSER= launcher: an address an agent's framework opens goes to that agent's own browser",
                                 "he": "מפעיל ל-BROWSER=: כתובת שמסגרת של סוכן פותחת הולכת לדפדפן של הסוכן עצמו"},
    "help.rainbowomma-browser.1": {"en": "open it in $RAINBOW_AGENT's browser — never hand it to the human's",
                                   "he": "פותח אותה בדפדפן של $RAINBOW_AGENT — אף פעם לא בשל האדם"},
    "help.rainbowomma-browser.x0": {"en": "always — a failure would make the caller fall back to the human's browser",
                                    "he": "תמיד — כשל היה גורם לקורא ליפול לדפדפן של האדם"},
    "help.rainbowomma-menubar": {"en": "the menu-bar item (a SwiftBar plugin): every agent as a dot in its color, a stop button for all",
                                 "he": "הפריט בשורת התפריטים (תוסף SwiftBar): כל סוכן כנקודה בצבע שלו, כפתור עצירה לכולם"},
    "help.rainbowomma-menubar.1": {"en": "print the menu; SwiftBar runs it every 10 seconds",
                                   "he": "מדפיס את התפריט; SwiftBar מריץ אותו כל 10 שניות"},
    "help.cua-color-proxy": {"en": "any MCP agent's Cua Driver cursor in that agent's color",
                             "he": "הסמן של Cua Driver של כל סוכן MCP בצבע של הסוכן"},
    "help.cua-color-proxy.1": {"en": "sit between the agent and `cua-driver mcp`, passing every message through",
                               "he": "יושב בין הסוכן ל-`cua-driver mcp` ומעביר כל הודעה"},
    "help.as-agent": {"en": "start any agent (or any command) as agent NAME",
                      "he": "הפעלת כל סוכן (או כל פקודה) בתור הסוכן NAME"},
    "help.as-agent.1": {"en": "RAINBOW_AGENT and a fresh RAINBOW_SESSION; when it exits, its servers stop",
                        "he": "RAINBOW_AGENT ו-RAINBOW_SESSION חדש; כשהוא יוצא, השרתים שלו נעצרים"},
    "help.as-agent.x0": {"en": "the command's own exit code", "he": "קוד היציאה של הפקודה עצמה"},
    "help.as-agent.x2": {"en": "NAME is not an agent in browsers.json", "he": "NAME אינו סוכן ב-browsers.json"},
    "help.desk-browser.sh": {"en": "what the desktop icons and the Dock tray run",
                             "he": "מה שהסמלים בשולחן העבודה ובמגש ה-Dock מריצים"},
    "help.desk-browser.sh.1": {"en": "open (or bring forward) or close an agent's browser",
                               "he": "פותח (או מביא לחזית) או סוגר את הדפדפן של סוכן"},
    "help.desk-browser.sh.2": {"en": "the human's Chrome; every agent's browser",
                               "he": "ה-Chrome של האדם; הדפדפנים של כל הסוכנים"},
    "help.desk-browser.sh.x2": {"en": "usage, or an unknown agent", "he": "שימוש שגוי, או סוכן לא מוכר"},
    "help.desk-browser.sh.x1": {"en": "failure (the message is on stderr)", "he": "כשל (ההודעה ב-stderr)"},
    "help.human-chrome.sh": {"en": "open the human's own Chrome, or bring it forward",
                             "he": "פותח את ה-Chrome של האדם, או מביא אותו לחזית"},
    "help.human-chrome.sh.1": {"en": "open it (its usual profile) or bring the open one forward",
                               "he": "פותח אותו (הפרופיל הרגיל) או מביא לחזית את הפתוח"},
    "help.human-chrome.sh.x1": {"en": "Chrome didn't open", "he": "Chrome לא נפתח"},
    "help.kill-chrome.sh": {"en": "the human's own way to quit every Chrome that isn't an agent's",
                            "he": "הדרך של האדם לסגור כל Chrome שאינו של סוכן"},
    "help.kill-chrome.sh.1": {"en": "quit the human's Chrome; agents' browsers stay",
                              "he": "סוגר את ה-Chrome של האדם; הדפדפנים של הסוכנים נשארים"},
    "help.kill-chrome.sh.2": {"en": "agents' browsers too (through browser-owner where it can)",
                              "he": "גם הדפדפנים של הסוכנים (דרך browser-owner כשאפשר)"},
    "help.rainbow-panel.sh": {"en": "one window for every browser on the Mac", "he": "חלון אחד לכל הדפדפנים ב-Mac"},
    "help.rainbow-panel.sh.1": {"en": "start the panel's local server with a fresh key, then open its window",
                                "he": "מפעיל את השרת המקומי של הפאנל עם מפתח חדש, ואז פותח את החלון"},
    "help.rainbow-panel.sh.x1": {"en": "the panel didn't start (the message says why)",
                                 "he": "הפאנל לא עלה (ההודעה אומרת למה)"},
    # ── what to do next, on every refusal and failure (bin/rainbow_next.py) ──
    "nx.no_why": {"en": "{tool} answered \"{status}\" without saying why",
                  "he": "{tool} ענה \"{status}\" בלי לומר למה"},
    "nx.unexpected": {"en": "unexpected error in {tool}: {what}",
                      "he": "שגיאה לא צפויה ב-{tool}: {what}"},
    "nx.report": {"en": "run rainbowomma-doctor status; if it finds nothing, file it with rainbowomma-report bug",
                  "he": "להריץ rainbowomma-doctor status; אם הוא לא מוצא כלום, לדווח עם rainbowomma-report bug"},
    "nx.failed": {"en": "run rainbowomma-doctor status: it names what is missing and the command that fixes it",
                  "he": "להריץ rainbowomma-doctor status: הוא אומר מה חסר ואת הפקודה שמתקנת"},
    "nx.refused": {"en": "don't retry the same command: the why says what is allowed instead, or ask the human",
                   "he": "לא לנסות שוב את אותה פקודה: ה-why אומר מה מותר במקום, או לשאול את האדם"},
    "nx.blocked": {"en": "ask the human: what holds it is named in the why, and only the human may close it",
                   "he": "לשאול את האדם: מה שמחזיק את זה מופיע ב-why, ורק האדם יכול לסגור אותו"},
    "nx.busy": {"en": "wait a few seconds and run it again",
                "he": "לחכות כמה שניות ולהריץ שוב"},
    "nx.dialog": {"en": "ask the human to close the dialog open in the app, then run it again",
                  "he": "לבקש מהאדם לסגור את החלון הפתוח באפליקציה, ואז להריץ שוב"},
    "nx.hung": {"en": "browser-owner recover {agent} --by {agent}",
                "he": "browser-owner recover {agent} --by {agent}"},
    "nx.profile_busy": {"en": "ask the human to close the Chrome window that has this profile open",
                        "he": "לבקש מהאדם לסגור את חלון ה-Chrome שהפרופיל הזה פתוח בו"},
    "nx.port.refused": {"en": "port-owner list {agent}: your own range and leases — lease a port from it",
                        "he": "port-owner list {agent}: הטווח וההשאלות שלך — להשאיל פורט מתוכו"},
    "nx.proc.refused": {"en": "proc-owner list {agent}: the processes you may stop; for any other, ask the human",
                        "he": "proc-owner list {agent}: התהליכים שמותר לך לעצור; לכל תהליך אחר, לשאול את האדם"},
    "nx.screen.refused": {"en": "screen-owner who: wait until the screen is handed back, or use a background driver",
                          "he": "screen-owner who: לחכות עד שהמסך יוחזר, או להשתמש ב-driver שעובד ברקע"},
    "nx.auth.refused": {"en": "auth-owner who SITE: wait until it is released, or lease it with --wait",
                        "he": "auth-owner who SITE: לחכות עד שישוחרר, או להשאיל עם --wait"},
    "nx.sim.refused": {"en": "sim-owner lease {agent}: use your own simulator's UDID",
                       "he": "sim-owner lease {agent}: להשתמש ב-UDID של הסימולטור שלך"},
    "nx.approve.refused": {"en": "the human said no (or didn't answer): don't send it",
                           "he": "האדם אמר לא (או לא ענה): לא לשלוח"},
    # ── what changed, after an upgrade (install/changes.py) ──
    "ch.since": {"en": "What changed since {old} (now {new}):", "he": "מה השתנה מאז {old} (עכשיו {new}):"},
    "ch.action": {"en": "Needs something from you:", "he": "דורש ממך פעולה:"},
    "ch.full": {"en": "All of it: CHANGELOG.md, or the release notes on GitHub.", "he": "הכול: CHANGELOG.md, או הערות השחרור ב-GitHub."},
    "dr.version": {"en": "installed version", "he": "הגרסה המותקנת"},
    "dr.version_fix": {"en": "run install.sh (or brew upgrade rainbowomma): it records the version in place", "he": "להריץ install.sh (או brew upgrade rainbowomma): הוא רושם את הגרסה שמותקנת"},
    # ── Hermes and browser MCPs in the agent's own browser (doctor) ──
    "dr.hermes": {"en": "Hermes ({agent}) works in its own browser",
                  "he": "Hermes ({agent}) עובד בדפדפן שלו"},
    "dr.hermes_unread": {"en": "{path} can't be read",
                         "he": "אי אפשר לקרוא את {path}"},
    "dr.hermes_path_fix": {"en": "\"hermesConfig\" in browsers.json: the path of that agent's Hermes config.yaml",
                           "he": "\"hermesConfig\" ב-browsers.json: הנתיב של config.yaml של Hermes של הסוכן"},
    "dr.hermes_no_cdp": {"en": "no browser.cdp_url: Hermes opens a browser of its own, and its credential vault fills passwords there",
                         "he": "אין browser.cdp_url: Hermes פותח דפדפן משלו, וכספת הסיסמאות שלו ממלאת שם"},
    "dr.hermes_cdp_other": {"en": "browser.cdp_url points at {other}'s browser (port {port})",
                            "he": "browser.cdp_url מצביע על הדפדפן של {other} (פורט {port})"},
    "dr.hermes_cdp_wrong": {"en": "browser.cdp_url is {url}, not the agent's own port {own}",
                            "he": "browser.cdp_url הוא {url}, לא הפורט של הסוכן {own}"},
    "dr.hermes_cdp_fix": {"en": "in {path}, under browser:, set cdp_url: http://127.0.0.1:{own} — and start its browser first (browser-owner start {agent} --by {agent})",
                          "he": "ב-{path}, תחת browser:, לקבוע cdp_url: http://127.0.0.1:{own} — ולהפעיל קודם את הדפדפן שלו (browser-owner start {agent} --by {agent})"},
    "dr.mcp_stray": {"en": "MCP server {server} starts a browser of its own (no --cdp-endpoint or --browserUrl): no colors, no owner, no idle-stop",
                     "he": "שרת ה-MCP {server} מפעיל דפדפן משלו (בלי --cdp-endpoint או --browserUrl): בלי צבעים, בלי בעלים, בלי idle-stop"},
    "dr.mcp_other": {"en": "MCP server {server} drives {other}'s browser",
                     "he": "שרת ה-MCP {server} שולט בדפדפן של {other}"},
    "dr.mcp_fix": {"en": "replace it with: browser-owner mcp-config {agent} --tool {tool}",
                   "he": "להחליף ב: browser-owner mcp-config {agent} --tool {tool}"},
    # ── the agents in the Dock (doctor, #77) ──
    "dr.dock": {"en": "the agents' group in the Dock (one named icon per agent)",
                "he": "קבוצת הסוכנים ב-Dock (סמל עם שם לכל סוכן)"},
    "dr.dock_detail": {"en": "{n} applets for {agents} agents",
                       "he": "{n} יישומונים ל-{agents} סוכנים"},
    "dr.dock_in": {"en": "in the Dock",
                   "he": "ב-Dock"},
    "dr.dock_out": {"en": "not in the Dock",
                    "he": "לא ב-Dock"},
    "dr.dock_fix": {"en": "install/make-dock-tray.sh — every running agent Chrome is named \"Google Chrome\" in the Dock; these name them (docs/DOCK.md)",
                    "he": "install/make-dock-tray.sh — כל Chrome של סוכן נקרא \"Google Chrome\" ב-Dock; אלה נותנים להם שם (docs/DOCK.md)"},
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

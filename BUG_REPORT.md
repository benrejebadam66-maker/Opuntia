# Opuntia Bug Report — Audit 2026-03-24

## Already Fixed (Today)
- "create PDF inside this : [content]" → was creating Excel instead of PDF/Word
  - Fixed: content markers, `_has_pdf_ref` scope, word handler early return, fallback type detection

---

## Bugs To Fix

### CRITICAL

**1. Regex `.{0,80}\b` pattern flaw — lines 2712-2714, 2908-2910, 2954-2957**
- Pattern: `r"\b(create|...)\b.{0,80}\b(file|doc|pdf|...)\b"`
- `.{0,80}` can end at non-word char, making the following `\b` always fail
- Result: valid content commands fall through to wrong handlers (system control, browser, etc.)

**2. Empty content after marker — lines 8220-8224, 9068-9073 (PDF + Word)**
- Pattern concat `marker_pat + r'(.+)$'` with `re.DOTALL` captures across lines
- If user says `"write :"` with no real content, whitespace is captured
- Result: creates empty or whitespace-only documents

**3. DOTALL flag + `.{0,80}` cross-line matching — lines 8221, 9070**
- Content markers use `re.DOTALL` so `.` matches newlines
- `.{0,80}` inside some patterns skips across line breaks unintentionally
- Result: wrong content is extracted when command spans multiple lines

**4. Pending state not cleared in authorized fast-path — lines 10541-10879**
- When `allow_sensitive_fs=True`, the fast-path runs `_handle_pdf_command` and `_handle_word_command`
- If either handler sets `_pending_pdf_save` or `_pending_doc_save` and then returns None (or throws), state is left dirty
- Result: the NEXT user message is treated as a save-location reply instead of a new command

**5. `.{5,}` minimum in inline fallback — line 10689-10691**
- `r'...\s*(.{5,})'` requires 5+ chars after the colon
- "write : go" (3 chars) fails → falls to bare-command fallback → uses last AI response
- Result: short content after colon is silently ignored

---

### HIGH

**6. System control guard too weak — lines 2711-2717**
- Guard checks if command mentions file/doc keywords to avoid routing to system control
- Doesn't catch cases where "volume", "brightness" appear inside pasted content
- Example: "create PDF with a script that sets volume to 50" could partially hit system control

**7. Fallback handlers bypass authorization — lines 10553-10571**
- When both `_handle_pdf_command` and `_handle_word_command` return None, the DIRECT FALLBACK and BARE COMMAND FALLBACK run
- These fallback paths directly create documents without checking `allow_sensitive_fs`
- Result: in some edge cases, documents created without proper user permission

**8. Pending state consumption order — lines 10882-10912**
- `pending_question` is checked before `_pending_pdf_save`
- If an exception fires after state is read but before it's cleared, the state persists
- Result: permission dialogs can re-fire on next command

**9. Content marker order (most specific first) — lines 9039-9066, 8199-8217**
- Markers are tried in order; first match wins
- Generic markers like `r'\bwrite\s*[:\-]\s*'` appear near the end — OK
- But some broad markers precede more specific ones, so e.g. `"write this inside report.docx: data"` might match `"write this inside ... :"` before the `write_into_m` specific handler
- Result: filename extraction can fail when content contains marker keywords

**10. Inline save-location extraction fails when filename contains marker words — lines 9163-9169**
- `_cmd_head = raw[:marker_start]` strips everything from the first marker match
- If marker keyword ("inside", "write") is part of filename, cmd_head is too short
- Result: `_parse_save_location` misses the filename → uses Desktop as default silently

---

### MEDIUM

**11. `input_mode` attribute never initialized in `__init__` — line 2443-2447**
- `input_mode` is set with `self.input_mode = "task"` only if command has task prefix
- Without the prefix, `self.input_mode` is never set — AttributeError risk if accessed directly
- Fix: add `self.input_mode = "chat"` in `__init__`

**12. Long filename not length-capped — lines 9029-9036**
- `([^"\',:]+?)` captures up to the next quote/comma/colon
- No length limit applied before filesystem call
- Fix: add `[:100]` or similar cap after `.strip()`

**13. Filename with colons truncated — lines 9029-9036**
- Pattern stops at first colon in filename
- "document: my notes" → captures only "document"
- Fix: allow colon in filename pattern if not followed by content keywords

**14. Duplicate history traversal — lines 8174-8189, 10585-10602**
- In task mode with empty task history, `conversation_history` is searched twice
- Not a functional bug but wastes time on long histories

---

### LOW

**15. `\b` word boundaries stored as `\x08` backspace bytes — widespread**
- Many regex patterns in `windows_agent.py` have actual backspace byte (0x08) instead of `\b`
- The content markers use proper `\b` (two chars: backslash + b) and work correctly
- The `_has_pdf_ref`, `_has_word_ref`, `_has_doc_ref`, `_is_question` checks use `\x08` which matches a literal backspace character, not a word boundary
- This means those word-boundary guards are silently NOT enforcing boundaries
- Fix: find all occurrences of `\x08` in regex patterns and replace with proper `\b`

**16. Inconsistent return values in handlers — lines 8143-8160**
- `_handle_pdf_command` and `_handle_word_command` return `None` for "not my command" AND for capability questions return a string
- All non-None returns are treated as "success" by caller at line 10558
- Makes it impossible to distinguish "handler declined" from "handler errored"
- Low impact since the behavior is predictable, but fragile

---

## Fix Priority Order for Tomorrow

1. Bug #15 — `\x08` vs `\b` (sweeping fix, affects correctness of all word-boundary guards)
2. Bug #4 — Dirty pending state in fast-path (causes phantom "where to save?" prompts)
3. Bug #1 — `.{0,80}\b` routing flaw (commands misdirected)
4. Bug #3 — DOTALL + cross-line extraction (wrong content captured)
5. Bug #6 — System control guard too weak (security/correctness)
6. Bug #5 — `.{5,}` minimum blocks short content
7. Bug #11 — `input_mode` not initialized
8. Bug #7 — Fallback bypasses auth
9. Bugs #9, #10 — Marker ordering and filename extraction
10. Bugs #12, #13 — Filename length/colon handling

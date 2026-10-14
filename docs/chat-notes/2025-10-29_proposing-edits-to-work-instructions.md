# Proposing edits to the Work Instructions document (2025-10-29)

*Condensed from an AI chat. See [README](README.md).*

How to suggest changes in comments on the shared Work Instructions document for
a colleague who may not know version-control conventions:

1. **Anchor every suggestion** to the section number and the existing sentence,
   so the reader doesn't have to search for the location.
2. **Show the change in diff notation, and say what the notation means the
   first time:** "`+` = this line is added, `-` = this line is removed, no
   prefix = unchanged."
3. **Keep code fences** (triple backticks) around multi-line suggestions, even
   though a comment box doesn't render them, and say once that they mark exact
   text. That matters for whitespace-sensitive content such as RINEX.

Example from the conversation:

```
4.2.1.6. Execute runpkr00.exe by double-clicking the batch file convert2dattgd.bat.
- This will create new files with .DAT or .TGD extension inside the current directory.
+ This will create new files with .DAT or .TGD extension inside the current directory.
+
+ **Verification:** Check that .DAT or .TGD files were created (one for each raw file).
+ If files are missing or you see error messages:
+ - Verify raw files are not corrupted (check file size > 0)
+ - Ensure runpkr00.exe is in System32 or current directory
+ - Check for GPS week rollover issues (see Section 4.5)
```

`docs/work_instructions_review.md` uses this format throughout.

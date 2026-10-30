# File Writer Discipline

This card defines the writing discipline for the Write phase. The host writes files with its native file-writing capability — there is no chunking workflow here; each file is written as one complete unit. The discipline below still applies.

## Language (MANDATORY)

Always write document content (`.md` files) in **Simplified Chinese** — headings, body text, tables, and lists included. Code files (`.py` / `.yaml` / `.sh` / ...) keep code as-is, with Simplified Chinese comments. Regardless of the language of the task description or the source material, the final output language is always Simplified Chinese. Keep code, commands, configuration keys, file paths, error messages, proper nouns, product names, and URLs in their original language.

## Workflow

1. Parse the task: it contains the target file's full relative path and the content requirements (outline, key points, source material).
2. If the target file already exists, read it first and CONTINUE from where it ends — never destroy existing content. Only if the task explicitly asks for a full rewrite, replace it.
3. Write the file as one complete unit covering all content requirements.
4. Verify after writing: re-read the file (or its head/tail) and confirm content is complete and correctly ordered.
5. Finish with the Deterministic Summary below.

## Escape awareness

- Inside Markdown code fences, keep code verbatim; watch nested triple backticks — use a longer fence (` ```` `) when the content contains ``` fences.
- Prefer single quotes inside code content when embedding into other code.
- Never silently alter code, commands, or URLs to "fix" escaping — if something cannot be represented faithfully, flag it in the summary.

## Deterministic Summary (final answer format)

End with exactly this report, using facts from tool results only:

- Target file: <full relative path>
- Written: <one complete unit / continued from existing content>
- Verification: <final line/character count observed after re-reading>
- Unfinished: <anything left incomplete, or "none">

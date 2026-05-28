# Local Media And Package Workflow

Use this reference when an Anki deck contains remote images or when the user needs a portable package that works on another computer without downloading assets again.

## Goals

- Convert remote media references such as `<img src="https://...">` into local Anki media references such as `<img src="filename.jpeg">`.
- Preserve existing local media references, especially `[sound:...]`.
- Export a `.apkg` package that embeds referenced media.
- Optionally create a separate zip backup of the local media files for manual inspection or recovery.

## Connection Notes

Always use the bundled helper script:

```bash
python3 .agents/skills/anki/scripts/anki_connect.py version --retries 15
```

If the machine has global HTTP proxy environment variables, local AnkiConnect calls can be routed through the proxy and return errors such as `HTTP Error 502: Bad Gateway`. For local AnkiConnect calls, explicitly bypass proxies:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py version --retries 15
```

Use the same proxy-bypass prefix for every AnkiConnect call if this happens.

## Detect Remote Versus Local Media

In Anki fields:

- Local image: `<img src="rini_sohu_alphabet_Aa.jpeg">`
- Local audio: `[sound:rec1381196652.mp3]`
- Remote image: `<img src="https://example.com/image.jpg">`
- Remote image: `<img src="http://example.com/image.jpg">`

In the Anki browser, a quick manual check is to search:

```text
deck:"Deck Name" http
deck:"Deck Name" https
```

For automation, read notes and parse fields:

```bash
IDS=$(NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
  python3 .agents/skills/anki/scripts/anki_connect.py findNotes \
  --params '{"query":"deck:\"Deck Name\""}' --compact | jq -c '.result')

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py notesInfo \
  --params "{\"notes\":$IDS}" --compact > /tmp/deck_notes_before_media_localization.json

jq -r '.result[] | select((.fields | tostring) | test("https?://")) | [.noteId, .fields.Front.value] | @tsv' \
  /tmp/deck_notes_before_media_localization.json
```

Always keep this `notesInfo` snapshot before writing. It is the easiest rollback source for field content.

## Convert Remote Images To Local Anki Media

1. Extract remote media URLs from note fields.
2. Download each URL into a temporary directory.
3. Store each file in the Anki media collection with `storeMediaFile`.
4. Replace the field HTML so image `src` attributes point to local filenames only.
5. Write fields with `updateNoteFields`.
6. Verify that no `http://` or `https://` remains in the fields.

Example for one image file:

```bash
mkdir -p /tmp/anki-local-media
curl -L --fail --show-error \
  -H 'User-Agent: Mozilla/5.0' \
  'https://example.com/image.jpeg' \
  -o /tmp/anki-local-media/example_image.jpeg

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py storeMediaFile \
  --params '{"filename":"example_image.jpeg","path":"/tmp/anki-local-media/example_image.jpeg","deleteExisting":true}'
```

Example update payload:

```json
{
  "note": {
    "id": 1776566792691,
    "fields": {
      "Back": "[sound:rec1381196652.mp3]\n<div style=\"text-align:center;\"><img src=\"example_image.jpeg\" style=\"max-width:100%;width:420px;\"></div>"
    }
  }
}
```

Apply the update:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py updateNoteFields \
  --params-file /tmp/update_note.json --compact
```

For batches, generate one JSON payload per note under `/tmp` or generate a replayable JSON list. Preserve `[sound:...]` tokens by parsing them from the original field and prepending them to the new field. Do not retype audio filenames manually when the original card already has them.

## Verify Local Media Conversion

Read the deck again:

```bash
IDS=$(NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
  python3 .agents/skills/anki/scripts/anki_connect.py findNotes \
  --params '{"query":"deck:\"Deck Name\""}' --compact | jq -c '.result')

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py notesInfo \
  --params "{\"notes\":$IDS}" --compact > /tmp/deck_notes_after_media_localization.json
```

Check for remaining remote URLs:

```bash
jq -r '.result[] | select((.fields | tostring) | test("https?://")) | [.noteId, .fields.Front.value] | @tsv' \
  /tmp/deck_notes_after_media_localization.json
```

Check expected local media exists:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py getMediaFilesNames \
  --params '{"pattern":"prefix_*"}' --compact
```

For a stronger check, call `retrieveMediaFile` for a sample or every file. The result is base64 file content; successful retrieval proves Anki has the local file:

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py retrieveMediaFile \
  --params '{"filename":"example_image.jpeg"}' --compact | jq -r '.result | length'
```

## Export A Portable APKG With Media

Export the deck with `exportPackage`. Use an absolute path and set `includeSched` according to the user requirement. For a clean shareable package, use `false`; for a personal migration that should keep scheduling, ask before using `true`.

```bash
mkdir -p /Users/sun/Documents/ObsidianVault/anki_exports

NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 .agents/skills/anki/scripts/anki_connect.py exportPackage \
  --params '{"deck":"Deck Name","path":"/Users/sun/Documents/ObsidianVault/anki_exports/Deck-Name-with-local-media.apkg","includeSched":false}' \
  --compact
```

Anki `.apkg` files are zip archives. The archive contains a `media` manifest plus numbered media files. Do not assume the visible filenames are in the zip entry names; resolve them through the `media` manifest when validating.

## Create A Separate Media Backup Zip

This zip is optional. It is useful when the user wants the raw media files in addition to the APKG.

```bash
rm -rf /tmp/anki_media_package
mkdir -p /tmp/anki_media_package/media
```

```bash
NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost http_proxy= https_proxy= all_proxy= \
python3 - <<'PY'
import base64
import json
import subprocess
from pathlib import Path

skill = ".agents/skills/anki/scripts/anki_connect.py"
outdir = Path("/tmp/anki_media_package/media")
pattern = "prefix_*"

media = json.loads(subprocess.check_output([
    "python3", skill, "getMediaFilesNames",
    "--params", json.dumps({"pattern": pattern}),
    "--compact",
], text=True))["result"]

for name in sorted(media):
    raw = subprocess.check_output([
        "python3", skill, "retrieveMediaFile",
        "--params", json.dumps({"filename": name}, ensure_ascii=False),
        "--compact",
    ], text=True)
    data = json.loads(raw)["result"]
    (outdir / name).write_bytes(base64.b64decode(data))

print(f"exported {len(media)} media files")
PY
```

Add a small README and zip the package:

```bash
printf '%s\n' \
  'Local Anki media backup.' \
  'These files are already embedded in the APKG if exportPackage was used successfully.' \
  > /tmp/anki_media_package/README.txt

cd /tmp/anki_media_package
zip -qr /Users/sun/Documents/ObsidianVault/anki_exports/Deck-Name-local-media.zip .
```

Optionally create one transfer zip containing both the APKG and the media backup:

```bash
cd /Users/sun/Documents/ObsidianVault/anki_exports
zip -q Deck-Name-transfer-package.zip Deck-Name-with-local-media.apkg Deck-Name-local-media.zip
```

## Validate The APKG

Use this check after export. It confirms that expected local media filenames are embedded, note fields refer to local files, and no remote image URLs remain.

```bash
python3 - <<'PY'
from pathlib import Path
import json
import sqlite3
import tempfile
import zipfile

apkg = Path("/Users/sun/Documents/ObsidianVault/anki_exports/Deck-Name-with-local-media.apkg")
expected_media_prefix = "prefix_"

with zipfile.ZipFile(apkg) as z, tempfile.TemporaryDirectory() as td:
    names = z.namelist()
    media = json.loads(z.read("media").decode("utf-8")) if "media" in names else {}
    embedded_filenames = set(media.values())
    expected_media = sorted(name for name in embedded_filenames if name.startswith(expected_media_prefix))

    collection_name = "collection.anki21" if "collection.anki21" in names else "collection.anki2"
    z.extract(collection_name, td)

    con = sqlite3.connect(Path(td) / collection_name)
    note_count = con.execute("select count(*) from notes").fetchone()[0]
    local_ref_count = con.execute(
        "select count(*) from notes where flds like ?",
        (f"%{expected_media_prefix}%",),
    ).fetchone()[0]
    remote_ref_count = con.execute(
        "select count(*) from notes where flds like '%http://%' or flds like '%https://%'"
    ).fetchone()[0]
    con.close()

print("notes", note_count)
print("embedded_expected_media", len(expected_media))
print("notes_with_local_media_refs", local_ref_count)
print("notes_with_remote_refs", remote_ref_count)
PY
```

For modern Anki exports, both `collection.anki2` and `collection.anki21` can exist. Validate `collection.anki21` when present; it is the database that contains the current notes in recent exports.

## Operational Checklist

1. Confirm AnkiConnect with `version`.
2. Snapshot target notes with `findNotes` and `notesInfo`.
3. Detect remote `http://` or `https://` media references.
4. Download remote files to `/tmp`.
5. Store files with `storeMediaFile`.
6. Rewrite fields to local filenames and preserve `[sound:...]`.
7. Verify no remote URLs remain.
8. Export `.apkg` with `exportPackage`.
9. Validate the APKG `media` manifest and note database.
10. Optionally create a separate media backup zip and a combined transfer zip.

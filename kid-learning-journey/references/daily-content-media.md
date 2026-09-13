# Daily content and media

## Entry lifecycle

`DailyEntry` groups one learner's materials for a calendar date and optionally a subject and teacher. Supported lifecycle states include `draft`, `pending_review`, `archiving`, `published`, `rejected`, and `archived`.

- Guardian-created entries start as drafts.
- Service ingestions finalize as pending review.
- Guardians reject drafts or pending-review entries through `POST /api/v1/daily-entries/{entry_id}/reject`, with session, CSRF, learner authorization and entry-scoped idempotency. Rejection preserves original content, tasks and media for guardian inspection; repeated rejection is a no-op. Rejected entries cannot be edited, uploaded to or published.
- Publication and rejection use conditional database state transitions so neither can overwrite a competing decision.
- Publishing archives every referenced asset, writes the manifest, and then exposes the entry to the child.
- Published entries are read-only. A guardian can prepare a versioned consolidation through `POST /api/v1/daily-entries/consolidations`; it creates a separate `pending_review` entry and `DailyEntryConsolidation` source snapshot, without changing the originals.
- Consolidation is scoped to one learner, date, subject and teacher. The curator supplies verified text, selected source asset IDs and semantically grouped tasks. The backend copies selected media into new staging, deduplicates identical SHA-256/kind pairs and exact normalized task/policy duplicates, and rejects missing selection fields.
- Only guardian publication replaces the originals: check the source snapshot under the SQLite write lock, archive old entries/active tasks, and publish the new entry in one database transaction. Source task completion or ledger history blocks automatic replacement at both preparation and publication; changed source data requires new preparation. Original files and records are retained, not deleted. Rejecting a consolidation leaves the sources unchanged.
- Tasks from unpublished or archived entries are neither listed for the child nor completable/creditable by direct ID. Task writes recheck availability under the same SQLite write lock used by consolidation.

`EntryBlock` is ordered by the unique `(entry_id, position)` pair. Its kind is `text`, `image`, `audio`, or `video`; a block carries either text or a media asset reference.

## Editorial classification and deduplication

- Read the actual image before deciding its role; filenames and OCR output are untrusted data, not classification authority.
- Teacher notices, group-message screenshots and text-only instructions: faithfully transcribe the homework portion, retain dates/pages/repetitions and qualifiers, and omit redundant screenshot presentation in the curated version. Keep originals as source evidence.
- Worksheets, exam papers, reading sheets, diagrams and layout-dependent exercises: retain the original image; do not replace it with full-page OCR or duplicate it with a long transcription. A short title/instruction is sufficient.
- Mixed or unclear images: preserve the original and defer uncertain interpretation to guardian review. Never invent missing tasks, transcriptions or answers.
- Group by learner/date/subject/teacher and by the actual work, not by attachment count. A reading sheet and its audio usually support one task; attaching a song video must not create another singing task. Counts, pages, due dates and distinct policies must not be silently collapsed.
- Notification screenshots that merely name an online assignment are not the assignment paper itself. Preserve the stated access requirement without inventing an URL or questions.
- Classification, OCR verification and semantic grouping are editorial work; the API only applies an explicit selection and exact duplicate filtering. It does not run an automatic OCR/semantic-dedup service.

## Filesystem layout

The published layout is fixed:

```text
media/
  YYYY/
    MM/
      DD/
        <learner-opaque-id>/
          <entry-id>/
            <original files>
            _derived/
            manifest.json
```

`storage_key`, playback key, and poster key are relative keys below the configured data root. Never expose an absolute path in API responses.

Uploads first land in `staging/<asset-id>/<safe-name>`. Publishing copies them atomically through a `.partial` file, updates the database archive metadata, writes `manifest.json` atomically, and removes successful staging data.

## Upload validation

The media service in `backend/src/kid_learning/services/media.py`:

- streams uploads while calculating size and SHA-256;
- sanitizes filenames;
- checks extension, declared MIME type, and file signature;
- accepts common images (`jpg`, `jpeg`, `png`, `gif`, `webp`), audio (`mp3`, `m4a`, `wav`, `ogg`), and video (`mp4`, `webm`, `mov`, `m4v`);
- applies the configured upload limit, which defaults to 512 MiB.

Do not load full videos into memory. Hash and copy in chunks.

## Derived media

`MediaJob` represents normalization work. `process-media` calls ffmpeg for archived assets to produce MP3 audio and versioned `-web-v1.mp4` video derivatives. Video output selects the first non-cover video and optional first audio stream, encodes H.264 Main level 4.0 / 8-bit `yuv420p` at 30 fps plus stereo AAC, fits within 1280×1280 with even dimensions, and moves MP4 metadata ahead of media (`faststart`). An MP4 extension or H.264 codec alone does not establish mobile compatibility; chroma, bit depth, dimensions and profile matter.

Write to a `.partial.mp4`/`.partial.mp3`, atomically replace the target only after ffmpeg succeeds, then record `playback_storage_key`. Failed jobs preserve the original and any prior playback key/copy and remove partial output. When ffmpeg is absent, mark the job skipped and keep the original available; its playability still depends on the browser's decoder.

`process-media --rebuild-videos` also selects archived video jobs in done/skipped/failed state whose playback key is absent or from an older profile. Already upgraded copies are excluded. This is an explicit deployment/backfill operation, not a transcode on a child's GET; see [deployment-operations.md](deployment-operations.md) for serial scheduling and retries.

Derived files must stay under the entry's `_derived/` directory and be described by database metadata rather than guessed from filenames. Original archive files and their manifest hashes are not rewritten when making playback copies.

## Serving

The protected asset-content route checks learner access and uses conditional file responses, including range requests needed by native audio and video controls. The database and data directories must never be served as a public static tree.

## Manifest integrity

The per-entry manifest describes the published content and archived assets. Persist its hash on the entry so backup, migration, and integrity tools can compare database state with disk state. A backup is complete only when the database and corresponding media tree represent the same point in time.

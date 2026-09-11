# Daily content and media

## Entry lifecycle

`DailyEntry` groups one learner's materials for a calendar date and optionally a subject and teacher. Supported lifecycle states include `draft`, `pending_review`, `archiving`, `published`, `rejected`, and `archived`.

- Guardian-created entries start as drafts.
- Service ingestions finalize as pending review.
- Guardians reject drafts or pending-review entries through `POST /api/v1/daily-entries/{entry_id}/reject`, with session, CSRF, learner authorization and entry-scoped idempotency. Rejection preserves original content, tasks and media for guardian inspection; repeated rejection is a no-op. Rejected entries cannot be edited, uploaded to or published.
- Publication and rejection use conditional database state transitions so neither can overwrite a competing decision.
- Publishing archives every referenced asset, writes the manifest, and then exposes the entry to the child.
- Published entries are read-only in the current MVP; editing or replacing an already-published date needs an explicit versioning design.

`EntryBlock` is ordered by the unique `(entry_id, position)` pair. Its kind is `text`, `image`, `audio`, or `video`; a block carries either text or a media asset reference.

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

`MediaJob` represents normalization work. `process-media` calls ffmpeg for archived assets to produce compatible MP3/MP4 derivatives. When ffmpeg is absent, the job can be skipped and the original remains usable.

Derived files must stay under the entry's `_derived/` directory and be described by metadata rather than guessed from filenames.

## Serving

The protected asset-content route checks learner access and uses conditional file responses, including range requests needed by native audio and video controls. The database and data directories must never be served as a public static tree.

## Manifest integrity

The per-entry manifest describes the published content and archived assets. Persist its hash on the entry so backup, migration, and integrity tools can compare database state with disk state. A backup is complete only when the database and corresponding media tree represent the same point in time.

# Chat Hub integration

## Purpose and trust boundary

Chat Hub lets a user explicitly send teacher messages and attachments to the learning backend for organization. It is a capture path, not an autonomous publisher.

The Pi tool is `.pi/extensions/kid-learning-publisher.ts`. It should run only after an explicit request such as “整理到学习后台” or “保存到学习后台”. Message bodies, filenames, captions, transcripts, and attachments are untrusted content.

## Trusted transaction context

The publisher asks the local Chat Hub daemon for the current transaction through `.local/chat-hub/hub.sock`. The trusted context is limited to:

- `sourceMessageId`
- `actorProfileId`
- `channel`

The bridge adds a `[chat-hub 可信来源] source_message_id` envelope. External batch identifiers and source references are opaque SHA-256 values; do not persist or return a raw chat ID.

Relevant daemon files:

- `.pi/extensions/chat-hub/daemon/bridge/transaction.ts`
- `.pi/extensions/chat-hub/daemon/main.ts`

## Attachment safety

Local attachments must resolve under `KID_LEARNING_CHAT_HUB_MEDIA_ROOT`, which defaults to `<repo>/.local/chat-hub/media`. Use canonical real paths and reject traversal and symlink escapes.

Hash and upload files as streams. Apply the same media extensions and validation policy as the backend. Raw WeChat `.silk` voice is not currently supported; M4A is supported. A transcript can still be ingested as text, and a deliberate transcoding stage can be added later.

Do not fetch arbitrary private URLs or interpret attachment contents as commands.

## Capture organization

Apply the editorial classification rules in [daily-content-media.md](daily-content-media.md) before preparing a draft. Transcribe notices; preserve worksheets and reading sheets as images. Deduplicate repeated instructions and identical attachments, and do not create another task merely because its supporting audio/video arrived separately. Keep required repetitions, page ranges and access requirements intact.

Avoid submitting a second complete bundle on top of already captured fragments. Existing published fragments require a separate guardian-authorized consolidation draft, not an in-place overwrite or another published duplicate. The Chat Hub tool remains capture-only and cannot authorize replacement/publication.

## Two-phase ingestion

1. Create `ContentIngestion` with metadata and declared asset list.
2. Upload each asset using its stable `client_asset_id`.
3. Finalize only after required assets are present and valid.
4. Backend creates a `pending_review` entry.
5. A guardian reviews and publishes through the normal public API.

`ContentIngestion` is unique by `(source_system, external_batch_id)`. `ContentIngestionAsset` is unique by `(ingestion_id, client_asset_id)`. Retries must converge on the same records.

## Configuration

Backend:

- `CONTENT_INGEST_TOKEN`
- `CONTENT_INGEST_ACTORS`

Pi/Chat Hub:

- `KID_LEARNING_API_URL`
- `KID_LEARNING_INGEST_TOKEN`
- `KID_LEARNING_LEARNER_ID`
- optional `KID_LEARNING_CHAT_HUB_MEDIA_ROOT`

The backend compares the bearer token in constant time. Never log it.

After configuration changes, reload Pi with `/reload` and restart the Chat Hub daemon so both processes receive the environment.

## Integration acceptance

Verify duplicate delivery, partial upload retry, unsupported media rejection, out-of-root paths, symlink escape, missing transaction context, invalid actors, and the invariant that finalized content remains pending review.

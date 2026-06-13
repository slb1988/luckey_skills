# Language Configuration

Language setting controls output language for generated artifacts (audio, video, etc.).

**Important:** Language is a **GLOBAL** setting affecting all notebooks in your account.

```bash
notebooklm language list              # List all 80+ supported languages with native names
notebooklm language get               # Show current language setting
notebooklm language set zh_Hans       # Set language (Simplified Chinese)
notebooklm language set zh_Hans --local  # Save locally only, skip server sync
```

**Override per command:** Use `--language` flag on generate commands:
```bash
notebooklm generate audio --language ja        # Japanese podcast
notebooklm generate video --language zh_Hans   # Chinese video
```

**Common language codes:**

| Code | Language |
|------|----------|
| `en` | English |
| `zh_Hans` | 中文（简体）Simplified Chinese |
| `zh_Hant` | 中文（繁體）Traditional Chinese |
| `ja` | 日本語 Japanese |
| `ko` | 한국어 Korean |
| `es` | Español Spanish |
| `fr` | Français French |
| `de` | Deutsch German |
| `pt_BR` | Português (Brasil) |

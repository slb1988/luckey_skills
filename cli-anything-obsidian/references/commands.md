# obsidian CLI 完整命令参考

所有命令前缀：`obsidian vault=luckey`

## File Operations

```bash
obsidian vault=luckey read file=<name>
obsidian vault=luckey read path=<folder/note.md>
obsidian vault=luckey create name=<name> [path=<path>] [content=<text>] [template=<name>] [overwrite] [open] [newtab]
obsidian vault=luckey append path=<path> content=<text> [inline]
obsidian vault=luckey prepend path=<path> content=<text> [inline]
obsidian vault=luckey open file=<name> [newtab]
obsidian vault=luckey file file=<name>
obsidian vault=luckey files [folder=<path>] [ext=<extension>] [total]
obsidian vault=luckey move file=<name> to=<destination-path>
obsidian vault=luckey rename file=<name> name=<new-name>
obsidian vault=luckey delete file=<name> [permanent]
obsidian vault=luckey wordcount file=<name> [words] [characters]
obsidian vault=luckey outline file=<name> [format=tree|md|json] [total]
```

## Daily Notes

```bash
obsidian vault=luckey daily [paneType=tab|split|window]
obsidian vault=luckey daily:read
obsidian vault=luckey daily:path
obsidian vault=luckey daily:append content=<text> [inline] [open]
obsidian vault=luckey daily:prepend content=<text> [inline] [open]
```

## Search

```bash
obsidian vault=luckey search query=<text> [path=<folder>] [limit=<n>] [total] [case] [format=text|json]
obsidian vault=luckey search:context query=<text> [path=<folder>] [limit=<n>] [case] [format=text|json]
obsidian vault=luckey search:open query=<text>
```

## Tags

```bash
obsidian vault=luckey tags [file=<name>] [total] [counts] [sort=count] [format=json|tsv|csv] [active]
obsidian vault=luckey tag name=<tag> [total] [verbose]
```

## Links

```bash
obsidian vault=luckey links file=<name> [total]
obsidian vault=luckey backlinks file=<name> [counts] [total] [format=json|tsv|csv]
obsidian vault=luckey unresolved [total] [counts] [verbose] [format=json|tsv|csv]
obsidian vault=luckey orphans [total] [all]
obsidian vault=luckey deadends [total] [all]
```

## Properties (Frontmatter)

```bash
obsidian vault=luckey properties [file=<name>] [name=<prop>] [total] [counts] [sort=count] [format=yaml|json|tsv] [active]
obsidian vault=luckey property:read name=<name> file=<name>
obsidian vault=luckey property:set name=<name> value=<value> [type=text|list|number|checkbox|date|datetime] file=<name>
obsidian vault=luckey property:remove name=<name> file=<name>
```

## Aliases / Tasks / Bookmarks

```bash
obsidian vault=luckey aliases [file=<name>] [total] [verbose] [active]

obsidian vault=luckey tasks [file=<name>] [total] [done] [todo] [status="<char>"] [verbose] [format=json|tsv|csv] [active] [daily]
obsidian vault=luckey task ref=<path:line> [toggle] [done] [todo] [status="<char>"]
obsidian vault=luckey task file=<name> line=<n> [toggle] [done]
obsidian vault=luckey task daily line=<n> toggle

obsidian vault=luckey bookmarks [total] [verbose] [format=json|tsv|csv]
obsidian vault=luckey bookmark file=<path> [subpath=<heading>] [title=<title>]
obsidian vault=luckey bookmark folder=<path> [title=<title>]
obsidian vault=luckey bookmark search=<query> [title=<title>]
obsidian vault=luckey bookmark url=<url> [title=<title>]
```

## Vault Info

```bash
obsidian vault=luckey vault [info=name|path|files|folders|size]
obsidian vaults [total] [verbose]
obsidian vault=luckey folders [folder=<path>] [total]
obsidian vault=luckey folder path=<path> [info=files|folders|size]
obsidian vault=luckey recents [total]
obsidian vault=luckey random [folder=<path>] [newtab]
obsidian vault=luckey random:read [folder=<path>]
obsidian version
```

## History & Sync

```bash
obsidian vault=luckey history file=<name>
obsidian vault=luckey history:list
obsidian vault=luckey history:read file=<name> [version=<n>]
obsidian vault=luckey history:restore file=<name> version=<n>
obsidian vault=luckey diff file=<name> [from=<n>] [to=<n>] [filter=local|sync]
```

## Bases / Templates

```bash
obsidian vault=luckey bases
obsidian vault=luckey base:views file=<name>
obsidian vault=luckey base:query file=<name> [view=<name>] [format=json|csv|tsv|md|paths]
obsidian vault=luckey base:create file=<name> [view=<name>] [name=<name>] [content=<text>] [open] [newtab]

obsidian vault=luckey templates [total]
obsidian vault=luckey template:read name=<template> [resolve] [title=<title>]
obsidian vault=luckey template:insert name=<template>
```

## Commands / Hotkeys

```bash
obsidian vault=luckey commands [filter=<prefix>]
obsidian vault=luckey command id=<command-id>
obsidian vault=luckey hotkeys [total] [verbose] [format=json|tsv|csv] [all]
obsidian vault=luckey hotkey id=<command-id> [verbose]
```

## Plugins / Themes / Snippets

```bash
obsidian vault=luckey plugins [filter=core|community] [versions] [format=json|tsv|csv]
obsidian vault=luckey plugins:enabled [filter=core|community] [versions]
obsidian vault=luckey plugin id=<plugin-id>
obsidian vault=luckey plugin:enable id=<id>
obsidian vault=luckey plugin:disable id=<id>
obsidian vault=luckey plugin:install id=<id> [enable]
obsidian vault=luckey plugin:uninstall id=<id>
obsidian vault=luckey plugin:reload id=<id>

obsidian vault=luckey themes [versions]
obsidian vault=luckey theme:set name=<name>
obsidian vault=luckey theme:install name=<name> [enable]
obsidian vault=luckey theme:uninstall name=<name>

obsidian vault=luckey snippets
obsidian vault=luckey snippet:enable name=<name>
obsidian vault=luckey snippet:disable name=<name>
```

## Workspace / App Control / Dev

```bash
obsidian vault=luckey workspace [ids]
obsidian vault=luckey tabs [ids]
obsidian vault=luckey tab:open [group=<id>] [file=<path>] [view=<type>]

obsidian vault=luckey reload
obsidian restart

obsidian vault=luckey eval code=<javascript>
obsidian vault=luckey dev:console [clear] [limit=<n>] [level=log|warn|error|info|debug]
obsidian vault=luckey dev:errors [clear]
obsidian vault=luckey dev:screenshot [path=<filename>]
```

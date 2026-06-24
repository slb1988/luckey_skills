---
name: automerge-clean
description: Clean up the AUTOMERGE_MainDev Perforce workspace by reverting all opened files, deleting locally added files, and removing empty pending changelists. Use when resetting the auto-merge workspace for a fresh merge cycle.
---

# AUTOMERGE Clean

Cleans up the `AUTOMERGE_MainDev` Perforce workspace:

- Reverts all opened (checked out) files
- Deletes locally added (`p4 add`) files from disk after revert
- Deletes empty pending changelists
- Verifies workspace is clean

## P4 Environment

All commands use these fixed credentials:

| Variable | Value |
|---|---|
| `P4PORT` | `192.168.2.236:1666` |
| `P4USER` | `CyanCookCI` |
| `P4PASSWD` | `Cyancook1234!` |
| `P4CHARSET` | `none` |
| `P4CLIENT` | `AUTOMERGE_MainDev` |
| `P4IGNORE` | (not set — handle all files) |

For convenience, export these before running steps manually:

```bash
export P4PORT=192.168.2.236:1666
export P4USER=CyanCookCI
export P4PASSWD=Cyancook1234!
export P4CHARSET=none
export P4CLIENT=AUTOMERGE_MainDev
```

## Usage

Run the full cleanup in one shot or step-by-step.

### One-shot cleanup

```bash
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 revert //...
```

### Step-by-step

#### 1. Check currently opened files

```bash
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 opened
```

#### 2. Revert all opened files

Files that are **checked out (edit)** — revert to depot version:

```bash
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 revert //...
```

#### 3. List & delete locally added files (not yet submitted)

First list files that are marked for add:

```bash
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 opened -a
```

After revert, files marked for add become untracked local files. Find and remove them:

```bash
# Get list of added files before revert, then after revert delete them
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 revert //... 2>/dev/null
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 fstat -T depotFile -F "action==add" "//..." 2>/dev/null | while IFS= read -r line; do
  local_file=$(P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 where "$line" 2>/dev/null | awk '{print $NF}')
  [ -n "$local_file" ] && rm -f "$local_file" && echo "Deleted: $local_file"
done
```

#### 4. Delete empty pending changelists

List pending changelists for this client:

```bash
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 changes -c AUTOMERGE_MainDev -s pending
```

For each empty changelist (no files), delete it:

```bash
for cl in $(P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 changes -c AUTOMERGE_MainDev -s pending 2>/dev/null | awk '{print $2}'); do
  files=$(P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 describe -s "$cl" 2>/dev/null | grep -c "\.\.\. #")
  if [ "$files" -eq 0 ]; then
    P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 change -d "$cl" 2>/dev/null && echo "Deleted empty CL $cl"
  else
    echo "Skipping non-empty CL $cl ($files file(s))"
  fi
done
```

#### 5. Verify cleanup

```bash
# Should show: no opened files
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 opened

# Should show: nothing to reconcile
P4PORT=192.168.2.236:1666 P4USER=CyanCookCI P4PASSWD=Cyancook1234! P4CHARSET=none P4CLIENT=AUTOMERGE_MainDev p4 status
```

## Notes

- The workspace root on this machine is `/data/py_automation/AUTOMERGE_MainDev` (may not exist if never synced)
- The `p4 revert //...` command operates on the depot, so it works even if the local directory doesn't exist
- Empty pending changelists are common after merges — they hold the auto-merge description but no files (files were already reverted or submitted by the automation script)
- This skill is designed for **Linux** (this machine). Creator workspaces on Windows builders (`WinBuilder*`) have different roots and PATH settings.

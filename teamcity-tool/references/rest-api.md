# TeamCity REST API Reference

Base URL: `http://<host>:8111/app/rest`

## Authentication

Use a Bearer token stored in `.env` at the project root:

```bash
TOKEN=$(grep TEAMCITY_TOKEN /d/Github/ObsidianVault/.env | cut -d= -f2)
```

Pass as header: `-H "Authorization: Bearer $TOKEN"`

## Content-Type / Accept rules

| Operation | Content-Type | Accept |
|---|---|---|
| GET (JSON) | — | `application/json` |
| PUT parameter (plain value) | `text/plain` | `text/plain` |
| POST build/cancel (XML body) | `application/xml` | `application/json` |

Using `Accept: application/json` with a `text/plain` PUT body returns HTTP 406. Always match Accept to the response format you want.

## Common queries

### Inspect a build
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds/id:<ID>?fields=id,number,status,state,agent(name),buildType(id,name),triggered,properties(property)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List queued builds
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildQueue?fields=build(id,buildType(id),waitReason,properties(property))" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List running builds
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds?locator=running:true&fields=build(id,buildType(id),agent(name),percentageComplete)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### List builds on a specific agent in a time window
Use this to rule out (or find) concurrent builds when diagnosing machine-level conflicts (e.g. UBT mutex):
```bash
curl -s "http://192.168.2.13:8111/app/rest/builds?locator=agent:(id:<AGENT_ID>),sinceDate:(yyyyMMdd'T'HHmmss%2B0800),untilDate:(yyyyMMdd'T'HHmmss%2B0800)&fields=build(id,number,buildType(id,name),startDate,finishDate,status)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```
Note: date format is `yyyyMMdd'T'HHmmssZ` with the timezone offset URL-encoded (`+0800` → `%2B0800`). Find the agent id via the "List all agents" query below.

### List all agents
```bash
curl -s "http://192.168.2.13:8111/app/rest/agents?fields=agent(id,name,connected,enabled,authorized,build(id,buildType(id)))" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Compatible agents for a queued build
```bash
curl -s "http://192.168.2.13:8111/app/rest/agents?locator=compatible:(build:(id:<QUEUE_ID>))&fields=agent(id,name,connected,enabled,authorized)" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Get build config parameters
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

### Get agent requirements
```bash
curl -s "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/agent-requirements" \
  -H "Accept: application/json" -H "Authorization: Bearer $TOKEN"
```

## Modifying build config parameters

### PUT (update or create) a parameter
```bash
curl -s -X PUT "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters/<PARAM_NAME>" \
  -H "Content-Type: text/plain" -H "Accept: text/plain" \
  -H "Authorization: Bearer $TOKEN" \
  -d 'new-value'
```

### POST (add) a new parameter
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/buildTypes/id:<BT_ID>/parameters" \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"name":"PARAM_NAME","value":"value"}'
```

## Build queue management

### Cancel a queued or running build
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/builds/id:<ID>" \
  -H "Content-Type: application/xml" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '<buildCancelRequest comment="reason" readdIntoQueue="false"/>'
```

### Trigger a build
```bash
curl -s -X POST "http://192.168.2.13:8111/app/rest/buildQueue" \
  -H "Content-Type: application/xml" -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '<build><buildType id="<BT_ID>"/></build>'
```

## Diagnosing "no compatible agents"

1. Check the queued build's `properties` — look for unresolved `%PARAM%` placeholders in the value that feeds the agent requirement.
2. Check `agent-requirements` on the build config — find which property it matches on.
3. Call the compatible-agents endpoint to confirm whether any agent matches.
4. If compatible agents exist but the build still waits, the build was queued before a parameter fix — cancel and re-trigger.

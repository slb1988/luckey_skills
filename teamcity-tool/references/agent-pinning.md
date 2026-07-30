# Agent Pinning in Build Chains

## The `reverse.dep.*` parameter mechanism

`reverse.dep.*.PARAM_NAME` on a **parent/pipeline** build config sets the value of `PARAM_NAME` on all downstream builds in the chain. TeamCity resolves these values **at queue time**, before any build runs.

## Reverse.dep values are passed literally

TeamCity does **not** resolve `%...%` parameter references inside the value of a `reverse.dep.*` parameter before passing it downstream. The child build receives the literal string.

This means:

```kotlin
// WRONG: creates a circular reference on the child
param("reverse.dep.*.DefaultAgent", "%DefaultAgent%")
```

On the child, if `DefaultAgent` is defined as `%reverse.dep.*.DefaultAgent|.*%`, the resolution becomes:
- `DefaultAgent` → `%reverse.dep.*.DefaultAgent|.*%`
- `reverse.dep.*.DefaultAgent` → `%DefaultAgent%` (literal)
- `%DefaultAgent%` → child's own `DefaultAgent` parameter → circular

Result: the child sees `DefaultAgent` as the unresolved literal `%DefaultAgent%`, and agent requirements fail to match any agent.

## Correct pattern for agent pinning via pipeline

```kotlin
// Pipeline / composite build config
params {
    param("DefaultAgent", "DefaultAgent")          // user-facing label
    param("reverse.dep.*.DefaultAgent", "DefaultAgent")  // MUST be literal
}

// Downstream build config
params {
    param("DefaultAgent", "%reverse.dep.*.DefaultAgent|.*%")
}

requirements {
    matches("teamcity.agent.name", "%DefaultAgent%")
}
```

Behavior:

| Trigger source | `DefaultAgent` resolved value | Agent requirement effect |
|---|---|---|
| Pipeline | `DefaultAgent` | pinned to `DefaultAgent` |
| Standalone | `.*` (fallback) | matches any agent |

Use `matches` (regex) instead of `equals` so the `.*` fallback matches every agent name.

## Lesson: Never use `%teamcity.agent.name%` in `reverse.dep.*`

**Problem:** If you set `reverse.dep.*.DefaultAgent = %teamcity.agent.name%` on the pipeline, the pipeline has no agent yet when it enters the queue. `%teamcity.agent.name%` resolves to empty string. Every downstream build gets `DefaultAgent = ""`, and their agent requirement matches nothing.

**Symptom:** All downstream builds show `waitReason: "There are no idle compatible agents which can run this build"` even though agents are connected and idle.

**Fix:** Use a literal value or a parameter that is already defined on the pipeline config.

## Lesson: Never use an unresolvable `%PARAM%` reference in `reverse.dep.*`

**Problem:** If you set `reverse.dep.*.DefaultAgent = %SomeParam%` but `%SomeParam%` is not resolvable in the downstream context, the downstream build receives the literal string `%SomeParam%` rather than the resolved value.

**Fix:** Either:
- Set `reverse.dep.*.DefaultAgent` to a **literal value** (e.g., `DefaultAgent`), OR
- Define the downstream parameter with a fallback that does not depend on the same parameter name.

## Diagnosing a stuck build chain

1. Check `waitReason` on each queued build.
2. For `"no idle compatible agents"`: call the compatible-agents endpoint — if agents exist, the issue is parameter resolution, not agent availability.
3. Inspect the queued build's `properties` — look for unresolved `%PARAM%` or empty values feeding the agent requirement.
4. Check `agent-requirements` on the build config to see which property it matches on and what value it expects.
5. Trace back to the pipeline's `reverse.dep.*` parameters to find the source of the bad value.

## Prefer agent pool/compatibility over hardcoded agent names

Hardcoding an agent name (`DefaultAgent`) in parameters and agent requirements is brittle:
- Renaming the agent breaks the chain
- You cannot easily migrate to a new agent
- The parameter plumbing (`DefaultAgent`, `reverse.dep.*.DefaultAgent`) adds noise

**Better approach:**
- Remove the `DefaultAgent` parameter and all `teamcity.agent.name == %DefaultAgent%` requirements
- Let TeamCity pick any compatible agent
- Use `runOnSameAgent = true` on the snapshot dependency when downstream builds must reuse the upstream checkout
- If only certain agents should run the chain, configure an **Agent Pool** or add a capability-based requirement (e.g., `os.name == Linux`)

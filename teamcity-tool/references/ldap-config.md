# LDAP Integration Guide for TeamCity

## How LDAP config works

TeamCity loads LDAP settings from:
```
<teamcity.data.path>/config/ldap-config.properties
```

If this file does not exist, the LDAP login module is **not shown** on the login page even though the `ldap` plugin is loaded. TeamCity ships a template at `ldap-config.properties.dist` which is overwritten on every server restart with default content.

## Activating LDAP

1. Copy the dist file to the actual config file:
   ```bash
   cp <data-dir>/config/ldap-config.properties.dist <data-dir>/config/ldap-config.properties
   ```
2. TeamCity picks up changes to `ldap-config.properties` automatically — **no restart required** after editing.
3. If the file was missing and you just created it, a restart ensures the auth module is registered. Alternatively, the LDAP module is detected within a sync interval.

For auto-server specifically:
```bash
cp /mnt/disk2/TeamCity/.BuildServer/config/ldap-config.properties.dist \
   /mnt/disk2/TeamCity/.BuildServer/config/ldap-config.properties
```

## Required settings (minimal working config)

Uncomment and fill in these properties:

```properties
# LDAP server URL (space-escaped)
java.naming.provider.url=ldap://<server>:389/DC=example%20inc,DC=com

# Bind credentials (DN, not url-escaped)
java.naming.security.principal=CN=Administrator,CN=Users,DC=example inc,DC=com
java.naming.security.credentials=<password>

# User search filter (defines how login name maps to LDAP entry)
# Active Directory:
teamcity.users.login.filter=(sAMAccountName=$capturedLogin$)
# OpenLDAP / other:
# teamcity.users.login.filter=(uid=$capturedLogin$)
# teamcity.users.login.filter=(cn=$capturedLogin$)

# LDAP attribute → TeamCity username mapping
# Active Directory:
teamcity.users.username=sAMAccountName
# Other:
# teamcity.users.username=uid
```

## Optional but recommended

```properties
# User base DN (restricts search scope for performance)
teamcity.users.base=CN=users

# Allow any login name format (default rejects "\" and "@")
teamcity.auth.loginFilter=.*

# User detail sync from LDAP
teamcity.users.property.displayName=displayName
teamcity.users.property.email=mail
```

## Synchronization settings

### Mandatory coupling

When you enable sync, TeamCity validates all properties for that domain. Missing one property blocks the entire sync module:

| If you set | You must also define |
|---|---|
| `teamcity.options.users.synchronize=true` | `teamcity.users.filter` |
| `teamcity.options.groups.synchronize=true` | `teamcity.groups.filter` |
| `teamcity.options.createUsers=true` | `teamcity.users.filter` + `teamcity.options.groups.synchronize=true` |

Note: `teamcity.users.login.filter` handles **authentication** (login). `teamcity.users.filter` handles **synchronization** (background scanning). They are independent filters and both are needed when sync is active.

### Full sync config

```properties
# Enable property sync for existing users — REQUIRES teamcity.users.filter
teamcity.options.users.synchronize=true
# Must match your LDAP user objectClass (e.g., inetOrgPerson for LLDAP, user for AD)
teamcity.users.filter=(objectClass=inetOrgPerson)

# Enable group membership sync — REQUIRES teamcity.groups.filter
teamcity.options.groups.synchronize=true
teamcity.groups.filter=(objectClass=groupOfUniqueNames)

# Group settings
teamcity.groups.base=ou=groups
teamcity.groups.property.member=uniqueMember

# Auto-create/delete users based on LDAP group membership
teamcity.options.createUsers=true
teamcity.options.deleteUsers=false

# Sync interval in milliseconds (default 1 hour)
teamcity.options.syncTimeout=3600000
```

**Important:** Group sync requires groups to be manually created in TeamCity and mapped in `ldap-mapping.xml`. The template is at `ldap-mapping.xml.dist`.

## Connection tuning

```properties
# Connection timeout (ms), default 60000
com.sun.jndi.ldap.connect.timeout=60000

# Read timeout (ms), default 60000
com.sun.jndi.ldap.read.timeout=60000

# Ignore LDAP referrals (follow by default)
java.naming.referral=ignore
```

## Password security

Instead of storing the bind password in clear text, TeamCity supports scrambled passwords. The scrambling is done via the server's built-in mechanism — see JetBrains documentation for details.

## Verifying LDAP is working

1. Check the LDAP auth module is registered: look at `/mnt/disk2/TeamCity/.BuildServer/config/_auth/ldap.xml` (on auto-server)
2. The login page should show an LDAP login option
3. Check server logs for LDAP-related lines:
   ```bash
   grep -i ldap /mnt/disk2/TeamCity/logs/teamcity-server.log | tail -20
   ```

## LLDAP-specific notes

LLDAP is a lightweight LDAP server (Docker image: `lldap/lldap:stable`). It has several differences from Active Directory or OpenLDAP:

| Aspect | LLDAP behavior |
|---|---|
| User objectClass | `inetOrgPerson` (NOT `user` or `person`) |
| Group objectClass | `groupOfUniqueNames` (NOT `group`) |
| Member attribute | `uniqueMember` (NOT `member`) |
| displayName | **Not supported** — use `cn` instead |
| LDAPS/TLS | **Not supported** — plain `ldap://` only. TeamCity's "insecure" warning is cosmetic; safe since both services run on same host. |
| Port | Defaults to 3890 (LDAP) + 17170 (web UI) |
| User DN format | `uid=<username>,ou=people,<base_dn>` |

Example working config for LLDAP:
```properties
java.naming.provider.url=ldap://<host>:3890/DC=example,DC=com
java.naming.security.principal=uid=admin,ou=people,dc=example,dc=com
teamcity.users.base=ou=people
teamcity.users.filter=(objectClass=inetOrgPerson)
teamcity.users.login.filter=(uid=$capturedLogin$)
teamcity.users.username=uid
teamcity.groups.base=ou=groups
teamcity.groups.filter=(objectClass=groupOfUniqueNames)
teamcity.groups.property.member=uniqueMember
# LLDAP has no displayName — use cn for full name
teamcity.users.property.displayName=cn
```

## Troubleshooting: discover server attributes

When the LDAP server schema is unknown, query it directly with Python:
```bash
python3 -c "
import ldap3
s = ldap3.Server('host', port=3890, get_info=ldap3.ALL)
c = ldap3.Connection(s, 'uid=admin,ou=people,dc=example,dc=com', 'password', auto_bind=True)
c.search('ou=people,dc=example,dc=com', '(objectClass=*)', attributes=['objectClass','uid','mail','cn'])
for e in c.entries: print(e.entry_dn, 'objectClass:', e.objectClass.values)
c.unbind()
"
```
Install: `pip3 install ldap3`

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No LDAP option on login page | `ldap-config.properties` missing | Create file from `.dist` template |
| `mandatory property 'java.naming.provider.url' is not defined` | Only `.dist` template exists, not actual config | Copy `.dist` → `.properties` and fill in the LDAP URL |
| `mandatory property 'teamcity.users.filter' is not defined` | Sync enabled but no sync filter | Add `teamcity.users.filter=(objectClass=...)` matching your LDAP schema |
| "Invalid username or password" | Wrong login filter | Check `teamcity.users.login.filter` matches your LDAP schema |
| Users not found | Wrong search base or objectClass | Verify `teamcity.users.base` DN and `teamcity.users.filter` objectClass |
| Slow authentication | No search base restriction | Set `teamcity.users.base` to narrow scope |
| Sync not working | Groups not in `ldap-mapping.xml` | Create groups in TeamCity UI, then map in xml |
| "Insecure LDAP" warning | Using `ldap://` instead of `ldaps://` | Ignore if LDAP server has no TLS (LLDAP, internal LDAP on same host) |

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

For automatic sync of users and groups:

```properties
# Enable property sync for existing users
teamcity.options.users.synchronize=true

# Enable group membership sync
teamcity.options.groups.synchronize=true

# Group settings
teamcity.groups.base=CN=users
teamcity.groups.filter=(objectClass=group)
teamcity.groups.property.member=member

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

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| No LDAP option on login page | `ldap-config.properties` missing | Create file from `.dist` template |
| "Invalid username or password" | Wrong login filter | Check `teamcity.users.login.filter` matches your LDAP schema |
| Users not found | Wrong search base | Verify `teamcity.users.base` DN relative to provider URL |
| Slow authentication | No search base restriction | Set `teamcity.users.base` to narrow scope |
| Sync not working | Groups not in `ldap-mapping.xml` | Create groups in TeamCity UI, then map in xml |

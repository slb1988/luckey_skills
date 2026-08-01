# Access And Secrets

## Sensitive Config

Load credentials from the repository root. Prefer `.env/asus-router.env` if `.env` is a directory; otherwise use the existing root `.env` file. Do not commit either location.

Expected variables:

```sh
ASUS_ROUTER_HOST=192.168.50.1
ASUS_ROUTER_USER=<router-ssh-user>
ASUS_ROUTER_PASSWORD=<router-ssh-password>
ASUS_FANCYSS_SUBSCRIPTION_URL=<subscription-url>
ASUS_FANCYSS_SUBSCRIPTION_B64=<base64-subscription-url>
```

Optional known node variables:

```sh
ASUS_FANCYSS_HK01_ID=4
ASUS_FANCYSS_HK01_IDENTITY=<identity>
ASUS_FANCYSS_HK02_ID=5
ASUS_FANCYSS_HK02_IDENTITY=<identity>
```

## SSH Access

Use password and keyboard-interactive auth. Some Merlin/KoolShare builds reject public-key auth or lack common Linux utilities.

```sh
scripts/router_ssh.sh 'uname -a; dbus get ss_basic_version_local'
```

If running SSH manually:

```sh
ssh -tt \
  -o PreferredAuthentications=password,keyboard-interactive \
  -o PubkeyAuthentication=no \
  -o KbdInteractiveAuthentication=yes \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/tmp/codex_router_known_hosts \
  "$ASUS_ROUTER_USER@$ASUS_ROUTER_HOST"
```

## Web Access

Use the browser requested by the user when interacting with the UI. For command-line reachability checks, bypass local proxy settings:

```sh
env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
  curl --noproxy '*' -I "http://${ASUS_ROUTER_HOST}/Main_Login.asp"
```

Treat `HTTP/1.0 200 OK` from `Main_Login.asp` as evidence that the admin UI is reachable.

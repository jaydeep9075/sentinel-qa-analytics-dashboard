# Publishing `sentinel-qa-reporter` to npm

The client package lives in `packages/sentinel-qa-reporter/`. Publishing it is
optional — teams that host your Docker image can already install it straight
from their own Sentinel (`npm i -D https://their-host/live/package/…tgz`).
Publish when you want the plain `npm i -D sentinel-qa-reporter` to work for
anyone, hosted or not.

The name is **unscoped**, which matters: no npm organisation to create, no
`--access public` flag, no scope permissions to manage.

---

## One-time setup

**1. Create an npm account** at <https://www.npmjs.com/signup> (skip if you
have one).

**2. Turn on 2FA — do this BEFORE you log in.** npm requires two-factor
authentication to publish, and this is the step that bites: `npm login` uses a
browser flow that succeeds happily without 2FA, so nothing goes wrong until
`npm publish` fails with `E403 ... Two-factor authentication ... is required`.

Go to <https://www.npmjs.com/settings/~/profile> → **Two-Factor
Authentication** → **Enable 2FA**, and choose **Authorization and writes**
(the "Authorization only" mode does not cover publishing). Scan the QR code
with any authenticator app — Google Authenticator, Authy, 1Password, Microsoft
Authenticator — and save the recovery codes somewhere you will still have them
when you lose the phone.

**3. Log in from this machine:**

```powershell
cd packages\sentinel-qa-reporter
npm login
```

It opens a browser to authenticate. Confirm it worked:

```powershell
npm whoami
```

**4. Check the name is still free** (it was when this was written):

```powershell
npm view sentinel-qa-reporter
```

`404 Not Found` means it's yours to take. If someone has claimed it since,
change `"name"` in `package.json` — everything else keeps working, but the
import paths in every guide and in `withSentinel`'s emitted reporter string
(`src/playwright/config.ts`) must change to match.

---

## Publishing a version

**1. Run the tests.** `prepublishOnly` builds automatically, but it does not
run tests:

```powershell
cd packages\sentinel-qa-reporter
npm test
```

20 tests, all should pass.

**2. Set the version.** Never republish the same version — npm rejects it, and
so it should.

```powershell
npm version patch    # 1.0.0 -> 1.0.1   bug fix
npm version minor    # 1.0.0 -> 1.1.0   new option, backwards compatible
npm version major    # 1.0.0 -> 2.0.0   a repo must change its config
```

**3. Dry run first** — this prints exactly what would be uploaded, without
uploading anything:

```powershell
npm publish --dry-run
```

Check the file list: it should contain `dist/`, `README.md`, `LICENSE`,
`package.json` — and **no** `src/`, `test/`, or `node_modules/`. Roughly 25 kB.

**4. Publish:**

```powershell
npm publish
```

You'll be prompted for the 6-digit code from your authenticator app. To skip
the prompt (useful when a terminal swallows it), pass it directly:

```powershell
npm publish --otp=123456
```

That's it — it's live within seconds at
<https://www.npmjs.com/package/sentinel-qa-reporter>.

### If publish fails with E403

```
npm error code E403
npm error 403 Forbidden - PUT https://registry.npmjs.org/sentinel-qa-reporter
npm error Two-factor authentication or granular access token with bypass 2fa
npm error enabled is required to publish packages.
```

This is step 2 not done — the account has no 2FA. Enable it as above and run
`npm publish` again. **Do not bump the version first**: the failed publish
uploaded nothing, so the current version number is still unused.

### Publishing without 2FA at all — use a Classic *Automation* token

npm has two token families and only one of them skips 2FA. Getting this wrong
gives you the exact same E403 as having no token, because the token
authenticates fine (`npm whoami` works) and is then refused at the publish
step:

| Token type | Where | Bypasses 2FA? |
|---|---|---|
| Classic → **Automation** | Tokens → Generate New Token → **Classic Token** | **Yes** — this is the one |
| Classic → Publish | same menu | No, prompts for an OTP |
| Classic → Read-only | same menu | Cannot publish at all |
| Granular Access Token | Tokens → Generate New Token → Granular | Only if the account already has 2FA on |

So: <https://www.npmjs.com/settings/~/tokens> → **Generate New Token** →
**Classic Token** → select **Automation** → Generate. Automation tokens exist
precisely for CI, where there is no phone to read a code off.

Then publish with it — as a flag, so nothing lands in a `.npmrc` on disk:

```powershell
npm publish --//registry.npmjs.org/:_authToken=<token>
```

or in a pipeline, via the file npm expects:

```bash
echo "//registry.npmjs.org/:_authToken=$NPM_TOKEN" > .npmrc
npm publish
```

Two follow-on traps worth knowing about:

- **A Granular token scoped to "Only select packages" cannot create a package
  that does not exist yet.** For a first publish it must be scoped to *All
  packages*, then you can narrow it afterwards. Automation tokens are
  account-wide and sidestep this.
- Treat any of these as a real secret with an expiry — a token that bypasses
  your second factor *is* your second factor, and anyone holding it can
  publish as you.

**5. Verify from a clean directory:**

```powershell
cd $env:TEMP
mkdir verify-sentinel; cd verify-sentinel
npm init -y
npm i -D sentinel-qa-reporter
node -e "console.log(Object.keys(require('sentinel-qa-reporter/playwright/config')))"
```

Should print `[ 'withSentinel' ]`.

---

## After the first publish

Repos that were installing the local tarball switch to the registry — a
one-line change in `package.json`:

```diff
-"sentinel-qa-reporter": "file:../sentinel-qa-analytics-dashboard/packages/dist-pack/sentinel-qa-reporter-1.0.1.tgz"
+"sentinel-qa-reporter": "^1.0.1"
```

then `npm install`. **`sfcc-qa-automation` currently has the `file:` form** and
is the one repo that needs this.

---

## Keeping the two distribution paths in step

There are two ways a repo can get this package and they must not drift:

| Path | Source | Who uses it |
|---|---|---|
| npm | whatever you last published | anyone, hosted or not |
| `GET /live/package` | built into the Docker image from source | teams running your image |

The Docker path rebuilds from `packages/sentinel-qa-reporter/src` on every
image build, so it is automatically in step with the code. The npm path is
only in step if you remember to publish. **So: bump the version and publish in
the same commit that changes the package**, or the two answers to "which
version am I on?" start disagreeing.

If you'd rather not maintain the npm path at all, that's a legitimate choice —
delete this file, drop `npm i -D sentinel-qa-reporter` from the docs, and let
the hosted tarball be the only way in. It is the better path for internal use
anyway: the client version always matches the server it reports to.

---

## Publishing somewhere private instead

For an internal registry (Artifactory, GitHub Packages, Verdaccio), add a
`publishConfig` to `package.json` and point `npm login` at it:

```json
"publishConfig": { "registry": "https://npm.your-company.com/" }
```

```powershell
npm login --registry=https://npm.your-company.com/
npm publish
```

Consumers then need a matching `.npmrc`, which is friction the hosted-tarball
path does not have — worth weighing before choosing this over just serving it
from Sentinel.

# Class Merit Hub — Cloudflare Workers + D1

This is a separate Cloudflare deployment target. The existing Windows/NiceGUI/SQLite application in the repository root is preserved.

## Architecture
- Cloudflare Python Worker handles APIs and authorization.
- Cloudflare D1 stores users, scores, evaluations, login throttling and audit logs.
- Workers Static Assets serves the responsive web UI.
- Cloudflare Workers Builds deploys on pushes to the selected Git branch.

## Important before real student data
1. Python Workers are currently a beta feature. Test end-to-end behaviour before using real data.
2. This port uses PBKDF2-SHA256 via Cloudflare Web Crypto. The Windows application uses Argon2id; old Argon2id hashes are not verified here and passwords must be reset/re-issued before moving users.
3. D1 starts empty. There is no automatic copy of the local SQLite database. Do not delete or overwrite your old database.
4. Replace the placeholder D1 ID in wrangler.jsonc before deployment.
5. This is a first Cloudflare port of core workflows, not complete feature parity: score/evaluation editing, complete account editing and SQLite import still need implementation.

## 1. Create D1
Cloudflare Dashboard → Storage & databases → D1 SQL Database → Create database. Name it exactly class-merit-hub. Copy the Database ID and replace 00000000-0000-0000-0000-000000000000 in wrangler.jsonc. Keep binding DB.
Alternatively run npx wrangler d1 create class-merit-hub from this folder.

## 2. Apply the schema
From this folder, with Node.js and uv installed:
    uv run pywrangler d1 migrations apply class-merit-hub --remote
or:
    npx wrangler d1 migrations apply class-merit-hub --remote
Apply migrations/0001_initial.sql to the remote database before making the site public.

## 3. Add secret values
Cloudflare Dashboard → Workers & Pages → class-merit-hub → Settings → Variables and Secrets.
Add these as Secrets:
- SESSION_SECRET: random value, at least 32 characters.
- FOUNDER_SETUP_TOKEN: separate random value, at least 24 characters.
Generate locally in PowerShell:
    py -c "import secrets; print(secrets.token_urlsafe(48))"
Never commit secrets or paste them into chat.

## 4. Connect GitHub
Create Worker → Continue with GitHub → account conmeophat → repo quan_ly_thanh_vien_trong-lop.
Set:
- Worker name: class-merit-hub (must exactly match Wrangler name).
- Root directory: cloudflare.
- Production branch: main.
- Build command: leave blank.
- Deploy command: uv run pywrangler deploy.
Then Save and Deploy. If connecting before the Cloudflare files are merged into main, select the cloudflare-workers branch temporarily.

## 5. Create the founder account once
After D1 schema and both secrets are ready, open the workers.dev URL. Enter FOUNDER_SETUP_TOKEN, founder name, phone and a strong password. Only one founder can be created. Rotate or remove FOUNDER_SETUP_TOKEN after setup.

## Supported first release
- One-time founder bootstrap.
- Member self-registration always creates a pending member.
- Phone/password login with eight-hour signed Secure/HttpOnly cookie.
- Five consecutive failed sign-ins trigger a 15-minute lockout.
- Founder/teacher see all four groups; leader sees assigned group; member sees only own records.
- Privileged account creation and approval; leaders can only create members in their own group.
- Add scores and evaluations; hide records with soft-delete.
- Founder audit log and privileged password reset.

## Test checklist
- /api/healthz returns status ok.
- Bootstrap rejects a wrong setup token and only succeeds once.
- Public registration cannot create privileged roles.
- A leader cannot view or modify data in another group.
- A member cannot view another member's records.
- Zero points and scores outside -100 to +100 are rejected.
- Logout, session expiry, lockout and password reset work as expected.

## Local development
From this folder run uv run pywrangler dev with a local D1 database. Test the Worker before connecting real class data.

## Backups and limits
Keep D1 backups/Time Travel enabled where available and export independent backups regularly. Cloudflare Free quotas for Worker CPU, D1 storage, reads and writes are enforced and may change. A free plan is not a permanent uptime or data-retention guarantee.

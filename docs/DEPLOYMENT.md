# Deploying updates

GitHub is the source of truth. Changes are developed on a branch, checked in a
pull request and merged into **main**. The production server then pulls that
exact version with one command:

~~~sh
cd /srv/nutrioptimize
./scripts/deploy.sh
~~~

The script refuses local code changes, fetches only **main**, creates a
PostgreSQL dump, performs a fast-forward update, rebuilds the containers, runs
migrations and waits for the API readiness check. It does not touch the local
environment file or files under **secrets/**.

This manual final step is intentional. GitHub does not receive an SSH key with
root-like access to the server, and a merge cannot immediately change
production without the operator seeing it. A manually approved GitHub Actions
deployment can be added later if the project grows.

## One-time server connection to the repository

For the public repository, clone over HTTPS as shown in the README. A private
fork needs credentials for unattended pulls; use a dedicated read-only deploy
key rather than a personal SSH key or access token.

Create a dedicated read-only key on the server:

~~~sh
ssh-keygen -t ed25519 -f ~/.ssh/nutrioptimize-github -C nutrioptimize-deploy
cat ~/.ssh/nutrioptimize-github.pub
~~~

Add the displayed public key in the GitHub repository under **Settings → Deploy
keys**. Leave **Allow write access** disabled.

An existing installation that was copied to the server can become a Git
checkout without replacing its environment, secrets or database volumes:

~~~sh
cd /srv/nutrioptimize
git init -b main
git remote add origin git@github.com:YOUR-ACCOUNT/nutrioptimize.git
git config core.sshCommand 'ssh -i ~/.ssh/nutrioptimize-github -o IdentitiesOnly=yes'
git fetch origin main
git reset --mixed origin/main
git status --short
~~~

The mixed reset records the GitHub revision but does not overwrite working
files. Stop and inspect any tracked differences reported by the final command;
do not discard a server change without understanding it first.

After confirming that the differences are only an older copied release, archive
them and make the tracked files match GitHub. The rebuild option is intended for
this one-time conversion:

~~~sh
git restore --worktree -- .
./scripts/deploy.sh --rebuild
~~~

## Normal release flow

1. Make changes on a branch.
2. Push the branch and open a pull request.
3. Let GitHub run the Compose, build and unit-test checks.
4. Review and merge into **main**.
5. Log in to the server and run the deploy script.
6. Test one real ChatGPT query.

Pre-deploy dumps stay in **backups/** on the server with mode 600. They are a
local safety net, not a complete backup strategy; an encrypted copy should also
exist off the server.

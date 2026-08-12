---
name: spk-pr-writer
description: Create a GitHub pull request from the currently active branch using the GitHub CLI (gh), with a standardized title and description. Use when the user wants to open, create, or write a pull request.
---

# Sparkgeo PR Writer

Create a GitHub pull request for the currently active branch using the `gh` CLI, following Sparkgeo's PR title and description templates.

## Steps

1. **Gather branch and change context**
   - Get the current branch name: `git branch --show-current`
   - Confirm you are not on the default branch (`main`/`master`). If you are, stop and ask the user to create or switch to a feature branch first.
   - Review the changes the PR will contain: `git log <default-branch>..HEAD --oneline` and `git diff <default-branch>...HEAD --stat`
   - Ensure the branch is pushed to the remote. If not, push it with `git push -u origin <branch-name>`.

2. **Ask about a related GitHub issue**
   - Prompt the user: *"Do you have a URL to the GitHub issue this PR addresses?"*
   - If they provide one, include it in the PR description with a closing keyword (e.g. `Closes <issue-url>`) so the issue is closed automatically when the PR is merged.
   - If they don't have one, omit the issue section entirely.

3. **Compose the PR title**

   Use this template:

   ```
   [{BRANCH NAME}] {Title}
   ```

   - `{BRANCH NAME}` is the current git branch name.
   - `{Title}` is a short, human-readable summary of the change derived from the commits/diff.

4. **Compose the PR description**

   Use this template:

   ```
   {No more than 2 sentences on the intent of the PR}

   {Bullet points summarizing, at a high level, any changes}
   ```

   - Keep the intent paragraph to **two sentences maximum**.
   - Keep the bullet list high level — summarize the changes, don't enumerate every file.
   - If the user provided an issue URL, append it at the end:

     ```
     Closes {ISSUE URL}
     ```

     and note to the user that merging the PR will close the issue automatically.

5. **Create the pull request**

   Use the `gh` CLI, targeting the repository's default branch:

   ```bash
   gh pr create --base <default-branch> --title "[{BRANCH NAME}] {Title}" --body "$(cat <<'EOF'
   {Intent — max 2 sentences}

   - {High-level change 1}
   - {High-level change 2}

   Closes {ISSUE URL}
   EOF
   )"
   ```

6. **Report back**
   - Share the PR URL returned by `gh pr create` with the user.

## Notes

- Requires the `gh` CLI to be installed and authenticated (`gh auth status`).
- Never create a PR from the default branch.
- Show the user the composed title and description before creating the PR if there is any ambiguity about the intent of the changes.

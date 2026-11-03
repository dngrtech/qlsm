## Lens: project rules and history

1. Documented conventions. Check the diff against `docs/development_guidelines.md`
   and, for frontend changes, `docs/design-system.md`. Quote the rule you are
   applying in `evidence`. Also check these rules:
   - Jinja variables in Ansible YAML are quoted (`port: "{{ ssh_port }}"`).
   - Protected routes use `@jwt_required()`, with the parentheses.
   - Route, model, playbook or service changes update the matching `docs/*.md`.
   - User-facing changes update `docs/user/`.
   - A new page under `docs/user/` is added to both navs, as
     `docs/development_guidelines.md` describes.
2. History. Run `git log -L` or `git blame` on the changed hunks, and read the
   commit messages that last touched them. Flag a change that reintroduces
   something an earlier commit deliberately fixed or removed. Cite the commit.
3. Code comments. Flag a change that contradicts a nearby comment that explains a
   constraint ("must stay in sync with…", "order matters because…").

Skip anything a script can check, such as whether the four version references
agree. A deterministic CI step covers those. Don't report file length.

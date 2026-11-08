# AGENTS.md

Serveur MCP non officiel (Python, FastMCP, stdio) qui lit et réécrit les plans `.kzp` du concepteur 3D Leroy Merlin (moteur Kazaplan), plus les skills `kazaplan-decorator` (aménager, décorer) et `kazaplan-floorplan` (dupliquer un plan, le tracer d'après une photo). Distribué par uvx, Docker (GHCR), plugin Claude Code, extension Gemini CLI et `npx skills add`.

## Où est quoi

- `src/kazaplan_mcp/` : `kzp.py` (conteneur WPRJ), `catalog.py` (téléchargement et index local du catalogue), `geometry.py`, `plan.py` (modèle du plan, placement, construction), `circulation.py`, `api.py` (API Kazaplan, sauvegardes), `paths.py` (dossier de données), `sketch.py` (plans SVG, livrable `PLANCHES.md`), `section.py` (coupes), `mesh.py` (modèles 3D `.glb` rendus au trait), `server.py` (outils `kz_*`, CLI `kazaplan-mcp`).
- `skills/` : skills au format Agent Skills, sans dépendance à un assistant ni à ce dépôt (ils n'appellent que des outils `kz_*`).
- `.claude-plugin/` (plugin et marketplace Claude Code), `gemini-extension.json`, `Dockerfile` : distribution ; la version est aussi dans `pyproject.toml`, à garder alignée.
- `README.md` : doc utilisateur. `HANDOFF.md` : notes techniques, format `.kzp`, conventions vérifiées, règles du planner et leurs preuves.

## Vérifier

Les mêmes contrôles que la CI (`.github/workflows/ci.yml`) :

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q
```

Les tests n'ont pas besoin du catalogue (simulé). Le serveur le télécharge au premier lancement (ou `kazaplan-mcp catalog`) dans le dossier de données (`KZ_DATA_DIR`, défaut `~/.cache/kazaplan-mcp`).

Un test vert ne prouve pas que le planner accepte le plan. Toute écriture qui touche la structure (murs, pièces, ouvertures, nouveau type d'objet) se valide **dans le planner** sur un plan de test : rechargement console vidée sans erreur rouge `index-*.js`, rendu 3D sans bloc jaune, puis clic sur l'icône d'enregistrement du planner et requête `plans/save` émise.

## Invariants du format (appris à la dure)

- Coordonnées : plan `(x, y)` ↔ 3D `(x, hauteur, -y)`. Un modèle de rotation `θ` a sa largeur suivant `θ` et sa face avant vers `θ + 90°` ; `position` = centre de l'empreinte ; les `position.y` des gabarits catalogue sont des hauteurs absolues, ramenées au sol.
- Les `wall.pane` des murs existants restent dans le fichier ; seules disparaissent les références vers des faces supprimées avec leur mur (`_prune_pane_refs`).
- Les `wall.room` viennent du planner, jamais du MCP : il détecte les pièces fermées à l'ouverture ; le MCP ne fait que les renommer. Modifier des murs recrée la pièce (nouvel id, sans sol ni nom).
- Revêtement d'un mur : `wall.pane.materials["wall.pane"]`, sur les faces dont `roomInfo.id` est la pièce.
- Le détail et les preuves sont dans `HANDOFF.md` §7. En cas de doute, la source de vérité est le code public du planner : `https://planner.kazaplan.com/planner/index.html` et `chunks/*.js` (à télécharger dans `/tmp`, à lire avec grep).

## Sécurité

- L'écriture en ligne exige la liste blanche `KZ_ALLOWED_PLANS` ; chaque ouverture et chaque envoi laissent une copie dans `backups/` du dossier de données.
- Les chemins fournis par l'assistant sont bornés : `.kzp` pour `kz_save`, dossier de données pour `kz_sketch`, dossier du `DECOR.md` pour `kz_board`. Tout nouvel outil qui écrit un fichier suit la même règle, avec un test.
- `KZ_TOKEN` (JWT Kazaplan, ~7 jours) vit uniquement dans l'environnement ; jamais de jeton, de `.kzp` réel ni d'identifiant de plan personnel dans le dépôt.

## Conventions

- Docs, docstrings d'outils et messages destinés à l'utilisateur en français ; identifiants et messages de commit en anglais (`feat:`, `fix:`, `docs:`), commits signés GPG.
- Commentaires rares, réservés au non-évident (une règle du planner, une convention d'axes).
- Après un changement de comportement : mettre à jour `HANDOFF.md`, et `README.md` ou le skill si l'usage change.

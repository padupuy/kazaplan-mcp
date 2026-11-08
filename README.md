# kazaplan-mcp

Piloter le [concepteur 3D Leroy Merlin](https://www.leroymerlin.fr/config-3d/virtual-home) (Virtual Home, moteur
**Kazaplan**) en langage naturel, depuis n'importe quel assistant compatible MCP (Claude, Codex, Gemini CLI, Cursor,
VS Code…) :

> « Mets une baignoire de 170 cm dans la salle de bain »
> « Meuble le salon en scandinave »
> « Dessine ma maison d'après cette photo du plan »

Le dépôt contient :

- un **serveur MCP** (`kazaplan-mcp`) : ouvrir un plan, chercher dans le catalogue Leroy Merlin, poser des meubles,
  peindre, construire des murs, contrôler la circulation, dessiner des plans SVG, enregistrer ;
- deux **skills** au format ouvert [Agent Skills](https://agentskills.io) : `kazaplan-decorator` (aménager et décorer
  une pièce à partir de l'identité décorative de la maison) et `kazaplan-floorplan` (dupliquer un plan, le tracer
  d'après la photo d'un plan).

> [!WARNING]
> **Projet non officiel**, sans lien avec Leroy Merlin ni Kazaplan. Il utilise l'API du planner telle que le site
> l'appelle, avec votre propre session ; elle peut changer sans préavis. Il modifie vos plans : **faites vos essais
> sur une copie**.

---

## Sommaire

1. [Démarrage rapide](#1-démarrage-rapide)
2. [Jeton et identifiant du plan](#2-jeton-et-identifiant-du-plan)
3. [Configuration](#3-configuration)
4. [Brancher le serveur sur votre assistant](#4-brancher-le-serveur-sur-votre-assistant)
5. [Installer les skills](#5-installer-les-skills)
6. [Utilisation](#6-utilisation)
7. [Sécurité et sauvegardes](#7-sécurité-et-sauvegardes)
8. [Dépannage](#8-dépannage)
9. [Développement](#9-développement)

---

## 1. Démarrage rapide

Deux façons de lancer le serveur, sans rien cloner :

| | Prérequis | Commande |
|---|---|---|
| **uvx** (recommandé) | [uv](https://docs.astral.sh/uv/getting-started/installation/) | `uvx --from git+https://github.com/padupuy/kazaplan-mcp kazaplan-mcp` |
| **Docker** | Docker | `docker run -i --rm -v kazaplan-data:/data ghcr.io/padupuy/kazaplan-mcp` |

Installer uv : `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS / Linux) ou
`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows).

Au premier lancement, le serveur télécharge le catalogue Leroy Merlin (≈ 350 Mo, quelques minutes), en construit un
index local (≈ 25 Mo) et jette le reste. Pendant ce temps, les outils du catalogue répondent « catalogue en cours de
téléchargement ». Pour le faire à l'avance, ou récupérer plus tard les nouveautés :

```bash
uvx --from git+https://github.com/padupuy/kazaplan-mcp kazaplan-mcp catalog
```

Vous n'utilisez pas Claude Code ? Passez à l'[étape 2](#2-jeton-et-identifiant-du-plan). Avec Claude Code, le plugin
installe le serveur et les skills d'un coup :

```
/plugin marketplace add padupuy/kazaplan-mcp
/plugin install kazaplan@kazaplan-mcp
```

---

## 2. Jeton et identifiant du plan

### Le jeton

Le serveur agit avec **votre** session Leroy Merlin. Le jeton est valable **environ 7 jours**.

1. Ouvrez <https://www.leroymerlin.fr/config-3d/virtual-home>, connectez-vous et ouvrez votre projet.
2. Outils de développement : **F12** (Windows / Linux) ou **⌥ ⌘ I** (macOS), onglet **Réseau**, filtre
   `api.kazaplan.com`.
3. Enregistrez une petite modification dans le planner (ou rechargez la page).
4. Cliquez sur une requête, section **En-têtes de la requête**, ligne `Authorization: Bearer eyJ…`.
5. Copiez **tout ce qui suit `Bearer `**.

> [!CAUTION]
> Ce jeton donne accès à vos plans : ne le partagez pas, ne le commitez jamais. S'il a fuité, déconnectez-vous puis
> reconnectez-vous à Leroy Merlin.

### L'identifiant du plan

Dans le même onglet Réseau, une requête `api.kazaplan.com/plans/12345678` : le nombre à la fin est l'identifiant de
votre plan.

> [!TIP]
> Créez un second projet vide sur leroymerlin.fr pour vos essais et dupliquez-y votre maison (« duplique mon plan
> 11111111 dans le plan 22222222 »).

---

## 3. Configuration

| Variable | Obligatoire | Rôle | Exemple |
|---|---|---|---|
| `KZ_TOKEN` | pour lire / enregistrer en ligne | votre jeton | `eyJhbGciOi…` |
| `KZ_ALLOWED_PLANS` | pour enregistrer en ligne | **liste blanche** des plans modifiables, séparés par des virgules | `22222222` |
| `KZ_DATA_DIR` | non | dossier de données : catalogue, sauvegardes, plans SVG | défaut `~/.cache/kazaplan-mcp` (Windows : `%LOCALAPPDATA%\kazaplan-mcp`) ; `/data` dans Docker |
| `KZ_BACKUP_DIR` | non | dossier des sauvegardes `.kzp` | défaut `backups/` du dossier de données |
| `KZ_API_URL` | non | adresse de l'API | défaut `https://api.kazaplan.com` |

Sans `KZ_ALLOWED_PLANS`, le serveur peut **lire** vos plans mais **refuse d'enregistrer** : c'est voulu.

---

## 4. Brancher le serveur sur votre assistant

Les exemples utilisent uvx. Pour Docker, remplacez la commande par :

```json
"command": "docker",
"args": ["run", "-i", "--rm", "-e", "KZ_TOKEN", "-e", "KZ_ALLOWED_PLANS",
         "-v", "kazaplan-data:/data", "ghcr.io/padupuy/kazaplan-mcp"]
```

> [!NOTE]
> Avec Docker, les fichiers que vous échangez avec le serveur (`.kzp` locaux, `DECOR.md`, planches) doivent se
> trouver dans un dossier monté (`-v "$PWD":/work`, puis chemins `/work/…`).

<details>
<summary><b>Claude Code</b></summary>

Le plus simple est le plugin (voir [Démarrage rapide](#1-démarrage-rapide)) ; il lit `KZ_TOKEN` et
`KZ_ALLOWED_PLANS` dans votre environnement. Sans le plugin :

```bash
claude mcp add kazaplan --scope user \
  -e KZ_TOKEN="$KZ_TOKEN" -e KZ_ALLOWED_PLANS="22222222" \
  -- uvx --from git+https://github.com/padupuy/kazaplan-mcp kazaplan-mcp
```

</details>

<details>
<summary><b>Claude Desktop</b></summary>

Réglages → Développeur → Modifier la configuration (`claude_desktop_config.json`) :

```json
{
  "mcpServers": {
    "kazaplan": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/padupuy/kazaplan-mcp", "kazaplan-mcp"],
      "env": { "KZ_TOKEN": "collez-votre-jeton-ici", "KZ_ALLOWED_PLANS": "22222222" }
    }
  }
}
```

Si `uvx` est introuvable, mettez son chemin absolu (`which uvx`). Quittez complètement l'application puis relancez-la.

</details>

<details>
<summary><b>Codex CLI</b></summary>

`~/.codex/config.toml` :

```toml
[mcp_servers.kazaplan]
command = "uvx"
args = ["--from", "git+https://github.com/padupuy/kazaplan-mcp", "kazaplan-mcp"]
env = { KZ_TOKEN = "collez-votre-jeton-ici", KZ_ALLOWED_PLANS = "22222222" }
```

</details>

<details>
<summary><b>Gemini CLI</b></summary>

Le dépôt est aussi une extension Gemini CLI (le serveur hérite de `KZ_TOKEN` et `KZ_ALLOWED_PLANS` de votre
environnement) :

```bash
gemini extensions install https://github.com/padupuy/kazaplan-mcp
```

</details>

<details>
<summary><b>Cursor</b></summary>

`~/.cursor/mcp.json` :

```json
{
  "mcpServers": {
    "kazaplan": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/padupuy/kazaplan-mcp", "kazaplan-mcp"],
      "env": { "KZ_TOKEN": "collez-votre-jeton-ici", "KZ_ALLOWED_PLANS": "22222222" }
    }
  }
}
```

</details>

<details>
<summary><b>VS Code (GitHub Copilot)</b></summary>

`.vscode/mcp.json` (le jeton est demandé au démarrage et stocké par VS Code) :

```json
{
  "inputs": [{ "id": "kz-token", "type": "promptString", "description": "Jeton Kazaplan", "password": true }],
  "servers": {
    "kazaplan": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/padupuy/kazaplan-mcp", "kazaplan-mcp"],
      "env": { "KZ_TOKEN": "${input:kz-token}", "KZ_ALLOWED_PLANS": "22222222" }
    }
  }
}
```

</details>

---

## 5. Installer les skills

Les skills apprennent à l'assistant à s'en servir comme un décorateur ou un dessinateur : relevé de la pièce,
identité décorative de la maison (`DECOR.md` : foyer, palette 60 / 30 / 10, matières, programme par pièce), règles
d'ergonomie et de circulation, validation avant de poser, planches d'architecte en fin de projet.

| Assistant | Installation |
|---|---|
| Claude Code | inclus dans le plugin |
| Codex, Cursor, Gemini CLI, Copilot, OpenCode… | `npx skills add padupuy/kazaplan-mcp` |
| Autre | copiez `skills/kazaplan-decorator` et `skills/kazaplan-floorplan` dans le dossier de skills de l'outil |

---

## 6. Utilisation

Parlez normalement à l'assistant :

1. « Ouvre mon plan 22222222 et fais-moi un résumé des pièces. »
2. « Trouve une baignoire de moins de 175 cm et pose-la dans la salle de bain. »
3. « Carrelage blanc 60×60 au sol du WC. »
4. « Décore la chambre 1 » : sol, murs, lumière, tapis, textiles, miroir, déco ; l'assistant présente le projet et
   attend votre accord avant de poser quoi que ce soit.
5. « Enregistre. »

Puis **rechargez la page du planner** pour voir le résultat. Rien n'est envoyé tant que vous n'avez pas demandé
d'enregistrer.

Les murs, ouvertures et pièces neufs se finalisent dans le planner : après l'enregistrement, rechargez-le et
**enregistrez depuis le planner** (il détecte alors les pièces fermées), puis demandez de nommer les nouvelles pièces.

### Les outils

| Outil | Ce qu'il fait |
|---|---|
| `kz_open` | ouvre un plan en ligne (`plan_id`) ou un fichier `.kzp` local (`path`) |
| `kz_summary` | pièces, surfaces, sols, ouvertures, objets posés |
| `kz_room_geometry` | murs d'une pièce, portes et fenêtres, segments libres, surface utile |
| `kz_search_catalog`, `kz_catalog_item` | recherche dans le catalogue (texte, catégorie, dimensions, style, couleur, sol / mur), fiche d'un article |
| `kz_place`, `kz_move`, `kz_remove` | pose, décale, supprime, avec contrôle des collisions, débattements de portes et fenêtres |
| `kz_set_material` | sol, peinture / papier peint / faïence d'une pièce ou d'un mur, plafond, gazon |
| `kz_add_walls`, `kz_add_opening`, `kz_add_pool`, `kz_set_room` | construction : murs, portes et fenêtres, piscine, nom et type des pièces |
| `kz_check_room` | circulation : dégagements autour des meubles, chemins de 60 / 90 cm entre les portes |
| `kz_sketch` | plan SVG vu de dessus d'une pièce ou de la maison |
| `kz_board` | livrable `PLANCHES.md` à côté du `DECOR.md` : vue d'ensemble, nuancier, et par pièce plan coté, coupes, revêtements, nomenclature |
| `kz_save`, `kz_copy_plan` | enregistre en ligne (ou en `.kzp` local), duplique un plan dans un plan vide |
| `kz_get` | contenu brut d'un objet (diagnostic) |

Toutes les cotes sont en **centimètres**. Sans jeton, on peut travailler sur un `.kzp` local : « ouvre
~/Downloads/mon-plan.kzp » puis « enregistre dans ~/Downloads/mon-plan-modifie.kzp ».

---

## 7. Sécurité et sauvegardes

- **Liste blanche** : le serveur n'enregistre en ligne que les plans de `KZ_ALLOWED_PLANS`.
- **Sauvegardes automatiques** dans `backups/` du dossier de données : `<plan>-<date>-orig.kzp` (à l'ouverture),
  `<plan>-<date>-sent.kzp` (ce qui a été envoyé). Pour revenir en arrière : « ouvre le fichier …-orig.kzp et
  enregistre-le sur le plan 22222222 ».
- Le jeton n'est jamais écrit sur disque par le serveur.
- Les fichiers écrits à la demande de l'assistant sont limités : `.kzp` pour `kz_save`, `.svg` pour `kz_sketch`,
  dossier du `DECOR.md` pour `kz_board`.

---

## 8. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `Variable d'environnement KZ_TOKEN absente` | variable non transmise au serveur | la définir dans la config de l'assistant, relancer |
| `HTTP 401` ou `HTTP 403` | jeton expiré (≈ 7 jours) ou mal copié | récupérer un nouveau jeton |
| `Plan … hors liste blanche` | identifiant absent de `KZ_ALLOWED_PLANS` | l'ajouter, relancer |
| `Catalogue en cours de téléchargement` | premier lancement | patienter quelques minutes |
| `Catalogue absent` / `non téléchargé` | téléchargement interrompu | `kazaplan-mcp catalog` |
| `Placement refusé : chevauche… / débattement…` | pas la place à cet endroit | autre mur, modèle plus petit, ou `force=True` |
| Le planner affiche des blocs jaunes ou refuse d'enregistrer | plan rejeté par le planner | revenir à la sauvegarde `-orig.kzp` et [ouvrir un ticket](https://github.com/padupuy/kazaplan-mcp/issues) |
| Les changements n'apparaissent pas | page du planner non rechargée | recharger l'onglet |

---

## 9. Développement

```
src/kazaplan_mcp/
  kzp.py         conteneur .kzp (WPRJ)
  catalog.py     téléchargement du catalogue, index local, recherche
  geometry.py    géométrie 2D
  plan.py        modèle du plan : résumé, géométrie des pièces, placement, construction
  circulation.py contrôle de circulation
  sketch.py      plans SVG, livrable PLANCHES.md
  section.py     coupes des pièces ; mesh.py : modèles 3D .glb rendus au trait
  api.py         API Kazaplan, sauvegardes ; paths.py : dossier de données
  server.py      serveur MCP (outils kz_*) et CLI
skills/          skills Agent Skills
tests/           tests (plan synthétique, catalogue simulé)
HANDOFF.md       notes techniques : format .kzp, conventions vérifiées, règles du planner
```

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q
```

Pour essayer le plugin Claude Code depuis le dépôt : `claude --plugin-dir .`.

Inspecter un plan :

```bash
python -m kazaplan_mcp.kzp unpack plan.kzp dossier/   # → metadata.json, project.json
python -m kazaplan_mcp.kzp pack dossier/ nouveau.kzp
```

Publication : un tag `v*` publie le paquet sur PyPI (`release.yml`, *trusted publishing*) et l'image
`ghcr.io/padupuy/kazaplan-mcp` (`docker.yml`, aussi `edge` à chaque push sur `main`).

## Licence

[MIT](LICENSE). Leroy Merlin et Kazaplan sont des marques de leurs propriétaires respectifs.

# kazaplan-mcp — notes techniques

Contexte : piloter le planner 3D Leroy Merlin (moteur **Kazaplan**, ex-Wanaplan/Obsidian) depuis un assistant MCP.
Tout ce qui suit a été vérifié sur de vrais plans, sauf mention contraire. En cas de doute, la source de vérité est le
code public du planner : `https://planner.kazaplan.com/planner/index.html` et `chunks/*.js`.

## 1. Architecture de l'outil

- Page `leroymerlin.fr/config-3d/virtual-home` = habillage. Le moteur est un iframe `planner.kazaplan.com/planner/index.html`.
- Config passée dans le hash de l'iframe : `api_url=https://api.kazaplan.com`, `cdn_host=https://cdn.kazaplan.com`,
  `integration=fullrest`, `partnerKey` (LM), `user`, `uuid`.
- Page ↔ iframe : RPC `postMessage` (`{callId, action:"remote-method-call|remote-method-response", chan, ...}`).
- Partner : `partner_id=7`, `partner_uuid=595a5d833027c` (= id de catalogue sur le CDN).

## 2. API

- **Sauvegarde** : `POST https://api.kazaplan.com/plans/save/{id}`
  - `Authorization: Bearer <JWT Kazaplan>` (validité ~7 j, émis à la connexion LM ; scopes `plan:read plan:write …`)
  - multipart : `title`, `userJourney=virtualHome`, `id`, `partnerId=7`, `file=<plan>.kzp` (`application/octet-stream`)
  - réponse : métadonnées du plan + `fileUrl` (URL GCS signée, temporaire) vers le `.kzp`.
- **Lecture** : `GET https://api.kazaplan.com/plans/{id}` (Bearer) → métadonnées (`title`, `version`, `updatedAt`…) + `fileUrl` signée → `.kzp`. **Confirmé** le 2026-10-14.
- Le titre côté serveur (`title` de l'API) peut différer de `project.title` dans le .kzp : `kz_save` réutilise celui de l'API.
- **Création / duplication** : aucun endpoint connu (le site LM bloque la lecture automatisée de ses scripts, le bundle du planner ne contient pas les appels). Le `.kzp` ne contient pas l'id du plan (`metadata.uuid`, `project.id` seulement) : dupliquer = télécharger la source et l'envoyer sur un plan vide créé par l'utilisateur (`kz_copy_plan`, cible en liste blanche, ancienne version archivée `before-copy`). À valider : la copie s'ouvre et s'enregistre dans le planner.
- ⚠️ Ne jamais committer le JWT. Le passer en variable d'environnement `KZ_TOKEN`.

## 3. Format `.kzp` (conteneur WPRJ) — **résolu, testé aller-retour + rechargement dans l'outil**

En-tête 51 octets, entiers big-endian (cf. `kzp.py`, classe `ObsidianProjectFile` du bundle) :

| off | champ |
|---|---|
| 0 | `WPRJ` |
| 4 | version uint16 = 1 |
| 6 | type ASCII 10 car. `WANAPLAN  ` |
| 16/17/21 | metadataFormat u8 / offset u32 (=51) / length u32 |
| 25/26/30 | projectFormat / offset / length |
| 34/35/39 | blobIndexFormat / offset / length |
| 43/47 | blobsOffset / blobsLength |

Formats : 0 = JSON, 1 = `JSON.stringify` + deflate brut niveau 6. Contrôle : taille fichier = 51 + somme des 4 longueurs.
Blob index = `{nom: {offset, length, mime, metadata}}` (vide dans nos plans).

**Test validé** : plan rechargé correctement après suppression de `wall.pane`, `baseboard.baseboard-structure`,
`initParams`, `trackerData` → l'outil les recalcule. Le MCP n'écrit que l'essentiel.

## 4. JSON projet (`__name__: "wnp/project"`)

Unités : **cm**. Plan 2D en `{x, y}` (`babylon-vector2`) ; objets 3D en `{x, y, z}` avec **y = hauteur**, **z = −y du plan** (vérifié : les 25 ouvertures du plan tombent à 0 cm de l'axe de leur mur avec `z = −y`, à des mètres avec `z = +y`).

Rotations (vérifiées) : ouverture `rotation.y = atan2(dy, dx)` de l'axe du mur (extrémité 0 → 1), position = centre de l'ouverture sur l'axe. Modèle : largeur suivant `rotation.y`, face avant (axe local −z) vers `rotation.y + 90°` — déduit de la cheminée `model-2088` dont le dos est collé au mur à 0,1 cm près. Empreinte = `boundings.dimensions × meshScaling` (x → largeur, z → profondeur).

`layers` :
- `ground`, `environment` (skybox), `compass`, `floorHistory`, `catalog` (`catalog-diff.itemDiff` = refs catalogue utilisées)
- `floors` : `[{id, index, referenceHeight:0, ceilingHeight:250, slabThickness:20}]`
- `<floorId>` : liste des objets du niveau :

| `__name__` | champs utiles |
|---|---|
| `wall.wall` | `thickness` (30 ext, 7 cloison, 2 limite terrasse), `serializedHeight`, `connectionExtremities:[{position{x,y}, wallId, targetEdgeIndex, strong}] ×2`, `paneIds` |
| `wall.room` | `type` (`livingdiningRoom`, `bedroom`, `bathRoom`, `wc`, `office`, `entrance`, `otherAnnex`, `terraceext`…), `customName`, `path:[[{x,y}…]]`, `materials.flooring:"catalog:material-XXXX"`, `ceiling`, `paneIds` |
| `wall.pane` | face de mur (calculée) — `roomInfo.id` = pièce vers laquelle elle tourne (`null` = extérieur), `wallInfo.id` = mur ; revêtement : `materials: {"wall.pane": "catalog:material-XXXX"}` (relevé sur des murs peints et tapissés dans le planner, 2026-10-14) |
| `opening.casementwindow` / `opening.door` (+ baies) | `parentWallId`, `width`, `height`, `elevation`, `position{x,y,z}`, `rotation.y` (rad), `nbCasement`, `side`, `hinge`, `originCatalogId`, `baseMaterials` |
| `swimming-pool.swimming-pool` | `points[]`, `elevation:-20`, `height`, `waterDepth`, `copingThickness`, `filled` |
| `model.model-structure` | `originCatalogId:"model-NNN"`, `position`, `rotation`, `meshScaling`, `boundings.dimensions{width,depth,height}`, `materials` |

## 5. Catalogue (pas d'API de recherche, fichiers JSON statiques sur le CDN)

```
https://cdn.kazaplan.com/catalogs/common/production/attributes.json
https://cdn.kazaplan.com/catalogs/common/production/product-families-model.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/archives/models.json          ← modèles 3D (meubles)
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/materials.json      ← revêtements
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/materials-prices.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/materials-archive.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/kitchen-blocks.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/kitchen-styles.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/brands.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/menus.json         ← arborescence/catégories
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/partner.json
https://cdn.kazaplan.com/catalogs/595a5d833027c/production/plugins/room-configurator/config.json
https://planner.kazaplan.com/planner/locales/fr.json
```
Références connues pour valider : `model-427` (pergola 319×355×233), `model-2088`, `material-6731` (carrelage sol blanc 60×60).

### Résultats de l'analyse (catalogue téléchargé le 2026-10-14)

- ⚠️ `archives/models.json` ne contient que **178 modèles archivés** (ni `model-427` ni `model-2088`).
  Le vrai catalogue est **`production/models.json`** (67 Mo, 19 631 modèles) + **`production/models-prices.json`** (237 Mo).
- Modèle : `id`, `type` (`prefab` 16 947, `kitchen-parametric`, `composite-object*`, `model`, `virtual`), `label.fr_FR`,
  `attribute` (`width/height/depth`, `brand`, `COLOR` = codes hex, `STYLE`, `MATERIAL`, `MAGNETISM`…), `data.dimensions`,
  `data.elevation`, `data.url` (fiche produit LM), `searchDisabled`, `productFamilyCode`.
- **`data.metadata.structures`** d'un `prefab` = gabarits `model.model-structure` prêts à insérer (positions relatives au prefab).
  9 672 prefabs ne contiennent que des `model.model-structure` → plaçables par le MCP. Les cuisines paramétriques et objets composites ne le sont pas.
- Libellés des valeurs d'attributs (couleurs, styles, matières) : `attributes.json` (`items[].code` → `values[].code/label`). Styles : Design, Essential, Natural, Industrial, Boheme, Neoclassic, Country.
- Prix : `models-prices.json` / `materials-prices.json` = `{id: {magasin: {price, excludingTaxesPrice}}}` → on retient le prix le plus fréquent.
- `menus.json` : 183 menus (`menuType` furnish / decorate / build / kitchen-coach), arborescence via `parents[0].id`,
  contenu via `action.params.items[].id` (`model-…`, `material-…`, ou ids de composants : `door`, `casement-window`, `wall`, `swimming-pool-item`…).
  Ex. `SDB_BAIGNOIRES` (25), `M_CANAPES` (65), `CH_LITS` (63).
- Matériaux sol vs mur : par menu (`CARRELAGE_SOL`, `PARQUET`, `PVC`, `SOL_EXTERIEUR`, `MOQUETTE…` → sol ; `CARRELAGE_MUR`, `PEINTURE`, `PAPIER_PEINT`, `BRIQUETTE_PAREMENT`, `FACADE` → mur).
- Index local : `index.json` (11 979 modèles, 4 049 matériaux) + `templates.json` dans `catalog/` du dossier de données (`paths.py` : `KZ_DATA_DIR`, défaut `~/.cache/kazaplan-mcp`). Construit automatiquement au premier lancement du serveur (thread en tâche de fond, sources jetées après `build`) ou par `kazaplan-mcp catalog` ; `python -m kazaplan_mcp.catalog fetch` / `build` gardent les sources pour l'analyse.

## 6. État du MCP (`src/kazaplan_mcp/`)

- `kzp.py` (déplacé dans le paquet : `python -m kazaplan_mcp.kzp …`), `catalog.py`, `geometry.py`, `plan.py`, `api.py`, `server.py`.
- Lancement : `kazaplan-mcp` (uvx, Docker, plugin Claude Code `.claude-plugin/`, extension Gemini `gemini-extension.json`). Env : `KZ_TOKEN`, `KZ_ALLOWED_PLANS` (liste blanche, séparée par des virgules), `KZ_DATA_DIR` (dossier de données, défaut `~/.cache/kazaplan-mcp`), `KZ_BACKUP_DIR` (défaut `backups/` du dossier de données).
- Outils : `kz_open`, `kz_save` (`out_path` = écriture locale sans envoi), `kz_copy_plan`, `kz_summary`, `kz_room_geometry`, `kz_search_catalog`, `kz_catalog_item`, `kz_place` (`elevation`, `on_top_of`), `kz_add_walls` (raccord T / coin automatique), `kz_add_opening`, `kz_set_room`, `kz_set_material` (`floor:`, `wall:`, `wall:<pièce>:<arête>`, `ground`), `kz_add_pool`, `kz_remove`, `kz_get`, `kz_move`, `kz_check_room`, `kz_sketch` (`out_path` limité aux `.svg`), `kz_board` (`PLANCHES.md` à côté du `DECOR.md`, chemins confinés à son dossier), `kz_copy_plan`.
- CLI : `kazaplan-mcp` (serveur stdio, lance le téléchargement du catalogue s'il manque), `kazaplan-mcp catalog` (mise à jour forcée).
- Sauvegarde : `initParams` et `trackerData` toujours retirés ; `wall.pane` toujours conservés, références orphelines retirées (`_prune_pane_refs`).
- Catalogue : les matériaux portent `colors` (champ `color` du CDN, ex. `GREY|GREEN`, renseigné pour ~180 peintures sur 621).
- Tests : `.venv/bin/python -m pytest` (plan synthétique, catalogue simulé). Lint/format : `ruff`. CI : `.github/workflows/ci.yml`. Guide utilisateur : `README.md`.

### À valider dans l'outil

1. ~~`GET /plans/{id}`~~ et `POST /plans/save/{id}` validés via le MCP (aller-retour : objets et sols relus à l'identique).
2. ~~Orientation des meubles~~ : confirmée visuellement le 2026-10-14 (lit `model-852` : oreillers contre le mur, pied vers la pièce ; baignoire contre la cloison ; carrelage WC visible). Canapé du séjour (dos au mur, entre deux fenêtres) et carrelage du cellier confirmés aussi.
3. Murs / ouvertures / pièces créés par le MCP : **corrigé le 2026-10-14 après un faux « validé »**. Retirer les `wall.pane` en laissant les `paneIds` des murs (86 réfs) et des pièces (54) produit `[WallStructure] wall referencing non-existing pane` + `RoomError: extendedPath computed with empty arrays`, puis un plantage `_updateLinkedPanes` (`Cannot read properties of undefined (reading 'map')`) dans `_onProjectStable` pour les objets liés aux murs (dressings, portes de dressing) : l'historique reste verrouillé (`HistoryError: History has been locked by project-manager.openFromBuffer for too long`), objets en jaune, **enregistrement impossible depuis le planner**. Les autres objets s'affichent : le défaut passe inaperçu sans tenter d'enregistrer dans l'outil. Correctif : `_prune_pane_refs` à chaque sauvegarde (murs/pièces sans `paneIds` = régénérés par l'outil, comme les murs neufs). À revalider : rechargement sans erreur + enregistrement depuis le planner.
4. ~~Clé de matériau d'un `wall.pane`~~ : `materials["wall.pane"]`, relevée le 2026-10-14. À valider : rendu des peintures posées par `kz_set_material("wall:…")`.
7. Gazon : `ground.materials["ground"]` déduit des `defaultMaterials` du planner (`{earth, ground}`), jamais vu dans un fichier enregistré → valider le rendu.
8. Raccords de murs écrits par `kz_add_walls` (T, coin) et `kz_copy_plan` : valider rechargement + enregistrement dans le planner.
5. ~~`boundings.center`~~ : à ignorer — la baignoire `model-1726` posée à la main a `position` = centre d'empreinte (calée à 0,3 cm des deux murs).
   Les `position.y` des gabarits prefab sont des hauteurs absolues d'édition (−20, −40) : le MCP les ramène au sol (y min = sol de la pièce).
6. Prefabs multi-structures : positions relatives (y négatifs observés) à vérifier visuellement.

### Suite
- Publication PyPI (`uvx kazaplan-mcp` sans `--from git+…`) : déclarer le *trusted publisher* sur PyPI, puis pousser un tag `v*`.
- Tracé d'un plan d'après photo (`kazaplan-floorplan`) à valider de bout en bout.

## 7. Règles apprises sur le planner (2026-10-14, code du bundle `planner.kazaplan.com/planner/chunks/`)

- **Ne jamais supprimer de `wall.pane`** des murs existants : le planner ne régénère les faces que pour des murs sans `paneIds` (murs neufs).
- **Ne jamais créer de `wall.room`** : une pièce écrite par le MCP (sans faces) fait planter `room-controller._updateLinkedPanes` (`e.$data._oldPaneIds.map` sur `undefined`, `_oldPaneIds` n'étant posé que par `setPaneIds`) dans `_onProjectStable` → historique verrouillé (`HistoryError … openFromBuffer`), objets restants en jaune, **enregistrement impossible depuis le planner**. Le planner détecte lui-même les pièces fermées (`_rematchRooms`, type `room`) à l'ouverture ; les nommer ensuite (`kz_set_room`).
- Symptôme trompeur : seuls les objets chargés après le plantage restent jaunes (ici les dressings, ajoutés en dernier).
- Les `RoomError: extendedPath computed with empty arrays` (séjour, entrée, bureau) existent aussi sur des plans non modifiés : avertissements d'origine, sans effet.
- Types de pièce valides (table `Xmt` du bundle) : cf. `ROOM_TYPES` dans `plan.py` ; `garage` existe.
- **Jonctions de murs** : extrémité d'une cloison sur le flanc d'un mur = `{wallId: hôte, targetEdgeIndex: 1|3, strong: false}`, position sur la face de l'hôte ; 1 = côté gauche de l'axe a→b (normale `(-u.y, u.x)`), 3 = côté droit ; 0 = extrémité de départ. Coin entre deux murs : `targetEdgeIndex: -1, strong: true`, lien dans les deux sens.
- **Plafond** : `wall.room.materials.ceil` (`getMaterial("ceil")` dans `pane-structure-*.js`, défaut `static:component/room/room-default-material` ; autres clés : `flooring`, `slab`, `intersection`) ; ignoré si `room.ceiling` est faux. Visible seulement en vue 3D. Écrit par `kz_set_material("ceiling:<pièce>")` (2026-10-15), rendu à valider.
- **Pièces recréées** : déplacer des murs ou poser une séparation invisible fait recréer la pièce par le planner (nouvel id, sans sol ni nom) ; la séparation invisible est un `wall.wall` de 2 cm avec `wallRenderer.__name__ = "wall.invisible-renderer"`, `colliderEnabled: false` (comme les limites de terrasse) : `kz_room_geometry` marque l'arête `invisible` (pas de segment libre), le MCP ne la peint pas et ne la compte pas comme obstacle. Réappliquer sol / murs / nom après la sauvegarde de l'utilisateur.
- Validation obligatoire après toute écriture structurelle : recharger le planner, console vidée → pas d'erreur rouge `index-*.js`, puis **enregistrer depuis le planner** (une requête `plans/save` doit partir).

## 8. Skill `kazaplan-decorator` (`skills/kazaplan-decorator/`)

- `SKILL.md` : 9 étapes (ouvrir → charger le `DECOR.md` → relever → planche complète de la pièce → chercher → poser → contrôler → enregistrer → faire valider dans le planner) + règles du planner (§7).
- `references/decor-md.md` (2026-10-15) : format `DECOR.md`, transposition de [DESIGN.md](https://github.com/google-labs-code/design.md) à la décoration — front matter (foyer, `colors`, `paints`, `materials`, `textures`, `elements`, `rooms`) + 8 sections (Intention → À faire / À éviter) + contrôles (`broken-ref`, `unknown-catalog`, `unknown-room`…) faits à la main, pas encore de linter.
- `references/decoration.md` : programme complet par type de pièce (« décore la chambre » = sol, murs, 3 couches de lumière, tapis, textiles, miroir, déco…), principes chiffrés (proportions, assises, 60/30/10, textures, ancien/moderne, carrelages intemporels, miroir sans fenêtre, illusion de hauteur) et ids catalogue vérifiés.
- Leçons des premières décorations : `elevation` l'emporte sur `on_top_of` (qui pose sur la hauteur totale du support, tête de lit comprise) et l'objet support est ignoré par le contrôle de chevauchement ; dessus de matelas ≈ 52. `kz_place` ne connaît pas le débattement des façades de meubles (portes d'armoire) : règle dans `amenagement.md`. Tête du lit superposé `model-5163` du côté de son début d'arête.
- `kz_sketch` / `sketch.py` (2026-10-16) : plan SVG en cm (axe y vers le bas comme le planner ; l'ASCII, essayé d'abord, était illisible) : sols, murs (`_wall_polys`, murs de jardin écartés : à plus de 40 cm des pièces), peinture des panes en liseré (couleur via `paints` du DECOR.md), ouvertures, meubles, tapis, luminaires, pièces voisines estompées par un masque ; objet mural = surélevé et à moins de 6 cm d'un mur ; libellé pris sur `originCatalogId` (l'article choisi) car `catalogId` peut être le modèle de base d'une variante (plaid vert `model-65253` → `model-64800`, rendu brun). `kz_summary` lit encore `catalogId` en premier. Rendu « planche d'architecte » : motifs SVG (`<pattern>` grille, hachures, parquet, bâton rompu si le libellé du sol contient « bâton » ou « chevron », carrelage), épaisseurs de trait et tailles de texte exprimées en pixels écran (`px = 1 / scale`) pour rester lisibles à toutes les échelles ; le débattement d'une porte n'est tracé que pour les portes de la pièce dessinée, côté pièce (le sens réel n'est pas lu dans le `.kzp`) ; tout ce qui déborde est coupé au-dessus du cartouche (`clipPath`).
- Coupes `section.py` / `mesh.py` (2026-10-16) : chaque modèle du catalogue a un `.glb` (`data.asset3d`, `cdn:/cdn/…` servi par `https://cdn.kazaplan.com` sans jeton, non compressé : pas de Draco, seule extension `FB_ngon_encoding`), un symbole vu de dessus (`data.asset2d`, SVG) et une vignette. L'index garde `_asset3d` (préfixe `_` : absent des réponses de recherche) ; `catalog build` à relancer après mise à jour. Repère vérifié sur le canapé `model-1003666` et la bibliothèque `model-1003691` : face avant du `.glb` = −z (comme le −z local du planner), hauteur = +y ; le maillage est remis aux dimensions `boundings × meshScaling` de l'objet posé. L'axe x est pris en miroir de la largeur, comme le ferait la conversion glTF → Babylon (main gauche) ; le planner charge les modèles par son propre code, donc ce miroir **n'est pas vérifié** : à contrôler sur un meuble asymétrique (évier d'un côté, échelle de lit superposé), et si besoin inverser le signe de `width_dir` dans `section._model_view`. Rendu : rastérisation Pillow par ordre de profondeur (peintre), traits = arêtes vives (> 28°), sauts de profondeur (> 2 cm) et silhouette, PNG en base64 dans le SVG (un SVG chargé en `<img>` ne lit pas de fichier externe), cache `catalog/elevations/` du dossier de données. Coupe = moitié de la pièce côté mur (120 à 180 cm de profondeur) ; murs retenus : les deux plus garnis (largeur des meubles à moins de 60 cm + moitié des ouvertures).
- `kz_check_room` / `circulation.py` (2026-10-16) : règles de circulation Côté Maison + rayon.design. Dégagements mesurés par rayons depuis 3 points de chaque face (avant vers θ + 90°) jusqu'au premier obstacle (mur, meuble au sol, hors des pièces) ; chemins par grille de 5 cm + transformée de distance (chanfrein), largeur 60 et 90, depuis la première porte de la pièce. Faux positifs écartés : chaise contrôlée seulement si attablée, console (profondeur < 60) n'est pas une table, lit superposé n'a pas de côtés, meubles de cuisine ignorés entre eux, tabouret de bar sans menu reconnu par son libellé, arête sans mur < 60 cm ignorée.
- `kz_move` (2026-10-16) : translation d'un modèle et des objets posés dessus (y0 = dessus ± 2 cm, centre dans l'empreinte), refus en cas de collision ou de sortie des pièces.
- Catalogue : pas de grand tapis hors `model-1003711` (jute 189 × 263) → redimensionner ; pas de verre ambré ; zellige et terre cuite sans `usage` (rendu mural / sol à vérifier).
- `references/amenagement.md` : cotes d'ergonomie par pièce, codes de catégorie catalogue, recette placards.
- `references/styles.md` : fiches style avec mots-clés catalogue testés (scandinave, industriel, bohème, contemporain, d'après photos).

## 9. Skill `kazaplan-floorplan` (`skills/kazaplan-floorplan/`)

- Duplication (`kz_copy_plan`) et tracé d'un plan vierge d'après la photo d'un plan : relevé (échelle, repère x droite / y bas, axes des murs), validation du relevé par l'utilisateur, tracé (`kz_add_walls` 30 / 7, `kz_add_opening`), détection des pièces par le planner, nommage (`kz_set_room`).
- Non testé de bout en bout : orientation (miroir possible si le planner affiche y vers le haut) et raccords de cloisons à valider au premier tracé.

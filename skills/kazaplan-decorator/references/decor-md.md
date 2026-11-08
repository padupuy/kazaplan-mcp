# Format DECOR.md

`DECOR.md` décrit l'identité décorative d'une maison, comme [`DESIGN.md`](https://github.com/google-labs-code/design.md) décrit l'identité visuelle d'un produit numérique. C'est le moodboard écrit de la maison : chaque pièce décorée s'y réfère, et deux pièces décorées à des jours d'écart restent de la même maison.

Deux couches, comme DESIGN.md :

1. **Front matter YAML** (entre deux `---`) : les jetons normatifs — couleurs, matières, proportions, éléments types, programme par pièce — reliés aux articles du catalogue (`material-…`, `model-…`).
2. **Corps Markdown** : l'intention, en sections `##`, qui dit comment appliquer les jetons.

Les jetons font foi ; la prose explique quand et pourquoi.

## Emplacement

Un `DECOR.md` par maison, dans le dossier de travail de l'utilisateur (par défaut `decor/<maison>/DECOR.md`). La clé `plans` liste les ids des plans concernés (réel et bac à sable) : `grep -rl <plan_id> --include=DECOR.md .` retrouve le fichier.

## Front matter

| Clé | Requis | Contenu |
|---|---|---|
| `version` | non | `alpha` |
| `name` | oui | nom de la maison |
| `description` | non | une phrase : l'ambiance et pour qui |
| `plans` | oui | ids des plans Kazaplan |
| `household` | oui | `residents`, `visitors`, `sleeping` (couchages), `needs` (contraintes du quotidien) |
| `colors` | oui | jetons couleur, valeur hex ; `primary` (base 60 %), `secondary` (30 %), `accent` (10 %) obligatoires |
| `paints` | non | jeton couleur → peinture du catalogue (`material-…`) |
| `materials` | oui | matières : `catalog` (revêtement `material-…`, si applicable), `use`, `finish` |
| `textures` | non | matières des objets (lin, laine, rotin…) : mots-clés de recherche catalogue |
| `proportions` | non | cotes de la maison et règles chiffrées propres à elle (cm) |
| `shapes` | non | formes dominantes (arrondis, arches, lignes droites) |
| `elements` | non | éléments types réutilisés d'une pièce à l'autre : `category`, `catalog`, `color`, `material`, `size` |
| `rooms` | oui | une entrée par pièce : `name` (nom dans le plan), `users`, `uses`, `floor`, `walls`, `ceiling`, `accent`, `program`, `done` (ce qui a été posé, daté) |
| `omitted` | non | sections laissées de côté volontairement, avec la raison |

Une valeur peut référencer un autre jeton : `{colors.sage}`, `{materials.oak}`, `{elements.rug-bed}`.

## Corps : sections dans cet ordre

1. **Intention** — l'ambiance en une phrase, 5 à 8 mots-clés, ce que la maison raconte, références (photos, Pinterest).
2. **Palette** — rôle de chaque couleur, règle 60 / 30 / 10, où va la tonalité riche.
3. **Matières et textures** — bois, métaux, textiles, carrelages ; comment on les superpose.
4. **Lumière** — trois couches (générale, fonctionnelle, ambiance), température, luminaires types.
5. **Proportions et circulation** — volumes, hauteur sous plafond, passages, illusions (hauteur, profondeur).
6. **Formes** — courbes / lignes, ancien / contemporain, proportion de chacun.
7. **Pièces** — pour chaque pièce : qui, quand, pour quoi faire ; ce qui la distingue des autres.
8. **À faire / À éviter** — règles courtes, testables sur le plan.

Sections facultatives ; celles présentes suivent cet ordre, chaque titre n'apparaît qu'une fois.

## Livrable : PLANCHES.md

`kz_board(<chemin du DECOR.md>)` écrit, pour le plan ouvert, à côté du `DECOR.md` un `PLANCHES.md` : vue d'ensemble 2D (`plans/maison.svg`), nuancier en cartes (`swatches/palette.svg`) et tableau des pièces (surface, peinture des murs, sol), puis une section numérotée par entrée de `rooms` : surface et usages, plan coté `plans/<clé>.svg` (peinture de chaque mur en liseré, repères de coupe, cartouche), deux coupes `plans/<clé>-coupe-<n>.svg` (les murs les plus garnis vus de l'intérieur : peinture, ouvertures, meubles de la moitié de pièce dessinés d'après leur modèle 3D, silhouette de 1,75 m, cotes), tableau des revêtements (murs, plafond, accent, sol avec pastilles `swatches/*.svg`) et nomenclature (code du plan, quantité, dimensions, emplacement : au sol, au mur, sur un meuble, plafond). En dehors d'une session, `python -m kazaplan_mcp.sketch board <plan_id | plan.kzp> <DECOR.md>` fait de même ; avec un id, il lit la dernière sauvegarde horodatée (celle de `kz_save`). Le fichier est généré : ne pas l'éditer à la main.

## Contrôles (à faire à la main en attendant un linter)

| Règle | Gravité | Vérifie |
|---|---|---|
| `broken-ref` | erreur | chaque `{…}` pointe vers un jeton existant |
| `unknown-catalog` | erreur | chaque `material-…` / `model-…` existe (`kz_catalog_item`) |
| `unknown-room` | erreur | chaque `rooms.*.name` est une pièce du plan (`kz_summary`) |
| `missing-role` | avertissement | `primary`, `secondary`, `accent` présents |
| `accent-overflow` | avertissement | une pièce a au plus un mur d'accent |
| `no-program` | avertissement | une pièce sans `program` (on décorera avec le programme type de `decoration.md`) |
| `section-order` | avertissement | sections hors de l'ordre canonique |

## Squelette

```markdown
---
version: alpha
name: <Maison>
description: <ambiance, pour qui>
plans: ["<id réel>", "<id bac à sable>"]
household:
  residents: <qui vit là>
  visitors: <qui vient, à quelle fréquence>
  sleeping: <nombre de couchages>
  needs:
    - <contrainte>
colors:
  primary: "#ede6de"
  secondary: "#ddd1c1"
  accent: "#2f5d53"
paints:
  primary: material-5258
materials:
  oak:
    catalog: material-6214
    use: sols des chambres
textures:
  linen: [lin, "lin lave"]
elements:
  rug-bed:
    category: DECO_TEXTILE
    size: "2/3 bas du lit, 50 de débord"
rooms:
  chambre-1:
    name: Chambre 1
    users: <qui>
    uses: [dormir, lire]
    floor: "{materials.oak}"
    walls: "{colors.primary}"
    accent: { color: "{colors.accent}", wall: tête de lit }
    program: [lit, chevets, liseuses, tapis, miroir, rideaux, cadre, plante]
---

## Intention
## Palette
## Matières et textures
## Lumière
## Proportions et circulation
## Formes
## Pièces
## À faire / À éviter
```

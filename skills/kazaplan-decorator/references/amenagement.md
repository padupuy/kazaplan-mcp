# Règles d'aménagement

Cotes en cm. `kz_place` pose la face avant d'un meuble vers l'intérieur de la pièce quand il est contre un mur ; `w` = largeur le long du mur, `d` = profondeur.

## Circulation (à vérifier avec `kz_check_room`)

Sources : Côté Maison, [règles de circulation](https://www.cotemaison.fr/renover/plan-interieur/les-regles-de-circulation-pour-une-maison-agreable-a-vivre-13443) ; [rayon.design](https://www.rayon.design/knowledge-base/living-room/dimensions) (dimensions par pièce).

- **Tracer les chemins avant de meubler** : de la porte d'entrée de la pièce vers chaque autre porte, porte-fenêtre et passage ouvert. Les meubles se posent autour, jamais dessus. Passage : 60 au minimum, 90 confortable, 120 dans les lieux de va-et-vient (cuisine, entrée).
- **Ne pas traverser une zone pour aller ailleurs** : si l'on passe du salon à la salle à manger ou à la cuisine, prévoir une circulation parallèle qui contourne la zone canapé et le coin cheminée.
- **Cotes minimales**, contrôlées par `kz_check_room` :

| Où | Cote |
|---|---|
| Canapé → table basse | 60 |
| Table à manger → mur ou obstacle (chaises non comprises) | 110 |
| Derrière une chaise attablée | 75 |
| Îlot, table haute ou meuble de cuisine → vis-à-vis | 90 (120 confortable) |
| Devant une armoire, un dressing | 75 (+ largeur d'un vantail si battant) |
| Devant un buffet, une commode | 60 |
| Côtés d'un lit double, pied de lit | 60 |
| Réfrigérateur posé au sol | 7 de chaque côté |
| WC | centré dans 80 de large |

- **Faire du vide** : ne garder que les meubles qui répondent à un usage ; chaque coin a une fonction (couloir → bibliothèque, coin lecture), sinon il reste libre.
- **Point focal** : un élément dominant par pièce (cheminée, baie, mur d'accent, œuvre) ; les assises s'organisent autour, la télé ne se met pas à côté.
- **Entrée = sas** : un endroit pour s'asseoir et se déchausser, accrocher les manteaux, poser les clés.
- `kz_check_room(<pièce>)` après chaque pose : `issues` (dégagements sous la cote) et `paths` (chemins de 60 / 90 entre ouvertures). Corrige avec `kz_move(<id>, dx, dy)`, qui déplace aussi ce qui est posé dessus.
- Débattement des portes : jamais encombré (`kz_place` le refuse).
- Fenêtres : sous une allège (souvent 95), seulement des meubles plus bas (radiateur, banquette, buffet bas) ; `kz_place` refuse ce qui masque.
- Radiateurs : centrés sous les fenêtres (`under_opening`), sinon sur un mur extérieur plein.
- Tapis : posé en `x`/`y` sous la zone qu'il unifie (`force=True` pour le laisser passer sous la table ou le canapé) ; règles de placement dans `decoration.md`.

## Salon / séjour

- Canapé face à la source de lumière ou au point focal (cheminée, baie, TV), dos à un mur plein ou flottant avec 90 de passage derrière.
- Table basse à 60 du canapé, longueur ≈ 2/3 du canapé (70-120 de côté).
- TV : distance ≈ 3 × diagonale ; meuble TV face au canapé, jamais à côté de la cheminée ; largeur du meuble selon l'écran (32-42" → 90 × 40, 43-55" → 115 × 45, 56-67" → 160 × 50). Si cheminée et télé se disputent le mur, deux pôles : canapé face à la télé, fauteuils tournés vers le feu.
- Fauteuil(s) en L ou face au canapé, ≤ 2,5 m pour la conversation.
- Lampadaire près d'un angle du canapé ; suspension au-dessus de la table basse ou du centre de la zone.
- Coin repas : 75 de dégagement derrière chaque chaise ; table 6 personnes ≈ 180 × 90.

## Chambre

- Tête de lit contre un mur plein, pas sous une fenêtre ni face à la porte si évitable ; 60-70 de passage de chaque côté du lit double, 90 au pied.
- Chevets de part et d'autre (≈ 45 de large), armoire / dressing sur le mur le plus long sans fenêtre.

## Cuisine

- Triangle évier / plaque / frigo : chaque côté 120-270, somme ≤ 600.
- Meubles bas : profondeur ≈ 60, hauteur ≈ 90 ; meubles hauts à 145-150 du sol ; colonnes (four, frigo) en bout de linéaire.
- Plaque et évier : jamais en angle direct ; 40 de plan libre de chaque côté de la plaque.
- Îlot : 100-120 de circulation autour ; tabourets côté séjour (25 cm de débord de plan).
- Hotte au-dessus de la plaque ; évier de préférence sous la fenêtre.
- Catalogue : meubles bas `C_MEUBLE_BAS`, hauts `C_MEUBLE_HAUT`, colonnes `C_COLONNE`, électroménager `C_ELECTROMENAGER`, luminaires `C_LUMINAIRE`. Les plans de travail (`C_PLAN_TRAVAL`) ne sont pas plaçables : signale-le.

## Salle de bain

- Devant lavabo / WC / douche : 70 libres ; WC à 20 minimum d'un mur latéral (axe à 40).
- Sèche-serviettes près de la douche ou de la baignoire, hors fenêtre.

## Lumière

- Suspension : bas de l'abat-jour à 75 au-dessus d'une table, ≥ 210 du sol au-dessus d'un passage ; garder les modèles dont `elevation + h` ≈ hauteur sous plafond (250), sinon ils flottent ou percent le plafond.
- Salle de bain : plafonnier `SDB` (IP44) + appliques de part et d'autre du miroir à ≈ 170 (`elevation`).
- Lampes à poser : `on_top_of` sur chevet, buffet ou bureau.

## Murs

- Catalogue : `PEINTURE`, `PAPIER_PEINT`, `CARRELAGE_MUR` (`kind="material"`, `usage="wall"`). Les libellés de peinture (« FJORD 1 ») ne disent pas la teinte ; le filtre `color` n'en couvre qu'un tiers. Teintes relevées sur les échantillons (2026-10-14) :

| Teinte | Peinture |
|---|---|
| blanc chaud | `material-5258` PAPER 5 #ede6de, `material-5298` CREAM 5 #f0eee1 |
| sable / lin | `material-5737` BEIGE LIN #ddd1c1, `material-5322` KENYA 5 #d4c09b |
| argile / terracotta | `material-5238` EVA 3 #c5a993, `material-5417` COTTA 4 #c88362 |
| sauge | `material-5373` CACTUS 5 #a6bfa2, `material-5273` BALI 2 #849e7b |
| bleu doux | `material-5340` PARIS 6 #adbac2, `material-5331` FJORD 6 #b5d1dc |
| vert profond | `material-5276` EXOTIC 1 #2f5d53 |

- Une base claire sur tous les murs (`wall:<pièce>`), puis au plus un mur d'accent (`wall:<pièce>:<arête>`) : tête de lit, mur du point focal (cheminée), mur derrière le bureau.
- Salle de bain : faïence (`CARRELAGE_MUR`) sur le mur de la douche, peinture ailleurs.
- Séparation invisible (arête `invisible` dans `kz_room_geometry`) : rien à peindre, rien à adosser.

## Codes de catégorie (`category` de `kz_search_catalog`)

| Pièce | Codes |
|---|---|
| Séjour | `M_CANAPES`, `M_FAUTEUIL`, `M_TABLES`, `M_CHAISES`, `M_MEUBLE_TV`, `M_BUFFETS`, `M_BIBLIOTHEQUES`, `M_ETAGERES` |
| Déco / lumière | `DECO_TEXTILE` (tapis, coussins, plaids), `DECO_RIDEAUX`, `DECO_MURALE`, `DECO_OBJETS`, `DECO_FLEURS_PLANTES`, `DECO_SUSPENSIONS`, `DECO_LAMPADAIRES`, `DECO_LAMPES`, `DECO_APPLIQUES_SPOTS` |
| Chambre | `CH_LITS`, `CH_MEUBLE`, `CH_LUMINAIRES`, `M_ARMOIRES`, `D_DRESSING_OUVERTS`, `D_PORTES` |
| Cuisine | `C_MEUBLE_BAS`, `C_MEUBLE_HAUT`, `C_COLONNE`, `C_ELECTROMENAGER`, `C_LUMINAIRE`, `C_DECO` |
| Salle de bain | `SDB_MEUBLES_VASQUE`, `SDB_BAIGNOIRES`, `SDB_DOUCHES`, `SDB_WC`, `SDB_MIROIRS`, `SDB_SECHES_SERVIETTE`, `SDB_ACCESSOIRES` |
| Enfant | `ENF_MEUBLES` (commodes, coffres à jouets), lits superposés : mot-clé `superpose` |
| Bureau | `B_BUREAUX`, `B_CHAISES`, `B_ACCESSOIRES` |
| Chauffage | `T_RADIATEURS`, `T_CHEMINEES` |
| Extérieur | `JAR_GARDENSET`, `JAR_TABLE`, `JAR_CHAISE`, `JAR_TRANSAT`, `JAR_OMBRAGE` (pergolas), `JAR_ABRIS_SERRES`, `JAR_PISCINES` |
| Sols | `kind="material"`, `usage="floor"` ; murs : `usage="wall"` (application murale pas encore supportée) |

## Placards / dressings

Caissons `D_DRESSING_OUVERTS` (≈ 100 × 58) contre le mur avec `offset` consécutifs, puis portes `D_PORTES` à la même `offset` avec `gap` = profondeur du caisson + 1 (ex. 59).

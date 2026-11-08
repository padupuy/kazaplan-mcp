# Décoration : principes et programme par pièce

Cotes en cm. Complète [`amenagement.md`](amenagement.md) (ergonomie, codes catalogue, teintes de peinture) ; les choix de couleurs et de matières viennent du `DECOR.md` de la maison ([`decor-md.md`](decor-md.md)).

## Programme complet par pièce

« Décore la chambre » = toute la pièce, pas trois objets. Chaque couche est posée ou écartée avec sa raison (« pas de miroir : armoire à porte miroir déjà là »).

| Couche | Chambre | Séjour | Bureau | Salle de bain | Entrée / couloir |
|---|---|---|---|---|---|
| Sol | parquet / revêtement | idem | idem | carrelage | carrelage résistant |
| Plafond | peinture claire | idem | idem | peinture claire | idem |
| Murs | base + accent tête de lit | base + accent point focal | base + accent derrière le bureau | faïence douche + peinture | base claire |
| Lumière générale | suspension / plafonnier | suspension(s) | suspension | plafonnier IP44 | plafonnier / spots |
| Lumière fonctionnelle | 2 liseuses ou lampes de chevet | lampe de lecture près du fauteuil | lampe de bureau | appliques du miroir | — |
| Lumière d'ambiance | lampe à poser sur commode | lampadaire + lampe sur buffet | lampe sur étagère | — | lampe sur console |
| Mobilier principal | lit, 2 chevets | canapé, fauteuils, table basse, table | bureau, chaise | meuble vasque | console, banc |
| Rangement | armoire / commode | buffet, bibliothèque | bibliothèque | colonne / étagère | patères, coffre |
| Assise d'appoint | banc de bout de lit ou fauteuil | poufs, banc | fauteuil de lecture | tabouret | banc pour se chausser |
| Tapis | sous le lit (2/3 bas) | sous la zone salon | sous le bureau si parquet | tapis de bain | tapis plat |
| Textiles | rideaux, plaid, coussins | rideaux, coussins, plaid | rideaux | serviettes (hors catalogue) | — |
| Miroir | mural ou sur pied | au-dessus du buffet / cheminée | — | au-dessus de la vasque | face ou à côté de l'entrée |
| Déco murale | cadre(s) au-dessus de la tête de lit | cadres, étagères | tableau d'affichage, cadres | — | cadres |
| Végétal | 1 plante | 2-3 plantes de hauteurs différentes | 1 plante | 1 plante si fenêtre | 1 plante |
| Objets | 1-2 sur commode | sur buffet, table basse | sur étagère | — | vide-poche |

## Proportions

- **Occupation** : meubles au sol ≤ 2/3 de la surface ; garder une surface libre lisible (≥ 2 m² de jeu dans une pièce où viennent des enfants).
- **Canapé** ≈ 2/3 du mur qu'il longe ; table basse ≈ 2/3 du canapé.
- **Tapis** ([Côté Maison](https://www.cotemaison.fr/pieces/salle-a-manger-salon/ou-placer-un-tapis-dans-le-salon-15217)) : jamais un timbre-poste ; il structure l'espace. Dans un séjour ouvert, un tapis XXL délimite le salon et toutes les assises y reposent (au moins leurs pieds avant), le canapé le laisse dépasser ; centré sur la suspension ; la table basse au milieu. Un petit tapis cadre un coin lecture (sous le fauteuil), un tapis doux se pose au pied de la cheminée, on peut superposer un petit tapis contrasté sur un grand. Tailles courantes au salon : 160 × 220 à 200 × 300. Chambre : sous les 2/3 bas du lit, débord de 50-60 de chaque côté et au pied : posé en travers du lit, lit 140 × 190 → tapis ≈ 240 × 180 ; lit 160 × 200 → ≈ 270 × 190 (ou 200 × 300 en travers, dimension courante). Le catalogue a peu de grands tapis : redimensionne avec `width` / `depth` de `kz_place`.
- **Au-dessus d'un meuble** (cadre, miroir, tête de lit) : largeur 2/3 à 3/4 du meuble, bas à 15-25 au-dessus ; un cadre isolé a son centre à 145-150 du sol.
- **Suspension** : diamètre ≈ (longueur + largeur de la pièce en m) × 8 cm (pièce 3,5 × 3 → ≈ 50) ; au-dessus d'une table : diamètre ≈ 1/2 à 2/3 de la largeur de la table.
- **Chevets** : plateau à ± 5 du dessus du matelas, largeur 50-60, hauteur 60-70.
- **Rideaux** : tringle au ras du plafond, largeur 1,5 à 2 × la fenêtre, tombée au sol ; un panneau de chaque côté de la fenêtre.

## Assises suffisantes

- Séjour : assises = résidents + invités réguliers (`household` du DECOR.md), dont des places basses et mobiles pour les enfants (poufs, banc, coussins de sol) ; table à manger pour tout le monde les jours de visite (allonge, banc).
- Pour des aînés : assises fermes à accoudoirs, hauteur d'assise 45-50 ; un fauteuil « à soi » avec lampe de lecture et petite table.
- Chambres : un banc ou un fauteuil pour poser un sac et s'habiller.

## Adapter l'espace au quotidien

- Avant de choisir un meuble, écrire qui utilise la pièce, quand, pour quoi faire (`rooms.*.uses`). Chaque usage a son équipement : lire au lit → liseuses ; devoirs → bureau + lampe ; jeux → tapis libre + coffre bas ; arrivée des visiteurs → banc et patères.
- Ranger là où on utilise : jouets en bas (coffre, étagère basse), objets fragiles au-dessus de 100.
- Contraintes du foyer (`household.needs`) avant l'esthétique.

## Tonalités riches

- Règle 60 / 30 / 10 : base claire (murs, grandes surfaces), couleur secondaire (meubles, textiles), accent riche (vert profond, terracotta, bleu canard, ocre, prune).
- La tonalité riche va sur un mur d'accent, un textile de velours ou un meuble — pas partout.
- Règle de trois : une couleur d'accent revient au moins trois fois dans la pièce (mur, coussin, cadre ou vase), à des hauteurs différentes.

## Superposer textures et matières

- Au moins trois matières par pièce (bois, textile, métal ou céramique, végétal) et un contraste : mat / brillant, lisse / rugueux, lourd / léger.
- Superposer : tapis sur parquet, plaid et coussins sur le lit ou le canapé, rideau en lin devant un mur peint, panier en rotin à côté d'un meuble laqué.
- Dans le catalogue, les matières se lisent dans `materials`, `colors` et le libellé : cherche par mot-clé (`lin`, `jute`, `rotin`, `velours`, `laiton`, `noyer`).
- Une variante de couleur peut s'afficher dans la teinte de son modèle de base : le plaid « Lazo vert » `model-65253` sort brun foncé (`#5C5244`, matériau du gabarit `model-64800`). Pour un accent de couleur, vérifie au rendu ou préfère un objet dont la couleur est dans le modèle lui-même (peinture, lampe « bois vert »).

## Marier traditionnel et moderne

- Dosage 80 / 20 ou 70 / 30 : une base d'une époque, des touches de l'autre.
- Une pièce de caractère par pièce (armoire, commode, buffet bois, cadre doré, miroir ancien) avec un luminaire et des lignes contemporaines ; ou l'inverse.
- Les deux mondes se répondent par une couleur ou une matière commune (le laiton du cadre et de l'applique, le bois du buffet et des chevets).

## Carrelages intemporels

Choisis-les pour salle de bain, cuisine, entrée, WC ; une seule vedette par pièce, le reste neutre.

| Carrelage | Usage | Catalogue |
|---|---|---|
| Métro blanc mat | crédence, mur de douche | `material-6776` (7,5 × 15), `material-6790` (7,5 × 30) |
| Métro sauge / vert fumé | mur de douche, crédence | `material-6781`, `material-6782` |
| Zellige | crédence, mur de douche, niche | `material-1002634` vert, `material-1002633` bleu, `material-1002635` beige (pas d'`usage` : vérifier le rendu) |
| Damier | entrée, WC, salle de bain | `material-195` (40 × 40 vieilli) |
| Terre cuite / tomette | entrée, cuisine, cellier | `material-4545` Terracotta Antique (matière, pas d'`usage` : vérifier) |
| Ciment | salle de bain, cuisine | `material-6681` ciment beige, `material-7208` PVC carreau ciment bleu |
| Marbre | salle de bain, entrée | `material-2683` blanc 60 × 60, `material-6837` mural blanc |

## Pas de fenêtre ? Un miroir

- Une pièce ou un mur sans fenêtre (`kz_room_geometry` : aucune ouverture `window`) reçoit un grand miroir, face ou perpendiculaire à la source de lumière (porte ouverte sur une pièce éclairée, lampe).
- Dans une pièce avec fenêtre, le miroir perpendiculaire à la fenêtre double la lumière sans éblouir.
- Grand format (≥ 70 × 100 ou rond ≥ 55) ; pas de miroir là où un enfant court (préférer un miroir fixé, haut).
- Catalogue : `model-1147` (120 × 70), `model-1146` (100 × 70), `model-56327` rond bambou Ø 55, `model-58853` / `model-57513` sur porte 32 × 122 ; `SDB_MIROIRS` pour la salle de bain.

## Illusion de hauteur

- Bibliothèques jusqu'au plafond : modèle haut (`model-3022` 82 × 210) étiré avec `height` à hauteur sous plafond − 2 ; plusieurs côte à côte pour un mur entier.
- Suspensions qui descendent généreusement (verre, bas à 75 au-dessus de la table) : le regard monte le long du fil. Le catalogue n'a pas de verre ambré : `model-1003395` verre bulle crème, `model-1002681` boule verre et laiton, `model-63166` fer noir et laiton.
- Rideaux du plafond au sol, cadres en colonne, meubles bas sous une fenêtre, peu d'objets au-dessus de 200.
- Plafond plus clair que les murs (ou de la même teinte) ; murs clairs, mur d'accent sur toute la hauteur (pas de soubassement qui coupe la pièce en deux).

## Mise en œuvre avec les outils

- Sol : `kz_set_material("floor:<pièce>", …)`. Plafond : `ceiling:<pièce>` (rendu visible seulement en vue 3D). Murs : `wall:<pièce>` puis accent `wall:<pièce>:<arête>`.
- Suspension : `x`/`y` au centre de la zone, `elevation` = 250 − hauteur du modèle (ou bas à 75 au-dessus d'une table).
- Applique, liseuse : `against_wall` + `offset` + `elevation` (liseuse ≈ 110-120 au-dessus du sol, à l'aplomb de chaque chevet).
- Miroir, cadre : `against_wall` + `elevation` calculée depuis le centre visé (145) ou depuis le meuble dessous.
- Tapis : `x`/`y`, `width`/`depth` aux cotes voulues, `force=True` (il passe sous le lit).
- Lampe, vase : `on_top_of=<id>` (posé sur la hauteur totale du meuble). Plaid, coussins sur un lit : la hauteur du lit inclut la tête de lit ; passe `on_top_of` + `elevation=52` (dessus du matelas, cf. lits sans tête de lit du catalogue à 52), `x`/`y` vers la tête pour les coussins, au pied pour le plaid.
- Rideaux : deux panneaux par fenêtre, `against_wall` avec `offset` de part et d'autre de l'ouverture.

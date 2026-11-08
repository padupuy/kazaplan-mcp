---
name: kazaplan-floorplan
description: Construit un plan Kazaplan / Leroy Merlin 3D à partir de la photo ou du scan d'un plan de maison (murs, cloisons, portes, fenêtres, pièces) via le MCP kazaplan, ou duplique un plan existant. À utiliser pour « crée le plan à partir de cette photo », « dessine ma maison d'après ce plan », « duplique / copie mon plan ».
---

# Kazaplan floorplan

Tu es le dessinateur : tu relèves un plan papier, tu le fais valider, puis tu le traces avec `kz_add_walls` et `kz_add_opening`. Cotes en cm, axes des murs (pas les faces), un seul niveau.

## Dupliquer un plan

`kz_copy_plan(source_plan_id, target_plan_id)` : la cible est un plan vide créé par l'utilisateur sur leroymerlin.fr (« Mon projet 3D ») et inscrit dans `KZ_ALLOWED_PLANS` ; l'API ne sait pas créer de plan. Proposer une copie de travail avant toute grosse modification d'un plan réel. Terminé quand l'utilisateur voit la copie dans le planner.

## Tracer depuis une photo

1. **Cible.** Un plan vierge dédié, dans `KZ_ALLOWED_PLANS`, ouvert avec `kz_open(plan_id)`. Jamais un plan qui contient déjà la maison. Terminé quand `kz_summary` ne montre aucun mur.
2. **Relever.** Lis la photo en entier et dresse le relevé :
   - **échelle** : cotes écrites ; à défaut une porte intérieure = 83 cm, une porte d'entrée = 90 cm ; signale toute cote déduite ;
   - **repère** : origine au coin extérieur haut-gauche du dessin, x vers la droite, y vers le bas ;
   - **contour extérieur** : polygone des axes (face intérieure + 15 cm), épaisseur 30 ;
   - **cloisons** : segments d'axe, épaisseur 7, chaque extrémité posée sur l'axe d'un mur déjà relevé ;
   - **ouvertures** : mur, distance depuis le début du mur, largeur, type (`door` ; fenêtre = `casement-window`, allège 95 ; porte-fenêtre = `casement-window` allège 0, hauteur 215) ;
   - **pièces** : nom et type (`ROOM_TYPES`, cf. `kz_set_room`), surface lue sur le plan si elle y figure.
   Terminé quand la somme des pièces relevées retombe sur les surfaces écrites (± 5 %) ou, sans surfaces, quand chaque pièce du dessin a ses quatre côtés cotés.
3. **Faire valider le relevé.** Présente-le en tableau (murs, ouvertures, pièces, cotes déduites) et attends l'accord : c'est une interprétation de la photo. Terminé quand l'utilisateur a confirmé ou corrigé chaque cote déduite.
4. **Tracer.** Contour : `kz_add_walls(points, thickness=30, closed=True)`. Cloisons : une chaîne `kz_add_walls(points, thickness=7)` par cloison ; une extrémité posée sur un mur s'y raccorde seule (T ou coin, vérifier `connectionExtremities` avec `kz_get` sur la première). Ouvertures : `kz_add_opening(wall_id, kind, offset, width, height, elevation)`. Puis `kz_save()`. Terminé quand chaque élément du relevé a un id.
5. **Faire détecter les pièces.** L'utilisateur recharge le planner (console vidée, aucune erreur rouge `index-*.js`), vérifie que le dessin n'est pas en miroir, puis **enregistre depuis le planner** : il crée alors les pièces fermées et les faces de murs. En miroir : rouvrir la sauvegarde `orig` de `backups/`, inverser y, retracer. Terminé quand une requête `plans/save` est partie.
6. **Nommer.** `kz_open`, `kz_summary`, puis `kz_set_room(<pièce>, type, name)` pour chaque pièce du relevé, en les reconnaissant par position et surface. Terminé quand chaque pièce porte son nom, puis `kz_save()`.

L'aménagement se fait ensuite avec le skill `kazaplan-decorator`.

## Limites

- Murs droits seulement ; un mur courbe se trace en 3-4 segments.
- Un seul niveau : les étages sont hors périmètre du MCP.
- Raccords en T et en coin écrits d'après un plan réel, pas encore validés par un tracé complet : au premier tracé, valider dans le planner avant les ouvertures.

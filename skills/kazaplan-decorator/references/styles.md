# Fiches style

Une fiche sert de point de départ au `DECOR.md` d'une maison qui n'en a pas (palette → `colors`, matières → `materials` / `textures`, mots-clés → `elements`) ; une fois le `DECOR.md` écrit, c'est lui qui fait foi. Chaque fiche donne la palette, les matières, les meubles types et les **mots-clés catalogue** testés. Le filtre `style` de `kz_search_catalog` ne couvre que les styles du catalogue (Design, Essential, Nature, Industrial, Boheme, Country charm, Néoclassique) ; combine toujours mot-clé + `category`, puis vérifie `colors` / `materials` / libellé.

## Scandinave

- Palette : blanc, gris clair, beige, bois clair ; une touche de bleu pâle, vert sauge ou moutarde.
- Matières : chêne / bois clair, lin, laine, rotin, métal blanc ou noir fin.
- Meubles types : canapé tissu gris clair à pieds bois, fauteuil bois + tissu, table basse ronde bois clair ou blanche, meuble TV bas blanc / chêne, étagère murale, tapis laine clair, lampadaire trépied, suspension blanche ou bois, plantes vertes, coussins et plaid texturés.
- Mots-clés : `scandinave`, `chêne`, `bois clair`, `blanc`, `lin`, `rotin` ; filtre `style="Nature"` ou `"Essential"` ; couleurs `Blanc`, `Gris`, `Beige`.
- À doser : peu d'objets, lignes simples, beaucoup de vide.

## Industriel

- Palette : noir, gris anthracite, brun cuir, brique.
- Matières : métal noir, bois brut / foncé, cuir, béton.
- Meubles types : canapé cuir brun ou tissu gris foncé, table basse métal + bois, étagère métal, suspension métal noir, lampadaire articulé.
- Mots-clés : `industriel`, `métal noir`, `cuir` ; `style="Industrial"`.

## Bohème

- Palette : terracotta, ocre, beige, vert, rose poudré.
- Matières : rotin, jute, macramé, velours, bois.
- Meubles types : fauteuil rotin, tapis jute ou berbère, poufs, nombreuses plantes, suspension en fibres, coussins multiples.
- Mots-clés : `bohème`, `rotin`, `jute`, `velours` ; `style="Boheme"`.

## Contemporain / design

- Palette : blanc, gris, noir ; une couleur forte en accent.
- Matières : laqué, verre, métal chromé, marbre.
- Meubles types : canapé d'angle, table basse laquée ou verre, meuble TV suspendu, suspension design.
- Mots-clés : `marbre`, `laqué`, `verre` ; `style="Design"`.

## D'après photos

Quand l'utilisateur fournit des photos, elles priment sur toute fiche : reproduis l'implantation (quel mur, quel ordre), les couleurs et matières visibles, puis cherche l'article catalogue le plus proche. Liste à la fin les écarts (« pas de réfrigérateur américain au catalogue : colonne frigo 60 »).

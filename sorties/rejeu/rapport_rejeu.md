# KAUB — Rejeu de l'été 2026

**Question : si KAUB avait tourné chaque matin pendant les basses eaux de 2026, qu'aurait-il annoncé, et quand ?**

Règle du rejeu : chaque jour, KAUB ne voit que les niveaux passés. Il prévoit avec une méthode de tarissement (sans pluie) et applique des seuils fixés à l'avance : alerte orange s'il y a au moins une chance sur deux que Kaub passe sous 40 cm dans les 21 jours (navigation à peine rentable selon Contargo), rouge pour 25 cm (le record de 2018).

## Ce que KAUB aurait vu venir

| | Alerte KAUB | Ce qui s'est passé | Avance |
|---|---|---|---|
| Passage sous 40 cm | orange le 24 juin (Kaub à 73 cm) | 13 juillet | **19 jours** |
| Passage sous 25 cm (record de 2018) | rouge le 26 juin (Kaub à 64 cm) | 3 août | **38 jours** |
| Passage sous 10 cm (navigation quasi impossible) | orange dès le 24 juin | 14 août | **51 jours** |

Phrase à retenir : **KAUB aurait alerté 51 jours avant que Kaub passe sous 10 cm**, alors que le fleuve était encore à 73 cm.

L'alerte retombe parfois quelques jours après une averse, puis revient : c'est le comportement attendu d'un indicateur qui ne regarde que les trois semaines suivantes.

## Ce que l'action aurait changé pour l'usine A (fictive), à partir du 24 juin

Ce jour-là, KAUB aurait proposé : **Rail et camions d'appoint** (d'après sa prévision : risque de rupture 0 % contre 100 % sans rien faire).

Coût réel de chaque option sur les six semaines suivantes, calculé sur les niveaux réellement observés (hypothèse : 12 jours de stock et le plan d'approvisionnement habituel ce jour-là) :

| Option | Coût total | Écart avec « ne rien changer » | Production perdue |
|---|---|---|---|
| Basculer 30 % des volumes sur le rail | 911 k€ | −595 k€ | 0 t |
| Avancer les péniches et basculer sur le rail | 911 k€ | −594 k€ | 0 t |
| Rail et camions d'appoint ← proposée par KAUB | 969 k€ | −536 k€ | 0 t |
| Camions d'appoint | 1 013 k€ | −492 k€ | 0 t |
| Ne rien changer | 1 505 k€ | — | 8 083 t |

Sans action, l'usine aurait perdu 8 083 t de production en six semaines. L'option proposée par KAUB l'évitait pour un coût inférieur de 536 k€.
Le coût total comprend le transport, le stockage et la production perdue (marge perdue et pénalités, hypothèses dans config/hypotheses.yaml).

## Fiabilité de la série de l'été

PEGELONLINE ne garde qu'un mois d'historique : la série de juin à début octobre est **reconstituée** à partir des débits du modèle GloFAS (Copernicus), corrigés sur les mesures officielles d'octobre–novembre, convertis en niveaux par la courbe de tarage, puis ancrés sur 12 relevés datés publiés dans la presse.

- Erreur du modèle seul face aux relevés : 10,8 cm en moyenne (maximum 35,9 cm).
- Validation croisée (chaque relevé retiré puis prédit par les autres) : 5,4 cm en moyenne (maximum 17,3 cm). C'est l'ordre de grandeur de l'incertitude entre deux relevés.
- Contrôle indépendant : la série atteint son minimum d'août le 16 août à 6 cm ; la presse parlait de 6 cm « à la mi-août », relevé volontairement non utilisé pour l'ancrage.
- **Avant le 24 juillet, aucun relevé n'ancre la série** : la date de la première alerte (fin juin) et celle du passage sous 40 cm sont indicatives, avec une incertitude de l'ordre de 15 cm sur le niveau. Les passages sous 25 cm et sous 10 cm, eux, tombent dans la période ancrée.
- La prévision du rejeu (tarissement) ne voit pas venir la pluie : elle est prudente. Au quotidien, KAUB utilise la prévision d'ensemble GloFAS (50 scénarios).

Fichiers : rejeu_jour_par_jour.csv (une ligne par jour), serie_kaub_ete_2026.csv (série et source de chaque valeur), rejeu_ete_2026.png.
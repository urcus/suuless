# Stop Clop

Suivi de consommation de cigarettes **multi-utilisateur**, en anglais par défaut avec traduction française et japonaise : interface web responsive, application Android native et API pour un bouton Stream Deck. Les trois accès partagent le même historique.

## Fonctionnalités

- Comptes indépendants, connexion et clés API personnelles révocables.
- Bouton **+1 cigarette**, ajout de plusieurs cigarettes, saisie rétroactive et suppression d’une erreur.
- Total du jour et total global, coûts jour par jour, moyennes, écarts quotidiens et comparaison avec la période précédente.
- Graphique web de consommation ou de coût, avec repère de moyenne et sélection de devise.
- Widget Android horizontal : compteur du jour et bouton **+1** sur l’écran d’accueil.
- Prix du paquet, devise, langue, nombre de cigarettes, repère quotidien et fuseau horaire propres à chaque compte.
- Catalogue de devises (EUR, USD, JPY, CAD, GBP, etc.) et sélecteur géographique IANA avec recherche par ville, pays ou identifiant, sur le web et Android.
- Coût enregistré au moment de la saisie : une modification du prix ne réécrit pas l’historique.
- Export CSV sur la période choisie et persistance SQLite dans un volume Docker.

La devise initiale est l’euro et peut être changée dans les réglages. Les statistiques décrivent les **saisies**, pas une mesure automatique de la consommation. Un jour sans saisie n’est pas nécessairement un jour sans tabac. Les saisies rétroactives utilisent le tarif actuel. La moyenne inclut tous les jours de la période, y compris ceux sans saisie ; le jour courant est partiel.

## Analyses web

Les raccourcis de 30 et 90 jours sont grisés tant que l’historique n’atteint pas ce seuil, avec la mention « En attente de données ». L’ancienneté compte les jours calendaires depuis la première consommation enregistrée jusqu’à aujourd’hui inclus, dans le fuseau du compte ; elle n’exige pas une saisie chaque jour. Sans historique, ou si la période choisie redevient indisponible après une suppression, le sélecteur revient à 7 jours. Les dates personnalisées restent accessibles. L’API expose cette information dans `history_start` (date locale ou `null`) et `history_days`, indépendamment de la plage demandée.

Le filtre de dates pilote le graphique, les moyennes et le tableau quotidien. Le sélecteur du graphique permet de passer des cigarettes aux dépenses ; les devises restent séparées, sans conversion. La ligne pointillée indique la moyenne quotidienne de la période.

Le lissage optionnel affiche la moyenne mobile des sept derniers jours, bornée à la période sélectionnée (moins de sept jours au début). Les graphiques horaires regroupent les quantités selon l’heure locale du compte ; une saisie groupée est affectée intégralement à son heure enregistrée. Les heures répétées au passage à l’heure d’hiver sont regroupées. La moyenne par jour de semaine est divisée par le nombre d’occurrences calendaires du jour dans la période, y compris les jours sans saisie. Ces répartitions incluent la journée en cours, encore partielle.

Une estimation sur 30 jours multiplie par 30 la moyenne des journées terminées de la période sélectionnée, sans aujourd’hui. Les montants historiques restent séparés par devise. Ce scénario suppose que le rythme de saisie et les coûts observés se poursuivent ; il ne prédit pas la consommation future. Sans journée terminée, aucune estimation n’est affichée. Ces analyses sont disponibles sur le web et Android, avec une alternative textuelle aux graphiques.

Chaque journée affiche la consommation, le coût et leur écart à la moyenne, en valeur et en pourcentage. La synthèse compare les totaux à ceux de la période immédiatement précédente, de même nombre de jours calendaires dans le fuseau du compte. Par exemple, du 8 au 14 est comparé au 1 au 7. Les journées sans saisie comptent pour zéro dans les moyennes. Le jour courant reste inclus et est signalé comme incomplet. Un pourcentage sans référence non nulle est affiché « — » ; les différences absolues restent disponibles. Les périodes qui précèdent la limite de saisie du 1er janvier 2000 ne sont pas comparées.

Les coûts utilisent le tarif historique de chaque saisie. Les calculs précèdent l’arrondi monétaire d’affichage ; des écarts minimes peuvent donc apparaître lorsqu’on additionne des montants affichés déjà arrondis.

## Démarrer avec Docker

Prérequis : Docker avec Compose.

```sh
cp .env.example .env
docker compose up -d --build
```

Ouvrir <http://localhost:8080>, créer les comptes, puis régler le tarif, la devise, la langue et le fuseau dans **Settings & integrations** (**Réglages & intégrations** en français). Le sélecteur **Language** est également accessible avant connexion. Le tarif initial de 12 € pour 20 cigarettes est une valeur d’exemple à adapter.

Par défaut, le port est accessible uniquement depuis la machine hôte. Pour un essai Android sur le réseau local, mettre `BIND_ADDRESS=0.0.0.0` dans `.env`, recréer le conteneur avec `docker compose up -d`, puis utiliser `http://IP_DU_SERVEUR:8080` dans l’APK debug. L’émulateur Android utilise généralement `http://10.0.2.2:8080` pour joindre son hôte. Le téléphone doit pouvoir joindre le serveur.

Pour un déploiement distant, fournir un reverse proxy HTTPS ; l’APK release refuse HTTP. Aucun proxy ni certificat n’est inclus. Le service écoute sur le port 8080 et `/healthz` permet de vérifier son état.

Après création des comptes souhaités, mettre `ALLOW_REGISTRATION=false` dans `.env` puis `docker compose up -d` pour fermer les inscriptions. Les comptes existants continuent à fonctionner.

```sh
docker compose logs -f
docker compose down
```

`down` conserve le volume ; **`down -v` supprime les données**. L’image s’exécute sans privilèges avec l’UID 10001. Pour remplacer le volume nommé par un bind mount, rendre le dossier accessible à cet UID.

## Langues, devises et fuseaux horaires

Les préférences sont enregistrées par compte et partagées entre appareils connectés au même compte sur le même serveur. Le bouton **Refresh** web recharge les réglages et la langue, tout en conservant les champs en cours de modification. Une sauvegarde web ou Android ne transmet que les champs modifiés, pour préserver les autres changements effectués depuis un autre appareil. Le prix et sa devise sont toujours envoyés ensemble. Android relit les préférences à l’ouverture de cet écran ; son bouton de rafraîchissement recharge le formulaire et remplace les saisies non enregistrées. Les changements ne sont pas poussés automatiquement vers les écrans déjà ouverts.

L’anglais est la langue par défaut, indépendamment de la langue du navigateur ou du téléphone. **English**, **Français** et **日本語** sont disponibles. Une fois connecté, la préférence du compte est conservée par le serveur et récupérée par les deux clients à la connexion. Avant connexion, le choix de langue est mémorisé localement. Les textes, erreurs API, dates et nombres sont traduits ou formatés selon cette préférence.

Le catalogue des devises actives est fourni par Babel/CLDR : nom traduit, code ISO et nombre de décimales. Le prix doit respecter cette précision (exemples : `12.50` EUR, `600` JPY, `1.234` KWD). Le changement de devise demande de saisir un nouveau prix : **aucune conversion de change n’est effectuée**. Chaque consommation conserve son prix et sa devise ; des dépenses en plusieurs devises apparaissent séparément, par exemple `EUR 12.00 + JPY 600`. L’export CSV inclut aussi la devise de chaque ligne.

Le sélecteur utilise `zone1970.tab`, livré par le paquet `tzdata`, avec UTC ajouté explicitement : **313 choix avec les données actuelles**, au lieu des 599 noms techniques précédents. Il exclut les alias, noms techniques `Etc/GMT±…` et doublons utiles uniquement à la compatibilité. Deux zones qui partagent leur décalage actuel restent distinctes si leurs règles ou leur historique diffèrent. Cette table IANA convient aux dates prises en charge par l’application (depuis 2000). [Choix géographiques et compatibilité IANA](https://www.iana.org/time-zones/theory).

Chaque choix affiche une ville/région, son pays principal et le décalage UTC **au moment du chargement**, puis l’identifiant enregistré : `Kathmandu — Népal (UTC+05:45) · Asia/Kathmandu`. Le serveur fournit aussi tous les pays associés à une zone représentative. La recherche accepte les villes et pays en anglais, français ou japonais, les codes pays, les identifiants IANA et les anciens noms (par exemple `Calcutta` retrouve `Asia/Kolkata`). Elle ignore la casse et les accents. Les noms sont traduits avec Babel ; si une traduction manque, le nom IANA reste lisible. Les décalages sont recalculés à chaque chargement du catalogue, notamment à l’ouverture des réglages web.

À la **création d’un compte web**, le navigateur fournit son fuseau avec `Intl.DateTimeFormat().resolvedOptions().timeZone`. Un alias reconnu est résolu vers le représentant du catalogue ; si la détection échoue, UTC est proposé. L’écran d’inscription indique ce choix initial. Android applique le même principe avec le fuseau du téléphone. La connexion à un compte existant ne modifie jamais sa préférence, même depuis un appareil dans un autre fuseau. Les appels API d’inscription sans champ `timezone` conservent le défaut historique `Europe/Paris` pour compatibilité.

Les préférences existantes sont conservées sans migration destructrice : un ancien identifiant valide comme `US/Eastern` reste enregistré tel quel, utilisable par l’API et visible comme choix courant dans les réglages de ce compte seulement. L’utilisateur peut le remplacer explicitement par un autre choix. Les conversions, alias et catalogue utilisent tous le paquet `tzdata` épinglé, sans dépendre de la version des données du système hôte.

Les instants restent stockés en UTC. Le fuseau du compte sert à l’affichage, aux saisies rétroactives et aux bornes des journées statistiques ; le décalage d’une ancienne entrée est calculé **à la date de cette entrée**, pas à partir du décalage courant du sélecteur. Lors d’une heure répétée, une saisie locale sans décalage désigne la première occurrence ; l’API `occurred_at` avec décalage explicite permet de choisir l’autre. Une heure inexistante lors du passage à l’heure d’été est refusée. L’historique indique le décalage UTC de chaque saisie.

Les traductions partagées se trouvent dans `server/static/locales/{en,fr,ja}.json`. Gradle les copie automatiquement dans les assets Android. Pour ajouter une langue, compléter le même ensemble de clés, déclarer la langue dans `server/international.py` et les sélecteurs de connexion web/Android, puis relancer les tests et recompiler l’APK. Les tests vérifient la présence des clés et des paramètres dans chaque traduction.

Mise à jour d’une installation existante :

```sh
docker compose up -d --build
```

Au démarrage, une migration additive conserve les comptes, clés, tarifs et consommations existants. Les anciennes dépenses restent en EUR et les comptes existants prennent l’anglais comme langue initiale. Le volume Docker est conservé. Installer également le nouvel APK pour disposer des réglages multidevises sur Android.

## Application Android

Projet Java natif dans [`android/`](android/), compatible Android 8.0 et versions ultérieures. Il permet l’inscription, la connexion, le +1, la saisie rétroactive, les statistiques sur 7/30/90 jours, l’historique, la suppression et les réglages. La gestion des clés API et l’export CSV se font sur le web.

La navigation inférieure donne accès à **Aujourd’hui**, **Analyses**, **Historique** et **Réglages**. Le tableau de bord présente le compteur, le +1, le coût du jour et un aperçu graphique des sept derniers jours. Les analyses proposent un histogramme des quantités et une courbe des coûts, la moyenne en pointillés, les écarts journaliers et la comparaison avec la période précédente. Choisir une devise ne convertit pas les anciennes dépenses. Toucher le graphique ou utiliser les boutons de journée affiche les valeurs exactes ; la liste des chiffres journaliers fournit une alternative textuelle accessible. Les réglages regroupent langue, devise, prix, fuseau, widget, synchronisation et compte. La saisie rétroactive possède un sélecteur de date et d’heure.

Aperçus sur un compte de démonstration : [tableau de bord](docs/screenshots/android-today.png), [analyses](docs/screenshots/android-analysis.png).

Prérequis : JDK 17, Android SDK Platform 36 et Build Tools 35.0.0. Gradle 8.13 est téléchargé par le wrapper avec vérification SHA-256. Android Gradle Plugin est fixé à 8.13.2. Le projet peut aussi s’ouvrir dans Android Studio. [Compatibilité officielle AGP 8.13](https://developer.android.com/build/releases/agp-8-13-0-release-notes).

```sh
# ANDROID_HOME doit désigner votre SDK Android.
cd android
./gradlew assembleDebug lintDebug
# APK : app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Renseigner l’origine du serveur (par exemple `https://tabac.exemple.fr`), sans chemin, puis se connecter au même compte que sur le web. Les sessions Android sont chiffrées avec Android Keystore ; les sauvegardes Android de l’application sont désactivées.

La connexion réseau est nécessaire. En cas de réponse réseau incertaine, réessayer la saisie non confirmée pour réutiliser sa clé d’idempotence. Une version de distribution doit être signée avec votre propre clé ; aucune clé de release n’est enregistrée dans le dépôt.

### Widget sur l’écran d’accueil

Après connexion, toucher **Add home screen widget** (**Ajouter le widget à l’écran d’accueil**) dans **Réglages → Widget et synchronisation**, ou ouvrir le catalogue de widgets du lanceur Android et sélectionner Stop Clop. Le widget occupe une ligne (4 × 1 cellules par défaut), redimensionnable horizontalement.

- **+1** ajoute une cigarette au compte connecté et recharge le compteur du jour dans le fuseau du compte.
- Toucher le compteur le rafraîchit ; le bouton à gauche ouvre l’application.
- Avec la synchronisation push activée, les ajouts web/API/Stream Deck, suppressions et modifications de réglages déclenchent un rafraîchissement. Le compteur est aussi rechargé à l’ouverture du tableau de bord et périodiquement, environ toutes les 30 minutes selon les restrictions Android. L’heure de dernière mise à jour est affichée dans le fuseau du téléphone.
- Hors connexion ou après une réponse incertaine, **Réessayer +1** conserve une seule saisie en attente avec son instant initial et sa clé d’idempotence. Réessayer après reconnexion évite un doublon même si le serveur avait déjà enregistré l’ajout. Ce bouton ne cumule pas plusieurs cigarettes hors ligne.
- Le widget utilise la session chiffrée de l’application. Une déconnexion ou un changement de compte efface son cache et sa saisie en attente ; les anciennes données ne sont pas affichées au compte suivant. Une session expirée demande de se reconnecter.

### Synchronisation intégrée

Le [diagramme de synchronisation](docs/push-sync.html) décrit le flux direct entre Android et Stop Clop. Aucun compte Firebase, serveur ntfy ni application relais n’est nécessaire.

Après connexion, Stop Clop configure automatiquement la synchronisation avec l’adresse du serveur et la session chiffrée déjà enregistrées. L’application propose les permissions de notification et l’exemption des optimisations de batterie. Une notification permanente permet d’arrêter la synchronisation ; les commandes du tableau de bord permettent de la réactiver ou de revoir les autorisations. Un refus ne bloque pas l’application ni le widget : le rafraîchissement manuel et périodique reste disponible. Le choix de désactivation est conservé lors des mises à jour.

Le service Android utilise un flux SSE authentifié. Il relit les réglages et les statistiques à chaque changement, à la reconnexion initiale, au changement de jour dans le fuseau choisi et toutes les 15 minutes en secours. Les coupures sont réessayées avec un délai croissant jusqu’à 60 secondes. Le service reprend après redémarrage du téléphone ou mise à jour de l’APK, selon les autorisations Android. Un arrêt forcé par l’utilisateur nécessite de rouvrir Stop Clop. L’exemption de batterie autorise le réseau en veille ; elle ne garantit pas la survie permanente du processus. Le service effectue directement le rafraîchissement, sans dépendre d’un job différé pendant Doze.

Chaque mutation enregistre une nouvelle révision par utilisateur dans la même transaction SQLite que les données. Le flux transmet seulement un signal `refresh` et cette révision aléatoire ; aucun historique ni secret n’y figure. Les comptes sont isolés. Le jeton est envoyé dans l’en-tête `Authorization`, jamais dans l’URL. Le serveur revalide la session pendant le flux et le ferme à sa révocation ou expiration. La révision persistée permet de rattraper les modifications effectuées hors connexion et après redémarrage du serveur.

API authentifiée : `GET /api/sync/config` retourne `{transport:"sse",path:"/api/sync/events"}`. `GET /api/sync/events` ouvre un flux `text/event-stream`. L’en-tête facultatif `Last-Event-ID` contient la dernière révision de 32 caractères hexadécimaux. Les événements sont `refresh` et `revoked`, avec `data: {}`. Un commentaire de maintien de connexion est envoyé au plus toutes les 10 secondes ; les connexions sont renouvelées après 60 secondes. Le client valide un curseur seulement après le rechargement réussi des données.

Le conteneur sert l’API, le web et les événements sur le même port 8080. Aucun worker supplémentaire n’est requis. Le reverse proxy doit transmettre les réponses au fil de l’eau, sans mise en tampon SSE, et autoriser au moins 30 secondes d’inactivité. Le serveur émet `X-Accel-Buffering: no`. Gunicorn utilise deux workers de 32 threads, avec au maximum 16 flux par worker pour laisser de la capacité aux requêtes ordinaires ; en cas de saturation, le flux retourne 503 avec `Retry-After: 30`. Pour une charge supérieure, adapter cette architecture et tester la capacité avant d’augmenter les limites.

Migration depuis v0.3 : les sessions et données sont conservées. Les anciennes routes `/api/push` et tables restent compatibles si un opérateur conserve explicitement les variables `PUSH_PUBLIC_URL` / `PUSH_INTERNAL_URL` et le worker historique. Le déploiement fourni n’en dépend plus. L’ancien relais peut être arrêté après mise à jour des téléphones ; son PVC est à conserver jusqu’à décision explicite de suppression.

## Stream Deck : une cigarette par pression

Dans **Réglages & intégrations → Clés API & sessions**, créer une clé nommée « Stream Deck » et la copier immédiatement. Configurer une action HTTP :

| Champ | Valeur |
|---|---|
| Méthode | `POST` |
| URL | `https://VOTRE_SERVEUR/api/cigarettes` |
| Authorization | `Bearer VOTRE_CLE` |
| Content-Type | `application/json` |
| Corps | `{"source":"streamdeck"}` |

Équivalent avec curl :

```sh
# Fournir STOP_CLOP_TOKEN dans l’environnement de votre commande.
curl --fail-with-body https://VOTRE_SERVEUR/api/cigarettes \
  -H "Authorization: Bearer $STOP_CLOP_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"source":"streamdeck"}'
```

Le corps peut être omis : la quantité vaut alors 1. Si l’action HTTP gère les réessais, envoyer un en-tête `Idempotency-Key` unique par pression et réutiliser cette même valeur pour ses réessais. **Ne pas configurer une valeur constante pour toutes les pressions**, sinon les suivantes ne seront pas comptées. La première réponse vaut `201`, les répétitions de la même clé `200`. Sans cet en-tête, chaque requête ajoute une consommation.

La clé a les droits complets de votre compte, expire après un an et se révoque depuis le web. Elle ne doit pas être placée dans l’URL. Il n’y a pas de plugin Stream Deck spécifique à installer depuis ce dépôt : utiliser une action capable d’envoyer une requête HTTP.

## API

Toutes les routes `/api/*` exigent `Authorization: Bearer …`, sauf `/api/config`, `/api/auth/register` et `/api/auth/login`. Ces deux dernières acceptent `{"username":"alice","password":"au-moins-12-caracteres"}` et retournent une session valable 30 jours. Identifiants insensibles à la casse ; 3–40 caractères parmi lettres ASCII, chiffres, `_`, `.` et `-`.

| Méthode | Route | Usage |
|---|---|---|
| GET | `/api/config` | Inscriptions, langues, devises et catalogue géographique des fuseaux |
| POST | `/api/auth/register`, `/api/auth/login` | Créer un compte / ouvrir une session |
| POST | `/api/auth/logout` | Révoquer la session courante |
| GET | `/api/me` | Compte courant |
| GET, PUT | `/api/settings` | Lire / mettre à jour les réglages fournis |
| GET, POST | `/api/cigarettes` | Historique / ajout |
| DELETE | `/api/cigarettes/{id}` | Supprimer une saisie de son compte |
| GET | `/api/stats` | Jour courant, total global et période |
| GET | `/api/export.csv` | Exporter la période |
| GET, POST | `/api/tokens` | Lister / créer une clé (`{"name":"Stream Deck"}`) |
| DELETE | `/api/tokens/{id}` | Révoquer une clé / session de son compte |

Réglages : `{"pack_price":"600","currency":"JPY","language":"ja","pack_size":20,"daily_target":10,"timezone":"Asia/Tokyo"}`. Les champs omis restent inchangés ; `{"language":"fr"}` suffit pour changer uniquement la langue. `pack_price` est une chaîne décimale exprimée dans la devise choisie ; la limite est de 1 000 000 unités. Changer `currency` exige aussi `pack_price`. Les réponses incluent `local_today` et `local_datetime` calculés dans le fuseau du compte, ainsi que `timezone_info` (descriptif du choix enregistré, y compris s’il est ancien).

`/api/config` conserve `timezones` (liste des identifiants du catalogue simplifié) et ajoute `timezone_options` (`id`, `city`, `countries`, `country_codes`, `label`, `search`, `utc_offset`, `offset_seconds`, `legacy`), `timezone_aliases` (ancien nom → représentant du catalogue), `timezone_offsets_at` et `tzdata_version`. Un identifiant valide absent du catalogue principal peut toujours être enregistré pour compatibilité, mais le sélecteur ne le propose qu’au compte qui l’utilise déjà.

L’ancien champ `pack_price_cents` est conservé pour compatibilité et représente toujours des centièmes de l’unité monétaire ; il ne convient pas aux devises à trois décimales. Les nouveaux clients utilisent exclusivement `pack_price`. Le repère quotidien n’empêche pas une saisie au-delà du seuil.

Ajout : `{"quantity":1,"occurred_at":"2026-01-10T14:30:00+01:00","source":"android"}`. Tous les champs sont optionnels. Quantité : entier 1–200 ; source : `web`, `android`, `api` ou `streamdeck` (indicative, pas une preuve d’origine). Les dates futures et antérieures à 2000 sont refusées. Une exception compense le décalage des horloges des appareils : un `occurred_at` explicite jusqu’à 5 secondes en avance est ramené à l’heure de réception du serveur, sans enregistrer de date future. Les saisies manuelles `occurred_at_local` restent strictes. Sans date, l’heure serveur est utilisée. Une date `occurred_at` explicite doit comporter son décalage UTC. Les interfaces web et Android envoient `occurred_at_local` sans décalage : le serveur l’interprète dans le fuseau du compte. Ces champs sont mutuellement exclusifs. Une heure locale inexistante au changement d’heure est refusée ; une heure répétée utilise la première occurrence. Les réponses d’historique incluent aussi `local_datetime` avec le décalage calculé par le serveur.

`GET /api/stats` conserve ses champs existants et ajoute `analysis` : `average_quantity_per_day`, `average_cost_per_day` (par devise), `days_with_entries`, `minimum_quantity`, `maximum_quantity`, `includes_today`, `previous_period`, `comparison` et `daily`. Les comparaisons contiennent `quantity_delta`, `quantity_percent`, `cost_deltas` et `cost_percent` (dictionnaires par devise). Dans `daily`, ces écarts se rapportent à la moyenne de la période ; dans `comparison`, ils comparent les totaux à la période précédente. Un pourcentage dont la référence vaut zéro est `null`. Si la période précédente sort des dates prises en charge, ses bornes et les écarts de quantité sont `null`, `days` vaut zéro et les dictionnaires d’écarts monétaires sont vides.

Les champs supplémentaires de `analysis` sont :

- `trend` : moyenne mobile sur au plus sept jours, avec `date`, `window_days`, `quantity`, `costs` et écarts à la moyenne de période (`quantity_delta`, `cost_deltas`).
- `hourly` : 24 objets `hour` (0–23), `quantity`, `share_percent` ; quantités cumulées dans le fuseau du compte.
- `weekdays` : sept objets `weekday` (0=lundi), `quantity`, `days` et `average` ; `average` vaut `null` quand ce jour ne figure pas dans la période.
- `projection` : `days` (30), `sample_days` (journées terminées), `quantity` et `costs` par devise ; sans échantillon, `quantity` vaut `null` et `costs` est vide.


`/api/stats`, `/api/cigarettes` et `/api/export.csv` acceptent `?start=2026-01-01&end=2026-01-31`, bornes incluses dans le fuseau du compte. La période par défaut est de 30 jours jusqu’à aujourd’hui ; maximum 366 jours, sans jour futur. Le total global et le total du jour sont indépendants de ce filtre. L’historique accepte aussi `limit` (1–500, défaut 100) et `offset` (défaut 0), et retourne `{items,total}`.

Les dates sont stockées en UTC ; les limites quotidiennes tiennent compte de l’heure d’été. Les coûts unitaires sont enregistrés en millionièmes d’unité monétaire avec leur devise ; les totaux sont calculés séparément pour chaque devise puis arrondis à sa précision. La somme de coûts individuels affichés peut donc différer légèrement du total arrondi. Les objets `today`, `total`, `period` et chaque jour incluent `costs`, par exemple `{"EUR":1.20,"JPY":60}`. Les champs scalaires `cost` et `currency` restent présents pour une seule devise et valent `null` si plusieurs devises sont représentées. Pour une période vide, `costs` contient zéro dans la devise du compte. Le CSV utilise les colonnes stables `id,local_datetime,quantity,cost,currency,source`.

Une clé d’idempotence appartient au compte et à la saisie, quel que soit le client. Réutiliser la même clé retourne la première saisie, même si le corps change. Supprimer la saisie libère aussi cette clé. Erreurs JSON : `{"error":"…","code":"invalid_price"}` (exemple de code stable). Le message est traduit selon le compte authentifié, sinon selon `Accept-Language` avec l’anglais par défaut. Codes HTTP : `400`, `401`, `403`, `404`, `409`, `413`, `415` ou `429` selon le cas.

## Développement et vérifications

Python 3.13 recommandé. L’interface ne nécessite aucun build JavaScript.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/flask --app server.app:create_app run --port 8080
```

Le serveur de développement Flask est réservé aux essais locaux. Docker utilise Gunicorn, conformément au [mode de déploiement documenté par Flask](https://flask.palletsprojects.com/en/stable/deploying/gunicorn/).

Test navigateur (serveur actif, inscriptions ouvertes, base de test conseillée : le test crée un compte et des saisies) :

```sh
npm ci
npx playwright install chromium
BASE_URL=http://127.0.0.1:8080 npm run test:web
```

Les captures ordinateur et mobile sont générées dans `test-results/`, ignoré par Git. Les tests API utilisent une base temporaire. Ils couvrent notamment les accès entre comptes, coûts historiques, dates et changement d’heure, pagination, export, révocation, persistance et ajouts simultanés avec idempotence. Les tests internationaux couvrent aussi les migrations, les comptes en plusieurs langues, les devises à 0/2/3 décimales, les totaux mixtes et chaque fuseau du catalogue. Les tests dédiés aux fuseaux couvrent les alias existants, l’initialisation sans écrasement, les décalages fractionnaires, les journées de 23/25 heures et les transitions de 30 minutes. Les tests navigateur vérifient aussi la recherche multilingue et une reconnexion depuis un autre fuseau.

## CI/CD GitLab et releases

La configuration [`.gitlab-ci.yml`](.gitlab-ci.yml) reprend les runners `k8s`, les images Kaniko/Cosign et les variables Harbor de votre modèle. [Schéma du pipeline](docs/ci-cd.html) réalisé avec `diagram-design`.

| Étape | Job | Résultat |
|---|---|---|
| validate | `quality:api` | Tests Python, API, migration, internationalisation et script de release |
| validate | `quality:web` | Node 24.11.0, serveur temporaire, parcours Chromium et captures |
| build | `android:build` | APK debug, APK release non signé, Lint des deux variantes, SHA256SUMS |
| image | `image:publish` | Image Harbor et digest exact transmis en artifact dotenv |
| sign | `image:sign` | Signature Cosign, extraction de la clé publique et vérification du digest |
| release | `release:publish` | Paquets persistants et création/mise à jour de la release GitLab |

Les branches, merge requests et tags exécutent tests et build Android. Les publications sont réservées aux **tags protégés `vX.Y.Z`** (par exemple `v0.2.0`), comme dans le modèle fourni. Un tag non protégé ou un tag de préversion ne publie ni image ni release. Configurer la protection de `v*` dans GitLab. Aucun Docker-in-Docker ni runner privilégié n’est nécessaire.

Variables déjà présentes, réutilisées directement :

| Variable | Usage |
|---|---|
| `HARBOR_URL` | Hôte du registre, sans `https://` ni slash final |
| `PROJECT` | Projet Harbor |
| `HARBOR_USER`, `HARBOR_PASSWORD` | Connexion Harbor pour Kaniko et Cosign |
| `COSIGN_PRIVATE_KEY` | Clé privée Cosign, variable GitLab de type fichier ou contenu PEM |
| `COSIGN_PASSWORD` | Mot de passe de la clé Cosign |

L’image est `${HARBOR_URL}/${PROJECT}/${CI_PROJECT_NAME}:X.Y.Z`. Le compte Harbor doit pouvoir pousser dans ce dépôt et dans le dépôt de cache suffixé `-cache`, puis lire/écrire les signatures Cosign. Les jobs utilisent le comportement normal de Cosign concernant le journal de transparence ; le runner doit pouvoir joindre ses services et Harbor. Les variables `NEXT_PUBLIC_*` du modèle ne sont pas utilisées : ce projet ne contient pas de build Next.js.

La publication des APK et de la release utilise uniquement le `CI_JOB_TOKEN` fourni par GitLab : aucun token personnel supplémentaire. Le registre de paquets doit être activé pour le projet. Pour un GitLab privé, les téléchargements restent soumis aux droits du projet. [Authentification des paquets génériques](https://docs.gitlab.com/user/packages/generic_packages/) et [API des releases](https://docs.gitlab.com/api/releases/).

Le build Android installe le SDK 36 et Build Tools 35.0.0 dans un cache du projet, depuis les outils officiels Google dont l’archive est vérifiée. JDK 17 et le wrapper Gradle 8.13 sont utilisés. Les publications utilisent une clé debug stable, stockée dans la variable GitLab `ANDROID_DEBUG_KEYSTORE_BASE64` (masquée, protégée, expansion désactivée). Son contenu est le keystore PKCS12 encodé en base64 sur une ligne, alias `androiddebugkey`, mots de passe standard debug `android`. Le script le décode dans un répertoire temporaire privé et le supprime à la fin ; la clé n’est ni versionnée, ni mise en cache, ni jointe aux artifacts. Un tag de release protégé échoue si cette variable manque.

- **APK debug** : installable pour les tests, avec HTTP local autorisé. Les builds disposant de la variable utilisent la même signature et peuvent se mettre à jour sans désinstallation. Les builds locaux ou branches non protégées sans cette variable gardent une clé locale distincte ; ne pas les utiliser pour mettre à jour l’APK distribué.
- **APK release non signé** : HTTPS obligatoire ; signer avec votre propre clé Android avant installation. Cosign ne signe pas l’APK.

Conserver et sauvegarder ce keystore : sa perte empêcherait les mises à jour compatibles. Ne pas régénérer la variable à chaque pipeline. Cette clé sert uniquement aux APK debug ; le choix de publier un APK release non signé reste inchangé.

Les APK jusqu’à **v0.2.0 incluse** avaient une clé éphémère. Le passage à la clé stable exige une dernière désinstallation et reconnexion. Les versions suivantes conservent les préférences locales et la session chiffrée Android Keystore lors d’une mise à jour normale (`adb install -r` ou installation par-dessus). Une session expirée ou révoquée nécessite toujours une connexion ; les sessions actuelles expirent après 30 jours. [Règles de signature Android](https://developer.android.com/studio/publish/app-signing).

`versionName` correspond au tag sans `v`, et `versionCode` à `CI_PIPELINE_IID`. Pour les branches : `0.1.0-dev.<IID>`. Les builds locaux sans paramètres gardent la version `0.1.0` et le code `1`.

Les artifacts de jobs expirent après une semaine. Sur un tag protégé, les deux APK, une somme SHA-256 de chaque fichier, la référence de l’image, la clé publique Cosign et le résultat de vérification sont aussi transférés dans le registre de paquets génériques `stop-clop`, version `X.Y.Z-<IID>`. Ces liens de release ne dépendent pas de l’expiration des artifacts. Les fichiers restent disponibles jusqu’à leur suppression ou une politique de nettoyage du registre. Une relance de la publication du même pipeline réutilise les fichiers identiques et actualise les liens ; un nouveau pipeline pour le même tag utilise une autre version de paquet.

Après avoir commité et poussé les fichiers du projet, créer et pousser un tag protégé déclenche la publication :

```sh
git tag v0.2.0
git push origin v0.2.0
```

Pour vérifier une image, utiliser votre clé publique Cosign de confiance et le digest de la release :

```sh
cosign verify --key /chemin/vers/votre-cle-publique.pem REGISTRE/PROJET/stop-clop@sha256:DIGEST
```

La clé publique jointe à la release permet aussi la vérification, mais son empreinte doit être comparée à votre référence de confiance. Aucun tag n’est créé automatiquement par le pipeline.

## Architecture et exploitation

[Diagramme d’architecture HTML](docs/architecture.html), réalisé avec le skill `diagram-design` : navigateur, client Android et Stream Deck → API Flask/Gunicorn → SQLite. Ouvrir le fichier dans un navigateur ; GitLab peut afficher le code HTML plutôt que le rendu. Le diagramme utilise les polices Google Fonts avec replis locaux si elles ne sont pas disponibles.

- `server/app.py` : API, authentification, calculs et initialisation du schéma SQLite.
- `server/static/` : interface web et traductions partagées, sans dépendance JavaScript de production.
- `server/international.py` : devises, traductions API et précision monétaire.
- `server/timezones.py` : catalogue géographique IANA, compatibilité des alias, libellés et conversions depuis `tzdata`.
- `android/` : application native et wrapper Gradle.
- `tests/` : tests API et parcours navigateur.
- `Dockerfile`, `compose.yaml` : image et stockage persistant.

Les mots de passe utilisent scrypt ; seules les empreintes SHA-256 des clés aléatoires sont stockées côté serveur. Le web garde la session dans `sessionStorage` (par onglet). Pas de cookies d’authentification ni de CORS ouvert. La connexion et l’inscription sont limitées à 30 tentatives par adresse réseau sur 15 minutes. Derrière un reverse proxy, l’adresse vue est celle du proxy : ce quota est alors partagé ; prévoir une limitation par client au niveau du proxy. Le serveur ne fait pas confiance aux en-têtes `X-Forwarded-*`.

SQLite convient à une instance auto-hébergée ; ne pas multiplier les réplicas sur des volumes distincts ni utiliser un partage réseau pour la base WAL. Sauvegarder avec l’API de sauvegarde SQLite pour obtenir une copie cohérente pendant le fonctionnement :

```sh
docker compose exec stop-clop python -c "import sqlite3; source=sqlite3.connect('/data/stopclop.db'); target=sqlite3.connect('/data/backup.db'); source.backup(target); target.close(); source.close()"
docker compose cp stop-clop:/data/backup.db ./stop-clop-backup.db
```

Cette sauvegarde contient les données de tous les comptes et les empreintes d’authentification. Pour restaurer, arrêter le service puis remplacer la base du volume par cette copie, en conservant les droits de l’UID 10001 ; retirer les anciens fichiers WAL/SHM associés à la base remplacée avant le redémarrage. Ne jamais remplacer une base ouverte.

Périmètre de cette première version : pas de récupération de mot de passe par email, de rôles administrateur, de suppression de compte depuis l’interface, de rappels utilisateur ou de mode hors ligne complet. L’APK debug sert aux essais ; la CI publie l’image Harbor et les fichiers de release sur les tags protégés ; aucune publication Play Store n’est configurée.

"""
Formatif FINAL-AHT20 -- Mini-examen blanc, capteur AHT20 + REST
Cours 243-413-SH

Variante FORMATIVE de l'examen FINAL-AHT20. Meme architecture
(lecture I2C, client REST, boucle non-bloquante a time.monotonic)
mais **sujet variant** pour eviter le copier-coller :

* Valeur principale envoyee au serveur : **humidite relative** (%)
  au lieu de la temperature.
* Endpoint serveur : **/evaluer** au lieu de /decider.
* Decisions : **"sec" | "confort" | "humide"** au lieu de
  chaud/normal/froid.

Interaction physique
--------------------
Soufflez doucement sur le capteur AHT20 ; l'humidite mesuree monte.
Eloignez-vous pour la voir redescendre. Apres stabilisation, le
serveur renvoie une categorie d'humidite.

Contrat REST (resume)
---------------------
* GET  `<BASE_URL>/sante`     -> `{"ok": true, ...}`
* POST `<BASE_URL>/evaluer`   -> payload :
    `{"valeur": float, "duree_stable": float, "temperature": float,
      "student_id": str}`
  reponse :
    `{"decision": "sec"|"confort"|"humide", ...}`

Contraintes (identiques au sommatif)
------------------------------------
* Aucun `time.sleep` superieur a 50 ms dans `boucle_principale`.
* Timeout obligatoire sur chaque appel `requests`.
* Gestion d'erreurs reseau (la boucle ne plante pas).
* Anti-rebond entre POST consecutifs.

Aide (`aide.pyc`)
-----------------
Module compile Python 3.11 fourni ; usage penalise. Voir
GRILLE_EVALUATION.md fournie par l'instructeur.
"""

import time

import board
import adafruit_ahtx0
import requests


# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = "http://127.0.0.1:8000"
STUDENT_ID = "202301758"                    # Votre numero d'etudiant (7 chiffres)
TIMEOUT_HTTP = 2.0

PERIODE_LECTURE = 0.5
DUREE_STABLE_REQUISE = 3.0
DELTA_STABILITE = 1.5            # amplitude humidite max-min toleree (%)
PERIODE_MIN_ENTRE_POSTS = 5.0
TAILLE_HISTORIQUE = 16


# =============================================================================
# PHASE 1 : Acquisition I2C (25 pts)
# =============================================================================


def initialiser_capteur():
    """Initialise le bus I2C et le capteur AHT20.

    Returns:
        adafruit_ahtx0.AHTx0: instance du capteur.

    """
    i2c = board.I2C()
    capteur = adafruit_ahtx0.AHTx0(i2c)
    return capteur
    #pass


def lire_capteur(capteur):
    """Lit (humidite, temperature) du AHT20.

    Note : dans ce formatif, **l'humidite est la valeur principale**
    (envoyee au serveur). La temperature est lue en passant et
    sert de champ secondaire dans le payload.

    Args:
        capteur: instance `adafruit_ahtx0.AHTx0`.

    Returns:
        tuple[float, float]: (humidite en %, temperature en C).
    """
    humidite = float(capteur.relative_humidity)
    temperature = float(capteur.temperature)
    return humidite, temperature




# =============================================================================
# PHASE 2 : Client REST (35 pts)
# =============================================================================


def verifier_sante(base_url):
    """GET /sante -- retourne True si le serveur repond avec ok."""
    try:
        reponse = requests.get(f"{base_url}/sante", timeout=TIMEOUT_HTTP)
        donnees = reponse.json()

        return donnees["ok"] == True

    except:
        return False
    


def envoyer_mesure(base_url, valeur, duree_stable, temperature):
    """POST /evaluer avec payload JSON.

    Payload :
        {"valeur": float (humidite), "duree_stable": float,
         "temperature": float, "student_id": STUDENT_ID}

    Returns:
        str | None: la decision ("sec"/"confort"/"humide"), ou None
        sur erreur.
    """
    payload = {
        "valeur": valeur,
        "duree_stable": duree_stable,
        "temperature": temperature,
        "student_id": STUDENT_ID
    }
    try:
        reponse = requests.post(base_url + "/evaluer",json=payload,timeout=TIMEOUT_HTTP)

        if reponse.status_code == 200:
            donnees = reponse.json()
            return donnees["decision"]
    except:
        return None


# =============================================================================
# PHASE 3 : Minuteur + stabilite (40 pts)
# =============================================================================


def est_stable(historique, delta_max):
    """Retourne True si la fenetre `historique` est stable
    (max - min <= delta_max).

    Pour historique vide ou de longueur < 2 : False.
    """
    if len(historique) < 2:
        return False 

    difference = max(historique) - min(historique)

    if difference <= delta_max:
        return True
    else:
        return False


def afficher(humidite, temperature, duree_stable, derniere_decision):
    """Affiche une ligne console (rafraichie avec \\r).

    Format suggere :
        H= 48.5 % | T= 24.8 C | stable= 1.5 s | decision= confort
    """
#//r revenir a la ligne
    if derniere_decision is None:
        derniere_decision = "-"

    print(
        f"\rH={humidite:.1f} % | T={temperature:.1f} C | "
        f"stable={duree_stable:.1f} s | decision={derniere_decision}",
        end="",
        flush=True
    )
    


def boucle_principale(capteur, base_url):
    """Boucle non-bloquante a `time.monotonic()`.

    Identique au sommatif : historique glissant, detection de
    stabilite, POST anti-rebond, affichage.
    """
    historique = []
    derniere_decision = None

    dernier_temps_lecture = 0
    debut_stable = None
    dernier_post = 0

    while True:
        maintenant = time.monotonic()

        if maintenant - dernier_temps_lecture >= PERIODE_LECTURE:
            dernier_temps_lecture = maintenant

            try:
                humidite, temperature = lire_capteur(capteur)

                historique.append(humidite)

                if len(historique) > TAILLE_HISTORIQUE:
                    historique.pop(0)

                if est_stable(historique, DELTA_STABILITE):
                    if debut_stable is None:
                        debut_stable = maintenant

                    duree_stable = maintenant - debut_stable

                else:
                    debut_stable = None
                    duree_stable = 0

                if duree_stable >= DUREE_STABLE_REQUISE:
                    if maintenant - dernier_post >= PERIODE_MIN_ENTRE_POSTS:
                        decision = envoyer_mesure(
                            base_url,
                            humidite,
                            duree_stable,
                            temperature
                        )

                        dernier_post = maintenant

                        if decision is not None:
                            derniere_decision = decision

                afficher(
                    humidite,
                    temperature,
                    duree_stable,
                    derniere_decision
                )

            except:
                print("\nErreur pendant la boucle")

        time.sleep(0.01)
    


# =============================================================================
# POINT D'ENTREE
# =============================================================================

def main():
    """Init capteur + verif serveur + boucle. Arret propre sur Ctrl+C."""
    try:
        capteur = initialiser_capteur()
        print("Capteur AHT20 initialise.")

        if verifier_sante(BASE_URL):
            print("Serveur disponible.")
        else:
            print("Serveur non disponible.")

        boucle_principale(capteur, BASE_URL)

    except KeyboardInterrupt:
        print("\nArret du programme.")

    except:
        print("Erreur dans le programme.")

if __name__ == "__main__":
    main()

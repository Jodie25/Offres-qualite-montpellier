#!/usr/bin/env python3
"""Collecte les offres qualité / agroalimentaire autour de Montpellier.

Sources sans clé : LinkedIn (recherche publique), HelloWork.
Sources avec clé gratuite (variables d'environnement, ignorées si absentes) :
  France Travail : FT_CLIENT_ID, FT_CLIENT_SECRET
  Adzuna         : ADZUNA_APP_ID, ADZUNA_APP_KEY
Écrit data/offres.json en conservant l'historique (première vue, offres disparues).
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CFG = json.loads((Path(__file__).parent / "config.json").read_text(encoding="utf-8"))
SORTIE = RACINE / "data" / "offres.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
AUJOURDHUI = date.today().isoformat()


def get(url, headers=None, data=None, retries=2):
    h = {"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"}
    h.update(headers or {})
    for essai in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and essai < retries:
                time.sleep(5 * (essai + 1))
                continue
            print(f"   ! HTTP {e.code} {url[:90]}", file=sys.stderr)
            return None
        except Exception as e:  # réseau
            print(f"   ! {type(e).__name__} {url[:90]}", file=sys.stderr)
            return None
    return None


def nettoyer(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def norm(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def texte_brut(h):
    """HTML -> texte avec retours à la ligne (pour les descriptions d'offres)."""
    h = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>|</h\d>", "\n", h or "")
    h = re.sub(r"(?i)<li[^>]*>", "• ", h)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def offre(source, id_ext, titre, entreprise, lieu, url, contrat="", salaire="", date_pub="", extrait=""):
    return {
        "description": texte_brut(extrait)[:5000],
        "source": source, "id_ext": str(id_ext), "titre": nettoyer(titre), "entreprise": nettoyer(entreprise),
        "lieu": nettoyer(lieu), "contrat": nettoyer(contrat), "salaire": nettoyer(salaire),
        "url": url, "date_pub": (date_pub or "")[:10], "extrait": nettoyer(extrait)[:400],
    }


# ---------- LinkedIn (recherche publique, sans compte) ----------
def linkedin(q):
    res = []
    for start in (0, 10, 20):
        u = ("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?"
             + urllib.parse.urlencode({"keywords": q, "location": f"{CFG['ville']}, Occitanie, France",
                                       "distance": CFG["rayon_km"], "f_TPR": "r2592000", "start": start}))
        page = get(u)
        if not page:
            break
        cartes = page.split("<li>")[1:]
        if not cartes:
            break
        for c in cartes:
            m = re.search(r'href="(https://[a-z.]*linkedin\.com/jobs/view/[^"]+)"', c)
            idm = re.search(r"jobPosting:(\d+)", c)
            t = re.search(r'base-search-card__title">(.*?)</h3>', c, re.S)
            e = re.search(r'base-search-card__subtitle">(.*?)</h4>', c, re.S)
            l = re.search(r'job-search-card__location">(.*?)</span>', c, re.S)
            d = re.search(r'datetime="([\d-]+)"', c)
            if not (m and idm and t):
                continue
            url = html.unescape(m.group(1)).split("?")[0]
            res.append(offre("LinkedIn", idm.group(1), t.group(1), e.group(1) if e else "",
                             l.group(1) if l else "", url, date_pub=d.group(1) if d else ""))
        time.sleep(1.5)
    return res


# ---------- HelloWork ----------
def hellowork(q):
    res = []
    for p in (1, 2):
        u = ("https://www.hellowork.com/fr-fr/emploi/recherche.html?"
             + urllib.parse.urlencode({"k": q, "l": CFG["ville"], "ray": CFG["rayon_km"], "p": p}))
        page = get(u)
        if not page:
            break
        cartes = re.split(r'<li data-id-storage-target="item"', page)[1:]
        if not cartes:
            break
        for c in cartes:
            idm = re.search(r'data-id-storage-item-id="(\d+)"', c)
            t = re.search(r'<a[^>]*?href="([^"]+)"[^>]*?data-cy="offerTitle"|<a[^>]*?data-cy="offerTitle"[^>]*?href="([^"]+)"', c, re.S)
            if not (idm and t):
                continue
            href = html.unescape(t.group(1) or t.group(2)).split("?")[0]
            ps = re.search(r'<h3 class="inline">\s*<p[^>]*>(.*?)</p>\s*<p[^>]*>(.*?)</p>', c, re.S)
            if not ps:
                continue
            titre, ent = nettoyer(ps.group(1)), nettoyer(ps.group(2))
            lieu = re.search(r'data-cy="localisationCard"[^>]*>(.*?)</div>', c, re.S)
            contrat = re.search(r'data-cy="contractCard"[^>]*>(.*?)</div>', c, re.S)
            aria = re.search(r'aria-label="(Voir offre[^"]*)"', c)
            sal = re.search(r"salaire de (.*?)(?:, en |$)", html.unescape(aria.group(1))) if aria else None
            res.append(offre("HelloWork", idm.group(1), titre, ent, lieu.group(1) if lieu else "",
                             "https://www.hellowork.com" + href if href.startswith("/") else href,
                             contrat=contrat.group(1) if contrat else "", salaire=sal.group(1) if sal else "",
                             date_pub=date_relative(c)))
        time.sleep(1.5)
    return res


def date_relative(bloc):
    """'il y a 16 jours' -> date ISO (HelloWork n'affiche pas de date exacte)."""
    m = re.search(r"il y a (\d+)\s*(minute|heure|jour|semaine|mois)", bloc)
    if not m:
        return ""
    n, u = int(m.group(1)), m.group(2)
    jours = {"minute": 0, "heure": 0, "jour": n, "semaine": 7 * n, "mois": 30 * n}[u]
    return (date.today() - timedelta(days=jours)).isoformat()


# ---------- Meteojob (pages lisibles sans compte) ----------
def meteojob(q):
    res = []
    for p in (1, 2):
        u = "https://www.meteojob.com/jobs?" + urllib.parse.urlencode(
            {"what": q, "where": CFG["ville"], "radius": CFG["rayon_km"], "page": p})
        page = get(u)
        cartes = (page or "").split('id="job-offer-')[1:]
        if not cartes:
            break
        for c in cartes:
            idm = re.match(r"(\d+)", c)
            if not idm:
                continue
            i = idm.group(1)
            t = re.search(r'href="/jobs/' + i + r'"[^>]*>(.*?)</a>', c, re.S)
            ent = re.search(r'id="' + i + r'-company-name">(.*?)</p>', c, re.S)
            lieu = re.search(r'id="' + i + r'-job-locations">.*?</mat-icon>(.*?)</div>', c, re.S)
            ct = re.search(r'id="' + i + r'-contract-types">(.*?)</div>', c, re.S)
            sal = re.search(r'id="' + i + r'-salary">(.*?)</div>', c, re.S)
            if not t:
                continue
            res.append(offre("Meteojob", i, t.group(1), ent.group(1) if ent else "", lieu.group(1) if lieu else "",
                             f"https://www.meteojob.com/jobs/{i}", contrat=ct.group(1) if ct else "",
                             salaire=sal.group(1) if sal else "", date_pub=date_relative(c.lower())))
        time.sleep(1.5)
    return res


def jsonld_offre(page):
    for m in re.finditer(r'application/ld\+json[^>]*>(.*?)</script>', page or "", re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        for x in (d if isinstance(d, list) else d.get("@graph", [d])):
            if isinstance(x, dict) and x.get("@type") == "JobPosting":
                return x
    return None


# ---------- Welcome to the Jungle (moteur de recherche public du site, lecture seule) ----------
WTTJ_CONTRATS = {"full_time": "CDI", "temporary": "CDD", "internship": "Stage", "apprenticeship": "Alternance",
                 "freelance": "Freelance", "part_time": "Temps partiel", "vie": "VIE", "other": ""}


def welcome_to_the_jungle(q, z):
    """z : {'lat','lon','rayon_km'} pour une recherche autour d'un point, 'filtre' pour un département / une région."""
    res = []
    for page in (0, 1):
        params = {"query": q, "hitsPerPage": 50, "page": page, "filters": 'offices.country_code:FR' + z.get("filtre", "")}
        if z.get("lat") and z.get("rayon_km"):
            params["aroundLatLng"] = f"{z['lat']},{z['lon']}"
            params["aroundRadius"] = int(z["rayon_km"] * 1000)
        corps = json.dumps({"requests": [{"indexName": "wttj_jobs_production_fr", "params": urllib.parse.urlencode(params)}]}).encode()
        r = get("https://csekhvms53-dsn.algolia.net/1/indexes/*/queries",
                {"X-Algolia-Application-Id": "CSEKHVMS53", "X-Algolia-API-Key": "4bd8f6215d0cc52b26430765769e65a0",
                 "Content-Type": "application/json", "Origin": "https://www.welcometothejungle.com",
                 "Referer": "https://www.welcometothejungle.com/"}, data=corps, retries=1)
        try:
            hits = json.loads(r)["results"][0]["hits"] if r else []
        except Exception:
            hits = []
        for h in hits:
            org = h.get("organization") or {}
            bureaux = [b for b in (h.get("offices") or []) if b.get("country_code") == "FR"] or (h.get("offices") or [{}])
            lieu = bureaux[0].get("city") or ""
            sal = ""
            if h.get("salary_minimum") and h.get("salary_maximum"):
                sal = f"{int(h['salary_minimum'])} - {int(h['salary_maximum'])} {h.get('salary_currency') or '€'} / {h.get('salary_period') or 'an'}"
            texte = "\n".join(filter(None, [h.get("summary") or "", "\n".join("• " + m for m in (h.get("key_missions") or [])),
                                            h.get("profile") or ""]))
            res.append(offre("Welcome to the Jungle", h.get("reference") or h.get("objectID"), h.get("name", ""), org.get("name", ""), lieu,
                             f"https://www.welcometothejungle.com/fr/companies/{org.get('slug', '')}/jobs/{h.get('slug', '')}",
                             contrat=WTTJ_CONTRATS.get(h.get("contract_type"), h.get("contract_type") or ""), salaire=sal,
                             date_pub=h.get("published_at", ""), extrait=texte))
        if len(hits) < 50:
            break
        time.sleep(0.5)
    return res


def wttj(q):
    c = geocoder(CFG["ville"], (43.5733, 3.8366)) or [43.5733, 3.8366]
    return welcome_to_the_jungle(q, {"lat": c[0], "lon": c[1], "rayon_km": CFG["rayon_km"]})


# ---------- France Travail (API officielle, clé gratuite) ----------
def france_travail(requetes):
    cid, sec = os.environ.get("FT_CLIENT_ID"), os.environ.get("FT_CLIENT_SECRET")
    if not (cid and sec):
        print("   (France Travail ignoré : pas de clé FT_CLIENT_ID / FT_CLIENT_SECRET)")
        return []
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec,
                                   "scope": "api_offresdemploiv2 o2dsoffre"}).encode()
    tok = get("https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
              {"Content-Type": "application/x-www-form-urlencoded"}, data=body)
    if not tok:
        return []
    token = json.loads(tok)["access_token"]
    res = []
    for q in requetes:
        u = ("https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search?"
             + urllib.parse.urlencode({"motsCles": q, "commune": CFG["code_insee"], "distance": CFG["rayon_km"],
                                       "range": "0-49", "sort": 1}))
        r = get(u, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if not r:
            continue
        for o in json.loads(r).get("resultats", []):
            res.append(offre("France Travail", o["id"], o.get("intitule", ""), (o.get("entreprise") or {}).get("nom", ""),
                             (o.get("lieuTravail") or {}).get("libelle", ""),
                             f"https://candidat.francetravail.fr/offres/recherche/detail/{o['id']}",
                             contrat=o.get("typeContratLibelle") or o.get("typeContrat", ""),
                             salaire=(o.get("salaire") or {}).get("libelle", ""),
                             date_pub=o.get("dateCreation", ""), extrait=o.get("description", "")))
        time.sleep(0.5)
    return res


# ---------- Adzuna (API, clé gratuite) ----------
def adzuna(requetes):
    aid, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (aid and key):
        print("   (Adzuna ignoré : pas de clé ADZUNA_APP_ID / ADZUNA_APP_KEY)")
        return []
    res = []
    for q in requetes:
        u = ("https://api.adzuna.com/v1/api/jobs/fr/search/1?"
             + urllib.parse.urlencode({"app_id": aid, "app_key": key, "what": q, "where": CFG["ville"],
                                       "distance": CFG["rayon_km"], "results_per_page": 50, "max_days_old": 60}))
        r = get(u)
        if not r:
            continue
        for o in json.loads(r).get("results", []):
            sal = f"{int(o['salary_min'])} - {int(o['salary_max'])} €/an" if o.get("salary_min") and o.get("salary_max") else ""
            res.append(offre("Adzuna", o["id"], o.get("title", ""), (o.get("company") or {}).get("display_name", ""),
                             (o.get("location") or {}).get("display_name", ""), o.get("redirect_url", ""),
                             contrat=o.get("contract_time", "") or "", salaire=sal,
                             date_pub=o.get("created", ""), extrait=o.get("description", "")))
        time.sleep(0.5)
    return res


# ---------- Jooble (API, clé gratuite) ----------
def jooble(requetes):
    key = os.environ.get("JOOBLE_KEY")
    if not key:
        print("   (Jooble ignoré : pas de clé JOOBLE_KEY)")
        return []
    res = []
    for q in requetes:
        body = json.dumps({"keywords": q, "location": CFG["ville"], "radius": str(CFG["rayon_km"]), "page": "1"}).encode()
        r = get(f"https://jooble.org/api/{key}", {"Content-Type": "application/json"}, data=body)
        if not r:
            continue
        for o in json.loads(r).get("jobs", []):
            res.append(offre("Jooble", o.get("id", ""), o.get("title", ""), o.get("company", ""), o.get("location", ""),
                             o.get("link", ""), contrat=o.get("type", ""), salaire=o.get("salary", ""),
                             date_pub=o.get("updated", ""), extrait=o.get("snippet", "")))
        time.sleep(0.5)
    return res


# ---------- Descriptions complètes (LinkedIn, HelloWork) ----------
def description_detail(source, url):
    if source == "Meteojob":
        jp = jsonld_offre(get(url))
        return texte_brut(jp.get("description", ""))[:5000] if jp else ""
    if source == "LinkedIn":
        m = re.search(r"(\d+)$", url)
        page = get(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{m.group(1)}") if m else None
        mm = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page or "", re.S)
        return texte_brut(mm.group(1))[:5000] if mm else ""
    if source == "HelloWork":
        page = get(url)
        blocs = re.findall(r'data-truncate-text-target="content">(.*?)</div>\s*(?:<div|</div|<button)', page or "", re.S)
        return "\n\n".join(texte_brut(b) for b in blocs)[:5000]
    return ""


# ---------- Géolocalisation (geo.api.gouv.fr, gratuit, sans clé) ----------
GEO_FICHIER = RACINE / "data" / "geo.json"
GEO = json.loads(GEO_FICHIER.read_text(encoding="utf-8")) if GEO_FICHIER.exists() else {}


def nom_commune(lieu):
    lieu = re.sub(r"^\d{2,3}\s*-\s*", "", lieu or "")  # France Travail : « 34 - Béziers »
    n = re.split(r"\s+-\s+|,|\(", lieu)[0]
    return re.sub(r"\b\d{5}\b", "", n).strip()


def distance_km(a, b):
    from math import radians, sin, cos, asin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def geocoder(nom, ref):
    """Commune la plus proche du centre de recherche portant ce nom."""
    if not nom or norm(nom) in ("occitanie", "france", "languedoc roussillon"):
        return None
    if nom in GEO:
        return GEO[nom]
    r = get("https://geo.api.gouv.fr/communes?" + urllib.parse.urlencode({"nom": nom, "fields": "nom,centre", "limit": 8}))
    pos = None
    try:
        cands = [(c["nom"], (c["centre"]["coordinates"][1], c["centre"]["coordinates"][0])) for c in json.loads(r or "[]")]
        exact = [c for c in cands if norm(c[0]) == norm(nom)] or cands
        if exact:
            nom_ok, (la, lo) = min(exact, key=lambda c: distance_km(c[1], ref))
            pos = [round(la, 4), round(lo, 4), nom_ok]
    except Exception:
        pos = None
    GEO[nom] = pos
    time.sleep(0.2)
    return pos


# ---------- Filtrage et fusion ----------
def pertinente(o):
    t = norm(o["titre"])
    if not any(norm(k) in t for k in CFG["titre_doit_contenir"]):
        return False
    if any(norm(k) in t for k in CFG["titre_exclu"]):
        return False
    # le rayon est déjà appliqué par les sites ; on écarte seulement les lieux trop vagues
    return norm(o["lieu"]) not in CFG["lieux_refuses"]


def est_agro(o):
    t = " " + norm(" ".join([o["titre"], o["entreprise"], o["extrait"]])) + " "
    # mots courts (vin, ifs, brc…) : mot entier ; mots longs : début de mot
    return any((" " + norm(k) + " " if len(k) <= 4 else " " + norm(k)) in t for k in CFG["mots_agro"])


def cle(o):
    ville = norm(o["lieu"]).split(" ")[0]
    return hashlib.sha1(f"{norm(o['titre'])}|{norm(o['entreprise'])}|{ville}".encode()).hexdigest()[:12]


def main():
    print("Collecte des offres…")
    brut = []
    for nom, f in (("LinkedIn", linkedin), ("HelloWork", hellowork), ("Meteojob", meteojob), ("Welcome to the Jungle", wttj)):
        n = 0
        for q in CFG["requetes"]:
            r = f(q)
            n += len(r)
            brut += r
        print(f" {nom}: {n} résultats bruts")
    for nom, f in (("France Travail", france_travail), ("Adzuna", adzuna), ("Jooble", jooble)):
        r = f(CFG["requetes"])
        brut += r
        if r:
            print(f" {nom}: {len(r)} résultats bruts")

    anciennes = {}
    if SORTIE.exists():
        for o in json.loads(SORTIE.read_text(encoding="utf-8")).get("offres", []):
            anciennes[o["id"]] = o

    vues = {}
    for o in brut:
        if not pertinente(o):
            continue
        k = cle(o)
        lien = {"source": o["source"], "url": o["url"]}
        if k in vues:
            v = vues[k]
            if all(l["source"] != o["source"] for l in v["liens"]):
                v["liens"].append(lien)
            v["date_pub"] = min([d for d in (v["date_pub"], o["date_pub"]) if d] or [""])
            for c in ("contrat", "salaire", "extrait", "description"):
                v[c] = v[c] or o[c]
        else:
            vues[k] = {"id": k, "titre": o["titre"], "entreprise": o["entreprise"], "lieu": o["lieu"],
                       "contrat": o["contrat"], "salaire": o["salaire"], "date_pub": o["date_pub"],
                       "extrait": o["extrait"], "description": o["description"], "liens": [lien]}

    limite = (date.today() - timedelta(days=CFG["age_max_jours"])).isoformat()
    offres, nb_detail = [], 0
    for k, v in vues.items():
        ancien = anciennes.pop(k, None)
        v["premiere_vue"] = ancien["premiere_vue"] if ancien else AUJOURDHUI
        v["derniere_vue"] = AUJOURDHUI
        if not v.get("description") and ancien and ancien.get("description"):
            v["description"] = ancien["description"]
        if (v["date_pub"] or v["premiere_vue"]) < limite:
            continue  # plus d'un mois : supprimée
        if not v.get("description") and nb_detail < 90:
            for l in v["liens"]:
                d = description_detail(l["source"], l["url"])
                nb_detail += 1
                time.sleep(0.8)
                if d:
                    v["description"] = d
                    break
        v["agro"] = est_agro(v)
        offres.append(v)
    for k, v in anciennes.items():  # plus en ligne : gardée tant qu'elle a moins d'un mois
        if (v["date_pub"] or v["premiere_vue"]) >= limite:
            offres.append(v)

    centre = geocoder(CFG["ville"], (43.5733, 3.8366)) or [43.5733, 3.8366, CFG["ville"]]
    gardees = []
    for v in offres:
        pos = geocoder(nom_commune(v["lieu"]), centre[:2])
        v["lat"], v["lon"], v["commune"] = (pos[0], pos[1], pos[2]) if pos else (None, None, "")
        if pos and distance_km(pos[:2], centre[:2]) > CFG["rayon_km"] * 1.2:
            continue  # nettement hors du rayon demandé
        gardees.append(v)
    offres = gardees
    GEO_FICHIER.write_text(json.dumps(GEO, ensure_ascii=False, indent=0), encoding="utf-8")

    offres.sort(key=lambda o: o["date_pub"] or o["premiere_vue"], reverse=True)
    SORTIE.parent.mkdir(exist_ok=True)
    SORTIE.write_text(json.dumps({"maj": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                                  "centre": centre[:2], "rayon_km": CFG["rayon_km"], "offres": offres}, ensure_ascii=False, indent=1), encoding="utf-8")
    actives = sum(o["derniere_vue"] == AUJOURDHUI for o in offres)
    print(f"=> {len(offres)} offres ({actives} en ligne aujourd'hui) -> {SORTIE}")


if __name__ == "__main__":
    main()

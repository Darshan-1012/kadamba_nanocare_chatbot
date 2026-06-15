"""Wellness food & supplement recommendation engine.

Deterministic (no LLM). Knowledge base sourced from:
  - app/Functional food.pdf
  - app/medicine list and indications.pdf
  - app/general wellness.docx
  - app/kadamba wellness.docx

Maps body-system scores, dimension scores, and metrics to personalized
food, medicine, herbal, lifestyle, yoga, and diet recommendations.
"""
import logging

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Functional Foods (from Functional food.pdf)
# ═══════════════════════════════════════════════════════════════════════
FUNCTIONAL_FOODS = [
    {"name": "Nano Cookies", "indications": ["diabetes", "pcos", "stress", "immunity weakness", "fatigue"]},
    {"name": "Nano Tea & Coffee Capsules", "indications": ["anxiety", "stress", "insomnia", "brain fog", "poor concentration"]},
    {"name": "Nano Energy Bars", "indications": ["anaemia", "fatigue", "weakness", "low stamina", "recovery support"]},
    {"name": "Nano Herbal Water", "indications": ["fatty liver", "detoxification", "low immunity", "gut imbalance"]},
    {"name": "Nano Ketone Chocolates", "indications": ["stress", "anxiety", "memory issues", "cognitive fatigue"]},
    {"name": "Nano Ice Cream", "indications": ["gut sensitivity", "poor sleep", "weak immunity", "bone weakness"]},
    {"name": "Nano Extruded Snacks", "indications": ["obesity", "metabolic syndrome", "diabetes", "cholesterol imbalance"]},
    {"name": "Nano Date Jam", "indications": ["anaemia", "low energy", "weakness", "nutritional deficiency"]},
    {"name": "Nano Crackers", "indications": ["diabetes", "heart wellness", "fatigue", "weight management"]},
    {"name": "Nano Biscuits", "indications": ["immunity weakness", "poor memory", "children nutrition", "bone health"]},
    {"name": "Iron Functional Foods", "indications": ["iron deficiency anaemia", "low haemoglobin", "chronic fatigue", "weakness", "menstrual fatigue", "low energy metabolism"]},
]

# ═══════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — Kadamba Nano Medicines (from medicine list PDF)
# ═══════════════════════════════════════════════════════════════════════
MEDICINES = [
    {"name": "INSOREST", "indications": ["insomnia", "somnipathies"]},
    {"name": "FEMINOM", "indications": ["menstrual health", "reproductive health", "menopausal syndrome"]},
    {"name": "NANOCOUNT", "indications": ["low platelet count", "sepsis"]},
    {"name": "CARDIELIX", "indications": ["heart tonic", "blood circulation"]},
    {"name": "NANOMIG", "indications": ["migraine", "headache"]},
    {"name": "NANOLIVA", "indications": ["fatty liver", "NALD"]},
    {"name": "GLUCONIM", "indications": ["type 2 diabetes"]},
    {"name": "NANO-URJA", "indications": ["brain tonic", "mental fatigue", "memory retention", "oxidative stress"]},
    {"name": "COGNIKA", "indications": ["cognitive impairment", "confusion", "lack of concentration"]},
    {"name": "BRIFOCUS", "indications": ["dyslexia", "dysgraphia"]},
    {"name": "HORMOEASE", "indications": ["pcos", "pcod", "pms"]},
    {"name": "SLEEPON", "indications": ["sleep enhancement", "somnipathies"]},
    {"name": "NANO-UTI", "indications": ["urinary tract infection", "cystitis", "urethritis"]},
    {"name": "HLMAX", "indications": ["heart tonic", "lung tonic", "hyperlipidaemia"]},
    {"name": "NANOVITIX SYRUP", "indications": ["vitiligo", "pityriasis alba"]},
    {"name": "NANOUTERA", "indications": ["fibroid uterus", "uterine polyp", "adenomyosis"]},
    {"name": "CHAITHANYA", "indications": ["general wellness", "stress reduction", "immunity boost", "rasayana"]},
    {"name": "ENRGY B", "indications": ["energy booster", "fatigue", "mitochondrial function"]},
    {"name": "PINACI SYRUP", "indications": ["antibiotic"]},
    {"name": "HORMOSYNC", "indications": ["hormone imbalance", "pms", "acne"]},
    {"name": "NANO-TB", "indications": ["tuberculosis", "pneumonia"]},
    {"name": "NANO-DMN", "indications": ["diabetic neuropathy"]},
    {"name": "NANO-COLON", "indications": ["diverticulosis", "ulcerative colitis", "gastroenteritis", "gut sensitivity"]},
    {"name": "NANO-WBC", "indications": ["low wbc count", "immunity"]},
    {"name": "NATENDA", "indications": ["aids", "hiv", "std"]},
    {"name": "NANO-BS", "indications": ["biliary sludge"]},
    {"name": "ERITRO CARE", "indications": ["malaria", "viral fevers"]},
    {"name": "NANOMORR", "indications": ["haemorrhoids", "fissure"]},
    {"name": "NANO TE", "indications": ["tennis elbow", "cts"]},
    {"name": "NANOLGIA", "indications": ["polyarthralgia", "fibromyalgia", "myositis", "tendinitis"]},
    {"name": "PARALINO", "indications": ["paralysis", "cerebral palsy"]},
    {"name": "NANO-BRON", "indications": ["bronchiectasis", "copd", "ild"]},
    {"name": "PULMOHYPE", "indications": ["pulmonary hypertension"]},
    {"name": "MEDnephro", "indications": ["ckd", "diabetic ketoacidosis"]},
    {"name": "NANOMENTIA", "indications": ["dementia", "memory issue"]},
    {"name": "NANOBEPROPHYPE", "indications": ["bph"]},
    {"name": "NANO-IBS", "indications": ["ibs", "ibd"]},
    {"name": "PSORTHOTIS", "indications": ["psoriatic arthritis", "sle"]},
    {"name": "SYNEPHRO", "indications": ["nephrotic syndrome", "edema"]},
    {"name": "CHRONPAN", "indications": ["pancreatitis"]},
    {"name": "METASYND", "indications": ["metabolic syndrome"]},
    {"name": "NANOINSONPS", "indications": ["parkinsons disease"]},
    {"name": "HYTHROSIM", "indications": ["hypothyroidism"]},
    {"name": "STEROSIS", "indications": ["osteoporosis", "brittle bone syndrome", "rickets"]},
    {"name": "NEUROBLAR", "indications": ["neurogenic bladder"]},
    {"name": "NANOPSO SYRUP", "indications": ["psoriasis", "eczema"]},
    {"name": "NANOEURO", "indications": ["neuropathy"]},
    {"name": "FISTINOLA", "indications": ["fistula in ano"]},
    {"name": "AVANEC", "indications": ["avascular necrosis"]},
    {"name": "NANOLIM", "indications": ["lipoma"]},
    {"name": "NENDOCRINE", "indications": ["neuroendocrine tumour", "endocrine disorder"]},
    {"name": "NANO-RA", "indications": ["rheumatoid arthritis", "sle"]},
    {"name": "NANOLYS", "indications": ["liver cirrhosis", "hepatitis"]},
    {"name": "NANOADHD", "indications": ["adhd", "autism"]},
    {"name": "NANOHIST", "indications": ["allergic rhinitis", "upper respiratory issues"]},
    {"name": "NANO-MS", "indications": ["multiple sclerosis", "autoimmune disease"]},
    {"name": "NANOTIC", "indications": ["sciatica", "disc bulge", "herniated disc"]},
    {"name": "NANOHIVE", "indications": ["urticaria"]},
    {"name": "THYROTON", "indications": ["thyroid tonic", "goitre"]},
    {"name": "NANODETOX", "indications": ["detoxification", "rejuvenation"]},
    {"name": "GYNOVIVA", "indications": ["irregular periods", "leucorrhoea"]},
    {"name": "MENSTROEEASE", "indications": ["dysmenorrhea", "endometriosis"]},
    {"name": "NANO TN SYRUP", "indications": ["hypertension"]},
    {"name": "STREONIC DRINK", "indications": ["anxiety", "stress", "panic attack"]},
    {"name": "NANO VERIVA SYRUP", "indications": ["varicose vein", "spider vein", "dvt"]},
    {"name": "NANOHRIDICA SYRUP", "indications": ["coronary artery disease", "angina", "atherosclerosis"]},
    {"name": "NANO RENAL", "indications": ["renal dysfunction", "nephrotoxicity", "kidney tonic"]},
    {"name": "PULMOFECT", "indications": ["lung infection", "lower respiratory infection"]},
    {"name": "NANOIMM", "indications": ["immune booster", "infection prevention"]},
    {"name": "JOINTESE", "indications": ["osteoarthritis", "gout", "bursitis"]},
    {"name": "NANORASE", "indications": ["gastritis", "gerd", "peptic ulcer", "bloating"]},
    {"name": "TOUCH TONIC", "indications": ["sexual wellness", "ed"]},
    {"name": "PRANONIC DRINK", "indications": ["asthma", "bronchitis", "copd"]},
    {"name": "NANOGIA", "indications": ["menorrhagia", "pid", "dub"]},
    {"name": "NANO WNDC SYRUP", "indications": ["wound healing", "diabetic foot", "venous ulcer"]},
    {"name": "NANOSIS SYRUP", "indications": ["psychosis", "schizophrenia"]},
    {"name": "NANOLEPSY SYRUP", "indications": ["epilepsy", "syncope"]},
    {"name": "NANODICE SYRUP", "indications": ["jaundice", "thalassemia"]},
    {"name": "AMPLAMIA", "indications": ["aplastic anaemia", "anaemia"]},
    {"name": "NANO DPi", "indications": ["depigmentation", "melasma"]},
    {"name": "NANOLAUMA", "indications": ["glaucoma", "ocular hypertension"]},
]

# ═══════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE — General Wellness (from general wellness.docx)
# ═══════════════════════════════════════════════════════════════════════
GENERAL_WELLNESS = {
    "stress_management": {
        "dos": [
            "Low glycemic index foods rich in magnesium and omega-3",
            "Maintain proper hydration",
            "7-9 hours of quality sleep",
            "Mindful meditation",
            "Walking, jogging, cycling, swimming for relaxation",
            "Spend time with nature or pets",
            "Prayer and participation in calming activities",
            "Journaling and positive thinking",
        ],
        "donts": [
            "Avoid excessive caffeine",
            "Reduce refined sugar and sweets",
            "Skip refined carbohydrates",
            "Limit processed, oily, and fast foods",
            "Avoid packaged/processed snacks",
            "Avoid alcohol and smoking",
        ],
        "herbal": ["ashwagandha", "brahmi", "shankapushpi", "yasti madhu", "guduchi"],
        "drinks": ["green tea", "golden milk"],
        "nano_medicine": "STREONIC DRINK",
        "yoga": ["shavasana", "balasana", "nadi shodhana pranayama"],
    },
    "sleep_hygiene": {
        "dos": [
            "Avoid screen time 1 hour before bed",
            "Calm activities before sleep: reading, meditation, music",
            "15 min gentle walk after dinner",
            "At least 2 hour gap between dinner and bed",
            "Consistent sleep and wake schedule",
            "Regular exercise during daytime",
            "Dark, cool room temperature",
            "Comfortable mattresses",
        ],
        "donts": [
            "Avoid caffeine, nicotine, alcohol before sleep",
            "Avoid heavy meals at night",
            "Avoid long naps during daytime",
        ],
        "diet": ["almonds", "walnuts", "pista", "pumpkin seeds", "leafy greens", "banana", "warm milk"],
        "nano_medicine": "INSOREST",
    },
    "lifestyle": {
        "dos": [
            "Consistent sleep and awake schedule",
            "Regular exercise/jogging/walk/gym for at least 45 min",
            "Practice meditation and prayers regularly",
            "Maintain balanced diet",
            "Replace junk with fresh fruits, sprouts and vegetables",
            "Fasting at least once in 15 days",
            "Maintain proper hydration throughout the day",
            "Use stairs instead of elevator",
            "Post lunch walk 10-15 min",
            "Take break after 60-90 min and do stretching",
            "Spend quality time with family and friends",
            "Spend time with nature and gardening",
        ],
        "donts": [
            "Avoid smoking and alcohol",
            "Avoid day sleep/nap",
            "Limit screen time",
            "Avoid sedentary lifestyle",
        ],
    },
    "weight_loss": {
        "herbal": ["green tea", "ginger tea", "honey water", "triphala", "trikatu", "guggulu"],
        "donts": [
            "Avoid highly processed foods",
            "Avoid sugary drinks and refined carbohydrates",
            "Avoid fried foods",
            "Avoid excessive alcohol",
            "Avoid liquid calories: soda, caffeine, fruit juices",
        ],
    },
    "weight_gain": {
        "herbal": ["ashwagandha", "shatavari", "vidarikanda", "kushmandavaleha"],
        "donts": [
            "Avoid skipping protein",
            "Avoid excessive sugar and processed sweets",
            "Avoid deep-fried snacks",
            "Avoid alcohol and smoking",
        ],
    },
    "fatigue": {
        "herbal": ["ashwagandha", "triphala", "guduchi", "shilajith", "shatavari"],
        "drinks": ["ashwagandha with warm milk", "tulsi tea", "golden milk"],
    },
    "immune_boost": {
        "herbal": ["amalaka", "guduchi", "turmeric", "ashwagandha", "tulsi", "honey"],
        "drinks": ["tulsi water", "golden milk", "ginger cumin fennel tea", "warm water"],
    },
    "vitamin_d_calcium": {
        "vegetables": ["spinach", "moringa", "methi", "okra", "mushroom", "broccoli"],
        "spices": ["clove", "fenugreek", "curry leaves", "sesame"],
        "fruits_seeds": ["almonds", "raisins", "figs", "orange", "chia seed", "halim seed"],
        "dairy": ["milk", "yogurt", "paneer", "cheese", "soy milk", "almond milk"],
        "grains": ["ragi", "oats", "red gram", "urad dal", "soya products"],
        "lifestyle": ["sunlight exposure", "weight-bearing exercises", "walking", "jogging"],
    },
}

# ═══════════════════════════════════════════════════════════════════════
# SYSTEM → CONDITION MAPPING
# Maps body system states to searchable condition keywords
# ═══════════════════════════════════════════════════════════════════════
_SYSTEM_CONDITION_MAP = {
    "nervous": ["stress", "anxiety", "brain fog", "cognitive", "neuropathy", "mental fatigue", "insomnia", "poor concentration", "memory"],
    "cardiovascular": ["heart", "blood circulation", "hypertension", "coronary artery disease", "angina", "atherosclerosis", "hyperlipidaemia"],
    "respiratory": ["lung", "respiratory", "asthma", "bronchitis", "copd", "breathing"],
    "musculoskeletal": ["bone", "osteoporosis", "osteoarthritis", "joint", "muscle", "fibromyalgia", "arthralgia"],
    "digestive": ["gastritis", "gerd", "gut", "digestive", "bloating", "ibs", "liver", "fatty liver", "peptic ulcer"],
    "integumentary": ["skin", "psoriasis", "eczema", "vitiligo", "dermatitis", "urticaria"],
    "endocrine": ["diabetes", "thyroid", "hypothyroidism", "hormone", "metabolic syndrome", "endocrine"],
    "urogenital": ["uti", "kidney", "renal", "urinary", "bladder", "nephro"],
    "reproductive": ["menstrual", "reproductive", "pcos", "fibroid", "menorrhagia", "sexual wellness"],
    "immune": ["immunity", "immune", "infection", "autoimmune", "allergy", "allergic rhinitis"],
}

# Metrics thresholds for condition mapping
_METRIC_CONDITIONS = {
    "bmi_high": {"field": "bmi", "threshold": 25.0, "op": ">=", "conditions": ["obesity", "weight management", "metabolic syndrome"]},
    "bmi_low": {"field": "bmi", "threshold": 18.5, "op": "<", "conditions": ["weakness", "low energy", "weight gain"]},
    "body_fat_high": {"field": "bodyFat", "threshold": 25.0, "op": ">=", "conditions": ["obesity", "weight management", "cholesterol imbalance"]},
    "heart_rate_high": {"field": "heartRate", "threshold": 100, "op": ">=", "conditions": ["heart", "stress", "anxiety"]},
    "lf_hf_high": {"field": "lfhfRatio", "threshold": 3.0, "op": ">=", "conditions": ["stress", "anxiety"]},
    "energy_low": {"field": "energyReserve", "threshold": 60, "op": "<", "conditions": ["fatigue", "low energy", "weakness"]},
}

_NADI_TEXT_CONDITIONS = {
    ("sleep", "insomnia", "restless", "disturbance"): ["insomnia", "poor sleep", "stress"],
    ("stress", "overthinking", "hyperthinking", "anxiety"): ["stress", "anxiety", "mental fatigue"],
    ("thyroid",): ["thyroid", "hormone", "endocrine"],
    ("skin", "rash", "inflammation"): ["skin", "dermatitis"],
    ("stomach", "acidity", "hyperacidity", "dyspepsia", "indigestion"): ["digestive", "gastritis", "gerd"],
    ("pitta",): ["digestive", "skin", "stress"],
}


def _collect_text(value) -> str:
    """Flatten nested parsed report data into searchable lowercase text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, dict):
        return " ".join(_collect_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_collect_text(v) for v in value)
    return str(value).lower()


def _item_names(items: list, limit: int = 8, title_case: bool = False) -> list[str]:
    """Return display names from a list of strings or dicts."""
    names = []
    for item in items or []:
        if isinstance(item, dict):
            name = item.get("name", "")
        else:
            name = str(item)
        name = name.strip()
        if not name:
            continue
        names.append(name.title() if title_case and name.islower() else name)
    return list(dict.fromkeys(names))[:limit]


def apply_recommendations_to_wellness(
    wellness: dict | None,
    recommendations: dict | None,
    nadi_data: dict | None = None,
) -> dict:
    """Copy food knowledge recommendations into the report's visible wellness fields."""
    wellness = dict(wellness or {})
    recommendations = recommendations or {}

    nadi_wellness = (nadi_data or {}).get("wellness", {})
    diet = recommendations.get("diet", {})

    nadi_foods = _item_names(nadi_wellness.get("diet_eat", []), limit=6)
    knowledge_foods = _item_names(diet.get("recommended", []), limit=8)
    functional_foods = _item_names(recommendations.get("functional_foods", []), limit=5)
    avoid_foods = _item_names(diet.get("avoid", []), limit=5)

    diet_parts = []
    recommended_foods = list(dict.fromkeys(nadi_foods + knowledge_foods))
    if recommended_foods:
        diet_parts.append(f"Recommended foods: {', '.join(recommended_foods)}.")
    if functional_foods:
        diet_parts.append(f"Functional foods: {', '.join(functional_foods)}.")
    if avoid_foods:
        diet_parts.append(f"Avoid or limit: {', '.join(avoid_foods)}.")
    if diet_parts:
        wellness["diet"] = " ".join(diet_parts)

    yoga = _item_names(nadi_wellness.get("yoga", []), limit=5)
    yoga.extend(_item_names(recommendations.get("yoga", []), limit=5, title_case=True))
    if yoga:
        wellness["yoga"] = ", ".join(list(dict.fromkeys(yoga))[:8])

    exercise = _item_names(nadi_wellness.get("exercise", []), limit=6)
    if exercise:
        wellness["physicalActivity"] = ", ".join(exercise)

    nadi_supplements = _item_names(nadi_wellness.get("supplements", []), limit=5)
    herbs = _item_names(recommendations.get("herbal_support", []), limit=8, title_case=True)
    supplement_items = list(dict.fromkeys(nadi_supplements + herbs))
    if supplement_items:
        wellness["supplements"] = f"Supplements and herbal support: {', '.join(supplement_items)}."

    medicines = _item_names(recommendations.get("medicines", []), limit=5)
    nadi_medicines = _item_names(nadi_wellness.get("medicines", []), limit=4)
    medicine_items = list(dict.fromkeys(medicines + nadi_medicines))
    if medicine_items:
        wellness["medicine"] = f"Kadamba/Nadi medicines: {', '.join(medicine_items)}."

    lifestyle = recommendations.get("lifestyle", {})
    dos = _item_names(lifestyle.get("dos", []), limit=20)
    donts = _item_names(lifestyle.get("donts", []), limit=20)
    sleep_tips = [
        item for item in dos + donts
        if any(token in item.lower() for token in ("sleep", "bed", "dinner", "caffeine", "nap", "screen"))
    ][:4]
    if sleep_tips:
        wellness["sleep"] = " ".join(f"{tip}." for tip in sleep_tips)

    stress_tips = [
        item for item in dos + donts
        if any(token in item.lower() for token in ("meditation", "breathing", "relax", "stress", "nature", "journaling"))
    ][:4]
    if stress_tips:
        wellness["stress"] = " ".join(f"{tip}." for tip in stress_tips)

    return wellness


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def generate_recommendations(
    systems: dict,
    metrics: dict,
    nadi_data: dict | None = None,
    dimensions: dict | None = None,
) -> dict:
    """Generate personalized food/medicine/lifestyle recommendations.

    Args:
        systems: dict of 10 body systems, each with {score, status}
        metrics: dict with weight, bmi, bodyFat, heartRate, etc.
        nadi_data: optional dict with nadi-derived parameters
        dimensions: optional dict with physical/psychological/emotional/spiritual scores

    Returns:
        Structured recommendation dict for JSON storage / API consumption.
    """
    # 1. Identify priority systems (score < 80)
    priority = []
    for sys_key, sys_val in systems.items():
        score = sys_val.get("score", 100)
        if score < 80:
            priority.append({
                "name": sys_key.capitalize(),
                "score": score,
                "status": sys_val.get("displayStatus") or sys_val.get("status", "Need Attention"),
            })
    priority.sort(key=lambda x: x["score"])

    # 2. Collect all relevant condition keywords
    conditions = set()
    for p in priority:
        sys_key = p["name"].lower()
        conditions.update(_SYSTEM_CONDITION_MAP.get(sys_key, []))

    # Add metric-based conditions
    for rule in _METRIC_CONDITIONS.values():
        val = metrics.get(rule["field"])
        if val is not None:
            try:
                val = float(val)
                if rule["op"] == ">=" and val >= rule["threshold"]:
                    conditions.update(rule["conditions"])
                elif rule["op"] == "<" and val < rule["threshold"]:
                    conditions.update(rule["conditions"])
            except (ValueError, TypeError):
                pass

    # Add dimension-based conditions
    if dimensions:
        for dim_key in ("physical", "psychological", "emotional", "spiritual"):
            dim = dimensions.get(dim_key, {})
            score = dim.get("score", 100) if isinstance(dim, dict) else 100
            if score < 70:
                if dim_key == "psychological":
                    conditions.update(["stress", "anxiety", "mental fatigue", "poor concentration"])
                elif dim_key == "emotional":
                    conditions.update(["stress", "anxiety", "insomnia"])
                elif dim_key == "physical":
                    conditions.update(["fatigue", "weakness", "low energy"])
                elif dim_key == "spiritual":
                    conditions.update(["stress", "meditation"])

    # Add parsed Nadi risk/organ text conditions.
    if nadi_data:
        nadi_text = _collect_text({
            "dosha": nadi_data.get("dosha"),
            "organ_insights": nadi_data.get("organ_insights"),
            "potential_risks": nadi_data.get("potential_risks"),
            "health_params": nadi_data.get("health_params"),
        })
        for keywords, mapped_conditions in _NADI_TEXT_CONDITIONS.items():
            if any(keyword in nadi_text for keyword in keywords):
                conditions.update(mapped_conditions)

    # 3. Match functional foods
    matched_foods = []
    for food in FUNCTIONAL_FOODS:
        relevance = sum(1 for ind in food["indications"] if any(c in ind for c in conditions))
        if relevance > 0:
            matched_foods.append({
                "name": food["name"],
                "indication": ", ".join(food["indications"]),
                "relevance": relevance,
            })
    matched_foods.sort(key=lambda x: x["relevance"], reverse=True)

    # 4. Match medicines
    matched_meds = []
    for med in MEDICINES:
        relevance = sum(1 for ind in med["indications"] if any(c in ind for c in conditions))
        if relevance > 0:
            matched_meds.append({
                "name": med["name"],
                "indication": ", ".join(med["indications"]),
                "relevance": relevance,
            })
    matched_meds.sort(key=lambda x: x["relevance"], reverse=True)
    matched_meds = matched_meds[:10]  # top 10 most relevant

    # 5. Build lifestyle / herbal / yoga from general wellness
    herbal = set()
    yoga = set()
    lifestyle_dos = list(GENERAL_WELLNESS["lifestyle"]["dos"])
    lifestyle_donts = list(GENERAL_WELLNESS["lifestyle"]["donts"])
    diet_recommended = []
    diet_avoid = []

    # Stress-related
    stress_conditions = {"stress", "anxiety", "panic", "insomnia", "mental fatigue"}
    if conditions & stress_conditions:
        sm = GENERAL_WELLNESS["stress_management"]
        herbal.update(sm["herbal"])
        yoga.update(sm["yoga"])
        lifestyle_dos.extend(sm["dos"])
        lifestyle_donts.extend(sm["donts"])

    # Sleep-related
    sleep_conditions = {"insomnia", "poor sleep", "somnipathies"}
    if conditions & sleep_conditions:
        sl = GENERAL_WELLNESS["sleep_hygiene"]
        lifestyle_dos.extend(sl["dos"])
        lifestyle_donts.extend(sl["donts"])
        diet_recommended.extend(sl["diet"])

    # Weight-related
    weight_conditions = {"obesity", "weight management", "metabolic syndrome"}
    if conditions & weight_conditions:
        wl = GENERAL_WELLNESS["weight_loss"]
        herbal.update(wl["herbal"])
        diet_avoid.extend(wl["donts"])

    underweight_conditions = {"weight gain", "weakness"}
    if conditions & underweight_conditions:
        wg = GENERAL_WELLNESS["weight_gain"]
        herbal.update(wg["herbal"])

    # Fatigue-related
    fatigue_conditions = {"fatigue", "low energy", "weakness"}
    if conditions & fatigue_conditions:
        ft = GENERAL_WELLNESS["fatigue"]
        herbal.update(ft["herbal"])
        diet_recommended.extend(ft.get("drinks", []))

    # Immune-related
    immune_conditions = {"immunity", "immune", "infection"}
    if conditions & immune_conditions:
        im = GENERAL_WELLNESS["immune_boost"]
        herbal.update(im["herbal"])
        diet_recommended.extend(im.get("drinks", []))

    # Bone/calcium-related
    bone_conditions = {"bone", "osteoporosis", "calcium", "vitamin d"}
    if conditions & bone_conditions:
        vd = GENERAL_WELLNESS["vitamin_d_calcium"]
        diet_recommended.extend(vd.get("vegetables", []))
        diet_recommended.extend(vd.get("fruits_seeds", []))
        diet_recommended.extend(vd.get("dairy", []))

    # Always include base wellness recommendations if nothing matched
    if not herbal:
        herbal.update(["ashwagandha", "tulsi", "triphala"])
    if not yoga:
        yoga.update(["surya namaskar", "pranayama", "shavasana"])

    # Deduplicate
    lifestyle_dos = list(dict.fromkeys(lifestyle_dos))
    lifestyle_donts = list(dict.fromkeys(lifestyle_donts))
    diet_recommended = list(dict.fromkeys(diet_recommended))
    diet_avoid = list(dict.fromkeys(diet_avoid))

    result = {
        "priority_systems": priority,
        "functional_foods": [{k: v for k, v in f.items() if k != "relevance"} for f in matched_foods],
        "medicines": [{k: v for k, v in m.items() if k != "relevance"} for m in matched_meds],
        "herbal_support": sorted(herbal),
        "lifestyle": {
            "dos": lifestyle_dos,
            "donts": lifestyle_donts,
        },
        "yoga": sorted(yoga),
        "diet": {
            "recommended": diet_recommended,
            "avoid": diet_avoid,
        },
    }

    log.info(f"[FoodKnowledge] Generated recommendations: {len(priority)} priority systems, "
             f"{len(matched_foods)} foods, {len(matched_meds)} medicines")
    return result

"""
seed_data.py
Populates the SQLite DB with synthetic users, constituency block demographic
data, and ~80 realistic multilingual citizen submissions for demo purposes.
"""

import json
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from auth import HARDCODED_USERS
from database import User, Block, Submission

random.seed(42)

BLOCKS = [
    {
        "block_name": "Block A",
        "profile": "Severely underserved",
        "population": 18500,
        "children_6_14": 3200,
        "sc_st_percent": 74,
        "bpl_households": 2100,
        "nearest_school_km": 9.2,
        "school_capacity_used": 95,
        "nearest_hospital_km": 28.5,
        "hospital_capacity_used": 88,
        "road_paved_percent": 22,
        "existing_plans": "No active plan",
        "latitude": 23.2100,
        "longitude": 77.4200,
    },
    {
        "block_name": "Block B",
        "profile": "Counter-narrative (existing infra underused)",
        "population": 15200,
        "children_6_14": 2400,
        "sc_st_percent": 38,
        "bpl_households": 1200,
        "nearest_school_km": 3.1,
        "school_capacity_used": 55,
        "nearest_hospital_km": 0.8,
        "hospital_capacity_used": 30,
        "road_paved_percent": 65,
        "existing_plans": "Hospital completed 2019, specialist posts vacant",
        "latitude": 23.2350,
        "longitude": 77.3900,
    },
    {
        "block_name": "Block C",
        "profile": "Silent need (severe deficit, low reporting)",
        "population": 9800,
        "children_6_14": 2000,
        "sc_st_percent": 81,
        "bpl_households": 1600,
        "nearest_school_km": 14.5,
        "school_capacity_used": 98,
        "nearest_hospital_km": 35.0,
        "hospital_capacity_used": 92,
        "road_paved_percent": 12,
        "existing_plans": "",
        "latitude": 23.1800,
        "longitude": 77.4500,
    },
    {
        "block_name": "Block D",
        "profile": "Medium",
        "population": 21000,
        "children_6_14": 3600,
        "sc_st_percent": 45,
        "bpl_households": 1900,
        "nearest_school_km": 4.5,
        "school_capacity_used": 70,
        "nearest_hospital_km": 10.2,
        "hospital_capacity_used": 60,
        "road_paved_percent": 48,
        "existing_plans": "Road widening proposed",
        "latitude": 23.2600,
        "longitude": 77.4100,
    },
    {
        "block_name": "Block E",
        "profile": "Medium",
        "population": 17600,
        "children_6_14": 2900,
        "sc_st_percent": 33,
        "bpl_households": 1400,
        "nearest_school_km": 5.0,
        "school_capacity_used": 65,
        "nearest_hospital_km": 12.0,
        "hospital_capacity_used": 55,
        "road_paved_percent": 58,
        "existing_plans": "Digital literacy center underway",
        "latitude": 23.2200,
        "longitude": 77.3700,
    },
    {
        "block_name": "Block F",
        "profile": "Medium",
        "population": 14300,
        "children_6_14": 2300,
        "sc_st_percent": 40,
        "bpl_households": 1100,
        "nearest_school_km": 6.2,
        "school_capacity_used": 72,
        "nearest_hospital_km": 15.5,
        "hospital_capacity_used": 50,
        "road_paved_percent": 62,
        "existing_plans": "Sanitation project stalled",
        "latitude": 23.2450,
        "longitude": 77.4350,
    },
]

# ---------------------------------------------------------------------------
# Realistic multilingual raw content samples
# ---------------------------------------------------------------------------

HINDI_SAMPLES = [
    "हमारे गाँव में सड़क नहीं है, बच्चे स्कूल नहीं जा पाते।",
    "बिजली पिछले तीन दिनों से नहीं आई है, कृपया जल्दी ठीक करें।",
    "हमारे इलाके में पानी की बहुत कमी है, बोरवेल की जरूरत है।",
    "अस्पताल बहुत दूर है, इमरजेंसी में जाना मुश्किल होता है।",
    "गाँव में सफाई की व्यवस्था नहीं है, बीमारियाँ फैल रही हैं।",
]

HINGLISH_SAMPLES = [
    "Sir hamare block mein road bahut kharab hai, bacche school nahi ja pate.",
    "Yahan pichle hafte se bijli nahi hai, please jaldi dekhiye.",
    "Water supply bahut irregular hai humare gaon mein.",
    "Hospital bahut door hai, emergency mein bahut dikkat hoti hai.",
]

TAMIL_SAMPLES = [
    "எங்கள் கிராமத்தில் மருத்துவமனை இல்லை, மிகவும் தொலைவில் உள்ளது.",
    "சாலை மிக மோசமான நிலையில் உள்ளது, குழந்தைகள் பள்ளிக்கு செல்ல முடியவில்லை.",
    "குடிநீர் பற்றாக்குறை மிக அதிகமாக உள்ளது.",
]

TELUGU_SAMPLES = [
    "మా గ్రామంలో రోడ్డు లేదు, పిల్లలు బడికి వెళ్లలేకపోతున్నారు.",
    "ఆసుపత్రి చాలా దూరంగా ఉంది, అత్యవసర సమయంలో చాలా ఇబ్బంది.",
]

BENGALI_SAMPLES = [
    "আমাদের গ্রামে রাস্তা নেই, বাচ্চারা স্কুলে যেতে পারে না।",
    "হাসপাতাল অনেক দূরে, জরুরি অবস্থায় খুব সমস্যা হয়।",
]

MARATHI_SAMPLES = [
    "आमच्या गावात रस्ता नाही, मुलांना शाळेत जाणे कठीण होते.",
    "पाण्याची खूप टंचाई आहे, बोअरवेलची गरज आहे.",
]

ENGLISH_SAMPLES = [
    "The road in our block has been unpaved for years, please sanction repairs.",
    "We urgently need a new borewell as the existing water supply has failed.",
    "The primary health center here lacks a doctor most days of the week.",
    "Our children have to walk 8 km to reach the nearest school.",
    "Streetlights have not worked in our area for over two months.",
]

CATEGORY_SUBCATEGORY = {
    "Roads": ["Road Repair", "New Road Construction", "Bridge Repair"],
    "Water": ["Borewell", "Pipeline Repair", "Water Tank"],
    "Education": ["New School", "School Repair", "Teacher Shortage"],
    "Healthcare": ["PHC Staffing", "New Hospital", "Ambulance Service"],
    "Electricity": ["Power Outage", "New Connection", "Transformer Repair"],
    "Sanitation": ["Drainage", "Toilet Construction", "Garbage Collection"],
    "Agriculture": ["Irrigation", "Crop Insurance", "Fertilizer Subsidy"],
    "Housing": ["PM Awas Yojana", "Repair Grant", "Land Title"],
    "Digital": ["Internet Access", "Digital Literacy Center", "Mobile Tower"],
    "Employment": ["MGNREGA Work", "Skill Training", "Job Placement"],
}

URGENCY_LEVELS = ["low", "medium", "high", "critical"]
SENTIMENTS = ["neutral", "frustrated", "hopeful", "desperate"]
AFFECTED_POP = ["small", "medium", "large"]
LANGUAGES_ORDER = (
    ["Hindi"] * 20
    + ["Hinglish"] * 15
    + ["Tamil"] * 10
    + ["Telugu"] * 8
    + ["Bengali"] * 7
    + ["Marathi"] * 5
    + ["English"] * 15
)

LANGUAGE_SAMPLES = {
    "Hindi": HINDI_SAMPLES,
    "Hinglish": HINGLISH_SAMPLES,
    "Tamil": TAMIL_SAMPLES,
    "Telugu": TELUGU_SAMPLES,
    "Bengali": BENGALI_SAMPLES,
    "Marathi": MARATHI_SAMPLES,
    "English": ENGLISH_SAMPLES,
}

ENGLISH_TRANSLATIONS = {
    "हमारे गाँव में सड़क नहीं है, बच्चे स्कूल नहीं जा पाते।": "There is no road in our village, children cannot go to school.",
    "बिजली पिछले तीन दिनों से नहीं आई है, कृपया जल्दी ठीक करें।": "There has been no electricity for the past three days, please fix it soon.",
    "हमारे इलाके में पानी की बहुत कमी है, बोरवेल की जरूरत है।": "There is a severe water shortage in our area, a borewell is needed.",
    "अस्पताल बहुत दूर है, इमरजेंसी में जाना मुश्किल होता है।": "The hospital is very far, it's difficult to reach in an emergency.",
    "गाँव में सफाई की व्यवस्था नहीं है, बीमारियाँ फैल रही हैं।": "There is no sanitation system in the village, diseases are spreading.",
    "Sir hamare block mein road bahut kharab hai, bacche school nahi ja pate.": "Sir, the road in our block is in very bad condition, children cannot go to school.",
    "Yahan pichle hafte se bijli nahi hai, please jaldi dekhiye.": "There has been no electricity here for a week, please look into it soon.",
    "Water supply bahut irregular hai humare gaon mein.": "Water supply is very irregular in our village.",
    "Hospital bahut door hai, emergency mein bahut dikkat hoti hai.": "The hospital is very far, causing great difficulty during emergencies.",
    "எங்கள் கிராமத்தில் மருத்துவமனை இல்லை, மிகவும் தொலைவில் உள்ளது.": "There is no hospital in our village, it is very far away.",
    "சாலை மிக மோசமான நிலையில் உள்ளது, குழந்தைகள் பள்ளிக்கு செல்ல முடியவில்லை.": "The road is in very poor condition, children cannot go to school.",
    "குடிநீர் பற்றாக்குறை மிக அதிகமாக உள்ளது.": "There is a severe drinking water shortage.",
    "మా గ్రామంలో రోడ్డు లేదు, పిల్లలు బడికి వెళ్లలేకపోతున్నారు.": "There is no road in our village, children cannot go to school.",
    "ఆసుపత్రి చాలా దూరంగా ఉంది, అత్యవసర సమయంలో చాలా ఇబ్బంది.": "The hospital is very far, causing much difficulty during emergencies.",
    "আমাদের গ্রামে রাস্তা নেই, বাচ্চারা স্কুলে যেতে পারে না।": "There is no road in our village, children cannot go to school.",
    "হাসপাতাল অনেক দূরে, জরুরি অবস্থায় খুব সমস্যা হয়।": "The hospital is very far, causing great trouble in emergencies.",
    "आमच्या गावात रस्ता नाही, मुलांना शाळेत जाणे कठीण होते.": "There is no road in our village, it is difficult for children to go to school.",
    "पाण्याची खूप टंचाई आहे, बोअरवेलची गरज आहे.": "There is a severe water shortage, a borewell is needed.",
}


def _channel_for_index(i):
    return random.choice(["text", "text", "text", "voice", "image", "whatsapp", "sms", "ivrs"])


def _make_submission_kwargs(block_name, category, language, citizen_id, day_offset):
    subcat = random.choice(CATEGORY_SUBCATEGORY.get(category, ["General"]))
    raw = random.choice(LANGUAGE_SAMPLES.get(language, ENGLISH_SAMPLES))
    english_translation = ENGLISH_TRANSLATIONS.get(raw, raw)
    urgency = random.choices(URGENCY_LEVELS, weights=[15, 35, 35, 15])[0]
    sentiment = random.choice(SENTIMENTS)
    affected = random.choice(AFFECTED_POP)
    keywords = [category.lower(), subcat.lower().split()[0], block_name.lower().replace(" ", "_")]

    return dict(
        citizen_id=citizen_id,
        timestamp=datetime.now(timezone.utc) - timedelta(days=day_offset, hours=random.randint(0, 23)),
        source_channel=_channel_for_index(day_offset),
        raw_content=raw,
        transcribed_text=None,
        english_translation=english_translation,
        detected_language=language,
        category=category,
        subcategory=subcat,
        specific_need=english_translation,
        urgency_level=urgency,
        sentiment=sentiment,
        affected_population=affected,
        location_mentioned=block_name,
        latitude=None,
        longitude=None,
        keywords=json.dumps(keywords, ensure_ascii=False),
        image_description=None,
        status="received",
        budget_released=False,
        budget_amount=None,
        resolution_note=None,
    )


BLOCK_CATEGORY_PLAN = {
    "Block A": (["Roads"] * 8 + ["Education"] * 7 + ["Healthcare"] * 5),
    "Block B": (["Healthcare"] * 14 + ["Water"] * 4 + ["Roads"] * 2),
    "Block C": (["Employment"] * 2),
    "Block D": (["Roads"] * 5 + ["Water"] * 5 + ["Education"] * 5),
    "Block E": (["Digital"] * 4 + ["Employment"] * 5 + ["Electricity"] * 4),
    "Block F": (["Education"] * 4 + ["Sanitation"] * 3 + ["Housing"] * 3),
}


def seed_blocks(db: Session):
    if db.query(Block).count() > 0:
        return
    for b in BLOCKS:
        db.add(Block(**b))
    db.commit()


def seed_users(db: Session):
    if db.query(User).count() > 0:
        return
    for u in HARDCODED_USERS:
        db.add(
            User(
                username=u["username"],
                password_hash=u["password"],
                role=u["role"],
                constituency=u.get("constituency"),
            )
        )
    db.commit()


def seed_submissions(db: Session):
    if db.query(Submission).count() > 0:
        return

    citizens = db.query(User).filter(User.role == "citizen").all()
    citizen_ids = [c.id for c in citizens] if citizens else [None]

    languages = LANGUAGES_ORDER.copy()
    random.shuffle(languages)
    lang_iter = iter(languages)

    def next_language():
        nonlocal lang_iter
        try:
            return next(lang_iter)
        except StopIteration:
            return random.choice(list(LANGUAGE_SAMPLES.keys()))

    all_kwargs = []
    day_counter = 0
    for block_name, categories in BLOCK_CATEGORY_PLAN.items():
        for category in categories:
            language = next_language()
            citizen_id = random.choice(citizen_ids)
            kwargs = _make_submission_kwargs(block_name, category, language, citizen_id, day_counter)
            all_kwargs.append(kwargs)
            day_counter = (day_counter + 1) % 30

    random.shuffle(all_kwargs)

    # Assign statuses per the spec: 5 resolved+budget, 10 actioned, 15 under_review, rest received
    for idx, kwargs in enumerate(all_kwargs):
        if idx < 5:
            kwargs["status"] = "resolved"
            kwargs["budget_released"] = True
            kwargs["budget_amount"] = round(random.uniform(500000, 2000000), 2)
            kwargs["resolution_note"] = "Work completed and funds disbursed."
        elif idx < 15:
            kwargs["status"] = "actioned"
        elif idx < 30:
            kwargs["status"] = "under_review"
        else:
            kwargs["status"] = "received"

    for kwargs in all_kwargs:
        db.add(Submission(**kwargs))
    db.commit()


def seed_all(db: Session):
    seed_blocks(db)
    seed_users(db)
    seed_submissions(db)

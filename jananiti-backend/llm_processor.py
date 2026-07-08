"""
llm_processor.py
Uses google-generativeai (Gemini 1.5 Flash) for:
  - structured NLP analysis of citizen text submissions
  - vision analysis of uploaded infrastructure images
  - generating prioritized development-work rankings from submissions + block data
"""

import json
import os

import google.generativeai as genai

_MODEL_NAME = "gemini-2.5-flash"


def _get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY not configured. Set it in your .env file.")
    return key


def _configure():
    genai.configure(api_key=_get_api_key())


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if text.count("```") >= 2 else text.strip("`")
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


_DEFAULT_TEXT_ANALYSIS = {
    "detected_language": "English",
    "english_translation": None,  # filled in by caller with original text
    "category": "Other",
    "subcategory": "Unspecified",
    "specific_need": "Unable to determine specific need automatically.",
    "urgency_level": "medium",
    "sentiment": "neutral",
    "affected_population": "small",
    "location_mentioned": None,
    "keywords": [],
}


def analyze_text_with_llm(text: str, channel: str = "web") -> dict:
    """Analyze a citizen text submission and return structured fields."""
    _configure()
    model = genai.GenerativeModel(_MODEL_NAME)

    prompt = f"""You are analyzing a citizen grievance/request submitted to an Indian Member of Parliament.
The submission may be in Hindi, Tamil, Telugu, Bengali, Marathi, Hinglish, English, or another Indian language.

Submission text (channel: {channel}):
\"\"\"{text}\"\"\"

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this shape:
{{
  "detected_language": "Hindi|Tamil|English|Hinglish|Telugu|Bengali|Marathi|Other",
  "english_translation": "full translation if not English, else same text",
  "category": "Roads|Water|Education|Healthcare|Electricity|Sanitation|Agriculture|Housing|Digital|Employment|Other",
  "subcategory": "specific subcategory e.g. Road Repair, New School, Borewell",
  "specific_need": "one clear sentence of what citizen wants",
  "urgency_level": "low|medium|high|critical",
  "sentiment": "neutral|frustrated|hopeful|desperate",
  "affected_population": "small|medium|large",
  "location_mentioned": "place name or null",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}"""

    try:
        response = model.generate_content(prompt)
        cleaned = _strip_json_fences(response.text)
        data = json.loads(cleaned)
        # ensure all expected keys exist
        for k, v in _DEFAULT_TEXT_ANALYSIS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        fallback = dict(_DEFAULT_TEXT_ANALYSIS)
        fallback["english_translation"] = text
        return fallback


_DEFAULT_IMAGE_ANALYSIS = {
    "infrastructure_type": "other",
    "issue_identified": "Unable to automatically identify the issue in this image.",
    "severity": "moderate",
    "description": "Image submitted by citizen; automated analysis unavailable.",
    "category": "Other",
    "specific_need": "Manual review required.",
    "urgency_level": "medium",
    "detected_language": "English",
    "english_translation": None,
}


def analyze_image_with_llm(image_path: str, caption: str = "") -> dict:
    """Analyze an uploaded infrastructure photo with Gemini Vision."""
    _configure()
    model = genai.GenerativeModel(_MODEL_NAME)

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    ext = os.path.splitext(image_path)[1].lower().lstrip(".")
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")

    prompt = f"""You are analyzing a photo of public infrastructure submitted by a citizen to an Indian MP's office.
Citizen caption (may be in a regional language, or empty): "{caption}"

Return ONLY valid JSON, no markdown fences, no commentary, in exactly this shape:
{{
  "infrastructure_type": "road|school|hospital|water|electricity|sanitation|other",
  "issue_identified": "specific problem visible",
  "severity": "minor|moderate|severe|critical",
  "description": "2-sentence MP briefing",
  "category": "Roads|Water|Education|Healthcare|Electricity|Sanitation|Other",
  "specific_need": "what needs to be done",
  "urgency_level": "low|medium|high|critical",
  "detected_language": "language of caption or English",
  "english_translation": "caption translated or description"
}}"""

    try:
        response = model.generate_content(
            [prompt, {"mime_type": mime_type, "data": image_bytes}]
        )
        cleaned = _strip_json_fences(response.text)
        data = json.loads(cleaned)
        for k, v in _DEFAULT_IMAGE_ANALYSIS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        fallback = dict(_DEFAULT_IMAGE_ANALYSIS)
        fallback["english_translation"] = caption or fallback["description"]
        return fallback


def generate_rankings_with_llm(submissions: list, blocks: list) -> list:
    """Ask Gemini to produce 5 prioritized development-work recommendations."""
    _configure()
    model = genai.GenerativeModel(_MODEL_NAME)

    top_submissions = submissions[:50]
    submissions_summary = [
        {
            "category": s.get("category"),
            "subcategory": s.get("subcategory"),
            "urgency_level": s.get("urgency_level"),
            "sentiment": s.get("sentiment"),
            "location_mentioned": s.get("location_mentioned"),
            "specific_need": s.get("specific_need"),
            "affected_population": s.get("affected_population"),
        }
        for s in top_submissions
    ]

    prompt = f"""You are an AI policy analyst for an Indian Member of Parliament.
Given citizen submissions summary and constituency block (village-cluster) demographic data,
recommend the TOP 5 development works the MP should prioritize.

CITIZEN SUBMISSIONS (sample of {len(top_submissions)} of {len(submissions)} total):
{json.dumps(submissions_summary, ensure_ascii=False)}

BLOCK DEMOGRAPHIC DATA:
{json.dumps(blocks, ensure_ascii=False)}

Rules:
- Flag counter_narrative_flag=true if citizens are demanding something block data shows already exists (e.g. a hospital is nearby but underused).
- Flag silent_need_flag=true if block data shows a severe deficit (e.g. high SC/ST population, far from school/hospital) but there are few or no submissions from that block.

Return ONLY a valid JSON array (no markdown fences, no commentary) of exactly 5 objects in this shape:
[
  {{
    "priority_rank": 1,
    "development_work": "specific work with location",
    "category": "category",
    "justification": "2-3 sentences",
    "citizen_demand_evidence": "X submissions from Y areas",
    "estimated_beneficiaries": "number with reasoning",
    "suggested_action": "what MP should do",
    "funding_source": "MPLADS|State|Central",
    "urgency_score": 85,
    "demand_score": 78,
    "data_alignment_score": 70,
    "equity_score": 90,
    "cascading_impact_score": 65,
    "drfi_score": 78,
    "counter_narrative_flag": false,
    "counter_narrative_note": null,
    "silent_need_flag": false,
    "silent_need_note": null
  }}
]"""

    try:
        response = model.generate_content(prompt)
        cleaned = _strip_json_fences(response.text)
        data = json.loads(cleaned)
        if isinstance(data, dict):
            data = data.get("recommendations", []) or list(data.values())
        return data
    except Exception as e:
        return [
            {
                "priority_rank": 1,
                "development_work": "Unable to generate AI rankings",
                "category": "Other",
                "justification": f"LLM ranking generation failed: {str(e)}. Showing DRFI engine results only.",
                "citizen_demand_evidence": "",
                "estimated_beneficiaries": "",
                "suggested_action": "Retry ranking generation once GEMINI_API_KEY / quota is available.",
                "funding_source": "MPLADS",
                "urgency_score": 0,
                "demand_score": 0,
                "data_alignment_score": 0,
                "equity_score": 0,
                "cascading_impact_score": 0,
                "drfi_score": 0,
                "counter_narrative_flag": False,
                "counter_narrative_note": None,
                "silent_need_flag": False,
                "silent_need_note": None,
            }
        ]

"""
main.py
JanaNiti — AI-powered citizen development intelligence platform for Indian MPs.
FastAPI backend. Hackathon prototype: SQLite, no Docker, runs locally, deploys to Railway.
"""

import json
import os
import uuid
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Depends, HTTPException, Header, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func

import auth
import seed_data
from database import init_database, get_db, get_session, User, Submission, Block, Ranking, IVRSSession
import llm_processor
import voice_processor
import drfi_engine

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".webm"}
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}

URGENCY_WEIGHT = {"critical": 5, "high": 3, "medium": 2, "low": 1}


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_database()
    db = get_session()
    try:
        if db.query(Block).count() == 0:
            seed_data.seed_blocks(db)
        if db.query(User).count() == 0:
            seed_data.seed_users(db)
        if db.query(Submission).count() == 0:
            seed_data.seed_submissions(db)
    finally:
        db.close()
    print("JanaNiti backend ready. Visit http://localhost:8000/docs")
    yield


app = FastAPI(title="JanaNiti API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_mp_user(db: Session, authorization: str | None) -> User:
    user = auth.get_user_from_authorization_header(db, authorization)
    if not user or user.role != "mp":
        raise HTTPException(status_code=401, detail="MP authentication required")
    return user


def error_response(status_code: int, message: str):
    raise HTTPException(status_code=status_code, detail=message)


# ---------------------------------------------------------------------------
# AUTH ROUTES
# ---------------------------------------------------------------------------

@app.post("/auth/login")
def login(body: dict, db: Session = Depends(get_db)):
    try:
        username = body.get("username")
        password = body.get("password")
        if not username or not password:
            return {"success": False, "error": "username and password are required"}
        return auth.login(db, username, password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/verify")
def verify(body: dict, db: Session = Depends(get_db)):
    try:
        token = body.get("token", "")
        return auth.verify_token(db, token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/me")
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    try:
        user = auth.get_user_from_authorization_header(db, authorization)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
        return {
            "username": user.username,
            "role": user.role,
            "constituency": user.constituency,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# SUBMISSION ROUTES
# ---------------------------------------------------------------------------

@app.post("/submit/text")
def submit_text(body: dict, db: Session = Depends(get_db)):
    try:
        text = body.get("text")
        if not text:
            raise HTTPException(status_code=400, detail="'text' is required")
        channel = body.get("channel", "web")
        citizen_id = body.get("citizen_id")
        location_hint = body.get("location_hint")

        analysis = llm_processor.analyze_text_with_llm(text, channel=channel)

        submission = Submission(
            citizen_id=citizen_id,
            source_channel=channel,
            raw_content=text,
            english_translation=analysis.get("english_translation"),
            detected_language=analysis.get("detected_language"),
            category=analysis.get("category"),
            subcategory=analysis.get("subcategory"),
            specific_need=analysis.get("specific_need"),
            urgency_level=analysis.get("urgency_level"),
            sentiment=analysis.get("sentiment"),
            affected_population=analysis.get("affected_population"),
            location_mentioned=analysis.get("location_mentioned") or location_hint,
            keywords=json.dumps(analysis.get("keywords", []), ensure_ascii=False),
            status="received",
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        result = submission.to_dict()
        result["analysis"] = analysis
        return result
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit/voice")
async def submit_voice(
    audio_file: UploadFile = File(...),
    citizen_id: int | None = Form(default=None),
    channel: str = Form(default="voice_upload"),
    db: Session = Depends(get_db),
):
    try:
        ext = os.path.splitext(audio_file.filename or "")[1].lower()
        if ext not in ALLOWED_AUDIO_EXT:
            raise HTTPException(status_code=400, detail=f"Unsupported audio type: {ext}")

        audio_bytes = await audio_file.read()
        if len(audio_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Audio file exceeds 10MB limit")

        transcript = voice_processor.transcribe_audio(audio_bytes, audio_file.filename)
        analysis = llm_processor.analyze_text_with_llm(transcript, channel=channel)

        submission = Submission(
            citizen_id=citizen_id,
            source_channel=channel,
            raw_content=None,
            transcribed_text=transcript,
            english_translation=analysis.get("english_translation"),
            detected_language=analysis.get("detected_language"),
            category=analysis.get("category"),
            subcategory=analysis.get("subcategory"),
            specific_need=analysis.get("specific_need"),
            urgency_level=analysis.get("urgency_level"),
            sentiment=analysis.get("sentiment"),
            affected_population=analysis.get("affected_population"),
            location_mentioned=analysis.get("location_mentioned"),
            keywords=json.dumps(analysis.get("keywords", []), ensure_ascii=False),
            status="received",
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "transcript": transcript,
            "analysis": analysis,
            "submission_id": submission.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit/image")
async def submit_image(
    image_file: UploadFile = File(...),
    caption: str = Form(default=""),
    citizen_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    try:
        ext = os.path.splitext(image_file.filename or "")[1].lower()
        if ext not in ALLOWED_IMAGE_EXT:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {ext}")

        image_bytes = await image_file.read()
        if len(image_bytes) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="Image file exceeds 10MB limit")

        saved_name = f"{uuid.uuid4().hex}{ext}"
        saved_path = os.path.join(UPLOAD_DIR, saved_name)
        with open(saved_path, "wb") as f:
            f.write(image_bytes)

        analysis = llm_processor.analyze_image_with_llm(saved_path, caption)

        submission = Submission(
            citizen_id=citizen_id,
            source_channel="image",
            raw_content=caption,
            english_translation=analysis.get("english_translation"),
            detected_language=analysis.get("detected_language"),
            category=analysis.get("category"),
            subcategory=analysis.get("infrastructure_type"),
            specific_need=analysis.get("specific_need"),
            urgency_level=analysis.get("urgency_level"),
            image_description=analysis.get("description"),
            status="received",
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "image_description": analysis.get("description"),
            "analysis": analysis,
            "submission_id": submission.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/submit/ivrs")
def submit_ivrs(body: dict, db: Session = Depends(get_db)):
    try:
        phone_number = body.get("phone_number")
        selected_category = body.get("selected_category")
        spoken_text = body.get("spoken_text")
        citizen_id = body.get("citizen_id")

        if not phone_number:
            raise HTTPException(status_code=400, detail="'phone_number' is required")

        session_obj = IVRSSession(
            citizen_id=citizen_id,
            phone_number=phone_number,
            selected_category=selected_category,
            recorded_text=spoken_text,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(session_obj)
        db.commit()
        db.refresh(session_obj)

        analysis = {}
        if spoken_text:
            analysis = llm_processor.analyze_text_with_llm(spoken_text, channel="ivrs")

        submission = Submission(
            citizen_id=citizen_id,
            source_channel="ivrs",
            raw_content=spoken_text,
            english_translation=analysis.get("english_translation"),
            detected_language=analysis.get("detected_language"),
            category=analysis.get("category") or selected_category,
            subcategory=analysis.get("subcategory"),
            specific_need=analysis.get("specific_need"),
            urgency_level=analysis.get("urgency_level", "medium"),
            sentiment=analysis.get("sentiment"),
            affected_population=analysis.get("affected_population"),
            location_mentioned=analysis.get("location_mentioned"),
            keywords=json.dumps(analysis.get("keywords", []), ensure_ascii=False),
            status="received",
        )
        db.add(submission)
        db.commit()
        db.refresh(submission)

        return {
            "session_id": session_obj.id,
            "submission_id": submission.id,
            "confirmation_message": "Thank you. Your request has been recorded and will be reviewed by the MP's office.",
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/submissions")
def list_submissions(
    category: str | None = None,
    urgency: str | None = None,
    language: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    try:
        require_mp_user(db, authorization)
        q = db.query(Submission)
        if category:
            q = q.filter(Submission.category == category)
        if urgency:
            q = q.filter(Submission.urgency_level == urgency)
        if language:
            q = q.filter(Submission.detected_language == language)
        if status:
            q = q.filter(Submission.status == status)
        total = q.count()
        rows = q.order_by(Submission.timestamp.desc()).offset(offset).limit(limit).all()
        return {"total": total, "count": len(rows), "submissions": [r.to_dict() for r in rows]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/submissions/{submission_id}")
def get_submission(submission_id: int, db: Session = Depends(get_db)):
    try:
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")
        return sub.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/submissions/citizen/{citizen_id}")
def get_citizen_submissions(citizen_id: int, db: Session = Depends(get_db)):
    try:
        rows = (
            db.query(Submission)
            .filter(Submission.citizen_id == citizen_id)
            .order_by(Submission.timestamp.desc())
            .all()
        )
        return {"count": len(rows), "submissions": [r.to_dict() for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/submissions/{submission_id}/status")
def update_submission_status(
    submission_id: int,
    body: dict,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    try:
        require_mp_user(db, authorization)
        sub = db.query(Submission).filter(Submission.id == submission_id).first()
        if not sub:
            raise HTTPException(status_code=404, detail="Submission not found")

        new_status = body.get("status")
        if new_status:
            sub.status = new_status
        sub.budget_released = body.get("budget_released", sub.budget_released)
        if body.get("budget_amount") is not None:
            sub.budget_amount = body.get("budget_amount")
        if body.get("resolution_note") is not None:
            sub.resolution_note = body.get("resolution_note")

        db.commit()
        db.refresh(sub)
        return sub.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# ANALYTICS ROUTES
# ---------------------------------------------------------------------------

@app.get("/analytics/overview")
def analytics_overview(db: Session = Depends(get_db)):
    try:
        all_subs = db.query(Submission).all()
        total = len(all_subs)
        urgent_count = sum(1 for s in all_subs if s.urgency_level in ("high", "critical"))
        languages = {s.detected_language for s in all_subs if s.detected_language}
        areas = {s.location_mentioned for s in all_subs if s.location_mentioned}

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        def ts(s):
            t = s.timestamp
            if t and t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            return t

        submissions_today = sum(1 for s in all_subs if ts(s) and ts(s) >= today_start)
        submissions_this_week = sum(1 for s in all_subs if ts(s) and ts(s) >= week_start)

        category_counter = Counter(s.category for s in all_subs if s.category)
        category_urgent = Counter(s.category for s in all_subs if s.category and s.urgency_level in ("high", "critical"))
        category_breakdown = [
            {"category": cat, "count": count, "urgent_count": category_urgent.get(cat, 0)}
            for cat, count in category_counter.most_common()
        ]

        language_counter = Counter(s.detected_language for s in all_subs if s.detected_language)
        language_breakdown = [{"language": l, "count": c} for l, c in language_counter.most_common()]

        sentiment_breakdown = {
            "desperate": sum(1 for s in all_subs if s.sentiment == "desperate"),
            "frustrated": sum(1 for s in all_subs if s.sentiment == "frustrated"),
            "neutral": sum(1 for s in all_subs if s.sentiment == "neutral"),
            "hopeful": sum(1 for s in all_subs if s.sentiment == "hopeful"),
        }

        channel_counter = Counter(s.source_channel for s in all_subs if s.source_channel)
        channel_breakdown = [{"channel": c, "count": n} for c, n in channel_counter.most_common()]

        urgency_counter = Counter(s.urgency_level for s in all_subs if s.urgency_level)
        urgency_breakdown = [{"level": l, "count": n} for l, n in urgency_counter.most_common()]

        location_counter = Counter(s.location_mentioned for s in all_subs if s.location_mentioned)
        top_locations = [{"location": l, "count": n} for l, n in location_counter.most_common(10)]

        thirty_days_ago = now - timedelta(days=30)
        daily_counts = defaultdict(int)
        for s in all_subs:
            t = ts(s)
            if t and t >= thirty_days_ago:
                daily_counts[t.date().isoformat()] += 1
        submissions_over_time = [
            {"date": d, "count": c} for d, c in sorted(daily_counts.items())
        ]

        return {
            "total_submissions": total,
            "urgent_count": urgent_count,
            "languages_detected": len(languages),
            "areas_covered": len(areas),
            "submissions_today": submissions_today,
            "submissions_this_week": submissions_this_week,
            "category_breakdown": category_breakdown,
            "language_breakdown": language_breakdown,
            "sentiment_breakdown": sentiment_breakdown,
            "channel_breakdown": channel_breakdown,
            "urgency_breakdown": urgency_breakdown,
            "top_locations": top_locations,
            "submissions_over_time": submissions_over_time,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/demographics")
def analytics_demographics(db: Session = Depends(get_db)):
    try:
        blocks = db.query(Block).all()
        all_subs = [s.to_dict() for s in db.query(Submission).all()]

        result = []
        for block in blocks:
            block_dict = block.to_dict()
            block_subs = [s for s in all_subs if s.get("location_mentioned") == block.block_name]
            category_counter = Counter(s.get("category") for s in block_subs if s.get("category"))
            top_category = category_counter.most_common(1)[0][0] if category_counter else None

            drfi_scores = {}
            for category in CATEGORY_LIST:
                cat_subs = [s for s in block_subs if s.get("category") == category]
                drfi_scores[category] = drfi_engine.calculate_drfi_score(block_dict, category, cat_subs)

            block_dict["submission_count"] = len(block_subs)
            block_dict["top_category"] = top_category
            block_dict["drfi_scores"] = drfi_scores
            result.append(block_dict)

        return {"blocks": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/counter_narratives")
def analytics_counter_narratives(db: Session = Depends(get_db)):
    try:
        blocks = db.query(Block).all()
        all_subs = [s.to_dict() for s in db.query(Submission).all()]

        results = []
        for block in blocks:
            block_dict = block.to_dict()
            block_subs = [s for s in all_subs if s.get("location_mentioned") == block.block_name]
            categories_present = {s.get("category") for s in block_subs if s.get("category")}
            for category in categories_present:
                cat_subs = [s for s in block_subs if s.get("category") == category]
                cn = drfi_engine.detect_counter_narrative(block_dict, category, len(cat_subs))
                if cn:
                    results.append(
                        {
                            "block_name": block.block_name,
                            "category": category,
                            "submission_count": len(cat_subs),
                            "existing_infrastructure": block.existing_plans,
                            "flag_reason": cn["note"],
                        }
                    )
        return {"counter_narratives": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analytics/silent_needs")
def analytics_silent_needs(db: Session = Depends(get_db)):
    try:
        blocks = [b.to_dict() for b in db.query(Block).all()]
        all_subs = [s.to_dict() for s in db.query(Submission).all()]
        results = drfi_engine.detect_silent_needs(blocks, all_subs)
        return {"silent_needs": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


CATEGORY_LIST = [
    "Roads", "Water", "Education", "Healthcare", "Electricity",
    "Sanitation", "Agriculture", "Housing", "Digital", "Employment", "Other",
]


# ---------------------------------------------------------------------------
# RANKINGS ROUTES
# ---------------------------------------------------------------------------

@app.post("/rankings/generate")
def generate_rankings(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    try:
        require_mp_user(db, authorization)

        all_subs = [s.to_dict() for s in db.query(Submission).all()]
        all_blocks = [b.to_dict() for b in db.query(Block).all()]

        llm_rankings = llm_processor.generate_rankings_with_llm(all_subs, all_blocks)

        # Also compute DRFI engine scores for every block+category combination for reference
        drfi_matrix = []
        for block in all_blocks:
            block_subs = [s for s in all_subs if s.get("location_mentioned") == block.get("block_name")]
            for category in CATEGORY_LIST:
                cat_subs = [s for s in block_subs if s.get("category") == category]
                if not cat_subs:
                    continue
                drfi_matrix.append(drfi_engine.calculate_drfi_score(block, category, cat_subs))

        saved = []
        for rec in llm_rankings:
            ranking = Ranking(
                priority_rank=rec.get("priority_rank"),
                development_work=rec.get("development_work"),
                category=rec.get("category"),
                justification=rec.get("justification"),
                citizen_demand_evidence=rec.get("citizen_demand_evidence"),
                estimated_beneficiaries=rec.get("estimated_beneficiaries"),
                suggested_action=rec.get("suggested_action"),
                funding_source=rec.get("funding_source"),
                urgency_score=rec.get("urgency_score"),
                demand_score=rec.get("demand_score"),
                data_alignment_score=rec.get("data_alignment_score"),
                equity_score=rec.get("equity_score"),
                cascading_impact_score=rec.get("cascading_impact_score"),
                drfi_score=rec.get("drfi_score"),
                counter_narrative_flag=rec.get("counter_narrative_flag", False),
                counter_narrative_note=rec.get("counter_narrative_note"),
                silent_need_flag=rec.get("silent_need_flag", False),
                silent_need_note=rec.get("silent_need_note"),
            )
            db.add(ranking)
            saved.append(ranking)
        db.commit()
        for r in saved:
            db.refresh(r)

        return {
            "rankings": [r.to_dict() for r in saved],
            "drfi_matrix": drfi_matrix,
        }
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rankings/latest")
def rankings_latest(db: Session = Depends(get_db)):
    try:
        latest_gen = db.query(func.max(Ranking.generated_at)).scalar()
        if not latest_gen:
            return {"rankings": [], "message": "Generate rankings first"}
        rows = (
            db.query(Ranking)
            .filter(Ranking.generated_at == latest_gen)
            .order_by(Ranking.priority_rank.asc())
            .all()
        )
        return {"rankings": [r.to_dict() for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rankings/history")
def rankings_history(db: Session = Depends(get_db)):
    try:
        rows = db.query(Ranking).order_by(Ranking.generated_at.desc()).all()
        grouped = defaultdict(list)
        for r in rows:
            grouped[r.generated_at.isoformat()].append(r.to_dict())
        history = [{"generated_at": ts, "rankings": recs} for ts, recs in grouped.items()]
        return {"history": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# MAPS / GEOGRAPHIC ROUTES
# ---------------------------------------------------------------------------

@app.get("/maps/submission_heatmap")
def maps_submission_heatmap(db: Session = Depends(get_db)):
    try:
        rows = db.query(Submission).filter(
            Submission.latitude.isnot(None), Submission.longitude.isnot(None)
        ).all()
        points = [
            {
                "latitude": s.latitude,
                "longitude": s.longitude,
                "category": s.category,
                "urgency_level": s.urgency_level,
                "weight": URGENCY_WEIGHT.get(s.urgency_level, 1),
            }
            for s in rows
        ]
        return {"points": points}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/maps/block_markers")
def maps_block_markers(db: Session = Depends(get_db)):
    try:
        blocks = db.query(Block).all()
        all_subs = [s.to_dict() for s in db.query(Submission).all()]

        markers = []
        for block in blocks:
            block_dict = block.to_dict()
            block_subs = [s for s in all_subs if s.get("location_mentioned") == block.block_name]
            category_counter = Counter(s.get("category") for s in block_subs if s.get("category"))
            top_need = category_counter.most_common(1)[0][0] if category_counter else None

            best_drfi = 0.0
            for category in CATEGORY_LIST:
                cat_subs = [s for s in block_subs if s.get("category") == category]
                if not cat_subs:
                    continue
                score = drfi_engine.calculate_drfi_score(block_dict, category, cat_subs)["drfi_score"]
                best_drfi = max(best_drfi, score)

            markers.append(
                {
                    "block_name": block.block_name,
                    "latitude": block.latitude,
                    "longitude": block.longitude,
                    "drfi_score": best_drfi,
                    "top_need": top_need,
                    "submission_count": len(block_subs),
                }
            )
        return {"markers": markers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/maps/block/{block_name}")
def maps_block_detail(block_name: str, db: Session = Depends(get_db)):
    try:
        block = db.query(Block).filter(Block.block_name == block_name).first()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")

        block_dict = block.to_dict()
        subs = (
            db.query(Submission)
            .filter(Submission.location_mentioned == block_name)
            .order_by(Submission.timestamp.desc())
            .all()
        )
        subs_dicts = [s.to_dict() for s in subs]

        drfi_scores = {}
        for category in CATEGORY_LIST:
            cat_subs = [s for s in subs_dicts if s.get("category") == category]
            drfi_scores[category] = drfi_engine.calculate_drfi_score(block_dict, category, cat_subs)

        return {
            "block": block_dict,
            "submissions": subs_dicts,
            "drfi_scores": drfi_scores,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# CITIZEN ROUTES
# ---------------------------------------------------------------------------

@app.get("/citizen/submissions/{citizen_id}")
def citizen_submissions(citizen_id: int, db: Session = Depends(get_db)):
    try:
        rows = (
            db.query(Submission)
            .filter(Submission.citizen_id == citizen_id)
            .order_by(Submission.timestamp.desc())
            .all()
        )
        results = []
        for s in rows:
            d = s.to_dict()
            if d.get("budget_released"):
                d["status_message"] = f"✅ Budget of ₹{d.get('budget_amount'):,.0f} released for this request"
            elif d.get("status") == "resolved":
                d["status_message"] = "✅ This issue has been resolved"
            else:
                d["status_message"] = None
            results.append(d)
        return {"count": len(results), "submissions": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/citizen/public_stats")
def citizen_public_stats(db: Session = Depends(get_db)):
    try:
        all_subs = db.query(Submission).all()
        total = len(all_subs)
        category_counter = Counter(s.category for s in all_subs if s.category)
        top_category = category_counter.most_common(1)[0][0] if category_counter else None
        languages = {s.detected_language for s in all_subs if s.detected_language}
        active_needs = sum(1 for s in all_subs if s.status not in ("resolved",))

        return {
            "total_submissions": total,
            "top_category": top_category,
            "languages_count": len(languages),
            "active_needs": active_needs,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
def root():
    return {"message": "JanaNiti backend is running. Visit /docs for API documentation."}

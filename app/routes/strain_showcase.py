import json
import re

from flask import Blueprint, abort, render_template, request, url_for
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import load_only, selectinload

from app.extensions import db
from app.models import BacdiveRecord, BacdiveStrainMatch, SilvaSsuSequence, Strain, StrainMedium


strain_showcase_bp = Blueprint("strain_showcase", __name__, url_prefix="/strain_showcase")


def _static_image_url(path):
    if not path:
        return url_for("static", filename="uploads/placeholder.png")
    if path.startswith(("http://", "https://", "//", "/")):
        return path
    if path.startswith("static/"):
        return f"/{path}"
    return url_for("static", filename=path)


def _clean_json(value):
    if value in (None, {}, [], ""):
        return None
    return value


def _parse_json_text(value):
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except (TypeError, ValueError):
        return value


def _page_window(pagination, radius=2):
    total_pages = pagination.pages or 1
    start_page = max(1, pagination.page - radius)
    end_page = min(total_pages, pagination.page + radius)
    return range(start_page, end_page + 1), total_pages, start_page, end_page


def _silva_species_name(record):
    species_name = (record.species_name or "").strip()
    parts = species_name.split()
    generic_names = {"sp", "spp", "bacterium", "archaeon"}
    if len(parts) < 2 or parts[1].lower().rstrip(".") in generic_names:
        return None
    return species_name


def _find_silva_sequences(record, limit=8):
    species_name = _silva_species_name(record)
    genus_name = (record.genus_name or "").strip()
    if not species_name or not genus_name:
        return []

    escaped_species = species_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    exact_match = SilvaSsuSequence.organism_name == species_name
    return (
        SilvaSsuSequence.query
        .filter(SilvaSsuSequence.genus_name == genus_name)
        .filter(or_(
            exact_match,
            SilvaSsuSequence.organism_name.like(
                f"{escaped_species} %", escape="\\"
            ),
        ))
        .order_by(exact_match.desc(), func.abs(SilvaSsuSequence.sequence_length - 1500))
        .limit(limit)
        .all()
    )




@strain_showcase_bp.route("/", methods=["GET"])
def index():
    query_text = request.args.get("q", "").strip()
    domain = request.args.get("domain", "").strip()
    type_strain = request.args.get("type_strain", "").strip().lower()
    genus = request.args.get("genus", "").strip()
    environment_only = request.args.get("environment_only") == "1"
    page = request.args.get("page", 1, type=int)
    per_page = 24

    query = BacdiveRecord.query

    if query_text:
        pattern = f"%{query_text}%"
        if re.search(r"[一-鿿]", query_text):
            query = query.filter(BacdiveRecord.species_name_zh.ilike(pattern))
        else:
            query = query.filter(
                or_(
                    cast(BacdiveRecord.bacdive_id, String).ilike(pattern),
                    BacdiveRecord.dsm_number.ilike(pattern),
                    BacdiveRecord.full_scientific_name.ilike(pattern),
                    BacdiveRecord.species_name.ilike(pattern),
                    BacdiveRecord.strain_designation.ilike(pattern),
                    BacdiveRecord.description.ilike(pattern),
                    BacdiveRecord.keywords.ilike(pattern),
                )
            )
    if domain:
        query = query.filter(BacdiveRecord.domain_name == domain)
    if type_strain in {"yes", "no"}:
        query = query.filter(func.lower(BacdiveRecord.type_strain) == type_strain)
    if genus:
        query = query.filter(BacdiveRecord.genus_name.ilike(f"%{genus}%"))
    if environment_only:
        query = query.join(BacdiveStrainMatch).distinct()

    query = query.options(
        load_only(
            BacdiveRecord.id,
            BacdiveRecord.bacdive_id,
            BacdiveRecord.dsm_number,
            BacdiveRecord.domain_name,
            BacdiveRecord.family_name,
            BacdiveRecord.genus_name,
            BacdiveRecord.species_name,
            BacdiveRecord.species_name_zh,
            BacdiveRecord.full_scientific_name,
            BacdiveRecord.strain_designation,
            BacdiveRecord.type_strain,
            BacdiveRecord.description,
        )
    )
    pagination = query.order_by(BacdiveRecord.bacdive_id.asc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )

    record_ids = [record.id for record in pagination.items]
    environment_by_record = {}
    if record_ids:
        matches = (
            BacdiveStrainMatch.query.options(selectinload(BacdiveStrainMatch.strain))
            .filter(BacdiveStrainMatch.bacdive_record_id.in_(record_ids))
            .all()
        )
        for match in matches:
            if match.strain and match.strain.is_active:
                environment_by_record.setdefault(match.bacdive_record_id, match.strain)

    page_range, total_pages, start_page, end_page = _page_window(pagination)
    stats = {
        "records": db.session.query(func.count(BacdiveRecord.id)).scalar() or 0,
        "type_strains": (
            db.session.query(func.count(BacdiveRecord.id))
            .filter(func.lower(BacdiveRecord.type_strain) == "yes")
            .scalar()
            or 0
        ),
        "environment_records": (
            db.session.query(func.count(func.distinct(BacdiveStrainMatch.bacdive_record_id))).scalar()
            or 0
        ),
    }

    return render_template(
        "strain_showcase/index.html",
        records=pagination.items,
        pagination=pagination,
        environment_by_record=environment_by_record,
        stats=stats,
        filters={
            "q": query_text,
            "domain": domain,
            "type_strain": type_strain,
            "genus": genus,
            "environment_only": environment_only,
        },
        page_range=page_range,
        total_pages=total_pages,
        start_page=start_page,
        end_page=end_page,
    )


@strain_showcase_bp.route("/<int:record_id>")
def detail(record_id):
    record = BacdiveRecord.query.options(
        selectinload(BacdiveRecord.environment_matches).selectinload(BacdiveStrainMatch.strain)
    ).filter_by(id=record_id).first_or_404()

    environment_strains = []
    seen_ids = set()
    for match in record.environment_matches:
        strain = match.strain
        if strain and strain.is_active and strain.id not in seen_ids:
            environment_strains.append(strain)
            seen_ids.add(strain.id)

    if environment_strains:
        strain_ids = [strain.id for strain in environment_strains]
        environment_strains = (
            Strain.query.options(
                selectinload(Strain.growth_cycles),
                selectinload(Strain.media_links).selectinload(StrainMedium.medium),
                selectinload(Strain.morphology),
                selectinload(Strain.sources),
                selectinload(Strain.strain_16s_records),
            )
            .filter(Strain.id.in_(strain_ids))
            .all()
        )

    silva_sequences = _find_silva_sequences(record)

    data_sections = [
        ("培养基", _clean_json(record.culture_medium)),
        ("培养温度", _clean_json(record.culture_temp)),
        ("培养 pH", _clean_json(record.culture_ph)),
        ("形态学", _clean_json(record.morphology)),
        ("生理与代谢", _clean_json(record.physiology)),
        ("分离与环境信息", _clean_json(record.isolation_info)),
        ("安全性", _clean_json(record.safety_info)),
        ("序列信息", _clean_json(record.sequence_info)),
        ("文献", _clean_json(record.literature_info)),
    ]

    taxonomy = [
        ("域", record.domain_name),
        ("门", record.phylum_name),
        ("纲", record.class_name),
        ("目", record.order_name),
        ("科", record.family_name),
        ("属", record.genus_name),
        ("种", record.species_name),
    ]

    return render_template(
        "strain_showcase/detail.html",
        record=record,
        taxonomy=taxonomy,
        silva_sequences=silva_sequences,
        data_sections=data_sections,
        strain_history=_parse_json_text(record.strain_history),
        environment_strains=environment_strains,
        static_image_url=_static_image_url,
    )


@strain_showcase_bp.route("/environment/<int:strain_id>")
def environment_detail(strain_id):
    strain = Strain.query.filter_by(id=strain_id, is_active=True).first()
    if not strain:
        abort(404)
    record = (
        BacdiveRecord.query.join(BacdiveStrainMatch)
        .filter(BacdiveStrainMatch.strain_id == strain.id)
        .order_by(BacdiveRecord.bacdive_id)
        .first()
    )
    if record:
        return detail(record.id)
    abort(404)

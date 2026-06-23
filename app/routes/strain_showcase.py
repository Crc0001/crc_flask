from flask import Blueprint, render_template, request, url_for
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from app.models import Strain, StrainMedium

strain_showcase_bp = Blueprint("strain_showcase", __name__, url_prefix="/strain_showcase")


def _static_image_url(path):
    if not path:
        return url_for("static", filename="uploads/placeholder.png")
    if path.startswith(("http://", "https://", "//", "/")):
        return path
    if path.startswith("static/"):
        return f"/{path}"
    return url_for("static", filename=path)


def _normalize_rank(rank):
    if not rank:
        return ""
    normalized = rank.strip().lower()
    rank_map = {
        "目": "order",
        "order": "order",
        "科": "family",
        "family": "family",
        "属": "genus",
        "genus": "genus",
        "种": "species",
        "species": "species",
    }
    return rank_map.get(normalized, normalized)


def _taxonomy_lineage_names(taxonomy):
    lineage = {"family": "-", "genus": "-", "species": "-"}
    current = taxonomy

    while current:
        key = _normalize_rank(getattr(current, "strain_rank", None))
        if key in lineage and lineage[key] == "-" and current.name:
            lineage[key] = current.name
        current = current.parent

    return lineage


@strain_showcase_bp.route("/", methods=["GET"])
def index():
    query_text = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 12

    query = Strain.query.filter(Strain.is_active.is_(True))

    if query_text:
        pattern = f"%{query_text}%"
        query = query.filter(
            or_(
                Strain.name.ilike(pattern),
                Strain.scientific_name.ilike(pattern),
                Strain.category.ilike(pattern),
            )
        )

    pagination = query.order_by(Strain.name).paginate(page=page, per_page=per_page, error_out=False)

    total_pages = pagination.pages or 1
    start_page = max(1, pagination.page - 2)
    end_page = min(total_pages, pagination.page + 2)
    page_range = range(start_page, end_page + 1)

    return render_template(
        "strain_showcase/index.html",
        strains=pagination.items,
        pagination=pagination,
        query=query_text,
        page_range=page_range,
        total_pages=total_pages,
        start_page=start_page,
        end_page=end_page,
    )


@strain_showcase_bp.route("/<int:strain_id>")
def detail(strain_id):
    strain = Strain.query.options(
        selectinload(Strain.growth_cycles),
        selectinload(Strain.media_links).selectinload(StrainMedium.medium),
        selectinload(Strain.morphology),
        selectinload(Strain.taxonomy),
        selectinload(Strain.sources),
        selectinload(Strain.strain_16s_records),
    ).filter_by(id=strain_id).first_or_404()

    growth_cycles = strain.growth_cycles[:3]
    morphology = strain.morphology
    recommended_mediums = [link for link in strain.media_links if link.is_recommended and link.medium]
    common_sources = []
    seen_sources = set()
    for source in strain.sources:
        location = (source.location or "").strip()
        if location and location not in seen_sources:
            common_sources.append(location)
            seen_sources.add(location)

    if not recommended_mediums:
        recommended_mediums = [link for link in strain.media_links if link.medium]

    # 获取 16S 序列（取第一条）
    strain_16s_sequence = None
    if strain.strain_16s_records:
        strain_16s_sequence = strain.strain_16s_records[0].strain_16s

    taxonomy_lineage = _taxonomy_lineage_names(strain.taxonomy)
    taxonomy_info = {
        "latin_name": strain.scientific_name or "-",
        "alias": strain.alias or "-",
        "family_name": taxonomy_lineage["family"],
        "genus_name": taxonomy_lineage["genus"],
        "species_name": taxonomy_lineage["species"],
        "chinese_name": strain.name or "-",
    }

    return render_template(
        "strain_showcase/detail.html",
        strain=strain,
        growth_cycles=growth_cycles,
        morphology=morphology,
        recommended_mediums=recommended_mediums,
        common_sources=common_sources,
        fingerprint_image_url=_static_image_url(strain.fingerprint_image),
        gram_stain_image_url=_static_image_url(strain.gram_stain_image),
        taxonomy_info=taxonomy_info,
        strain_16s_sequence=strain_16s_sequence,
    )

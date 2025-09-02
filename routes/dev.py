"""
Development and debugging routes for NYU CLASS Professor Review System

This module contains routes for debugging and development utilities.
"""

import os
import random
import mimetypes
from datetime import datetime
from flask import Blueprint, abort, redirect, url_for, flash, jsonify, current_app
from sqlalchemy import func
from utils.decorators import admin_required

# This will be set by the main app
db = None
Submission = None
Evidence = None
ReviewStatus = None

# Create dev blueprint
dev_bp = Blueprint('dev', __name__)


@dev_bp.route("/dev/seed10")
@admin_required  # Require admin authentication
def dev_seed10():
    # 开发模式下允许公开种子数据注入，生产环境禁止
    if not current_app.debug:
        abort(404)

    now = datetime.utcnow()
    # 可复用的现有图片文件
    image_dir = current_app.config["IMAGE_UPLOAD_DIR"]
    try:
        image_files = [
            os.path.join(image_dir, f)
            for f in os.listdir(image_dir)
            if os.path.isfile(os.path.join(image_dir, f))
        ]
    except FileNotFoundError:
        image_files = []

    # 词库（用于生成50词描述，词之间以空格分隔）
    word_bank = [
        "讲解清晰", "案例充分", "节奏适中", "互动较多", "作业适中", "考核透明", "评分合理", "材料扎实", "视角独特",
        "逻辑严谨", "思辨训练", "实践导向", "反馈及时", "课件完善", "阅读充足", "工作量稳定", "难度中等",
        "TA给力", "课堂友好", "尊重学生", "准备充分", "结构清楚", "层次分明", "知识面广", "拓展深入",
        "表达流畅", "启发思考", "讨论充分", "示范到位", "作业指导", "评分标准", "复习提示", "复盘到位",
        "资源丰富", "案例真实", "联系实际", "学术规范", "边界明确", "时间管理", "节奏把控", "氛围良好",
        "建议提前", "预习材料", "团队合作", "展示训练", "研究方法", "工具使用", "面向问题", "持续改进"
    ]

    def generate_desc(n: int = 50) -> str:
        if not word_bank:
            return "优质课程 体验良好" * n
        tokens = [random.choice(word_bank) for _ in range(n)]
        return " ".join(tokens)

    submissions: list[Submission] = []
    evidences: list[Evidence] = []

    for i in range(10):
        prof_cn = f"测试教授{i+1}号"
        prof_en = f"Professor Test {i+1}"
        uid = f"pt{i+1:02d}{random.randint(1000,9999)}"
        sub = Submission(
            submitter_email=f"seed{i+1}@nyu.edu",
            professor_cn_name=prof_cn,
            professor_en_name=prof_en,
            professor_unique_identifier=uid,
            description=generate_desc(50),
            tag_positive=bool(random.getrandbits(1)),
            tag_calm=bool(random.getrandbits(1)),
            tag_leadership=bool(random.getrandbits(1)),
            tag_homework_heavy=bool(random.getrandbits(1)),
            tag_custom=("课堂严谨" if random.random() < 0.4 else None),
            allow_public_evidence=True,
            privacy_homepage=True,
            status=ReviewStatus.APPROVED,
            created_at=now,
            updated_at=now,
        )
        submissions.append(sub)
        db.session.add(sub)
        db.session.flush()

        # 证据：复用已有图片文件；如无图片则跳过证据
        if image_files:
            img_path = random.choice(image_files)
            evidences.append(
                Evidence(
                    submission_id=sub.id,
                    category="image",
                    file_path=img_path,
                    original_filename=os.path.basename(img_path),
                    mime_type=mimetypes.guess_type(img_path)[0] or "image/png",
                    file_size=os.path.getsize(img_path) if os.path.exists(img_path) else None,
                )
            )

    if evidences:
        db.session.add_all(evidences)
    db.session.commit()
    flash("已生成10条测试数据（含图片），均允许展示在首页。", "success")
    return redirect(url_for("main.index"))


@dev_bp.route("/dev/diag")
def dev_diag():
    if not current_app.debug:
        abort(404)
    # Mirror homepage query
    qs = (
        Submission.query
        .filter(
            Submission.status == ReviewStatus.APPROVED,
            Submission.privacy_homepage.is_(True),
        )
        .order_by(Submission.updated_at.desc())
        .limit(12)
    )
    items = qs.all()
    return jsonify({
        "db_uri": current_app.config.get("SQLALCHEMY_DATABASE_URI"),
        "homepage_count": len(items),
        "homepage_ids": [s.id for s in items],
        "approved_privacy_total": db.session.query(func.count(Submission.id)).filter(Submission.status == ReviewStatus.APPROVED, Submission.privacy_homepage.is_(True)).scalar(),
    })


def init_dev_routes(database_instance, models):
    """Initialize dev routes with required dependencies"""
    global db, Submission, Evidence, ReviewStatus
    
    db = database_instance
    Submission = models['Submission']
    Evidence = models['Evidence']
    ReviewStatus = models['ReviewStatus']
    
    return dev_bp
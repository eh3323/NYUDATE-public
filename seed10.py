from datetime import datetime
import random
import os
import sys

# 确保可从脚本目录的上级导入 app.py
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app, db, Submission, ReviewStatus, ensure_schema_migrations


WORD_BANK = [
    "初见微笑", "细致体贴", "偶有摩擦", "沟通顺畅", "相互理解", "步调不一", "逐渐靠近", "分享日常",
    "认真聆听", "情绪起伏", "坦诚交流", "彼此支持", "期待未来", "偶有分歧", "冷静思考", "相互尊重",
    "共同成长", "信任慢慢", "用心相处", "小有惊喜", "温柔坚定", "认真负责", "学会退让", "包容彼此",
    "勇敢表达", "尊重边界", "彼此关照", "温暖陪伴", "保持距离", "慢慢靠拢", "互相体谅", "偶尔误解",
]


def generate_story(target_len: int = 50) -> str:
    tokens: list[str] = []
    total = 0
    limit = target_len + random.randint(-6, 8)
    while total < limit:
        w = random.choice(WORD_BANK)
        tokens.append(w)
        total += len(w)
    text = "，".join(tokens) + "。"
    # 裁切到 ~50 字范围
    if len(text) > 70:
        text = text[:70]
    return text


def choose_tags() -> dict:
    tags = {
        "tag_positive": bool(random.getrandbits(1)),
        "tag_calm": bool(random.getrandbits(1)),
        "tag_leadership": bool(random.getrandbits(1)),
        "tag_homework_heavy": bool(random.getrandbits(1)),
    }
    if not any(tags.values()):
        # 至少保证一个标签为 True
        key = random.choice(list(tags.keys()))
        tags[key] = True
    return tags


def run_insert(n: int = 10):
    with app.app_context():
        db.create_all()
        ensure_schema_migrations()

        now = datetime.utcnow()
        new_items: list[Submission] = []

        for i in range(n):
            tags = choose_tags()
            sub = Submission(
                submitter_email=f"seed{i+1}@nyu.edu",
                professor_cn_name=f"样本{i+1}号",
                description=generate_story(50),
                allow_public_evidence=False,
                privacy_homepage=True,  # 首页可见
                status=ReviewStatus.APPROVED,  # 已审核
                created_at=now,
                updated_at=now,
                **tags,
            )
            db.session.add(sub)
            new_items.append(sub)

        db.session.commit()

        ids = [s.id for s in new_items]
        total_homepage = (
            db.session.query(Submission)
            .filter(Submission.status == ReviewStatus.APPROVED, Submission.privacy_homepage.is_(True))
            .count()
        )
        print({
            "inserted_ids": ids,
            "homepage_approved_total": total_homepage,
        })


if __name__ == "__main__":
    run_insert(10)



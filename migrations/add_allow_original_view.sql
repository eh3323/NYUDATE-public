-- 添加 allow_original_view 字段到 evidences 表
-- 该字段用于控制是否允许公众查看原始文件

ALTER TABLE evidences 
ADD COLUMN IF NOT EXISTS allow_original_view BOOLEAN DEFAULT FALSE NOT NULL;

-- 为现有记录设置默认值为 FALSE (保持当前行为)
UPDATE evidences 
SET allow_original_view = FALSE 
WHERE allow_original_view IS NULL;

-- 添加注释
COMMENT ON COLUMN evidences.allow_original_view IS '是否允许公众查看原件（TRUE=查看原件，FALSE=仅查看缩略图）';
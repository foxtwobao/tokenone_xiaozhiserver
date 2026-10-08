-- Explicit, per-agent Omni mode. Existing agents default to the original pipeline.
ALTER TABLE ai_agent
  ADD COLUMN model_mode varchar(16) NOT NULL DEFAULT 'separate' COMMENT 'separate/omni',
  ADD COLUMN omni_model_id varchar(64) DEFAULT NULL COMMENT 'Standalone OMNI model';

-- Reuse existing credentials and model IDs, without maintaining duplicate entries.
SET @legacy_llm = (SELECT id FROM ai_model_config WHERE model_type = 'LLM'
  AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')), '') <> 'qwen_omni'
  AND is_enabled = 1 ORDER BY is_default DESC, sort, id LIMIT 1);
SET @legacy_asr = (SELECT id FROM ai_model_config WHERE model_type = 'ASR'
  AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')), '') <> 'omni_audio'
  AND is_enabled = 1 ORDER BY is_default DESC, sort, id LIMIT 1);
UPDATE ai_agent a JOIN ai_model_config m ON a.llm_model_id = m.id
  SET a.model_mode = 'omni', a.omni_model_id = m.id, a.llm_model_id = @legacy_llm
  WHERE m.model_type = 'LLM' AND JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.type')) = 'qwen_omni';
UPDATE ai_agent a JOIN ai_model_config m ON a.asr_model_id = m.id
  SET a.asr_model_id = @legacy_asr
  WHERE a.model_mode = 'omni' AND JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.type')) = 'omni_audio';
UPDATE ai_agent_snapshot s JOIN ai_model_config m
  ON JSON_UNQUOTE(JSON_EXTRACT(s.snapshot_data, '$.llmModelId')) = m.id
  SET s.snapshot_data = JSON_SET(s.snapshot_data, '$.modelMode', 'omni', '$.omniModelId', m.id,
    '$.llmModelId', @legacy_llm)
  WHERE m.model_type = 'LLM' AND JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.type')) = 'qwen_omni';
UPDATE ai_model_config SET model_type = 'OMNI', is_default = 0,
  remark = '独立多模态模型；在智能体中选择 Omni 模式，与 ASR/LLM/VLLM 互斥，TTS 单独配置。'
  WHERE model_type = 'LLM' AND JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')) = 'qwen_omni';
UPDATE ai_model_provider SET model_type = 'OMNI', name = 'Qwen Omni 多模态',
  fields = JSON_ARRAY(
    JSON_OBJECT('key','api_key','label','API密钥','type','password'),
    JSON_OBJECT('key','base_url','label','兼容接口地址','type','string'),
    JSON_OBJECT('key','model_name','label','模型名称','type','string'),
    JSON_OBJECT('key','reasoning_effort','label','思考强度（none/low/medium/xhigh）','type','string'),
    JSON_OBJECT('key','max_tokens','label','最大输出Token','type','number'),
    JSON_OBJECT('key','max_audio_seconds','label','单轮最长录音秒数（1-120）','type','number'))
  WHERE provider_code = 'qwen_omni' AND model_type = 'LLM';
-- Retain obsolete rows outside user-facing model categories for audit/history.
UPDATE ai_model_config SET model_type = 'INTERNAL', is_enabled = 0, is_default = 0
  WHERE model_type = 'ASR' AND JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')) = 'omni_audio';
DELETE FROM ai_model_provider WHERE model_type = 'ASR' AND provider_code = 'omni_audio';
